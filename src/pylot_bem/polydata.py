"""Meshes as ``vtkPolyData``, with nothing else attached.

One conversion, used by both things that draw: :mod:`pylot_bem.plotting`, which
opens a window from a script, and :mod:`pylot_bem.app.viewport`, which renders
into a Qt widget.

**This module does not import vedo**, so the application can render without
it: :mod:`pylot_bem.app.viewport` drives ``vtkmodules`` directly and vedo stays
where it earns its keep, in ``plotting.show()`` for scripts.

Worth two sentences, because the original reason was **wrong**. The split was
made after a Qt render widget died with an access violation whenever vedo had
been imported, and vedo looked like the cause. It is not. The cause is
``vtkmodules.vtkRenderingOpenGL2`` being imported *at all* -- vedo merely
happens to import it -- and under a Qt platform plugin that gives no native
window there is no pixel format to be had, so VTK crashes the process rather
than raising. :mod:`pylot_bem.app.viewport` imports that module deliberately
and refuses to initialise on such a platform; see ``BLIND_PLATFORMS`` there.

What survives is the smaller claim: vedo is a 0.4 s import the application
never needs, and it sets VTK render-window defaults of its own (8 multisamples,
8 alpha bit planes) that the viewport would then have to undo. Keeping it out
is worth doing. It is not what stops the crash.

Imports are from ``vtkmodules.*`` and never the top-level ``vtk`` shim
(spec 07 section 3.2), which eagerly imports every module and breaks when
another distribution supplies its own build. ``pymeshup`` does.
"""

import numpy as np
from pylot_db.entities import FloatArray, IntArray
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData

__all__ = ["to_polydata", "triangles_to_polydata"]


def triangles_to_polydata(vertices: FloatArray, faces: IntArray) -> vtkPolyData:
    """Build a ``vtkPolyData`` from vertices and triangle indices.

    Note that ``vtkPoints`` is **single precision** by default and left that
    way. That is fine for drawing and a reason not to compute with one: the
    arrays in storage are float64 and stay float64.

    Args:
        vertices: ``(N, 3)`` coordinates [m].
        faces: ``(M, 3)`` triangle vertex indices.

    Returns:
        The polydata, ready for a ``vtkPolyDataMapper``.
    """
    vertices = np.asarray(vertices, dtype=float)
    faces = np.asarray(faces)

    points = vtkPoints()
    points.SetNumberOfPoints(len(vertices))
    for index, point in enumerate(vertices):
        points.SetPoint(index, float(point[0]), float(point[1]), float(point[2]))

    triangles = vtkCellArray()
    for face in faces:
        triangles.InsertNextCell(3)
        for index in face[:3]:
            triangles.InsertCellPoint(int(index))

    polydata = vtkPolyData()
    polydata.SetPoints(points)
    polydata.SetPolys(triangles)
    return polydata


def to_polydata(mesh) -> vtkPolyData:
    """The ``vtkPolyData`` for anything carrying ``vertices`` and ``faces``.

    A :class:`~pylot_db.entities.BaseShape`, a
    :class:`~pylot_db.entities.CalculationMesh`, or a
    :class:`~pylot_bem.mesh_pipeline.MeshGeometry`. They are not all in the
    same **frame** and nothing in the geometry says which -- see
    :mod:`pylot_bem.plotting`.
    """
    return triangles_to_polydata(mesh.vertices, mesh.faces)
