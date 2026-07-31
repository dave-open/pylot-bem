"""The eleven checks of spec 03 section 8.

The boxboat is 60 x 20 x 10 with its origin at stern / centerline / keel, so
at ``z_origin = -4`` every expected number can be worked out by hand:

- submerged box: 60 x 20 x 4, diffraction z from -4 to 0
- application point, diffraction: (30, 0, -2); vessel-local: (30, 0, 2)

Assertions are on **bounds, extents and face counts**, never on areas or
volumes. Those are not a requirement of this pipeline (spec 02 section 1), and
the surface area is in any case the one quantity the remesher does not
reproduce across processes.
"""

import numpy as np
import pytest
from hull import BOX_FACES, BOX_VERTICES, make_base_shape
from pylot_bem.capytaine_mesh import to_capytaine_mesh
from pylot_bem.mesh_pipeline import (
    MeshPipelineError,
    _as_volume,
    application_point_for,
    build_mesh,
    check_full_mesh,
)
from pylot_db.frames import transform

DESIGN = transform(trim=0.0, heel=0.0, z_origin=-4.0)

# Coarse settings: these tests are about geometry and ordering, not convergence.
COARSE = {"pct": 10.0, "iterations": 5}


# --------------------------------------------------------------------------
# 1. A box at a known condition gives the expected geometry
# --------------------------------------------------------------------------


def test_submerged_bounds_are_the_expected_box(asymmetric_boxboat):
    mesh = build_mesh(asymmetric_boxboat, DESIGN, **COARSE)
    lo, hi = mesh.vertices.min(axis=0), mesh.vertices.max(axis=0)
    assert lo == pytest.approx([0.0, -10.0, -4.0], abs=1e-9)
    assert hi == pytest.approx([60.0, 10.0, 0.0], abs=1e-9)


# --------------------------------------------------------------------------
# 2. Nothing survives above the waterplane
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("trim", "heel", "z_origin"),
    [(0.0, 0.0, -4.0), (0.1, 0.0, -4.0), (0.0, 0.05, -4.0), (0.05, -0.1, -6.0)],
)
def test_nothing_survives_above_the_waterplane(asymmetric_boxboat, trim, heel, z_origin):
    mesh = build_mesh(asymmetric_boxboat, transform(trim, heel, z_origin), **COARSE)
    assert mesh.vertices[:, 2].max() <= 1e-9, "the cut is at diffraction z = 0"


def test_the_cut_happens_in_diffraction_space_not_vessel_space(asymmetric_boxboat):
    """A trimmed vessel keeps a wedge, not a flat slice at a vessel-local z.

    If the transform were applied after the cut, the result would be a box.
    """
    mesh = build_mesh(asymmetric_boxboat, transform(0.1, 0.0, -4.0), **COARSE)
    in_vessel = (np.linalg.inv(transform(0.1, 0.0, -4.0)) @ np.c_[mesh.vertices, np.ones(len(mesh.vertices))].T).T
    assert np.ptp(in_vessel[:, 2]) > 1.0, "the wetted part spans a range of vessel-local z"


# --------------------------------------------------------------------------
# 3, 5. Symmetry
# --------------------------------------------------------------------------


def test_a_symmetric_hull_upright_is_cut_in_half(boxboat):
    mesh = build_mesh(boxboat, DESIGN, **COARSE)
    assert mesh.is_xz_symmetric is True
    assert mesh.vertices[:, 1].max() <= 1e-9, "cut_at_xz keeps negative y"
    assert mesh.vertices[:, 1].min() == pytest.approx(-10.0, abs=1e-9), "the full port side"


def test_heel_refuses_symmetry_and_keeps_the_whole_hull(boxboat):
    mesh = build_mesh(boxboat, transform(0.0, 0.05, -4.0), **COARSE)
    assert mesh.is_xz_symmetric is False
    assert mesh.vertices[:, 1].max() > 1.0, "both sides are kept"


@pytest.mark.parametrize("trim", [0.0, 0.05, -0.1])
def test_trim_preserves_symmetry(boxboat, trim):
    """Rotation about y keeps the y <-> -y mirror; only heel destroys it."""
    mesh = build_mesh(boxboat, transform(trim, 0.0, -4.0), **COARSE)
    assert mesh.is_xz_symmetric is True
    assert mesh.vertices[:, 1].max() <= 1e-9


def test_an_asymmetric_base_shape_never_uses_symmetry(asymmetric_boxboat):
    mesh = build_mesh(asymmetric_boxboat, DESIGN, **COARSE)
    assert mesh.is_xz_symmetric is False


# --------------------------------------------------------------------------
# 4. Determinism
# --------------------------------------------------------------------------


def test_building_twice_gives_exactly_the_same_mesh(boxboat):
    """Exactly. Not within tolerance.

    The prototype's regrid retry made output resolution depend on input
    density; a determinism test is what stops that creeping back.
    """
    first = build_mesh(boxboat, DESIGN, **COARSE)
    second = build_mesh(boxboat, DESIGN, **COARSE)
    assert np.array_equal(first.vertices, second.vertices)
    assert np.array_equal(first.faces, second.faces)


def test_different_settings_give_different_meshes(boxboat):
    """The guard on the determinism test: pct must actually do something."""
    coarse = build_mesh(boxboat, DESIGN, pct=20.0, iterations=5)
    fine = build_mesh(boxboat, DESIGN, pct=5.0, iterations=5)
    assert len(fine.faces) > len(coarse.faces)


# --------------------------------------------------------------------------
# 6. Meaningful failure
# --------------------------------------------------------------------------


def test_a_vessel_entirely_above_water_raises_with_the_numbers_in_the_message(boxboat):
    with pytest.raises(MeshPipelineError) as excinfo:
        build_mesh(boxboat, transform(0.0, 0.0, 50.0), **COARSE)

    message = str(excinfo.value)
    assert "nothing lies below the waterplane" in message
    assert "z_origin=50.0" in message
    assert "0.0..60.0" in message, "the base shape extent belongs in the message"


def test_an_empty_cut_is_never_returned_as_an_empty_mesh(boxboat):
    """pymeshup returns an empty mesh with degenerate bounds rather than raising."""
    with pytest.raises(MeshPipelineError):
        application_point_for(boxboat, transform(0.0, 0.0, 50.0))


# --------------------------------------------------------------------------
# 8. The two cuts commute
# --------------------------------------------------------------------------


def test_the_cut_order_gives_the_same_solid_but_not_the_same_tessellation(boxboat):
    """Measured, and it corrects what spec 03 section 1 originally claimed.

    The spec said the two half-space cuts "commute, so the resulting geometry
    is identical". They do not. The **bounds** agree exactly -- which is all the
    application point depends on, and the only reason the reorder was made --
    but the triangulations differ: 13 vertices one way, 12 the other, and still
    different after regridding.

    So the reorder is safe *for its purpose*, not neutral in general.
    """
    placed = _as_volume(boxboat.vertices, boxboat.faces).transform(DESIGN)

    waterline_first = placed.cut_at_waterline().cut_at_xz()
    xz_first = placed.cut_at_xz().cut_at_waterline()

    assert np.allclose(waterline_first.bounds, xz_first.bounds, atol=1e-9), (
        "the same solid, so the same application point"
    )

    a = np.asarray(waterline_first.vertices)
    b = np.asarray(xz_first.vertices)
    assert a.shape != b.shape, (
        "if these ever match, the spec claim was right after all and this test "
        "and spec 03 section 1 should both be revisited"
    )


# --------------------------------------------------------------------------
# 9. The application point
# --------------------------------------------------------------------------


def test_application_point_is_the_centre_of_the_submerged_bounds(boxboat):
    """Vessel-local (30, 0, 2) for a keel origin: half of the 4 m draft above the keel.

    In diffraction space the same point is (30, 0, -2) -- mid-draft, below the
    waterplane. Which frame you are reading matters, and the sign differs.
    """
    point = application_point_for(boxboat, DESIGN)
    assert point == pytest.approx([30.0, 0.0, 2.0], abs=1e-9)

    in_diffraction = DESIGN @ np.append(point, 1.0)
    assert in_diffraction[:3] == pytest.approx([30.0, 0.0, -2.0], abs=1e-9)


def test_application_point_is_on_the_centreline_for_a_symmetric_hull(boxboat):
    """Spec 01 invariant 9, which Phase 0 had to defer for want of geometry."""
    for trim in (0.0, 0.08, -0.12):
        point = application_point_for(boxboat, transform(trim, 0.0, -4.0))
        assert point[1] == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize(("pct", "iterations"), [(20.0, 5), (10.0, 5), (5.0, 10)])
def test_application_point_is_independent_of_mesh_density(boxboat, pct, iterations):
    """Refining a mesh must not move the moment reference of an existing database.

    That is why the bounds are taken before the regrid, not after.
    """
    assert application_point_for(boxboat, DESIGN) == pytest.approx([30.0, 0.0, 2.0], abs=1e-9)
    build_mesh(boxboat, DESIGN, pct=pct, iterations=iterations)  # must not affect it
    assert application_point_for(boxboat, DESIGN) == pytest.approx([30.0, 0.0, 2.0], abs=1e-9)


def test_application_point_uses_the_whole_vessel_not_the_symmetric_half(boxboat):
    """Taken before the XZ cut: a half-vessel y-bound would put it off centreline."""
    symmetric = application_point_for(boxboat, DESIGN)
    asymmetric = application_point_for(make_base_shape(is_xz_symmetric=False), DESIGN)
    assert symmetric == pytest.approx(asymmetric, abs=1e-12)


def test_application_point_moves_with_the_condition(boxboat):
    """A property of the submerged geometry, so a deeper draft gives a deeper point."""
    shallow = application_point_for(boxboat, transform(0.0, 0.0, -2.0))
    deep = application_point_for(boxboat, transform(0.0, 0.0, -6.0))
    assert shallow[2] == pytest.approx(1.0, abs=1e-9)
    assert deep[2] == pytest.approx(3.0, abs=1e-9)


# --------------------------------------------------------------------------
# 10. A half mesh is refused
# --------------------------------------------------------------------------


def half_box(side, residue=0.0):
    """A real half box: the far side collapsed onto the cut plane at y = 0.

    Not ``BOX_VERTICES[y >= 0]`` -- the box has vertices only at y = +/-10, so
    filtering leaves a flat plane rather than a half vessel, and a check could
    pass that for the wrong reason.

    ``residue`` puts the cut face slightly on the wrong side, which is what a
    real cutting tool produces.
    """
    vertices = BOX_VERTICES.copy()
    if side == "port":
        vertices[vertices[:, 1] < 0, 1] = -residue
    else:
        vertices[vertices[:, 1] > 0, 1] = residue
    return make_base_shape(vertices=vertices, faces=BOX_FACES)


@pytest.mark.parametrize("side", ["port", "starboard"])
def test_a_half_mesh_base_shape_is_refused(side):
    half = half_box(side)

    with pytest.raises(MeshPipelineError, match="half mesh"):
        build_mesh(half, DESIGN, **COARSE)
    with pytest.raises(MeshPipelineError, match="half mesh"):
        application_point_for(half, DESIGN)


@pytest.mark.parametrize("side", ["port", "starboard"])
def test_a_cut_leaves_residue_on_the_plane_and_is_still_refused(side):
    """The check is against the beam, not against exact zero.

    Halving the tanker fixture with ``cut_at_xz`` leaves ``y.max() = 3.6e-15``.
    An exact one-sided test passes that, the pipeline cuts it a second time,
    and the result is a quarter vessel whose only symptom is half the
    displacement -- which nothing downstream measures.
    """
    half = half_box(side, residue=1e-14)
    y = half.vertices[:, 1]
    assert y.min() < 0 < y.max(), "vertices genuinely straddle zero, so an exact test would pass this"

    with pytest.raises(MeshPipelineError, match="half mesh"):
        build_mesh(half, DESIGN, **COARSE)


def test_a_full_mesh_is_not_mistaken_for_a_half_mesh(boxboat):
    """The guard on the guard: the check must not reject legitimate input."""
    build_mesh(boxboat, DESIGN, **COARSE)


def test_a_lopsided_but_real_hull_is_accepted():
    """A hull may be strongly asymmetric without being a half mesh. The
    threshold is a millionth of the beam, so 'narrow on one side' is nowhere
    near it.
    """
    vertices = BOX_VERTICES.copy()
    vertices[vertices[:, 1] > 0, 1] = 0.1  # 0.1 m to port, 10 m to starboard

    build_mesh(make_base_shape(vertices=vertices, faces=BOX_FACES), DESIGN, **COARSE)


def test_a_flat_shape_is_named_as_such():
    """Zero width is a different fault from a half mesh, and saying "half mesh"
    would send the user looking for a cut that never happened.
    """
    vertices = BOX_VERTICES.copy()
    vertices[:, 1] = 0.0

    with pytest.raises(MeshPipelineError, match="no width"):
        check_full_mesh(vertices)


# --------------------------------------------------------------------------
# 11. No lid leaks into the mesh
# --------------------------------------------------------------------------


def test_the_pipeline_produces_hull_geometry_only(boxboat):
    """A lid belongs to the solve, not to the mesh (spec 04 section 2).

    Nothing may appear on the waterplane: a lid there would show up as a sheet
    of faces at z = 0, roughly the waterplane area.
    """
    mesh = build_mesh(boxboat, DESIGN, **COARSE)

    centroids = mesh.vertices[mesh.faces].mean(axis=1)
    on_waterplane = np.isclose(centroids[:, 2], 0.0, atol=1e-9)
    assert not on_waterplane.any(), "a lid would appear as a sheet of faces at z = 0"


# --------------------------------------------------------------------------
# Conversion to Capytaine
# --------------------------------------------------------------------------


def test_triangles_become_degenerate_quads(asymmetric_boxboat):
    mesh = build_mesh(asymmetric_boxboat, DESIGN, **COARSE)
    cpt_mesh = to_capytaine_mesh(mesh.vertices, mesh.faces, is_xz_symmetric=False)

    assert cpt_mesh.nb_faces == len(mesh.faces)
    assert cpt_mesh.faces.shape[1] == 4, "capytaine wants quads"
    assert np.array_equal(cpt_mesh.faces[:, 2], cpt_mesh.faces[:, 3]), "last vertex repeated"


def test_a_symmetric_mesh_is_wrapped_and_represents_the_whole_body(boxboat):
    mesh = build_mesh(boxboat, DESIGN, **COARSE)
    cpt_mesh = to_capytaine_mesh(mesh.vertices, mesh.faces, is_xz_symmetric=True)

    assert cpt_mesh.nb_faces == 2 * len(mesh.faces), "the half plus its mirror image"
    assert cpt_mesh.vertices[:, 1].max() == pytest.approx(10.0, abs=1e-9), "starboard restored"
    assert cpt_mesh.vertices[:, 1].min() == pytest.approx(-10.0, abs=1e-9)


def test_a_stored_mesh_can_be_converted_without_rerunning_the_pipeline(boxboat):
    """A mesh loaded from a library must be solvable on its own."""
    mesh = build_mesh(boxboat, DESIGN, **COARSE)
    vertices, faces, symmetric = mesh.vertices.copy(), mesh.faces.copy(), mesh.is_xz_symmetric

    del mesh
    cpt_mesh = to_capytaine_mesh(vertices, faces, is_xz_symmetric=symmetric)
    assert cpt_mesh.nb_faces > 0


# --------------------------------------------------------------------------
# Measuring the wetted part
# --------------------------------------------------------------------------


def test_the_submerged_summary_measures_a_box_by_hand(boxboat):
    """A 60 x 20 x 10 box at z_origin = -4 is arithmetic, not a golden value.

    Wetted area is the bottom plus four sides: 60*20 + 2*60*4 + 2*20*4.
    """
    from pylot_bem.mesh_pipeline import submerged_summary

    summary = submerged_summary(boxboat, transform(trim=0.0, heel=0.0, z_origin=-4.0))

    assert summary.wetted_area == pytest.approx(60 * 20 + 2 * 60 * 4 + 2 * 20 * 4)
    assert summary.waterline_length == pytest.approx(60.0)
    assert summary.lo == pytest.approx([0.0, -10.0, -4.0])
    assert summary.hi == pytest.approx([60.0, 10.0, 0.0], abs=1e-9)


def test_a_deeper_draft_is_more_wetted_area(boxboat):
    """Otherwise the measurement could be of the whole hull, cut or not."""
    from pylot_bem.mesh_pipeline import submerged_summary

    shallow = submerged_summary(boxboat, transform(trim=0.0, heel=0.0, z_origin=-2.0))
    deep = submerged_summary(boxboat, transform(trim=0.0, heel=0.0, z_origin=-8.0))

    assert deep.wetted_area > shallow.wetted_area
    assert deep.lo[2] == pytest.approx(-8.0)


def test_the_submerged_summary_refuses_a_condition_out_of_the_water(boxboat):
    from pylot_bem.mesh_pipeline import submerged_summary

    with pytest.raises(MeshPipelineError, match="below the waterplane"):
        submerged_summary(boxboat, transform(trim=0.0, heel=0.0, z_origin=5.0))
