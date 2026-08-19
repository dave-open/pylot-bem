"""Spec 11: the object-oriented API.

Every test here drives :class:`~pylot_bem.api.Pylot` the way a caller would --
a real STL, a real mesh, a real Capytaine solve on a coarse box. Nothing is
mocked. Where a test needs a dataset that disagrees with its settings, it takes
a genuinely solved one and lies about the settings, rather than fabricating a
dataset that might not resemble Capytaine's output.

The facade exists for the derivations, so most of these assert that a value was
*derived* rather than accepted -- and each one also asserts the derived value is
not the trivial one, because a test that would pass against zeros is a test
that cannot fail.
"""

import numpy as np
import pytest
from hull import BOX_FACES, BOX_VERTICES, TANKER_STL
from pymeshup import Load

from pylot_bem.angles import slope_from_degrees
from pylot_bem.api import Pylot, _check_dataset_matches, condition_name
from pylot_bem.mesh_pipeline import MeshPipelineError, application_point_for
from pylot_bem.solver import SolveSettings, SolverError
from pylot_db.frames import decompose, transform
from pylot_db.storage import Library, LibraryError

COARSE = {"pct": 20.0, "iterations": 5}
OMEGAS = (0.5, 0.9)
DIRECTIONS = (0.0, 90.0)


def make_box(path, **overrides):
    """A boxboat library through the inherited create, so no STL is needed."""
    kwargs = {
        "vessel_name": "Boxboat",
        "origin_description": "stern, centerline, keel",
        "vertices": BOX_VERTICES,
        "faces": BOX_FACES,
        "is_xz_symmetric": True,
    }
    kwargs.update(overrides)
    return Pylot.create(path, **kwargs)


@pytest.fixture
def box(tmp_path):
    with make_box(tmp_path / "box.pylot") as library:
        yield library


@pytest.fixture(scope="module")
def solved(tmp_path_factory):
    """One real solve, reused: condition -> mesh -> result, all through Pylot."""
    library = make_box(tmp_path_factory.mktemp("api") / "solved.pylot")
    condition = library.create_condition(z_origin=-4.0, condition_id="design")
    mesh = library.create_mesh(condition, **COARSE, mesh_id="fine")
    result = library.run_solve(
        mesh,
        SolveSettings(omegas=OMEGAS, wave_directions=DIRECTIONS, g=9.8),
        result_id="run1",
    )
    yield library, condition, mesh, result
    library.close()


# --------------------------------------------------------------------------
# create_new: the STL boundary
# --------------------------------------------------------------------------


def test_create_new_reads_the_mesh_file(tmp_path):
    with Pylot.create_new(
        tmp_path / "tanker.pylot", TANKER_STL, "stern, centerline, keel", is_xz_symmetric=True
    ) as library:
        base = library.base_shape
        assert len(base.vertices) == 246
        assert len(base.faces) == 488
        assert base.is_xz_symmetric is True


def test_scale_is_applied_at_import(tmp_path):
    """The only unit conversion in the system. Compared against the unscaled
    import, so a scale that silently did nothing would fail.
    """
    plain = Pylot.create_new(tmp_path / "m.pylot", TANKER_STL, "keel", is_xz_symmetric=True)
    scaled = Pylot.create_new(tmp_path / "mm.pylot", TANKER_STL, "keel", is_xz_symmetric=True, scale=0.001)

    lo, hi = plain.base_shape.bounds
    lo_scaled, hi_scaled = scaled.base_shape.bounds

    assert np.ptp(hi - lo) > 1.0, "the unscaled hull is metres across, so the comparison means something"
    assert np.allclose(hi_scaled - lo_scaled, (hi - lo) / 1000.0)
    plain.close()
    scaled.close()


def test_a_non_positive_scale_is_refused(tmp_path):
    with pytest.raises(ValueError, match="mirrors the hull"):
        Pylot.create_new(tmp_path / "x.pylot", TANKER_STL, "keel", is_xz_symmetric=True, scale=-1.0)


def test_the_vessel_name_defaults_to_the_file_stem(tmp_path):
    with Pylot.create_new(tmp_path / "anything.pylot", TANKER_STL, "keel", is_xz_symmetric=True) as library:
        assert library.info.vessel_name == "tanker"


def test_an_explicit_vessel_name_wins(tmp_path):
    with Pylot.create_new(
        tmp_path / "a.pylot", TANKER_STL, "keel", is_xz_symmetric=True, vessel_name="Aframax"
    ) as library:
        assert library.info.vessel_name == "Aframax"


def test_a_half_mesh_is_refused_and_leaves_no_library_behind(tmp_path):
    """Spec 02 section 1 asks for this **at import**. The point is not only
    that it raises: it must raise before the file exists, because a library
    that has to be deleted by hand is a worse outcome than a refusal.
    """
    half = tmp_path / "half.stl"
    Load(str(TANKER_STL)).cut_at_xz().save(str(half))

    path = tmp_path / "half.pylot"
    with pytest.raises(MeshPipelineError, match="one side of y = 0"):
        Pylot.create_new(path, half, "keel", is_xz_symmetric=True)

    assert not path.exists(), "refused before anything was written"


def test_symmetry_must_be_declared(tmp_path):
    """No default. Nothing can derive it -- the tanker's own tessellation is
    not mirrored -- so guessing would be guessing about the physics.
    """
    with pytest.raises(TypeError, match="is_xz_symmetric"):
        Pylot.create_new(tmp_path / "x.pylot", TANKER_STL, "keel")


def test_open_returns_a_pylot_not_a_library(tmp_path):
    make_box(tmp_path / "b.pylot").close()
    with Pylot.open(tmp_path / "b.pylot") as reopened:
        assert isinstance(reopened, Pylot)
        assert hasattr(reopened, "create_condition")


# --------------------------------------------------------------------------
# create_condition: the application point is derived
# --------------------------------------------------------------------------


def test_the_application_point_is_derived_from_the_submerged_geometry(box):
    condition = box.create_condition(z_origin=-4.0)
    expected = application_point_for(box.base_shape, transform(0.0, 0.0, -4.0))

    assert condition.application_point == pytest.approx(expected)
    assert condition.application_point == pytest.approx([30.0, 0.0, 2.0]), "mid-length, centreline, mid-draft"


def test_a_deeper_condition_moves_the_application_point(box):
    shallow = box.create_condition(z_origin=-2.0)
    deep = box.create_condition(z_origin=-6.0)

    assert deep.application_point[2] > shallow.application_point[2], "half of a deeper draft is higher off the keel"


def test_heel_and_trim_are_slopes_not_degrees(box):
    """CLAUDE.md: slopes in storage and every API, degrees in the UI only.
    0.1 as a slope is 5.7 degrees; 0.1 degrees would store a slope of 0.0017.
    """
    condition = box.create_condition(z_origin=-4.0, heel=0.1)

    assert condition.heel == pytest.approx(0.1)
    assert decompose(condition.transform).heel == pytest.approx(0.1)


def test_a_condition_out_of_the_valid_domain_is_refused(box):
    with pytest.raises(ValueError):
        box.create_condition(z_origin=-4.0, heel=1.5, trim=1.5)


def test_a_condition_with_nothing_submerged_is_refused(box):
    with pytest.raises(MeshPipelineError, match="below the waterplane"):
        box.create_condition(z_origin=5.0)


# --------------------------------------------------------------------------
# create_mesh
# --------------------------------------------------------------------------


def test_the_mesh_is_a_half_vessel_when_the_condition_allows_it(box):
    upright = box.create_mesh(box.create_condition(z_origin=-4.0), **COARSE)
    heeled = box.create_mesh(box.create_condition(z_origin=-4.0, heel=0.2), **COARSE)

    assert upright.is_xz_symmetric is True
    assert heeled.is_xz_symmetric is False, "a heeled vessel is not symmetric, whatever the hull is"


def test_a_condition_may_be_named_by_object_or_by_id(box):
    condition = box.create_condition(z_origin=-4.0, condition_id="design")
    by_object = box.create_mesh(condition, **COARSE)
    by_id = box.create_mesh("design", **COARSE)

    assert by_object.condition_id == by_id.condition_id == "design"
    assert by_object.id != by_id.id, "two meshes, not one stored twice"


def test_the_regrid_settings_are_recorded_as_given(box):
    mesh = box.create_mesh(box.create_condition(z_origin=-4.0), pct=15.0, iterations=4)

    assert mesh.pct == pytest.approx(15.0)
    assert mesh.iterations == 4


# --------------------------------------------------------------------------
# The conversion that used to live in the CLI
# --------------------------------------------------------------------------


def test_the_application_point_is_converted_into_diffraction_space(box):
    condition = box.create_condition(z_origin=-4.0, condition_id="design")
    in_diffraction = box.application_point_in_diffraction_space("design")

    expected = (condition.transform @ np.append(condition.application_point, 1.0))[:3]
    assert in_diffraction == pytest.approx(expected)
    assert in_diffraction[2] == pytest.approx(-2.0), "mid-draft, below the waterplane"
    assert condition.application_point[2] == pytest.approx(2.0), "and above the keel in vessel coordinates"


def test_the_two_frames_disagree_by_the_draft(box):
    """The whole reason this method exists. Passing the stored point straight
    into the solver puts the moment reference out by exactly this much.
    """
    condition = box.create_condition(z_origin=-4.0)
    local = condition.application_point
    diffraction = box.application_point_in_diffraction_space(condition)

    assert diffraction[2] - local[2] == pytest.approx(-4.0)


# --------------------------------------------------------------------------
# run_solve
# --------------------------------------------------------------------------


def test_the_result_records_the_settings_the_solve_actually_used(solved):
    _, _, _, result = solved

    assert result.g == pytest.approx(9.8), "the non-default gravity reached storage"
    assert result.water_depth == np.inf
    assert result.forward_speed == 0.0


def test_a_result_records_no_density_at_all(solved):
    """There is nothing to record. Results are stored per unit density and
    scaled on delivery, so a stored result cannot be wrong about the density
    it was computed at -- the field it could be wrong in does not exist.
    """
    _, _, _, result = solved

    assert not hasattr(result, "rho")


def test_the_result_knows_what_it_covers(solved):
    _, _, mesh, result = solved

    assert result.mesh_id == mesh.id
    assert result.has_radiation is True
    assert result.has_diffraction is True
    assert result.omegas == pytest.approx(OMEGAS)
    assert result.wave_directions == pytest.approx(DIRECTIONS)


def test_the_solver_that_ran_is_recorded(solved):
    _, _, _, result = solved

    assert result.solver_name == "Capytaine"
    assert result.solver_version != "unknown"


def test_a_dataset_that_disagrees_with_the_settings_is_refused(solved):
    """A real solved dataset, checked against settings that lie about it.

    This is the gap the facade closes: solve() and add_result() each took the
    physical settings separately, so a result could record a density it was
    never computed at and would be unmatchable forever.
    """
    library, _, _, result = solved
    dataset = library.result_dataset(result.id)

    honest = SolveSettings(omegas=OMEGAS, wave_directions=DIRECTIONS, g=9.8)
    _check_dataset_matches(dataset, honest)  # the real one passes

    with pytest.raises(SolverError, match="water_depth"):
        _check_dataset_matches(dataset, SolveSettings(omegas=OMEGAS, g=9.8, water_depth=50.0))

    with pytest.raises(SolverError, match="g"):
        _check_dataset_matches(dataset, SolveSettings(omegas=OMEGAS, g=9.81))


def test_a_dataset_that_is_not_normalised_is_refused(solved):
    """The density check has no setting to compare against -- it compares
    against SOLVE_RHO_SI. That is what makes "stored per unit density" a
    property of the file rather than a promise about the code that wrote it.
    """
    library, _, _, result = solved
    dataset = library.result_dataset(result.id).assign_coords(rho=1025.0)

    with pytest.raises(SolverError, match="rho"):
        _check_dataset_matches(dataset, SolveSettings(omegas=OMEGAS, wave_directions=DIRECTIONS, g=9.8))


def test_the_lid_mode_is_derived_from_the_lid_position():
    assert SolveSettings(omegas=(1.0,), lid_z=None).lid_mode is None
    assert SolveSettings(omegas=(1.0,), lid_z=0.0).lid_mode == "free_surface"
    assert SolveSettings(omegas=(1.0,), lid_z=-0.2).lid_mode == "below_free_surface"


def test_progress_reaches_the_caller_through_run_solve(box):
    """The hook has to survive the facade. Per frequency, not per problem --
    spec 06 section 6.5.1, and the reason is measured there.
    """
    condition = box.create_condition(z_origin=-4.0)
    mesh = box.create_mesh(condition, **COARSE)
    calls = []

    box.run_solve(mesh, SolveSettings(omegas=OMEGAS, wave_directions=DIRECTIONS), progress=lambda *c: calls.append(c))

    assert calls == [(n, len(OMEGAS)) for n in range(1, len(OMEGAS) + 1)]


def test_raising_from_progress_cancels_and_stores_nothing(box):
    """The whole cancellation mechanism: no flag, no thread, no new machinery.
    A caller that wants to stop raises, and the library is untouched.
    """
    condition = box.create_condition(z_origin=-4.0)
    mesh = box.create_mesh(condition, **COARSE)

    class Cancelled(Exception):
        pass

    def stop_at_the_first_frequency(done, total):
        raise Cancelled

    with pytest.raises(Cancelled):
        box.run_solve(mesh, SolveSettings(omegas=OMEGAS), progress=stop_at_the_first_frequency)

    assert box.results() == [], "an interrupted solve writes nothing"


def test_a_mesh_may_be_named_by_object_or_by_id(solved):
    """Library.mesh takes either, so Pylot needs no resolver of its own."""
    library, _, mesh, _ = solved

    assert library.mesh(mesh.id).id == mesh.id
    assert library.mesh(mesh).id == mesh.id
    assert library.condition(library.condition("design")).id == "design"


def test_an_unknown_mesh_is_refused(box):
    with pytest.raises(LibraryError, match="no mesh"):
        box.run_solve("ghost", SolveSettings(omegas=OMEGAS))


# --------------------------------------------------------------------------
# The whole chain, through the facade only
# --------------------------------------------------------------------------


def test_the_facade_alone_produces_a_usable_library(solved):
    library, condition, _, _ = solved

    assert library.validate() == []

    views = library.databases()
    assert len(views) == 1
    assert views[0].usable, "radiation and diffraction at every frequency"
    assert views[0].key.condition_id == condition.id


def test_a_library_built_through_the_facade_matches_and_delivers(solved):
    """The read side, reached as methods on the same object that built it."""
    library, condition, _, _ = solved

    ranking = library.select(z_origin=-4.0, water_depth=np.inf, forward_speed=0.0)
    assert ranking.best.condition.id == condition.id
    assert ranking.best.rms_error == pytest.approx(0.0, abs=1e-12)

    selection = library.deliver(ranking.best, rho=1.025)
    assert selection.hyddb.frequencies == pytest.approx(OMEGAS)
    assert selection.application_point == pytest.approx(condition.application_point)


def test_a_plain_library_reads_what_the_facade_wrote(solved):
    """The split, demonstrated: no capytaine, no pymeshup, same file."""
    library, _, _, _ = solved

    with Library.open(library.path) as read_only:
        assert type(read_only) is Library
        assert read_only.validate() == []
        assert read_only.results()[0].solver_name == "Capytaine"


# --------------------------------------------------------------------------
# Storing what something else solved
# --------------------------------------------------------------------------


def test_store_result_records_the_same_checks_as_run_solve(solved, tmp_path):
    """The application drives the frequencies itself, and must not skip them.

    ``store_result`` is the second half of ``run_solve``, split out so the
    pooled path can reuse it rather than reimplement the checks -- which are
    what stop a result being recorded against conditions it was not solved at.
    """
    library, _condition, mesh, result = solved
    dataset = library.result_dataset(result.id)
    settings = SolveSettings(omegas=OMEGAS, wave_directions=DIRECTIONS, g=9.8)

    stored = library.store_result(mesh, dataset, settings, label="from a pool", result_id="pooled")

    assert stored.id == "pooled"
    assert stored.label == "from a pool"
    assert stored.g == 9.8
    assert np.allclose(stored.omegas, result.omegas)
    assert stored.solver_name == result.solver_name


def test_store_result_refuses_a_dataset_solved_at_other_conditions(solved):
    """The check that makes the split safe, rather than a copy waiting to rot."""
    library, _condition, mesh, result = solved
    dataset = library.result_dataset(result.id)

    # Everything else matches, so water depth is the only thing it can object
    # to -- otherwise this would pass on whichever setting it happened to
    # check first.
    with pytest.raises(SolverError, match="water_depth"):
        library.store_result(mesh, dataset, SolveSettings(omegas=OMEGAS, g=9.8, water_depth=30.0))


def test_store_result_accepts_a_shorter_grid_than_was_asked_for(solved):
    """A stopped run is a complete result over fewer frequencies (spec 06 §6.4).

    So the frequency grid is deliberately *not* checked, while everything
    physical still is. The grid recorded is the one in the dataset.
    """
    library, _condition, mesh, result = solved
    dataset = library.result_dataset(result.id)
    asked_for = SolveSettings(omegas=(*OMEGAS, 1.3, 1.7), wave_directions=DIRECTIONS, g=9.8)

    stored = library.store_result(mesh, dataset, asked_for, result_id="short")

    assert len(stored.omegas) == len(OMEGAS)
    assert np.allclose(stored.omegas, result.omegas)


# --------------------------------------------------------------------------
# A condition names itself
# --------------------------------------------------------------------------


def test_a_condition_is_named_after_what_floats_it(box):
    """The alternative shown everywhere a condition appears is its generated
    id, and a tree of seven hundred uuids is a tree nobody can read.
    """
    condition = box.create_condition(
        z_origin=-4.0, heel=slope_from_degrees(-1.0), trim=slope_from_degrees(2.0)
    )

    assert condition.label == "z-4.00_h-1.00_t2.00"


def test_the_name_is_in_degrees_because_every_column_is(box):
    """A slope in a label would be the one place in pylot that showed one."""
    condition = box.create_condition(z_origin=-4.0, heel=slope_from_degrees(30.0))

    assert condition.label == "z-4.00_h30.00_t0.00", "30 degrees, not its sine"


def test_a_label_that_was_given_is_never_replaced(box):
    condition = box.create_condition(z_origin=-4.0, label="Design draft, summer")

    assert condition.label == "Design draft, summer"


def test_the_name_never_reads_as_negative_zero():
    """A heel a hair below zero would otherwise show as "-0.00" — which looks
    like a typo in a column of otherwise identical rows.
    """
    assert condition_name(-3.0, -1e-9, -0.0) == "z-3.00_h0.00_t0.00"


def test_two_conditions_close_enough_to_be_one_read_alike():
    """Two decimals is one order finer than the 1e-3 at which two conditions
    are held to be the same condition, so rows that read alike are alike.
    """
    assert condition_name(-3.0, 0.0, 0.0) == condition_name(-3.0000001, 0.0, 0.0)


def test_the_name_is_a_label_and_never_an_id(box):
    """ADR-4: ids are opaque and nothing may parse one. The previous
    implementation encoded parameters into names and read them back out, which
    is the failure that rule exists to prevent — so this goes in the field that
    nothing anywhere parses and that can be corrected afterwards.
    """
    condition = box.create_condition(z_origin=-4.0)

    assert condition.id != condition.label
    assert "-4.00" not in condition.id
    # And it really is only a label: renaming it changes nothing else.
    box.set_condition_label(condition.id, "something else")
    assert box.condition(condition.id).z_origin == -4.0
