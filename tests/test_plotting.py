"""Spec 11: getting meshes out, and looking at them.

Every render here runs **offscreen for real** -- an actual VTK render pass to
an actual PNG. Constructing a ``vedo.Mesh`` and asserting it exists would test
nothing; the interesting failures are geometry that arrives transposed, empty,
or in the wrong frame, and all three survive object construction.

The frame is the thing to watch. Nothing in a vertex array says whether it is
vessel-local or diffraction-space, so the tests that matter here are the ones
that pin which frame a mesh comes back in.
"""

import numpy as np
import pytest
from hull import BOX_FACES, BOX_VERTICES

from pylot_bem.api import Pylot
from pylot_bem.plotting import to_polydata, to_vedo, waterplane
from pylot_bem.solver import SolveSettings
from pylot_db.frames import transform_points

COARSE = {"pct": 20.0, "iterations": 5}


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    """A boxboat: 60 x 20 x 10, origin at stern / centerline / keel."""
    lib = Pylot.create(
        tmp_path_factory.mktemp("plot") / "box.pylot",
        vessel_name="Boxboat",
        origin_description="stern, centerline, keel",
        vertices=BOX_VERTICES,
        faces=BOX_FACES,
        is_xz_symmetric=True,
    )
    lib.create_condition(z_origin=-4.0, condition_id="design")
    lib.create_mesh("design", **COARSE, mesh_id="fine")
    lib.run_solve("fine", SolveSettings(omegas=(0.5, 0.9), wave_directions=(0.0, 90.0)), result_id="run1")
    yield lib
    lib.close()


# --------------------------------------------------------------------------
# Retrieval, and which frame it comes back in
# --------------------------------------------------------------------------


def test_the_base_shape_is_vessel_local(library):
    """Straight out of storage, as imported. The box's keel is at z = 0."""
    base = library.base_shape

    assert base.vertices[:, 2].min() == pytest.approx(0.0)
    assert base.vertices[:, 2].max() == pytest.approx(10.0)


def test_the_placed_base_shape_is_in_diffraction_space(library):
    """The whole reason base_shape_at exists: at z_origin = -4 the keel sits
    4 m under the waterplane and 6 m of the 10 m depth is dry.
    """
    placed = library.base_shape_at("design")

    assert placed.vertices[:, 2].min() == pytest.approx(-4.0)
    assert placed.vertices[:, 2].max() == pytest.approx(6.0)


def test_placing_moves_nothing_but_the_geometry(library):
    """Same faces, same count, same order -- only the coordinates change."""
    base = library.base_shape
    placed = library.base_shape_at("design")

    assert np.array_equal(placed.faces, base.faces)
    assert len(placed.vertices) == len(base.vertices)


def test_the_placed_hull_is_never_a_half_vessel(library):
    """The condition is upright on a symmetric hull, so the *calculation* mesh
    is half. The placed base shape is not: nothing is cut, and a viewer that
    drew half a hull against the water would be showing a lie.
    """
    placed = library.base_shape_at("design")

    assert placed.is_xz_symmetric is False
    assert placed.vertices[:, 1].min() < 0 < placed.vertices[:, 1].max()
    assert library.mesh("fine").is_xz_symmetric is True, "the premise: the mesh really is a half"


def test_a_condition_may_be_named_by_object_or_id(library):
    by_id = library.base_shape_at("design")
    by_object = library.base_shape_at(library.condition("design"))

    assert np.array_equal(by_id.vertices, by_object.vertices)


def test_the_probes_land_exactly_on_the_waterplane_once_placed(library):
    """What a surface probe *is*. The 3D view draws them in diffraction space,
    so if this were wrong they would visibly float; asserting it here means the
    picture is checked rather than merely produced.
    """
    condition = library.condition("design")
    placed = transform_points(condition.probes, condition.transform)

    assert placed[:, 2] == pytest.approx(0.0, abs=1e-12)


# --------------------------------------------------------------------------
# What the UI actually embeds
# --------------------------------------------------------------------------


def test_the_polydata_carries_every_vertex_and_face(library):
    mesh = library.mesh("fine")
    polydata = to_polydata(mesh)

    assert polydata.GetNumberOfPoints() == len(mesh.vertices)
    assert polydata.GetNumberOfCells() == len(mesh.faces)


def test_the_polydata_carries_the_actual_coordinates(library):
    """Counts alone would pass on a transposed or reordered array.

    Compared with a float32 tolerance, because that is what VTK stores: a
    ``vtkPoints`` is single precision. Fine for drawing, and a reason not to
    round-trip geometry through a polydata -- the arrays in storage are the
    ones to compute with.
    """
    from vtkmodules.util.numpy_support import vtk_to_numpy

    mesh = library.mesh("fine")
    points = vtk_to_numpy(to_polydata(mesh).GetPoints().GetData())

    assert points.dtype == np.float32
    assert np.allclose(points, mesh.vertices, atol=1e-4)


@pytest.mark.parametrize("what", ["base_shape", "placed", "mesh"])
def test_anything_with_vertices_and_faces_can_be_drawn(library, what):
    """Three different types, one duck type -- BaseShape, MeshGeometry and
    CalculationMesh have no common base class and do not need one.
    """
    source = {
        "base_shape": library.base_shape,
        "placed": library.base_shape_at("design"),
        "mesh": library.mesh("fine"),
    }[what]

    actor = to_vedo(source)
    assert actor.nvertices == len(source.vertices)
    assert actor.ncells == len(source.faces)


def test_the_waterplane_is_sized_per_axis(library):
    """A hull is long and narrow. A square plane sized to its length would put
    the horizon ten beams off the side.
    """
    placed = library.base_shape_at("design")
    x_lo, x_hi, y_lo, y_hi, z_lo, z_hi = waterplane(placed).bounds()

    assert z_lo == pytest.approx(0.0) and z_hi == pytest.approx(0.0), "it is the waterplane"
    assert x_hi - x_lo == pytest.approx(60.0 * 1.15, rel=1e-3)
    assert y_hi - y_lo == pytest.approx(20.0 * 1.15, rel=1e-3)


# --------------------------------------------------------------------------
# A real render
# --------------------------------------------------------------------------


def test_show_condition_renders_a_picture(library, tmp_path):
    """Offscreen, but a genuine VTK render pass to a genuine PNG."""
    from pylot_bem.plotting import show_condition

    png = tmp_path / "design.png"
    plotter = show_condition(library, "design", interactive=False, screenshot=png)
    plotter.close()

    assert png.exists()
    assert png.stat().st_size > 5000, "a blank canvas compresses to almost nothing"


def test_show_condition_can_leave_the_mesh_out(library, tmp_path):
    from pylot_bem.plotting import show_condition

    with_mesh = tmp_path / "with.png"
    without = tmp_path / "without.png"
    show_condition(library, "design", interactive=False, screenshot=with_mesh).close()
    show_condition(library, "design", mesh=False, interactive=False, screenshot=without).close()

    assert with_mesh.read_bytes() != without.read_bytes(), "the mesh visibly changed the picture"


def test_a_condition_with_no_mesh_still_renders(library, tmp_path):
    """The 3D view has to work before anything has been meshed."""
    from pylot_bem.plotting import show_condition

    library.create_condition(z_origin=-6.0, condition_id="bare")
    png = tmp_path / "bare.png"
    show_condition(library, "bare", interactive=False, screenshot=png).close()

    assert library.meshes("bare") == []
    assert png.exists()


# --------------------------------------------------------------------------
# The vedo-free conversion the application uses
# --------------------------------------------------------------------------


def test_the_polydata_conversion_agrees_with_vedo(library):
    """One geometry, two routes: this is what lets the app skip vedo entirely.

    ``pylot_bem.polydata`` exists because the Qt viewport must not import vedo,
    and a second conversion is only safe if it produces the same thing. Checked
    on the coordinates, not on the object: a transposed or truncated array
    builds a perfectly valid vtkPolyData.
    """
    from vtkmodules.util.numpy_support import vtk_to_numpy

    from pylot_bem.polydata import to_polydata as direct

    mesh = library.mesh("fine")
    theirs = to_vedo(mesh).dataset
    ours = direct(mesh)

    assert ours.GetNumberOfPoints() == theirs.GetNumberOfPoints() == len(mesh.vertices)
    assert ours.GetNumberOfPolys() == theirs.GetNumberOfPolys() == len(mesh.faces)
    assert np.allclose(
        vtk_to_numpy(ours.GetPoints().GetData()),
        vtk_to_numpy(theirs.GetPoints().GetData()),
    )


def test_the_polydata_carries_the_real_coordinates(library):
    """Sanity-check the comparison above rather than only its outcome."""
    from vtkmodules.util.numpy_support import vtk_to_numpy

    from pylot_bem.polydata import to_polydata as direct

    mesh = library.mesh("fine")
    points = vtk_to_numpy(direct(mesh).GetPoints().GetData())

    assert np.allclose(points, mesh.vertices, atol=1e-4), "single precision, so not exact"
    assert points.max() > 0.0 and points.min() < 0.0, "a mesh of zeros would satisfy any comparison"
