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

**A library is a document, the way a text file is.** Opening one makes a private
working copy (:class:`~pylot_bem.workspace.Workspace`); everything the window
does happens to the copy; Save replaces the file, Save As writes another, and
closing, opening or creating over unsaved changes asks first. The file a person
chose is never held open, which is what keeps a synced folder from filling with
half-written ``-wal`` files. The Python API and the command line do not work
this way and are unchanged: they write in place.
"""

import os
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import numpy as np
from pylot_db.probes import probes_for_condition
from pylot_db.storage import LibraryError
from PySide6.QtCore import QLocale, QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
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
from pylot_bem.workspace import Recovery, SourceChangedError, SourceLockedError, Workspace, WorkspaceError

__all__ = ["MainWindow"]

#: How often the window asks the workspace whether it has unsaved changes, in
#: milliseconds. Not only for the asterisk in the title: the first ``True`` the
#: workspace answers is also written to its crash-recovery record, so this poll
#: is what makes a batch's results recoverable while nothing in the window
#: itself is being touched.
DIRTY_POLL_MS = 2000

#: What a Save As dialog offers, and the suffix added to a name typed without one.
LIBRARY_SUFFIX = ".pylot"
LIBRARY_FILTER = f"pylot library (*{LIBRARY_SUFFIX})"

#: The setting behind File → Save when a batch finishes.
AUTOSAVE_SETTING = "autosaveAfterBatch"

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


@contextmanager
def _waiting() -> Iterator[None]:
    """The wait cursor, for as long as the block runs.

    Saving, opening, creating and recovering all copy or write a whole library,
    and on a slow or synced disk that is long enough for the window to look
    hung. Only ever wraps the work itself: a question asked with a wait cursor
    showing looks like the answer is being waited for by the program rather
    than from the person.
    """
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        yield
    finally:
        QApplication.restoreOverrideCursor()


def _ask(
    parent: QWidget,
    title: str,
    text: str,
    detail: str,
    choices: list[tuple[str, str, QMessageBox.ButtonRole]],
    *,
    default: str,
    dismiss: str = "cancel",
) -> str:
    """Put a question with named answers to the user and return the chosen key.

    Args:
        choices: ``(key, label, role)`` per button, in the order given.
        default: The key of the button Enter presses.
        dismiss: The key answered when the box is closed with Escape or the
            title bar, which must be the answer that does the least.
    """
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(title)
    box.setText(text)
    box.setInformativeText(detail)
    buttons = {key: box.addButton(label, role) for key, label, role in choices}
    box.setDefaultButton(buttons[default])
    box.setEscapeButton(buttons[dismiss])
    box.exec()
    clicked = box.clickedButton()
    return next((key for key, button in buttons.items() if button is clicked), dismiss)


class MainWindow(QMainWindow):
    """The application.

    Opens with no library: everything below is disabled and says so, rather
    than showing an empty tree that looks like a library with nothing in it.
    """

    #: File → Recent Files, most recent first. Beyond this many, the oldest
    #: drops off -- unbounded growth would make the menu itself the thing that
    #: needs scrolling to find a recent file in.
    MAX_RECENT_FILES = 10

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        settings: QSettings | None = None,
        work_root: str | Path | None = None,
    ) -> None:
        """Build the window, with no library open.

        Args:
            parent: Qt parent.
            settings: Where Recent Files and the auto-save choice are kept.
            work_root: Where working copies of libraries are made. ``None`` is
                :func:`~pylot_bem.workspace.default_work_root`, which honours
                ``PYLOT_BEM_WORK_DIR``.
        """
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

        self._work_root = work_root
        self.workspace: Workspace | None = None
        self._dirty_timer = QTimer(self)
        self._dirty_timer.setInterval(DIRTY_POLL_MS)
        self._dirty_timer.timeout.connect(self._sync_document_state)

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

        # Direct, or Qt queues the call and the session manager has already
        # decided by the time a question could be asked. Undone in closeEvent:
        # a closed window must not be asked anything at logoff.
        if isinstance(app := QGuiApplication.instance(), QGuiApplication):
            app.commitDataRequest.connect(self.commit_data, Qt.ConnectionType.DirectConnection)

    @property
    def library(self) -> Pylot | None:
        """The open library: the workspace's working copy, or ``None``.

        Read-only. Which library is open is the workspace's to say, and a second
        place that could be assigned would be one more thing to keep in step.
        """
        return self.workspace.library if self.workspace is not None else None

    @property
    def source_path(self) -> Path | None:
        """The file the user opened -- not the working copy the window edits."""
        return self.workspace.path if self.workspace is not None else None

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
        self.save_action = file_menu.addAction("&Save", self.save_library)
        self.save_action.setShortcut(QKeySequence("Ctrl+S"))
        self.save_as_action = file_menu.addAction("Save &As…", self.save_library_as)
        self.save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.revert_action = file_menu.addAction("&Revert", self.revert_library)
        file_menu.addSeparator()

        # Off is a real choice: a person who runs a batch to try something out
        # may not want the file they opened replaced by its results.
        self.autosave_action = QAction("Save when a batch finishes", self, checkable=True)
        self.autosave_action.setChecked(bool(self._settings.value(AUTOSAVE_SETTING, True, type=bool)))
        self.autosave_action.setToolTip(
            "Save the library when a batch ends, so a night's results are in the file by morning"
        )
        self.autosave_action.toggled.connect(lambda on: self._settings.setValue(AUTOSAVE_SETTING, on))
        file_menu.addAction(self.autosave_action)
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
        """Create a library, write it to the chosen path, and open it.

        Unsaved changes are asked about **first**. The new file is written the
        moment the dialog is accepted, so there is no later point at which the
        library it replaces could still be asked about; and a question after
        the dialog would have nothing left to cancel back to.
        """
        if not self._release_current():
            return
        dialog = NewLibraryDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            # Meshing the hull and writing the file: the dialog is gone by now, so
            # this is the wait the person is left looking at.
            with _waiting():
                workspace = Workspace.create(**dialog.values(), work_root=self._work_root)
        except (LibraryError, MeshPipelineError, OSError) as exc:
            self._problem("Could not create the library", exc)
            return
        self._adopt(workspace)

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

        The file is opened **before** unsaved changes are asked about, so a
        file that will not open costs the library on screen nothing -- not even
        a question. The exception is the file that is already open and has
        unsaved changes: the new copy would be made from the file as it is
        now, and a Save answered afterwards would replace that file, leaving
        the window on an out-of-date copy of a file it then reports as
        changed by somebody else.
        """
        released = False
        workspace = self.workspace
        if workspace is not None and workspace.dirty and self._is_open_file(path):
            if not self._release_current():
                return
            released = True
        try:
            # Only the copy: the cursor is back before a refusal or a question
            # is shown.
            with _waiting():
                opened = Workspace.open(path, work_root=self._work_root)
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
        if not released and not self._release_current():
            opened.close()
            return
        self._adopt(opened)

    def _is_open_file(self, path) -> bool:
        source = self.source_path
        if source is None:
            return False
        try:
            return os.path.samefile(path, source)
        except OSError:
            return False

    def close_library(self) -> bool:
        """Close the library, after asking about unsaved changes.

        Returns:
            ``False`` if the user cancelled, or a save they asked for failed;
            the library is then exactly as it was.
        """
        if not self._release_current():
            return False
        self._drop_library()
        return True

    def _drop_library(self) -> None:
        """Close the open library and show the window as it is with none."""
        self._close_workspace()
        self._set_enabled(False)
        self._update_title()
        self.statusBar().showMessage("No library open.")

    def _adopt(self, workspace: Workspace) -> None:
        """Make ``workspace`` the open library, closing whatever was open.

        Nothing here asks about the old one: every caller has already decided
        what becomes of its changes, and by this point the new one is open, so
        there is nothing left that can fail halfway.
        """
        self._close_workspace()
        self.workspace = workspace
        self._set_enabled(True)
        self._update_title()
        # The file the user chose, never the working copy: that is a folder
        # they have never seen and that is deleted when the library closes.
        if workspace.path is not None:
            self._remember_recent_file(workspace.path)
        self._dirty_timer.start()
        self.refresh()
        self.tree.select_ids(["library"])

    def _close_workspace(self, *, reset_views: bool = True) -> None:
        """Stop watching the open library, empty every view, and delete its copy.

        Args:
            reset_views: Whether to empty the views first. Each holds the
                library it last displayed, and one that outlives it is a
                replot away from a closed database -- but a window that is
                closing has no use for that, and its 3D view is released next.
        """
        self._dirty_timer.stop()
        workspace, self.workspace = self.workspace, None
        if reset_views:
            self._reset_views()
        if workspace is not None:
            workspace.close()

    def _reset_views(self) -> None:
        self.tree.rebuild(None)
        self.viewport.clear()
        self.library_pane.clear()
        self.results_tab.clear()
        self.databases_tab.clear()
        self.inspect_tab.clear()
        self.match_tab.clear()
        self.validation_tab.clear()
        self.selection_pane.show_nothing()
        self.panes.setCurrentWidget(self.selection_pane)

    # -- the document: unsaved changes, saving, reverting --------------------

    def _update_title(self) -> None:
        """The title bar: the file the user opened, and ``*`` while it has unsaved changes.

        ``[*]`` is Qt's own placeholder, replaced by an asterisk (or the
        platform's modified marker) while :meth:`setWindowModified` is on.
        """
        workspace = self.workspace
        if workspace is None:
            self.setWindowModified(False)
            self.setWindowTitle("pylot")
            return
        self.setWindowTitle(f"pylot — {workspace.path or workspace.name}[*]")
        self.setWindowModified(workspace.dirty)

    def _sync_document_state(self) -> None:
        """Bring the modified marker in line with the workspace.

        Called on a timer and after every refresh and save. Polled rather than
        signalled because the changes that matter most arrive from a thread
        this window does not run -- a batch's connection -- and only a look at
        the database can see them.
        """
        workspace = self.workspace
        if workspace is None or workspace.closed:
            self._dirty_timer.stop()
            return
        self.setWindowModified(workspace.dirty)

    def _release_current(self) -> bool:
        """Settle the open library's unsaved changes, so something else can take its place.

        Asks and saves; **never closes anything**. Closing is the caller's
        step, taken only once everything that could still be cancelled has been.

        Returns:
            ``True`` if there was nothing to lose, or the user saved, or chose
            to discard. ``False`` on Cancel, or when the save they asked for
            did not happen.
        """
        workspace = self.workspace
        if workspace is None or not workspace.dirty:
            return True
        answer = self._ask_save()
        if answer == "save":
            return self.save_library()
        return answer == "discard"

    def save_library(self) -> bool:
        """Replace the file with the working copy.

        Returns:
            Whether the file now holds the library. ``False`` after a
            cancelled or failed save, with every change still in the window.
        """
        workspace = self.workspace
        if workspace is None:
            return False
        if workspace.path is None:  # a recovered session that never had a file
            return self.save_library_as()
        outcome = self._store(lambda force: workspace.save(force=force))
        if outcome == "save_as":
            return self.save_library_as()
        return outcome == "saved"

    def save_library_as(self) -> bool:
        """Write the library to another file, which is then the one the window has open."""
        workspace = self.workspace
        if workspace is None:
            return False
        start = str(workspace.path or workspace.name)
        chosen, _ = QFileDialog.getSaveFileName(self._dialog_parent(), "Save library as", start, LIBRARY_FILTER)
        if not chosen:
            return False
        target = Path(chosen)
        if not target.suffix:
            target = target.with_suffix(LIBRARY_SUFFIX)
            # The file dialog confirmed replacing what it was shown, and it was
            # shown "precious", not "precious.pylot". The suffix is ours, so the
            # question about the file it now names is ours too. (The open file is
            # exempt: writing to it is just Save.)
            if target.exists() and not self._is_open_file(target) and not self._ask_replace(target):
                return False

        # Saving over the file that is already open is just Save, and it is
        # checked as one: the changed-on-disk test applies to a file this
        # workspace has read, and only that.
        def write(force: bool) -> None:
            if force:
                workspace.save(force=True)
            else:
                workspace.save_as(target)

        outcome = self._store(write)
        if outcome == "save_as":
            return self.save_library_as()
        if outcome != "saved":
            return False
        self._update_title()
        if workspace.path is not None:
            self._remember_recent_file(workspace.path)
        # The tree's root names the file (its tooltip, and its label while the
        # vessel has no name), so it is stale until it is rebuilt. The refresh
        # replaces the status text with the library's counts; say what happened.
        self.refresh(keep=self.tree.selected_ids())
        self.statusBar().showMessage(f"Saved {self.source_path}.")
        return True

    def _store(self, write: Callable[[bool], None]) -> str:
        """Run a save, and settle what goes wrong with it by asking.

        Args:
            write: Does the saving, given whether the user has agreed to
                overwrite a file that changed.

        Returns:
            ``"saved"``, ``"save_as"`` if the user asked to save somewhere else
            instead, or ``"failed"`` (already reported, or cancelled).
        """
        force = False
        while True:
            try:
                with _waiting():
                    write(force)
            except SourceChangedError as exc:
                answer = self._ask_conflict(exc)
                if answer == "overwrite":
                    force = True
                    continue
                return "save_as" if answer == "save_as" else "failed"
            except SourceLockedError as exc:
                answer = self._ask_locked(exc)
                if answer == "retry":
                    continue
                return "save_as" if answer == "save_as" else "failed"
            except (WorkspaceError, LibraryError, OSError, sqlite3.Error) as exc:
                self._problem("Could not save the library", exc)
                return "failed"
            self._sync_document_state()
            self.statusBar().showMessage(f"Saved {self.source_path}.")
            return "saved"

    def revert_library(self) -> None:
        """Throw away the changes made since the file was opened, and read it again.

        The file is opened before the working copy is given up, so a file that
        can no longer be read leaves the window as it was.
        """
        workspace = self.workspace
        if workspace is None or workspace.path is None:
            return
        if workspace.dirty and not self._ask_revert():
            return
        try:
            with _waiting():
                fresh = Workspace.open(workspace.path, work_root=self._work_root)
        except (LibraryError, OSError) as exc:
            self._problem("Could not reload the library", exc)
            return
        self._adopt(fresh)
        self.statusBar().showMessage("Reverted to the saved file.")

    # -- questions ---------------------------------------------------------
    #
    # One method each, holding nothing but the message box, so a test can
    # replace exactly the question and exercise everything that follows an
    # answer. The logic that acts on the answer is never in here.

    def _dialog_parent(self) -> QWidget:
        """Where a question should hang from.

        The batch screen is modal and stays open long after its run has ended;
        a question parented to this window would sit behind it, unanswerable.
        """
        return QApplication.activeModalWidget() or self

    def _ask_save(self) -> str:
        """``"save"``, ``"discard"`` or ``"cancel"``."""
        name = self.workspace.name if self.workspace is not None else "the library"
        box = QMessageBox(self._dialog_parent())
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Unsaved changes")
        box.setText(f"Save changes to {name}?")
        box.setInformativeText("Your changes will be lost if you do not save them.")
        box.setStandardButtons(
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel
        )
        box.setDefaultButton(QMessageBox.StandardButton.Save)
        box.setEscapeButton(QMessageBox.StandardButton.Cancel)
        answer = box.exec()
        if answer == QMessageBox.StandardButton.Save:
            return "save"
        return "discard" if answer == QMessageBox.StandardButton.Discard else "cancel"

    def _ask_conflict(self, error: SourceChangedError) -> str:
        """``"overwrite"``, ``"save_as"`` or ``"cancel"``."""
        return _ask(
            self._dialog_parent(),
            "File changed",
            f"{error.path.name} was changed by someone else since it was opened.",
            f"Saving would replace their changes with yours.\n\n{error.path}",
            [
                ("overwrite", "&Overwrite", QMessageBox.ButtonRole.DestructiveRole),
                ("save_as", "Save &As…", QMessageBox.ButtonRole.AcceptRole),
                ("cancel", "Cancel", QMessageBox.ButtonRole.RejectRole),
            ],
            default="cancel",
        )

    def _ask_locked(self, error: SourceLockedError) -> str:
        """``"retry"``, ``"save_as"`` or ``"cancel"``."""
        return _ask(
            self._dialog_parent(),
            "File in use",
            f"{error.path.name} cannot be saved right now.",
            f"{error}\n\nAnother program — a sync client, DAVE, a virus scanner — may have it open, "
            "or it may be read-only. Your changes are safe in this window.",
            [
                ("retry", "&Retry", QMessageBox.ButtonRole.AcceptRole),
                ("save_as", "Save &As…", QMessageBox.ButtonRole.ActionRole),
                ("cancel", "Cancel", QMessageBox.ButtonRole.RejectRole),
            ],
            default="retry",
            dismiss="cancel",
        )

    def _ask_recover(self, recovery: Recovery) -> str:
        """``"recover"``, ``"discard"`` or ``"later"``."""
        name = (recovery.source or recovery.working_path).name
        when = f" Last recorded {recovery.updated.astimezone():%Y-%m-%d %H:%M}." if recovery.updated else ""
        return _ask(
            self._dialog_parent(),
            "Recover unsaved changes",
            f"pylot did not shut down cleanly, and {name} had unsaved changes.",
            f"Recover them to carry on where you stopped.{when} Discard deletes the recovered copy; "
            "Later asks again the next time pylot starts.",
            [
                ("recover", "&Recover", QMessageBox.ButtonRole.AcceptRole),
                ("discard", "&Discard", QMessageBox.ButtonRole.DestructiveRole),
                ("later", "&Later", QMessageBox.ButtonRole.RejectRole),
            ],
            default="recover",
            dismiss="later",
        )

    def _ask_replace(self, path: Path) -> bool:
        """Whether to replace ``path``, which exists and which the person did not name in full.

        Only asked when the window itself added the suffix: a name typed with
        one was already confirmed by the file dialog. Defaults to No, and so
        does Escape -- the answer that loses nothing.
        """
        box = QMessageBox(self._dialog_parent())
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Replace file")
        box.setText(f"{path.name} already exists. Replace it?")
        box.setInformativeText(f"{path}\n\nThe library that is there now will be overwritten. This cannot be undone.")
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        box.setEscapeButton(QMessageBox.StandardButton.No)
        return box.exec() == QMessageBox.StandardButton.Yes

    def _ask_revert(self) -> bool:
        name = self.workspace.name if self.workspace is not None else "the library"
        box = QMessageBox(self._dialog_parent())
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Revert")
        box.setText(f"Discard your changes and reload {name} from disk?")
        box.setInformativeText("Everything changed since it was opened is lost. This cannot be undone.")
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        return box.exec() == QMessageBox.StandardButton.Yes

    # -- after a crash, and at logoff ----------------------------------------

    def offer_recovery(self) -> None:
        """Offer the unsaved work earlier sessions left behind.

        Called once at startup. A session that died holding changes has its
        working copy on disk, and the only way it is ever found again is by
        someone asking; declined ones are asked about again next start.
        """
        try:
            found = Workspace.recoverable(self._work_root)
        except OSError as exc:
            self._problem("Could not look for unsaved work", exc)
            return
        postponed = 0
        for index, entry in enumerate(found):
            answer = self._ask_recover(entry)
            if answer == "discard":
                # The list was made before the question was asked, and in that
                # time another pylot may have started and picked this session up.
                # A notice rather than a status text: the next entry's answer, or
                # the recovery after it, would write over one.
                if not entry.discard():
                    self._problem(
                        "Could not discard the unsaved changes",
                        WorkspaceError(
                            f"{(entry.source or entry.working_path).name} is being used by another running pylot, "
                            "which has taken it over since the question was asked. Nothing was deleted."
                        ),
                    )
            elif answer == "recover":
                if not self._release_current():
                    return
                try:
                    with _waiting():
                        workspace = Workspace.recover(entry)
                except (LibraryError, OSError, sqlite3.Error) as exc:
                    self._problem("Could not recover the library", exc)
                    postponed += 1
                    continue
                self._adopt(workspace)
                waiting = postponed + len(found) - index - 1
                message = f"Recovered the unsaved changes to {workspace.name}."
                if waiting:
                    message += f" {waiting} more recoverable session(s) will be offered the next time pylot starts."
                self.statusBar().showMessage(message)
                return
            else:
                postponed += 1

    def commit_data(self, manager) -> None:
        """The operating system is logging off or shutting down.

        Asked only when the system allows it to ask. When it does not, nothing
        is done: the working copy is still on disk, and the next start offers
        it back.
        """
        workspace = self.workspace
        if workspace is None or not workspace.dirty or not manager.allowsInteraction():
            return
        if not self._release_current():
            manager.cancel()
        elif workspace.dirty:
            # Discard was the answer. The process is about to end without a
            # close event, and a working copy left behind with changes in it
            # is offered back at the next start as work somebody threw away.
            self._drop_library()

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
        for action in (self.close_action, self.save_action, self.save_as_action, self.revert_action):
            action.setEnabled(on)

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
            ("tree", lambda: self.tree.rebuild(self.library, keep=keep, path=self.source_path)),
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

        # Nearly every refresh follows a change, so this is the moment the
        # title should know about it; the timer covers the changes that do not.
        self._sync_document_state()

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

        What the status bar says afterwards is set last, after that refresh has
        written the library's counts over it: how the run ended, and whether it
        was saved automatically.
        """
        from pylot_bem.app.batch import BatchDialog, summarise

        if self.library is None:
            return
        # The run is handed the working copy (the dialog reads it from the
        # library), and the user's file only for naming things beside it.
        dialog = BatchDialog(self.library, condition_ids or [], self, source_path=self.source_path)
        # Once when the run ends, not per step, so a dialog left open after a
        # batch does not sit in front of a window describing the library as it
        # was last night. The same moment is when it is saved: the dialog is
        # modal and may stay open for hours after the run, and a night's
        # results should not wait on someone closing it.
        ended: list[bool] = []  # per run that reported its end: whether that saved

        def run_ended() -> None:
            ended.append(self._after_batch())

        dialog.libraryChanged.connect(run_ended)
        dialog.exec()
        # Closing the screen over a running batch kills it and waits, but the
        # thread's report is only queued: it is delivered after exec() has
        # returned, if the event loop ever gets there. Listening for it would
        # refresh (and drop the selection) at some arbitrary later moment, so
        # this is the last the hook hears.
        dialog.libraryChanged.disconnect(run_ended)
        self.refresh(keep=[])

        # A run that was begun and never reported its end was cut short by that
        # close, and left whatever it had written in the working copy. One that
        # did report has had its chance to save -- and if the person declined
        # the question that came with it, it is not asked again.
        cut_short = dialog.runs_started > len(ended)
        saved = any(ended)
        if cut_short:
            saved = self._autosave() or saved
        if not ended and not cut_short:
            return  # the screen was opened and closed; refresh() has said what the library holds

        # After the refresh, which writes the library's counts over the status
        # bar, and always: a crashed run has no outcome and still has to say so.
        if dialog.outcome is not None:
            message = summarise(dialog.outcome)
        elif cut_short:
            message = "The batch was closed before it finished."
        else:
            message = "The batch failed."
        if saved:
            message += " Saved automatically after the batch."
        self.statusBar().showMessage(message)

    def _after_batch(self) -> bool:
        """Show what a run wrote and, if asked to, save it. Whether it was saved.

        ``libraryChanged`` fires when a run ends whether or not it wrote
        anything -- a run that found everything already done, or that crashed
        first -- so what decides is whether the workspace is actually dirty.
        """
        self.refresh(keep=[])
        return self._autosave()

    def _autosave(self) -> bool:
        """Save what a batch wrote, if the setting says to and there is something to save.

        A save goes through :meth:`save_library` like any other, so a file
        changed on disk meanwhile is asked about rather than overwritten.

        Returns:
            Whether the library was saved.
        """
        workspace = self.workspace
        if workspace is None or not self.autosave_action.isChecked() or not workspace.dirty:
            return False
        if not self.save_library():
            return False
        self.statusBar().showMessage("Saved automatically after the batch.")
        return True

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
        QMessageBox.warning(self._dialog_parent(), title, f"{type(exc).__name__}\n\n{exc}")

    # -- odds and ends -----------------------------------------------------

    def set_theme(self, name: str) -> None:
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
        """Close, unless the user cancels being asked about unsaved changes.

        The question comes **before** anything is shut down. The viewport used
        to be released first, which after a Cancel left a live window with a
        dead 3D view.
        """
        if not self._release_current():
            event.ignore()
            return
        if isinstance(app := QGuiApplication.instance(), QGuiApplication):
            try:
                app.commitDataRequest.disconnect(self.commit_data)
            except RuntimeError, TypeError:  # never connected, or already gone
                pass
        self._close_workspace(reset_views=False)
        self.viewport.shutdown()
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
