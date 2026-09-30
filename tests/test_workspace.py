"""The editor model: a library opened as a private copy and saved back atomically.

``Workspace`` is what lets the application behave like a text editor without
ever letting SQLite near the file a person chose. These tests drive the
Qt-free core the way the window and the batch screen do -- a real library, real
files in real folders, real threads committing to the working copy -- and
assert on the *files*: what is in the folder, what the bytes are, what the
header says. A mock would agree with whatever the code does.

The failure modes are the point. Most tests here are about something going
wrong (the file changed underneath, the file is locked, the process died) and
about what is *not* lost when it does: the original is either the old file or
the whole new one, the workspace still holds every edit, and a second attempt
works.

Windows is the platform where these files are hard to keep safe: a file cannot
be replaced while anything holds it open, and a test that keeps a handle open
is the only honest way to exercise that. Those tests are marked, and the rest
run everywhere.
"""

import hashlib
import json
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
import threading
import time
import uuid
from contextlib import closing, contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from hull import BOX_FACES, BOX_VERTICES, TANKER_STL
from pylot_db.storage import Library, LibraryError

import pylot_bem
from pylot_bem import workspace as workspace_module
from pylot_bem.api import Pylot
from pylot_bem.workspace import (
    WORK_DIR_ENV,
    Fingerprint,
    Recovery,
    SourceChangedError,
    SourceLockedError,
    Stamp,
    Workspace,
    WorkspaceError,
    default_work_root,
)

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="a file is only locked by an open handle on Windows")
not_root = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root can write to a read-only file"
)

ROLLBACK = b"\x01\x01"
WAL = b"\x02\x02"


# -- material ----------------------------------------------------------------------------


def make_box(path: Path) -> Path:
    """A boxboat library, closed: an ordinary single file in rollback mode."""
    Pylot.create(
        path,
        vessel_name="Boxboat",
        origin_description="stern, centerline, keel",
        vertices=BOX_VERTICES,
        faces=BOX_FACES,
        is_xz_symmetric=True,
    ).close()
    return path


@pytest.fixture(scope="module")
def template(tmp_path_factory) -> Path:
    """One library, built once and copied for every test that needs a file."""
    return make_box(tmp_path_factory.mktemp("template") / "boat.pylot")


@pytest.fixture
def folder(tmp_path) -> Path:
    """The folder the user's library lives in -- the one a sync client watches."""
    path = tmp_path / "docs"
    path.mkdir()
    return path


@pytest.fixture
def original(template, folder) -> Path:
    """The user's file: a fresh copy, so nothing a test does reaches another."""
    path = folder / "boat.pylot"
    shutil.copyfile(template, path)
    return path


@pytest.fixture
def work_root(tmp_path) -> Path:
    return tmp_path / "work"


def make_legacy(template: Path, build: Path, folder: Path, *, condition_id: str = "old") -> Path:
    """A library as an older version left it: WAL header and a live ``-wal``.

    ``condition_id`` is committed to the ``-wal`` and never reaches the main
    file. The pair is copied while the writers are still open, which is exactly
    what a crash, or a sync client uploading a library that is open, leaves
    behind. Reading the main file alone gives a library without the condition.
    """
    build.mkdir()
    source = build / "boat.pylot"
    shutil.copyfile(template, source)
    keeper = sqlite3.connect(source)  # keeps the last-connection checkpoint from ever running
    try:
        keeper.execute("PRAGMA journal_mode = WAL")
        with Pylot.open(source) as writer:
            writer.create_condition(z_origin=-4.0, condition_id=condition_id)
            shutil.copyfile(source, folder / "boat.pylot")
            shutil.copyfile(source.with_name("boat.pylot-wal"), folder / "boat.pylot-wal")
    finally:
        keeper.close()
    return folder / "boat.pylot"


@pytest.fixture
def legacy(template, tmp_path, folder) -> Path:
    path = make_legacy(template, tmp_path / "build", folder)
    assert header(path) == WAL
    assert path.with_name("boat.pylot-wal").stat().st_size > 0
    assert main_file_conditions(path) == []  # the row really is only in the -wal
    return path


def main_file_conditions(path: Path) -> list[str]:
    """Condition ids in the main file alone, ignoring any ``-wal`` beside it."""
    uri = f"{path.absolute().as_uri()}?mode=ro&immutable=1"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        return [row[0] for row in connection.execute("SELECT id FROM condition ORDER BY id")]


def make_mismatched(template: Path, build: Path, folder: Path) -> Path:
    """A main file and a ``-wal`` that were never a pair, as a sync client can leave them.

    The main file is the library from before the first checkpoint; the ``-wal``
    is the log from after the second, so the main file is missing every page
    the log was written on top of. Each frame is valid by its own checksum and
    SQLite has no way to ask whether the log belongs to the main file beside
    it: it lays the frames over whatever it finds there.

    What is written in between, and touched again afterwards, is what makes the
    difference *visible*: a few rows would land in pages both files share and
    the pair would look like a consistent library.
    """
    build.mkdir()
    source = build / "boat.pylot"
    shutil.copyfile(template, source)
    keeper = sqlite3.connect(source, timeout=0)  # keeps the last-connection checkpoint from ever running

    def restart_the_log() -> None:
        # The first attempt can report busy while the writer's last read is still marked
        # in the log, and would then wait out the whole default timeout for it to go.
        for _ in range(5):
            if keeper.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] == 0:
                return
        raise AssertionError("the log could not be restarted")

    try:
        keeper.execute("PRAGMA journal_mode = WAL")
        with Pylot.open(source) as writer:
            writer.create_condition(z_origin=-4.0, condition_id="early")
            shutil.copyfile(source, folder / "boat.pylot")  # the old main file
            restart_the_log()
            keeper.execute("CREATE TABLE filler (x BLOB)")
            with keeper:
                keeper.executemany("INSERT INTO filler VALUES (?)", [(b"x" * 2000,)] * 400)
            restart_the_log()
            writer.create_condition(z_origin=-1.0, condition_id="late")
            with keeper:
                keeper.execute("INSERT INTO filler VALUES (?)", (b"y" * 100,))
            shutil.copyfile(source.with_name("boat.pylot-wal"), folder / "boat.pylot-wal")  # the new log
    finally:
        keeper.close()
    return folder / "boat.pylot"


def with_stale_sidecars(folder: Path) -> None:
    """A ``-shm`` and a ``-journal`` beside a legacy pair, as a library that was open in an older version leaves."""
    (folder / "boat.pylot-shm").write_bytes(b"\0" * 32768)
    (folder / "boat.pylot-journal").write_bytes(b"not a journal")


# -- looking at files ---------------------------------------------------------------------


def names(folder: Path) -> list[str]:
    return sorted(entry.name for entry in folder.iterdir())


def header(path: Path) -> bytes:
    """Bytes 18-19: the file-format write and read versions, 1 for a rollback journal, 2 for WAL."""
    with path.open("rb") as handle:
        return handle.read(20)[18:20]


def state_of(path: Path) -> tuple[bytes, int]:
    """Everything that tells whether a file was touched: its bytes and its modification time."""
    return path.read_bytes(), path.stat().st_mtime_ns


def description_of(path: Path) -> str:
    with Library.open(path, read_only=True) as library:
        return library.info.description


def conditions_of(path: Path) -> list[str]:
    with Library.open(path, read_only=True) as library:
        return sorted(condition.id for condition in library.conditions())


def record(session: "Workspace | Path") -> dict:
    """The session record on disk, as crash recovery would read it."""
    work_dir = session.work_dir if isinstance(session, Workspace) else session
    return json.loads((work_dir / "session.json").read_text(encoding="utf-8"))


def work_dirs(work_root: Path) -> list[Path]:
    return sorted(work_root.iterdir()) if work_root.exists() else []


def edit(workspace: Workspace, text: str = "edited") -> None:
    workspace.library.set_info(description=text)


def bump_mtime(path: Path, seconds: float = 5.0) -> None:
    """Move a file's modification time without touching a byte of it."""
    info = path.stat()
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + int(seconds * 1e9)))


def someone_else_edits(path: Path, text: str = "someone else") -> None:
    """Another program changes the library, through SQLite, the ordinary way.

    The modification time is moved on explicitly: on a coarse filesystem clock
    a change made within a tick of the copy would otherwise look identical by
    size and time, which is a limit of the cheap check and not of what these
    tests are about.
    """
    with Pylot.open(path) as other:
        other.set_info(description=text)
    bump_mtime(path)


def run_on_thread(work) -> None:
    """Run ``work`` on its own thread and re-raise whatever it raised."""
    failures: list[BaseException] = []

    def target() -> None:
        try:
            work()
        except BaseException as exc:
            failures.append(exc)

    thread = threading.Thread(target=target)
    thread.start()
    thread.join(60)
    assert not thread.is_alive(), "the helper thread hung"
    if failures:
        raise failures[0]


def commit_elsewhere(database: Path, sql: str, *params) -> None:
    """Commit ``sql`` through a connection of its own on another thread.

    That is what the batch screen's worker does to the working copy: its own
    connection, its own thread, no involvement of the window's ``Pylot``.
    """

    def work() -> None:
        with closing(sqlite3.connect(database, timeout=30)) as connection, connection:
            connection.execute(sql, params)

    run_on_thread(work)


def crash(workspace: Workspace) -> Path:
    """Stop a workspace the way a dying process stops, and return its folder.

    Simulates what the operating system does for a killed process -- the
    connections are closed and the session lock is released -- and nothing
    else: no ``closed`` in the record, the folder left where it is, which is
    what makes it recoverable.

    It does *not* leave the copy with a ``-wal`` in it. Closing the last
    connection checkpoints the copy into one rollback-mode file, so there is
    nothing for a recovery to replay. That path -- the dead process's commits
    still only in its ``-wal`` -- is covered by
    ``test_a_killed_process_leaves_its_unsaved_edits_recoverable``, which kills
    a real interpreter.
    """
    workspace._monitor.close()
    workspace.library.close()
    workspace._lock.release()
    return workspace.work_dir


def abandoned(
    original: Path, work_root: Path, text: str = "unsaved work", *, damage_record=None
) -> tuple[Path, Recovery]:
    """A session that died with ``text`` unsaved: its folder and what ``recoverable`` offers for it.

    ``damage_record``, if given, is called with the session record's contents
    (a dict, changed in place) before the folder is looked at again.
    """
    workspace = Workspace.open(original, work_root=work_root)
    edit(workspace, text)
    assert workspace.dirty
    work_dir = crash(workspace)
    if damage_record is not None:
        data = record(work_dir)
        damage_record(data)
        (work_dir / "session.json").write_text(json.dumps(data), encoding="utf-8")
    (found,) = Workspace.recoverable(work_root)
    assert found.work_dir == work_dir
    return work_dir, found


def leftovers(folder: Path) -> list[str]:
    """What a finished or a failed Save must never leave in the user's folder: staged files, moved-aside sidecars."""
    return sorted(entry.name for entry in folder.iterdir() if entry.name.startswith("~") or entry.name.endswith(".tmp"))


def tree_state(root: Path) -> dict[str, tuple[bool, bytes | None, int]]:
    """Every entry at and under ``root`` -- kind, bytes, modification time -- keyed by relative path.

    A directory's own modification time is in it: creating or removing
    anything inside moves it, so a lock file dropped into a folder shows.
    """
    state = {".": (True, None, root.stat().st_mtime_ns)}
    for entry in sorted(root.rglob("*")):
        key = entry.relative_to(root).as_posix()
        state[key] = (entry.is_dir(), None if entry.is_dir() else entry.read_bytes(), entry.stat().st_mtime_ns)
    return state


def integrity_of(path: Path) -> str:
    """``PRAGMA integrity_check`` on the file alone, without creating anything beside it."""
    uri = f"{path.absolute().as_uri()}?mode=ro&immutable=1"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        return connection.execute("PRAGMA integrity_check").fetchone()[0]


def refuse_replace(monkeypatch, when) -> list[Path]:
    """Make ``os.replace`` fail the way an open handle makes it fail on Windows, for the moves ``when`` selects.

    ``when(source, destination)`` gets both as paths. Returns the destinations
    that were refused, in order. This is how the same failure is reached on
    platforms where holding a file open does not stop a rename.
    """
    real = os.replace
    refused: list[Path] = []

    def replace_or_refuse(source, destination, *args, **kwargs):
        if when(Path(source), Path(destination)):
            refused.append(Path(destination))
            raise PermissionError(13, "simulated: another program has it open", str(destination))
        return real(source, destination, *args, **kwargs)

    monkeypatch.setattr(os, "replace", replace_or_refuse)
    return refused


def save_at_once(workspace: Workspace, count: int) -> list[BaseException]:
    """Call ``workspace.save()`` from ``count`` threads released together by a barrier; what they raised."""
    barrier = threading.Barrier(count)
    failures: list[BaseException] = []

    def save() -> None:
        try:
            barrier.wait(30)
            workspace.save()
        except BaseException as exc:
            failures.append(exc)

    threads = [threading.Thread(target=save) for _ in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    assert not any(thread.is_alive() for thread in threads), "a save hung"
    return failures


def someone_writes_during_the_first_refusal(monkeypatch, path: Path, text: str) -> list[Path]:
    """Refuse the first ``os.replace`` onto ``path`` -- as a scanner's handle does -- and change the file during the wait.

    The change is made by a second Pylot, through SQLite, at the moment the
    refusal happens: exactly the interval in which Save is retrying and has
    already decided the file is unchanged. Returns the sources of the attempts
    made onto ``path``, in order.
    """
    real = os.replace
    attempts: list[Path] = []

    def replace(source, destination, *args, **kwargs):
        if Path(destination) == path:
            attempts.append(Path(source))
            if len(attempts) == 1:
                someone_else_edits(path, text)
                raise PermissionError(13, "simulated: another program has it open", str(destination))
        return real(source, destination, *args, **kwargs)

    monkeypatch.setattr(os, "replace", replace)
    return attempts


def fail_record_writes(monkeypatch, times: int = 1) -> list[dict]:
    """Make the next ``times`` writes of the session record fail as a full disk does; returns the records refused."""
    real = workspace_module._write_record
    refused: list[dict] = []

    def write_or_refuse(work_dir, body):
        if len(refused) < times:
            refused.append(body)
            raise OSError(28, "No space left on device")
        real(work_dir, body)

    monkeypatch.setattr(workspace_module, "_write_record", write_or_refuse)
    return refused


def craft_session(
    work_root: Path,
    template: Path,
    *,
    source: Path | None,
    record_text: str | None = None,
    working: bool = True,
    age: float | None = None,
) -> Path:
    """A dead session folder written by hand, for the states that are hard to reach for real.

    ``record_text`` replaces the record file's text outright, and an empty
    string leaves no record at all.
    ``age`` backdates the folder, in seconds. The lock file is created here, as
    a real session does before anything else, so that finding the session does
    not itself refresh the folder's modification time.
    """
    work_dir = work_root / uuid.uuid4().hex
    work_dir.mkdir(parents=True)
    (work_dir / "session.lock").write_bytes(b"L")
    if working:
        shutil.copyfile(template, work_dir / "boat.pylot")
    body = {
        "version": 1,
        "source": str(source) if source else None,
        "name": "boat.pylot",
        "dirty": True,
        "closed": False,
        "fingerprint": None,
        "pid": 0,
        "updated": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    if record_text is None:
        (work_dir / "session.json").write_text(json.dumps(body), encoding="utf-8")
    elif record_text:
        (work_dir / "session.json").write_text(record_text, encoding="utf-8")
    if age is not None:
        past = time.time() - age
        os.utime(work_dir, (past, past))
    return work_dir


# ==========================================================================================
# OPEN
# ==========================================================================================


def test_open_makes_a_private_copy_in_the_work_root(original, folder, work_root):
    with Workspace.open(original, work_root=work_root) as workspace:
        assert workspace.path == original
        assert workspace.name == "boat.pylot"
        assert workspace.work_dir.parent == work_root
        assert workspace.working_path.parent == workspace.work_dir
        assert workspace.working_path != original
        assert workspace.working_path.is_file()
        assert workspace.library.info.vessel_name == "Boxboat"
        assert Path(workspace.library.path) == workspace.working_path
        assert not workspace.closed


def test_open_and_edit_and_close_leave_the_original_byte_identical(original, folder, work_root):
    before = state_of(original)
    with Workspace.open(original, work_root=work_root) as workspace:
        edit(workspace)
        workspace.library.create_condition(z_origin=-3.0, condition_id="c1")
        assert workspace.dirty
    assert state_of(original) == before  # bytes and modification time
    assert names(folder) == ["boat.pylot"]  # and no sidecar of any kind appeared


def test_nothing_holds_the_original_open_while_the_workspace_is_(original, folder, work_root):
    # On Windows a file with any open handle -- ours, in this process, a leaked
    # sqlite connection -- cannot be replaced or deleted. This is the property
    # a sync client and DAVE rely on, so it is asserted directly.
    with Workspace.open(original, work_root=work_root) as workspace:
        edit(workspace)
        assert workspace.dirty
        other = folder / "other.pylot"
        shutil.copyfile(original, other)
        os.replace(other, original)
        original.unlink()
        assert not original.exists()


def test_nothing_holds_the_original_open_after_a_save_either(original, folder, work_root):
    with Workspace.open(original, work_root=work_root) as workspace:
        edit(workspace)
        workspace.save()
        other = folder / "other.pylot"
        shutil.copyfile(original, other)
        os.replace(other, original)
        original.unlink()


def test_the_workspace_is_exported_from_the_package():
    assert pylot_bem.Workspace is Workspace


def test_paths_with_spaces_hashes_percents_and_accents_work_end_to_end(template, tmp_path):
    # Names that mean something else once a path is turned into a URI ("#" starts
    # a fragment, "%" an escape): Save opens its staging file read-only, in the
    # work root, and that open goes through one.
    docs = tmp_path / "dö cs #2 100%"
    docs.mkdir()
    library = docs / "b#at %41 é.pylot"
    shutil.copyfile(template, library)
    with Workspace.open(library, work_root=tmp_path / "wörk #1 %20 & co") as workspace:
        edit(workspace, "saved")
        workspace.save()
        workspace.save_as(docs / "second #2.pylot")
    assert description_of(library) == "saved"
    assert names(docs) == ["b#at %41 é.pylot", "second #2.pylot"]


@pytest.mark.parametrize("root_name", ["work root", "wörk ünï cödé", "日本語 フォルダ"])
def test_save_works_when_the_work_root_has_spaces_or_non_ascii_letters(root_name, original, folder, tmp_path):
    # Save verifies the staging file, which lives in the work root, so a work root
    # whose name needs care is where a change to how that path is handled would
    # show first. (The UNC test below is the one that failed for real.)
    root = tmp_path / root_name
    with Workspace.open(original, work_root=root) as workspace:
        assert workspace.work_dir.parent == root
        edit(workspace, "saved")
        workspace.save()
        edit(workspace, "saved again")
        workspace.save_as(folder / "copy.pylot")

    assert description_of(original) == "saved"
    assert description_of(folder / "copy.pylot") == "saved again"
    assert header(original) == ROLLBACK
    assert names(folder) == ["boat.pylot", "copy.pylot"]
    assert work_dirs(root) == []


@windows_only
def test_save_works_when_the_work_root_is_a_unc_path(original, folder, tmp_path):
    # A file: URI cannot carry a UNC path -- SQLite refuses any authority but
    # localhost -- and the work root can be one when the user points
    # PYLOT_BEM_WORK_DIR at a share. This machine's own administrative share,
    # reached by its loopback address, is a UNC path that needs no network.
    unc_base = Path("\\\\127.0.0.1\\" + tmp_path.drive[0] + "$") / tmp_path.relative_to(tmp_path.anchor)
    if not unc_base.is_dir():
        pytest.skip("the administrative share of this machine is not reachable")
    root = unc_base / "unc work root"

    with Workspace.open(original, work_root=root) as workspace:
        assert str(workspace.working_path).startswith("\\\\127.0.0.1\\")
        edit(workspace, "saved over a UNC work root")
        workspace.save()

    assert description_of(original) == "saved over a UNC work root"
    assert header(original) == ROLLBACK
    assert names(folder) == ["boat.pylot"]
    assert work_dirs(root) == []


def test_open_without_a_work_root_uses_the_configured_one(original, tmp_path, monkeypatch):
    configured = tmp_path / "configured"
    monkeypatch.setenv(WORK_DIR_ENV, str(configured))
    with Workspace.open(original) as workspace:
        assert workspace.work_dir.parent == configured
    assert work_dirs(configured) == []


@pytest.mark.parametrize("kind", ["missing", "directory", "text", "empty", "not_a_library", "future", "past"])
def test_a_file_that_is_not_a_readable_library_is_refused_and_leaves_no_work_dir(kind, folder, work_root, template):
    target = folder / "victim.pylot"
    if kind == "text":
        target.write_text("this is not a database, it is a shopping list\n" * 40)
    elif kind == "empty":
        target.write_bytes(b"")
    elif kind == "not_a_library":
        with closing(sqlite3.connect(target)) as connection, connection:
            connection.execute("CREATE TABLE notes (x)")
    elif kind in ("future", "past"):
        shutil.copyfile(template, target)
        with closing(sqlite3.connect(target)) as connection:
            connection.execute(f"PRAGMA user_version = {99 if kind == 'future' else 1}")
    elif kind == "directory":
        target = folder
    before = state_of(target) if target.is_file() else None

    with pytest.raises(LibraryError):
        Workspace.open(target, work_root=work_root)

    assert work_dirs(work_root) == []
    assert (state_of(target) if target.is_file() else None) == before
    assert not any(entry.name.endswith(("-wal", "-shm", "-journal")) for entry in folder.iterdir())


def test_a_legacy_libraries_uncheckpointed_commits_come_through_and_the_original_is_not_touched(
    legacy, folder, work_root
):
    before = {entry.name: state_of(entry) for entry in folder.iterdir()}
    assert sorted(before) == ["boat.pylot", "boat.pylot-wal"]

    with Workspace.open(legacy, work_root=work_root) as workspace:
        # The row exists only in the -wal beside the original: copying the main
        # file alone would have opened a library without it.
        assert [condition.id for condition in workspace.library.conditions()] == ["old"]
        assert not workspace.dirty  # having the old rows is not an edit

    assert {entry.name: state_of(entry) for entry in folder.iterdir()} == before


def test_the_wal_that_was_copied_is_recorded_in_the_fingerprint(legacy, folder, work_root):
    wal = folder / "boat.pylot-wal"
    with Workspace.open(legacy, work_root=work_root) as workspace:
        stamp = record(workspace)["fingerprint"]
        assert stamp["main"]["size"] == legacy.stat().st_size
        assert stamp["main"]["sha256"] == hashlib.sha256(legacy.read_bytes()).hexdigest()
        assert stamp["wal"]["size"] == wal.stat().st_size
        assert stamp["wal"]["sha256"] == hashlib.sha256(wal.read_bytes()).hexdigest()


def test_an_ordinary_original_has_no_wal_in_its_fingerprint(original, work_root):
    with Workspace.open(original, work_root=work_root) as workspace:
        assert record(workspace)["fingerprint"]["wal"] is None


def test_a_wal_that_does_not_agree_with_the_main_file_refuses_to_open(legacy, work_root, monkeypatch):
    monkeypatch.setattr(Workspace, "_quick_check_ok", lambda self: False)
    before = state_of(legacy)
    with pytest.raises(WorkspaceError, match="do not agree"):
        Workspace.open(legacy, work_root=work_root)
    assert work_dirs(work_root) == []
    assert state_of(legacy) == before


def test_a_real_wal_that_belongs_to_another_main_file_refuses_to_open_and_touches_nothing(
    template, tmp_path, folder, work_root
):
    # The stubbed test above proves the refusal is wired up; this one proves SQLite
    # really does hand back a library that fails its check when the log and the
    # main file are from different moments, which is what the check exists for.
    library = make_mismatched(template, tmp_path / "build", folder)
    assert header(library) == WAL
    assert library.with_name("boat.pylot-wal").stat().st_size > 0
    assert main_file_conditions(library) == []  # the old main file is a perfectly good library on its own

    # The fixture is only worth anything if SQLite itself sees the mismatch; look at a copy.
    probe = tmp_path / "probe"
    probe.mkdir()
    shutil.copyfile(library, probe / "boat.pylot")
    shutil.copyfile(library.with_name("boat.pylot-wal"), probe / "boat.pylot-wal")
    with closing(sqlite3.connect(probe / "boat.pylot")) as connection:
        assert connection.execute("PRAGMA quick_check").fetchone()[0] != "ok"

    before = {entry.name: state_of(entry) for entry in folder.iterdir()}
    with pytest.raises(WorkspaceError, match="do not agree"):
        Workspace.open(library, work_root=work_root)

    assert work_dirs(work_root) == []
    assert {entry.name: state_of(entry) for entry in folder.iterdir()} == before  # read, never written


def test_a_modern_original_is_not_integrity_checked_at_open(original, work_root, monkeypatch):
    # The check exists for a -wal that may disagree with its main file. On a
    # file with none it would only cost time on a large library.
    monkeypatch.setattr(Workspace, "_quick_check_ok", lambda self: pytest.fail("ran quick_check"))
    Workspace.open(original, work_root=work_root).close()


def test_an_original_that_keeps_changing_is_refused_after_three_tries(original, work_root, monkeypatch):
    real = workspace_module._copy_hashing

    def copy_then_change(source, target, *, sync=False):
        digest = real(source, target, sync=sync)
        if source == original:
            bump_mtime(original, 1.0)
        return digest

    monkeypatch.setattr(workspace_module, "_copy_hashing", copy_then_change)
    with pytest.raises(WorkspaceError, match="keeps changing"):
        Workspace.open(original, work_root=work_root)
    assert work_dirs(work_root) == []


def test_an_original_that_settles_after_one_change_is_copied_and_fingerprinted_as_it_ended(
    original, work_root, monkeypatch
):
    real = workspace_module._copy_hashing
    calls = []

    def change_once(source, target, *, sync=False):
        digest = real(source, target, sync=sync)
        if source == original and not calls:
            calls.append(source)
            bump_mtime(original, 1.0)
        return digest

    monkeypatch.setattr(workspace_module, "_copy_hashing", change_once)
    with Workspace.open(original, work_root=work_root) as workspace:
        assert record(workspace)["fingerprint"]["main"]["mtime_ns"] == original.stat().st_mtime_ns
        workspace.save()  # and the settled fingerprint is the one Save compares against


# ==========================================================================================
# DIRTY
# ==========================================================================================


def test_a_workspace_is_clean_until_something_is_written(original, work_root):
    with Workspace.open(original, work_root=work_root) as workspace:
        assert [workspace.dirty for _ in range(5)] == [False] * 5
        assert record(workspace)["dirty"] is False
        # Reading is not writing.
        workspace.library.conditions()
        workspace.library.info  # noqa: B018
        assert not workspace.dirty


def test_a_write_through_the_library_makes_it_dirty(original, work_root):
    with Workspace.open(original, work_root=work_root) as workspace:
        edit(workspace)
        assert workspace.dirty


def test_a_write_by_a_batch_worker_on_another_thread_makes_it_dirty(original, work_root):
    # The one that matters: BatchThread opens its own Pylot on library.path and
    # commits from its own thread, so nothing on the window's connection moves.
    with Workspace.open(original, work_root=work_root) as workspace:
        assert not workspace.dirty

        def batch() -> None:
            with Pylot.open(workspace.library.path) as worker:
                worker.create_condition(z_origin=-6.0, condition_id="from-the-batch")

        run_on_thread(batch)

        assert workspace.dirty
        assert [c.id for c in workspace.library.conditions()] == ["from-the-batch"]


@pytest.mark.parametrize(
    "sql", ["CREATE TABLE scratch (x)", "PRAGMA user_version = 5", "CREATE INDEX scratch_label ON condition (label)"]
)
def test_a_change_that_is_only_schema_or_a_pragma_is_seen(sql, original, work_root):
    with Workspace.open(original, work_root=work_root) as workspace:
        assert not workspace.dirty
        commit_elsewhere(workspace.library.path, sql)
        assert workspace.dirty


def test_dirty_can_be_polled_from_another_thread(original, work_root):
    with Workspace.open(original, work_root=work_root) as workspace:
        seen = []
        run_on_thread(lambda: seen.append(workspace.dirty))
        edit(workspace)
        run_on_thread(lambda: seen.append(workspace.dirty))
        assert seen == [False, True]


def test_dirty_is_sticky(original, work_root):
    with Workspace.open(original, work_root=work_root) as workspace:
        commit_elsewhere(workspace.library.path, "UPDATE library SET description = ?", "x")
        assert [workspace.dirty for _ in range(5)] == [True] * 5


def test_a_save_makes_it_clean_and_it_stays_clean_until_the_next_write(original, work_root):
    with Workspace.open(original, work_root=work_root) as workspace:
        edit(workspace)
        assert workspace.dirty
        workspace.save()
        assert [workspace.dirty for _ in range(5)] == [False] * 5  # saving is not itself a change
        assert record(workspace)["dirty"] is False
        edit(workspace, "again")
        assert workspace.dirty


def test_a_commit_that_lands_during_a_save_leaves_the_workspace_dirty(original, work_root, monkeypatch):
    real = Workspace._snapshot

    def snapshot_then_a_commit_lands(self, stage):
        real(self, stage)
        commit_elsewhere(self.working_path, "UPDATE library SET description = ?", "landed during the save")

    with Workspace.open(original, work_root=work_root) as workspace:
        edit(workspace, "in the snapshot")
        monkeypatch.setattr(Workspace, "_snapshot", snapshot_then_a_commit_lands)
        workspace.save()
        monkeypatch.setattr(Workspace, "_snapshot", real)

        assert description_of(original) == "in the snapshot"  # the late commit is not in the file...
        assert workspace.dirty  # ...so the workspace must not claim it is
        assert record(workspace)["dirty"] is True

        workspace.save()
        assert description_of(original) == "landed during the save"
        assert not workspace.dirty


def test_the_first_dirty_poll_records_the_session_for_crash_recovery(original, work_root):
    with Workspace.open(original, work_root=work_root) as workspace:
        assert record(workspace)["dirty"] is False
        edit(workspace)
        assert workspace.dirty
        written = record(workspace)
        assert written["dirty"] is True
        assert written["closed"] is False
        assert written["source"] == str(original)
        assert written["name"] == "boat.pylot"
        assert written["fingerprint"]["main"]["sha256"] == hashlib.sha256(original.read_bytes()).hexdigest()


def test_a_dirty_state_the_record_missed_is_rewritten_until_it_sticks_and_then_left_alone(
    original, work_root, monkeypatch
):
    # The record is the only thing crash recovery has to go on. A full disk at the
    # one moment the state changed must not leave it saying "nothing to lose" for
    # the rest of the session.
    with Workspace.open(original, work_root=work_root) as workspace:
        assert record(workspace)["dirty"] is False
        refused = fail_record_writes(monkeypatch)
        edit(workspace)

        assert workspace.dirty is True
        assert len(refused) == 1
        assert record(workspace)["dirty"] is False  # the disk still says there is nothing to lose

        assert workspace.dirty is True  # the next poll tries again...
        assert record(workspace)["dirty"] is True  # ...and this time it lands
        assert "session.json.tmp" not in names(workspace.work_dir)

        attempts = []
        real = workspace_module._write_record
        monkeypatch.setattr(workspace_module, "_write_record", lambda *args: (attempts.append(1), real(*args)))
        assert [workspace.dirty for _ in range(5)] == [True] * 5
        assert attempts == []  # a poll is cheap once the record is right: no fsync per call


def test_a_clean_state_the_record_missed_after_a_save_is_rewritten_by_a_later_poll(original, work_root, monkeypatch):
    # The reverse direction. A record that still says "dirty" after a successful Save
    # would offer a recovery of work that is already in the file.
    with Workspace.open(original, work_root=work_root) as workspace:
        edit(workspace, "mine")
        assert workspace.dirty
        assert record(workspace)["dirty"] is True
        refused = fail_record_writes(monkeypatch)

        workspace.save()  # the file is written; only the note about it is not

        assert description_of(original) == "mine"
        assert len(refused) == 1
        assert record(workspace)["dirty"] is True  # stale
        assert workspace.dirty is False
        assert record(workspace)["dirty"] is False  # and the poll put it right


def test_the_session_record_is_synced_before_it_replaces_the_previous_one(tmp_path, monkeypatch):
    # A rename can outlive the data it points at across a power cut. Syncing the
    # staged record first is what keeps "the record" from reading as empty.
    events = []
    real_fsync, real_replace = os.fsync, os.replace

    def fsync(descriptor):
        events.append("fsync")
        return real_fsync(descriptor)

    def replace(source, destination, *args, **kwargs):
        events.append("replace")
        return real_replace(source, destination, *args, **kwargs)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "replace", replace)

    workspace_module._write_record(tmp_path, {"version": 1, "dirty": True})

    assert events == ["fsync", "replace"]
    assert names(tmp_path) == ["session.json"]  # no session.json.tmp left behind
    assert json.loads((tmp_path / "session.json").read_text(encoding="utf-8")) == {"version": 1, "dirty": True}


# ==========================================================================================
# SAVE
# ==========================================================================================


def test_save_gives_the_original_the_edits_as_a_single_rollback_mode_file(original, folder, work_root):
    with Workspace.open(original, work_root=work_root) as workspace:
        edit(workspace, "saved")
        workspace.library.create_condition(z_origin=-3.0, condition_id="c1")
        workspace.save()

        assert description_of(original) == "saved"
        assert conditions_of(original) == ["c1"]
        assert header(original) == ROLLBACK  # not WAL: nothing will ask for -wal/-shm beside it
        assert names(folder) == ["boat.pylot"]  # no sidecars, no ~temp, no stage

    assert names(folder) == ["boat.pylot"]


def test_save_leaves_no_staging_files_behind_and_the_workspace_keeps_working(original, folder, work_root):
    with Workspace.open(original, work_root=work_root) as workspace:
        edit(workspace, "one")
        workspace.save()
        edit(workspace, "two")
        workspace.save()
        assert description_of(original) == "two"
        assert workspace.library.info.description == "two"
        assert sorted(entry.name for entry in workspace.work_dir.iterdir() if entry.name.startswith(".")) == []


def test_save_replaces_a_legacy_original_with_one_clean_file_and_its_old_rows_do_not_come_back(
    legacy, folder, work_root
):
    (folder / "boat.pylot-shm").write_bytes(b"\0" * 32768)
    (folder / "boat.pylot-journal").write_bytes(b"not a journal")

    with Workspace.open(legacy, work_root=work_root) as workspace:
        workspace.library.delete_condition("old")
        workspace.library.create_condition(z_origin=-8.0, condition_id="new")
        workspace.save()

    assert names(folder) == ["boat.pylot"]  # the stale -wal, -shm and -journal are gone
    assert header(legacy) == ROLLBACK
    # If the stale -wal had been left in place, SQLite would replay it onto the
    # new file and hand back a mixture with "old" in it.
    assert conditions_of(legacy) == ["new"]


def test_save_raises_source_changed_when_someone_else_changed_the_original_and_writes_nothing(
    original, folder, work_root
):
    with Workspace.open(original, work_root=work_root) as workspace:
        edit(workspace, "mine")
        someone_else_edits(original, "theirs")
        theirs = state_of(original)

        with pytest.raises(SourceChangedError) as caught:
            workspace.save()

        assert caught.value.path == original
        assert state_of(original) == theirs  # their change is still there
        assert names(folder) == ["boat.pylot"]
        assert workspace.dirty  # and none of mine is lost
        assert workspace.library.info.description == "mine"


def test_a_changed_original_is_noticed_before_any_work_is_done(original, work_root, monkeypatch):
    # On a large library the snapshot is the expensive part; there is no point
    # making one to throw away.
    with Workspace.open(original, work_root=work_root) as workspace:
        edit(workspace, "mine")
        someone_else_edits(original, "theirs")
        monkeypatch.setattr(Workspace, "_snapshot", lambda self, stage: pytest.fail("took a snapshot"))
        with pytest.raises(SourceChangedError):
            workspace.save()


def test_force_overwrites_a_changed_original_and_the_next_plain_save_works(original, work_root):
    with Workspace.open(original, work_root=work_root) as workspace:
        edit(workspace, "mine")
        someone_else_edits(original, "theirs")
        with pytest.raises(SourceChangedError):
            workspace.save()

        workspace.save(force=True)
        assert description_of(original) == "mine"
        assert not workspace.dirty

        edit(workspace, "mine, again")
        workspace.save()  # the fingerprint now describes what force wrote
        assert description_of(original) == "mine, again"


def test_save_notices_a_change_that_lands_after_the_first_check_and_before_the_replace(
    original, folder, work_root, monkeypatch
):
    real = Workspace._snapshot

    def snapshot_then_someone_saves(self, stage):
        real(self, stage)
        someone_else_edits(original, "theirs, mid-save")

    with Workspace.open(original, work_root=work_root) as workspace:
        edit(workspace, "mine")
        monkeypatch.setattr(Workspace, "_snapshot", snapshot_then_someone_saves)
        with pytest.raises(SourceChangedError):
            workspace.save()

        assert description_of(original) == "theirs, mid-save"
        assert names(folder) == ["boat.pylot"]  # the ~temp file did not stay
        assert not [entry for entry in workspace.work_dir.iterdir() if entry.name.endswith(".tmp")]
        assert workspace.dirty


def test_a_touched_original_with_identical_content_is_not_a_change(original, work_root):
    # What a sync client does: rewrites the modification time, not a byte.
    with Workspace.open(original, work_root=work_root) as workspace:
        edit(workspace, "mine")
        bump_mtime(original)
        workspace.save()  # no SourceChangedError
        assert description_of(original) == "mine"

        bump_mtime(original)
        edit(workspace, "mine, later")
        workspace.save()
        assert description_of(original) == "mine, later"


def test_save_recreates_an_original_that_was_deleted(original, folder, work_root):
    with Workspace.open(original, work_root=work_root) as workspace:
        edit(workspace, "still here")
        original.unlink()
        workspace.save()  # nothing there to overwrite, so nothing to warn about
        assert description_of(original) == "still here"
        assert header(original) == ROLLBACK
        assert names(folder) == ["boat.pylot"]


@not_root
def test_a_read_only_original_can_be_opened_but_not_saved_over(original, folder, work_root):
    os.chmod(original, stat.S_IREAD)
    try:
        with Workspace.open(original, work_root=work_root) as workspace:
            edit(workspace, "mine")
            assert workspace.dirty
            before = state_of(original)

            with pytest.raises(SourceLockedError) as caught:
                workspace.save()

            assert "read-only" in caught.value.reason
            assert caught.value.path == original
            assert names(folder) == ["boat.pylot"]  # no ~temp left
            assert state_of(original) == before
            assert workspace.dirty

            os.chmod(original, stat.S_IREAD | stat.S_IWRITE)
            workspace.save()
            assert description_of(original) == "mine"
    finally:
        os.chmod(original, stat.S_IREAD | stat.S_IWRITE)


@windows_only
def test_an_original_held_open_elsewhere_cannot_be_saved_over_and_nothing_is_lost(
    original, folder, work_root, monkeypatch
):
    monkeypatch.setattr(workspace_module, "REPLACE_BUDGET", 0.3)
    with Workspace.open(original, work_root=work_root) as workspace:
        edit(workspace, "mine")
        assert workspace.dirty
        before = state_of(original)

        with original.open("rb"):
            started = time.perf_counter()
            with pytest.raises(SourceLockedError) as caught:
                workspace.save()
            waited = time.perf_counter() - started

        assert waited >= 0.25  # it kept trying for the budget rather than giving up at once
        assert caught.value.path == original
        assert caught.value.reason
        assert state_of(original) == before  # nothing was written
        assert names(folder) == ["boat.pylot"]  # and no ~temp was left
        assert [entry.name for entry in workspace.work_dir.iterdir() if entry.name.startswith(".stage")] == []
        assert workspace.dirty

        workspace.save()  # the handle is closed now
        assert description_of(original) == "mine"
        assert not workspace.dirty


HOLDS = [pytest.param("a real handle", marks=windows_only), "a refused rename"]


@contextmanager
def held_open(path: Path, how: str):
    """For the length of the block something else has ``path`` and no rename involving it can succeed.

    ``"a real handle"`` is the real thing, on the platform where a handle stops
    a rename. ``"a refused rename"`` makes ``os.replace`` fail the same way
    (``PermissionError``) for any move that has ``path`` as its source or its
    destination, so the code under test meets the same failure anywhere.
    """
    if how == "a real handle":
        with path.open("rb"):
            yield
    else:
        with pytest.MonkeyPatch.context() as patch:
            refuse_replace(patch, lambda source, destination: path in (source, destination))
            yield


@pytest.mark.parametrize("how", HOLDS)
def test_a_replace_that_fails_costs_a_legacy_original_nothing_not_even_its_sidecars(
    how, legacy, folder, work_root, monkeypatch
):
    # Save sets the stale -wal, -shm and -journal aside before it replaces the main
    # file, because SQLite would replay them onto the new one. When the replace then
    # fails they must be exactly as they were: a -wal can hold commits the main
    # file does not have, and a Save that did not happen may not cost any.
    with_stale_sidecars(folder)
    monkeypatch.setattr(workspace_module, "REPLACE_BUDGET", 0.3)
    with Workspace.open(legacy, work_root=work_root) as workspace:
        workspace.library.create_condition(z_origin=-8.0, condition_id="new")
        before = {entry.name: state_of(entry) for entry in folder.iterdir()}
        assert sorted(before) == ["boat.pylot", "boat.pylot-journal", "boat.pylot-shm", "boat.pylot-wal"]

        with held_open(legacy, how):
            started = time.perf_counter()
            with pytest.raises(SourceLockedError) as caught:
                workspace.save()
            waited = time.perf_counter() - started

        assert waited >= 0.25  # it kept trying for the budget rather than giving up at once
        assert caught.value.path == legacy
        # In place, byte for byte, with the times they had -- and no ~name.tmp of any kind.
        assert {entry.name: state_of(entry) for entry in folder.iterdir()} == before
        assert leftovers(folder) == []
        assert workspace.dirty
        assert record(workspace)["dirty"] is True

        # The retry is not told the file "has been changed by someone else" when the
        # only someone is us: the -wal it was opened with is back where it was.
        workspace.save()

        assert main_file_conditions(legacy) == ["new", "old"]  # "old" lived only in the -wal; it is in the file now
        assert names(folder) == ["boat.pylot"]  # and the sidecars are gone for good
        assert not workspace.dirty


@pytest.mark.parametrize("how", HOLDS)
@pytest.mark.parametrize("held", ["-wal", "-shm", "-journal"])
def test_a_sidecar_that_cannot_be_set_aside_puts_back_the_ones_that_were(
    held, how, legacy, folder, work_root, monkeypatch
):
    # They are moved in the order -wal, -shm, -journal, so holding the last means the
    # first two have already gone: those have to come back, and the main file has
    # not been touched. A sidecar that will not move is waited for like a main file
    # that will not be replaced -- whatever holds it may be about to let go.
    monkeypatch.setattr(workspace_module, "REPLACE_BUDGET", 0.3)
    with_stale_sidecars(folder)
    with Workspace.open(legacy, work_root=work_root) as workspace:
        edit(workspace, "mine")
        before = {entry.name: state_of(entry) for entry in folder.iterdir()}
        assert len(before) == 4

        with held_open(folder / f"boat.pylot{held}", how), pytest.raises(SourceLockedError) as caught:
            workspace.save()

        assert caught.value.path == legacy
        assert {entry.name: state_of(entry) for entry in folder.iterdir()} == before
        assert leftovers(folder) == []
        assert workspace.dirty

        workspace.save()
        assert description_of(legacy) == "mine"
        assert names(folder) == ["boat.pylot"]


@windows_only
def test_a_handle_that_is_released_during_the_wait_lets_the_save_through(original, work_root, monkeypatch):
    monkeypatch.setattr(workspace_module, "REPLACE_BUDGET", 10.0)
    with Workspace.open(original, work_root=work_root) as workspace:
        edit(workspace, "mine")
        handle = original.open("rb")
        release = threading.Timer(0.4, handle.close)
        release.start()
        try:
            workspace.save()  # a scanner or a sync client lets go within moments
        finally:
            release.join()
            handle.close()
        assert description_of(original) == "mine"


def test_a_change_that_lands_while_save_waits_for_the_file_is_not_overwritten(original, folder, work_root, monkeypatch):
    # Save checks the original is unchanged, and then may wait seconds for a scanner
    # to let go of it. The check has to be made again before every attempt, or a
    # change that arrives during the wait is replaced by a Save that "knew" better.
    attempts = someone_writes_during_the_first_refusal(monkeypatch, original, "theirs, during the wait")
    with Workspace.open(original, work_root=work_root) as workspace:
        edit(workspace, "mine")

        with pytest.raises(SourceChangedError) as caught:
            workspace.save()

        assert caught.value.path == original
        assert len(attempts) == 1  # it did not go round again and succeed
        assert description_of(original) == "theirs, during the wait"  # the other writer's content is what is on disk
        assert names(folder) == ["boat.pylot"]
        assert workspace.dirty  # and none of mine is lost

        workspace.save(force=True)  # the person who is told may still choose to
        assert description_of(original) == "mine"


def test_a_forced_save_is_not_rechecked_while_it_waits(original, folder, work_root, monkeypatch):
    # force means the person has been told the file is different and chose to
    # overwrite it. A recheck on every attempt would turn that choice down.
    attempts = someone_writes_during_the_first_refusal(monkeypatch, original, "theirs, during the wait")
    with Workspace.open(original, work_root=work_root) as workspace:
        edit(workspace, "mine")

        workspace.save(force=True)

        assert len(attempts) == 2  # refused once, then through
        assert description_of(original) == "mine"
        assert names(folder) == ["boat.pylot"]
        assert not workspace.dirty


@windows_only
def test_a_change_that_lands_while_the_original_is_really_held_open_is_not_overwritten(
    original, folder, work_root, monkeypatch
):
    monkeypatch.setattr(workspace_module, "REPLACE_BUDGET", 6.0)
    real = workspace_module._replace
    failures: list[BaseException] = []

    def other_writer() -> None:
        try:
            time.sleep(0.3)
            someone_else_edits(original, "theirs, while held")
        except BaseException as exc:
            failures.append(exc)

    writer = threading.Thread(target=other_writer)

    def replace_and_a_change_lands(sent, dest, **kwargs):
        writer.start()  # the wait for the file has begun; 0.3 s into it, somebody writes to the file
        return real(sent, dest, **kwargs)

    monkeypatch.setattr(workspace_module, "_replace", replace_and_a_change_lands)
    with Workspace.open(original, work_root=work_root) as workspace:
        edit(workspace, "mine")
        try:
            with original.open("rb"), pytest.raises(SourceChangedError):
                workspace.save()
        finally:
            if writer.ident is not None:
                writer.join(60)

        assert writer.ident is not None, "Save never got as far as waiting for the file"
        assert not failures
        assert description_of(original) == "theirs, while held"
        assert leftovers(folder) == []
        assert workspace.dirty


def test_two_saves_at_once_both_succeed_and_leave_a_whole_file(original, work_root, monkeypatch):
    # The second save has to be compared against what the first one wrote, not
    # against what the workspace knew before the first finished -- otherwise the
    # second is told the file was changed by someone else, and that someone is us.
    real = Workspace._snapshot
    snapshots: list[int] = []

    def slow_snapshot(self, stage):
        snapshots.append(threading.get_ident())
        time.sleep(0.15)  # long enough that the other save is certainly waiting its turn
        real(self, stage)

    monkeypatch.setattr(Workspace, "_snapshot", slow_snapshot)
    with Workspace.open(original, work_root=work_root) as workspace:
        for round_number in range(3):
            edit(workspace, f"edit {round_number}")

            assert save_at_once(workspace, 2) == []

            assert len(snapshots) == 2 * (round_number + 1)  # both really saved, one after the other
            assert description_of(original) == f"edit {round_number}"
            assert integrity_of(original) == "ok"
            assert header(original) == ROLLBACK
            assert not workspace.dirty
    assert names(original.parent) == ["boat.pylot"]


def test_a_symlinked_library_is_staged_in_the_real_targets_folder(template, tmp_path, work_root, monkeypatch):
    # The temporary file has to be next to the file it replaces: os.replace is only
    # atomic -- and only possible at all -- within one volume, and the link's own
    # folder may be on another. Creating a symlink needs a privilege on Windows,
    # so the operating system is told a stand-in path is one instead.
    real_dir, link_dir = tmp_path / "real", tmp_path / "links"
    real_dir.mkdir()
    link_dir.mkdir()
    target = real_dir / "boat.pylot"
    link = link_dir / "boat.pylot"
    shutil.copyfile(template, target)
    shutil.copyfile(template, link)  # what the link "is": a file that must come out of this untouched
    link_before = state_of(link)

    real_is_symlink, real_realpath = Path.is_symlink, os.path.realpath
    monkeypatch.setattr(Path, "is_symlink", lambda self: self == link or real_is_symlink(self))

    def realpath(path, *args, **kwargs):
        return str(target) if Path(path) == link else real_realpath(path, *args, **kwargs)

    monkeypatch.setattr(os.path, "realpath", realpath)
    replaced: list[tuple[Path, Path]] = []
    real_replace = workspace_module._replace

    def spy(sent, dest, **kwargs):
        replaced.append((sent, dest))
        return real_replace(sent, dest, **kwargs)

    monkeypatch.setattr(workspace_module, "_replace", spy)

    with Workspace.open(link, work_root=work_root) as workspace:
        edit(workspace, "through the link")
        workspace.save()

    ((sent, dest),) = replaced
    assert dest == target
    assert sent.parent == real_dir  # staged beside the real file...
    assert sent.name.startswith("~boat.pylot.")
    assert sent.name.endswith(".tmp")
    assert description_of(target) == "through the link"  # ...whose content is the new library
    assert header(target) == ROLLBACK
    assert state_of(link) == link_before  # and the link's own path was not touched
    assert names(real_dir) == ["boat.pylot"]
    assert names(link_dir) == ["boat.pylot"]


def test_a_snapshot_that_is_not_a_rollback_mode_file_is_refused_and_nothing_is_written(
    original, folder, work_root, monkeypatch
):
    def snapshot_by_backup(self, stage):
        # Connection.backup copies the WAL flag in the header along with the
        # pages: a file that asks for -wal and -shm beside it on every open.
        with closing(sqlite3.connect(self.working_path)) as source, closing(sqlite3.connect(stage)) as target:
            source.backup(target)

    with Workspace.open(original, work_root=work_root) as workspace:
        edit(workspace, "mine")
        before = state_of(original)
        monkeypatch.setattr(Workspace, "_snapshot", snapshot_by_backup)

        with pytest.raises(WorkspaceError, match="rollback"):
            workspace.save()

        assert state_of(original) == before
        assert names(folder) == ["boat.pylot"]
        assert [entry.name for entry in workspace.work_dir.iterdir() if entry.name.endswith(".tmp")] == []
        assert workspace.dirty


@pytest.mark.parametrize("damage", ["cut short", "last page garbled"])
def test_a_damaged_snapshot_is_refused_and_nothing_is_written(damage, original, folder, work_root, monkeypatch):
    real = Workspace._snapshot

    def damaged_snapshot(self, stage):
        real(self, stage)
        data = bytearray(stage.read_bytes())
        if damage == "cut short":  # a disk that filled up
            del data[5000:]
        else:  # an index page nothing reads at open, which only the integrity check finds
            data[-4096:-4032] = b"\xff" * 64
        stage.write_bytes(bytes(data))

    with Workspace.open(original, work_root=work_root) as workspace:
        edit(workspace, "mine")
        before = state_of(original)
        monkeypatch.setattr(Workspace, "_snapshot", damaged_snapshot)

        if damage == "cut short":
            with pytest.raises(LibraryError):
                workspace.save()
        else:
            with pytest.raises(WorkspaceError, match="integrity"):
                workspace.save()

        assert state_of(original) == before
        assert names(folder) == ["boat.pylot"]
        assert [entry.name for entry in workspace.work_dir.iterdir() if entry.name.endswith(".tmp")] == []
        assert workspace.dirty


def test_save_as_writes_elsewhere_switches_to_it_and_leaves_the_old_file_alone(original, folder, work_root):
    target = folder / "renamed.pylot"
    before = state_of(original)
    with Workspace.open(original, work_root=work_root) as workspace:
        edit(workspace, "first")
        workspace.save_as(target)

        assert workspace.path == target
        assert workspace.name == "renamed.pylot"
        assert not workspace.dirty
        assert description_of(target) == "first"
        assert header(target) == ROLLBACK
        assert state_of(original) == before

        edit(workspace, "second")
        assert workspace.dirty
        workspace.save()  # goes to the new file
        assert description_of(target) == "second"
        assert state_of(original) == before

    assert names(folder) == ["boat.pylot", "renamed.pylot"]


def test_after_save_as_the_changed_on_disk_check_watches_the_new_file(original, folder, work_root):
    target = folder / "renamed.pylot"
    with Workspace.open(original, work_root=work_root) as workspace:
        workspace.save_as(target)
        someone_else_edits(original, "irrelevant now")  # the old file is no concern of this workspace
        edit(workspace, "mine")
        workspace.save()
        assert description_of(target) == "mine"

        someone_else_edits(target, "theirs")
        edit(workspace, "mine again")
        with pytest.raises(SourceChangedError):
            workspace.save()
        assert description_of(target) == "theirs"


def test_save_as_replaces_an_unrelated_file_that_is_already_there(original, folder, work_root):
    target = folder / "other.pylot"
    target.write_bytes(b"whoever chose this name has been asked already")
    with Workspace.open(original, work_root=work_root) as workspace:
        edit(workspace, "mine")
        workspace.save_as(target)
        assert description_of(target) == "mine"
    assert names(folder) == ["boat.pylot", "other.pylot"]


def test_save_as_onto_the_current_file_is_a_save_and_keeps_its_changed_on_disk_check(original, work_root):
    with Workspace.open(original, work_root=work_root) as workspace:
        edit(workspace, "mine")
        someone_else_edits(original, "theirs")
        with pytest.raises(SourceChangedError):
            workspace.save_as(original)
        assert description_of(original) == "theirs"

        workspace.save(force=True)
        edit(workspace, "mine, later")
        workspace.save_as(original)  # unchanged since, so this is simply a save
        assert description_of(original) == "mine, later"
        assert workspace.path == original


def test_save_as_onto_the_current_file_spelled_differently_is_still_that_file(original, folder, work_root):
    respelled = folder / ".." / folder.name / "boat.pylot"
    with Workspace.open(original, work_root=work_root) as workspace:
        edit(workspace, "mine")
        someone_else_edits(original, "theirs")
        with pytest.raises(SourceChangedError):
            workspace.save_as(respelled)
        assert description_of(original) == "theirs"


def test_save_on_a_closed_workspace_is_refused(original, folder, work_root):
    workspace = Workspace.open(original, work_root=work_root)
    edit(workspace)
    workspace.close()
    with pytest.raises(WorkspaceError, match="closed"):
        workspace.save()
    with pytest.raises(WorkspaceError, match="closed"):
        workspace.save_as(folder / "elsewhere.pylot")
    assert names(folder) == ["boat.pylot"]


def test_saving_to_a_symlinked_library_replaces_the_target_and_keeps_the_link(template, tmp_path, work_root):
    real_dir, link_dir = tmp_path / "real", tmp_path / "links"
    real_dir.mkdir()
    link_dir.mkdir()
    real = real_dir / "boat.pylot"
    shutil.copyfile(template, real)
    link = link_dir / "boat.pylot"
    try:
        link.symlink_to(real)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"cannot create a symlink here: {exc}")

    with Workspace.open(link, work_root=work_root) as workspace:
        edit(workspace, "through the link")
        workspace.save()

    assert link.is_symlink()  # the link was not replaced by a regular file
    assert description_of(real) == "through the link"
    assert names(real_dir) == ["boat.pylot"]
    assert names(link_dir) == ["boat.pylot"]


def test_saving_while_another_thread_commits_gives_a_consistent_file(original, work_root):
    stop = threading.Event()
    running = threading.Event()
    failures: list[BaseException] = []
    commits: list[int] = []

    with Workspace.open(original, work_root=work_root) as workspace:

        def writer() -> None:
            try:
                with closing(sqlite3.connect(workspace.working_path, timeout=60)) as connection:
                    while not stop.is_set():
                        value = f"n{len(commits) + 1}"
                        with connection:  # two statements, one transaction: a torn copy shows as a mismatch
                            connection.execute("UPDATE library SET description = ? WHERE id = 1", (value,))
                            connection.execute("UPDATE library SET vessel_name = ? WHERE id = 1", (value,))
                        commits.append(1)
                        if len(commits) >= 5:
                            running.set()
            except BaseException as exc:
                failures.append(exc)
                running.set()

        thread = threading.Thread(target=writer)
        thread.start()
        seen = []
        try:
            assert running.wait(60)
            for _ in range(3):
                assert thread.is_alive()
                workspace.save()
                uri = f"{original.absolute().as_uri()}?mode=ro&immutable=1"
                with closing(sqlite3.connect(uri, uri=True)) as connection:
                    assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                    description, vessel = connection.execute("SELECT description, vessel_name FROM library").fetchone()
                assert description == vessel
                seen.append(int(description[1:]))
                time.sleep(0.02)
        finally:
            stop.set()
            thread.join(60)

        assert not failures
        assert seen == sorted(seen) and seen[0] >= 5  # each save is a later moment in the writer's life
        assert workspace.dirty  # the writer kept going after the last save
        workspace.save()
        assert description_of(original) == f"n{len(commits)}"


# ==========================================================================================
# CREATE
# ==========================================================================================


def test_create_writes_the_file_at_once_and_starts_clean(folder, work_root):
    target = folder / "new.pylot"
    with Workspace.create(
        target, TANKER_STL, "stern, centerline, keel", work_root=work_root, is_xz_symmetric=True
    ) as ws:
        assert target.is_file()
        assert header(target) == ROLLBACK
        assert names(folder) == ["new.pylot"]
        assert ws.path == target
        assert ws.name == "new.pylot"
        assert not ws.dirty
        assert ws.library.info.origin_description == "stern, centerline, keel"
        assert description_of(target) == ""
        with Library.open(target, read_only=True) as written:
            assert written.info.vessel_name == "tanker"
            assert len(written.base_shape.vertices) == 246

        ws.library.create_condition(z_origin=-5.0, condition_id="c1")
        assert ws.dirty
        ws.save()
        assert conditions_of(target) == ["c1"]

    assert names(folder) == ["new.pylot"]
    assert work_dirs(work_root) == []


def test_create_refuses_an_existing_path_and_leaves_no_work_dir(folder, work_root):
    target = folder / "taken.pylot"
    target.write_bytes(b"somebody's library")
    with pytest.raises(LibraryError, match="already exists"):
        Workspace.create(target, TANKER_STL, "origin", work_root=work_root, is_xz_symmetric=True)
    assert target.read_bytes() == b"somebody's library"
    assert work_dirs(work_root) == []


@pytest.mark.parametrize("problem", ["no such mesh", "not a mesh", "blank origin", "no such folder"])
def test_a_create_that_fails_leaves_nothing_behind(problem, folder, work_root):
    mesh, origin, target = TANKER_STL, "stern, centerline, keel", folder / "new.pylot"
    if problem == "no such mesh":
        mesh = folder / "missing.stl"
    elif problem == "not a mesh":
        mesh = folder / "notes.stl"
        mesh.write_text("nonsense")
    elif problem == "blank origin":
        origin = "   "
    else:
        target = folder / "not-there" / "new.pylot"

    with pytest.raises(Exception):  # noqa: B017 -- which error depends on the reader; the aftermath is the point
        Workspace.create(target, mesh, origin, work_root=work_root, is_xz_symmetric=True)

    assert not target.exists()
    assert not any(entry.name.startswith("~") or entry.suffix == ".pylot" for entry in folder.iterdir())
    assert work_dirs(work_root) == []


def test_create_does_not_overwrite_a_file_that_appears_while_it_is_being_written(folder, work_root, monkeypatch):
    target = folder / "new.pylot"
    real = Workspace._snapshot

    def snapshot_then_somebody_creates_the_file(self, stage):
        real(self, stage)
        target.write_bytes(b"created by somebody else in the meantime")

    monkeypatch.setattr(Workspace, "_snapshot", snapshot_then_somebody_creates_the_file)
    with pytest.raises(LibraryError, match="already exists"):
        Workspace.create(target, TANKER_STL, "origin", work_root=work_root, is_xz_symmetric=True)

    assert target.read_bytes() == b"created by somebody else in the meantime"
    assert names(folder) == ["new.pylot"]
    assert work_dirs(work_root) == []


# ==========================================================================================
# CLOSE AND RECOVERY
# ==========================================================================================


def test_close_deletes_the_working_copy_and_is_idempotent(original, work_root):
    before = state_of(original)
    workspace = Workspace.open(original, work_root=work_root)
    edit(workspace)
    assert workspace.dirty
    work_dir = workspace.work_dir
    assert work_dir.is_dir()

    workspace.close()

    assert workspace.closed
    assert not work_dir.exists()
    assert work_dirs(work_root) == []
    workspace.close()  # twice is fine
    assert workspace.dirty is True  # and asking afterwards does not raise
    assert state_of(original) == before  # closing never saves


def test_leaving_the_with_block_closes_the_workspace(original, work_root):
    with Workspace.open(original, work_root=work_root) as workspace:
        pass
    assert workspace.closed
    assert work_dirs(work_root) == []


def test_two_workspaces_on_the_same_file_do_not_share_a_copy(original, work_root):
    with Workspace.open(original, work_root=work_root) as one, Workspace.open(original, work_root=work_root) as two:
        assert one.work_dir != two.work_dir
        edit(one, "only in one")
        assert one.dirty
        assert not two.dirty
        assert two.library.info.description == ""


DOOMED = """
import sys, time
from pylot_bem.workspace import Workspace

workspace = Workspace.open(sys.argv[1], work_root=sys.argv[2])
workspace.library.set_info(description="written by a process that is about to be killed")
assert workspace.dirty
print("READY", flush=True)
time.sleep(600)
"""


def test_a_killed_process_leaves_its_unsaved_edits_recoverable(original, work_root):
    process = subprocess.Popen(
        [sys.executable, "-c", DOOMED, str(original), str(work_root)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    watchdog = threading.Timer(180, process.kill)
    watchdog.start()
    try:
        output = ""
        for line in process.stdout:
            output += line
            if line.strip() == "READY":
                break
        else:
            pytest.fail(f"the child process never got as far as READY:\n{output}")
        process.kill()  # no chance to close, save, or tidy anything
        process.wait(60)
    finally:
        watchdog.cancel()
        process.kill()
        process.stdout.close()

    before = state_of(original)
    deadline = time.monotonic() + 10
    while not (found := Workspace.recoverable(work_root)) and time.monotonic() < deadline:
        time.sleep(0.1)  # the operating system releases a dead process's lock a moment after it exits

    assert len(found) == 1
    assert found[0].source == original
    assert found[0].working_path.is_file()
    assert state_of(original) == before

    with Workspace.recover(found[0]) as workspace:
        assert workspace.dirty
        assert workspace.path == original
        # The commit was still in the dead process's -wal; recovering replays it.
        assert workspace.library.info.description == "written by a process that is about to be killed"
        workspace.save()
        assert description_of(original) == "written by a process that is about to be killed"

    assert work_dirs(work_root) == []


def test_a_dead_session_with_recorded_edits_is_offered_for_recovery_and_can_be_saved(original, work_root):
    workspace = Workspace.open(original, work_root=work_root)
    edit(workspace, "unsaved work")
    assert workspace.dirty
    work_dir = crash(workspace)
    before = state_of(original)

    (found,) = Workspace.recoverable(work_root)

    assert found.work_dir == work_dir
    assert found.source == original
    assert found.working_path == work_dir / "boat.pylot"
    assert found.updated is not None
    assert abs((datetime.now(UTC) - found.updated).total_seconds()) < 120
    assert state_of(original) == before  # finding it does not touch anything

    with Workspace.recover(found) as recovered:
        assert recovered.dirty  # unsaved by definition
        assert recovered.path == original
        assert recovered.library.info.description == "unsaved work"
        assert state_of(original) == before
        assert record(recovered)["dirty"] is True

        recovered.save()

        assert description_of(original) == "unsaved work"
        assert not recovered.dirty
        assert record(recovered)["dirty"] is False  # what a later crash would read
    assert work_dirs(work_root) == []


def test_a_live_session_is_not_offered_for_recovery(original, work_root):
    with Workspace.open(original, work_root=work_root) as workspace:
        edit(workspace, "in use right now")
        assert workspace.dirty

        assert Workspace.recoverable(work_root) == []
        assert Workspace.recoverable(work_root) == []  # and asking did not take the lock away

        assert workspace.work_dir.is_dir()
        workspace.save()
        assert description_of(original) == "in use right now"


def test_recoverable_on_a_root_that_does_not_exist_or_holds_strays_is_quiet(tmp_path):
    assert Workspace.recoverable(tmp_path / "never-created") == []
    root = tmp_path / "root"
    root.mkdir()
    (root / "notes.txt").write_text("not a session")
    assert Workspace.recoverable(root) == []
    assert (root / "notes.txt").exists()


def test_a_dead_session_that_recorded_no_edits_is_deleted_without_a_word(original, work_root):
    workspace = Workspace.open(original, work_root=work_root)
    workspace.dirty  # noqa: B018
    work_dir = crash(workspace)
    assert work_dir.is_dir()

    assert Workspace.recoverable(work_root) == []
    assert not work_dir.exists()


def test_a_session_that_closed_but_could_not_delete_its_folder_is_cleaned_up_later(original, work_root, monkeypatch):
    workspace = Workspace.open(original, work_root=work_root)
    edit(workspace)
    assert workspace.dirty
    with monkeypatch.context() as patched:
        patched.setattr(shutil, "rmtree", lambda *args, **kwargs: None)  # something had it open
        workspace.close()
    assert workspace.work_dir.is_dir()
    assert record(workspace)["closed"] is True

    assert Workspace.recoverable(work_root) == []  # closed on purpose: whoever closed it decided about the edits
    assert not workspace.work_dir.exists()


@pytest.mark.parametrize(
    "record_text",
    ["", "{ this is not json", '{"version": 99, "dirty": true, "name": "boat.pylot"}'],
    ids=["no record", "garbage", "unknown version"],
)
def test_a_folder_without_a_usable_record_is_deleted_once_it_is_old_enough(record_text, template, work_root):
    old = craft_session(work_root, template, source=None, record_text=record_text, age=3600)
    assert Workspace.recoverable(work_root) == []
    assert not old.exists()


@pytest.mark.parametrize("record_text", ["", "{ this is not json"], ids=["no record", "garbage"])
def test_a_folder_without_a_usable_record_that_is_very_young_is_left_alone(record_text, template, work_root):
    # It may be a session being born: the folder exists a moment before the
    # first record does, and deleting it would pull the floor from under a
    # window that is just opening.
    young = craft_session(work_root, template, source=None, record_text=record_text)
    assert Workspace.recoverable(work_root) == []
    assert young.is_dir()
    assert (young / "boat.pylot").is_file()


def test_a_record_that_says_dirty_but_whose_working_copy_is_gone_is_deleted(template, work_root, original):
    gone = craft_session(work_root, template, source=original, working=False)
    assert Workspace.recoverable(work_root) == []
    assert not gone.exists()


def test_recovering_a_session_whose_original_moved_on_makes_save_say_so(original, work_root):
    workspace = Workspace.open(original, work_root=work_root)
    edit(workspace, "unsaved work")
    assert workspace.dirty
    crash(workspace)
    someone_else_edits(original, "theirs, in the meantime")

    (found,) = Workspace.recoverable(work_root)
    with Workspace.recover(found) as recovered:
        assert recovered.dirty
        with pytest.raises(SourceChangedError):
            recovered.save()
        assert description_of(original) == "theirs, in the meantime"

        recovered.save(force=True)
        assert description_of(original) == "unsaved work"


def test_recovering_a_session_whose_original_did_not_change_saves_without_asking(original, work_root):
    workspace = Workspace.open(original, work_root=work_root)
    edit(workspace, "unsaved work")
    assert workspace.dirty
    crash(workspace)
    bump_mtime(original)  # touched, not changed

    (found,) = Workspace.recoverable(work_root)
    with Workspace.recover(found) as recovered:
        recovered.save()
    assert description_of(original) == "unsaved work"


def test_recover_is_refused_while_another_session_holds_the_folder(original, work_root):
    workspace = Workspace.open(original, work_root=work_root)
    edit(workspace)
    assert workspace.dirty
    crash(workspace)
    (found,) = Workspace.recoverable(work_root)

    with Workspace.recover(found) as first:
        with pytest.raises(WorkspaceError, match="in use"):
            Workspace.recover(found)
        assert Workspace.recoverable(work_root) == []  # it is alive, so it is not on offer either
        assert first.dirty

    assert work_dirs(work_root) == []


def test_discarding_a_recovery_removes_its_folder(original, work_root):
    workspace = Workspace.open(original, work_root=work_root)
    edit(workspace)
    assert workspace.dirty
    work_dir = crash(workspace)
    before = state_of(original)
    (found,) = Workspace.recoverable(work_root)

    assert found.discard() is True

    assert not work_dir.exists()
    assert Workspace.recoverable(work_root) == []
    assert state_of(original) == before
    assert found.discard() is True  # already gone: nothing left to do is not a failure


def test_discard_deletes_nothing_while_a_running_session_holds_the_folder(original, work_root):
    # A Recovery is a listing, and listings go stale: by the time somebody clicks
    # "discard" the session may have been picked up. It must not be able to delete
    # work another window is looking at.
    work_dir, found = abandoned(original, work_root)
    with Workspace.recover(found) as running:
        listing = names(work_dir)

        assert found.discard() is False

        assert names(work_dir) == listing
        assert running.dirty
        assert running.library.info.description == "unsaved work"
        running.save()
        assert description_of(original) == "unsaved work"

    assert not work_dir.exists()  # the session that had it closed, as it does
    assert found.discard() is True


def test_discard_deletes_nothing_while_the_session_lock_is_held_and_everything_once_it_is_not(original, work_root):
    work_dir, found = abandoned(original, work_root)
    listing = names(work_dir)
    lock = workspace_module._SessionLock.acquire(work_dir / "session.lock")
    assert lock is not None
    try:
        assert found.discard() is False
        assert names(work_dir) == listing
        assert found.working_path.is_file()
    finally:
        lock.release()

    assert found.discard() is True
    assert not work_dir.exists()


FOREIGN_NAMES = [
    "my-stuff",  # not a session name at all
    "0123456789ABCDEF0123456789ABCDEF",  # 32 hex digits, but upper case: sessions are named in lower case
    "0123456789abcdef0123456789abcde",  # one short
    "0123456789abcdef0123456789abcdef0",  # one long
    "g" * 32,  # the right length, and not hex
]


@pytest.mark.parametrize("bait", ["a session record", "nothing but age"])
def test_recoverable_reads_locks_and_deletes_nothing_that_is_not_a_session(bait, original, template, work_root):
    # PYLOT_BEM_WORK_DIR may point at a folder the user already uses. Anything in it
    # that is not named the way a session is named is not ours to look inside, lock
    # or delete -- however much it looks like a session, and however old it is.
    dirty = Workspace.open(original, work_root=work_root)
    edit(dirty)
    assert dirty.dirty
    dirty_dir = crash(dirty)
    clean = Workspace.open(original, work_root=work_root)
    clean_dir = crash(clean)  # a genuine session with nothing to lose, next to the strangers

    strangers = []
    for name in FOREIGN_NAMES:
        folder = work_root / name
        folder.mkdir()
        (folder / "notes.txt").write_text("the user's own file")
        if bait == "a session record":
            shutil.copyfile(template, folder / "boat.pylot")
            body = {"version": 1, "source": str(original), "name": "boat.pylot", "dirty": True, "closed": False}
            (folder / "session.json").write_text(json.dumps(body), encoding="utf-8")
        past = time.time() - 3600  # old enough that a session without a record would be deleted
        os.utime(folder / "notes.txt", (past, past))
        os.utime(folder, (past, past))
        strangers.append(folder)
    (work_root / "readme.txt").write_text("a plain file in the work root")
    (work_root / uuid.uuid4().hex).write_bytes(b"a plain file that is named like a session")
    strangers += [entry for entry in work_root.iterdir() if entry.is_file()]

    def state(stranger: Path):
        return tree_state(stranger) if stranger.is_dir() else state_of(stranger)

    before = {stranger: state(stranger) for stranger in strangers}

    found = Workspace.recoverable(work_root)

    assert [offered.work_dir for offered in found] == [dirty_dir]  # the genuine session is handled as always
    assert not clean_dir.exists()
    # Contents and modification times, and no session.lock dropped into any of them.
    assert {stranger: state(stranger) for stranger in strangers} == before
    assert not [entry for stranger in strangers if stranger.is_dir() for entry in stranger.rglob("session.lock")]


LOST_FINGERPRINTS = {
    "missing": lambda data: data.pop("fingerprint"),
    "null": lambda data: data.update(fingerprint=None),
    "garbled": lambda data: data.update(fingerprint={"main": 5}),
    "wrong types": lambda data: data.update(fingerprint={"main": {"size": "many", "mtime_ns": 1, "sha256": "x"}}),
}


@pytest.mark.parametrize("how", LOST_FINGERPRINTS)
def test_a_recovery_that_lost_its_fingerprint_asks_before_saving_over_an_original_that_is_there(
    how, original, folder, work_root
):
    # Without the baseline there is no way to know whether the original moved on, so
    # the answer cannot be "no": the first Save says so and lets a person choose.
    # Skipping the check would be the quiet way to overwrite somebody's work.
    _, found = abandoned(original, work_root, damage_record=LOST_FINGERPRINTS[how])
    assert found.fingerprint is None
    assert found.source == original
    before = state_of(original)

    with Workspace.recover(found) as recovered:
        assert recovered.dirty
        with pytest.raises(SourceChangedError) as caught:
            recovered.save()

        assert caught.value.path == original
        assert state_of(original) == before  # the original is exactly as it was; only the evidence is missing
        assert names(folder) == ["boat.pylot"]

        recovered.save(force=True)
        assert description_of(original) == "unsaved work"

        edit(recovered, "and more")
        recovered.save()  # what force wrote is a baseline again
        assert description_of(original) == "and more"


@pytest.mark.parametrize("how", ["missing", "garbled"])
def test_a_recovery_that_lost_its_fingerprint_recreates_an_original_that_is_gone(how, original, folder, work_root):
    _, found = abandoned(original, work_root, damage_record=LOST_FINGERPRINTS[how])
    original.unlink()

    with Workspace.recover(found) as recovered:
        recovered.save()  # nothing there to overwrite, so nothing to ask about

    assert description_of(original) == "unsaved work"
    assert header(original) == ROLLBACK
    assert names(folder) == ["boat.pylot"]


def test_the_unknown_baseline_of_a_recovery_survives_another_crash(original, work_root):
    _, found = abandoned(original, work_root, damage_record=LOST_FINGERPRINTS["missing"])
    crash(Workspace.recover(found))

    (again,) = Workspace.recoverable(work_root)
    with Workspace.recover(again) as second:
        with pytest.raises(SourceChangedError):
            second.save()  # still not a baseline it can trust
        second.save(force=True)
        assert description_of(original) == "unsaved work"


@pytest.mark.parametrize("kind", ["ordinary", "legacy"])
def test_a_recovery_carries_the_fingerprint_its_session_recorded_and_saves_against_it(kind, request, work_root):
    source = request.getfixturevalue("legacy" if kind == "legacy" else "original")
    wal = source.with_name("boat.pylot-wal")
    expected = Fingerprint(Stamp.of(source), Stamp.of(wal) if kind == "legacy" else None)

    _, found = abandoned(source, work_root)

    assert found.fingerprint == expected
    with Workspace.recover(found) as recovered:
        bump_mtime(source)  # touched, not changed: the recorded content decides
        recovered.save()
        assert description_of(source) == "unsaved work"
        assert names(source.parent) == ["boat.pylot"]


@pytest.mark.parametrize("given", ["a fingerprint that matches nothing", "no fingerprint"])
def test_recover_compares_against_the_recovery_it_is_handed(given, original, work_root):
    # What the record on disk says is beside the point: the Recovery is the contract.
    _, found = abandoned(original, work_root)
    assert found.fingerprint is not None
    handed = replace(found, fingerprint=Fingerprint(Stamp(1, 2, "not this file")) if "matches" in given else None)

    with Workspace.recover(handed) as recovered:
        with pytest.raises(SourceChangedError):
            recovered.save()
        assert description_of(original) == ""


def test_a_working_copy_that_will_not_open_is_left_for_salvage_and_can_be_offered_again(template, original, work_root):
    broken = craft_session(work_root, template, source=original)
    (broken / "boat.pylot").write_text("what a disk error made of it\n" * 20)
    (found,) = Workspace.recoverable(work_root)

    with pytest.raises(LibraryError):
        Workspace.recover(found)

    assert (broken / "boat.pylot").is_file()  # nothing was deleted
    assert Workspace.recoverable(work_root) == [found]  # and the lock was let go


def test_a_recovered_session_that_never_had_a_file_saves_only_as(template, folder, work_root):
    craft_session(work_root, template, source=None)
    (found,) = Workspace.recoverable(work_root)
    assert found.source is None

    with Workspace.recover(found) as recovered:
        assert recovered.dirty
        assert recovered.path is None
        assert recovered.name == "boat.pylot"
        with pytest.raises(WorkspaceError, match="save_as"):
            recovered.save()

        target = folder / "rescued.pylot"
        recovered.save_as(target)
        assert not recovered.dirty
        assert recovered.path == target
        assert conditions_of(target) == []
        assert description_of(target) == ""
        recovered.save()  # and from now on it is an ordinary workspace


# ==========================================================================================
# FINGERPRINT AND STAMP
# ==========================================================================================


@pytest.fixture
def watched(tmp_path) -> Path:
    path = tmp_path / "watched.bin"
    path.write_bytes(b"the original content")
    return path


def fingerprint_of(path: Path, *, wal: bool = False) -> Fingerprint:
    return Fingerprint(Stamp.of(path), Stamp.of(path.with_name(path.name + "-wal")) if wal else None)


def test_a_file_that_has_not_changed_checks_out_as_the_same_fingerprint(watched):
    fingerprint = fingerprint_of(watched)
    assert fingerprint.check(watched) is fingerprint


def test_a_file_that_was_only_touched_checks_out_with_a_refreshed_fingerprint(watched):
    fingerprint = fingerprint_of(watched)
    bump_mtime(watched)

    refreshed = fingerprint.check(watched)

    assert refreshed is not None
    assert refreshed is not fingerprint
    assert refreshed.main.mtime_ns == watched.stat().st_mtime_ns
    assert refreshed.main.sha256 == fingerprint.main.sha256
    assert refreshed.check(watched) is refreshed  # so the next check is the cheap one again


@pytest.mark.parametrize("new_content", [b"the original content, extended", b"the original c0ntent"])
def test_a_file_whose_content_changed_is_a_change(watched, new_content):
    fingerprint = fingerprint_of(watched)
    watched.write_bytes(new_content)  # once with a different size, once with the same size
    bump_mtime(watched)
    assert fingerprint.check(watched) is None


def test_a_file_of_a_different_size_is_a_change_even_if_its_modification_time_was_put_back(watched, monkeypatch):
    # Size and modification time are only the cheap first look. A different size is
    # settled by content -- and is a change, whatever the clock on the file says.
    fingerprint = fingerprint_of(watched)
    hashed = []
    real = workspace_module._hash_file
    monkeypatch.setattr(workspace_module, "_hash_file", lambda path: (hashed.append(path), real(path))[1])
    assert fingerprint.check(watched) is fingerprint
    assert hashed == []  # the cheap look was enough

    watched.write_bytes(b"something else, and a good deal longer than before")
    os.utime(watched, ns=(watched.stat().st_atime_ns, fingerprint.main.mtime_ns))
    assert watched.stat().st_mtime_ns == fingerprint.main.mtime_ns
    assert watched.stat().st_size != fingerprint.main.size

    assert fingerprint.check(watched) is None
    assert hashed == [watched]  # and it was the content that said so


def test_a_file_that_is_gone_is_not_a_change(watched):
    fingerprint = fingerprint_of(watched)
    watched.unlink()
    assert fingerprint.check(watched) is fingerprint


def test_a_wal_that_appeared_beside_the_file_is_a_change(watched):
    fingerprint = fingerprint_of(watched)
    watched.with_name("watched.bin-wal").write_bytes(b"commits somebody else made")
    assert fingerprint.check(watched) is None


def test_an_empty_wal_beside_the_file_says_nothing(watched):
    fingerprint = fingerprint_of(watched)
    watched.with_name("watched.bin-wal").write_bytes(b"")
    assert fingerprint.check(watched) is fingerprint


def test_a_recorded_wal_that_is_unchanged_touched_altered_or_gone(watched):
    wal = watched.with_name("watched.bin-wal")
    wal.write_bytes(b"commits that were in the wal when we copied")
    fingerprint = fingerprint_of(watched, wal=True)
    assert fingerprint.check(watched) is fingerprint

    bump_mtime(wal)
    refreshed = fingerprint.check(watched)
    assert refreshed is not None
    assert refreshed.wal is not None
    assert refreshed.wal.mtime_ns == wal.stat().st_mtime_ns
    assert refreshed.wal.sha256 == fingerprint.wal.sha256

    wal.write_bytes(b"commits that were in the wal when we copied, and more")
    assert fingerprint.check(watched) is None

    wal.unlink()
    assert fingerprint.check(watched) is None


def test_a_stamp_matches_the_stat_it_was_taken_from_until_the_file_moves_on(watched):
    stamp = Stamp.of(watched)
    assert stamp.matches(watched.stat())
    assert not stamp.matches(None)
    bump_mtime(watched)
    assert not stamp.matches(watched.stat())


def test_a_stamp_can_take_its_hash_from_the_bytes_that_were_copied(watched):
    stamp = Stamp.of(watched, "0" * 64)
    assert stamp.sha256 == "0" * 64
    assert stamp.size == watched.stat().st_size


@pytest.mark.parametrize("with_wal", [False, True])
def test_a_fingerprint_survives_a_round_trip_through_json(watched, with_wal):
    if with_wal:
        watched.with_name("watched.bin-wal").write_bytes(b"wal")
    fingerprint = fingerprint_of(watched, wal=with_wal)
    restored = Fingerprint.from_json(json.loads(json.dumps(fingerprint.to_json())))
    assert restored == fingerprint
    assert (restored.wal is not None) is with_wal


@pytest.mark.parametrize(
    "garbage",
    [
        None,
        {},
        [],
        "main",
        42,
        [1, 2],
        {"wal": None},
        {"main": None},
        {"main": 5},
        {"main": {}},
        {"main": {"size": "many", "mtime_ns": 1, "sha256": "x"}},
        {"main": {"size": None, "mtime_ns": 1, "sha256": "x"}},
        {"main": {"size": 1, "mtime_ns": 1, "sha256": "x"}, "wal": {"size": 1}},
    ],
)
def test_a_fingerprint_that_cannot_be_read_back_is_none_rather_than_an_error(garbage):
    assert Fingerprint.from_json(garbage) is None


# ==========================================================================================
# MISC
# ==========================================================================================


def test_default_work_root_honours_the_environment_override(tmp_path, monkeypatch):
    monkeypatch.setenv(WORK_DIR_ENV, str(tmp_path / "elsewhere"))
    assert default_work_root() == tmp_path / "elsewhere"


def test_default_work_root_is_a_per_user_pylot_bem_work_folder_otherwise(tmp_path, monkeypatch):
    monkeypatch.delenv(WORK_DIR_ENV, raising=False)
    if sys.platform == "win32":
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    elif sys.platform != "darwin":
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    root = default_work_root()
    assert root.parts[-2:] == ("pylot-bem", "work")
    if sys.platform != "darwin":
        assert root == tmp_path / "pylot-bem" / "work"


def test_an_empty_override_is_no_override(tmp_path, monkeypatch):
    monkeypatch.setenv(WORK_DIR_ENV, "")
    assert default_work_root().parts[-2:] == ("pylot-bem", "work")


# -- Pylot.close ----------------------------------------------------------------------------


def test_closing_a_library_that_was_written_in_wal_mode_leaves_one_ordinary_file(tmp_path):
    path = tmp_path / "written.pylot"
    library = Pylot.create(
        path,
        vessel_name="Boxboat",
        origin_description="o",
        vertices=BOX_VERTICES,
        faces=BOX_FACES,
        is_xz_symmetric=True,
    )
    library.create_condition(z_origin=-4.0, condition_id="c1")
    assert len(names(tmp_path)) > 1  # while it is open there are -wal and -shm beside it

    library.close()

    assert names(tmp_path) == ["written.pylot"]
    assert header(path) == ROLLBACK
    assert conditions_of(path) == ["c1"]  # and the commits that were in the -wal are in the file
    assert names(tmp_path) == ["written.pylot"]  # reading it back added nothing


def test_the_context_manager_closes_the_same_way(tmp_path):
    path = make_box(tmp_path / "boat.pylot")
    with Pylot.open(path) as library:
        library.set_info(description="written")
    assert names(tmp_path) == ["boat.pylot"]
    assert header(path) == ROLLBACK


def test_close_with_another_connection_open_does_not_raise_and_leaves_the_other_working(tmp_path):
    path = make_box(tmp_path / "boat.pylot")
    first = Pylot.open(path)
    second = Pylot.open(path)
    first.set_info(description="written by the first")

    first.close()  # the file cannot be converted while the second is open; that is not an error

    assert second.info.description == "written by the first"  # the other connection is untouched

    second.close()  # the last one out converts the file
    assert names(tmp_path) == ["boat.pylot"]
    assert header(path) == ROLLBACK
    assert description_of(path) == "written by the first"


def test_closing_a_read_only_library_does_not_touch_the_file(tmp_path):
    path = make_box(tmp_path / "boat.pylot")
    before = state_of(path)
    with Pylot.open(path, read_only=True) as library:
        assert library.info.vessel_name == "Boxboat"
    assert state_of(path) == before
    assert names(tmp_path) == ["boat.pylot"]


def test_closing_a_read_only_library_does_not_convert_a_wal_file(tmp_path, template):
    path = tmp_path / "boat.pylot"
    shutil.copyfile(template, path)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
    assert header(path) == WAL
    before = state_of(path)

    with Pylot.open(path, read_only=True) as library:
        library.info  # noqa: B018

    assert header(path) == WAL
    assert state_of(path) == before
    assert names(tmp_path) == ["boat.pylot"]


def test_closing_twice_is_fine(tmp_path):
    library = Pylot.create(
        tmp_path / "twice.pylot",
        vessel_name="Boxboat",
        origin_description="o",
        vertices=BOX_VERTICES,
        faces=BOX_FACES,
        is_xz_symmetric=True,
    )
    library.close()
    library.close()
    read_only = Pylot.open(tmp_path / "twice.pylot", read_only=True)
    read_only.close()
    read_only.close()


def test_nothing_is_left_holding_a_file_after_everything_a_workspace_does(original, work_root):
    # The last word on "no handle left": on Windows a leaked handle would
    # refuse the deletes.
    copy = original.with_name("copy.pylot")
    with Workspace.open(original, work_root=work_root) as workspace:
        edit(workspace)
        workspace.save()
        workspace.save_as(copy)
    original.unlink()
    copy.unlink()
    assert work_dirs(work_root) == []


# -- the sidecars are set aside for one attempt at a time ---------------------------------------


def test_between_attempts_the_sidecars_are_back_where_they_were(legacy, folder, work_root, monkeypatch):
    # Waiting seconds for a scanner to let go of the file must not mean seconds
    # with the library's -wal missing from its folder: if anything happened to the
    # process then, the commits that live only in it would be somewhere nobody
    # looks. They are set aside for the length of one attempt and put straight back.
    with_stale_sidecars(folder)
    monkeypatch.setattr(workspace_module, "REPLACE_BUDGET", 5.0)
    attempts = []

    def swap(source, destination):
        if destination != legacy:
            return False
        attempts.append(1)
        return len(attempts) <= 3  # the first three swaps of the main file are refused

    refuse_replace(monkeypatch, swap)
    seen_while_waiting = []
    monkeypatch.setattr(workspace_module.time, "sleep", lambda seconds: seen_while_waiting.append(names(folder)))

    with Workspace.open(legacy, work_root=work_root) as workspace:
        workspace.library.create_condition(z_origin=-8.0, condition_id="new")
        workspace.save()

    assert len(attempts) == 4
    assert len(seen_while_waiting) == 3
    for listing in seen_while_waiting:
        assert {"boat.pylot", "boat.pylot-journal", "boat.pylot-shm", "boat.pylot-wal"} <= set(listing)
        # The only ~file is the copy waiting to be swapped in; none of the sidecars is set aside.
        (waiting,) = (name for name in listing if name.startswith("~"))
        assert waiting.startswith("~boat.pylot.") and waiting.endswith(".tmp")
    assert names(folder) == ["boat.pylot"]
    assert main_file_conditions(legacy) == ["new", "old"]


def test_a_sidecar_that_is_only_briefly_unmovable_is_waited_for(legacy, folder, work_root, monkeypatch):
    with_stale_sidecars(folder)
    monkeypatch.setattr(workspace_module, "REPLACE_BUDGET", 5.0)
    wal = folder / "boat.pylot-wal"
    refused = refuse_replace(monkeypatch, lambda source, destination: source == wal and len(refused) < 2)
    monkeypatch.setattr(workspace_module.time, "sleep", lambda seconds: None)

    with Workspace.open(legacy, work_root=work_root) as workspace:
        edit(workspace, "mine")
        workspace.save()  # a virus scanner had the -wal for two attempts, then let go

    assert description_of(legacy) == "mine"
    assert main_file_conditions(legacy) == ["old"]
    assert names(folder) == ["boat.pylot"]


def test_an_interrupt_half_way_through_setting_the_sidecars_aside_puts_the_first_back(
    legacy, folder, work_root, monkeypatch
):
    # Ctrl+C is not an OSError. Whatever had already been moved when it arrived is
    # the caller's to put back, and the caller has to know about it.
    with_stale_sidecars(folder)
    shm = folder / "boat.pylot-shm"
    real = os.replace

    def interrupted(source, destination, *args, **kwargs):
        if Path(source) == shm:
            raise KeyboardInterrupt
        return real(source, destination, *args, **kwargs)

    with Workspace.open(legacy, work_root=work_root) as workspace:
        edit(workspace, "mine")
        before = {entry.name: state_of(entry) for entry in folder.iterdir()}
        monkeypatch.setattr(os, "replace", interrupted)
        with pytest.raises(KeyboardInterrupt):
            workspace.save()
        monkeypatch.setattr(os, "replace", real)

        assert {entry.name: state_of(entry) for entry in folder.iterdir()} == before
        assert leftovers(folder) == []
        assert workspace.dirty
        workspace.save()
        assert description_of(legacy) == "mine"


def test_putting_a_sidecar_back_never_overwrites_a_file_that_appeared_in_its_place(tmp_path):
    aside, side = tmp_path / "~boat.pylot-wal.deadbeef.tmp", tmp_path / "boat.pylot-wal"
    aside.write_bytes(b"ours")
    side.write_bytes(b"theirs, created while the save was waiting")
    workspace_module._restore_sidecars([(aside, side)])
    assert side.read_bytes() == b"theirs, created while the save was waiting"
    assert aside.read_bytes() == b"ours"  # left for whoever needs it


def test_a_sidecar_is_put_back_when_nothing_is_in_its_place(tmp_path):
    aside, side = tmp_path / "~boat.pylot-wal.deadbeef.tmp", tmp_path / "boat.pylot-wal"
    aside.write_bytes(b"ours")
    workspace_module._restore_sidecars([(aside, side)])
    assert side.read_bytes() == b"ours"
    assert not aside.exists()


def test_a_modification_time_that_moves_while_save_waits_costs_one_hash_not_one_per_attempt(
    original, work_root, monkeypatch
):
    monkeypatch.setattr(workspace_module, "REPLACE_BUDGET", 5.0)
    monkeypatch.setattr(workspace_module.time, "sleep", lambda seconds: None)
    hashed = []
    real_hash = workspace_module._hash_file
    monkeypatch.setattr(workspace_module, "_hash_file", lambda path: hashed.append(path) or real_hash(path))
    attempts = []

    def swap(source, destination):
        if destination != original:
            return False
        attempts.append(1)
        if len(attempts) == 1:
            bump_mtime(original)  # a sync client touched it; not a byte changed
        return len(attempts) <= 4

    refuse_replace(monkeypatch, swap)
    with Workspace.open(original, work_root=work_root) as workspace:
        edit(workspace, "mine")
        workspace.save()

    assert len(attempts) == 5
    assert hashed == [original]
    assert description_of(original) == "mine"


# -- leftovers of a Save that died --------------------------------------------------------------


def age(path: Path, seconds: float) -> None:
    old = time.time() - seconds
    os.utime(path, (old, old))


def test_the_next_save_sweeps_the_half_copies_an_earlier_one_left_and_only_those(original, folder, work_root):
    stale = folder / "~boat.pylot.deadbeef.tmp"
    young = folder / "~boat.pylot.cafef00d.tmp"
    someone_elses = folder / "~other.pylot.deadbeef.tmp"
    moved_wal = folder / "~boat.pylot-wal.deadbeef.tmp"  # may hold the only copy of some commits
    not_ours = folder / "~boat.pylot.deadbeef.txt"
    for leftover in (stale, young, someone_elses, moved_wal, not_ours):
        leftover.write_bytes(b"x")
    for leftover in (stale, someone_elses, moved_wal, not_ours):
        age(leftover, 3600)

    with Workspace.open(original, work_root=work_root) as workspace:
        edit(workspace, "mine")
        workspace.save()

    assert not stale.exists()
    assert young.exists()  # another window may be writing it right now
    assert someone_elses.exists()
    assert moved_wal.exists()
    assert not_ours.exists()


# -- other things the review turned up ------------------------------------------------------------


def test_a_wal_that_vanishes_while_the_fingerprint_is_checked_is_a_change_not_an_error(legacy, monkeypatch):
    fingerprint = Fingerprint(Stamp.of(legacy), Stamp.of(legacy.with_name("boat.pylot-wal")))
    bump_mtime(legacy)  # forces the content check, which is where the -wal is stamped

    def vanished(cls, path, sha256=None):
        raise FileNotFoundError(path)

    monkeypatch.setattr(Stamp, "of", classmethod(vanished))
    assert fingerprint.check(legacy) is None


def test_a_document_keeps_the_name_it_was_opened_by_when_that_is_a_link(template, tmp_path, work_root, monkeypatch):
    # An editor saving through a symbolic link goes on calling the document by the
    # link's name: the title bar, the recent files and the next Save all follow it.
    real_dir, link_dir = tmp_path / "real", tmp_path / "links"
    real_dir.mkdir()
    link_dir.mkdir()
    target, link = real_dir / "boat.pylot", link_dir / "boat.pylot"
    shutil.copyfile(template, target)
    shutil.copyfile(template, link)
    real_is_symlink, real_realpath = Path.is_symlink, os.path.realpath
    monkeypatch.setattr(Path, "is_symlink", lambda self: self == link or real_is_symlink(self))
    monkeypatch.setattr(
        os.path, "realpath", lambda path, *a, **k: str(target) if Path(path) == link else real_realpath(path, *a, **k)
    )

    with Workspace.open(link, work_root=work_root) as workspace:
        edit(workspace, "first")
        workspace.save()
        assert workspace.path == link
        edit(workspace, "second")
        workspace.save()  # the second Save follows the link too, and finds the file it wrote
        assert workspace.path == link

    assert description_of(target) == "second"
