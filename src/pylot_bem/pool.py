"""Solving in a pool of worker processes, one frequency per task.

Why a process and not a thread (spec 06 section 6.3, decided): the Fortran
extension carries no ``!f2py threadsafe`` directive, so f2py never emits
``Py_BEGIN_ALLOW_THREADS`` and **the GIL is held for the whole matrix
assembly**. A worker thread would freeze the interface for the duration of a
single problem -- exactly what the worker was for. A process also gives the one
thing Capytaine has no mechanism for at all: interruption. Terminating a
process kills a Fortran call mid-flight.

**One frequency is one task.** That is Capytaine's own grouping key, and it is
what keeps the influence-matrix cache warm: the cache holds exactly one entry,
so every problem at one frequency -- six radiation dofs plus every wave
direction -- must run consecutively in one process or the O(N^2) assembly is
repeated for each. Never split a frequency across workers and never interleave
frequencies within one.

A pool of one worker is still a separate process, so parallelism is a
**setting** rather than a second code path.

See ``docs/spec/06_ui_and_integration.md`` sections 6.2 to 6.5.
"""

import os
import threading
import time
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from dataclasses import dataclass, field, replace

import numpy as np
import xarray as xr
from pylot_db.entities import FloatArray, IntArray

from pylot_bem.solver import SolveSettings, solve

__all__ = [
    "PoolSolve",
    "Progress",
    "SolveOutcome",
    "default_workers",
]

# Spec 09 section E.1: all parallelism in the process layer, one core left for
# the interface. Presumes an 8-core machine, so it is clamped to the real one.
PREFERRED_WORKERS = 7

# How often the run loop looks up from waiting to notice a stop or a kill.
# Short enough that Kill feels immediate, long enough not to spin.
_POLL_SECONDS = 0.2

type Progress = Callable[["SolveOutcome"], None]


def default_workers(n_frequencies: int) -> int:
    """How many workers to use when the caller does not say.

    Clamped to the frequency count -- more workers than frequencies is pure
    waste -- and to the machine, leaving a core for the interface.

    Memory can bind before cores do (spec 06 section 6.5): each worker holds
    two dense complex matrices, so a 5000-panel mesh costs about 800 MB
    *each*. The caller is expected to show that figure next to the setting; it
    is not clamped here because this module does not know the mesh.
    """
    cores = os.cpu_count() or 1
    return max(1, min(PREFERRED_WORKERS, cores - 1, n_frequencies))


@dataclass(frozen=True, slots=True)
class SolveOutcome:
    """What has been solved so far.

    Handed to the progress callback as each frequency lands, and returned when
    the run finishes.

    Attributes:
        requested: Every frequency the run was asked for [rad/s], ascending.
        solved: The frequencies that came back, ascending. Under several
            workers a cancelled run leaves **holes**, not a prefix, so this is
            the set and not a count.
        failed: ``{omega: message}`` for frequencies whose worker raised. A
            group that fails must not silently vanish from the grid.
        elapsed: Seconds since the run started.
        stopped: Whether the run ended early, by either tier.
        killed: Whether it ended by :meth:`PoolSolve.kill` specifically.

            The two tiers leave **differently trustworthy** output, which
            is why this is recorded rather than left to the caller to
            remember. After ``stop`` every frequency that finished did so
            normally and nothing was interrupted; after ``kill`` a worker
            was terminated mid-call, so whatever it was computing is gone
            and the user reached for the emergency handle. What was already
            returned is equally complete in both cases -- the difference is
            in what the user meant, not in the numbers.
        dataset: The assembled result, or ``None`` while running and when
            nothing at all completed.
    """

    requested: tuple[float, ...]
    solved: tuple[float, ...] = ()
    failed: dict[float, str] = field(default_factory=dict)
    elapsed: float = 0.0
    stopped: bool = False
    killed: bool = False
    dataset: xr.Dataset | None = None

    @property
    def complete(self) -> bool:
        """Every requested frequency came back."""
        return len(self.solved) == len(self.requested) and not self.failed

    @property
    def missing(self) -> tuple[float, ...]:
        """Requested frequencies that are not in the result."""
        return tuple(w for w in self.requested if w not in set(self.solved))


def _solve_one_frequency(payload: tuple) -> xr.Dataset:
    """Solve every problem at one frequency. **Runs in a worker process.**

    Module level and taking a plain tuple because Windows has no ``fork``:
    every worker is a fresh ``spawn`` that re-imports this module and receives
    its argument by pickle. Arrays and scalars pickle cheaply and
    unambiguously; a Capytaine body does not.

    It calls the same :func:`~pylot_bem.solver.solve` the in-process path uses,
    with a one-frequency grid. There is deliberately no second implementation
    of the solve for the pool to drift away from.
    """
    vertices, faces, is_xz_symmetric, application_point, settings, omega = payload
    return solve(
        vertices,
        faces,
        is_xz_symmetric=is_xz_symmetric,
        application_point=application_point,
        settings=replace(settings, omegas=(omega,)),
    )


class PoolSolve:
    """One solve, in a pool, that can be watched and stopped.

    :meth:`run` blocks, so a user interface calls it on a worker thread and
    lets the callback marshal progress back. :meth:`stop` and :meth:`kill` are
    safe to call from another thread -- which is the whole point.

    Two tiers, because they cost different things (spec 06 section 6.3):

    ==========  ==========================================  ================
    Tier        Action                                      Latency
    ==========  ==========================================  ================
    ``stop()``  queued frequencies dropped, running ones     one frequency
                finish and are kept
    ``kill()``  worker processes terminated                  immediate
    ==========  ==========================================  ================

    Both keep whatever had already come back. Because the unit of work is a
    frequency, that partial output is not ragged -- it is a valid result over a
    shorter grid, which pylot-db's spec 02 section 3 already assembles from.
    """

    def __init__(
        self,
        vertices: FloatArray,
        faces: IntArray,
        *,
        is_xz_symmetric: bool,
        application_point: FloatArray,
        settings: SolveSettings,
        workers: int | None = None,
        omp_threads: int = 1,
    ) -> None:
        """Set up a run. Nothing is submitted until :meth:`run`.

        Args:
            vertices: ``(N, 3)`` diffraction-space coordinates.
            faces: ``(M, 3)`` triangle indices.
            is_xz_symmetric: Whether the geometry is a half vessel.
            application_point: ``(3,)`` in diffraction space.
            settings: The physical conditions. Its ``omegas`` are the tasks.
            workers: Processes to use. Defaults to :func:`default_workers`.
            omp_threads: OpenMP threads **inside** each worker. Must be set
                explicitly or every worker spawns ``cpu_count`` threads and
                they oversubscribe the machine together (spec 06 section 6.5).
        """
        self._vertices = np.asarray(vertices, dtype=float)
        self._faces = np.asarray(faces)
        self._is_xz_symmetric = bool(is_xz_symmetric)
        self._application_point = np.asarray(application_point, dtype=float)
        self._settings = settings
        self._omegas = tuple(float(w) for w in settings.omegas)
        self._workers = workers if workers is not None else default_workers(len(self._omegas))
        self._omp_threads = int(omp_threads)

        self._lock = threading.Lock()
        self._pool: ProcessPoolExecutor | None = None
        self._futures: list[Future] = []
        self._stopping = False
        self._killed = False

    # -- introspection -----------------------------------------------------

    @property
    def workers(self) -> int:
        return self._workers

    @property
    def worker_pids(self) -> tuple[int, ...]:
        """The live worker process ids.

        Exposed because "the solve stopped" and "the processes are gone" are
        different claims, and only the second one is worth testing. An
        orphaned worker holds ~800 MB and a full core for minutes.
        """
        with self._lock:
            pool = self._pool
        return tuple(p.pid for p in _live_processes(pool))

    # -- control -----------------------------------------------------------

    def stop(self) -> None:
        """Drop queued frequencies; let running ones finish and be kept.

        Cancels the pending futures rather than shutting the pool down.
        ``shutdown()`` mid-iteration is a trap: it drops the executor's result
        queue and manager thread, so a task that is **already running** never
        delivers its result, its future never resolves, and ``as_completed``
        waits for it forever. Cancelling only touches work that has not
        started, which is exactly what this tier promises.
        """
        with self._lock:
            self._stopping = True
            futures = list(self._futures)
        for future in futures:
            future.cancel()  # returns False for anything already running

    def kill(self) -> None:
        """Terminate the workers now. Running frequencies are lost.

        ``ProcessPoolExecutor.shutdown()`` does **not** do this -- it waits for
        the running task, which on a large mesh is minutes. Terminating the
        process is the only thing that interrupts a Fortran call.

        The futures of the killed tasks resolve as ``BrokenProcessPool``, so
        the run ends rather than hanging.
        """
        with self._lock:
            self._stopping = True
            self._killed = True
            futures = list(self._futures)
            processes = _live_processes(self._pool)

        for future in futures:
            future.cancel()
        for process in processes:
            process.kill()
        for process in processes:
            process.join(timeout=5.0)

    # -- the run -----------------------------------------------------------

    def run(self, progress: Progress | None = None) -> SolveOutcome:
        """Solve every frequency and return what came back.

        Args:
            progress: Called with a :class:`SolveOutcome` as each frequency
                lands. **Per frequency, never per problem** -- the first
                problem at a frequency pays the whole matrix assembly and the
                rest are nearly free, so a per-problem count stalls and then
                jumps (spec 06 section 6.5.1).

        Returns:
            The outcome, complete or not. Stopping is not an error: a shorter
            grid is a complete result.
        """
        started = time.perf_counter()
        solved: dict[float, xr.Dataset] = {}
        failed: dict[float, str] = {}

        def snapshot(*, dataset=None, stopped=False) -> SolveOutcome:
            return SolveOutcome(
                requested=self._omegas,
                solved=tuple(sorted(solved)),
                failed=dict(failed),
                elapsed=time.perf_counter() - started,
                stopped=stopped,
                killed=self._killed,
                dataset=dataset,
            )

        if not self._omegas:
            return snapshot()

        with _openmp_threads(self._omp_threads):
            # The environment is set *around pool creation* on purpose. Each
            # worker is a fresh spawn that inherits this environment and reads
            # OMP_NUM_THREADS when it imports Capytaine -- an initializer would
            # run after that import and be too late.
            pool = ProcessPoolExecutor(max_workers=self._workers)

        with self._lock:
            if self._killed:  # killed before we got started
                pool.shutdown(wait=False, cancel_futures=True)
                return snapshot(stopped=True)
            self._pool = pool

        futures: dict[Future, float] = {
            pool.submit(_solve_one_frequency, self._payload(omega)): omega for omega in self._omegas
        }
        with self._lock:
            self._futures = list(futures)
            if self._stopping:
                # stop() or kill() arrived between creating the pool and
                # submitting, so it had nothing to cancel. Do it now.
                for future in self._futures:
                    future.cancel()

        # Not as_completed(). A future cancelled by stop() or kill() sits in
        # state CANCELLED until the *executor* notifies it, and a broken or
        # torn-down executor never does -- so as_completed waits forever on
        # work that will never run. Waiting in slices lets this drop cancelled
        # futures itself, and notice a kill, without busy-waiting.
        pending = set(futures)
        try:
            while pending:
                done, pending = wait(pending, timeout=_POLL_SECONDS, return_when=FIRST_COMPLETED)

                for future in done:
                    omega = futures[future]
                    if future.cancelled():
                        continue
                    try:
                        solved[omega] = future.result()
                    except Exception as exc:  # a worker died, or the solve raised
                        if not self._killed:
                            # A frequency that failed must be visible, not
                            # silently missing (spec 06 section 6.6). After a
                            # kill it is neither: it was abandoned, not failed.
                            failed[omega] = f"{type(exc).__name__}: {exc}"
                    if progress is not None:
                        progress(snapshot(stopped=self._stopping))

                pending = {future for future in pending if not future.cancelled()}
                if self._killed:
                    # Whatever is still running has had its process terminated
                    # and will never report. Abandon it and keep the rest.
                    break
        finally:
            # Only now, with the loop finished, is shutting down safe. Not
            # waiting after a kill: the workers are already gone and their
            # queues will not drain.
            pool.shutdown(wait=not self._killed, cancel_futures=True)
            with self._lock:
                self._pool = None
                self._futures = []

        return snapshot(dataset=_merge(solved), stopped=self._stopping)

    def _payload(self, omega: float) -> tuple:
        return (
            self._vertices,
            self._faces,
            self._is_xz_symmetric,
            self._application_point,
            self._settings,
            omega,
        )


def _live_processes(pool: ProcessPoolExecutor | None) -> list:
    """The pool's running worker processes.

    ``_processes`` is private, and there is no public way to reach the
    workers -- but terminating them is the only thing that interrupts a
    Fortran call, so the private access is deliberate. It is confined to this
    one function so a change upstream has one place to break.

    Defensive twice over. ``shutdown()`` sets ``_processes`` to **None**, so
    calling ``kill()`` after ``stop()``, or reading the pids of a finished
    run, would otherwise raise ``AttributeError`` on ``None.values()``. And a
    worker that has already exited must not be killed again.
    """
    processes = getattr(pool, "_processes", None) or {}
    return [process for process in processes.values() if process.is_alive()]


def _merge(solved: dict[float, xr.Dataset]) -> xr.Dataset | None:
    """One dataset from the frequencies that came back, ascending.

    Sorted because ``as_completed`` yields in finishing order, which under
    several workers has nothing to do with frequency.
    """
    if not solved:
        return None
    ordered = [solved[omega] for omega in sorted(solved)]
    if len(ordered) == 1:
        return ordered[0]
    return xr.concat(ordered, dim="omega").sortby("omega")


class _openmp_threads:
    """Set ``OMP_NUM_THREADS`` for the workers, and put it back afterwards.

    There are two layers of parallelism and they multiply: processes here,
    OpenMP threads inside the Fortran. Left alone, every worker spawns
    ``cpu_count`` threads and they fight each other (spec 06 section 6.5).

    The parent's own value is restored, because a solve should not change the
    environment of the application that ran it.
    """

    def __init__(self, threads: int) -> None:
        self._threads = threads
        self._previous: str | None = None

    def __enter__(self) -> None:
        self._previous = os.environ.get("OMP_NUM_THREADS")
        os.environ["OMP_NUM_THREADS"] = str(self._threads)

    def __exit__(self, *exc_info: object) -> None:
        if self._previous is None:
            os.environ.pop("OMP_NUM_THREADS", None)
        else:
            os.environ["OMP_NUM_THREADS"] = self._previous
