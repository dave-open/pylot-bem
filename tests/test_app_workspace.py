"""The window as a text editor: open a private copy, save when asked.

``test_app.py`` covers what the screens do to a library. This covers what the
window does about *the file*: the title and its asterisk, Save, Save As,
Revert, the questions asked before anything unsaved is given up, what happens
when the file changed underneath, when it cannot be replaced, when a batch
finishes, and when a session dies holding work.

Nothing is mocked but the message boxes -- and only the boxes. Every question
the window can ask is one overridable method, replaced here by a script of
answers that also records what was asked, so a test says "the user pressed
Cancel" and then asserts on what the window, the library and the files did.
A question nobody scripted fails the test, instead of blocking it.

Where a test needs a file to have changed on disk, another connection really
changes it; where it needs a file held open, a handle is really held; where it
needs a session to have crashed, a process is really killed.
"""

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import threading
import time
import types
from datetime import UTC, datetime
from pathlib import Path

import pytest
from hull import BOX_FACES, BOX_VERTICES, TANKER_STL
from pylot_db.storage import Library, LibraryError
from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox

import pylot_bem.app
import pylot_bem.app.window as window_module
from pylot_bem.api import Pylot
from pylot_bem.app.batch import BatchDialog, BatchThread, summarise
from pylot_bem.app.viewport import Viewport
from pylot_bem.app.window import MainWindow
from pylot_bem.batch import JOB_SUFFIX, BatchRun
from pylot_bem.solver import SolveSettings
from pylot_bem.workspace import Recovery, SourceChangedError, SourceLockedError, Workspace

# The questions as they really are, before the fixture below replaces them, so
# the wording and the buttons can be exercised too.
QUESTIONS = ("_ask_save", "_ask_conflict", "_ask_locked", "_ask_recover", "_ask_replace", "_ask_revert")
REAL_QUESTIONS = {name: getattr(MainWindow, name) for name in QUESTIONS}


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def library_path(tmp_path_factory):
    """A small library: a hull, two conditions, and one solved result on the second."""
    path = tmp_path_factory.mktemp("workspace") / "fixture.pylot"
    library = Pylot.create(
        path,
        vessel_name="Boxboat",
        origin_description="stern, centerline, keel",
        vertices=BOX_VERTICES,
        faces=BOX_FACES,
        is_xz_symmetric=True,
    )
    library.create_condition(z_origin=-2.0, condition_id="ballast", label="Ballast")
    design = library.create_condition(z_origin=-4.0, condition_id="design", label="Design")
    mesh = library.create_mesh(design, pct=20.0, iterations=5, mesh_id="design-mesh")
    library.run_solve(mesh, SolveSettings(omegas=(0.5, 0.6), wave_directions=(0.0, 90.0)), result_id="run")
    library.close()
    return path


@pytest.fixture
def path(library_path, tmp_path):
    """A private copy, so a test that saves cannot affect another."""
    copy = tmp_path / "library.pylot"
    shutil.copy(library_path, copy)
    return copy


@pytest.fixture
def other(library_path, tmp_path):
    """A second library, for the tests that replace the first."""
    copy = tmp_path / "other.pylot"
    shutil.copy(library_path, copy)
    return copy


@pytest.fixture
def isolated_settings(tmp_path):
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


@pytest.fixture
def work_root(tmp_path):
    return tmp_path / "work"


class Prompts:
    """Scripted answers to the window's questions, and a record of what was asked.

    ``will("save", "cancel")`` answers the next Save-changes question with
    Cancel. An answer may be a function of the question's arguments, for the
    test that has to do something *while* the question is up. A question with
    no answer scripted is a failure, not a hang.
    """

    def __init__(self, monkeypatch):
        self.asked: list[str] = []
        self.args: dict[str, list[tuple]] = {}
        self.unexpected: list[str] = []
        self._script: dict[str, list] = {}
        for name in QUESTIONS:
            monkeypatch.setattr(MainWindow, name, self._question(name.removeprefix("_ask_")))

    def will(self, key, *answers):
        self._script[key] = list(answers)

    def _question(self, key):
        def ask(window, *args):
            self.asked.append(key)
            self.args.setdefault(key, []).append(args)
            script = self._script.get(key)
            if not script:
                self.unexpected.append(key)
                raise AssertionError(f"unexpected prompt: {key}")
            answer = script.pop(0)
            return answer(*args) if callable(answer) else answer

        return ask


@pytest.fixture(autouse=True)
def prompts(monkeypatch):
    scripted = Prompts(monkeypatch)
    yield scripted
    assert not scripted.unexpected, f"the window asked {scripted.unexpected}, which the test did not script"


@pytest.fixture
def problems(monkeypatch):
    """Refusals the window reported, as ``(title, message)``, instead of a modal box."""
    seen = []
    monkeypatch.setattr(MainWindow, "_problem", lambda self, title, exc: seen.append((title, str(exc))))
    return seen


def make_window(settings, work_root, *, open_path=None):
    main = MainWindow(settings=settings, work_root=work_root)
    main.show()
    if open_path is not None:
        main.open_path(open_path)
    return main


@pytest.fixture
def window(qapp, path, isolated_settings, work_root, prompts):
    main = make_window(isolated_settings, work_root, open_path=path)
    yield main
    prompts.will("save", "discard")
    main.close()


@pytest.fixture
def empty_window(qapp, isolated_settings, work_root, prompts):
    main = make_window(isolated_settings, work_root)
    yield main
    prompts.will("save", "discard")
    main.close()


def pump(qapp, predicate, timeout=120.0):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()
    return predicate()


def edit(window, label="Edited"):
    """A change the way the window makes one: through the library, then a refresh."""
    window.library.set_condition_label("design", label)
    window.refresh(keep=[])


def label_in(path, condition="design"):
    """What the *file* says, read the way another program would."""
    with Library.open(path, read_only=True) as library:
        return library.condition(condition).label


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def strays(path):
    """Anything beside a library that is not the library: journals, temporaries."""
    return sorted(p.name for p in path.parent.iterdir() if p.name.startswith((path.name, "~")) and p != path)


def change_on_disk(path, label="Elsewhere"):
    """Somebody else changes the file, through their own connection."""
    with Pylot.open(path) as library:
        library.set_condition_label("ballast", label)


def choose_file(monkeypatch, chosen):
    """Answer the Save As file dialog, and keep what it was asked."""
    asked = []

    def dialog(*args, **kwargs):
        asked.append(args)
        return (str(chosen) if chosen else ""), ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(dialog))
    return asked


# --------------------------------------------------------------------------
# The title, the asterisk, and what Save writes
# --------------------------------------------------------------------------


def test_the_title_names_the_file_the_user_opened(window, path):
    assert window.windowTitle() == f"pylot — {path}[*]"
    assert not window.isWindowModified()
    assert window.source_path == path
    assert window.library.path != path
    assert window.workspace.working_path == window.library.path


def test_the_tree_names_the_users_file_not_the_working_copy(window, path):
    root = window.tree.topLevelItem(0)

    assert root.toolTip(0) == str(path)
    assert root.text(0) == "Boxboat"


def test_a_window_with_no_library_is_just_pylot(empty_window):
    assert empty_window.windowTitle() == "pylot"
    assert not empty_window.isWindowModified()
    assert empty_window.library is None
    assert empty_window.source_path is None


def test_the_library_cannot_be_assigned_from_outside(window):
    with pytest.raises(AttributeError):
        window.library = None
    assert window.library is window.workspace.library


def test_an_edit_marks_the_window_and_the_file_is_untouched_until_save(window, path):
    before = sha(path)
    edit(window)

    assert window.isWindowModified()
    assert window.library.condition("design").label == "Edited"
    assert sha(path) == before, "the file the user chose must not be written to by editing"
    assert strays(path) == [], "and no journal appears beside it"
    assert label_in(path) == "Design"


def test_save_writes_the_original_and_clears_the_mark(window, path):
    edit(window)

    assert window.save_library() is True

    assert not window.isWindowModified()
    assert label_in(path) == "Edited"
    assert strays(path) == [], "the saved file is one ordinary file"
    assert "Saved" in window.statusBar().currentMessage()
    assert window.source_path == path


def test_save_is_a_menu_action_with_the_usual_shortcut(window, path):
    assert window.save_action.shortcut().toString() == "Ctrl+S"
    assert window.save_as_action.shortcut().toString() == "Ctrl+Shift+S"
    edit(window)

    window.save_action.trigger()

    assert label_in(path) == "Edited"


def test_a_second_edit_after_saving_marks_the_window_again(window, path):
    edit(window)
    assert window.save_library()
    assert not window.isWindowModified()

    edit(window, "Edited again")

    assert window.isWindowModified()
    assert label_in(path) == "Edited"
    assert window.save_library()
    assert label_in(path) == "Edited again"


def test_save_shows_the_wait_cursor_and_gives_it_back(window, monkeypatch):
    seen = []
    real = Workspace.save

    def save(self, **kwargs):
        seen.append(QApplication.overrideCursor().shape())
        return real(self, **kwargs)

    monkeypatch.setattr(Workspace, "save", save)
    edit(window)

    assert window.save_library()

    assert seen == [Qt.CursorShape.WaitCursor]
    assert QApplication.overrideCursor() is None


def test_a_save_that_fails_is_reported_and_leaves_the_window_unsaved(window, path, tmp_path, problems):
    folder = tmp_path / "vanishing"
    folder.mkdir()
    doomed = folder / "library.pylot"
    shutil.copy(path, doomed)
    window.open_path(doomed)
    edit(window)
    shutil.rmtree(folder)  # nothing holds the file, so this is allowed -- and Save has nowhere to write

    assert window.save_library() is False

    assert problems and problems[0][0] == "Could not save the library"
    assert QApplication.overrideCursor() is None
    assert window.isWindowModified(), "a failed save must not look like a saved one"


def test_save_and_the_other_document_actions_need_a_library(empty_window, window):
    for action in ("save_action", "save_as_action", "revert_action", "close_action"):
        assert not getattr(empty_window, action).isEnabled(), action
        assert getattr(window, action).isEnabled(), action
    assert empty_window.save_library() is False
    assert empty_window.save_library_as() is False
    empty_window.revert_library()
    assert empty_window.library is None


def test_the_file_menu_is_in_the_documented_order(window):
    entries = ["" if a.isSeparator() else a.text().replace("&", "") for a in window.menus["File"].actions()]

    assert entries == [
        "New library…",
        "Open library…",
        "Recent Files",
        "Close library",
        "",
        "Save",
        "Save As…",
        "Revert",
        "",
        "Save when a batch finishes",
        "",
        "Exit",
    ]


# --------------------------------------------------------------------------
# Save As
# --------------------------------------------------------------------------


def test_save_as_moves_the_window_to_the_new_file_and_leaves_the_old_one(
    window, path, tmp_path, monkeypatch, prompts
):
    dialogs = choose_file(monkeypatch, tmp_path / "copy")  # no suffix: .pylot is added
    before = sha(path)
    edit(window)

    assert window.save_library_as() is True

    target = tmp_path / "copy.pylot"
    assert prompts.asked == [], "nothing was there to replace, so nothing to ask"
    assert dialogs[0][2] == str(path), "the dialog starts at the file being edited"
    assert window.source_path == target
    assert window.windowTitle() == f"pylot — {target}[*]"
    assert not window.isWindowModified()
    assert label_in(target) == "Edited"
    assert sha(path) == before, "the file it came from is exactly as it was"
    assert window._recent_files() == [str(target), str(path)]

    edit(window, "Edited again")
    assert window.save_library()
    assert label_in(target) == "Edited again", "later saves go to the new file"
    assert sha(path) == before


def test_cancelling_the_save_as_dialog_changes_nothing(window, path, monkeypatch):
    choose_file(monkeypatch, None)
    edit(window)

    assert window.save_library_as() is False

    assert window.source_path == path
    assert window.isWindowModified()
    assert label_in(path) == "Design"


def test_save_as_over_the_open_file_is_an_ordinary_save(window, path, monkeypatch):
    choose_file(monkeypatch, path)
    edit(window)

    assert window.save_library_as() is True

    assert window.source_path == path
    assert label_in(path) == "Edited"
    assert not window.isWindowModified()


def test_save_as_over_the_open_file_still_notices_it_changed(window, path, monkeypatch, prompts):
    choose_file(monkeypatch, path)
    edit(window)
    change_on_disk(path)
    prompts.will("conflict", "overwrite")

    assert window.save_library_as() is True

    assert prompts.asked == ["conflict"]
    assert label_in(path) == "Edited"
    assert label_in(path, "ballast") == "Ballast", "overwritten means their change is gone"


@pytest.fixture
def precious(tmp_path, other):
    """A library already at the name a Save As is about to give a suffix to."""
    target = tmp_path / "precious.pylot"
    shutil.copy(other, target)
    return target


def test_save_as_asks_before_replacing_a_file_only_the_added_suffix_points_at(
    window, path, tmp_path, precious, monkeypatch, prompts
):
    """The file dialog was shown "precious", and confirmed nothing about "precious.pylot"."""
    choose_file(monkeypatch, tmp_path / "precious")
    edit(window)
    prompts.will("replace", True)

    assert window.save_library_as() is True

    assert prompts.asked == ["replace"]
    assert prompts.args["replace"][0] == (precious,), "it names the file that would go"
    assert label_in(precious) == "Edited"
    assert window.source_path == precious
    assert QApplication.overrideCursor() is None


def test_refusing_to_replace_what_the_suffix_pointed_at_writes_nothing(
    window, path, tmp_path, precious, monkeypatch, prompts
):
    choose_file(monkeypatch, tmp_path / "precious")
    edit(window)
    theirs, ours = sha(precious), sha(path)
    prompts.will("replace", False)

    assert window.save_library_as() is False

    assert prompts.asked == ["replace"]
    assert sha(precious) == theirs and label_in(precious) == "Design"
    assert sha(path) == ours
    assert strays(precious) == [] and strays(path) == []
    assert window.source_path == path and window.isWindowModified()
    assert window.library.condition("design").label == "Edited", "every change is still in the window"
    assert window._recent_files() == [str(path)]


def test_save_as_does_not_ask_again_about_a_name_the_file_dialog_already_confirmed(
    window, precious, monkeypatch, prompts
):
    choose_file(monkeypatch, precious)  # typed in full, so the dialog has already asked
    edit(window)

    assert window.save_library_as() is True

    assert prompts.asked == []
    assert label_in(precious) == "Edited"


def test_save_as_to_the_open_files_name_without_its_suffix_is_just_a_save(window, path, monkeypatch, prompts):
    choose_file(monkeypatch, path.with_suffix(""))
    edit(window)

    assert window.save_library_as() is True

    assert prompts.asked == [], "it is the file already open, which Save writes without asking"
    assert window.source_path == path
    assert label_in(path) == "Edited"


@pytest.mark.parametrize("vessel", ["", "Boxboat"])
def test_save_as_brings_the_tree_root_up_to_date(window, path, tmp_path, monkeypatch, vessel):
    """The root names the file in its tooltip, and in its label while the vessel has no name."""
    window.library.set_info(vessel_name=vessel)
    window.tree.select_ids(["design"])
    window.refresh()
    root = window.tree.topLevelItem(0)
    assert root.text(0) == (vessel or "library")
    assert root.toolTip(0) == str(path)
    choose_file(monkeypatch, tmp_path / "renamed")

    assert window.save_library_as() is True

    target = tmp_path / "renamed.pylot"
    root = window.tree.topLevelItem(0)
    assert root.text(0) == (vessel or "renamed"), "the user's file, not the working copy that kept the old name"
    assert root.toolTip(0) == str(target)
    assert window.tree.selected_ids() == ["design"], "the selection survives the rebuild"
    assert window.statusBar().currentMessage() == f"Saved {target}."


# --------------------------------------------------------------------------
# Revert
# --------------------------------------------------------------------------


def test_revert_reloads_the_file_and_forgets_the_edit(window, path, prompts):
    edit(window)
    assert "Edited" in [window.tree.topLevelItem(0).child(i).text(0) for i in range(2)]
    old = window.workspace
    prompts.will("revert", True)

    window.revert_library()

    assert prompts.asked == ["revert"]
    assert old.closed and window.workspace is not old
    assert window.library.condition("design").label == "Design"
    assert "Edited" not in [window.tree.topLevelItem(0).child(i).text(0) for i in range(2)], "the tree was rebuilt"
    assert not window.isWindowModified()
    assert window.source_path == path
    assert window.statusBar().currentMessage() == "Reverted to the saved file."


def test_declining_a_revert_keeps_everything(window, prompts):
    edit(window)
    workspace = window.workspace
    prompts.will("revert", False)

    window.revert_library()

    assert window.workspace is workspace
    assert window.library.condition("design").label == "Edited"
    assert window.isWindowModified()


def test_reverting_a_clean_library_asks_nothing_and_rereads_the_file(window, path, prompts):
    change_on_disk(path)  # somebody else's change, which a reload should pick up
    assert window.library.condition("ballast").label == "Ballast"

    window.revert_library()

    assert prompts.asked == []
    assert window.library.condition("ballast").label == "Elsewhere"


def test_a_revert_that_cannot_read_the_file_keeps_the_window_as_it_was(window, path, problems, prompts):
    edit(window)
    workspace = window.workspace
    path.unlink()
    prompts.will("revert", True)

    window.revert_library()

    assert problems and problems[0][0] == "Could not reload the library"
    assert window.workspace is workspace and not workspace.closed
    assert window.library.condition("design").label == "Edited"
    assert window.isWindowModified()


# --------------------------------------------------------------------------
# Recent files hold the file, not the copy
# --------------------------------------------------------------------------


def test_recent_files_hold_the_users_file_never_the_working_copy(window, path, work_root, other):
    assert window._recent_files() == [str(path)]
    window.open_path(other)
    assert window._recent_files() == [str(other), str(path)]
    window.revert_library()
    assert window._recent_files() == [str(other), str(path)]

    for entry in window._recent_files():
        assert work_root not in Path(entry).parents


# --------------------------------------------------------------------------
# The questions: which entry points ask, in what order, and what Cancel does
# --------------------------------------------------------------------------


@pytest.fixture
def new_dialog(monkeypatch, tmp_path):
    """Stands in for the New library dialog: accepted, with values that make a real library."""
    state = types.SimpleNamespace(shown=0, target=tmp_path / "brand-new.pylot", accept=True, cursors=[])

    class Stub:
        def __init__(self, parent=None):
            pass

        def exec(self):
            state.shown += 1
            state.cursors.append(QApplication.overrideCursor())  # what the person sees while it is up
            return QDialog.DialogCode.Accepted if state.accept else QDialog.DialogCode.Rejected

        def values(self):
            return {
                "path": state.target,
                "mesh_file": TANKER_STL,
                "origin_description": "keel",
                "is_xz_symmetric": True,
                "scale": 1.0,
                "vessel_name": "Brand new",
                "description": "",
            }

    monkeypatch.setattr(window_module, "NewLibraryDialog", Stub)
    return state


def recent_action(window, target):
    window._remember_recent_file(target)
    return next(a for a in window.recent_menu.actions() if a.text() == str(target))


# name -> (do it, has it happened?)
def menu_action(window, menu, text):
    return next(a for a in window.menus[menu].actions() if a.text().replace("&", "") == text)


ENTRY_POINTS = {
    "close the window": (lambda w, c: w.close(), lambda w, c: w.workspace is None),
    "File > Exit": (lambda w, c: menu_action(w, "File", "Exit").trigger(), lambda w, c: w.workspace is None),
    "File > Close": (lambda w, c: w.close_library(), lambda w, c: w.workspace is None),
    "open": (lambda w, c: w.open_path(c.other), lambda w, c: w.source_path == c.other),
    "recent file": (
        lambda w, c: recent_action(w, c.other).trigger(),
        lambda w, c: w.source_path == c.other,
    ),
    "new": (lambda w, c: w.new_library(), lambda w, c: w.source_path == c.new.target),
}


@pytest.mark.parametrize("answer", ["save", "discard", "cancel"])
@pytest.mark.parametrize("entry", list(ENTRY_POINTS))
def test_every_way_of_leaving_unsaved_changes_asks_first(
    entry, answer, window, path, other, new_dialog, prompts, work_root, monkeypatch
):
    shutdowns = []
    real_shutdown = Viewport.shutdown
    monkeypatch.setattr(Viewport, "shutdown", lambda self: (shutdowns.append(True), real_shutdown(self)))
    context = types.SimpleNamespace(other=other, new=new_dialog)
    act, happened = ENTRY_POINTS[entry]
    edit(window)
    before = sha(path)
    workspace, library = window.workspace, window.library
    prompts.will("save", answer)

    act(window, context)

    assert prompts.asked == ["save"], "asked exactly once"
    if answer == "cancel":
        assert not happened(window, context)
        assert window.workspace is workspace and window.library is library
        assert not workspace.closed
        assert window.isVisible() and window.isWindowModified()
        assert window.library.condition("design").label == "Edited", "the change is still there"
        assert sha(path) == before, "and the file is untouched"
        assert shutdowns == [], "the 3D view of a window that stays open must stay alive"
        assert window.viewport._interactor.isVisible()
        assert len(list(work_root.iterdir())) == 1, "a library opened only to be refused was cleaned up"
        if entry == "new":
            assert new_dialog.shown == 0 and not new_dialog.target.exists(), "nothing to create over"
        return

    assert happened(window, context)
    assert workspace.closed
    assert label_in(path) == ("Edited" if answer == "save" else "Design")
    if answer == "discard":
        assert sha(path) == before
    if entry == "new":
        assert new_dialog.shown == 1 and new_dialog.target.is_file()
    if entry in ("close the window", "File > Exit", "File > Close"):
        assert list(work_root.iterdir()) == []
    else:
        assert len(list(work_root.iterdir())) == 1


def test_looking_at_a_library_changes_nothing_in_it(window, prompts):
    """Every screen reads; none may write, or the asterisk means nothing.

    A read that quietly wrote -- a cache, a migration, a default filled in --
    would make every library "unsaved" the moment it opened and teach people to
    click through the question.
    """
    for node in ("library", "ballast", "design", "design-mesh", "run"):
        window.tree.select_ids([node])
    window.validate()
    window.match_tab.rank()
    window.inspect(["run"])
    window.refresh()

    assert not window.workspace.dirty
    assert not window.isWindowModified()
    assert window.close_library()
    assert prompts.asked == []


def test_a_clean_library_is_left_without_a_question(window, other, prompts):
    window.open_path(other)
    window.close_library()

    assert prompts.asked == []


def test_the_asterisk_is_the_only_thing_that_decides(window, prompts):
    """A library that was edited and then saved is not asked about."""
    edit(window)
    assert window.save_library()

    assert window.close_library()
    assert prompts.asked == []


def test_a_library_that_will_not_open_costs_the_open_one_nothing_and_asks_nothing(
    window, tmp_path, problems, prompts
):
    edit(window)
    workspace = window.workspace
    rubbish = tmp_path / "rubbish.pylot"
    rubbish.write_bytes(b"this is not a database")

    window.open_path(rubbish)
    window.open_path(tmp_path / "missing.pylot")

    assert len(problems) == 2 and {title for title, _ in problems} == {"Could not open the library"}
    assert prompts.asked == []
    assert window.workspace is workspace and window.isWindowModified()


def test_reopening_the_file_that_is_open_saves_before_reading_it(window, path, prompts):
    """The one case where the order has to flip.

    Opened first, the new copy would be made from the file as it is now, and
    the Save that follows would replace that file -- leaving the window on a
    stale copy of a file it would then call changed by someone else.
    """
    edit(window)
    prompts.will("save", "save")

    window.open_path(path)

    assert prompts.asked == ["save"]
    assert window.library.condition("design").label == "Edited"
    assert not window.isWindowModified()
    edit(window, "Edited again")
    assert window.save_library(), "no spurious 'changed by someone else'"
    assert label_in(path) == "Edited again"


def test_reopening_the_file_that_is_open_and_discarding_starts_from_the_file(window, path, prompts):
    edit(window)
    prompts.will("save", "discard")

    window.open_path(path)

    assert prompts.asked == ["save"], "asked once, not again after the new copy exists"
    assert window.library.condition("design").label == "Design"
    assert not window.isWindowModified()


# --------------------------------------------------------------------------
# New library
# --------------------------------------------------------------------------


def test_a_new_library_is_a_file_immediately_and_starts_clean(window, new_dialog, tmp_path):
    window.new_library()

    target = new_dialog.target
    assert target.is_file(), "written at the chosen path straight away, not held as untitled"
    assert window.source_path == target
    assert not window.isWindowModified()
    assert window.windowTitle() == f"pylot — {target}[*]"
    assert window.library.path != target
    assert window._recent_files()[0] == str(target)
    assert len(window.library.conditions()) == 0
    assert window.library.info.vessel_name == "Brand new"


def test_a_new_library_that_cannot_be_created_leaves_the_open_one(window, new_dialog, problems, path):
    new_dialog.target = path  # exists already
    workspace = window.workspace

    window.new_library()

    assert problems and problems[0][0] == "Could not create the library"
    assert window.workspace is workspace and not workspace.closed


def test_cancelling_the_new_library_dialog_leaves_the_open_one(window, new_dialog):
    new_dialog.accept = False
    workspace = window.workspace

    window.new_library()

    assert new_dialog.shown == 1
    assert window.workspace is workspace and not new_dialog.target.exists()


# --------------------------------------------------------------------------
# The wait cursor: on the slow paths, around the work and nothing else
# --------------------------------------------------------------------------


def cursor_during(monkeypatch, name):
    """Record the override cursor at the moment ``Workspace.<name>`` is called.

    ``None`` is recorded as ``None``. The real method still runs, so the
    window carries on exactly as it does in use.
    """
    seen = []
    real = getattr(Workspace, name)

    def wrapped(*args, **kwargs):
        cursor = QApplication.overrideCursor()
        seen.append(cursor.shape() if cursor is not None else None)
        return real(*args, **kwargs)

    monkeypatch.setattr(Workspace, name, staticmethod(wrapped))
    return seen


def test_opening_a_library_shows_the_wait_cursor_and_gives_it_back(window, other, monkeypatch):
    seen = cursor_during(monkeypatch, "open")

    window.open_path(other)

    assert seen == [Qt.CursorShape.WaitCursor]
    assert QApplication.overrideCursor() is None
    assert window.source_path == other


def test_the_wait_cursor_is_gone_before_the_save_question_is_asked(window, other, prompts, monkeypatch):
    """The copy is made first and the question comes after it, so it must not be asked under a wait cursor."""
    edit(window)
    seen = cursor_during(monkeypatch, "open")
    at_question = []
    prompts.will("save", lambda: (at_question.append(QApplication.overrideCursor()), "discard")[1])

    window.open_path(other)

    assert seen == [Qt.CursorShape.WaitCursor]
    assert at_question == [None]


def test_the_wait_cursor_is_gone_before_a_refusal_is_shown(window, tmp_path, monkeypatch):
    shown = []
    monkeypatch.setattr(MainWindow, "_problem", lambda self, title, exc: shown.append(QApplication.overrideCursor()))
    seen = cursor_during(monkeypatch, "open")
    rubbish = tmp_path / "rubbish.pylot"
    rubbish.write_bytes(b"this is not a database")

    window.open_path(rubbish)

    assert seen == [Qt.CursorShape.WaitCursor], "it was waiting while it tried"
    assert shown == [None], "and is not when it says it failed"
    assert QApplication.overrideCursor() is None


def test_reverting_shows_the_wait_cursor_and_gives_it_back(window, monkeypatch):
    seen = cursor_during(monkeypatch, "open")

    window.revert_library()

    assert seen == [Qt.CursorShape.WaitCursor]
    assert QApplication.overrideCursor() is None
    assert window.statusBar().currentMessage() == "Reverted to the saved file."


def test_creating_a_library_shows_the_wait_cursor_only_once_the_dialog_has_closed(window, new_dialog, monkeypatch):
    seen = cursor_during(monkeypatch, "create")

    window.new_library()

    assert new_dialog.cursors == [None], "no wait cursor over the dialog the person is filling in"
    assert seen == [Qt.CursorShape.WaitCursor]
    assert QApplication.overrideCursor() is None
    assert window.source_path == new_dialog.target


def test_recovering_shows_the_wait_cursor_and_gives_it_back(empty_window, dead_session, prompts, monkeypatch):
    seen = cursor_during(monkeypatch, "recover")
    prompts.will("recover", "recover")

    empty_window.offer_recovery()

    assert seen == [Qt.CursorShape.WaitCursor]
    assert QApplication.overrideCursor() is None
    assert empty_window.library is not None


# --------------------------------------------------------------------------
# The file changed underneath
# --------------------------------------------------------------------------


def test_a_file_changed_by_someone_else_is_overwritten_only_when_asked(window, path, prompts):
    edit(window)
    change_on_disk(path)
    prompts.will("conflict", "overwrite")

    assert window.save_library() is True

    assert prompts.asked == ["conflict"]
    error = prompts.args["conflict"][0][0]
    assert isinstance(error, SourceChangedError) and error.path == path
    assert label_in(path) == "Edited"
    assert label_in(path, "ballast") == "Ballast", "their change is gone, as it was told it would be"
    assert not window.isWindowModified()


def test_a_file_changed_by_someone_else_can_be_kept_and_the_edit_saved_elsewhere(
    window, path, tmp_path, prompts, monkeypatch
):
    edit(window)
    change_on_disk(path)
    prompts.will("conflict", "save_as")
    choose_file(monkeypatch, tmp_path / "mine.pylot")

    assert window.save_library() is True

    assert label_in(path, "ballast") == "Elsewhere" and label_in(path) == "Design", "theirs is untouched"
    assert label_in(tmp_path / "mine.pylot") == "Edited"
    assert window.source_path == tmp_path / "mine.pylot"
    assert not window.isWindowModified()


def test_a_file_changed_by_someone_else_and_cancel_saves_nothing(window, path, prompts):
    edit(window)
    change_on_disk(path)
    ours = sha(path)
    prompts.will("conflict", "cancel")

    assert window.save_library() is False

    assert sha(path) == ours
    assert window.isWindowModified()
    assert window.library.condition("design").label == "Edited"
    assert window.source_path == path


def test_cancelling_a_conflict_while_closing_keeps_the_window(window, path, prompts):
    edit(window)
    change_on_disk(path)
    prompts.will("save", "save")
    prompts.will("conflict", "cancel")

    window.close()

    assert prompts.asked == ["save", "conflict"]
    assert window.isVisible() and window.workspace is not None
    assert window.library.condition("design").label == "Edited"


def test_a_touch_that_changes_no_byte_is_not_a_conflict(window, path):
    """A sync client rewrites modification times. That is not somebody's edit."""
    edit(window)
    before = path.stat()
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns + 5_000_000_000))

    assert window.save_library() is True  # a conflict prompt would have failed the test
    assert label_in(path) == "Edited"


# --------------------------------------------------------------------------
# The file cannot be replaced
# --------------------------------------------------------------------------

windows_only = pytest.mark.skipif(
    sys.platform != "win32", reason="only Windows refuses to replace a file that something has open"
)
not_root = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root can write to a read-only file"
)


@pytest.fixture
def impatient(monkeypatch):
    """Give up on a held file after a moment rather than the several seconds it really waits."""
    monkeypatch.setattr("pylot_bem.workspace.REPLACE_BUDGET", 0.05)


@windows_only
def test_a_file_held_open_can_be_retried_once_it_is_free(window, path, prompts, impatient):
    edit(window)
    handle = path.open("rb")
    prompts.will("locked", lambda error: (handle.close(), "retry")[1])
    try:
        assert window.save_library() is True
    finally:
        handle.close()

    assert prompts.asked == ["locked"]
    error = prompts.args["locked"][0][0]
    assert isinstance(error, SourceLockedError) and error.reason and error.path == path
    assert label_in(path) == "Edited"
    assert not window.isWindowModified()


@windows_only
def test_a_file_held_open_can_be_saved_elsewhere(window, path, tmp_path, prompts, impatient, monkeypatch):
    edit(window)
    prompts.will("locked", "save_as")
    choose_file(monkeypatch, tmp_path / "elsewhere.pylot")
    with path.open("rb"):
        assert window.save_library() is True

    assert label_in(tmp_path / "elsewhere.pylot") == "Edited"
    assert label_in(path) == "Design"
    assert window.source_path == tmp_path / "elsewhere.pylot"


@windows_only
def test_cancelling_a_locked_save_keeps_every_change(window, path, prompts, impatient):
    edit(window)
    prompts.will("locked", "cancel")
    with path.open("rb"):
        assert window.save_library() is False

    assert window.isWindowModified()
    assert window.library.condition("design").label == "Edited"
    assert label_in(path) == "Design"
    assert strays(path) == [], "the half-written temporary file was cleaned up"


@windows_only
def test_retrying_asks_again_while_the_file_is_still_held(window, path, prompts, impatient):
    edit(window)
    prompts.will("locked", "retry", "retry", "cancel")
    with path.open("rb"):
        assert window.save_library() is False

    assert prompts.asked == ["locked", "locked", "locked"]


@not_root
def test_a_read_only_file_is_reported_as_locked(window, path, prompts):
    edit(window)
    os.chmod(path, stat.S_IREAD)
    prompts.will("locked", "cancel")
    try:
        assert window.save_library() is False
    finally:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)

    assert isinstance(prompts.args["locked"][0][0], SourceLockedError)
    assert "read-only" in prompts.args["locked"][0][0].reason


# --------------------------------------------------------------------------
# Batches save themselves
# --------------------------------------------------------------------------


def set_up_tiny_job(dialog):
    """Fill the batch screen in with two new conditions on a small mesh, clear of the fixture's own."""
    dialog.ui.spinIterations.setValue(5)
    dialog.ui.spinWorkers.setValue(1)
    dialog.ui.spinZFrom.setValue(-3.7)
    dialog.ui.spinZTo.setValue(-3.2)
    dialog.ui.spinZStep.setValue(0.5)
    dialog.ui.editBands.setPlainText("20 -> 10")
    dialog.ui.spinDirFrom.setValue(0.0)
    dialog.ui.spinDirTo.setValue(90.0)
    dialog.ui.spinDirStep.setValue(90.0)


def run_ended(dialog):
    """Whether a run has ended: by completing, or by crashing -- which leaves no outcome."""
    return dialog.outcome is not None or "The batch failed" in dialog.ui.lblProgress.text()


def tiny_batch(monkeypatch, qapp, observe=None, *, run=True, interrupt=None):
    """Make the modal batch screen run one small job to its end and report.

    ``exec`` blocks until a person closes the screen. This runs the same
    two-condition job the batch tests in ``test_app.py`` do, waits for the run
    to end, and calls ``observe(dialog)`` **while the screen is still open**,
    which is the moment the auto-save is promised to have happened by.

    Args:
        run: ``False`` to run nothing and only report that a run ended.
        interrupt: ``"_stop"`` or ``"_kill"`` to press that button once both
            conditions have been created, which is after the run has written
            something and long before it could have finished.
    """

    def exec_(self):
        if run:
            set_up_tiny_job(self)
            self._start()
            if interrupt is not None:
                assert pump(qapp, lambda: self.ui.progressOverall.value() >= 2), "the run never got going"
                getattr(self, interrupt)()
            assert pump(qapp, lambda: run_ended(self)), "the batch never finished"
            self._thread.wait(30_000)
        else:
            self.libraryChanged.emit()
        if observe is not None:
            observe(self)
        self.close()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(BatchDialog, "exec", exec_)


def crash_after_writing(monkeypatch):
    """Make the run die the way one can: after it has written something, by raising.

    The screen then gets ``failed`` instead of ``completed``: no outcome, and
    a working copy that has changed.
    """

    class Crashing(BatchRun):
        def run(self, progress=None):
            self._library.create_condition(z_origin=-3.7, condition_id="written-before-dying")
            raise RuntimeError("the disk went away")

    monkeypatch.setattr("pylot_bem.app.batch.BatchRun", Crashing)


def tree_result_ids(window):
    """The ids of the results the tree is showing."""
    ids = set()

    def walk(item):
        kind, node_id = item.data(0, Qt.ItemDataRole.UserRole)
        if kind == "result":
            ids.add(node_id)
        for i in range(item.childCount()):
            walk(item.child(i))

    for i in range(window.tree.topLevelItemCount()):
        walk(window.tree.topLevelItem(i))
    return ids


def results_in(path):
    with Library.open(path, read_only=True) as library:
        return len(library.results())


def conditions_in(path):
    with Library.open(path, read_only=True) as library:
        return len(library.conditions())


def test_a_batch_saves_the_library_when_the_run_ends_not_when_the_screen_closes(window, path, qapp, monkeypatch):
    seen = {}
    before = results_in(path)
    listed_before = tree_result_ids(window)

    def observe(dialog):
        seen["file"] = results_in(path)
        seen["modified"] = window.isWindowModified()
        seen["batch_worked_on"] = dialog._thread._path
        seen["beside"] = dialog._beside_library()
        seen["tree"] = tree_result_ids(window)
        seen["stored"] = set(dialog.outcome.results_stored)
        seen["outcome"] = dialog.outcome

    tiny_batch(monkeypatch, qapp, observe)

    window.run_batch()

    assert seen["file"] == before + 2, "the file had the results while the screen was still open"
    assert seen["modified"] is False
    assert len(seen["stored"]) == 2 and seen["tree"] == listed_before | seen["stored"], (
        "and the tree already listed them: the refresh is at the run's end, not when the screen closes"
    )
    assert seen["batch_worked_on"] == window.library.path != path, "the batch runs against the working copy"
    assert seen["beside"] == str(path.with_suffix(JOB_SUFFIX)), "and job files go beside the user's file"
    assert not window.isWindowModified()
    assert len(window.library.results()) == before + 2
    assert window.statusBar().currentMessage() == f"{summarise(seen['outcome'])} Saved automatically after the batch."
    assert strays(path) == []


def test_with_auto_save_off_a_batch_leaves_the_library_modified(window, path, qapp, monkeypatch):
    window.autosave_action.setChecked(False)
    before = results_in(path)
    seen = {}
    tiny_batch(monkeypatch, qapp, lambda dialog: seen.update(file=results_in(path)))

    window.run_batch()

    assert seen["file"] == before, "the file is not written to"
    assert window.isWindowModified()
    assert window.workspace.dirty
    assert len(window.library.results()) == before + 2
    message = window.statusBar().currentMessage()
    assert message.startswith("Finished after") and "Saved automatically" not in message


def test_a_run_that_wrote_nothing_saves_nothing(window, path, qapp, monkeypatch):
    """``libraryChanged`` fires at the end of every run, whether or not it wrote."""
    saved = []
    monkeypatch.setattr(window, "save_library", lambda: saved.append(True) or True)
    before = sha(path)
    tiny_batch(monkeypatch, qapp, run=False)

    window.run_batch()

    assert saved == []
    assert sha(path) == before
    assert not window.isWindowModified()


def test_an_auto_save_meets_a_changed_file_like_any_save(window, path, qapp, monkeypatch, prompts):
    prompts.will("conflict", "cancel")
    ours = {}

    def observe(dialog):
        ours["file"] = sha(path)

    real = BatchDialog._start

    def start(self):
        change_on_disk(path)  # while the screen is open
        ours["before"] = sha(path)
        real(self)

    monkeypatch.setattr(BatchDialog, "_start", start)
    tiny_batch(monkeypatch, qapp, observe)

    window.run_batch()

    assert prompts.asked == ["conflict"]
    assert ours["file"] == ours["before"], "not overwritten"
    assert window.isWindowModified()
    assert "Saved automatically" not in window.statusBar().currentMessage()


def test_a_batch_that_crashed_says_so_and_still_saves_what_it_wrote(window, path, qapp, monkeypatch):
    """A crashed run has no outcome, and the report used to be skipped for want of one."""
    crash_after_writing(monkeypatch)
    before = conditions_in(path)
    seen = {}
    tiny_batch(monkeypatch, qapp, lambda dialog: seen.update(outcome=dialog.outcome, file=conditions_in(path)))

    window.run_batch()

    assert seen["outcome"] is None
    assert seen["file"] == before + 1, "saved when the run ended, with the screen still open"
    assert window.statusBar().currentMessage() == "The batch failed. Saved automatically after the batch."
    assert not window.isWindowModified()


def test_a_batch_that_crashed_with_auto_save_off_still_says_so(window, path, qapp, monkeypatch):
    window.autosave_action.setChecked(False)
    crash_after_writing(monkeypatch)
    tiny_batch(monkeypatch, qapp)

    window.run_batch()

    assert window.statusBar().currentMessage() == "The batch failed."
    assert window.isWindowModified()


def test_a_second_run_that_crashes_does_not_show_the_first_runs_outcome(window, qapp, monkeypatch):
    """``outcome`` is about the run that last began, or the window would report the wrong one."""
    dialog = BatchDialog(window.library, (), window)
    set_up_tiny_job(dialog)
    first = object()
    dialog.outcome = first  # what an earlier, finished run would have left
    crash_after_writing(monkeypatch)

    dialog._start()

    assert dialog.outcome is None and dialog.runs_started == 1
    assert pump(qapp, lambda: "The batch failed" in dialog.ui.lblProgress.text()), "the run never crashed"
    dialog._thread.wait(30_000)
    assert dialog.outcome is None
    dialog.close()


@pytest.mark.parametrize(("button", "ended", "killed"), [("_stop", "Stopped early", False), ("_kill", "Killed", True)])
def test_a_batch_that_was_stopped_or_killed_says_how_it_ended_and_keeps_what_it_wrote(
    window, path, qapp, monkeypatch, button, ended, killed
):
    before = conditions_in(path)
    seen = {}
    tiny_batch(
        monkeypatch,
        qapp,
        lambda dialog: seen.update(outcome=dialog.outcome, file=conditions_in(path)),
        interrupt=button,
    )

    window.run_batch()

    outcome = seen["outcome"]
    assert outcome.stopped and outcome.killed is killed
    assert seen["file"] == before + 2, "both conditions were created before the button was pressed"
    message = window.statusBar().currentMessage()
    assert message == f"{summarise(outcome)} Saved automatically after the batch."
    assert message.startswith(ended)
    assert not window.isWindowModified()


def test_closing_the_batch_screen_over_a_running_batch_saves_what_it_wrote(window, path, qapp, monkeypatch):
    """The run is killed and waited for, and nothing tells the window it ended.

    Measured: ``libraryChanged`` does not fire while ``exec()`` is still
    running. The thread's report is queued to the interface thread and is
    delivered only when the event loop next runs, after ``run_batch`` has
    returned. So the window saves for itself, straight after ``exec()``.
    """
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Yes))
    heard = []
    real_after = MainWindow._after_batch
    monkeypatch.setattr(MainWindow, "_after_batch", lambda self: heard.append("after_batch") or real_after(self))
    saves = []
    real_save = Workspace.save
    monkeypatch.setattr(Workspace, "save", lambda self, **kwargs: saves.append(kwargs) or real_save(self, **kwargs))
    screens = []
    inside = {}

    def exec_(self):
        screens.append(self)
        set_up_tiny_job(self)
        self.show()  # a screen that was never shown is never sent a close event
        self._start()
        assert pump(qapp, lambda: self.ui.progressOverall.value() >= 2), "the run never got going"
        assert self.close()
        inside.update(running=self._running(), heard=list(heard), outcome=self.outcome)
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(BatchDialog, "exec", exec_)
    before = conditions_in(path)

    window.run_batch()  # and no event loop has run since exec() returned

    assert inside == {"running": False, "heard": [], "outcome": None}
    assert conditions_in(path) == before + 2, "what it wrote is in the file"
    assert not window.isWindowModified()
    message = "The batch was closed before it finished. Saved automatically after the batch."
    assert window.statusBar().currentMessage() == message
    assert len(saves) == 1

    # The killed run's own report turns up afterwards, on a screen nobody is
    # watching any more. It must not refresh the window, save again, or replace
    # the status text.
    assert pump(qapp, lambda: run_ended(screens[0]), timeout=30), "the killed run never reported"
    pump(qapp, lambda: False, timeout=0.3)
    assert heard == []
    assert len(saves) == 1
    assert window.statusBar().currentMessage() == message


def test_closing_the_batch_screen_over_a_running_batch_with_auto_save_off_leaves_it_modified(
    window, path, qapp, monkeypatch
):
    window.autosave_action.setChecked(False)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Yes))
    screens = []

    def exec_(self):
        screens.append(self)
        set_up_tiny_job(self)
        self.show()
        self._start()
        assert pump(qapp, lambda: self.ui.progressOverall.value() >= 2), "the run never got going"
        self.close()
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(BatchDialog, "exec", exec_)
    before = conditions_in(path)

    window.run_batch()

    assert conditions_in(path) == before
    assert window.isWindowModified()
    assert window.statusBar().currentMessage() == "The batch was closed before it finished."
    assert pump(qapp, lambda: run_ended(screens[0]), timeout=30)


def scripted_questions(monkeypatch, *answers):
    """Answer the ``QMessageBox.question`` the batch screen asks over a running batch.

    Returns the list the arguments of every question asked are appended to.
    ``"yes"`` and ``"no"`` are taken in turn; a question nobody scripted is
    recorded and answered No, so a surprise never kills a run -- the test then
    fails on what was asked, not on a run that was quietly ended.
    """
    script = [
        QMessageBox.StandardButton.Yes if answer == "yes" else QMessageBox.StandardButton.No for answer in answers
    ]
    asked = []

    def question(*args, **kwargs):
        asked.append(args)
        return script.pop(0) if script else QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", staticmethod(question))
    return asked


def count_kills(monkeypatch):
    """Record each time a running batch is told to kill its workers, and still do it."""
    kills = []
    real = BatchThread.kill
    monkeypatch.setattr(BatchThread, "kill", lambda self: kills.append(True) or real(self))
    return kills


def reap(dialog):
    """Leave no run going, whatever the test found.

    A ``QThread`` destroyed while it is running aborts the whole process, so
    a test that shows a screen letting a run outlive it has to fail as a test
    rather than take the others with it.
    """
    thread = dialog._thread
    if thread is not None and thread.isRunning():
        thread.kill()
        thread.wait(30_000)


def escape_over_a_running_batch(qapp, screens, inside, heard):
    """A stand-in for ``exec`` that starts a run and presses Escape once it is under way.

    Presses it the way a person does -- a key event sent to the screen, not a
    call to ``reject()`` -- because the route from the key to the guard is the
    thing under test. What the screen looks like straight afterwards goes in
    ``inside``, before anything gets a chance to tidy up.
    """

    def exec_(self):
        screens.append(self)
        set_up_tiny_job(self)
        self.show()
        self._start()
        try:
            assert pump(qapp, lambda: self.ui.progressOverall.value() >= 2), "the run never got going"
            QTest.keyClick(self, Qt.Key.Key_Escape)
            inside.update(running=self._running(), heard=list(heard), outcome=self.outcome, visible=self.isVisible())
        finally:
            reap(self)
        return QDialog.DialogCode.Rejected

    return exec_


def test_escape_over_a_running_batch_asks_first_and_on_no_leaves_the_run_alone(window, qapp, monkeypatch):
    """Escape reaches a dialog as ``reject()``, which hides it without a close event.

    So the question that guards the Close button and the window's close box
    was never asked, and the screen went while its worker carried on writing
    to the library with nothing left to wait for it.
    """
    asked = scripted_questions(monkeypatch, "no", "no", "yes")
    kills = count_kills(monkeypatch)
    seen = {}

    def exec_(self):
        set_up_tiny_job(self)
        self.show()
        self._start()
        try:
            assert pump(qapp, lambda: self.ui.progressOverall.value() >= 2), "the run never got going"
            QTest.keyClick(self, Qt.Key.Key_Escape)
            pump(qapp, lambda: False, timeout=0.3)  # long enough for a wrong answer to have been acted on
            seen.update(
                asked=list(asked),
                visible=self.isVisible(),
                running=self._running(),
                ended=run_ended(self),
                killed=self._thread._run.killed,
                kills=list(kills),
            )

            # The Close button puts the very same question, and No is as final there.
            QTest.mouseClick(self.ui.btnClose, Qt.MouseButton.LeftButton)
            seen.update(both=list(asked), visible_after_close_button=self.isVisible(), running_after=self._running())

            # And the screen is not wedged: Escape and Yes still end it.
            QTest.keyClick(self, Qt.Key.Key_Escape)
            seen.update(
                kills_after_yes=list(kills),
                visible_after_yes=self.isVisible(),
                running_after_yes=self._running(),
            )
        finally:
            reap(self)
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(BatchDialog, "exec", exec_)

    window.run_batch()

    assert [args[1] for args in seen["asked"]] == ["A batch is running"], "Escape asked, once"
    assert "Close anyway?" in seen["asked"][0][2]
    assert seen["asked"][0][3] == QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    assert seen["asked"][0][4] == QMessageBox.StandardButton.No, "and No is what Enter would say"
    assert seen["visible"] and seen["running"] and not seen["ended"], "No: the screen stays, the run goes on"
    assert seen["killed"] is False and seen["kills"] == [], "nothing was killed"

    assert [args[1] for args in seen["both"]] == ["A batch is running"] * 2
    assert seen["both"][1][1:] == seen["both"][0][1:], "the Close button asks exactly what Escape did"
    assert seen["visible_after_close_button"] and seen["running_after"]

    assert seen["kills_after_yes"] == [True], "Yes killed the run, once"
    assert not seen["visible_after_yes"] and not seen["running_after_yes"]
    assert len(asked) == 3


def test_escape_over_a_running_batch_on_yes_kills_it_and_the_window_saves_what_it_wrote(
    window, path, qapp, monkeypatch
):
    """Escape and Yes are the Close button and Yes: the window sees a run cut short.

    Without the guard the screen went with the run still going, ``exec()``
    returned, and ``run_batch`` judged a run that was still writing.
    """
    asked = scripted_questions(monkeypatch, "yes")
    kills = count_kills(monkeypatch)
    heard = []
    real_after = MainWindow._after_batch
    monkeypatch.setattr(MainWindow, "_after_batch", lambda self: heard.append("after_batch") or real_after(self))
    saves = []
    real_save = Workspace.save
    monkeypatch.setattr(Workspace, "save", lambda self, **kwargs: saves.append(kwargs) or real_save(self, **kwargs))
    screens = []
    inside = {}
    monkeypatch.setattr(BatchDialog, "exec", escape_over_a_running_batch(qapp, screens, inside, heard))
    before = conditions_in(path)

    window.run_batch()  # and no event loop has run since exec() returned

    assert [args[1] for args in asked] == ["A batch is running"], "Escape asked, once"
    assert kills == [True]
    assert inside == {"running": False, "heard": [], "outcome": None, "visible": False}
    assert conditions_in(path) == before + 2, "what it wrote is in the file"
    assert not window.isWindowModified()
    message = "The batch was closed before it finished. Saved automatically after the batch."
    assert window.statusBar().currentMessage() == message
    assert len(saves) == 1

    # The killed run's own report turns up afterwards, on a screen nobody is
    # watching any more. It must not refresh the window, save again, or replace
    # the status text.
    assert pump(qapp, lambda: run_ended(screens[0]), timeout=30), "the killed run never reported"
    pump(qapp, lambda: False, timeout=0.3)
    assert heard == []
    assert len(saves) == 1
    assert window.statusBar().currentMessage() == message


def test_escape_over_a_running_batch_with_auto_save_off_leaves_it_modified(window, path, qapp, monkeypatch):
    window.autosave_action.setChecked(False)
    asked = scripted_questions(monkeypatch, "yes")
    screens = []
    inside = {}
    monkeypatch.setattr(BatchDialog, "exec", escape_over_a_running_batch(qapp, screens, inside, []))
    before = conditions_in(path)

    window.run_batch()

    assert [args[1] for args in asked] == ["A batch is running"]
    assert inside["running"] is False and inside["visible"] is False
    assert conditions_in(path) == before
    assert window.isWindowModified()
    assert window.statusBar().currentMessage() == "The batch was closed before it finished."
    assert pump(qapp, lambda: run_ended(screens[0]), timeout=30)


def test_escape_on_a_batch_screen_that_never_started_closes_it_without_a_question(window, monkeypatch):
    """The guard is for a running batch only. It must not make the screen harder to leave."""
    asked = scripted_questions(monkeypatch)
    dialog = BatchDialog(window.library, (), window)
    dialog.show()

    QTest.keyClick(dialog, Qt.Key.Key_Escape)

    assert asked == []
    assert not dialog.isVisible()
    assert dialog.runs_started == 0


def test_escape_on_a_batch_screen_whose_run_has_ended_closes_it_without_a_question(window, qapp, monkeypatch):
    """A thread that exists but has finished is not a batch running."""
    asked = scripted_questions(monkeypatch)
    crash_after_writing(monkeypatch)  # ends at once, and is the quickest run there is
    dialog = BatchDialog(window.library, (), window)
    set_up_tiny_job(dialog)
    dialog.show()
    dialog._start()
    try:
        assert pump(qapp, lambda: run_ended(dialog)), "the run never ended"
        dialog._thread.wait(30_000)
        assert not dialog._running() and dialog._thread is not None

        QTest.keyClick(dialog, Qt.Key.Key_Escape)

        assert asked == []
        assert not dialog.isVisible()
    finally:
        reap(dialog)


def test_a_batch_screen_closed_without_starting_anything_says_nothing_about_a_batch(window, path, monkeypatch):
    monkeypatch.setattr(BatchDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    saves = []
    monkeypatch.setattr(window, "save_library", lambda: saves.append(True) or True)

    window.run_batch()

    assert saves == []
    assert "batch" not in window.statusBar().currentMessage().lower()
    assert "conditions" in window.statusBar().currentMessage(), "the library's counts, as after any refresh"


def test_auto_save_is_a_persisted_setting_on_by_default(qapp, isolated_settings, work_root, tmp_path):
    first = make_window(isolated_settings, work_root)
    assert first.autosave_action.isCheckable() and first.autosave_action.isChecked()

    first.autosave_action.setChecked(False)
    first.close()

    second = make_window(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat), work_root)
    assert not second.autosave_action.isChecked()
    second.autosave_action.setChecked(True)
    second.close()
    third = make_window(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat), work_root)
    assert third.autosave_action.isChecked()
    third.close()


def test_job_files_are_offered_beside_the_users_file_not_the_working_copy(window, path):
    dialog = BatchDialog(window.library, (), window, source_path=window.source_path)
    assert dialog._beside_library() == str(path.with_suffix(JOB_SUFFIX))
    dialog.close()

    plain = BatchDialog(window.library, (), window)
    assert plain._beside_library() == str(window.library.path.with_suffix(JOB_SUFFIX)), "and without one, as before"
    plain.close()


def test_the_batch_thread_still_gets_the_working_copy(window, path, qapp, monkeypatch):
    got = []
    real = BatchThread.__init__

    def init(self, target, *args, **kwargs):
        got.append(target)
        real(self, target, *args, **kwargs)

    monkeypatch.setattr(BatchThread, "__init__", init)
    tiny_batch(monkeypatch, qapp)

    window.run_batch()

    assert got == [window.library.path] and got[0] != path


# --------------------------------------------------------------------------
# Polling: the asterisk, and the crash-recovery record
# --------------------------------------------------------------------------


def test_the_poll_sees_a_write_made_by_another_connection_on_another_thread(
    qapp, path, isolated_settings, work_root, monkeypatch, prompts
):
    """The batch case: nothing in the window is touched, and a thread commits."""
    monkeypatch.setattr(window_module, "DIRTY_POLL_MS", 30)
    main = make_window(isolated_settings, work_root, open_path=path)
    assert not main.isWindowModified()
    working = main.library.path

    def write():
        with Pylot.open(working) as library:
            library.set_condition_label("design", "From a thread")

    writer = threading.Thread(target=write)
    writer.start()
    assert pump(qapp, main.isWindowModified, timeout=20), "the timer never noticed"
    writer.join(timeout=30)
    assert not writer.is_alive()

    record = json.loads((main.workspace.work_dir / "session.json").read_text(encoding="utf-8"))
    assert record["dirty"] is True, "and polling is what wrote it down for crash recovery"
    prompts.will("save", "discard")
    main.close()


def test_the_poll_keeps_running_inside_a_modal_dialog(
    qapp, path, isolated_settings, work_root, monkeypatch, prompts
):
    monkeypatch.setattr(window_module, "DIRTY_POLL_MS", 30)
    main = make_window(isolated_settings, work_root, open_path=path)
    working = main.library.path

    def write():
        with Pylot.open(working) as library:
            library.set_condition_label("design", "From a thread")

    modal = QDialog(main)
    watcher = QTimer(modal)
    watcher.timeout.connect(lambda: modal.accept() if main.isWindowModified() else None)
    watcher.start(20)
    giving_up = QTimer(modal)
    giving_up.setSingleShot(True)
    giving_up.timeout.connect(modal.reject)
    giving_up.start(20_000)
    writers = []

    def start_writer():
        writers.append(threading.Thread(target=write))
        writers[-1].start()

    QTimer.singleShot(0, start_writer)

    modal.exec()

    for writer in writers:
        writer.join(timeout=30)
    assert len(writers) == 1 and not writers[0].is_alive()
    assert main.isWindowModified(), "a batch runs inside exactly this kind of event loop"
    prompts.will("save", "discard")
    main.close()


def test_the_timer_runs_while_a_library_is_open_and_stops_when_it_is_not(window, prompts):
    assert window._dirty_timer.isActive()
    assert window._dirty_timer.interval() == window_module.DIRTY_POLL_MS == 2000

    window.close_library()

    assert not window._dirty_timer.isActive()


def test_the_timer_does_not_fire_for_a_workspace_that_is_closed(window):
    window.workspace.close()

    window._sync_document_state()  # must not touch the closed database

    assert not window._dirty_timer.isActive()


# --------------------------------------------------------------------------
# Crash recovery
# --------------------------------------------------------------------------

CRASHING_SESSION = """
import sys, time
from pylot_bem.workspace import Workspace

workspace = Workspace.open(sys.argv[1], work_root=sys.argv[2])
workspace.library.set_condition_label("design", "Left behind")
assert workspace.dirty  # the poll that writes it down
print(workspace.work_dir.name, flush=True)
time.sleep(600)
"""


@pytest.fixture(scope="module")
def crashed_session(library_path, tmp_path_factory):
    """What a pylot that was killed mid-edit leaves: a real process, really killed."""
    root = tmp_path_factory.mktemp("crashed")
    process = subprocess.Popen(
        [sys.executable, "-c", CRASHING_SESSION, str(library_path), str(root)],
        stdout=subprocess.PIPE,
        text=True,
    )
    watchdog = threading.Timer(180, process.kill)  # a helper that hangs must not hang the suite
    watchdog.start()
    try:
        name = process.stdout.readline().strip()
        assert name, "the session that was to crash never came up"
    finally:
        watchdog.cancel()
        process.kill()
        process.wait()
        process.stdout.close()
    return root / name


@pytest.fixture
def dead_session(crashed_session, work_root, path):
    """The crashed session's folder, in this test's work root, aimed at this test's copy of the file."""
    target = work_root / crashed_session.name
    shutil.copytree(crashed_session, target)
    record = json.loads((target / "session.json").read_text(encoding="utf-8"))
    record["source"] = str(path)
    (target / "session.json").write_text(json.dumps(record), encoding="utf-8")
    return target


def test_a_crashed_session_is_offered_and_recovered_with_its_unsaved_changes(
    empty_window, dead_session, path, prompts
):
    prompts.will("recover", "recover")

    empty_window.offer_recovery()

    assert prompts.asked == ["recover"]
    recovery = prompts.args["recover"][0][0]
    assert isinstance(recovery, Recovery) and recovery.source == path
    assert empty_window.source_path == path
    assert empty_window.library.condition("design").label == "Left behind"
    assert empty_window.isWindowModified(), "recovered work is unsaved work"
    assert label_in(path) == "Design", "and the file has not been touched"
    assert "Recovered" in empty_window.statusBar().currentMessage()

    assert empty_window.save_library()
    assert label_in(path) == "Left behind"


def test_discarding_a_crashed_session_deletes_it(empty_window, dead_session, path, prompts):
    prompts.will("recover", "discard")

    empty_window.offer_recovery()

    assert not dead_session.exists()
    assert empty_window.library is None
    assert Workspace.recoverable(empty_window._work_root) == []


def test_discarding_a_session_another_pylot_has_taken_over_deletes_nothing_and_says_so(
    empty_window, dead_session, prompts, monkeypatch
):
    """The list is made before the question is asked, and a second pylot can start in between."""
    stale = Workspace.recoverable(empty_window._work_root)
    assert [r.work_dir for r in stale] == [dead_session]
    shown = []
    monkeypatch.setattr(MainWindow, "_problem", lambda self, title, exc: shown.append((title, str(exc))))
    prompts.will("recover", "discard")

    with Workspace.recover(stale[0]) as taken:  # the other pylot, after the list was made
        monkeypatch.setattr(Workspace, "recoverable", staticmethod(lambda root=None: stale))

        empty_window.offer_recovery()  # must not raise

        assert len(shown) == 1 and shown[0][0] == "Could not discard the unsaved changes"
        assert "another running pylot" in shown[0][1] and "Nothing was deleted" in shown[0][1]
        assert dead_session.exists(), "somebody is looking at it"
        assert taken.library.condition("design").label == "Left behind"
        assert empty_window.library is None


def test_a_discard_that_could_not_happen_does_not_stop_the_offer(
    empty_window, crashed_session, work_root, path, prompts, monkeypatch
):
    folders = []
    for name in ("a" * 32, "b" * 32):
        target = work_root / name
        shutil.copytree(crashed_session, target)
        record = json.loads((target / "session.json").read_text(encoding="utf-8"))
        record["source"] = str(path)
        (target / "session.json").write_text(json.dumps(record), encoding="utf-8")
        folders.append(target)
    stale = Workspace.recoverable(empty_window._work_root)
    shown = []
    monkeypatch.setattr(MainWindow, "_problem", lambda self, title, exc: shown.append(title))
    prompts.will("recover", "discard", "recover")

    with Workspace.recover(stale[0]):
        monkeypatch.setattr(Workspace, "recoverable", staticmethod(lambda root=None: stale))

        empty_window.offer_recovery()

        assert prompts.asked == ["recover", "recover"]
        assert shown == ["Could not discard the unsaved changes"]
        assert empty_window.workspace.work_dir == folders[1], "and the next session was offered and recovered"
        assert folders[0].exists()


def test_putting_a_crashed_session_off_leaves_it_for_next_time(empty_window, dead_session, prompts):
    prompts.will("recover", "later")

    empty_window.offer_recovery()

    assert dead_session.exists() and empty_window.library is None
    assert [r.work_dir for r in Workspace.recoverable(empty_window._work_root)] == [dead_session]


def test_no_crashed_session_means_no_question(empty_window, prompts):
    empty_window.offer_recovery()

    assert prompts.asked == []


def test_recovering_one_of_several_says_how_many_remain_and_stops(
    empty_window, crashed_session, work_root, path, prompts
):
    folders = []
    # Named the way a session folder is (32 hex characters): nothing else in the
    # work root is looked at, so shorter names would not be found at all.
    for name in ("a" * 32, "b" * 32, "c" * 32):
        target = work_root / name
        shutil.copytree(crashed_session, target)
        record = json.loads((target / "session.json").read_text(encoding="utf-8"))
        record["source"] = str(path)
        (target / "session.json").write_text(json.dumps(record), encoding="utf-8")
        folders.append(target)
    prompts.will("recover", "later", "recover")

    empty_window.offer_recovery()

    assert prompts.asked == ["recover", "recover"], "the third was never asked about"
    assert empty_window.workspace.work_dir == folders[1]
    assert "2 more" in empty_window.statusBar().currentMessage()
    assert folders[0].exists() and folders[2].exists()


def test_a_session_that_cannot_be_recovered_is_reported_and_kept(
    empty_window, dead_session, prompts, problems
):
    for leftover in dead_session.iterdir():
        if leftover.name.endswith(("-wal", "-shm")):
            leftover.unlink()
        elif leftover.suffix == ".pylot":
            leftover.write_bytes(b"this is not a database")
    prompts.will("recover", "recover")

    empty_window.offer_recovery()

    assert problems and problems[0][0] == "Could not recover the library"
    assert empty_window.library is None
    assert dead_session.exists(), "left where a person can still salvage it"


def test_recovering_over_unsaved_work_asks_about_that_first(window, dead_session, prompts):
    edit(window)
    prompts.will("recover", "recover")
    prompts.will("save", "cancel")
    workspace = window.workspace

    window.offer_recovery()

    assert prompts.asked == ["recover", "save"]
    assert window.workspace is workspace
    assert len(Workspace.recoverable(window._work_root)) == 1, "still there to be recovered later"


def test_the_application_offers_recovery_before_it_opens_the_file_it_was_given(
    qapp, path, isolated_settings, work_root, monkeypatch
):
    order = []
    made = []

    class Recording(MainWindow):
        def __init__(self):
            super().__init__(settings=isolated_settings, work_root=work_root)
            made.append(self)

        def offer_recovery(self):
            order.append("recovery")

        def open_path(self, given):
            order.append(("open", given))

    monkeypatch.setattr(window_module, "MainWindow", Recording)
    monkeypatch.setattr(QApplication, "exec", staticmethod(lambda: 0))

    assert pylot_bem.app.run(str(path)) == 0

    assert order == ["recovery", ("open", str(path))]
    made[0].close()


# --------------------------------------------------------------------------
# Logoff and shutdown
# --------------------------------------------------------------------------


class FakeSessionManager:
    """Enough of a ``QSessionManager`` to be asked to commit."""

    def __init__(self, *, interactive=True):
        self.interactive = interactive
        self.cancelled = False
        self.asked_to_interact = 0

    def allowsInteraction(self):
        self.asked_to_interact += 1
        return self.interactive

    def cancel(self):
        self.cancelled = True


def test_logoff_over_unsaved_changes_can_be_cancelled(window, path, prompts):
    edit(window)
    manager = FakeSessionManager()
    prompts.will("save", "cancel")

    window.commit_data(manager)

    assert prompts.asked == ["save"] and manager.cancelled
    assert window.isWindowModified() and label_in(path) == "Design"


def test_logoff_over_unsaved_changes_can_save_them(window, path, prompts):
    edit(window)
    manager = FakeSessionManager()
    prompts.will("save", "save")

    window.commit_data(manager)

    assert not manager.cancelled and label_in(path) == "Edited"


def test_logoff_can_discard_them(window, path, prompts):
    edit(window)
    manager = FakeSessionManager()
    prompts.will("save", "discard")
    folder = window.workspace.work_dir

    window.commit_data(manager)

    assert not manager.cancelled and label_in(path) == "Design"
    assert window.workspace is None and not folder.exists(), (
        "the process is about to end without a close event; a copy left dirty would be offered back as lost work"
    )


def test_logoff_that_forbids_questions_asks_none_and_leaves_the_copy_recoverable(window, path, prompts):
    edit(window)
    manager = FakeSessionManager(interactive=False)

    window.commit_data(manager)

    assert prompts.asked == [] and not manager.cancelled
    assert window.isWindowModified()
    assert window.workspace.working_path.is_file()


def test_logoff_with_nothing_unsaved_asks_nothing(window, prompts):
    manager = FakeSessionManager()

    window.commit_data(manager)

    assert prompts.asked == [] and not manager.cancelled


def test_the_window_listens_for_logoff_only_while_it_exists(qapp, isolated_settings, work_root):
    signal = "2commitDataRequest(QSessionManager&)"
    baseline = QGuiApplication.instance().receivers(signal)

    main = make_window(isolated_settings, work_root)
    assert QGuiApplication.instance().receivers(signal) == baseline + 1

    main.close()
    assert QGuiApplication.instance().receivers(signal) == baseline


def test_a_cancelled_close_still_listens_for_logoff(window, prompts):
    signal = "2commitDataRequest(QSessionManager&)"
    listening = QGuiApplication.instance().receivers(signal)
    edit(window)
    prompts.will("save", "cancel")

    window.close()

    assert QGuiApplication.instance().receivers(signal) == listening


# --------------------------------------------------------------------------
# Views that outlive the library
# --------------------------------------------------------------------------


def test_closing_a_library_lets_every_view_go_of_it(window):
    """Each of these held the closed library, and a control on each would query it."""
    window.tree.select_ids(["run"])
    window.match_tab.rank()
    window.validation_tab.run()

    assert window.inspect_tab._library is window.library and window.inspect_tab._result_ids == ["run"]
    assert window.match_tab._library is not None and window.validation_tab._library is not None

    assert window.close_library()

    assert window.inspect_tab._library is None and window.inspect_tab._result_ids == []
    assert window.match_tab._library is None and window.match_tab.table.rowCount() == 0
    assert window.validation_tab._library is None and window.validation_tab.table.rowCount() == 0
    assert window.library_pane._library is None
    assert window.results_tab.table.rowCount() == 0 and window.databases_tab.table.rowCount() == 0


def test_a_control_on_a_stale_view_no_longer_reaches_a_closed_library(window):
    """The failure this guards: rank / replot / reset probes against a closed database."""
    window.tree.select_ids(["run"])
    window.match_tab.rank()
    window.library_pane.display(window.library)
    window.validation_tab.run()

    window.close_library()

    window.match_tab.rank()  # raised "closed database" before
    window.inspect_tab.replot()  # so did this, at any change of the plot controls
    window.inspect_tab.quantity.setCurrentIndex(1)
    window.library_pane._reset_probes()
    assert window.validation_tab.run() == []
    assert "could not complete" not in window.validation_tab.summary.text().lower()
    assert window.match_tab.table.rowCount() == 0


def test_replacing_a_library_lets_the_views_go_of_the_old_one(window, other):
    old = window.library
    window.tree.select_ids(["run"])
    window.match_tab.rank()
    assert window.inspect_tab._library is old
    window.library_pane.ui.lblHealth.setText("3 errors -- from the old library")

    window.open_path(other)

    assert window.library is not old
    assert window.match_tab._library is window.library, "refreshed onto the new one"
    assert window.inspect_tab._library is None
    assert "old library" not in window.library_pane.ui.lblHealth.text()
    window.inspect_tab.replot()


def test_reverting_lets_the_views_go_of_the_old_copy(window, prompts):
    old = window.library
    edit(window)
    window.tree.select_ids(["run"])
    assert window.inspect_tab._library is old
    prompts.will("revert", True)

    window.revert_library()

    assert window.inspect_tab._library is None
    window.inspect_tab.replot()


# --------------------------------------------------------------------------
# The questions themselves: wording, default button, and Escape
# --------------------------------------------------------------------------


def ask(window, name, *args, press=None, key=None):
    """Put one of the window's real questions up, answer it from inside its own event loop, and say what it looked like.

    Returns ``(answer, seen)``. What was on the box is recorded rather than
    asserted in the callback, because an exception in a Qt callback is
    swallowed -- and a question nobody can answer would hang the suite.

    Args:
        press: The text of the button to click, or a ``QMessageBox.StandardButton``.
        key: A key to send to the box instead: Enter for its default, Escape.
    """
    seen = {}

    def respond():
        box = QApplication.activeModalWidget()
        if not isinstance(box, QMessageBox):
            QTimer.singleShot(20, respond)
            return
        seen["text"] = box.text()
        seen["detail"] = box.informativeText()
        seen["buttons"] = [b.text().replace("&", "") for b in box.buttons()]
        seen["default"] = box.defaultButton().text().replace("&", "") if box.defaultButton() else None
        seen["parent"] = box.parent()
        if key is not None:
            QTest.keyClick(box, key)
        elif isinstance(press, QMessageBox.StandardButton):
            box.button(press).click()
        else:
            match = [b for b in box.buttons() if b.text().replace("&", "") == press]
            (match[0] if match else box.buttons()[-1]).click()

    QTimer.singleShot(20, respond)
    return REAL_QUESTIONS[name](window, *args), seen


def test_the_save_question_offers_save_discard_and_cancel_and_defaults_to_save(window):
    answer, seen = ask(window, "_ask_save", key=Qt.Key.Key_Return)
    assert answer == "save"
    assert "library.pylot" in seen["text"] and "lost" in seen["detail"]
    assert seen["parent"] is window
    assert len(seen["buttons"]) == 3 and "Cancel" in seen["buttons"]

    assert ask(window, "_ask_save", press=QMessageBox.StandardButton.Discard)[0] == "discard"
    assert ask(window, "_ask_save", press=QMessageBox.StandardButton.Cancel)[0] == "cancel"
    assert ask(window, "_ask_save", key=Qt.Key.Key_Escape)[0] == "cancel"


def test_the_conflict_question_defaults_to_cancel(window, path):
    error = SourceChangedError(path)

    answer, seen = ask(window, "_ask_conflict", error, key=Qt.Key.Key_Return)
    assert answer == "cancel" and seen["default"] == "Cancel"
    assert "changed by someone else" in seen["text"] and str(path) in seen["detail"]
    assert set(seen["buttons"]) == {"Overwrite", "Save As…", "Cancel"}  # laid out per platform

    assert ask(window, "_ask_conflict", error, press="Overwrite")[0] == "overwrite"
    assert ask(window, "_ask_conflict", error, press="Save As…")[0] == "save_as"
    assert ask(window, "_ask_conflict", error, key=Qt.Key.Key_Escape)[0] == "cancel"


def test_the_locked_question_shows_the_reason_and_offers_retry_save_as_and_cancel(window, path):
    error = SourceLockedError(path, "is in use by another program, so it cannot be replaced")

    answer, seen = ask(window, "_ask_locked", error, key=Qt.Key.Key_Return)
    assert answer == "retry"
    assert set(seen["buttons"]) == {"Retry", "Save As…", "Cancel"}
    assert error.reason in seen["detail"]
    assert "—" in seen["detail"] and " -- " not in seen["detail"], "punctuated like the rest of the interface"

    assert ask(window, "_ask_locked", error, press="Save As…")[0] == "save_as"
    assert ask(window, "_ask_locked", error, press="Cancel")[0] == "cancel"
    assert ask(window, "_ask_locked", error, key=Qt.Key.Key_Escape)[0] == "cancel"


def test_the_recovery_question_defaults_to_recover_and_escape_means_later(window, path, tmp_path):
    recovery = Recovery(tmp_path / "dead", path, tmp_path / "dead" / "library.pylot", datetime.now(UTC))

    answer, seen = ask(window, "_ask_recover", recovery, key=Qt.Key.Key_Return)
    assert answer == "recover"
    assert set(seen["buttons"]) == {"Recover", "Discard", "Later"} and "library.pylot" in seen["text"]

    assert ask(window, "_ask_recover", recovery, press="Discard")[0] == "discard"
    assert ask(window, "_ask_recover", recovery, key=Qt.Key.Key_Escape)[0] == "later"
    unknown = Recovery(tmp_path / "dead", None, tmp_path / "dead" / "x.pylot", None)
    assert ask(window, "_ask_recover", unknown, press="Later")[0] == "later"


def test_the_replace_question_names_the_file_and_defaults_to_no(window, path):
    answer, seen = ask(window, "_ask_replace", path, key=Qt.Key.Key_Return)
    assert answer is False and seen["default"] == "No"
    assert "library.pylot" in seen["text"] and str(path) in seen["detail"]
    assert set(seen["buttons"]) == {"Yes", "No"}

    assert ask(window, "_ask_replace", path, press="Yes")[0] is True
    assert ask(window, "_ask_replace", path, press="No")[0] is False
    assert ask(window, "_ask_replace", path, key=Qt.Key.Key_Escape)[0] is False


def test_the_revert_question_defaults_to_no(window):
    answer, seen = ask(window, "_ask_revert", key=Qt.Key.Key_Return)
    assert answer is False and "library.pylot" in seen["text"]

    assert ask(window, "_ask_revert", press="Yes")[0] is True
    assert ask(window, "_ask_revert", key=Qt.Key.Key_Escape)[0] is False


def test_a_question_asked_over_a_modal_screen_belongs_to_that_screen(window):
    modal = QDialog(window)
    seen = []

    def probe():
        try:
            seen.append(window._dialog_parent())
        finally:
            modal.accept()

    QTimer.singleShot(0, probe)
    modal.exec()

    assert seen == [modal], "a box parented to the window would sit behind the screen it interrupts"
    assert window._dialog_parent() is window
