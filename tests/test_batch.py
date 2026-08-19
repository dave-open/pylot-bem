"""Filling a library in one go, and the four promises that makes it usable.

A batch is not the interactive path with a loop around it. It runs unattended,
which is what puts these four under test rather than under a docstring:

1. **the plan is the run.** What is counted before Start is the same object
   that is then executed, so the preview cannot promise work that does not
   happen -- or hide work that does;
2. **a failed step does not end the job.** A condition out of the water costs
   that condition and nothing else;
3. **running it again resumes.** Conditions already there are reused, matching
   meshes are reused, covered solves are skipped -- so the answer to a night
   that stopped early is to start the same job again;
4. **nothing it writes is different** from what the interactive path writes.
   Same conditions, same meshes, same results, no findings, no conflicts.

The solves here are real. They are tiny -- a boxboat at pct 20, one or two
frequencies -- but they are Capytaine, in worker processes, through the same
:class:`~pylot_bem.pool.PoolSolve` the Solve screen drives. A batch test that
stubbed the solver would pass with the one thing a batch exists to do left out.
"""

import numpy as np
import pytest
from hull import BOX_FACES, BOX_VERTICES
from pylot_db.validation import CONDITION_TOLERANCE

from pylot_bem.angles import slope_from_degrees
from pylot_bem.api import Pylot
from pylot_bem.batch import (
    TARGET_ALL,
    TARGET_GRID,
    TARGET_LISTED,
    Band,
    BatchError,
    BatchJob,
    BatchRun,
    format_bands,
    load_job,
    parse_bands,
    parse_numbers,
    plan,
    save_job,
    value_range,
)

# Coarse enough that a whole batch of them is seconds, fine enough to solve.
COARSE = Band(pct=20.0, periods=(8.0, 10.0), iterations=5)
COARSER = Band(pct=30.0, periods=(12.0,), iterations=5)


@pytest.fixture
def library(tmp_path):
    """An empty library on the boxboat."""
    with Pylot.create(
        tmp_path / "batch.pylot",
        vessel_name="Boxboat",
        origin_description="stern, centerline, keel",
        vertices=BOX_VERTICES,
        faces=BOX_FACES,
        is_xz_symmetric=True,
    ) as opened:
        yield opened


def small_job(**overrides) -> BatchJob:
    """Two conditions, one band, one direction. Seconds, and still a real solve."""
    return BatchJob(
        **{
            "z_origins": (-3.0, -2.5),
            "bands": (COARSE,),
            "wave_directions": (0.0,),
            "workers": 1,
            **overrides,
        }
    )


# --------------------------------------------------------------------------
# Reading a job
# --------------------------------------------------------------------------


def test_a_range_includes_its_end_when_the_step_lands_on_it():
    """*0.1 to 4.7 in steps of 0.1* is the 47 values a reader counts.

    ``arange`` returns 46 of them: the accumulated error at the last step is
    the wrong side of the comparison about half the time, which is a grid
    silently one draft short.
    """
    values = value_range(0.1, 4.7, 0.1)
    assert len(values) == 47
    assert values[0] == pytest.approx(0.1)
    assert values[-1] == pytest.approx(4.7)


def test_a_range_carries_no_binary_noise_into_the_library():
    """A z_origin is stored exactly as given and read back forever."""
    assert value_range(-4.7, -4.4, 0.1) == (-4.7, -4.6, -4.5, -4.4)


def test_a_degenerate_range_is_one_value_not_an_error():
    """A half-typed dialog previews something rather than refusing."""
    assert value_range(2.0, 1.0, 0.5) == (2.0,)
    assert value_range(2.0, 5.0, 0.0) == (2.0,)


def test_numbers_are_read_with_commas_spaces_or_ranges():
    assert parse_numbers("-1, 0, 1", what="Heel") == (-1.0, 0.0, 1.0)
    assert parse_numbers("-1 0 1", what="Heel") == (-1.0, 0.0, 1.0)
    assert parse_numbers("4..6..0.5", what="Periods") == (4.0, 4.5, 5.0, 5.5, 6.0)


def test_a_number_that_is_not_one_says_which():
    with pytest.raises(BatchError, match="'twelve' is not a number"):
        parse_numbers("1, twelve", what="Periods")


def test_the_band_table_is_read_as_it_is_written():
    """The job as the user writes it down, both separators, comments included."""
    bands = parse_bands(
        """
        # short waves need the fine mesh
        1 -> 1, 2, 3, 4
        2:  5, 6, 7, 8, 9, 10, 12
        """
    )
    assert [band.pct for band in bands] == [1.0, 2.0]
    assert bands[0].periods == (1.0, 2.0, 3.0, 4.0)
    assert bands[1].periods == (5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 12.0)


def test_the_band_order_is_the_order_written():
    """Not sorted: a user who put the fine mesh first wants its results first."""
    assert [band.pct for band in parse_bands("5 -> 10\n1 -> 2")] == [5.0, 1.0]


def test_a_band_line_with_no_separator_says_what_one_looks_like():
    with pytest.raises(BatchError, match="has no separator"):
        parse_bands("1 2 3")


def test_an_empty_band_table_is_refused():
    with pytest.raises(BatchError, match="no bands"):
        parse_bands("# nothing but a note\n\n")


def test_a_band_table_survives_a_round_trip():
    """The screen writes a job out and reads it back in; it must be the same job."""
    text = "1 -> 1, 2, 3, 4\n2 -> 5, 6, 7, 8, 9, 10, 12"
    assert format_bands(parse_bands(text)) == text


def test_periods_reach_the_solver_as_ascending_omega():
    """The solver is frequency-major, so ascending omega is descending period."""
    omegas = Band(pct=1.0, periods=(12.0, 4.0, 8.0)).omegas
    assert list(omegas) == sorted(omegas)
    assert omegas[0] == pytest.approx(2 * np.pi / 12.0)


def test_an_unknown_target_or_lid_is_refused_when_the_job_is_made():
    with pytest.raises(BatchError, match="targets must be"):
        BatchJob(targets="everything")
    with pytest.raises(BatchError, match="lid must be"):
        BatchJob(lid="maybe")


# --------------------------------------------------------------------------
# Keeping a job
# --------------------------------------------------------------------------


def a_whole_job() -> BatchJob:
    """Every field set to something other than its default.

    Written out rather than taken from a fixture so that a field added to
    :class:`BatchJob` and forgotten in :func:`job_to_dict` shows up as a round
    trip that lost something, which is the failure this section exists to
    catch.
    """
    return BatchJob(
        z_origins=value_range(-4.7, -0.1, 0.1),
        heels=tuple(slope_from_degrees(d) for d in (-1, 0, 1)),
        trims=tuple(slope_from_degrees(d) for d in (-2, -1, 0, 1, 2)),
        bands=parse_bands("1 -> 1, 2, 3, 4\n2 -> 5, 6, 7, 8, 9, 10, 12", iterations=15),
        targets=TARGET_LISTED,
        condition_ids=("design", "ballast"),
        wave_directions=(0.0, 45.0, 90.0),
        wave_directions_full=(0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0),
        water_depth=80.0,
        g=9.80665,
        forward_speed=2.5,
        lid="below",
        lid_z=-0.35,
        workers=3,
        omp_threads=2,
        resume=False,
    )


def test_a_saved_job_loads_back_as_the_same_job(tmp_path):
    """The whole promise of a job file: what you start again is what you saved.

    Asserted on the object, not field by field: a job that differs anywhere is
    a night spent solving something other than what was written down.
    """
    job = a_whole_job()
    assert load_job(save_job(job, tmp_path / "night")) == job


def test_a_saved_job_gets_the_suffix_when_none_was_typed(tmp_path):
    assert save_job(BatchJob(), tmp_path / "night").name == "night.pylotjob"
    assert save_job(BatchJob(), tmp_path / "night.json").name == "night.json", (
        "a suffix the caller chose is never substituted"
    )


def test_a_job_file_is_readable_and_editable(tmp_path):
    """It is a file a person keeps beside the library and edits.

    The drafts and the periods are the half worth editing by hand, so they stay
    on one line each rather than becoming forty-seven lines of one number.
    """
    text = save_job(a_whole_job(), tmp_path / "night").read_text(encoding="utf-8")

    assert '"z_origins": [ -4.7, -4.6' in text
    assert '"heels_deg": [ -1, 0, 1 ]'.replace("-1, 0, 1", "-1.0, 0.0, 1.0") in text
    assert len(text.splitlines()) < 40, "a 705-condition job must stay readable"


def test_infinite_depth_survives_as_null_rather_than_as_Infinity(tmp_path):
    """``Infinity`` is what Python's JSON writes and is not valid JSON, so a
    file carrying it reads back here and nowhere else.
    """
    path = save_job(BatchJob(water_depth=np.inf), tmp_path / "night")

    assert "Infinity" not in path.read_text(encoding="utf-8")
    assert '"water_depth": null' in path.read_text(encoding="utf-8")
    assert np.isinf(load_job(path).water_depth)


def test_angles_are_written_in_degrees(tmp_path):
    """Degrees at every human-facing boundary, and a job file is one. The unit
    is in the key so a reader cannot take one for the other.
    """
    text = save_job(BatchJob(heels=(slope_from_degrees(30.0),)), tmp_path / "n").read_text()

    assert '"heels_deg": [ 30.0 ]' in text
    assert "0.5" not in text, "the slope itself must not be what is written"


def test_the_degree_round_trip_is_exact_far_below_what_anything_compares_at(tmp_path):
    """``sin(asin(x))`` is exact to about one ULP -- five orders of magnitude
    tighter than the 1e-3 at which two conditions are the same condition.
    """
    job = BatchJob(heels=(0.03,), trims=(-0.017,))
    back = load_job(save_job(job, tmp_path / "n"))

    assert back.heels[0] == pytest.approx(0.03, abs=1e-12)
    assert back.trims[0] == pytest.approx(-0.017, abs=1e-12)


def test_a_file_that_is_not_a_job_is_refused_with_a_reason(tmp_path):
    path = tmp_path / "not-a-job.pylotjob"
    path.write_text('{"vessel": "tanker"}', encoding="utf-8")

    with pytest.raises(BatchError, match="not a pylot batch job"):
        load_job(path)


def test_picking_the_library_by_mistake_is_answered_rather_than_decoded(library):
    """The one wrong file anybody actually picks: it is in the same folder,
    under a name one letter away. "cannot decode byte 0x8a at position 98" is
    true and of no use to the person who picked it.
    """
    with pytest.raises(BatchError, match="is a pylot library, not a batch job"):
        load_job(library.path)


def test_a_job_from_another_version_is_refused_rather_than_half_read(tmp_path):
    path = tmp_path / "future.pylotjob"
    path.write_text('{"pylot_batch_job": 99}', encoding="utf-8")

    with pytest.raises(BatchError, match="version 99"):
        load_job(path)


def test_a_job_file_that_is_not_json_says_so(tmp_path):
    path = tmp_path / "broken.pylotjob"
    path.write_text("{ this is not json", encoding="utf-8")

    with pytest.raises(BatchError, match="not readable as JSON"):
        load_job(path)


def test_a_hand_edited_job_may_leave_fields_out(tmp_path):
    """Which is what makes one worth editing by hand: delete the half you do
    not care about and the defaults fill in.
    """
    path = tmp_path / "minimal.pylotjob"
    path.write_text(
        '{"pylot_batch_job": 1, "z_origins": [-3.0, -2.0],'
        ' "bands": [{"pct": 2.0, "periods": [8, 10]}]}',
        encoding="utf-8",
    )
    job = load_job(path)

    assert job.z_origins == (-3.0, -2.0)
    assert job.bands == (Band(pct=2.0, periods=(8.0, 10.0), iterations=20),)
    assert job.heels == BatchJob().heels
    assert job.resume is True


def test_a_hand_edited_job_that_is_wrong_says_which_field(tmp_path):
    path = tmp_path / "wrong.pylotjob"
    path.write_text(
        '{"pylot_batch_job": 1, "z_origins": ["shallow"]}', encoding="utf-8"
    )
    with pytest.raises(BatchError, match="'z_origins' must be a list of numbers"):
        load_job(path)


def test_a_hand_edited_job_with_an_impossible_setting_is_still_refused(tmp_path):
    """``targets`` and ``lid`` are checked by BatchJob itself, so a file cannot
    smuggle past the check a caller in Python cannot.
    """
    path = tmp_path / "wrong.pylotjob"
    path.write_text('{"pylot_batch_job": 1, "lid": "sometimes"}', encoding="utf-8")

    with pytest.raises(BatchError, match="lid must be"):
        load_job(path)


def test_a_saved_job_plans_the_same_as_the_one_it_came_from(library, tmp_path):
    """The point of the round trip, said in the terms that matter: the same
    file against the same library is the same work.
    """
    job = small_job(bands=(COARSE, COARSER))
    BatchRun(library, job).run()

    assert plan(library, load_job(save_job(job, tmp_path / "n"))) == plan(library, job)


# --------------------------------------------------------------------------
# The plan
# --------------------------------------------------------------------------


def test_the_plan_multiplies_the_grid_and_the_bands(library):
    """The whole point of the screen: the cost, before any of it is incurred."""
    job = BatchJob(
        z_origins=value_range(-4.7, -0.1, 0.1),
        heels=tuple(slope_from_degrees(d) for d in (-1, 0, 1)),
        trims=tuple(slope_from_degrees(d) for d in (-2, -1, 0, 1, 2)),
        bands=parse_bands("1 -> 1, 2, 3, 4\n2 -> 5, 6, 7, 8, 9, 10, 12"),
        wave_directions=tuple(float(d) for d in range(0, 180, 15)),
    )
    preview = plan(library, job)

    assert preview.conditions_to_create == 47 * 3 * 5
    assert preview.meshes_to_build == 47 * 3 * 5 * 2
    assert preview.solves_to_run == 47 * 3 * 5 * 2
    # Six radiation problems per frequency plus one per direction, which is
    # the count the Solve screen shows for a single mesh.
    assert preview.problems == 705 * (4 + 7) * (6 + 12)


def test_a_plan_with_no_bands_only_adds_conditions(library):
    preview = plan(library, BatchJob(z_origins=(-3.0, -2.0)))
    assert preview.conditions_to_create == 2
    assert preview.steps == ()
    assert preview.problems == 0


def test_a_plan_that_would_do_nothing_says_so(library):
    assert plan(library, BatchJob()).is_empty


def test_the_plan_counts_a_condition_that_already_exists_as_existing(library):
    library.create_condition(z_origin=-3.0)
    preview = plan(library, BatchJob(z_origins=(-3.0, -2.0), bands=(COARSE,)))

    assert preview.conditions_to_create == 1
    assert preview.conditions_existing == 1
    assert len(preview.steps) == 2, "both conditions are still meshed and solved"


def test_a_condition_within_the_validators_tolerance_is_the_same_condition(library):
    """Reused at exactly the tolerance the validator calls a duplicate by.

    A batch that reused at a tighter one would create the pairs the validator
    then reports; at a looser one it would silently solve a condition nobody
    asked for.
    """
    library.create_condition(z_origin=-3.0)
    close = plan(library, BatchJob(z_origins=(-3.0 + CONDITION_TOLERANCE / 2,)))
    apart = plan(library, BatchJob(z_origins=(-3.0 + CONDITION_TOLERANCE * 10,)))

    assert close.conditions_to_create == 0
    assert apart.conditions_to_create == 1


def test_targeting_every_condition_reaches_the_ones_the_grid_never_mentions(library):
    library.create_condition(z_origin=-1.5)
    preview = plan(
        library, BatchJob(z_origins=(-3.0,), bands=(COARSE,), targets=TARGET_ALL)
    )
    assert len(preview.steps) == 2, "the new one and the one already there"


def test_targeting_every_condition_never_meshes_one_twice(library):
    """A condition in the grid *and* in the library is one condition.

    Counted twice it would be meshed twice and its two results would contest
    every frequency they share -- a conflict manufactured by the batch itself.
    """
    library.create_condition(z_origin=-3.0)
    preview = plan(
        library, BatchJob(z_origins=(-3.0,), bands=(COARSE,), targets=TARGET_ALL)
    )
    assert len(preview.steps) == 1


def test_targeting_a_list_leaves_everything_else_alone(library):
    chosen = library.create_condition(z_origin=-3.0)
    library.create_condition(z_origin=-2.0)
    preview = plan(
        library,
        BatchJob(bands=(COARSE,), targets=TARGET_LISTED, condition_ids=(chosen.id,)),
    )
    assert [preview.conditions[step.condition].existing_id for step in preview.steps] == [chosen.id]


def test_a_state_read_once_plans_the_same_as_reading_the_library(library):
    """The batch screen re-plans on every keystroke, and a plan reads every
    mesh in the library -- geometry and all, because that is what a
    ``CalculationMesh`` carries. Reading it once is only safe if it gives the
    same answer, so that is what is asserted rather than the speed.
    """
    library.create_condition(z_origin=-3.0)
    job = BatchJob(z_origins=(-3.0, -2.0), bands=(COARSE, COARSER), targets=TARGET_ALL)

    from pylot_bem.batch import LibraryState

    assert plan(library, job, state=LibraryState.of(library)) == plan(library, job)


def test_the_grid_is_what_a_second_run_still_works_from(library):
    """:data:`TARGET_GRID` means the grid, not only what it created.

    Otherwise the second run of a job would target nothing, because by then
    every condition in the grid exists -- and resume would be impossible by
    construction.
    """
    library.create_condition(z_origin=-3.0)
    preview = plan(library, BatchJob(z_origins=(-3.0,), bands=(COARSE,), targets=TARGET_GRID))
    assert len(preview.steps) == 1


# --------------------------------------------------------------------------
# Running it
# --------------------------------------------------------------------------


def test_a_batch_builds_conditions_meshes_and_results(library):
    outcome = BatchRun(library, small_job()).run()

    assert len(outcome.conditions_created) == 2
    assert len(outcome.meshes_built) == 2
    assert len(outcome.results_stored) == 2
    assert outcome.failures == ()
    assert not outcome.stopped

    assert len(library.conditions()) == 2
    assert len(library.results()) == 2


def test_what_a_batch_writes_is_a_library_like_any_other(library):
    """No findings, no conflicts. A batched result is not a second kind of result."""
    BatchRun(library, small_job(bands=(COARSE, COARSER))).run()

    assert library.validate() == []
    assert all(not view.conflicts for view in library.databases())
    assert all(not view.incomplete for view in library.databases())


def test_the_plan_is_what_actually_happens(library):
    """The number on the screen and the work done are the same list."""
    job = small_job(bands=(COARSE, COARSER))
    run = BatchRun(library, job)
    expected = run.plan

    outcome = run.run()

    assert len(outcome.conditions_created) == expected.conditions_to_create
    assert len(outcome.meshes_built) == expected.meshes_to_build
    assert len(outcome.results_stored) == expected.solves_to_run


def test_a_band_puts_its_periods_on_its_own_mesh(library):
    """The whole reason bands exist: fine mesh, short waves; coarse mesh, long."""
    BatchRun(library, small_job(z_origins=(-3.0,), bands=(COARSE, COARSER))).run()

    by_pct = {library.mesh(r.mesh_id).pct: sorted(r.omegas) for r in library.results()}
    assert by_pct[20.0] == pytest.approx(sorted(COARSE.omegas))
    assert by_pct[30.0] == pytest.approx(sorted(COARSER.omegas))


def test_a_condition_out_of_the_water_costs_that_condition_and_no_other(library):
    """Promise 2, and the reason a batch is worth having at all.

    Abandoning the run on the first bad step would make an overnight job a
    coin toss on the ordering of the grid.
    """
    outcome = BatchRun(library, small_job(z_origins=(50.0, -3.0, -2.5))).run()

    assert len(outcome.failures) == 1
    assert "nothing lies below the waterplane" in outcome.failures[0][1]
    assert len(outcome.conditions_created) == 2
    assert len(outcome.results_stored) == 2, "the other two were solved regardless"


def test_a_failed_condition_is_reported_once_not_once_per_band(library):
    """One cause, one line. Its bands were never separate failures."""
    outcome = BatchRun(library, small_job(z_origins=(50.0,), bands=(COARSE, COARSER))).run()
    assert len(outcome.failures) == 1


def test_running_the_same_job_again_changes_nothing(library):
    """Promise 3. The answer to a night that stopped early is to start it again."""
    first = BatchRun(library, small_job()).run()
    assert len(first.results_stored) == 2

    second = BatchRun(library, small_job())
    assert second.plan.conditions_to_create == 0
    assert second.plan.meshes_to_build == 0
    assert second.plan.solves_to_run == 0

    outcome = second.run()
    assert outcome.conditions_created == ()
    assert outcome.meshes_built == ()
    assert outcome.results_stored == ()
    assert outcome.reused == 2
    assert outcome.skipped == 2

    assert len(library.conditions()) == 2
    assert len(library.meshes()) == 2
    assert len(library.results()) == 2


def test_a_job_extended_with_a_second_band_only_runs_the_new_one(library):
    """The other half of resume: adding to a library, not rebuilding it."""
    BatchRun(library, small_job()).run()

    extended = BatchRun(library, small_job(bands=(COARSE, COARSER)))
    assert extended.plan.meshes_to_build == 2, "one per condition, for the new band only"
    assert extended.plan.solves_to_run == 2

    outcome = extended.run()
    assert len(outcome.results_stored) == 2
    assert outcome.skipped == 2


def test_resume_switched_off_solves_it_all_again(library):
    """A deliberate second opinion, which is a conflict and is meant to be.

    Two results on one key contesting every frequency is exactly what the
    Databases tab is for; what matters is that it takes switching something
    off, and never happens by accident.
    """
    BatchRun(library, small_job()).run()
    outcome = BatchRun(library, small_job(resume=False)).run()

    assert len(outcome.results_stored) == 2
    assert len(library.results()) == 4
    assert any(view.conflicts for view in library.databases())


def test_a_solve_is_only_skipped_when_every_frequency_is_covered(library):
    """A partial match is not a match: skipping on one would leave a hole."""
    BatchRun(library, small_job(z_origins=(-3.0,))).run()

    wider = Band(pct=COARSE.pct, periods=(*COARSE.periods, 14.0), iterations=COARSE.iterations)
    assert BatchRun(library, small_job(z_origins=(-3.0,), bands=(wider,))).plan.solves_to_run == 1


def test_a_mesh_is_reused_only_at_the_same_regrid_settings(library):
    """``pct`` and ``iterations`` are what a mesh *is*; either differing is another mesh."""
    BatchRun(library, small_job(z_origins=(-3.0,))).run()
    other = Band(pct=COARSE.pct, periods=COARSE.periods, iterations=COARSE.iterations + 1)

    assert BatchRun(library, small_job(z_origins=(-3.0,), bands=(other,))).plan.meshes_to_build == 1


def test_stopping_before_anything_starts_writes_nothing(library):
    run = BatchRun(library, small_job())
    run.stop()
    outcome = run.run()

    assert outcome.stopped
    assert outcome.conditions_created == ()
    assert library.conditions() == []


def test_killing_before_anything_starts_writes_nothing(library):
    run = BatchRun(library, small_job())
    run.kill()
    outcome = run.run()

    assert outcome.killed
    assert library.results() == []


def test_progress_reports_every_step_and_names_what_it_did(library):
    """The log is the only record of what an overnight run did."""
    events = []
    BatchRun(library, small_job(z_origins=(-3.0,))).run(progress=events.append)

    kinds = [event.kind for event in events]
    assert kinds.count("condition") == 1
    assert kinds.count("mesh") == 1
    assert kinds.count("solve") == 1
    assert "solving" in kinds, "the frequencies inside a solve are reported too"
    assert all(event.done <= event.total for event in events)
    assert events[-1].done == events[-1].total


def test_a_band_below_the_meshs_resolution_is_warned_about(library):
    """The one check only a batch can make, because only it holds the mesh.

    Periods below the limit still solve, and are wrong by an amount nothing
    downstream detects -- which unattended means a library that looks complete
    and is not.
    """
    events = []
    short = Band(pct=20.0, periods=(2.0,), iterations=5)
    BatchRun(library, small_job(z_origins=(-3.0,), bands=(short,))).run(progress=events.append)

    warnings = [event.message for event in events if event.kind == "warning"]
    assert warnings and "will solve, and be wrong" in warnings[0]


def test_an_auto_lid_is_resolved_per_mesh_rather_than_per_job(library):
    """``auto`` has no answer until a mesh exists, which is why it is a mode.

    The command line refuses it for exactly that reason; a batch is holding the
    mesh by the time it matters.
    """
    outcome = BatchRun(library, small_job(z_origins=(-3.0,), lid="auto")).run()

    assert len(outcome.results_stored) == 1
    stored = library.result(outcome.results_stored[0])
    assert stored.lid_z is None or stored.lid_z < 0, "never a lid on the free surface by accident"


# --------------------------------------------------------------------------
# One heading grid could never have been right
# --------------------------------------------------------------------------

HALF_CIRCLE = tuple(float(d) for d in range(0, 181, 45))    # 5
WHOLE_CIRCLE = tuple(float(d) for d in range(0, 360, 45))   # 8


def mixed_job(**overrides) -> BatchJob:
    """Heels of -1, 0 and 1: a grid containing both kinds of mesh.

    Which is the whole point. A symmetric hull at zero heel is meshed as a half
    vessel whose port side mirrors its starboard side; heel it by a degree and
    the mesh is a full vessel with nothing to mirror. Any real grid of drafts
    and heels has both in it.
    """
    return BatchJob(
        **{
            "z_origins": (-3.0,),
            "heels": tuple(slope_from_degrees(d) for d in (-1, 0, 1)),
            "bands": (COARSE,),
            "wave_directions": HALF_CIRCLE,
            "wave_directions_full": WHOLE_CIRCLE,
            "workers": 1,
            **overrides,
        }
    )


def test_the_heading_grid_is_derived_from_the_mesh_never_chosen():
    """The same rule symmetry itself follows. A job that let a caller pick the
    grid per solve would let it pick the half grid for a full vessel, which is
    exactly the mistake two grids exist to make impossible.
    """
    job = mixed_job()

    assert job.directions_for(is_xz_symmetric=True) == HALF_CIRCLE
    assert job.directions_for(is_xz_symmetric=False) == WHOLE_CIRCLE


def test_a_job_that_never_said_falls_back_to_the_one_grid_it_has():
    """A convenience for a job with no heel in it — where it is also harmless,
    because such a job never builds a full mesh.
    """
    job = BatchJob(wave_directions=HALF_CIRCLE)

    assert job.directions_for(is_xz_symmetric=False) == HALF_CIRCLE


def test_the_plan_counts_the_full_vessel_solves_apart(library):
    """Three heels is not three times one heel: it is one half-circle solve and
    two whole-circle ones, and a single figure would under-count the job.
    """
    preview = plan(library, mixed_job())

    assert preview.conditions_to_create == 3
    assert preview.solves_to_run == 3
    assert preview.solves_on_a_full_vessel == 2, "heel != 0 gets a full mesh"
    assert preview.directions == len(HALF_CIRCLE)
    assert preview.directions_full == len(WHOLE_CIRCLE)

    periods = len(COARSE.periods)
    assert preview.problems == periods * (6 + 5) + 2 * periods * (6 + 8)


def test_an_asymmetric_hull_makes_every_solve_a_full_vessel_one(tmp_path):
    """Symmetry is derived from the hull *and* the heel, so a hull nobody
    declared symmetric puts every condition on the full-vessel grid.
    """
    with Pylot.create(
        tmp_path / "asymmetric.pylot",
        vessel_name="Boxboat",
        origin_description="stern, centerline, keel",
        vertices=BOX_VERTICES,
        faces=BOX_FACES,
        is_xz_symmetric=False,
    ) as library:
        preview = plan(library, mixed_job(heels=(0.0,), z_origins=(-3.0, -2.0)))

    assert preview.solves_to_run == 2
    assert preview.solves_on_a_full_vessel == 2, "no declared symmetry, so nothing to mirror"


def test_each_solve_is_given_the_grid_its_own_mesh_asks_for(library):
    """End to end, on the stored results: the half-vessel result carries half
    the circle and the full-vessel one carries all of it.
    """
    BatchRun(library, mixed_job()).run()

    by_symmetry = {}
    for result in library.results():
        mesh = library.mesh(result.mesh_id)
        by_symmetry.setdefault(mesh.is_xz_symmetric, []).append(sorted(result.wave_directions))

    assert by_symmetry[True] == [list(HALF_CIRCLE)], "the unheeled condition, meshed as a half"
    assert by_symmetry[False] == [list(WHOLE_CIRCLE)] * 2


def test_a_full_vessel_solved_over_half_the_circle_is_warned_about(library):
    """The one thing about a heading grid that nothing downstream detects.

    mafredo does not refuse a heading past 180 — it interpolates across
    whatever was never solved and returns a confident, wrong number. A batch
    running overnight has no screen to look at, so this has to be in the log.
    """
    events = []
    BatchRun(library, mixed_job(wave_directions_full=HALF_CIRCLE)).run(progress=events.append)

    warnings = [e.message for e in events if e.kind == "warning" and "compass" in e.message]
    assert len(warnings) == 2, "one per full-vessel solve, and none for the half-vessel one"


def test_a_full_vessel_solved_over_the_whole_circle_is_not_warned_about(library):
    """A warning that is always on is one nobody reads."""
    events = []
    BatchRun(library, mixed_job()).run(progress=events.append)

    assert not [e for e in events if e.kind == "warning" and "compass" in e.message]


def test_both_grids_survive_a_round_trip_through_a_file(tmp_path):
    job = mixed_job()
    assert load_job(save_job(job, tmp_path / "n")) == job


def test_a_job_file_written_before_there_were_two_grids_still_loads(tmp_path):
    """Fields load as defaults when absent, so an older file means what it
    always meant: one grid, used for whatever the job meshes.
    """
    path = tmp_path / "old.pylotjob"
    path.write_text(
        '{"pylot_batch_job": 1, "wave_directions": [0, 90, 180]}', encoding="utf-8"
    )
    job = load_job(path)

    assert job.wave_directions_full == ()
    assert job.directions_for(is_xz_symmetric=False) == (0.0, 90.0, 180.0)
