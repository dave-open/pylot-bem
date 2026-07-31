"""The whole chain, once: library -> condition -> mesh -> solve -> store -> match.

Spec 05 section 5 check 7. Every phase built so far participates, and the
assertion is the one that matters: a database retrieved by *matching* carries
the same numbers as one solved directly. Anything that quietly corrupts a
value on its way through storage, assembly or the bridge shows up here and
nowhere else.

This is also the answer to the previous suite's central failure. It mocked the
solver so thoroughly that tests asserted their own mock's return values, and
the generated case names never met the parser, so a load-bearing mismatch
stayed invisible while the suite was green.
"""

import numpy as np
import pytest
from hull import make_base_shape
from pylot_bem.mesh_pipeline import application_point_for, build_mesh
from pylot_bem.solver import SolveSettings, solve, solver_provenance

from pylot_db.assembly import assemble, databases
from pylot_db.frames import condition_from_global, decompose, transform
from pylot_db.hyddb import to_hyddb1
from pylot_db.matching import deliver, select
from pylot_db.storage import Library
from pylot_db.validation import validate

OMEGAS = (0.5, 0.9)
DIRECTIONS = (0.0, 90.0, 180.0)
COARSE = {"pct": 20.0, "iterations": 5}
FILTERS = {"water_depth": np.inf, "forward_speed": 0.0}

DRAFTS = (-3.0, -4.0, -5.0)


@pytest.fixture(scope="module")
def built_library(tmp_path_factory):
    """A real library: three drafts, each meshed and solved for real."""
    base = make_base_shape()
    path = tmp_path_factory.mktemp("e2e") / "boxboat.pylot"

    library = Library.create(
        path,
        vessel_name="Boxboat",
        origin_description="stern, centerline, keel",
        vertices=base.vertices,
        faces=base.faces,
        is_xz_symmetric=base.is_xz_symmetric,
    )

    for index, z_origin in enumerate(DRAFTS):
        pose = transform(0.0, 0.0, z_origin)
        point_local = application_point_for(base, pose)
        point_diffraction = (pose @ np.append(point_local, 1.0))[:3]

        condition = library.add_condition(
            trim=0.0,
            heel=0.0,
            z_origin=z_origin,
            application_point=point_local,
            condition_id=f"draft{index}",
        )
        geometry = build_mesh(base, pose, **COARSE)
        mesh = library.add_mesh(
            condition_id=condition.id,
            vertices=geometry.vertices,
            faces=geometry.faces,
            **COARSE,
            mesh_id=f"mesh{index}",
        )

        dataset = solve(
            geometry.vertices,
            geometry.faces,
            is_xz_symmetric=geometry.is_xz_symmetric,
            application_point=point_diffraction,
            settings=SolveSettings(omegas=OMEGAS, wave_directions=DIRECTIONS),
        )
        name, version = solver_provenance(dataset)
        library.add_result(
            mesh_id=mesh.id,
            data=dataset,
            water_depth=np.inf,
            solver_name=name,
            solver_version=version,
            result_id=f"result{index}",
        )

    yield library
    library.close()


@pytest.fixture(scope="module")
def reference_hyddb():
    """The middle draft, solved and converted without ever touching storage.

    Converted with the **same delivery settings** the library will use --
    the density, and the XZ symmetry that fills in the port half of the
    circle. Both are applied when a database is handed out rather than when
    it is stored, so a reference built without them would be a different
    database and this test would be comparing two correct things.
    """
    base = make_base_shape()
    pose = transform(0.0, 0.0, -4.0)
    point_local = application_point_for(base, pose)
    point_diffraction = (pose @ np.append(point_local, 1.0))[:3]

    geometry = build_mesh(base, pose, **COARSE)
    dataset = solve(
        geometry.vertices,
        geometry.faces,
        is_xz_symmetric=geometry.is_xz_symmetric,
        application_point=point_diffraction,
        settings=SolveSettings(omegas=OMEGAS, wave_directions=DIRECTIONS),
    )
    return to_hyddb1(
        dataset,
        application_point=point_diffraction,
        rho=1.025,
        is_xz_symmetric=geometry.is_xz_symmetric,
    )


# --------------------------------------------------------------------------
# The library that came out of it
# --------------------------------------------------------------------------


def test_the_built_library_validates_clean(built_library):
    assert validate(built_library) == []


def test_every_condition_produced_a_usable_database(built_library):
    views = databases(built_library)
    assert len(views) == len(DRAFTS)
    assert all(view.usable for view in views)


def test_it_survives_a_close_and_reopen(built_library):
    with Library.open(built_library.path) as reopened:
        assert validate(reopened) == []
        assert len(reopened.conditions()) == len(DRAFTS)
        assert reopened.results()[0].solver_name == "Capytaine"


# --------------------------------------------------------------------------
# Matching picks the right one
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("pose_z", "expected"), [(-3.05, "draft0"), (-4.0, "draft1"), (-4.9, "draft2")])
def test_matching_finds_the_nearest_draft(built_library, pose_z, expected):
    ranking = select(built_library, z_origin=pose_z, **FILTERS)
    assert ranking.best.condition.id == expected


def test_an_exact_pose_reads_zero_probe_error(built_library):
    ranking = select(built_library, z_origin=-4.0, **FILTERS)
    assert ranking.best.rms_error == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize("yaw", [0.0, 60.0, 180.0])
@pytest.mark.parametrize(("dx", "dy"), [(0.0, 0.0), (500.0, -300.0)])
def test_the_same_vessel_anywhere_at_any_heading_matches_the_same_condition(built_library, yaw, dx, dy):
    """A vessel moves and turns during a simulation; its draft does not.

    ``select`` takes three scalars, so this now runs the route a caller holding
    a world transform actually takes: project it with ``condition_from_global``
    and hand over what comes out. The invariance is the same exact algebra it
    always was -- it has simply moved to where it is visible.
    """
    c, s = np.cos(np.radians(yaw)), np.sin(np.radians(yaw))
    rotation = np.eye(4)
    rotation[0, 0], rotation[0, 1], rotation[1, 0], rotation[1, 1] = c, -s, s, c
    translation = np.eye(4)
    translation[:3, 3] = [dx, dy, 0.0]

    posed = translation @ rotation @ transform(0.0, 0.0, -4.0)
    scalars = decompose(condition_from_global(posed))
    assert scalars == pytest.approx(decompose(transform(0.0, 0.0, -4.0))), "yaw and position drop out"

    ranking = select(built_library, **scalars._asdict(), **FILTERS)

    assert ranking.best.condition.id == "draft1"
    assert ranking.best.rms_error == pytest.approx(0.0, abs=1e-9)


# --------------------------------------------------------------------------
# Check 7: the retrieved database equals the directly-solved one
# --------------------------------------------------------------------------


def test_the_matched_database_equals_a_direct_solve(built_library, reference_hyddb):
    """The whole point. Storage, assembly, matching and the bridge must all be
    transparent -- what goes in comes out.
    """
    selection = deliver(built_library, select(built_library, z_origin=-4.0, **FILTERS).best, rho=1.025)
    retrieved = selection.hyddb

    assert np.allclose(retrieved.frequencies, reference_hyddb.frequencies)
    assert np.allclose(retrieved.wave_directions, reference_hyddb.wave_directions)
    assert max(retrieved.wave_directions) > 180.0, (
        "a symmetric hull is solved over half the circle and delivered over all of it; "
        "if this ever reads 180 the mirroring has silently stopped happening"
    )

    for omega in OMEGAS:
        assert np.allclose(retrieved.amass(omega), reference_hyddb.amass(omega), rtol=1e-9)
        assert np.allclose(retrieved.damping(omega), reference_hyddb.damping(omega), rtol=1e-9)
        for direction in DIRECTIONS:
            assert np.allclose(
                retrieved.force(omega, direction),
                reference_hyddb.force(omega, direction),
                rtol=1e-9,
            )


def test_the_phase_origin_survives_the_round_trip(built_library, reference_hyddb):
    """It is metadata mafredo carries but never applies, so nothing else would
    notice if storage dropped it.
    """
    selection = deliver(built_library, select(built_library, z_origin=-4.0, **FILTERS).best, rho=1.025)

    assert selection.hyddb.phase_origin == pytest.approx(reference_hyddb.phase_origin)
    assert selection.hyddb.phase_origin[0] != 0.0, "the box's application point is not at x = 0"


def test_the_delivered_application_point_is_vessel_local(built_library):
    """Stored vessel-local, so it is comparable across conditions and is what
    the runtime and the user both work in.
    """
    selection = deliver(built_library, select(built_library, z_origin=-4.0, **FILTERS).best, rho=1.025)

    assert selection.application_point == pytest.approx([30.0, 0.0, 2.0], abs=1e-9)


def test_a_deeper_draft_gives_a_deeper_application_point(built_library):
    points = {}
    for pose_z, name in zip(DRAFTS, ("draft0", "draft1", "draft2"), strict=True):
        ranking = select(built_library, z_origin=pose_z, **FILTERS)
        assert ranking.best.condition.id == name
        points[name] = deliver(built_library, ranking.best, rho=1.025).application_point

    assert points["draft0"][2] < points["draft1"][2] < points["draft2"][2]


# --------------------------------------------------------------------------
# Assembling directly by key gives the same thing
# --------------------------------------------------------------------------


def test_assembling_by_key_and_by_matching_agree(built_library):
    ranking = select(built_library, z_origin=-4.0, **FILTERS)
    by_key = assemble(built_library, ranking.best.key, rho=1.025)
    by_match = deliver(built_library, ranking.best, rho=1.025).hyddb

    assert np.allclose(by_key.amass(0.9), by_match.amass(0.9))
    assert by_key.phase_origin == pytest.approx(by_match.phase_origin)


# --------------------------------------------------------------------------
# Spec 04 section 8: solving half the circle and mirroring the rest
# --------------------------------------------------------------------------
#
# The decision that section deferred, taken here because its own precondition
# was this comparison: expand a half-circle solve and check it against the same
# hull solved all the way round.


@pytest.fixture(scope="module")
def half_and_full():
    """One symmetric mesh, solved over 0-180 and over the whole circle."""
    base = make_base_shape()
    pose = transform(0.0, 0.0, -4.0)
    point = (pose @ np.append(application_point_for(base, pose), 1.0))[:3]
    geometry = build_mesh(base, pose, **COARSE)
    assert geometry.is_xz_symmetric, "the point of the fixture"

    def run(directions):
        return solve(
            geometry.vertices,
            geometry.faces,
            is_xz_symmetric=geometry.is_xz_symmetric,
            application_point=point,
            settings=SolveSettings(omegas=OMEGAS, wave_directions=directions),
        )

    half = run(tuple(float(d) for d in range(0, 181, 45)))
    full = run(tuple(float(d) for d in range(0, 360, 45)))
    return half, full, point


def test_expanding_half_the_circle_equals_solving_all_of_it(half_and_full):
    """The test spec 04 section 8 asks for by name.

    If this holds, solving the port half of a symmetric hull is computing
    numbers that are already known, and the interface is right to default to
    0-180. If it ever stops holding, that default is silently inventing data.
    """
    half, full, point = half_and_full

    expanded = to_hyddb1(half, rho=1.025, application_point=point, is_xz_symmetric=True)
    solved = to_hyddb1(full, rho=1.025, application_point=point, is_xz_symmetric=True)

    assert np.allclose(expanded.wave_directions, solved.wave_directions)
    assert max(expanded.wave_directions) > 180.0, "the expansion did not happen"

    for omega in OMEGAS:
        for direction in solved.wave_directions:
            assert np.allclose(
                expanded.force(omega, float(direction)),
                solved.force(omega, float(direction)),
                atol=1e-9,
            ), f"omega {omega}, direction {direction}"


def test_the_comparison_above_would_notice_a_difference(half_and_full):
    """Sanity-check the mechanism, not only its outcome.

    Both sides come from the same mesh, so a comparison that accidentally
    compared something with itself would pass just as well. Beam seas differ
    from head seas by a factor of thirty here; if they did not, the test above
    would be satisfied by any two databases at all.
    """
    _half, full, point = half_and_full
    solved = to_hyddb1(full, rho=1.025, application_point=point, is_xz_symmetric=True)

    head = abs(solved.force(0.5, 0.0)[1])
    beam = abs(solved.force(0.5, 90.0)[1])
    assert beam > 10 * max(head, 1e-9), f"sway at 0 deg {head}, at 90 deg {beam}"


def test_without_the_expansion_the_gap_is_filled_with_nonsense(half_and_full):
    """Why the expansion is not optional.

    A half-circle database delivered as-is does not refuse a direction past
    180 -- mafredo interpolates straight across the unsolved half and returns a
    confident, wrong number. Measured on a tanker: 431 kN of sway at beam seas
    from port where starboard gave 64 000.
    """
    half, _full, point = half_and_full

    unexpanded = to_hyddb1(half, rho=1.025, application_point=point, is_xz_symmetric=False)
    expanded = to_hyddb1(half, rho=1.025, application_point=point, is_xz_symmetric=True)

    assert max(unexpanded.wave_directions) <= 180.0
    starboard = abs(expanded.force(0.5, 90.0)[1])
    port_wrong = abs(unexpanded.force(0.5, 270.0)[1])
    port_right = abs(expanded.force(0.5, 270.0)[1])

    assert np.isclose(port_right, starboard), "mirrored beam seas should match"
    assert port_wrong < 0.5 * starboard, (
        "the unexpanded database happens to be right at 270 deg, so this test "
        "no longer demonstrates anything -- check whether mafredo now refuses "
        "out-of-range directions instead of interpolating"
    )
