"""Fill a library in one go: a grid of conditions, meshed and solved unattended.

    uv run python examples/06_batch_overnight.py

Creates ``examples/output/batch.pylot``. Examples 01 to 05 build a library the
way you explore a vessel -- one condition, one mesh, one solve at a time. This
is the other half: the forty drafts, three heels and five trims a *finished*
library needs, described once and left running.

Deliberately tiny, so it finishes in seconds. The settings at the bottom of this
docstring are the real ones; change ``Z_ORIGINS`` and ``BANDS`` and this same
script is the night job.

Three things it does that a ``for`` loop around example 01 would not:

- **a step that fails does not end the run.** The grid below deliberately
  contains one ``z_origin`` above the waterline, and the others still solve;
- **running it again resumes.** The script runs the same job twice and the
  second pass writes nothing at all;
- **the cost is counted first.** ``plan`` walks the whole job against the
  library and creates none of it.

It also saves the job beside the library, because a job is data: a small text
file is what you start again tomorrow and what you keep with the library.
"""

from pathlib import Path

from pylot_bem.angles import slope_from_degrees
from pylot_bem.api import Pylot
from pylot_bem.batch import BatchJob, BatchRun, load_job, parse_bands, plan, save_job

# --- edit these -----------------------------------------------------------

HULL = Path(__file__).parents[1] / "tests" / "assets" / "tanker.stl"
ORIGIN = "stern, centerline, keel"
IS_XZ_SYMMETRIC = True

# z of the vessel origin above the waterplane [m], negative when floating. NOT
# the naval draft. The last one is above the water on purpose -- watch it fail
# on its own without taking the others with it.
#
# A real job is a range instead:  value_range(-18.0, -5.0, 0.5)
Z_ORIGINS = (-12.0, -11.0, 5.0)

# Degrees here, slopes in the job -- converted at the boundary, as everywhere.
# A real job heels and trims too:  HEELS = (-1, 0, 1), TRIMS = (-2, -1, 0, 1, 2)
HEELS = (0.0,)
TRIMS = (0.0,)

# One line per mesh: pct -> the periods solved on it. Short waves need panels
# that long waves do not, and solver cost is quadratic in the panel count, so a
# single grid from 4 s to 20 s either wastes hours at the long end or returns
# confident nonsense at the short one.
#
# A real job:   1 -> 4, 5, 6, 7, 8
#               2 -> 9, 10, 12, 14, 16, 18, 20
BANDS = """
8  -> 16, 20
15 -> 24
"""

# Two heading grids, and which one a solve gets is derived from its mesh. A
# symmetric hull at zero heel is meshed as a half vessel whose port side mirrors
# its starboard side, so half the circle is exact and the rest is filled in on
# delivery. Heel that same hull and the mesh is a full vessel with nothing to
# mirror -- it needs the whole circle, or the delivered database is interpolated
# across what was never solved and is wrong there with nothing to show why.
#
# HEELS below is (0.0,), so every condition here is a half vessel and the second
# grid goes unused. Add a heel and watch the problem count jump.
DIRECTIONS = (0.0, 90.0, 180.0)                      # degrees, direction of travel
DIRECTIONS_FULL = (0.0, 90.0, 180.0, 270.0)          # for a full-vessel mesh

# --------------------------------------------------------------------------

OUTPUT = Path(__file__).parent / "output"
LIBRARY = OUTPUT / "batch.pylot"

# What each kind of step looks like in the log. A night's run is read the
# morning after by scrolling, so failures have to be findable without reading
# every line. The application's log does exactly this.
MARKERS = {"condition": "+", "mesh": "  +", "solve": "  =", "skip": "  ·", "warning": "  !", "failed": "  x"}


def report(event) -> None:
    """One line per step. ``solving`` is the running count inside one solve --
    it is what drives a progress bar on screen, and is noise in a log.
    """
    if event.kind != "solving":
        print(f"{MARKERS.get(event.kind, ' '):>4} [{event.done}/{event.total}] {event.message}")


def main() -> None:
    OUTPUT.mkdir(exist_ok=True)
    LIBRARY.unlink(missing_ok=True)  # a library is never overwritten in place

    library = Pylot.create_new(
        LIBRARY,
        HULL,
        ORIGIN,
        is_xz_symmetric=IS_XZ_SYMMETRIC,
        description="Built by examples/06_batch_overnight.py",
    )

    # 1. The job ----------------------------------------------------------
    #
    # One frozen value. Everything about the run is in here, which is what
    # makes it something you can write down, keep, and run again.
    job = BatchJob(
        z_origins=Z_ORIGINS,
        heels=tuple(slope_from_degrees(d) for d in HEELS),
        trims=tuple(slope_from_degrees(d) for d in TRIMS),
        # iterations is a knob on the regrid, one value for the whole table.
        bands=parse_bands(BANDS, iterations=5),
        wave_directions=DIRECTIONS,
        wave_directions_full=DIRECTIONS_FULL,
        workers=2,
    )

    # 2. What it would cost -----------------------------------------------
    #
    # plan() reads the library and changes nothing. Its steps are what run()
    # then executes, so this cannot promise work that does not happen.
    #
    # There is no memory or panel figure here on purpose: those come out of a
    # regrid that has not run yet, and an invented number beside real ones is
    # indistinguishable from them. Each mesh reports its own as it is built.
    preview = plan(library, job)
    print(f"conditions    {preview.conditions_to_create} new, {preview.conditions_existing} already there")
    print(f"meshes        {preview.meshes_to_build} to build, {preview.meshes_reused} reused")
    print(f"solves        {preview.solves_to_run} to run, {preview.solves_skipped} already covered")
    print(f"problems      {preview.problems} -- six radiation per frequency, plus one per direction")
    print(f"              {preview.directions} headings on a half vessel, "
          f"{preview.directions_full} on a full one; "
          f"{preview.solves_on_a_full_vessel} of {preview.solves_to_run} solves are full-vessel")

    # 3. Run it -----------------------------------------------------------
    #
    # progress gets an event per step and repeatedly during each solve. The
    # "solving" ones are dropped here; on screen they drive a progress bar.
    print()
    outcome = BatchRun(library, job).run(progress=report)

    # 4. What happened ----------------------------------------------------
    #
    # A run with failures is a run that *finished*. The whole point of batching
    # is that the hundredth condition does not depend on the first, so one
    # z_origin above the waterline costs that condition and no other.
    print()
    print(f"created       {len(outcome.conditions_created)} conditions, "
          f"{len(outcome.meshes_built)} meshes, {len(outcome.results_stored)} results "
          f"in {outcome.elapsed:.0f} s")
    for what, why in outcome.failures:
        print(f"FAILED        {what}")
        print(f"              {why.splitlines()[0][:100]}")

    # 5. Again -------------------------------------------------------------
    #
    # The answer to a night that ended early is to start the same job again.
    # Conditions already at those values are reused rather than added beside
    # themselves, meshes at the same pct and iterations are reused, and a solve
    # whose every frequency an existing result covers is skipped.
    #
    # What is left over is exactly the condition that cannot float, and its two
    # bands. A plan does not know a step will fail -- it says what would be
    # attempted, and the second pass fails it again and writes nothing.
    print()
    second = BatchRun(library, job)
    print(f"re-planned    {second.plan.conditions_to_create} conditions, "
          f"{second.plan.meshes_to_build} meshes, {second.plan.solves_to_run} solves left to attempt")
    again = second.run()
    print(f"second pass   wrote {len(again.results_stored)} results, "
          f"reused {again.reused} conditions, skipped {again.skipped} solves, "
          f"failed {len(again.failures)} again")

    # 6. Keep the job -------------------------------------------------------
    #
    # A job is data, so it is a file: what you start again after a night that
    # ended early, what you send with the library, and what says a year later
    # which drafts and periods this file actually covers. Angles are written
    # in degrees and infinite depth as null, so it can be edited by hand.
    print()
    saved = save_job(job, LIBRARY.with_suffix(".pylotjob"))
    print(f"job saved     {saved.name}, {len(saved.read_text().splitlines())} lines")
    print(f"loads back    {'identical' if load_job(saved) == job else 'DIFFERENT'}")

    # 7. What came out ------------------------------------------------------
    #
    # A batched result is not a second kind of result: same conditions, same
    # meshes, same everything the interactive path writes.
    print()
    print(f"validate      {library.validate() or 'clean'}")
    for view in library.databases():
        state = "usable" if view.usable else f"NOT usable: {view.conflicts or view.incomplete}"
        print(f"database      {view.key.condition_id[:8]} {len(view.coverage)} frequencies, {state}")

    library.close()
    print(f"\nwritten to    {LIBRARY}")


if __name__ == "__main__":
    main()
