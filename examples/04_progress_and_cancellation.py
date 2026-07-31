"""Watching a solve, and stopping one.

    uv run python examples/04_progress_and_cancellation.py

A solve takes seconds to minutes, so anything driving it needs to say where it
is -- and needs to be able to give up. Both are one argument: ``progress``.

There is no cancel API. Raising from the progress callback *is* the cancel: the
exception propagates out untouched and nothing is stored. A flag set from
another thread is therefore a complete mechanism, which is exactly what a UI
needs, with no machinery of its own.

Two limits worth knowing:

- Progress is reported **per frequency**, never per problem. The influence
  matrices are assembled once per frequency and cached for that frequency's
  remaining problems, so the first problem does nearly all the work; a
  per-problem bar crawls and then jumps.
- Cancellation therefore lands at a **frequency boundary**. A single problem
  is a Fortran call that cannot be interrupted at all -- which is also why
  Ctrl-C during a solve takes effect only when the current call returns.

Self-contained: writes its own ``examples/output/progress.pylot``.
"""

import threading
import time
from pathlib import Path

import numpy as np

from pylot_bem import Pylot, SolveSettings, influence_matrix_bytes, solved_panels

HULL = Path(__file__).parents[1] / "tests" / "assets" / "tanker.stl"
LIBRARY = Path(__file__).parent / "output" / "progress.pylot"

PERIODS = [12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 24.0, 26.0]
DIRECTIONS = [0.0, 45.0, 90.0, 135.0, 180.0]

# Fine enough that the solve takes a few seconds, which is the point -- turn
# it down to pct=1.0 if you want to watch it properly. Cost is quadratic in
# the panel count, so this is the knob that matters.
MESH = {"pct": 2.0, "iterations": 10}
CANCEL_AFTER = 0.6  # seconds


class SolveCancelledError(Exception):
    """Raised out of the progress callback to stop a solve."""


def bar(done: int, total: int, started: float) -> None:
    filled = round(20 * done / total)
    elapsed = time.perf_counter() - started
    eta = elapsed / done * (total - done)
    print(f"\r  [{'#' * filled}{'.' * (20 - filled)}] {done:2}/{total}  {elapsed:5.1f}s elapsed, {eta:5.1f}s left",
          end="", flush=True)


def main() -> None:
    LIBRARY.parent.mkdir(exist_ok=True)
    LIBRARY.unlink(missing_ok=True)

    library = Pylot.create_new(LIBRARY, HULL, "stern, centerline, keel", is_xz_symmetric=True)
    library.create_condition(z_origin=-12.0, condition_id="design")
    mesh = library.create_mesh("design", **MESH, mesh_id="fine")

    settings = SolveSettings(
        omegas=tuple(2 * np.pi / period for period in PERIODS),
        wave_directions=tuple(DIRECTIONS),
    )
    panels = solved_panels(mesh)
    print(f"mesh          {len(mesh.faces)} faces -> {panels} panels, {influence_matrix_bytes(panels) / 1e6:.0f} MB")
    print(f"grid          {len(PERIODS)} frequencies x {6 + len(DIRECTIONS)} problems = {len(PERIODS) * (6 + len(DIRECTIONS))} solves")

    # 1. Watch it ----------------------------------------------------------
    print("\nsolving")
    started = time.perf_counter()
    result = library.run_solve(mesh, settings, result_id="run1", progress=lambda d, t: bar(d, t, started))
    print(f"\n  stored      {result.id} in {time.perf_counter() - started:.1f} s")

    # 2. Stop one ----------------------------------------------------------
    #
    # The pattern a UI uses: a flag another thread sets, checked in the
    # callback. Here a timer stands in for the user clicking Cancel.
    print(f"\nsolving again, cancelling after {CANCEL_AFTER} s")
    stop = threading.Event()
    threading.Timer(CANCEL_AFTER, stop.set).start()

    started = time.perf_counter()
    reached = 0

    def watch_for_cancel(done: int, total: int) -> None:
        nonlocal reached
        reached = done
        bar(done, total, started)
        if stop.is_set():
            raise SolveCancelledError

    try:
        library.run_solve(mesh, settings, result_id="run2", progress=watch_for_cancel)
    except SolveCancelledError:
        print(f"\n  cancelled   after {reached} of {len(PERIODS)} frequencies")

    # 3. Nothing was written ------------------------------------------------
    #
    # A result is stored only once the whole solve has finished, so a cancelled
    # run leaves the library exactly as it was. Keeping partial work is a
    # question the application can ask a user; a script has nobody to ask.
    print(f"\nresults       {[r.id for r in library.results()]}")
    print(f"validate      {library.validate() or 'clean'}")
    print(f"database      {'usable' if library.databases()[0].usable else 'not usable'}"
          f", {len(library.databases()[0].coverage)} frequencies")

    library.close()


if __name__ == "__main__":
    main()
