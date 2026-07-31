"""The pipeline on a real hull, where a box cannot tell you anything.

``test_mesh_pipeline.py`` uses an analytic box so every expected number can be
derived by hand. That is the right way to check the *arithmetic*, and the wrong
way to check anything about **curvature or imperfect symmetry** -- a box has
flat axis-aligned faces, its remesh is trivial, and it is symmetric to the last
bit.

The tanker is 328 x 58 x 28 m, closed, and **nominally symmetric without being
exactly so**: under a millimetre of shape difference at the beam extremes, and
a tessellation that is not mirrored at all. Everything here is a check that
would pass vacuously on a box.

Includes spec 03 section 8 check 7, the fixture regression, which was the one
check the box tests did not cover.

Every assertion here is on an **exact** quantity -- face counts, bounds,
extents, the application point. Areas and volumes are deliberately not used:
they are not a requirement of this pipeline, and they are also the one thing
the remesher does not reproduce across processes (see REFERENCE below).
"""

import numpy as np
import pytest
from pylot_bem.mesh_pipeline import application_point_for, build_mesh
from pylot_db.frames import transform

# Draft 20 m on a hull whose keel sits at z ~ 0 and whose depth is 28 m.
LOADED = transform(trim=0.0, heel=0.0, z_origin=-20.0)

SETTINGS = {"pct": 2.0, "iterations": 20}

# --------------------------------------------------------------------------
# Reference values for the fixture regression (spec 03 section 8 check 7).
#
# Produced by this pipeline at pct=2.0, iterations=20 on tanker.stl, and
# verified stable over repeated runs in separate processes.
#
# Note what is *not* here. pymeshlab's isotropic remesher is reproducible
# within a process but not between them: repeated runs of an identical script
# settle on one of two surface areas 0.056% apart. Face counts, bounds and the
# application point were bit-identical in every run observed, because they are
# fixed before or independently of the remesh. So the regression is built on
# those and not on area -- which also happens to be what spec 02 section 1
# says these quantities are for, namely nothing load-bearing.
#
# If these fail, work out which happened: a pipeline change (the analytic box
# tests usually fail too) or a pymeshlab upgrade (they do not). Regenerate
# deliberately, never to turn a red test green.
# --------------------------------------------------------------------------
REFERENCE = {
    "full_faces": 1575,
    "half_faces": 829,
    "bounds_lo": (-5.5011, -29.0007, -20.003),
    "bounds_hi": (327.9289, 28.9969, 0.0),
    "half_bounds_hi": (327.9289, 0.0, 0.0),
    "application_point": (161.213913, 0.0, 9.9984860),
}

# The hull's own asymmetry, as built. Nominally symmetric, actually not.
TANKER_Y_MIN = -29.0007
TANKER_Y_MAX = 28.9999


# --------------------------------------------------------------------------
# 7. Fixture regression
# --------------------------------------------------------------------------


def test_the_full_hull_matches_its_stored_reference(asymmetric_tanker):
    mesh = build_mesh(asymmetric_tanker, LOADED, **SETTINGS)

    assert len(mesh.faces) == REFERENCE["full_faces"]
    assert mesh.vertices.min(axis=0) == pytest.approx(REFERENCE["bounds_lo"], abs=1e-4)
    assert mesh.vertices.max(axis=0) == pytest.approx(REFERENCE["bounds_hi"], abs=1e-4)


def test_the_symmetric_half_matches_its_stored_reference(tanker):
    mesh = build_mesh(tanker, LOADED, **SETTINGS)

    assert mesh.is_xz_symmetric is True
    assert len(mesh.faces) == REFERENCE["half_faces"]
    assert mesh.vertices.min(axis=0) == pytest.approx(REFERENCE["bounds_lo"], abs=1e-4)
    assert mesh.vertices.max(axis=0) == pytest.approx(REFERENCE["half_bounds_hi"], abs=1e-4)


def test_the_application_point_matches_its_stored_reference(tanker):
    """Exact to 1e-6, because it is taken *before* the regrid.

    The ordering rule in spec 03 section 5 exists so that refining a mesh
    cannot move the moment reference of an existing database. It turns out to
    shield the application point from the remesher's cross-process
    non-determinism as well.
    """
    point = application_point_for(tanker, LOADED)
    assert point == pytest.approx(REFERENCE["application_point"], abs=1e-6)


# --------------------------------------------------------------------------
# Imperfect symmetry -- the reason this fixture exists
# --------------------------------------------------------------------------


def test_the_hull_is_declared_symmetric_without_being_exactly_so(tanker):
    """Pins the premise the rest of this file rests on.

    If someone swaps the fixture for a perfectly symmetric hull, the tests
    below stop testing what they claim to, and this one says so.
    """
    y = tanker.vertices[:, 1]
    assert y.min() == pytest.approx(TANKER_Y_MIN, abs=1e-4)
    assert y.max() == pytest.approx(TANKER_Y_MAX, abs=1e-4)
    assert abs(y.min()) != pytest.approx(abs(y.max()), abs=1e-6), "not exactly symmetric"
    assert abs(y.min()) == pytest.approx(abs(y.max()), abs=1e-2), "but symmetric in intent"


def test_symmetry_is_a_declaration_not_a_derived_property(tanker, asymmetric_tanker):
    """The same geometry, meshed both ways, purely on what the modeller declared.

    A nearest-vertex mirror test on this hull reports a 28 m deviation, because
    the tessellation is not mirrored, while the surface it describes is
    symmetric to under a millimetre. Symmetry therefore cannot be derived from
    the mesh: it is a modelling statement, and spec 02 section 1 calling it "a
    property of the geometry alone" is misleading.
    """
    declared = build_mesh(tanker, LOADED, **SETTINGS)
    not_declared = build_mesh(asymmetric_tanker, LOADED, **SETTINGS)

    assert declared.is_xz_symmetric is True
    assert not_declared.is_xz_symmetric is False

    assert declared.vertices[:, 1].max() <= 1e-9, "declared symmetric -> cut to the port half"
    assert not_declared.vertices[:, 1].max() > 28.0, "not declared -> the whole beam is kept"


def test_a_declared_symmetric_hull_gets_its_point_exactly_on_the_centreline(tanker):
    """Spec 01 invariant 9, and it holds **exactly** even on an imperfect hull.

    The bounds of this hull put the centre at about -2 mm on a 58 m beam,
    because the surface is not modelled perfectly symmetrically. A hull the
    modeller declared symmetric, floating upright, is symmetric by definition,
    so that offset is an artefact of the model and not a moment reference.
    """
    assert application_point_for(tanker, LOADED)[1] == 0.0


def test_the_raw_bounds_really_are_off_centre(tanker):
    """The guard: without it the test above could pass on a hull that is
    already perfectly symmetric, and would prove nothing.
    """
    y = tanker.vertices[:, 1]
    assert (y.min() + y.max()) / 2 != 0.0, "this fixture is genuinely lopsided"


def test_a_hull_not_declared_symmetric_keeps_the_bounds_centre(asymmetric_tanker):
    """The rule keys on the declaration, not on the geometry."""
    y = application_point_for(asymmetric_tanker, LOADED)[1]
    assert y != 0.0
    assert abs(y) < 0.01


def test_heel_restores_the_bounds_centre_on_a_symmetric_hull(tanker):
    """Heel destroys the mirror, so the point follows the submerged form again."""
    y = application_point_for(tanker, transform(0.0, 0.05, -20.0))[1]
    assert abs(y) > 0.1, "a heeled hull is genuinely off-centre and must say so"


# --------------------------------------------------------------------------
# pct and iterations are real knobs
# --------------------------------------------------------------------------


def test_refining_produces_more_faces_over_a_wide_range(asymmetric_tanker):
    """On a box the face count barely responds, so `pct` could be ignored
    entirely without any box test noticing.
    """
    counts = [len(build_mesh(asymmetric_tanker, LOADED, pct=pct, iterations=20).faces) for pct in (10.0, 5.0, 2.0, 1.0)]

    assert counts == sorted(counts), f"refining must not coarsen: {counts}"
    assert counts[-1] > 20 * counts[0], "pct spans a wide range of densities"


def test_the_application_point_is_unmoved_by_refinement(tanker):
    """The reason the bounds are read before the regrid, on a hull where the
    regrid genuinely changes the surface.
    """
    points = [application_point_for(tanker, LOADED) for _ in range(2)]
    for pct in (10.0, 1.0):
        build_mesh(tanker, LOADED, pct=pct, iterations=20)
        points.append(application_point_for(tanker, LOADED))

    for point in points[1:]:
        assert point == pytest.approx(points[0], abs=1e-12)


# --------------------------------------------------------------------------
# Cutting through curvature
# --------------------------------------------------------------------------


def test_the_waterline_cut_follows_the_hull_form(asymmetric_tanker):
    """At a shallow draft the bow lifts clear, so the wetted length shortens.

    A box is prismatic and its wetted length never changes with draft, so this
    behaviour is invisible there.
    """
    deep = build_mesh(asymmetric_tanker, transform(0.0, 0.0, -20.0), **SETTINGS)
    shallow = build_mesh(asymmetric_tanker, transform(0.0, 0.0, -8.0), **SETTINGS)

    assert shallow.vertices[:, 0].min() > deep.vertices[:, 0].min() + 1.0
    assert shallow.vertices[:, 2].min() > deep.vertices[:, 2].min()


@pytest.mark.parametrize(
    ("trim", "heel", "z_origin"),
    [(0.0, 0.0, -20.0), (0.03, 0.0, -12.0), (0.0, 0.05, -12.0), (-0.02, -0.03, -16.0)],
)
def test_the_cut_is_always_at_the_diffraction_waterplane(asymmetric_tanker, trim, heel, z_origin):
    mesh = build_mesh(asymmetric_tanker, transform(trim, heel, z_origin), **SETTINGS)
    assert mesh.vertices[:, 2].max() <= 1e-9


def test_trim_changes_which_part_of_the_hull_is_wetted(asymmetric_tanker):
    """The cut plane is fixed in diffraction space; trim moves the hull through it."""
    level = build_mesh(asymmetric_tanker, transform(0.0, 0.0, -12.0), **SETTINGS)
    trimmed = build_mesh(asymmetric_tanker, transform(0.03, 0.0, -12.0), **SETTINGS)

    assert not np.isclose(level.vertices[:, 0].min(), trimmed.vertices[:, 0].min())


def test_heel_puts_one_side_deeper_than_the_other(asymmetric_tanker):
    heeled = build_mesh(asymmetric_tanker, transform(0.0, 0.05, -12.0), **SETTINGS)

    port = heeled.vertices[heeled.vertices[:, 1] < 0, 2].min()
    starboard = heeled.vertices[heeled.vertices[:, 1] > 0, 2].min()
    assert abs(port - starboard) > 0.5
