"""Looking at meshes.

Built on ``vedo``, which is the 3D display already in the stack (spec 07 §1)
and what spec 06 §2 commits the application to. ``vedo`` *is* VTK -- every
object here wraps a ``vtkPolyData``, reachable through :func:`to_polydata`, so
a Qt widget can render these without going through :func:`show` at all. That
split is the point: **the application embeds the polydata, a script calls
show()**.

Deliberately **not** imported by ``pylot_bem/__init__``. Importing ``vedo``
costs about 0.4 s and pulls in the whole of VTK, which the CLI has no use for::

    from pylot_bem.plotting import show, show_condition

Anything with ``vertices`` and ``faces`` can be drawn: a
:class:`~pylot_db.entities.BaseShape`, a
:class:`~pylot_db.entities.CalculationMesh`, a
:class:`~pylot_bem.mesh_pipeline.MeshGeometry`. They are not in the same
**frame**, though, and nothing in the geometry says which -- a base shape is
vessel-local and a calculation mesh is diffraction-space. Drawing both at once
is only meaningful once the hull is placed, which is what
:meth:`~pylot_bem.api.Pylot.base_shape_at` is for and what
:func:`show_condition` does.

The convention from spec 07 §3.2 applies to anything added here: import from
``vtkmodules.*``, never ``import vtk``. The top-level ``vtk`` shim eagerly
imports every module and breaks when another distribution supplies its own
build -- ``pymeshup`` does.
"""

from pathlib import Path

import numpy as np
import vedo
from vtkmodules.vtkCommonDataModel import vtkPolyData

from pylot_bem.palette import APPLICATION_POINT, CALCULATION_MESH, HULL, PROBE, SEA
from pylot_bem.polydata import to_polydata as _to_polydata
from pylot_db.entities import FloatArray
from pylot_db.frames import transform_points

__all__ = [
    "SEA",
    "show",
    "show_condition",
    "to_polydata",
    "to_vedo",
    "waterplane",
]


def to_vedo(mesh, *, color: str = HULL, alpha: float = 1.0, wireframe: bool = False) -> vedo.Mesh:
    """Wrap anything with ``vertices`` and ``faces`` as a :class:`vedo.Mesh`.

    Args:
        mesh: A ``BaseShape``, ``CalculationMesh``, ``MeshGeometry``, or any
            object carrying those two attributes.
        color: Any colour ``vedo`` understands.
        alpha: 0 transparent, 1 opaque.
        wireframe: Draw edges only.

    Returns:
        The mesh, ready to add to a scene.
    """
    actor = vedo.Mesh([np.asarray(mesh.vertices, dtype=float), np.asarray(mesh.faces)])
    actor.color(color).alpha(alpha).lighting("default")
    if wireframe:
        actor.wireframe(True)
    return actor


def to_polydata(mesh) -> vtkPolyData:
    """The ``vtkPolyData`` for a mesh. See :mod:`pylot_bem.polydata`.

    Re-exported here because this is the module a reader looking for "how do I
    draw one of these" finds first. The implementation lives next door
    **because it must not import vedo**, and the application uses it for
    exactly that reason.
    """
    return _to_polydata(mesh)


def waterplane(mesh, *, margin: float = 0.15) -> vedo.Mesh:
    """A translucent plane at ``z = 0``, sized to the mesh.

    Only meaningful for geometry in **diffraction space**, where ``z = 0`` is
    the waterplane by definition. On a vessel-local mesh it draws a plane
    through the vessel origin, which means nothing.
    """
    vertices = np.asarray(mesh.vertices, dtype=float)
    lo, hi = vertices.min(axis=0), vertices.max(axis=0)
    centre = (lo + hi) / 2

    # Per axis, not a square: a hull is long and narrow, and a plane sized to
    # its length would put the horizon 190 m off a 29 m half-beam.
    span = (hi[:2] - lo[:2]) * (1.0 + margin)
    plane = vedo.Plane(pos=(centre[0], centre[1], 0.0), normal=(0, 0, 1), s=tuple(span))
    return plane.color(SEA).alpha(0.25)


def _markers(points: FloatArray, *, color: str, radius: float) -> vedo.Points:
    return vedo.Points(np.atleast_2d(np.asarray(points, dtype=float)), r=radius).color(color)


def show(
    *items,
    title: str = "pylot",
    axes: int = 1,
    azimuth: float = -50.0,
    elevation: float = -20.0,
    interactive: bool = True,
    screenshot: str | Path | None = None,
) -> vedo.Plotter:
    """Open a window on some meshes.

    Args:
        items: ``vedo`` objects, or anything :func:`to_vedo` accepts.
        title: Window title.
        axes: ``vedo`` axes style. ``1`` is a labelled box.
        azimuth: Camera rotation about the vertical [deg].
        elevation: Camera tilt [deg]. Together with ``azimuth`` the defaults
            give a three-quarter view from slightly below the waterplane, which
            is the angle that shows a waterline at all -- ``vedo`` would
            otherwise reset to a plan view, where a hull is a silhouette and
            its draft is invisible.
        interactive: Block until the window is closed. **Pass ``False`` on a
            headless machine** -- it renders offscreen instead, which is also
            what makes ``screenshot`` work without a display.
        screenshot: Write a PNG here as well.

    Returns:
        The plotter, so a caller can keep adding to it.
    """
    actors = [item if isinstance(item, vedo.visual.CommonVisual) else to_vedo(item) for item in items]

    plotter = vedo.Plotter(title=title, offscreen=not interactive)
    # viewup="z" because z is up in every frame this project has (spec 01).
    plotter.show(*actors, axes=axes, viewup="z", azimuth=azimuth, elevation=elevation, interactive=False)
    if screenshot is not None:
        plotter.screenshot(str(screenshot))
    if interactive:
        plotter.interactive()
    return plotter


def show_condition(
    library,
    condition,
    *,
    mesh=None,
    probes: bool = True,
    application_point: bool = True,
    interactive: bool = True,
    screenshot: str | Path | None = None,
) -> vedo.Plotter:
    """The view the application needs: a hull sitting in the water.

    Everything is drawn in **diffraction space**, so the waterplane is ``z = 0``
    and the hull's position in it is the floating condition. That is the only
    frame in which putting the hull, the mesh and the waterline in one picture
    means anything.

    Args:
        library: An open :class:`~pylot_bem.api.Pylot`.
        condition: The condition, or its id.
        mesh: A calculation mesh to overlay, or its id. Defaults to the
            condition's first, if it has one. Pass ``False`` for none.
        probes: Mark the condition's surface probes. They lie on the waterplane
            by construction, so they should sit exactly in it -- which makes
            this a check as well as a display.
        application_point: Mark where the forces apply.
        interactive: See :func:`show`.
        screenshot: See :func:`show`.

    Returns:
        The plotter.
    """
    condition = library.condition(condition)
    placed = library.base_shape_at(condition)

    scene = [waterplane(placed), to_vedo(placed, color=HULL, alpha=0.35)]

    if mesh is None:
        candidates = library.meshes(condition.id)
        mesh = candidates[0] if candidates else False
    if mesh is not False:
        scene.append(to_vedo(library.mesh(mesh), color=CALCULATION_MESH, wireframe=True))

    if probes:
        # Stored vessel-local, so they need placing like the hull does.
        scene.append(_markers(transform_points(condition.probes, condition.transform), color=PROBE, radius=12))
    if application_point:
        scene.append(
            _markers(
                library.application_point_in_diffraction_space(condition),
                color=APPLICATION_POINT,
                radius=16,
            )
        )

    return show(
        *scene,
        title=f"{library.info.vessel_name} - {condition.id}",
        interactive=interactive,
        screenshot=screenshot,
    )
