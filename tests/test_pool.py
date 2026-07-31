"""Spec 06 sections 6.2 to 6.5: solving in a pool, and stopping one.

Every solve here runs the real Capytaine in real worker processes. The point
of the module is the failure modes, so the tests that matter most are the ones
that break something: kill a run mid-flight and assert **on the process ids**
that nothing survived, and make a worker fail and assert the frequency is
reported rather than quietly missing from the grid.

Spec 06 section 6.3: *build and test the kill path first, not last*. An
orphaned worker holds ~800 MB and a full core for minutes, and the naive
implementation produces exactly that -- ``ProcessPoolExecutor.shutdown()``
waits for a running task instead of ending it.
"""

import os
import time

import numpy as np
import pytest
from hull import make_base_shape

from pylot_bem.mesh_pipeline import application_point_for, build_mesh
from pylot_bem.pool import PREFERRED_WORKERS, PoolSolve, default_workers
from pylot_bem.solver import SolveSettings, solve
from pylot_db.frames import transform, transform_points

DESIGN = transform(trim=0.0, heel=0.0, z_origin=-4.0)
COARSE = {"pct": 20.0, "iterations": 5}
OMEGAS = (0.4, 0.6, 0.8, 1.0)
DIRECTIONS = (0.0, 90.0)


@pytest.fixture(scope="module")
def geometry():
    base = make_base_shape(is_xz_symmetric=False)
    mesh = build_mesh(base, DESIGN, **COARSE)
    return mesh, transform_points(application_point_for(base, DESIGN), DESIGN)


def make(geometry, omegas=OMEGAS, **kwargs):
    mesh, point = geometry
    return PoolSolve(
        mesh.vertices,
        mesh.faces,
        is_xz_symmetric=mesh.is_xz_symmetric,
        application_point=point,
        settings=SolveSettings(omegas=omegas, wave_directions=DIRECTIONS),
        **kwargs,
    )


# --------------------------------------------------------------------------
# It solves, and it agrees with the in-process path
# --------------------------------------------------------------------------


def test_a_pooled_solve_covers_every_frequency(geometry):
    outcome = make(geometry, workers=2).run()

    assert outcome.complete
    assert outcome.solved == OMEGAS
    assert outcome.failed == {}
    assert outcome.missing == ()


def test_the_frequencies_come_back_in_order_however_they_finish(geometry):
    """``as_completed`` yields in finishing order, which under several workers
    has nothing to do with frequency. The dataset must not inherit that.
    """
    outcome = make(geometry, workers=3).run()
    omegas = outcome.dataset["omega"].values

    assert list(omegas) == sorted(omegas)
    assert np.allclose(omegas, OMEGAS)


def test_a_pool_of_one_gives_the_same_numbers_as_solving_in_process(geometry):
    """The pool is a *setting*, not a second implementation. Both paths call
    the same solve() on the same arrays, so agreement should be tight -- and
    the finite-depth Prony spread that would loosen it is absent here, because
    this is infinite depth.
    """
    mesh, point = geometry
    direct = solve(
        mesh.vertices,
        mesh.faces,
        is_xz_symmetric=mesh.is_xz_symmetric,
        application_point=point,
        settings=SolveSettings(omegas=OMEGAS, wave_directions=DIRECTIONS),
    )
    pooled = make(geometry, workers=1).run().dataset

    for name in ("added_mass", "radiation_damping"):
        assert np.allclose(pooled[name].values, direct[name].values, rtol=1e-9)
    assert np.allclose(pooled["excitation_force"].values, direct["excitation_force"].values, rtol=1e-9)


def test_more_workers_does_not_change_the_answer(geometry):
    one = make(geometry, workers=1).run().dataset
    many = make(geometry, workers=4).run().dataset

    assert np.allclose(one["added_mass"].values, many["added_mass"].values, rtol=1e-9)


# --------------------------------------------------------------------------
# Stop: queued work dropped, finished work kept
# --------------------------------------------------------------------------


def test_stopping_keeps_what_was_solved(geometry):
    """A shorter grid is a complete result, not a partial one, so the point of
    Stop is that the frequencies that finished are still usable.
    """
    run = make(geometry, omegas=(0.4, 0.6, 0.8, 1.0, 1.2, 1.4), workers=1)
    stopped_after = []

    def watch(outcome):
        stopped_after.append(len(outcome.solved))
        if len(outcome.solved) == 2:
            run.stop()

    outcome = run.run(progress=watch)

    assert outcome.stopped
    assert not outcome.complete
    assert len(outcome.solved) >= 2, "what finished is kept"
    assert len(outcome.solved) < 6, "and the rest was dropped rather than solved"
    assert outcome.dataset is not None
    assert len(outcome.dataset["omega"]) == len(outcome.solved)


def test_what_is_missing_is_reported_not_inferred(geometry):
    """Under several workers the completed set has holes, so a count would not
    tell a user which frequencies they have.
    """
    run = make(geometry, workers=1)

    def watch(outcome):
        if len(outcome.solved) == 1:
            run.stop()

    outcome = run.run(progress=watch)

    assert set(outcome.solved) | set(outcome.missing) == set(OMEGAS)
    assert not set(outcome.solved) & set(outcome.missing)


def test_stopping_before_anything_finishes_is_not_an_error(geometry):
    run = make(geometry, workers=1)
    run.stop()
    outcome = run.run()

    assert outcome.stopped
    assert outcome.dataset is None or len(outcome.solved) < len(OMEGAS)


# --------------------------------------------------------------------------
# Kill: the test spec 06 section 7 asks for by name
# --------------------------------------------------------------------------


def test_kill_leaves_no_surviving_worker_process(geometry):
    """Spec 06 test 5a, asserted on the process ids rather than on the call
    returning. "The solve stopped" and "the processes are gone" are different
    claims and only the second one catches the orphan.
    """
    import threading

    run = make(geometry, omegas=tuple(0.3 + 0.1 * i for i in range(12)), workers=3)
    seen: list[tuple[int, ...]] = []

    def watch(outcome):
        pids = run.worker_pids
        if pids and not seen:
            seen.append(pids)
            threading.Thread(target=run.kill, daemon=True).start()

    run.run(progress=watch)

    assert seen, "the run has to have actually started for this to prove anything"
    for pid in seen[0]:
        assert not _alive(pid), f"worker {pid} survived kill()"
    assert run.worker_pids == ()


def test_kill_before_the_run_starts_is_harmless(geometry):
    run = make(geometry, workers=2)
    run.kill()
    outcome = run.run()

    assert outcome.stopped
    assert run.worker_pids == ()


def test_a_killed_run_still_reports_what_it_had(geometry):
    run = make(geometry, omegas=(0.4, 0.6, 0.8, 1.0, 1.2, 1.4), workers=1)

    def watch(outcome):
        if len(outcome.solved) == 2:
            run.kill()

    outcome = run.run(progress=watch)

    assert outcome.stopped
    assert len(outcome.solved) >= 2
    assert outcome.failed == {}, "a killed worker is not a failed frequency"


def _alive(pid: int) -> bool:
    """Whether a process id is still running. Windows has no os.kill(0)."""
    import subprocess

    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    out = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
        capture_output=True, text=True, check=False,
    ).stdout
    return str(pid) in out


# --------------------------------------------------------------------------
# A frequency that fails must be visible
# --------------------------------------------------------------------------


def test_a_failing_frequency_is_reported_rather_than_dropped(geometry):
    """Spec 06 section 6.6. A group that fails must not silently vanish from
    the omega grid -- that is how a database ends up quietly short.

    Zero frequency is genuinely refused by Capytaine ("Diffraction problems at
    zero or infinite frequency are not defined"), so the worker raises for
    real. A *negative* frequency, which was the first thing tried here, solves
    without complaint -- worth knowing, and not something this module can fix.
    """
    mesh, point = geometry
    run = PoolSolve(
        mesh.vertices,
        mesh.faces,
        is_xz_symmetric=mesh.is_xz_symmetric,
        application_point=point,
        settings=SolveSettings(omegas=(0.5, 0.0), wave_directions=DIRECTIONS),
        workers=1,
    )
    outcome = run.run()

    assert 0.0 in outcome.failed
    assert 0.5 in outcome.solved
    assert not outcome.complete
    assert 0.0 in outcome.missing, "a failed frequency is missing from the result too"
    assert "not defined" in outcome.failed[0.0], "the message says what went wrong"


def test_a_failure_does_not_stop_the_other_frequencies(geometry):
    """One bad frequency must not cost the whole grid."""
    mesh, point = geometry
    run = PoolSolve(
        mesh.vertices,
        mesh.faces,
        is_xz_symmetric=mesh.is_xz_symmetric,
        application_point=point,
        settings=SolveSettings(omegas=(0.4, 0.0, 0.8), wave_directions=DIRECTIONS),
        workers=2,
    )
    outcome = run.run()

    assert set(outcome.solved) == {0.4, 0.8}
    assert outcome.dataset is not None
    assert len(outcome.dataset["omega"]) == 2


# --------------------------------------------------------------------------
# Settings around the pool
# --------------------------------------------------------------------------


def test_worker_count_is_clamped_to_the_frequencies(geometry):
    """More workers than frequencies is pure waste."""
    assert default_workers(2) == 2
    assert default_workers(1) == 1


def test_worker_count_is_clamped_to_the_machine():
    cores = os.cpu_count() or 1
    assert default_workers(999) <= max(1, cores - 1)
    assert default_workers(999) <= PREFERRED_WORKERS


def test_openmp_threads_are_set_for_the_workers_and_restored(geometry):
    """Two layers of parallelism multiply: left alone every worker spawns
    cpu_count threads and they oversubscribe the machine together.
    """
    before = os.environ.get("OMP_NUM_THREADS")
    make(geometry, workers=1, omp_threads=1).run()

    assert os.environ.get("OMP_NUM_THREADS") == before, "the parent's environment is put back"


def test_an_empty_frequency_grid_returns_nothing_and_does_not_hang(geometry):
    outcome = make(geometry, omegas=()).run()

    assert outcome.solved == ()
    assert outcome.dataset is None
    assert outcome.complete is True, "nothing was asked for and nothing is missing"


def test_progress_is_reported_once_per_frequency(geometry):
    """Per frequency, never per problem (spec 06 section 6.5.1)."""
    calls = []
    outcome = make(geometry, workers=2).run(progress=lambda o: calls.append(len(o.solved)))

    assert len(calls) == len(OMEGAS)
    assert calls == sorted(calls), "monotonic"
    assert calls[-1] == len(outcome.solved)


def test_progress_carries_the_elapsed_time(geometry):
    seen = []
    make(geometry, workers=2).run(progress=lambda o: seen.append(o.elapsed))

    assert seen and all(t > 0 for t in seen)
    assert seen == sorted(seen)


@pytest.mark.parametrize("workers", [1, 2])
def test_the_pool_leaves_no_processes_behind_on_a_normal_run(geometry, workers):
    run = make(geometry, workers=workers)
    run.run()

    assert run.worker_pids == (), "the pool is shut down when the run returns"


# --------------------------------------------------------------------------
# Which tier ended the run
# --------------------------------------------------------------------------


def test_the_outcome_says_whether_it_was_stopped_or_terminated(geometry):
    """The caller keeps a stopped run and asks about a terminated one, so the
    two have to be distinguishable from the outcome alone -- not from which
    button the caller remembers pressing.
    """
    run = make(geometry, omegas=(0.4, 0.6, 0.8, 1.0, 1.2, 1.4), workers=1)

    def watch(outcome):
        if len(outcome.solved) == 2:
            run.stop()

    outcome = run.run(progress=watch)

    assert outcome.stopped
    assert not outcome.killed, "stop() is not kill()"


def test_a_killed_run_reports_that_it_was_killed(geometry):
    run = make(geometry, omegas=(0.4, 0.6, 0.8, 1.0, 1.2, 1.4), workers=1)

    def watch(outcome):
        if len(outcome.solved) == 2:
            run.kill()

    outcome = run.run(progress=watch)

    assert outcome.stopped
    assert outcome.killed


def test_a_run_that_finishes_is_neither(geometry):
    """Otherwise the two flags could be reading something else entirely."""
    outcome = make(geometry, workers=2).run()

    assert outcome.complete
    assert not outcome.stopped
    assert not outcome.killed
