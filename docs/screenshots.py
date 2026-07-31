"""Regenerate every screen grab in ``manual.md``.

    uv run python docs/screenshots.py

Builds a small library from ``tests/assets/tanker.stl`` in a temporary
directory, drives the window through it, and writes ``docs/images/*.png``. The
library is thrown away afterwards, so the manual's pictures are reproducible
rather than a set of files somebody once dragged in.

**This needs a real display.** Screen grabs are taken with
``QScreen.grabWindow`` rather than ``QWidget.grab``, because the 3D view is a
native VTK child window: Qt's own painting knows nothing about it and renders a
black rectangle where the hull should be. Grabbing the window off the screen is
the only way to capture both halves at once, and it means the window must be on
top and unobscured while this runs. Do not use the machine for the ~30 seconds
it takes.
"""

import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QDockWidget

from pylot_bem import Pylot, SolveSettings
from pylot_bem.app.dialogs import (
    CreateMeshDialog,
    DeleteFrequenciesDialog,
    NewConditionDialog,
    NewLibraryDialog,
    SolveDialog,
)
from pylot_bem.app.merge import MergeDialog
from pylot_bem.app.window import MainWindow

HULL = Path(__file__).parents[1] / "tests" / "assets" / "tanker.stl"
IMAGES = Path(__file__).parent / "images"

# Coarse on purpose. The pictures are of the interface, not of a study.
MESH = {"pct": 8.0, "iterations": 5}
PERIODS = [12.0, 16.0, 20.0]
DIRECTIONS = [0.0, 45.0, 90.0, 135.0, 180.0]
Z_ORIGINS = {"ballast": -5.0, "design": -12.0, "loaded": -18.0}


def build(path: Path) -> None:
    """A library with three drafts, and one deliberate conflict to show."""
    library = Pylot.create_new(
        path,
        HULL,
        "stern, centerline, keel",
        is_xz_symmetric=True,
        description="Demonstration library for the manual",
    )
    lo, hi = library.base_shape.bounds
    library.add_probe(x=0.5 * (lo[0] + hi[0]), y=0.0)

    settings = SolveSettings(
        omegas=tuple(2 * np.pi / period for period in PERIODS),
        wave_directions=tuple(DIRECTIONS),
        water_depth=np.inf,
        g=9.81,
    )
    for name, z_origin in Z_ORIGINS.items():
        library.create_condition(z_origin=z_origin, condition_id=name, label=name.title())
        library.create_mesh(name, **MESH, mesh_id=f"{name}-mesh")
        library.run_solve(f"{name}-mesh", settings, result_id=f"{name}-coarse", label=f"{name.title()} coarse")

    # A second, finer run over the same frequencies on the same condition. Two
    # results both supplying added mass at one frequency is a conflict, and the
    # Databases tab and the merge screen are both about looking at one.
    library.create_mesh("design", pct=5.0, iterations=5, mesh_id="design-mesh-fine")
    library.run_solve("design-mesh-fine", settings, result_id="design-fine", label="Design fine")
    library.close()


class Session:
    """One window, driven through the shots in order."""

    def __init__(self, app: QApplication, library: Path) -> None:
        self.app = app
        self.window = MainWindow()
        self.window.show()
        self.window.open_path(str(library))
        self.library = self.window.library

    def settle(self, times: int = 3) -> None:
        for _ in range(times):
            self.app.processEvents()
        self.window.viewport.render_window.Render()
        self.app.processEvents()

    def shoot(self, widget, name: str) -> None:
        self.settle()
        handle = widget.windowHandle()
        pixmap = handle.screen().grabWindow(widget.winId())
        target = IMAGES / f"{name}.png"
        if not pixmap.save(str(target)):
            raise SystemExit(f"could not write {target}")
        print(f"  {target.name}  {pixmap.width()}x{pixmap.height()}")

    def dialog(self, dialog, name: str) -> None:
        """Grab a dialog without running its event loop."""
        dialog.show()
        self.shoot(dialog, name)
        dialog.reject()
        self.app.processEvents()

    def run(self) -> None:
        window, library = self.window, self.library

        # -- the window, at each level of the tree -------------------------
        window.tree.select_ids([])
        window.viewport.reset_camera()
        self.shoot(window, "main-window")

        window.tree.select_ids(["design"])
        window.viewport.reset_camera()
        self.shoot(window, "condition")

        window.tree.select_ids(["design-mesh"])
        window.viewport.reset_camera()
        self.shoot(window, "mesh")

        window.tree.select_ids(["design-coarse"])
        self.shoot(window, "result")

        # -- the tabs ------------------------------------------------------
        #
        # The bottom dock opens at its minimum, which is enough for the tree
        # and the 3D view to have the room they need in normal use but shows
        # one row of a five-row table. For the tab pictures it is the table
        # that is the subject, so it gets the height.
        data = self.window.findChild(QDockWidget, "dockData")
        self.window.resize(1500, 1290)
        self.app.processEvents()
        self.window.resizeDocks([data], [560], Qt.Orientation.Vertical)
        self.app.processEvents()

        for index, name in enumerate(("results", "databases")):
            window.tabs.setCurrentIndex(index)
            self.shoot(window, f"tab-{name}")

        window.inspect_tab.show_results(library, ["design-coarse", "design-fine"])
        window.tabs.setCurrentWidget(window.inspect_tab)
        self.shoot(window, "tab-inspect")

        window.match_tab.display(library)
        window.match_tab.z_origin.setValue(-11.6)
        window.tabs.setCurrentWidget(window.match_tab)
        self.shoot(window, "tab-match")

        window.validation_tab.run()
        window.tabs.setCurrentWidget(window.validation_tab)
        self.shoot(window, "tab-validation")

        window.tabs.setCurrentIndex(0)
        self.window.resize(1500, 1000)
        self.window.resizeDocks([data], [300], Qt.Orientation.Vertical)
        self.app.processEvents()

        # -- the dialogs ---------------------------------------------------
        #
        # Filled in rather than blank. Half of what these screens are for is
        # the derived column beside the inputs -- the bounds under the chosen
        # unit, the panel count, the cost -- and an empty dialog shows none of
        # it.
        new_library = NewLibraryDialog(window)
        new_library.ui.editMeshFile.setText(str(HULL))
        new_library.ui.editMeshFile.editingFinished.emit()
        new_library.ui.editLibraryFile.setText(str(Path.home() / "tanker.pylot"))
        new_library.ui.editVesselName.setText("Tanker")
        new_library.ui.editOrigin.setText("stern, centerline, keel")
        new_library.ui.chkSymmetric.setChecked(True)
        self.dialog(new_library, "dlg-new-library")
        new_condition = NewConditionDialog(library, window)
        new_condition.ui.spinZOrigin.setValue(-8.5)
        new_condition.ui.editLabel.setText("Part loaded")
        new_condition.ui.editId.setText("part-loaded")
        self.dialog(new_condition, "dlg-new-condition")
        self.dialog(CreateMeshDialog(library, library.condition("design"), window), "dlg-create-mesh")
        self.dialog(SolveDialog(library, library.mesh("design-mesh"), window), "dlg-solve")
        self.dialog(
            DeleteFrequenciesDialog(library, library.result("design-coarse"), window),
            "dlg-trim-frequencies",
        )
        self.dialog(
            MergeDialog(library, [library.result("design-coarse"), library.result("design-fine")], window),
            "dlg-merge",
        )


def main() -> int:
    IMAGES.mkdir(exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="pylot-manual-"))
    try:
        path = workspace / "demonstration.pylot"
        print("building the demonstration library...")
        build(path)

        app = QApplication.instance() or QApplication(sys.argv)
        session = Session(app, path)

        # The window needs to be up, mapped and painted before anything is
        # grabbed off the screen; the first frame of a VTK window is not ready
        # the instant show() returns.
        def go():
            try:
                session.run()
            finally:
                session.window.close()
                app.quit()

        QTimer.singleShot(1500, go)
        app.exec()
        print(f"written to {IMAGES}")
        return 0
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
