"""Spec 04 section 10: the solver and the mafredo bridge.

Every solve here runs the real Capytaine on a coarse box. Nothing is mocked:
the previous suite's central failure was mocking the solver so thoroughly that
tests asserted their own mock's return values, and in-process Capytaine (ADR-1)
makes the real path cheap enough that there is no excuse.
"""

import logging
from itertools import groupby

import numpy as np
import pytest
from hull import make_base_shape
from mafredo.hyddb1 import Hyddb1
from pylot_db.hyddb import STORED_RHO, BridgeError, to_hyddb1
from pylot_bem.mesh_pipeline import application_point_for, build_mesh
from pylot_bem.solver import (
    KG_PER_TONNE,
    SOLVE_RHO,
    SOLVE_RHO_SI,
    SolveSettings,
    SolverError,
    build_body,
    make_problems,
    solve,
    solver_provenance,
)
from pylot_db.frames import transform, transform_points

import capytaine as cpt

DESIGN = transform(trim=0.0, heel=0.0, z_origin=-4.0)
COARSE = {"pct": 20.0, "iterations": 5}

# Unequal counts on purpose: a square grid hides a transposed force array,
# because mafredo can only compare lengths (spec 04 section 7.3).
OMEGAS = (0.5, 0.8, 1.2)
DIRECTIONS = (0.0, 45.0, 90.0, 180.0)


@pytest.fixture(scope="module")
def box_mesh():
    base = make_base_shape(is_xz_symmetric=False)
    mesh = build_mesh(base, DESIGN, **COARSE)
    point_local = application_point_for(base, DESIGN)
    point_diffraction = (DESIGN @ np.append(point_local, 1.0))[:3]
    return mesh, point_diffraction


@pytest.fixture(scope="module")
def settings():
    return SolveSettings(omegas=OMEGAS, wave_directions=DIRECTIONS)


@pytest.fixture(scope="module")
def dataset(box_mesh, settings):
    mesh, point = box_mesh
    return solve(
        mesh.vertices,
        mesh.faces,
        is_xz_symmetric=mesh.is_xz_symmetric,
        application_point=point,
        settings=settings,
    )


def raw_dataset(mesh, point, settings):
    """The dataset *before* the Froude-Krylov and diffraction parts are dropped."""
    body = build_body(mesh.vertices, mesh.faces, is_xz_symmetric=mesh.is_xz_symmetric, application_point=point)
    results = cpt.BEMSolver().solve_all(make_problems(body, settings), progress_bar=False)
    return cpt.assemble_dataset(results)


# --------------------------------------------------------------------------
# 1. The excitation identity, and what is stored
# --------------------------------------------------------------------------


def test_excitation_equals_froude_krylov_plus_diffraction(box_mesh, settings):
    """A free correctness check on the whole chain.

    Capytaine computes all three from the same solve, so this costs nothing.
    Checked before the components are dropped, because afterwards it cannot be
    checked at all.
    """
    raw = raw_dataset(*box_mesh, settings)
    assert np.allclose(
        raw["excitation_force"].values,
        raw["Froude_Krylov_force"].values + raw["diffraction_force"].values,
        rtol=1e-8,
    )


def test_a_broken_identity_raises(box_mesh, settings):
    """The guard: if the check could not fail, it would not be a check."""
    from pylot_bem.solver import _check_excitation_identity

    raw = raw_dataset(*box_mesh, settings).copy()
    raw["diffraction_force"] = raw["diffraction_force"] * 2.0

    with pytest.raises(SolverError, match="excitation_force !="):
        _check_excitation_identity(raw)


def test_only_the_excitation_survives(dataset):
    """The components are worth a third of the complex data and nothing else."""
    assert set(dataset.data_vars) == {"added_mass", "radiation_damping", "excitation_force"}
    assert "Froude_Krylov_force" not in dataset
    assert "diffraction_force" not in dataset


def test_a_radiation_only_solve_skips_the_identity_check(box_mesh):
    mesh, point = box_mesh
    radiation_only = solve(
        mesh.vertices,
        mesh.faces,
        is_xz_symmetric=mesh.is_xz_symmetric,
        application_point=point,
        settings=SolveSettings(omegas=(0.8,)),
    )
    assert "added_mass" in radiation_only
    assert "excitation_force" not in radiation_only


# --------------------------------------------------------------------------
# 2. Route equivalence -- the safety net for every conversion
# --------------------------------------------------------------------------


def test_our_bridge_agrees_with_mafredos_own_converter(box_mesh, settings):
    """The whole of spec 04 section 7.2, in one assertion.

    Units, dof ordering, direction conversion and phase extraction are all
    ours now. Any one of them silently wrong produces a plausible database, so
    they are checked against the converter that already worked.
    """
    raw = raw_dataset(*box_mesh, settings)

    ours = to_hyddb1(raw, rho=STORED_RHO)
    theirs = Hyddb1.create_from_capytaine_dataset(raw)

    assert np.allclose(ours.frequencies, theirs.frequencies)
    assert np.allclose(ours.wave_directions, theirs.wave_directions)
    for omega in OMEGAS:
        assert np.allclose(ours.amass(omega), theirs.amass(omega), rtol=1e-9)
        assert np.allclose(ours.damping(omega), theirs.damping(omega), rtol=1e-9)
        for direction in DIRECTIONS:
            assert np.allclose(ours.force(omega, direction), theirs.force(omega, direction), rtol=1e-9)


def test_the_grid_is_deliberately_not_square(settings):
    """The premise of the layout checks: a square grid hides a transposition."""
    assert len(settings.omegas) != len(settings.wave_directions)


# --------------------------------------------------------------------------
# 2b. Units
# --------------------------------------------------------------------------


def test_capytaine_is_run_in_si_not_tonnes():
    """Storage is t/m3; Capytaine is an SI code and mafredo divides by 1000.

    Those three facts only fit together if the conversion happens at this
    boundary. The prototype passed 1.025 straight in, which works by linearity
    but is a *different* convention -- combining the two scales an entire
    database by 1000.
    """
    assert SOLVE_RHO == 1.0, "results are stored per unit density"
    assert SOLVE_RHO_SI == 1000.0
    assert KG_PER_TONNE == 1000.0


def test_there_is_no_way_to_ask_for_another_density():
    """The normalisation has to be a guarantee, not a habit. A rho on
    SolveSettings would let a caller store a result that is not per unit
    density, and nothing downstream could tell.
    """
    assert not hasattr(SolveSettings(omegas=(0.5,)), "rho")

    with pytest.raises(TypeError):
        SolveSettings(omegas=(0.5,), rho=1.025)


def test_added_mass_is_in_tonnes_of_a_plausible_size(dataset):
    """A 60 x 20 x 4 m box displaces 4920 t at rho = 1.025.

    Heave added mass of the same order is right; 9.5 or 9.5 million would be a
    factor-1000 error, which is the failure this checks for and which no
    equivalence test could catch, since both routes would be wrong together.
    """
    hyddb = to_hyddb1(dataset, rho=1.025)
    heave = float(hyddb.amass(0.8)[2, 2])

    displacement = 60 * 20 * 4 * 1.025
    assert displacement < heave < 10 * displacement


# --------------------------------------------------------------------------
# 3. The application point -- the highest-value test here
# --------------------------------------------------------------------------


def test_the_application_point_moves_moments_but_not_force_phases(box_mesh, settings):
    """Spec 01 section 5.3, checked directly.

    ``rotation_center`` defines where moments are taken. It must change the
    rotational added mass and leave the *translational* force phases alone --
    the phase origin is fixed by construction and no choice of application
    point may move it. This is the test the previous design most needed and
    never had.
    """
    mesh, _ = box_mesh
    common = {
        "vertices": mesh.vertices,
        "faces": mesh.faces,
        "is_xz_symmetric": mesh.is_xz_symmetric,
        "settings": settings,
    }
    at_origin = solve(application_point=np.zeros(3), **common)
    moved = solve(application_point=np.array([5.0, 0.0, 0.0]), **common)

    pitch = dict(radiating_dof="Pitch", influenced_dof="Pitch")
    assert not np.allclose(
        at_origin["added_mass"].sel(**pitch).values,
        moved["added_mass"].sel(**pitch).values,
    ), "moving the moment reference must change rotational added mass"

    for dof in ("Surge", "Sway", "Heave"):
        assert np.allclose(
            np.angle(at_origin["excitation_force"].sel(influenced_dof=dof).values),
            np.angle(moved["excitation_force"].sel(influenced_dof=dof).values),
            atol=1e-9,
        ), f"{dof} force phase must not depend on the application point"


def test_translational_force_amplitudes_are_also_unmoved(box_mesh, settings):
    mesh, _ = box_mesh
    common = {
        "vertices": mesh.vertices,
        "faces": mesh.faces,
        "is_xz_symmetric": mesh.is_xz_symmetric,
        "settings": settings,
    }
    at_origin = solve(application_point=np.zeros(3), **common)
    moved = solve(application_point=np.array([5.0, 0.0, 0.0]), **common)

    for dof in ("Surge", "Sway", "Heave"):
        assert np.allclose(
            at_origin["excitation_force"].sel(influenced_dof=dof).values,
            moved["excitation_force"].sel(influenced_dof=dof).values,
            rtol=1e-9,
        )


# --------------------------------------------------------------------------
# 4, 5. Settings and provenance
# --------------------------------------------------------------------------


def test_the_settings_reach_the_solver_unchanged(dataset, settings):
    assert np.allclose(dataset["omega"].values, OMEGAS)
    assert np.allclose(np.degrees(dataset["wave_direction"].values), DIRECTIONS)
    assert float(dataset["rho"]) == SOLVE_RHO_SI
    assert float(dataset["g"]) == settings.g


@pytest.mark.parametrize(("depth", "speed"), [(np.inf, 0.0), (50.0, 0.0), (50.0, 1.5)])
def test_water_depth_and_forward_speed_are_inputs_not_constants(box_mesh, depth, speed):
    """The previous implementation pinned these inside accessor functions,
    which made both dimensions unusable for matching.
    """
    mesh, point = box_mesh
    result = solve(
        mesh.vertices,
        mesh.faces,
        is_xz_symmetric=mesh.is_xz_symmetric,
        application_point=point,
        settings=SolveSettings(omegas=(0.8,), wave_directions=(0.0,), water_depth=depth, forward_speed=speed),
    )
    assert float(result["water_depth"]) == depth
    assert np.unique(np.atleast_1d(result["forward_speed"].values)) == pytest.approx([speed])


def test_provenance_comes_from_what_actually_ran(dataset):
    name, version = solver_provenance(dataset)
    assert name == "Capytaine"
    assert version == cpt.__version__
    assert version != "unknown"


# --------------------------------------------------------------------------
# 7. The phase origin offset
# --------------------------------------------------------------------------


def test_phase_origin_is_the_negated_application_point(dataset, box_mesh):
    """The phase origin is diffraction (0, 0) by construction, so the offset
    mafredo carries is simply its negation -- and only x and y mean anything.
    """
    _, point = box_mesh
    hyddb = to_hyddb1(dataset, application_point=point, rho=1.025)
    assert hyddb.phase_origin == pytest.approx((-point[0], -point[1]))
    assert len(hyddb.phase_origin) == 2, "z carries no information and is not stored"


def test_phase_origin_defaults_to_coincident(dataset):
    assert to_hyddb1(dataset, rho=1.025).phase_origin == (0.0, 0.0)


def test_mafredo_stores_the_offset_without_applying_it(dataset, box_mesh):
    """It is metadata for the consumer, not a correction mafredo performs.

    Force RAOs are identical whatever the offset says; dave-dynamics must apply
    it when forming moments. A database is not "corrected" because the field is
    populated.
    """
    _, point = box_mesh
    plain = to_hyddb1(dataset, rho=1.025)
    offset = to_hyddb1(dataset, application_point=point, rho=1.025)

    assert offset.phase_origin != plain.phase_origin
    assert np.allclose(offset.force(0.8, 45.0), plain.force(0.8, 45.0))


# --------------------------------------------------------------------------
# 8. Wave-direction convention -- regression guard
# --------------------------------------------------------------------------


def test_wave_direction_is_the_direction_of_travel(settings):
    """A body further along +x is reached later by a wave travelling toward +x.

    This fixes the convention from Capytaine's own output rather than from any
    documentation -- mafredo's says "coming from" and is wrong. A 180 degree
    error here is silent and physically plausible, which is why a cheap guard
    is worth keeping.
    """
    base = make_base_shape(is_xz_symmetric=False)
    mesh = build_mesh(base, DESIGN, **COARSE)
    shifted = mesh.vertices + np.array([100.0, 0.0, 0.0])

    one_omega = SolveSettings(omegas=(0.8,), wave_directions=(0.0,))
    here = solve(
        mesh.vertices,
        mesh.faces,
        is_xz_symmetric=False,
        application_point=np.zeros(3),
        settings=one_omega,
    )
    further = solve(
        shifted,
        mesh.faces,
        is_xz_symmetric=False,
        application_point=np.array([100.0, 0.0, 0.0]),
        settings=one_omega,
    )

    heave = dict(influenced_dof="Heave", wave_direction=0.0, omega=0.8)
    phase_here = float(np.angle(here["excitation_force"].sel(**heave).values))
    phase_further = float(np.angle(further["excitation_force"].sel(**heave).values))

    # The excitation varies as exp(+i k x) along the direction of travel, so a
    # body 100 m further along +x differs by +k*d. Measured, not assumed: an
    # earlier version of this test guessed the opposite sign from "reached
    # later", which conflates the spatial phase with the time convention. The
    # magnitude came out exactly right either way, which is what identified the
    # error as one of sign alone.
    #
    # If direction 0 meant "coming from +x" this difference would be negative,
    # which is precisely the 180-degree error the guard exists to catch.
    k = 0.8**2 / 9.81  # deep-water wavenumber
    difference = np.angle(np.exp(1j * (phase_further - phase_here)))
    assert difference == pytest.approx(np.angle(np.exp(1j * k * 100.0)), abs=0.2)
    assert difference > 0.0, "a negative difference would mean the convention is reversed"


def test_directions_are_converted_to_degrees_without_an_offset(dataset):
    hyddb = to_hyddb1(dataset, rho=1.025)
    assert np.allclose(hyddb.wave_directions, DIRECTIONS)


# --------------------------------------------------------------------------
# 7.3 Layout guards
# --------------------------------------------------------------------------


def test_a_dataset_missing_a_variable_is_refused(dataset):
    with pytest.raises(BridgeError, match="radiation_damping"):
        to_hyddb1(dataset.drop_vars("radiation_damping"), rho=1.025)


def test_a_dataset_missing_a_dof_is_refused(dataset):
    without_yaw = dataset.sel(influenced_dof=["Surge", "Sway", "Heave", "Roll", "Pitch"])
    with pytest.raises(BridgeError, match="Yaw"):
        to_hyddb1(without_yaw, rho=1.025)


def test_dofs_are_reordered_into_mafredos_order_not_taken_as_they_come(dataset):
    """Capytaine labels dofs by name and promises no order.

    Taking them as they arrive would silently permute a 6x6 matrix -- roll and
    pitch exchanged is plausible-looking output.
    """
    shuffled = dataset.sel(
        influenced_dof=["Yaw", "Heave", "Surge", "Pitch", "Sway", "Roll"],
        radiating_dof=["Pitch", "Sway", "Yaw", "Surge", "Roll", "Heave"],
    )
    assert np.allclose(to_hyddb1(shuffled, rho=1.025).amass(0.8), to_hyddb1(dataset, rho=1.025).amass(0.8))


# --------------------------------------------------------------------------
# Progress and cancellation
# --------------------------------------------------------------------------


def test_progress_is_reported_once_per_frequency(box_mesh):
    """Spec 06 section 6.5.1, and measured there: the influence matrices are
    assembled once per frequency and cached for that frequency's remaining
    problems, so the first of ten problems does nearly all the work. A
    per-problem count reads as a hang followed by a jump.

    Asserted as the exact call sequence, so a hook that fired per problem,
    fired twice, or counted down would all fail.
    """
    mesh, point = box_mesh
    settings = SolveSettings(omegas=OMEGAS, wave_directions=DIRECTIONS)
    calls = []

    solve(
        mesh.vertices,
        mesh.faces,
        is_xz_symmetric=mesh.is_xz_symmetric,
        application_point=point,
        settings=settings,
        progress=lambda done, total: calls.append((done, total)),
    )

    assert calls == [(n, len(OMEGAS)) for n in range(1, len(OMEGAS) + 1)]
    assert len(OMEGAS) < len(OMEGAS) * (6 + len(DIRECTIONS)), "frequencies, not problems -- the two differ here"


def test_a_solve_without_a_progress_hook_still_works(box_mesh, dataset):
    """The guard on the hook: it is optional, and its absence changes nothing."""
    assert "added_mass" in dataset  # the module fixture solved with progress=None


def test_raising_from_the_progress_hook_stops_the_solve(box_mesh):
    """Cancellation, with no mechanism of its own. The count proves it stopped
    where it was told rather than running to the end and raising at the finish.
    """
    mesh, point = box_mesh
    calls = []

    class Cancelled(Exception):
        pass

    def stop_after_the_second_frequency(done, total):
        calls.append(done)
        if done == 2:
            raise Cancelled

    with pytest.raises(Cancelled):
        solve(
            mesh.vertices,
            mesh.faces,
            is_xz_symmetric=mesh.is_xz_symmetric,
            application_point=point,
            settings=SolveSettings(omegas=OMEGAS),
            progress=stop_after_the_second_frequency,
        )

    assert calls == [1, 2], "stopped at the frequency boundary it was told to, not at the end"
    assert len(OMEGAS) == 3, "the premise: there was a third frequency left to skip"


def test_the_grouping_guard_catches_problems_that_are_not_frequency_major(box_mesh, settings):
    """``groupby`` only groups *adjacent* equal keys.

    Nothing re-sorts the problems now, so an ordering mistake would split one
    frequency into two groups: the progress total would be wrong, and the
    O(N^2) influence matrices would be rebuilt for it. Checked rather than
    trusted.
    """
    from pylot_bem.solver import _check_grouping

    mesh, point = box_mesh
    body = build_body(
        mesh.vertices, mesh.faces, is_xz_symmetric=mesh.is_xz_symmetric, application_point=point
    )
    problems = make_problems(body, settings)
    scattered = sorted(problems, key=str)  # anything but frequency-major
    groups = [list(g) for _, g in groupby(scattered, key=lambda p: float(p.omega))]

    assert len(groups) > len(OMEGAS), "the premise: this ordering really is interleaved"
    with pytest.raises(SolverError, match="frequency-major"):
        _check_grouping(groups, scattered)


def test_the_problems_reach_the_solver_frequency_major(box_mesh, settings):
    """``solve_all`` used to re-sort the problems, so this ordering was a
    redundant agreement with Capytaine. Nothing re-sorts them now, and the
    influence-matrix cache holds exactly one entry -- so a frequency appearing
    twice in the sequence means the O(N^2) matrices are rebuilt for it.
    """
    mesh, point = box_mesh
    body = build_body(
        mesh.vertices, mesh.faces, is_xz_symmetric=mesh.is_xz_symmetric, application_point=point
    )
    omegas = [float(problem.omega) for problem in make_problems(body, settings)]

    assert omegas == sorted(omegas), "grouped, so each frequency is contiguous"
    assert len(set(omegas)) == len(OMEGAS)


def test_capytaines_pre_flight_warnings_still_reach_the_caller(box_mesh, caplog):
    """A guard on a private dependency.

    ``solve`` drives the problems itself, so it has to run Capytaine's
    pre-flight checks by hand -- and both are private methods. If a future
    Capytaine renames them, that has to fail here rather than silently take
    away two warnings that name the offending frequencies.

    They are **log records**, not ``warnings.warn`` -- so they reach a terminal
    through ``logging.lastResort`` and are invisible to ``pytest.warns``. Worth
    pinning: an application that configures logging decides whether its users
    ever see them.
    """
    mesh, point = box_mesh

    with caplog.at_level(logging.WARNING, logger="capytaine"):
        solve(
            mesh.vertices,
            mesh.faces,
            is_xz_symmetric=mesh.is_xz_symmetric,
            application_point=point,
            # Far too short for a mesh this coarse: about a 1.6 s wave.
            settings=SolveSettings(omegas=(4.0,)),
        )

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "resolution of the mesh might be insufficient" in logged
    assert "Irregular frequencies" in logged
    assert "4.000" in logged, "and it names the frequency, which our own check does not"


def test_the_pre_flight_warnings_are_not_repeated_per_problem(box_mesh, caplog):
    """The guard on the guard. Capytaine checks per *problem* by default, so
    running the checks up front only helps if the per-problem one is off --
    otherwise the same warning arrives six times and stops being read.
    """
    mesh, point = box_mesh

    with caplog.at_level(logging.WARNING, logger="capytaine"):
        solve(
            mesh.vertices,
            mesh.faces,
            is_xz_symmetric=mesh.is_xz_symmetric,
            application_point=point,
            settings=SolveSettings(omegas=(4.0,)),
        )

    resolution = [r for r in caplog.records if "resolution of the mesh" in r.getMessage()]
    assert len(resolution) == 1, "six radiation problems, one warning"


# --------------------------------------------------------------------------
# Where a lid goes, when one is wanted
# --------------------------------------------------------------------------


def test_the_auto_lid_sits_below_the_free_surface(boxboat):
    """A real answer is strictly negative. Zero means something else entirely."""
    from pylot_bem.mesh_pipeline import application_point_for, build_mesh
    from pylot_bem.solver import auto_lid_z

    mesh = build_mesh(boxboat, transform(trim=0.0, heel=0.0, z_origin=-4.0), pct=20.0, iterations=5)
    # A short period is a high frequency, which is where irregular frequencies
    # live and where the formula has an answer.
    z = auto_lid_z(
        mesh.vertices, mesh.faces, is_xz_symmetric=mesh.is_xz_symmetric, omega_max=2 * np.pi / 2.0
    )

    assert z is not None
    assert z < 0.0
    assert z > -10.0, "a lid below the keel would be nonsense"


def test_the_auto_lid_reports_no_answer_outside_its_domain(boxboat):
    """The trap of spec 09 section E.2, checked against what Capytaine does.

    Out of domain ``arctanh`` gives NaN, but ``lowest_lid_position`` starts at
    ``z_lid = 0.0`` and takes ``min(0.0, nan)``, which in Python is **0.0** --
    a valid-looking instruction to lid the free surface. So the absence has to
    be detected from the sign, not from ``isfinite``.
    """
    from pylot_bem.mesh_pipeline import build_mesh
    from pylot_bem.solver import auto_lid_z

    mesh = build_mesh(boxboat, transform(trim=0.0, heel=0.0, z_origin=-4.0), pct=20.0, iterations=5)
    # A long period is a low frequency: no irregular frequencies in range.
    assert (
        auto_lid_z(mesh.vertices, mesh.faces, is_xz_symmetric=mesh.is_xz_symmetric, omega_max=2 * np.pi / 20.0)
        is None
    )


def test_capytaine_really_returns_zero_rather_than_nan(boxboat):
    """Pin the behaviour the check above exists for.

    If a later Capytaine returns NaN instead, this fails and the reasoning in
    ``auto_lid_z`` can be simplified. If it silently changed and nothing
    checked, a user would get a free-surface lid they never asked for.
    """
    from pylot_bem.capytaine_mesh import to_capytaine_mesh
    from pylot_bem.mesh_pipeline import build_mesh

    mesh = build_mesh(boxboat, transform(trim=0.0, heel=0.0, z_origin=-4.0), pct=20.0, iterations=5)
    cpt_mesh = to_capytaine_mesh(
        mesh.vertices, mesh.faces, is_xz_symmetric=mesh.is_xz_symmetric, name="probe"
    )
    with np.errstate(invalid="ignore", divide="ignore"):
        raw = cpt_mesh.lowest_lid_position(2 * np.pi / 20.0)

    assert raw == 0.0, f"Capytaine now returns {raw!r} out of domain; auto_lid_z can be simplified"


# --------------------------------------------------------------------------
# The fixture is the right way out
# --------------------------------------------------------------------------


def test_the_box_fixture_is_wound_outward():
    """A hull wound inside out solves, and lies.

    This was true of the pylot-db copy of the same box for the whole of its
    life: the triangles were the same, the winding reversed, and because
    nothing in that package solves it was invisible there. Three test modules
    here imported it and put it through Capytaine.
    """
    from hull import BOX_FACES, BOX_VERTICES

    a, b, c = BOX_VERTICES[BOX_FACES[:, 0]], BOX_VERTICES[BOX_FACES[:, 1]], BOX_VERTICES[BOX_FACES[:, 2]]
    normals = np.cross(b - a, c - a)
    centres = (a + b + c) / 3
    # Divergence theorem: positive for outward normals, negative for inward.
    signed = float(np.sum(np.einsum("ij,ij->i", centres, normals)) / 6)

    assert signed == pytest.approx(60 * 20 * 10), "the box is 60 x 20 x 10 and wound outward"


def test_an_inside_out_hull_gives_unphysical_added_mass(boxboat):
    """Why the check above is worth having, measured rather than asserted.

    Heave added mass is a positive quantity. Solve the same box with its
    normals reversed and it comes back around -47,000,000 -- and nothing else
    in the suite would notice, because every other test asserts on structure.
    """
    from pylot_bem.mesh_pipeline import build_mesh
    from pylot_db.entities import BaseShape

    pose = transform(trim=0.0, heel=0.0, z_origin=-4.0)
    settings = SolveSettings(omegas=(0.5,))

    def heave_added_mass(faces):
        base = BaseShape(
            vertices=boxboat.vertices,
            faces=np.asarray(faces),
            is_xz_symmetric=True,
            probe_xy=np.zeros((4, 2)),
        )
        geometry = build_mesh(base, pose, pct=20.0, iterations=5)
        dataset = solve(
            geometry.vertices,
            geometry.faces,
            is_xz_symmetric=geometry.is_xz_symmetric,
            application_point=transform_points(application_point_for(base, pose), pose),
            settings=settings,
        )
        return float(dataset["added_mass"].sel(radiating_dof="Heave", influenced_dof="Heave").values[0])

    assert heave_added_mass(boxboat.faces) > 0.0, "the fixture as shipped is physical"
    assert heave_added_mass(boxboat.faces[:, ::-1]) < 0.0, "reversed, it is not"
