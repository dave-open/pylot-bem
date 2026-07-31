"""The 3D view: a hull sitting in the water.

Everything is drawn in **diffraction space**, which is the only frame where the
waterplane is ``z = 0`` and a hull's position in it *is* the floating condition
(pylot-db's spec 01). The base shape is stored vessel-local, so it is placed through
:meth:`~pylot_bem.api.Pylot.base_shape_at` first; a calculation mesh is already
in diffraction space and is drawn as it is stored.

This is the Qt half of what :mod:`pylot_bem.plotting` does for scripts. The two
share :func:`~pylot_bem.plotting.to_polydata` and the palette and nothing else:
a script wants a window and a blocking event loop, a panel wants neither. VTK
is reached through ``vtkmodules.*`` and never the top-level ``vtk`` shim
(spec 07 section 3.2) -- the shim eagerly imports every module and breaks when
another distribution supplies its own build, which ``pymeshup`` does.

**Backface colouring is always on** (spec 09 section L). An inverted normal is
a real failure and completely invisible on a shaded surface; a differently
coloured backface makes it obvious at a glance, and it costs nothing, where a
toggle would be off exactly when it was needed.
"""

import numpy as np

# Imported for its side effect as well as its contents: it registers object
# factory overrides, and without them ``vtkRenderWindow`` stays the **abstract
# base class**. A scene built on one accepts every actor, reports no error, and
# draws nothing -- which is indistinguishable from an empty library, and was
# the state this module shipped in until a test asked what class it had.
import vtkmodules.vtkRenderingOpenGL2
from pylot_db.frames import transform_points
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QVBoxLayout, QWidget
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import vtkPolyData
from vtkmodules.vtkFiltersSources import vtkPlaneSource, vtkSphereSource
from vtkmodules.vtkInteractionStyle import vtkInteractorStyleTrackballCamera
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkGlyph3DMapper,
    vtkPolyDataMapper,
    vtkProperty,
    vtkRenderer,
)

from pylot_bem.palette import APPLICATION_POINT, BACKFACE, CALCULATION_MESH, HULL, PROBE, SEA
from pylot_bem.polydata import to_polydata

__all__ = ["LAYERS", "Viewport"]

# The five things that can be shown, in the order they are listed in the View
# menu. A lid is deliberately absent: it is a solver setting regenerated per
# solve and never stored (spec 04 section 2), so outside a running solve there
# is nothing to draw.
LAYERS = ("base", "mesh", "waterplane", "probes", "application_point")

# Qt platform plugins that give a widget no native window. VTK's Win32 render
# window asks that window for a pixel format, gets none, and **crashes the
# process with an access violation** -- not an exception, so there is nothing
# to catch and nothing in the traceback. The only defence is not to initialise.
#
# Not a hypothetical: the test suite runs on `offscreen`, and so does any
# machine where QT_QPA_PLATFORM is set for a headless run. The scene can still
# be built and inspected there; only the drawing is unavailable.
BLIND_PLATFORMS = ("offscreen", "minimal", "vnc")

# Marker size as a fraction of the hull's diagonal, so the same code works for
# a 60 m box and a 330 m tanker.
PROBE_FRACTION = 0.006
APPLICATION_POINT_FRACTION = 0.010


def _colour(hex_string: str) -> tuple[float, float, float]:
    """``#rrggbb`` as the 0..1 triple VTK wants."""
    value = hex_string.lstrip("#")
    return tuple(int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))


def _mesh_actor(mesh, *, colour: str, opacity: float = 1.0, wireframe: bool = False) -> vtkActor:
    mapper = vtkPolyDataMapper()
    mapper.SetInputData(to_polydata(mesh))
    if wireframe:
        # The calculation mesh is a regrid of the hull's wetted surface, so it
        # sits exactly on it. Without an offset the two z-fight and the
        # wireframe dissolves into a dotted mess at every camera angle.
        mapper.SetResolveCoincidentTopologyToPolygonOffset()
        mapper.SetRelativeCoincidentTopologyLineOffsetParameters(0.0, -8.0)

    actor = vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(*_colour(colour))
    actor.GetProperty().SetOpacity(opacity)
    if wireframe:
        actor.GetProperty().SetRepresentationToWireframe()
        actor.GetProperty().SetLineWidth(1.0)
    else:
        # Some ambient light, so a surface turned away from the camera is still
        # recognisably the palette colour rather than near-black. A hull is
        # mostly curved away from wherever you are looking at it from.
        actor.GetProperty().SetAmbient(0.30)
        actor.GetProperty().SetDiffuse(0.75)
        back = vtkProperty()
        back.SetColor(*_colour(BACKFACE))
        back.SetAmbient(0.30)
        back.SetDiffuse(0.75)
        actor.SetBackfaceProperty(back)
    return actor


def _points_actor(points, *, colour: str, radius: float) -> vtkActor:
    """Spheres at a set of points, as one actor.

    Glyphed rather than one actor per point: the probe count is a user setting
    and a library with fifty of them should not cost fifty actors.
    """
    points = np.atleast_2d(np.asarray(points, dtype=float))

    vtk_points = vtkPoints()
    for point in points:
        vtk_points.InsertNextPoint(*point[:3])
    polydata = vtkPolyData()
    polydata.SetPoints(vtk_points)

    sphere = vtkSphereSource()
    sphere.SetRadius(radius)
    sphere.SetThetaResolution(16)
    sphere.SetPhiResolution(16)

    mapper = vtkGlyph3DMapper()
    mapper.SetInputData(polydata)
    mapper.SetSourceConnection(sphere.GetOutputPort())

    actor = vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(*_colour(colour))
    return actor


def _waterplane_actor(vertices, *, margin: float = 0.15) -> vtkActor:
    """A translucent plane at ``z = 0``, sized per axis.

    Per axis and not square, for the same reason
    :func:`pylot_bem.plotting.waterplane` is: a hull is long and narrow, and a
    plane sized to its length would put the horizon 190 m off a 29 m half-beam.
    """
    vertices = np.asarray(vertices, dtype=float)
    lo, hi = vertices.min(axis=0), vertices.max(axis=0)
    centre = (lo + hi) / 2
    half = (hi[:2] - lo[:2]) * (1.0 + margin) / 2

    plane = vtkPlaneSource()
    plane.SetOrigin(centre[0] - half[0], centre[1] - half[1], 0.0)
    plane.SetPoint1(centre[0] + half[0], centre[1] - half[1], 0.0)
    plane.SetPoint2(centre[0] - half[0], centre[1] + half[1], 0.0)

    mapper = vtkPolyDataMapper()
    mapper.SetInputConnection(plane.GetOutputPort())

    actor = vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(*_colour(SEA))
    actor.GetProperty().SetOpacity(0.25)
    return actor


class Viewport(QWidget):
    """The 3D panel.

    One scene at a time, rebuilt whenever the selection changes. Layers are
    kept as named actors so a visibility toggle does not need the scene rebuilt
    -- and so the View menu and the scene cannot disagree about what is shown.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._renderer = vtkRenderer()
        self._renderer.SetBackground(*_colour("#cdd8e6"))

        self._interactor = QVTKRenderWindowInteractor(self)
        render_window = self._interactor.GetRenderWindow()
        render_window.AddRenderer(self._renderer)

        # Correct translucency, and it is not cosmetic. The hull is drawn
        # see-through so the calculation mesh inside it is visible, and without
        # depth peeling VTK draws translucent faces in arbitrary order: the far
        # side of the hull paints over the near side, so the whole vessel comes
        # out in the **backface** colour. Backface colouring then says nothing
        # -- an inverted normal looks exactly like every other face, which is
        # the one thing spec 09 section L exists to prevent.
        #
        # Depth peeling needs alpha planes and no multisampling; that trade
        # gives up edge antialiasing for a picture that is telling the truth.
        render_window.SetAlphaBitPlanes(1)
        render_window.SetMultiSamples(0)
        self._renderer.SetUseDepthPeeling(True)
        self._renderer.SetMaximumNumberOfPeels(8)
        self._renderer.SetOcclusionRatio(0.05)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._interactor)

        self._actors: dict[str, vtkActor] = {}
        self._visible = dict.fromkeys(LAYERS, True)
        self._started = False
        self.unavailable = ""

    @property
    def render_window(self):
        """The VTK render window. Public so its class can be asserted on."""
        return self._interactor.GetRenderWindow()

    def start(self) -> None:
        """Begin interaction. Must run after the widget has been shown.

        The interactor style is set **explicitly**, and both halves of that
        matter. VTK's own default is ``vtkInteractorStyleSwitch`` delegating to
        ``vtkInteractorStyleJoystickCamera``: the camera keeps moving while a
        button is held, at a rate set by how far the cursor sits from centre,
        which is not how anything else made this century behaves. Trackball is
        the one where the model follows the cursor and stops when you do.

        And ``Switch`` reads the keyboard -- ``j``/``t`` for joystick and
        trackball, ``c``/``a`` for camera and **actor**. Actor mode lets the
        user drag the geometry around the scene, and in this viewport the
        geometry's position *is* the floating condition: everything is drawn in
        diffraction space, where ``z = 0`` is the waterplane. Dragging the hull
        off the water would leave a picture that quietly disagrees with the
        condition it claims to show. ``TrackballCamera`` moves the camera and
        nothing else, so that is unreachable rather than merely discouraged.

        Declines on a platform that cannot give the widget a native window,
        because there the alternative is not a blank panel but a dead process
        (see :data:`BLIND_PLATFORMS`). Everything else about the viewport keeps
        working: the scene is built, layers toggle, the camera moves. Only the
        pixels are missing, and :attr:`unavailable` says why.
        """
        if self._started or self.unavailable:
            return
        platform = QGuiApplication.platformName()
        if platform in BLIND_PLATFORMS:
            self.unavailable = (
                f"the Qt platform is {platform!r}, which gives no native window for OpenGL, "
                "so the 3D view cannot be drawn"
            )
            return
        self._interactor.SetInteractorStyle(vtkInteractorStyleTrackballCamera())
        self._interactor.Initialize()
        self._started = True

    def shutdown(self) -> None:
        """Release the render window.

        Called when the application closes: a VTK interactor outliving its Qt
        widget is a segfault on exit rather than a leak, and it happens after
        everything useful has been logged.
        """
        self._interactor.close()

    # -- scene -------------------------------------------------------------

    def clear(self) -> None:
        for actor in self._actors.values():
            self._renderer.RemoveActor(actor)
        self._actors.clear()
        self._render()

    def show_condition(self, library, condition, mesh=None) -> None:
        """Draw a floating condition, optionally with one of its meshes.

        Args:
            library: An open :class:`~pylot_bem.api.Pylot`.
            condition: The condition, or its id.
            mesh: A calculation mesh, or its id, or ``None`` for none. Not
                defaulted to the condition's first: which mesh is shown follows
                the tree selection, and guessing here would make the two
                disagree.
        """
        self.clear()
        condition = library.condition(condition)
        placed = library.base_shape_at(condition)
        diagonal = float(np.linalg.norm(placed.vertices.max(axis=0) - placed.vertices.min(axis=0)))

        self._actors["waterplane"] = _waterplane_actor(placed.vertices)
        # Opaque, and that is the whole point of backface colouring. Through a
        # see-through hull you are always looking at the inside of its far
        # side, so every face reads as a backface and an inverted normal --
        # the one thing the colour exists to reveal -- becomes invisible again.
        # To look inside, switch the base shape off in the View menu; the
        # calculation mesh is drawn over it in wireframe either way.
        self._actors["base"] = _mesh_actor(placed, colour=HULL)
        if mesh is not None:
            self._actors["mesh"] = _mesh_actor(library.mesh(mesh), colour=CALCULATION_MESH, wireframe=True)
        self._actors["probes"] = _points_actor(
            transform_points(condition.probes, condition.transform),
            colour=PROBE,
            radius=diagonal * PROBE_FRACTION,
        )
        self._actors["application_point"] = _points_actor(
            library.application_point_in_diffraction_space(condition),
            colour=APPLICATION_POINT,
            radius=diagonal * APPLICATION_POINT_FRACTION,
        )

        for name, actor in self._actors.items():
            actor.SetVisibility(self._visible[name])
            self._renderer.AddActor(actor)
        self.reset_camera()

    def show_geometry(self, mesh, *, colour: str = HULL) -> None:
        """Draw one arbitrary mesh and nothing else.

        For the import preview, where there is no condition yet -- the geometry
        is vessel-local and no waterplane would mean anything.
        """
        self.clear()
        self._actors["base"] = _mesh_actor(mesh, colour=colour)
        self._actors["base"].SetVisibility(self._visible["base"])
        self._renderer.AddActor(self._actors["base"])
        self.reset_camera()

    # -- layers and camera -------------------------------------------------

    def layer_visible(self, name: str) -> bool:
        return self._visible[name]

    def set_layer_visible(self, name: str, visible: bool) -> None:
        self._visible[name] = visible
        actor = self._actors.get(name)
        if actor is not None:
            actor.SetVisibility(visible)
        self._render()

    def reset_camera(self) -> None:
        """Frame the scene from three-quarters, slightly above the waterplane.

        The same angle :func:`pylot_bem.plotting.show` picks, and for the same
        reason: VTK's own reset gives a plan view, where a hull is a silhouette
        and its draft -- the thing a floating condition *is* -- is invisible.

        **The camera is oriented before the reset, not after.** VTK's default
        camera looks along -z, so setting the view up to +z afterwards makes it
        parallel to the view direction; ``OrthogonalizeViewUp`` then has nothing
        to project and leaves ``(0, 0, 0)``. A zero view up renders an empty
        window -- no warning, no error, five actors present and correct.
        ``ResetCamera`` preserves the direction and up vector it is given and
        only slides the camera along that axis to fit, so doing it in this order
        is both correct and simpler.
        """
        camera = self._renderer.GetActiveCamera()
        # Looking from -y towards +y with z up: a starboard elevation, which is
        # the view where a waterline reads as a waterline.
        camera.SetFocalPoint(0.0, 0.0, 0.0)
        camera.SetPosition(0.0, -1.0, 0.0)
        camera.SetViewUp(0.0, 0.0, 1.0)

        self._renderer.ResetCamera()
        camera.Azimuth(-50.0)
        camera.Elevation(20.0)
        camera.OrthogonalizeViewUp()
        self._renderer.ResetCameraClippingRange()
        self._render()

    def _render(self) -> None:
        if self._started:
            self._interactor.GetRenderWindow().Render()
