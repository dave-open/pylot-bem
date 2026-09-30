"""A library open for editing, the way a text editor opens a file.

A ``.pylot`` file is one SQLite database, and SQLite is at its best on a disk
that only one program uses. It is at its worst in a folder a sync client
(Nextcloud, OneDrive) is watching: WAL mode leaves ``-wal`` and ``-shm`` files
beside the library for as long as it is open, the client uploads them half
written, and two copies of a database that disagree about which frames are in
the log are a corrupted database.

So the file a person chose is never opened for editing. :class:`Workspace`
makes a private copy in a local folder, everything happens to the copy, and
**Save** is the only moment the original is touched::

    with Workspace.open("tanker.pylot") as w:
        w.library.create_condition(z_origin=-5.0)   # a Pylot, on the copy
        w.dirty                                      # True
        w.save()                                     # tanker.pylot replaced

What Save does, and why each step is there:

1. ``VACUUM INTO`` a staging file. One consistent snapshot of the copy even
   while a batch is committing to it, and the result is a plain rollback-mode
   file with no ``-wal`` -- unlike ``Connection.backup``, which keeps the WAL
   flag in the header, and unlike copying the file, which silently loses
   whatever is still only in the ``-wal``.
2. Verify the staging file before it can go anywhere near the original.
3. Copy it into the destination folder under a temporary name and ``fsync``.
4. Check that the original is still what it was when this workspace was
   opened. Compared by size and modification time first; a mismatch there is
   settled by content, because a sync client rewrites modification times
   without changing a byte.
5. ``os.replace``, retried for a few seconds: on Windows it fails for as long
   as anything -- an antivirus scanner, a sync client, DAVE -- has the original
   open.

The original is therefore either the old file or the whole new one, never
half of anything, and nothing has an open handle on it between saves.

The copy is kept in WAL mode: it lives in a private local folder where the
sidecars hurt nobody, and the batch screen depends on a writer and a reader
coexisting.

**Crash recovery.** With an explicit Save, hours of batch results exist only in
the copy until somebody saves. The copy therefore lives in a folder that
survives the process (:func:`default_work_root`), with a small session record
beside it, and a lock the operating system releases when the process dies
however it dies. :meth:`Workspace.recoverable` finds the sessions whose owner
is gone and that held unsaved work; :meth:`Workspace.recover` picks one up.
"""

import contextlib
import gc
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import threading
import time
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Self

from pylot_db.storage import Library, LibraryError

from pylot_bem.api import Pylot

__all__ = [
    "REPLACE_BUDGET",
    "WORK_DIR_ENV",
    "Fingerprint",
    "Recovery",
    "SourceChangedError",
    "SourceLockedError",
    "Stamp",
    "Workspace",
    "WorkspaceError",
    "default_work_root",
]

#: Environment variable that moves the working copies somewhere else -- another
#: drive for very large libraries, or a temporary folder for a test run.
WORK_DIR_ENV = "PYLOT_BEM_WORK_DIR"

#: How long Save keeps trying to swap the new file in while something else has
#: the old one open, in seconds. Long enough to outlast a scanner or a sync
#: client's momentary hold, short enough that a window does not look hung.
REPLACE_BUDGET = 8.0

_CHUNK = 1024 * 1024
_RECORD = "session.json"
_LOCK = "session.lock"
_RECORD_VERSION = 1
#: A session folder younger than this with no record yet is a session being
#: born, not one that died.
_YOUNG = 60.0
#: A half-copied ``~name.<token>.tmp`` older than this (seconds) is a Save that died.
_STALE_AFTER = 600.0
_SQLITE_HEADER = b"SQLite format 3\x00"
#: What a session folder is called (:func:`_new_session`). Nothing else in the work
#: root is ours to read, lock or delete -- it may be a folder the user already had.
_SESSION_DIR = re.compile(r"[0-9a-f]{32}")


def default_work_root() -> Path:
    r"""Where working copies live.

    Not the system temporary folder: that is cleaned at boot on some systems,
    and these copies are what a crash recovers from. Not beside the library
    either -- that is the synced folder this exists to stay out of.

    ``%LOCALAPPDATA%\\pylot-bem\\work`` on Windows, ``~/Library/Application
    Support/pylot-bem/work`` on macOS, ``$XDG_STATE_HOME/pylot-bem/work`` (or
    ``~/.local/state``) elsewhere. :data:`WORK_DIR_ENV` overrides all of them.
    """
    override = os.environ.get(WORK_DIR_ENV)
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    return base / "pylot-bem" / "work"


class WorkspaceError(LibraryError):
    """Opening or saving failed for a reason a person can act on.

    A :class:`~pylot_db.storage.LibraryError`, so everything that already
    reports a library that will not open reports these too. The message is
    written to be shown as it stands.
    """


class SourceChangedError(WorkspaceError):
    """The file on disk is no longer the one this workspace was opened from.

    Saving would throw the other change away. What to do about that is the
    user's decision: :meth:`Workspace.save` with ``force=True`` overwrites it,
    :meth:`Workspace.save_as` keeps both.
    """

    def __init__(self, path: Path) -> None:
        super().__init__(f"{path} has been changed by someone else since it was opened; saving would overwrite that")
        self.path = path


class SourceLockedError(WorkspaceError):
    """The file cannot be replaced right now.

    Another program has it open -- on Windows a file cannot be replaced while
    anything holds it -- or it is read-only. Nothing was written, and the
    workspace still holds every change: try again, or save somewhere else.
    """

    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f"{path} {reason}")
        self.path = path
        self.reason = reason


# -- knowing whether a file has changed ---------------------------------------


def _sidecar(path: Path, suffix: str) -> Path:
    return path.with_name(path.name + suffix)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_hashing(source: Path, target: Path, *, sync: bool = False) -> str:
    """Copy ``source`` to ``target`` in one pass and return its SHA-256.

    Hashing while copying costs almost nothing over the copy itself, and it is
    the only way to hash what was *copied* rather than what the file has since
    become.
    """
    digest = hashlib.sha256()
    with source.open("rb") as reading, target.open("wb") as writing:
        while chunk := reading.read(_CHUNK):
            writing.write(chunk)
            digest.update(chunk)
        if sync:
            writing.flush()
            os.fsync(writing.fileno())
    return digest.hexdigest()


def _live_wal(path: Path) -> os.stat_result | None:
    """``path``'s ``-wal`` if there is one holding anything.

    An empty ``-wal`` is what a clean close leaves behind on some platforms
    and says nothing; only one with content can hold commits the main file
    does not have.
    """
    try:
        info = _sidecar(path, "-wal").stat()
    except OSError:
        return None
    return info if info.st_size > 0 else None


@dataclass(frozen=True)
class Stamp:
    """What one file looked like: enough to tell later whether it has changed."""

    size: int
    mtime_ns: int
    sha256: str

    @classmethod
    def of(cls, path: Path, sha256: str | None = None) -> Self:
        info = path.stat()
        return cls(info.st_size, info.st_mtime_ns, sha256 if sha256 is not None else _hash_file(path))

    def to_json(self) -> dict:
        return {"size": self.size, "mtime_ns": self.mtime_ns, "sha256": self.sha256}

    @classmethod
    def from_json(cls, data: dict) -> Self:
        return cls(int(data["size"]), int(data["mtime_ns"]), str(data["sha256"]))

    def matches(self, info: os.stat_result | None) -> bool:
        return info is not None and (info.st_size, info.st_mtime_ns) == (self.size, self.mtime_ns)


@dataclass(frozen=True)
class Fingerprint:
    """What the original was when the workspace last read or wrote it.

    ``wal`` is only ever set for a library written by an older version, whose
    original had a ``-wal`` beside it holding commits: those are part of what
    the workspace copied, so a *different* ``-wal`` later means somebody else
    has been writing.
    """

    main: Stamp
    wal: Stamp | None = None

    def to_json(self) -> dict:
        return {"main": self.main.to_json(), "wal": self.wal.to_json() if self.wal else None}

    @classmethod
    def from_json(cls, data: dict | None) -> Self | None:
        if not data:
            return None
        try:
            return cls(Stamp.from_json(data["main"]), Stamp.from_json(data["wal"]) if data.get("wal") else None)
        except KeyError, TypeError, ValueError:
            return None

    def check(self, path: Path) -> Self | None:
        """This fingerprint, refreshed, if ``path`` still holds what it recorded.

        ``None`` means the content is different. A file that has gone is *not*
        different: there is nothing there to overwrite, and Save writes it
        again.

        Size and modification time are compared first because they are free.
        When they differ the content is hashed before anything is reported,
        since a sync client can change a modification time without changing a
        byte, and an alarm about a change that is not one teaches people to
        click through the real ones.
        """
        try:
            info = path.stat()
        except FileNotFoundError:
            return self
        wal_info = _live_wal(path)
        wal_same = (wal_info is None and self.wal is None) or (self.wal is not None and self.wal.matches(wal_info))
        if self.main.matches(info) and wal_same:
            return self

        digest = _hash_file(path)
        if digest != self.main.sha256:
            return None
        wal = None
        if wal_info is not None:
            # Gone again since it was looked at (the last connection closed): that is
            # a change too, and is reported as one below rather than raised.
            with contextlib.suppress(FileNotFoundError):
                wal = Stamp.of(_sidecar(path, "-wal"))
        if wal is None or self.wal is None:
            if wal is not self.wal:
                return None
        elif wal.sha256 != self.wal.sha256:
            return None
        return type(self)(Stamp(info.st_size, info.st_mtime_ns, digest), wal)


#: The baseline for a recovered session whose record lost it. Nothing on disk can
#: match it, so the first Save reports the original as changed and lets a person
#: choose -- rather than skipping the check because the evidence went missing.
_UNKNOWN = Fingerprint(Stamp(-1, -1, ""))


# -- the session lock and record ------------------------------------------------


if sys.platform == "win32":
    import msvcrt

    def _try_lock(handle) -> bool:
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    def _unlock(handle) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _try_lock(handle) -> bool:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        return True

    def _unlock(handle) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class _SessionLock:
    """An exclusive lock a live session holds on its own folder.

    Whether a session is still alive is asked of the operating system rather
    than of a process id: an id can be reused by an unrelated program, and a
    lock cannot outlive the process that took it, however that process died.
    """

    def __init__(self, handle) -> None:
        self._handle = handle

    @classmethod
    def acquire(cls, path: Path) -> Self | None:
        """The lock, or ``None`` if a live session already holds it."""
        handle = path.open("a+b")
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"L")
                handle.flush()
            if not _try_lock(handle):
                handle.close()
                return None
        except BaseException:
            handle.close()
            raise
        return cls(handle)

    def release(self) -> None:
        if self._handle is None:
            return
        with contextlib.suppress(OSError):
            _unlock(self._handle)
        self._handle.close()
        self._handle = None


def _write_record(work_dir: Path, record: dict) -> None:
    """Write the session record whole or not at all, so a crash cannot tear it."""
    staging = work_dir / f"{_RECORD}.tmp"
    with staging.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(record, indent=2))
        handle.flush()
        # Not just against a crash of this process: a rename can outlive the data
        # it points at across a power cut, leaving a record that reads as empty.
        os.fsync(handle.fileno())
    os.replace(staging, work_dir / _RECORD)


def _read_record(work_dir: Path) -> dict | None:
    try:
        data = json.loads((work_dir / _RECORD).read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None
    return data if isinstance(data, dict) and data.get("version") == _RECORD_VERSION else None


def _new_session(work_root: str | Path | None) -> tuple[Path, _SessionLock]:
    root = Path(work_root) if work_root is not None else default_work_root()
    work_dir = root / uuid.uuid4().hex
    work_dir.mkdir(parents=True)
    lock = _SessionLock.acquire(work_dir / _LOCK)
    if lock is None:  # a fresh random name cannot be held by anyone
        shutil.rmtree(work_dir, ignore_errors=True)
        raise WorkspaceError(f"could not lock the working folder {work_dir}")
    return work_dir, lock


def _copy_source(source: Path, working: Path) -> Fingerprint:
    """Copy a library for editing, along with anything that belongs to it.

    A library written by an older version can have a ``-wal`` beside it with
    commits the main file does not have yet. Copying the main file alone
    silently loses them, so a non-empty ``-wal`` is copied too and SQLite
    replays it when the copy is opened -- the original is only ever read.

    The copy is repeated if the original changes while it is being read; a
    file that will not keep still is not one to work on.
    """
    working_wal = _sidecar(working, "-wal")
    for _ in range(3):
        before = source.stat()
        wal_before = _live_wal(source)
        working_wal.unlink(missing_ok=True)
        digest = _copy_hashing(source, working)
        wal_digest = _copy_hashing(_sidecar(source, "-wal"), working_wal) if wal_before is not None else None
        after = source.stat()
        wal_after = _live_wal(source)
        same_wal = (wal_before is None and wal_after is None) or (
            wal_before is not None
            and wal_after is not None
            and (wal_before.st_size, wal_before.st_mtime_ns) == (wal_after.st_size, wal_after.st_mtime_ns)
        )
        if (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns) and same_wal:
            wal = None
            if wal_before is not None and wal_digest is not None:
                wal = Stamp(wal_before.st_size, wal_before.st_mtime_ns, wal_digest)
            return Fingerprint(Stamp(before.st_size, before.st_mtime_ns, digest), wal)
    raise WorkspaceError(f"{source} keeps changing while it is being copied; is another program writing to it?")


@dataclass(frozen=True)
class Recovery:
    """Unsaved work a previous session left behind when it died.

    Attributes:
        work_dir: The dead session's folder.
        source: The file the work was being done on.
        working_path: The working copy inside ``work_dir``.
        updated: When the session last recorded its state.
        fingerprint: What the original was when that session last read or wrote it.
    """

    work_dir: Path
    source: Path | None
    working_path: Path
    updated: datetime | None
    fingerprint: Fingerprint | None = None

    def discard(self) -> bool:
        """Throw the work away.

        Returns:
            ``False``, and deletes nothing, if a running session has taken the
            folder since it was listed -- a stale :class:`Recovery` must not be
            able to delete work somebody is looking at.
        """
        if not self.work_dir.is_dir():
            return True
        lock = _SessionLock.acquire(self.work_dir / _LOCK)
        if lock is None:
            return False
        try:
            # Everything but the lock goes while it is still held. Letting go first
            # would let a session that is being recovered at this moment lose its
            # record to the deletion and then be unrecoverable if it crashed too.
            for entry in self.work_dir.iterdir():
                if entry.name == _LOCK:
                    continue
                if entry.is_dir() and not entry.is_symlink():
                    shutil.rmtree(entry, ignore_errors=True)
                else:
                    with contextlib.suppress(OSError):
                        entry.unlink()
        finally:
            lock.release()
        shutil.rmtree(self.work_dir, ignore_errors=True)
        return True


# -- the workspace ----------------------------------------------------------------


class Workspace:
    """A library being edited: a private working copy and the file it came from.

    Build one with :meth:`open`, :meth:`create` or :meth:`recover`; the
    constructor is not for callers.

    Attributes:
        library: The :class:`~pylot_bem.api.Pylot` on the working copy. Do all
            the work through this, and open more connections to
            ``library.path`` from other threads as needed (the working copy is
            in WAL mode, which is what lets them coexist).
        path: The file this workspace saves to, or ``None`` until it has one.
        work_dir: The private folder holding the copy and its session record.
    """

    def __init__(
        self,
        *,
        library: Pylot,
        path: Path | None,
        work_dir: Path,
        lock: _SessionLock,
        fingerprint: Fingerprint | None,
        dirty: bool = False,
    ) -> None:
        self.library = library
        self.path = path
        self.work_dir = work_dir
        self._lock = lock
        self._fingerprint = fingerprint
        self._dirty = dirty
        self._closed = False
        #: What the session record on disk says, once a write of it has succeeded.
        self._recorded_dirty: bool | None = None
        self._state = threading.RLock()
        self._saving = threading.Lock()
        # A third connection that never writes. `PRAGMA data_version` changes
        # when *another* connection commits, so this one sees every write --
        # the window's, and a batch worker's -- which no counter on the
        # window's own connection can.
        self._monitor = sqlite3.connect(library.path, check_same_thread=False)
        self._seen = self._data_version()
        self._persist()

    # -- opening ------------------------------------------------------------

    @classmethod
    def open(cls, path: str | Path, *, work_root: str | Path | None = None) -> Self:
        """Open an existing library for editing.

        Args:
            path: The library file. It is read once, to make the copy, and not
                held open afterwards.
            work_root: Where to put the copy. Defaults to
                :func:`default_work_root`.

        Raises:
            LibraryError: If the file is missing, is not a library, or was
                written by another schema version -- the same refusals as
                :meth:`~pylot_db.storage.Library.open`.
            WorkspaceError: If the file will not keep still long enough to copy.
        """
        source = Path(path).absolute()
        if not source.is_file():
            raise LibraryError(f"{source} does not exist")
        work_dir, lock = _new_session(work_root)
        library = None
        try:
            working = work_dir / source.name
            fingerprint = _copy_source(source, working)
            library = Pylot.open(working)
            workspace = cls(library=library, path=source, work_dir=work_dir, lock=lock, fingerprint=fingerprint)
        except BaseException as exc:
            if library is not None:
                with contextlib.suppress(Exception):
                    library.close()
            lock.release()
            _release_frames(exc)
            shutil.rmtree(work_dir, ignore_errors=True)
            raise
        if fingerprint.wal is not None and not workspace._quick_check_ok():
            workspace.close()
            raise WorkspaceError(
                f"{source} and the write-ahead log beside it do not agree; another program may be writing to it"
            )
        return workspace

    @classmethod
    def create(
        cls,
        path: str | Path,
        mesh_file: str | Path,
        origin_description: str,
        *,
        work_root: str | Path | None = None,
        **options,
    ) -> Self:
        """Create a library and write it to ``path`` straight away.

        The arguments after ``work_root`` are those of
        :meth:`~pylot_bem.api.Pylot.create_new`. The library is built in a
        working copy and saved immediately, so ``path`` exists and the
        workspace starts clean -- there is no untitled state.

        Raises:
            LibraryError: If ``path`` exists, or for any refusal of
                :meth:`~pylot_bem.api.Pylot.create_new`.
        """
        target = Path(path).absolute()
        if target.exists():
            raise LibraryError(f"{target} already exists; refusing to overwrite a library")
        work_dir, lock = _new_session(work_root)
        library = None
        try:
            library = Pylot.create_new(work_dir / target.name, mesh_file, origin_description, **options)
            workspace = cls(library=library, path=None, work_dir=work_dir, lock=lock, fingerprint=None)
        except BaseException as exc:
            if library is not None:
                with contextlib.suppress(Exception):
                    library.close()
            lock.release()
            _release_frames(exc)
            shutil.rmtree(work_dir, ignore_errors=True)
            raise
        try:
            workspace._write(target, check=False, must_be_new=True)
        except BaseException:
            workspace.close()
            raise
        return workspace

    @classmethod
    def recoverable(cls, work_root: str | Path | None = None) -> list[Recovery]:
        """The unsaved work earlier sessions left behind.

        A session is a candidate when nothing holds its lock any more -- its
        process is gone -- and it had recorded changes. Dead sessions with
        nothing to lose are deleted here rather than offered.
        """
        root = Path(work_root) if work_root is not None else default_work_root()
        if not root.is_dir():
            return []
        found: list[Recovery] = []
        for work_dir in sorted(root.iterdir()):
            if not work_dir.is_dir() or not _SESSION_DIR.fullmatch(work_dir.name):
                continue
            lock = _SessionLock.acquire(work_dir / _LOCK)
            if lock is None:  # alive: somebody is using it right now
                continue
            try:
                record = _read_record(work_dir)
                if record is None and time.time() - work_dir.stat().st_mtime < _YOUNG:
                    continue  # a session being born
                keep = False
                if record is not None and record.get("dirty") and not record.get("closed") and record.get("name"):
                    working = work_dir / record["name"]
                    keep = working.is_file()
                    if keep:
                        updated = None
                        with contextlib.suppress(KeyError, ValueError, TypeError):
                            updated = datetime.fromisoformat(record["updated"])
                        source = Path(record["source"]) if record.get("source") else None
                        fingerprint = Fingerprint.from_json(record.get("fingerprint"))
                        found.append(Recovery(work_dir, source, working, updated, fingerprint))
            finally:
                lock.release()
            if not keep:
                shutil.rmtree(work_dir, ignore_errors=True)
        return found

    @classmethod
    def recover(cls, recovery: Recovery) -> Self:
        """Pick up the work a dead session left, as unsaved changes.

        The workspace comes back dirty, and its Save compares the original
        against what it was when that session last read or wrote it -- so if
        the file has moved on in the meantime, Save says so.

        Raises:
            WorkspaceError: If another running session has taken it meanwhile.
            LibraryError: If the working copy will not open. Its folder is
                left alone, so it can still be salvaged by hand.
        """
        lock = _SessionLock.acquire(recovery.work_dir / _LOCK)
        if lock is None:
            raise WorkspaceError(f"{recovery.work_dir} is in use by another running session")
        fingerprint = recovery.fingerprint
        if fingerprint is None and recovery.source is not None:
            fingerprint = _UNKNOWN
        try:
            library = Pylot.open(recovery.working_path)
            workspace = cls(
                library=library,
                path=recovery.source,
                work_dir=recovery.work_dir,
                lock=lock,
                fingerprint=fingerprint,
                dirty=True,
            )
        except BaseException as exc:
            lock.release()
            _release_frames(exc)  # the folder is left for salvage; nothing may keep the copy open
            raise
        return workspace

    # -- state --------------------------------------------------------------

    @property
    def working_path(self) -> Path:
        """The private copy every change is made to."""
        return Path(self.library.path)

    @property
    def name(self) -> str:
        """The file's name, for a title bar."""
        return (self.path or self.working_path).name

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def dirty(self) -> bool:
        """Whether there is anything Save would write that the file does not have.

        Sticky: once a commit has been seen it stays true until a Save.
        Cheap enough to poll, and polling is what records the state for crash
        recovery -- the first time this answers ``True`` it is also written to
        the session record, and written again on every poll until that has
        worked.
        """
        with self._state:
            if not self._closed:
                if not self._dirty and self._data_version() != self._seen:
                    self._dirty = True
                if self._dirty != self._recorded_dirty:
                    self._persist()
            return self._dirty

    def _data_version(self) -> int | None:
        try:
            return int(self._monitor.execute("PRAGMA data_version").fetchone()[0])
        except sqlite3.Error:
            return None

    def _quick_check_ok(self) -> bool:
        try:
            return bool(self._monitor.execute("PRAGMA quick_check").fetchone()[0] == "ok")
        except sqlite3.Error:
            return False

    def _persist(self, *, closed: bool = False) -> None:
        record = {
            "version": _RECORD_VERSION,
            "source": str(self.path) if self.path else None,
            "name": self.working_path.name,
            "dirty": self._dirty,
            "closed": closed,
            "fingerprint": self._fingerprint.to_json() if self._fingerprint else None,
            "pid": os.getpid(),
            "updated": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        # The record is a safety net. Failing to write it must not fail the
        # edit it is a net for.
        with contextlib.suppress(OSError):
            _write_record(self.work_dir, record)
            self._recorded_dirty = self._dirty

    # -- saving -------------------------------------------------------------

    def save(self, *, force: bool = False) -> None:
        """Replace the original with the working copy.

        Args:
            force: Skip the check that the original is unchanged since it was
                opened. Only for when the user has been told and chose to
                overwrite.

        Raises:
            SourceChangedError: The original changed since it was opened.
            SourceLockedError: The original could not be replaced, after retrying
                for :data:`REPLACE_BUDGET` seconds.
            WorkspaceError: The workspace has no file yet (use :meth:`save_as`),
                or the snapshot failed verification.
        """
        if self.path is None:
            raise WorkspaceError("this library has no file yet; use save_as")
        self._write(self.path, check=not force)

    def save_as(self, path: str | Path) -> None:
        """Write the working copy to a new file, which becomes the workspace's file.

        Anything already at ``path`` is replaced; asking whether that is
        intended is for whoever chose the name. The changed-on-disk check does
        not apply to a destination this workspace never read -- except when it
        is the file it already has, which is just :meth:`save`.
        """
        target = Path(path).absolute()
        if self._is_own_file(target):
            self.save()
            return
        self._write(target, check=False)

    def _is_own_file(self, path: Path) -> bool:
        return self.path is not None and _same_file(path, self.path)

    def _write(self, path: Path, *, check: bool, must_be_new: bool = False) -> None:
        with self._saving:
            self._require_open()
            # The document keeps the name it was given; the bytes go to what it points at.
            dest = Path(os.path.realpath(path)) if path.is_symlink() else path
            if must_be_new:
                _refuse_existing(dest)
            if dest.exists() and not os.access(dest, os.W_OK):
                raise SourceLockedError(dest, "is read-only, so it cannot be replaced")
            # Read under the lock: a second save is to be compared against what the
            # first one wrote, not against what it read before the first finished.
            current = self._fingerprint if check else None
            if current is not None:
                self._fingerprint = current = self._unchanged(dest, current)

            _sweep_stale(dest)
            with self._state:
                before = self._data_version()
            token = uuid.uuid4().hex[:8]
            stage = self.work_dir / f".stage-{token}.tmp"
            sent = dest.with_name(f"~{dest.name}.{token}.tmp")
            recheck = None
            if current is not None:
                watched = current

                def recheck() -> None:
                    # Refreshed each time, so a modification time that moved without the
                    # content costs one hash rather than one per attempt.
                    nonlocal watched
                    watched = self._unchanged(dest, watched)

            try:
                self._snapshot(stage)
                self._verify(stage)
                digest = _copy_hashing(stage, sent, sync=True)
                with contextlib.suppress(OSError):
                    shutil.copymode(dest, sent)
                if must_be_new:
                    _refuse_existing(dest)  # again, now that building the snapshot has taken a while
                aside = _replace(sent, dest, token=token, recheck=recheck)
            finally:
                # Each on its own, and never allowed to replace the real outcome.
                for leftover in (stage, sent):
                    with contextlib.suppress(OSError):
                        leftover.unlink(missing_ok=True)
            for moved, _ in aside:
                with contextlib.suppress(OSError):
                    moved.unlink(missing_ok=True)

            with self._state:
                self.path = path
                self._fingerprint = Fingerprint(Stamp.of(dest, digest))
                self._dirty = False
                # Baselined *before* the snapshot, so anything committed while
                # it was being taken -- a batch still running -- shows as
                # unsaved rather than being marked saved without being in it.
                self._seen = before
                self._persist()

    def _unchanged(self, dest: Path, expected: Fingerprint) -> Fingerprint:
        refreshed = expected.check(dest)
        if refreshed is None:
            raise SourceChangedError(dest)
        return refreshed

    def _snapshot(self, stage: Path) -> None:
        # A connection of its own: VACUUM INTO refuses to run inside a
        # transaction, and this one has never begun one.
        connection = sqlite3.connect(self.working_path)
        try:
            connection.execute("VACUUM INTO ?", (str(stage),))
        finally:
            connection.close()

    def _verify(self, stage: Path) -> None:
        """Refuse a snapshot that is not a whole, single-file library."""
        with stage.open("rb") as handle:
            header = handle.read(20)
        if header[:16] != _SQLITE_HEADER or header[18:20] != b"\x01\x01":
            raise WorkspaceError("the snapshot is not a rollback-mode SQLite file; nothing was written")
        with Library.open(stage, read_only=True):
            pass  # the schema version and the library table are there
        # A plain connection, not a ``file:`` URI: the working folder can be a UNC
        # path, which SQLite refuses as a URI. Safe because the header above says
        # rollback mode, so opening it creates nothing.
        with contextlib.closing(sqlite3.connect(stage)) as connection:
            outcome = connection.execute("PRAGMA quick_check").fetchone()[0]
        if outcome != "ok":
            raise WorkspaceError(f"the snapshot failed its integrity check ({outcome}); nothing was written")

    # -- closing ------------------------------------------------------------

    def close(self) -> None:
        """Close the library and delete the working copy.

        Whoever calls this has already decided what happens to unsaved
        changes; they are gone afterwards. (A crash never gets here, which is
        what leaves them recoverable.) Safe to call twice.
        """
        with self._state:
            if self._closed:
                return
            self._closed = True
        with contextlib.suppress(sqlite3.Error):
            self._monitor.close()
        with contextlib.suppress(Exception):
            self.library.close()
        self._persist(closed=True)
        self._lock.release()
        shutil.rmtree(self.work_dir, ignore_errors=True)

    def _require_open(self) -> None:
        if self._closed:
            raise WorkspaceError("this workspace is closed")

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def _release_frames(exc: BaseException | None) -> None:
    """Let go of whatever the frames an exception passed through still hold.

    ``Library.open`` on a file that is not a database fails inside its own
    ``_connect``, whose local still holds the half-open connection -- and the
    traceback keeps that frame alive for as long as the exception is. On
    Windows a folder cannot be deleted while a handle in it is open, so without
    this the working folder of a refused file stays behind. (A connection is
    also part of a reference cycle through its statement cache, so dropping the
    last name for it does not close it; only a collection does.)
    """
    while exc is not None:
        traceback.clear_frames(exc.__traceback__)
        exc = exc.__cause__ or exc.__context__
    gc.collect()


def _same_file(a: Path, b: Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _refuse_existing(dest: Path) -> None:
    if dest.exists():
        raise LibraryError(f"{dest} already exists; refusing to overwrite a library")


def _sweep_stale(dest: Path) -> None:
    """Delete the half-copies an earlier Save left beside ``dest`` when it died.

    Only the file a Save copies the new library into -- ``~name.<token>.tmp`` --
    and only once it is old enough that no other window can still be writing
    it. The ``-wal`` a Save set aside is *not* swept: it may be the only place
    some commits are.
    """
    pattern = re.compile(re.escape(f"~{dest.name}") + r"\.[0-9a-f]{8}\.tmp")
    try:
        names = os.listdir(dest.parent)
    except OSError:
        return
    now = time.time()
    for name in names:
        if pattern.fullmatch(name):
            leftover = dest.parent / name
            with contextlib.suppress(OSError):
                if now - leftover.stat().st_mtime > _STALE_AFTER:
                    leftover.unlink()


def _set_aside_sidecars(dest: Path, token: str, moved: list[tuple[Path, Path]]) -> None:
    """Move the files that would be replayed onto the new file out of the way.

    A ``-wal`` or ``-journal`` beside the original belongs to the *old* file.
    Left in place, SQLite would replay it onto the new one on the next open and
    hand back a mixture of both. They are moved rather than deleted because
    the replace can still fail, and a legacy ``-wal`` may hold commits the main
    file does not have: a Save that did not happen must not have cost the
    original anything.

    ``moved`` is the caller's, and gets ``(where it went, where it was)`` as
    each one goes, so that whatever interrupts this half way -- an error, a
    Ctrl+C -- the caller still knows what to put back with
    :func:`_restore_sidecars`.

    Raises:
        PermissionError: If one could not be moved -- another program has it
            open, which on Windows is exactly what stops a rename.
    """
    for suffix in ("-wal", "-shm", "-journal"):
        side = _sidecar(dest, suffix)
        aside = dest.with_name(f"~{dest.name}{suffix}.{token}.tmp")
        try:
            os.replace(side, aside)
        except FileNotFoundError:
            continue
        moved.append((aside, side))


def _restore_sidecars(moved: list[tuple[Path, Path]]) -> None:
    """Put back what :func:`_set_aside_sidecars` moved.

    Tried for a moment: whatever briefly held the file a second ago may still
    be letting go. Never over a file somebody has created there since -- theirs
    wins, and ours stays under its set-aside name for whoever needs it.
    """
    for aside, side in reversed(moved):
        if side.exists():
            continue
        for attempt in range(5):
            try:
                os.replace(aside, side)
            except OSError:
                time.sleep(0.05 * (attempt + 1))
            else:
                break


def _replace(
    sent: Path, dest: Path, *, token: str, recheck: Callable[[], None] | None = None
) -> list[tuple[Path, Path]]:
    """Swap ``sent`` in for ``dest``, kept trying for a few seconds.

    On Windows this fails with a permission error for as long as any program
    has ``dest`` open, and the programs that do -- a sync client mid-upload, a
    virus scanner, an indexer -- let go within moments. A person who sees an
    error every time a scanner looks at the file will stop trusting Save.

    ``recheck`` runs before every attempt: the wait can be seconds long, and a
    change that lands during it would otherwise be overwritten by a Save that
    had already decided the file was unchanged.

    The old file's sidecars are set aside only for the length of an attempt and
    put straight back if it fails, so a long wait never leaves a legacy library
    without its ``-wal``, nor a crash in the middle of one more than
    moments' worth of exposure.

    Returns:
        The sidecars that were set aside for the successful swap, which are now
        the old file's and are the caller's to delete.
    """
    deadline = time.monotonic() + REPLACE_BUDGET
    delay = 0.01
    while True:
        if recheck is not None:
            recheck()
        moved: list[tuple[Path, Path]] = []
        try:
            _set_aside_sidecars(dest, token, moved)
            os.replace(sent, dest)
        except PermissionError as exc:
            _restore_sidecars(moved)
            if time.monotonic() >= deadline:
                raise SourceLockedError(dest, "is in use by another program, so it cannot be replaced") from exc
            time.sleep(delay)
            delay = min(delay * 2, 0.25)
        except BaseException:
            _restore_sidecars(moved)
            raise
        else:
            return moved
