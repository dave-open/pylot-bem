"""Running a solve without freezing the interface.

:meth:`~pylot_bem.pool.PoolSolve.run` blocks for as long as the solve takes --
seconds for a small mesh, minutes for a real one (spec 06 section 6.5.1) -- so
it runs on a worker thread and reports back through signals.

A thread is enough here **because the solving does not happen in it**. The
Fortran matrix assembly holds the GIL for its whole duration (spec 06
section 6.3), so a thread that solved would freeze the interface just as
thoroughly as no thread at all. What this thread does is wait on a
:class:`~concurrent.futures.ProcessPoolExecutor`, which releases the GIL. The
separate processes are what make cancellation and responsiveness possible;
the thread only keeps the waiting off the event loop.

Signals cross back to the interface thread by Qt's own queueing, which is the
only place progress touches a widget. ``stop()`` and ``kill()`` go the other
way, from the interface thread into a running pool -- which
:class:`~pylot_bem.pool.PoolSolve` is built to survive.
"""

import traceback

from PySide6.QtCore import QThread, Signal

from pylot_bem.pool import PoolSolve, SolveOutcome

__all__ = ["SolveThread"]


class SolveThread(QThread):
    """One :class:`~pylot_bem.pool.PoolSolve` run, off the interface thread.

    Signals:
        progressed: A :class:`~pylot_bem.pool.SolveOutcome` after each solved
            frequency. Its ``dataset`` is ``None`` -- progress reports what has
            landed, not the data.
        completed: The final outcome, with its dataset.
        failed: A traceback, when the run raised rather than returning. A pool
            that dies has to say so in the interface: spec 06 section 6.6, and
            stderr is not visible from a window.
    """

    progressed = Signal(object)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, pool: PoolSolve, parent=None) -> None:
        super().__init__(parent)
        self._pool = pool

    @property
    def pool(self) -> PoolSolve:
        return self._pool

    def stop(self) -> None:
        """Drop the queued frequencies; let the running ones finish."""
        self._pool.stop()

    def kill(self) -> None:
        """Terminate the workers now. Frequencies in flight are lost."""
        self._pool.kill()

    def run(self) -> None:
        try:
            outcome: SolveOutcome = self._pool.run(progress=self.progressed.emit)
        except Exception:
            self.failed.emit(traceback.format_exc())
        else:
            self.completed.emit(outcome)
