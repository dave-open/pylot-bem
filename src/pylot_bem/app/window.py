"""The main window.

Built in code rather than from a ``.ui`` file, unlike the property panes and
the dialogs. The shell is three docks and a tab bar and has no design in it;
the panes are where the design lives, which is why those are the ones that come
out of Qt Designer.

The shape of the window follows from ADR-9 and spec 06 section 4. This is not a
wizard that walks a user from base shape to database once. It is an
**explore → compare → prune** loop: solve a variant, look at it, solve another,
decide which to keep, delete the rest. So:

- the tree holds work in progress, competing results included;
- the Results tab is never filtered by the tree selection;
- every deletion shows its blast radius first;
- nothing resolves a conflict automatically, ever.

There is no toolbar. Every action lives on the thing it acts on -- in the tree's
context menu and on the property pane -- which is what stops a button being
enabled for a selection it makes no sense for.
"""

from pathlib import Path

import numpy as np
from pylot_db.probes import probes_for_condition
from pylot_db.storage import LibraryError
from PySide6.QtCore import QLocale, QSettings, Qt
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QDockWidget,
    QFileDialog,
    QMainWindow,
    QMenu,
    QMessageBox,
    QStackedWidget,
    QTabWidget,
    QWidget,
)

from pylot_bem.api import Pylot
from pylot_bem.app.dialogs import (
    CreateMeshDialog,
    DeleteFrequenciesDialog,
    NewConditionDialog,
    NewLibraryDialog,
    SolveDialog,
)
from pylot_bem.app.formatting import escape, period_from_omega
from pylot_bem.app.properties import ConditionPane, LibraryPane, MeshPane, ResultPane, SelectionPane
from pylot_bem.app.tabs import DatabasesTab, InspectTab, MatchTab, ResultsTab, ValidationTab
from pylot_bem.app.tree import LibraryTree
from pylot_bem.app.viewport import LAYERS, Viewport
from pylot_bem.mesh_pipeline import MeshPipelineError

__all__ = ["MainWindow"]

LAYER_LABELS = {
    "base": "Base shape",
    "mesh": "Calculation mesh",
    "waterplane": "Waterplane",
    "probes": "Surface probes",
    "application_point": "Application point",
}

CONVENTIONS = """<h3>Conventions</h3>
<p><b>Lengths are metres, everywhere.</b> The only unit conversion in this
application is at base-shape import.</p>
<p><b>z_origin is not the draft.</b> It is the height of the vessel origin above
the waterplane, negative for a normally floating vessel. The two differ by
wherever the origin was put on the hull — which is what
<i>origin sits at</i> records.</p>
<p><b>Heel and trim are shown in degrees</b> and stored as slopes. Slopes are
never shown here, not even as a secondary readout.</p>
<p><b>Positive heel puts starboard down; positive trim puts the bow down.</b>
Both are a positive rotation about their own axis by the right-hand rule. The
frame is right-handed with z up and x forward, so +y points to port.</p>
<p><b>Frequencies are entered as periods in seconds</b> and stored as omega.
Ascending period is descending omega, so a grid solves in the reverse of the
order it is typed.</p>
<p><b>Wave direction is the direction of travel</b> — where the wave is going,
not where it comes from.</p>
<p><b>There is no density in a result.</b> Every solve runs at 1 t/m³ and the
density is applied when a database is delivered, so one library serves salt
water, fresh water and anything else. Density appears only in Inspect and
Match, and it is never a filter.</p>
"""


class MainWindow(QMainWindow):
    """The application.

    Opens with no library: everything below is disabled and says so, rather
    than showing an empty tree that looks like a library with nothing in it.
    """

    #: File → Recent Files, most recent first. Beyond this many, the oldest
    #: drops off -- unbounded growth would make the menu itself the thing that
    #: needs scrolling to find a recent file in.
    MAX_RECENT_FILES = 10

    def __init__(self, parent: QWidget | None = None, *, settings: QSettings | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("pylot")
        # All numeric controls use US locale (decimal dot) regardless of system
        # locale. Children inherit this, so it applies to spinboxes everywhere.
        self.setLocale(QLocale.c())
        self.resize(1500, 950)

        # Recent Files is stored here, not on self. A caller may substitute an
        # isolated QSettings -- the test suite does, backed by a private file
        # -- so opening libraries in a test run never touches a developer's
        # real registry entries for this application.
        self._settings = settings if settings is not None else QSettings("dave-open", "pylot")

        self.library: Pylot | None = None

        # Kept because a dock has a close button and nothing else offers one a
        # way back: closing Properties or Data hid it for the life of the
        # process. View -> Panels holds their toggles.
        self.docks: dict[str, QDockWidget] = {}

        self.viewport = Viewport(self)
        self.setCentralWidget(self.viewport)

        self.tree = LibraryTree(self)
        # Wide enough for a name at three levels of indent *and* the three
        # numeric columns. Narrower and the heel and trim columns are the first
        # thing squeezed out, which is where the only reason to have them as
        # columns rather than as text quietly disappears.
        self._dock("Library", self.tree, Qt.DockWidgetArea.LeftDockWidgetArea, 420)

        self.panes = QStackedWidget(self)
        self.library_pane = LibraryPane()
        self.condition_pane = ConditionPane()
        self.mesh_pane = MeshPane()
        self.result_pane = ResultPane()
        self.selection_pane = SelectionPane()
        for pane in (
            self.selection_pane,
            self.library_pane,
            self.condition_pane,
            self.mesh_pane,
            self.result_pane,
        ):
            self.panes.addWidget(pane)
        self.selection_pane.show_nothing()
        self._dock("Properties", self.panes, Qt.DockWidgetArea.RightDockWidgetArea, 340)

        self.tabs = QTabWidget(self)
        self.results_tab = ResultsTab()
        self.databases_tab = DatabasesTab()
        self.inspect_tab = InspectTab()
        self.match_tab = MatchTab()
        self.validation_tab = ValidationTab()
        for widget, title in (
            (self.results_tab, "Results"),
            (self.databases_tab, "Databases"),
            (self.inspect_tab, "Inspect"),
            (self.match_tab, "Match"),
            (self.validation_tab, "Validation"),
        ):
            self.tabs.addTab(widget, title)
        self._dock("Data", self.tabs, Qt.DockWidgetArea.BottomDockWidgetArea, 300)

        self._build_menus()
        self._connect()
        self.statusBar().showMessage("No library open. File → New library, or Open library.")
        self._set_enabled(False)

    def _dock(self, title: str, widget: QWidget, area, size: int) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(f"dock{title}")
        dock.setWidget(widget)
        self.addDockWidget(area, dock)
        if area in (Qt.DockWidgetArea.LeftDockWidgetArea, Qt.DockWidgetArea.RightDockWidgetArea):
            dock.setMinimumWidth(size)
        else:
            dock.setMinimumHeight(size)
        self.docks[title] = dock
        return dock

    # -- menus -------------------------------------------------------------

    def _build_menus(self) -> None:
        """Build the menu bar.

        Every menu is kept on ``self.menus``. ``addMenu(title)`` hands back a
        ``QMenu`` that Python owns, so one referenced only by a local in this
        method is destroyed the moment the method returns -- the entries stay
        drawn on the bar and still work, because Qt keeps them, but the
        ``QMenu`` a caller gets back from ``action.menu()`` is a wrapper around
        a deleted object. That is invisible in use and makes the menu bar
        untestable, which is how a submenu could have gone missing without
        anything noticing.
        """
        self.menus: dict[str, QMenu] = {}

        file_menu = self.menus["File"] = self.menuBar().addMenu("&File")
        file_menu.addAction("&New library…", self.new_library)
        file_menu.addAction("&Open library…", self.open_library)
        self.recent_menu = self.menus["Recent Files"] = file_menu.addMenu("Recent Files")
        self._rebuild_recent_files_menu()
        self.close_action = file_menu.addAction("&Close library", self.close_library)
        file_menu.addSeparator()
        file_menu.addAction("E&xit", self.close)

        view_menu = self.menus["View"] = self.menuBar().addMenu("&View")

        # Qt gives every dock a close button and no way back. Its own
        # toggleViewAction is the way back: already checkable, already named
        # after the dock, and already tracking whether the dock is visible --
        # so it cannot fall out of step with what is on screen the way a
        # hand-written checkable action would.
        panels = self.menus["Panels"] = view_menu.addMenu("Panels")
        for dock in self.docks.values():
            panels.addAction(dock.toggleViewAction())
        view_menu.addSeparator()

        self.layer_actions: dict[str, QAction] = {}
        for name in LAYERS:
            action = QAction(LAYER_LABELS[name], self, checkable=True, checked=True)
            action.toggled.connect(lambda on, layer=name: self.viewport.set_layer_visible(layer, on))
            view_menu.addAction(action)
            self.layer_actions[name] = action
        lid = QAction("Lid mesh", self, checkable=True, checked=False)
        lid.setEnabled(False)
        lid.setToolTip("A lid is a solver setting regenerated per solve and never stored, so there is none to draw")
        view_menu.addAction(lid)
        view_menu.addSeparator()
        view_menu.addAction("Reset camera", self.viewport.reset_camera)
        view_menu.addSeparator()

        theme_menu = self.menus["Theme"] = view_menu.addMenu("Theme")
        self.theme_group = QActionGroup(self)
        for label in ("System", "Fusion light", "Fusion dark"):
            action = QAction(label, self, checkable=True, checked=label == "System")
            action.triggered.connect(lambda _checked, name=label: self.set_theme(name))
            self.theme_group.addAction(action)
            theme_menu.addAction(action)

        help_menu = self.menus["Help"] = self.menuBar().addMenu("&Help")
        help_menu.addAction("Conventions — units and frames", self.show_conventions)
        help_menu.addAction("About pylot", self.show_about)

    def _connect(self) -> None:
        self.tree.selectionSummary.connect(self._selection_changed)
        self.tree.newConditionRequested.connect(self.new_condition)
        self.tree.batchRequested.connect(self.run_batch)
        self.tree.createMeshRequested.connect(self.create_mesh)
        self.tree.solveRequested.connect(self.solve_mesh)
        self.tree.inspectRequested.connect(self.inspect)
        self.tree.mergeRequested.connect(self.merge_results)
        self.tree.deleteFrequenciesRequested.connect(self.delete_frequencies)
        self.tree.removeRequested.connect(self.remove)
        self.tree.validateRequested.connect(self.validate)

        self.library_pane.identityEdited.connect(self.edit_identity)
        self.library_pane.probesEdited.connect(self.edit_probes)
        self.library_pane.validateRequested.connect(self.validate)

        self.condition_pane.labelEdited.connect(self.edit_condition_label)
        self.condition_pane.createMeshRequested.connect(lambda: self.create_mesh(self._current_id()))
        self.condition_pane.removeRequested.connect(lambda: self.remove("condition", self._current_id()))

        self.mesh_pane.solveRequested.connect(lambda: self.solve_mesh(self._current_id()))
        self.mesh_pane.removeRequested.connect(lambda: self.remove("mesh", self._current_id()))
        self.mesh_pane.resultActivated.connect(lambda result_id: self.tree.select_ids([result_id]))

        self.result_pane.labelEdited.connect(self.rename_result)
        self.result_pane.inspectRequested.connect(lambda: self.inspect([self._current_id()]))
        self.result_pane.deleteFrequenciesRequested.connect(lambda: self.delete_frequencies(self._current_id()))
        self.result_pane.removeRequested.connect(lambda: self.remove("result", self._current_id()))

        self.selection_pane.compareRequested.connect(lambda: self.inspect(self.tree.selected_ids()))
        self.selection_pane.mergeRequested.connect(lambda: self.merge_results(self.tree.selected_ids()))
        self.selection_pane.removeRequested.connect(self.remove_selected)

        self.databases_tab.inspectRequested.connect(self.inspect)
        self.validation_tab.ran.connect(self.library_pane.show_findings)

    # -- library lifecycle -------------------------------------------------

    def new_library(self) -> None:
        dialog = NewLibraryDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        try:
            library = Pylot.create_new(**values)
        except (LibraryError, MeshPipelineError, OSError) as exc:
            self._problem("Could not create the library", exc)
            return
        self._adopt(library)

    def open_library(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open library", "", "pylot library (*.pylot);;All files (*)")
        if path:
            self.open_path(path)

    def open_path(self, path) -> None:
        """Open a library file, reporting a refusal rather than raising.

        A library that cannot be opened at all -- wrong schema version, not a
        database -- is a message. A library that opens and is *inconsistent*
        goes to the Validation tab, which is a different problem with a
        different remedy.
        """
        try:
            library = Pylot.open(path)
        except (LibraryError, OSError) as exc:
            self._problem("Could not open the library", exc)
            # A moved or deleted file left permanently in Recent Files is a
            # menu entry that can never work again. A library that opened
            # fine last time but is inconsistent now, or that this schema
            # version refuses, is a different problem -- still the user's
            # file, still worth being able to get back to -- so only a
            # genuinely missing path is dropped.
            if not Path(path).exists():
                self._forget_recent_file(path)
            return
        self._adopt(library)

    def close_library(self) -> None:
        if self.library is not None:
            self.library.close()
        self.library = None
        self.tree.rebuild(None)
        self.viewport.clear()
        self.selection_pane.show_nothing()
        self.panes.setCurrentWidget(self.selection_pane)
        self._set_enabled(False)
        self.setWindowTitle("pylot")
        self.statusBar().showMessage("No library open.")

    def _adopt(self, library: Pylot) -> None:
        if self.library is not None:
            self.library.close()
        self.library = library
        self._set_enabled(True)
        self.setWindowTitle(f"pylot — {library.path}")
        self._remember_recent_file(library.path)
        self.refresh()
        self.tree.select_ids(["library"])

    # -- recent files --------------------------------------------------------

    def _recent_files(self) -> list[str]:
        stored = self._settings.value("recentFiles", [])
        # QSettings' ini backend collapses a one-element list back to a bare
        # string on read -- there is no way to tell "one path" from "one
        # character of a path" apart afterwards except by knowing this.
        if isinstance(stored, str):
            stored = [stored] if stored else []
        return [str(path) for path in stored]

    def _remember_recent_file(self, path) -> None:
        path = str(path)
        paths = [p for p in self._recent_files() if p != path]
        paths.insert(0, path)
        del paths[self.MAX_RECENT_FILES :]
        self._settings.setValue("recentFiles", paths)
        self._rebuild_recent_files_menu()

    def _forget_recent_file(self, path) -> None:
        path = str(path)
        paths = [p for p in self._recent_files() if p != path]
        self._settings.setValue("recentFiles", paths)
        self._rebuild_recent_files_menu()

    def _clear_recent_files(self) -> None:
        self._settings.setValue("recentFiles", [])
        self._rebuild_recent_files_menu()

    def _rebuild_recent_files_menu(self) -> None:
        """Redraw Recent Files from what :class:`QSettings` actually holds.

        Rebuilt wholesale rather than patched incrementally, for the same
        reason :meth:`refresh` rebuilds the tree wholesale: the underlying
        list changes from three different places -- opening a file, a missing
        one dropping out, Clear -- and a menu kept correct through all three
        by hand would be three places to get right instead of one.
        """
        self.recent_menu.clear()
        recent = self._recent_files()
        if not recent:
            placeholder = self.recent_menu.addAction("No recent files")
            placeholder.setEnabled(False)
            return
        for path in recent:
            self.recent_menu.addAction(path, lambda checked=False, p=path: self.open_path(p))
        self.recent_menu.addSeparator()
        self.recent_menu.addAction("Clear recent files", self._clear_recent_files)

    def _set_enabled(self, on: bool) -> None:
        self.tabs.setEnabled(on)
        self.panes.setEnabled(on)
        self.tree.setEnabled(on)
        self.close_action.setEnabled(on)

    def refresh(self, *, keep: list[str] | None = None) -> None:
        """Re-read everything from the library.

        Wholesale, for the same reason the tree rebuilds wholesale: any action
        can change any view -- storing a result changes a database's state,
        which changes a dot in the tree and a row in two tabs -- and a partial
        refresh would be a list of couplings to keep up to date.

        **Each view is refreshed independently, and one that throws does not
        stop the others.** Spec 06 section 7 requires a deliberately corrupted
        library to be *displayed*, not crashed on, and a library corrupt enough
        to break one view is exactly the one whose remaining views a user needs:
        a base shape that will not decode leaves the results table and the
        findings perfectly readable, and those are what say what happened.
        """
        if self.library is None:
            return

        broken = []
        for name, refreshing in (
            ("tree", lambda: self.tree.rebuild(self.library, keep=keep)),
            ("results", lambda: self.results_tab.display(self.library)),
            ("databases", lambda: self.databases_tab.display(self.library)),
            ("match", lambda: self.match_tab.display(self.library)),
            ("validation", lambda: self.validation_tab.display(self.library)),
            ("properties", lambda: self.library_pane.display(self.library)),
            ("summary", self._show_counts),
        ):
            try:
                refreshing()
            except Exception as exc:
                broken.append(f"{name} ({type(exc).__name__}: {exc})")

        if broken:
            self.statusBar().showMessage(f"This library is damaged. Could not show: {'; '.join(broken)}")
            self.tabs.setCurrentWidget(self.validation_tab)
            self.validation_tab.run()

    def _show_counts(self) -> None:
        library = self.library
        base = library.base_shape
        lo, hi = base.bounds
        self.statusBar().showMessage(
            f"{len(library.conditions())} conditions · {len(library.meshes())} meshes · "
            f"{len(library.results())} results   |   base shape {len(base.vertices)} vertices, "
            f"{len(base.faces)} faces, {hi[0] - lo[0]:.1f} × {hi[1] - lo[1]:.1f} × {hi[2] - lo[2]:.1f} m   |   "
            f"{'declared XZ-symmetric' if base.is_xz_symmetric else 'not symmetric'}"
        )

    # -- selection ---------------------------------------------------------

    def _current_id(self) -> str:
        ids = self.tree.selected_ids()
        return ids[0] if ids else ""

    def _selection_changed(self, kind: str, ids: list[str]) -> None:
        if self.library is None:
            return
        if kind == "library":
            self.library_pane.display(self.library)
            self.panes.setCurrentWidget(self.library_pane)
            # The base shape, vessel-local and with no waterplane -- there is no
            # condition at this level, so there is no water. Backface colouring
            # still applies, which makes the root the natural place to check the
            # hull's normals before anything is built on it.
            self.viewport.show_geometry(self.library.base_shape)
        elif kind == "condition":
            condition = self.library.condition(ids[0])
            self.condition_pane.display(self.library, condition)
            self.panes.setCurrentWidget(self.condition_pane)
            self.viewport.show_condition(self.library, condition)
        elif kind == "mesh":
            mesh = self.library.mesh(ids[0])
            self.mesh_pane.display(self.library, mesh)
            self.panes.setCurrentWidget(self.mesh_pane)
            self.viewport.show_condition(self.library, mesh.condition_id, mesh=mesh)
        elif kind == "result":
            result = self.library.result(ids[0])
            self.result_pane.display(self.library, result)
            self.panes.setCurrentWidget(self.result_pane)
            self.viewport.show_condition(self.library, result.condition_id, mesh=result.mesh_id)
            self.inspect_tab.show_results(self.library, ids)
        elif kind == "results":
            self.selection_pane.display(self.library, [self.library.result(i) for i in ids])
            self.panes.setCurrentWidget(self.selection_pane)
            self.inspect_tab.show_results(self.library, ids)
        else:
            self.selection_pane.show_nothing()
            self.panes.setCurrentWidget(self.selection_pane)

    # -- actions -----------------------------------------------------------

    def edit_identity(self, vessel_name: str, description: str, origin: str) -> None:
        try:
            self.library.set_info(
                vessel_name=vessel_name, description=description, origin_description=origin
            )
        except LibraryError as exc:
            self._problem("Could not apply", exc)
            return
        self.refresh()

    def edit_probes(self, values) -> None:
        """Apply a probe edit, after saying what it will change.

        Spec 06 section 3 requires the recomputation to be announced and the
        count of affected conditions reported. Computed with the same function
        storage would use, before anything is written -- a preview derived some
        other way could disagree with what then happens.
        """
        probe_xy = np.asarray(values, dtype=float).reshape(-1, 2)
        if len(probe_xy) == 0:
            self._problem("Could not apply", ValueError("a library must keep at least one probe"))
            return

        conditions = self.library.conditions()
        changed = sum(
            1
            for condition in conditions
            if not np.array_equal(probes_for_condition(condition.transform, probe_xy), condition.probes)
        )
        answer = QMessageBox.question(
            self,
            "Recompute every condition?",
            f"Applying {len(probe_xy)} probes recomputes the probe positions of all "
            f"{len(conditions)} conditions; {changed} would change.\n\n"
            "Probes are what matching ranks conditions by, so this changes how every future "
            "match scores. Nothing else is affected.",
            QMessageBox.StandardButton.Apply | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Apply:
            return
        self.library.set_probe_xy(probe_xy)
        self.refresh()
        self.statusBar().showMessage(f"Probes applied; {changed} of {len(conditions)} conditions changed.")

    def edit_condition_label(self, label: str) -> None:
        """Rename a condition.

        The only part of one that can change. ``z_origin``, heel and trim are
        what every mesh and result below were computed against, so editing them
        would invalidate that work rather than update it -- which is why they
        are shown as derived text and there is no widget for them. A label is
        human display only and nothing parses it, so it carries no such risk.
        """
        condition_id = self._current_id()
        if not condition_id:
            return
        self.library.set_condition_label(condition_id, label)
        self.refresh(keep=[condition_id])
        self.statusBar().showMessage(f"Renamed {condition_id}.")

    def rename_result(self, label: str) -> None:
        """Rename a result. Its only mutable field, for the same reason a
        condition's label is: nothing parses it, so nothing can break.
        """
        result_id = self._current_id()
        if not result_id:
            return
        self.library.set_result_label(result_id, label)
        self.refresh(keep=[result_id])
        self.statusBar().showMessage(f"Renamed {result_id}.")

    def new_condition(self) -> None:
        dialog = NewConditionDialog(self.library, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            condition = self.library.create_condition(**dialog.values())
        except (LibraryError, MeshPipelineError, ValueError) as exc:
            self._problem("Could not create the condition", exc)
            return
        self.refresh(keep=[condition.id])

    def create_mesh(self, condition_id: str) -> None:
        if not condition_id:
            return
        condition = self.library.condition(condition_id)
        dialog = CreateMeshDialog(self.library, condition, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            mesh = self.library.create_mesh(condition, **dialog.values())
        except (LibraryError, MeshPipelineError) as exc:
            self._problem("Could not build the mesh", exc)
            return
        self.refresh(keep=[mesh.id])

    def solve_mesh(self, mesh_id: str) -> None:
        if not mesh_id:
            return
        dialog = SolveDialog(self.library, self.library.mesh(mesh_id), self)
        dialog.resultStored.connect(lambda result_id: self.refresh(keep=[result_id]))
        dialog.exec()
        self.refresh()

    def run_batch(self, condition_ids: list[str] | None = None) -> None:
        """Open the batch screen: a night of conditions, meshes and solves.

        Imported here rather than at the top for the same reason
        :class:`~pylot_bem.app.merge.MergeDialog` is -- it is one screen out of
        several and there is no reason for opening a library to pay for it.

        The refresh is deferred to the end. A batch writes through **its own**
        connection to the same file (see
        :class:`~pylot_bem.app.batch.BatchThread`), so this window's view is
        simply out of date while it runs, and rebuilding a tree of seven
        hundred conditions after each of fourteen hundred steps would spend the
        night redrawing.
        """
        from pylot_bem.app.batch import BatchDialog, summarise

        if self.library is None:
            return
        dialog = BatchDialog(self.library, condition_ids or [], self)
        # Once when the run ends, not per step, so a dialog left open after a
        # batch does not sit in front of a window describing the library as it
        # was last night.
        dialog.libraryChanged.connect(lambda: self.refresh(keep=[]))
        dialog.exec()
        self.refresh(keep=[])
        if dialog.outcome is not None:
            self.statusBar().showMessage(summarise(dialog.outcome))

    def inspect(self, result_ids: list[str]) -> None:
        if not result_ids:
            return
        self.inspect_tab.show_results(self.library, list(result_ids))
        self.tabs.setCurrentWidget(self.inspect_tab)

    def merge_results(self, result_ids: list[str]) -> None:
        """Resolve an overlap by trimming the losers.

        Not a new result: one of them wins the contested frequencies and the
        others give them up, so every frequency keeps the mesh, lid and date
        it was solved with. See :mod:`pylot_bem.app.merge`.
        """
        from pylot_bem.app.merge import MergeDialog

        if self.library is None:
            return
        # Only results, defensively: the selection pane and the tree both hand
        # ids straight through, and a mesh id looked up as a result raises.
        known = {r.id for r in self.library.results()}
        results = [self.library.result(i) for i in result_ids if i in known]
        if len(results) < 2:
            return
        dialog = MergeDialog(self.library, results, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        if dialog.combining:
            combined = self.library.combine_results(
                [r.id for r in results], primary=dialog.primary_id()
            )
            self.refresh(keep=[combined.id])
            self.statusBar().showMessage(
                f"Combined {len(results)} results into {combined.id}, covering "
                f"{len(combined.omegas)} frequencies."
            )
            return

        plan = dialog.plan()
        for result_id, omegas in plan.items():
            self.library.delete_frequencies(result_id, omegas)
        self.refresh(keep=[dialog.primary_id()])
        self.statusBar().showMessage(
            f"Merged: {sum(len(v) for v in plan.values())} frequencies removed from "
            f"{len(plan)} result(s); {dialog.primary_id()} kept everything."
        )

    def validate(self) -> None:
        self.tabs.setCurrentWidget(self.validation_tab)
        self.validation_tab.run()

    # -- deletion ----------------------------------------------------------

    def remove(self, kind: str, entity_id: str) -> None:
        """Delete something, after showing exactly what goes with it."""
        if not entity_id or self.library is None:
            return
        planners = {
            "condition": self.library.plan_condition_deletion,
            "mesh": self.library.plan_mesh_deletion,
        }
        if kind == "result":
            if not self._confirm(f"Remove result {entity_id}?", "Only this result is removed."):
                return
            self.library.delete_result(entity_id)
            self.refresh(keep=[])
            return

        plan = planners[kind](entity_id)
        if not self._confirm(f"Remove {kind} {entity_id}?", describe_plan(plan)):
            return
        deleter = self.library.delete_condition if kind == "condition" else self.library.delete_mesh
        deleter(entity_id, cascade=True)
        self.refresh(keep=[])

    def remove_selected(self) -> None:
        ids = self.tree.selected_ids()
        if not ids or not self._confirm(
            f"Remove {len(ids)} results?", "\n".join(ids) + "\n\nNothing else is affected."
        ):
            return
        for result_id in ids:
            self.library.delete_result(result_id)
        self.refresh(keep=[])

    def delete_frequencies(self, result_id: str) -> None:
        """Trim a result's frequency grid.

        The significant maintenance operation (spec 09 section I.1): it is how
        a conflict is resolved without throwing away the frequencies the two
        results do *not* contest. Which is why the preview says which conflicts
        it resolves, rather than only what it removes -- trading a conflict for
        a silent gap is not a fix.
        """
        if not result_id or self.library is None:
            return
        dialog = DeleteFrequenciesDialog(self.library, self.library.result(result_id), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        omegas = dialog.chosen_omegas()
        if not omegas:
            return
        self.library.delete_frequencies(result_id, omegas)
        self.refresh(keep=[result_id])

    def _confirm(self, question: str, detail: str) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle("Confirm removal")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(question)
        box.setInformativeText(detail + "\n\nThis cannot be undone.")
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        return box.exec() == QMessageBox.StandardButton.Yes

    def _problem(self, title: str, exc: Exception) -> None:
        """Show a refusal with its reason, which is the whole message.

        Every exception this application catches carries a sentence written to
        be read by a user -- that is what the domain errors are for -- so it is
        shown as it stands rather than replaced with a generic apology.
        """
        QMessageBox.warning(self, title, f"{type(exc).__name__}\n\n{exc}")

    # -- odds and ends -----------------------------------------------------

    def set_theme(self, name: str) -> None:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return
        if name == "System":
            app.setStyleSheet("")
            return
        app.setStyle("Fusion")
        app.setStyleSheet(DARK_SHEET if name == "Fusion dark" else "")

    def show_conventions(self) -> None:
        QMessageBox.information(self, "Conventions", CONVENTIONS)

    def show_about(self) -> None:
        from importlib.metadata import PackageNotFoundError, version

        try:
            installed = version("pylot-bem")
        except PackageNotFoundError:
            installed = "development"

        QMessageBox.about(
            self,
            "About pylot",
            f"<h3>pylot {escape(installed)}</h3>"
            "<p>Build, inspect and match hydrodynamic databases.</p>"
            "<p>Solving is Capytaine, in-process, in worker processes. "
            "Results are stored per unit density and scaled on delivery.</p>",
        )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.viewport.start()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.viewport.shutdown()
        if self.library is not None:
            self.library.close()
            self.library = None
        super().closeEvent(event)


def describe_plan(plan) -> str:
    """A deletion plan in a sentence a user can weigh.

    The counts are the point. "Remove condition" and "remove a condition, its
    three meshes and the eleven solves that took forty minutes" are the same
    click and very different decisions.
    """
    parts = []
    if plan.conditions_removed:
        parts.append(f"{len(plan.conditions_removed)} condition(s): {', '.join(plan.conditions_removed)}")
    if plan.meshes_removed:
        parts.append(f"{len(plan.meshes_removed)} mesh(es): {', '.join(plan.meshes_removed)}")
    if plan.results_removed:
        parts.append(f"{len(plan.results_removed)} result(s): {', '.join(plan.results_removed)}")
    for result_id, omegas in plan.frequencies_removed.items():
        periods = ", ".join(f"{period_from_omega(w):.2f} s" for w in omegas)
        parts.append(f"{len(omegas)} frequencies from {result_id}: {periods}")
    return "Removes " + "; ".join(parts) if parts else "Nothing would be removed."


# Enough of a dark palette to be usable, and no more. A full theme is a project
# of its own and this is not it -- the point of the option is that a user who
# works in the dark can, not that the application ships two designs.
DARK_SHEET = """
QWidget { background: #1a2029; color: #e3e9f2; }
QMenuBar, QMenu, QTabBar::tab, QHeaderView::section { background: #1d232c; color: #e3e9f2; }
QMenu::item:selected, QTabBar::tab:selected { background: #2b3542; }
QTreeWidget, QTableWidget, QListWidget, QPlainTextEdit { background: #12171d; alternate-background-color: #171d25; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #12171d; border: 1px solid #333d4b; }
QPushButton { background: #253040; border: 1px solid #333d4b; padding: 4px 10px; }
QPushButton:hover { border-color: #5b8dc4; }
QGroupBox { border: 1px solid #333d4b; margin-top: 8px; padding-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; }
"""
