"""The batch screen: a night of conditions, meshes and solves, set up once.

Its own module rather than a fourth class in :mod:`pylot_bem.app.dialogs`, for
the reason :mod:`pylot_bem.app.merge` is: it is more than a filler over a
``.ui``. The other dialogs collect arguments for one call; this one describes
work that does not exist yet -- hundreds of conditions, twice as many meshes,
and every solve on them -- and has to say what that would cost before anybody
commits a night to it.

**Everything about the job is data, and the data lives in**
:mod:`pylot_bem.batch`. This screen reads widgets, builds a
:class:`~pylot_bem.batch.BatchJob`, and shows what
:func:`~pylot_bem.batch.plan` says about it. It works nothing out for itself:
the plan it previews is the same object
:meth:`~pylot_bem.batch.BatchRun.run` then executes, so what is on screen and
what happens cannot come apart.

Three things it must get right, and they are the same three the Solve screen
must -- one level up, over a run that lasts a night rather than a minute:

- **the cost is visible before Start**, in conditions, meshes, solves and
  boundary-value problems. Not in memory or panel counts: those come out of a
  regrid that has not happened, and an invented figure beside four real ones is
  indistinguishable from them;
- **Stop and Kill cost different things** and the buttons say which;
- **a failed step is visible**. It is in the log as it happens and counted in
  the summary at the end, because a batch that silently dropped eleven
  conditions is a library that looks finished and is not.
"""

import threading
import traceback
from pathlib import Path

import numpy as np
from PySide6.QtCore import QLocale, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QMessageBox,
    QToolBox,
    QWidget,
)

from pylot_bem.api import Pylot
from pylot_bem.app.formatting import (
    CLEAN,
    CONFLICT,
    INCOMPLETE,
    degrees_from_slope,
    derived,
    escape,
    format_grid,
    slope_from_degrees,
    spans_the_circle,
)
from pylot_bem.app.forms.dlg_batch_ui import Ui_DlgBatch
from pylot_bem.batch import (
    JOB_SUFFIX,
    TARGET_ALL,
    TARGET_GRID,
    TARGET_LISTED,
    Band,
    BatchError,
    BatchJob,
    BatchOutcome,
    BatchRun,
    LibraryState,
    format_bands,
    load_job,
    parse_bands,
    parse_numbers,
    plan,
    save_job,
    value_range,
)
from pylot_bem.pool import default_workers

__all__ = ["BatchDialog", "BatchThread", "format_duration", "summarise"]

JOB_FILTER = f"pylot batch job (*{JOB_SUFFIX});;All files (*)"

# The same four lid modes as the Solve screen, in the same order, spelled the
# way :mod:`pylot_bem.batch` spells them. Two lists that had to agree by hand
# is one list too many, so the caption and the value travel together.
LID_MODES = (
    ("None", "none"),
    ("At free surface", "surface"),
    ("Below free surface", "below"),
    ("Auto", "auto"),
)

TARGET_CAPTIONS = (
    ("The conditions in the grid", TARGET_GRID),
    ("Every condition in the library", TARGET_ALL),
    ("The conditions selected in the tree", TARGET_LISTED),
)

# Which lid mode needs the position spin box, by index into LID_MODES.
_LID_BELOW = 2


def format_duration(seconds: float) -> str:
    """Seconds as something a person can plan an evening around.

    A batch is the one screen where the remaining time is measured in hours,
    and ``43512 s`` is not a number anybody converts in their head.
    """
    seconds = max(0.0, float(seconds))
    if seconds < 90:
        return f"{seconds:.0f} s"
    minutes = seconds / 60
    if minutes < 90:
        return f"{minutes:.0f} min"
    hours = int(minutes // 60)
    return f"{hours} h {int(minutes - 60 * hours):02d} min"


def summarise(outcome: BatchOutcome) -> str:
    """One line for what a batch did, for the log and for a status bar.

    Failures are counted here rather than only listed, because the count is
    what says whether the library is finished: eleven failures in seven hundred
    conditions is a library with eleven holes in it, and nothing else on screen
    would say so.
    """
    ended = "Killed" if outcome.killed else "Stopped early" if outcome.stopped else "Finished"
    parts = [
        f"{len(outcome.conditions_created)} conditions",
        f"{len(outcome.meshes_built)} meshes",
        f"{len(outcome.results_stored)} results",
    ]
    if outcome.reused or outcome.skipped:
        parts.append(f"{outcome.reused} conditions and {outcome.skipped} solves already there")
    if outcome.failures:
        parts.append(f"{len(outcome.failures)} FAILED")
    return f"{ended} after {format_duration(outcome.elapsed)}: " + ", ".join(parts) + "."


class BatchThread(QThread):
    """One :class:`~pylot_bem.batch.BatchRun`, off the interface thread.

    The same arrangement as :class:`~pylot_bem.app.solving.SolveThread`, with
    one difference that decides the design: a batch **writes to the library**
    between solves, where a single solve hands its dataset back and is stored
    on the interface thread.

    ``sqlite3`` refuses a connection used from a thread other than the one that
    opened it, so this thread cannot be handed the window's library. It opens
    **its own connection to the same file** instead -- which is safe because
    every pylot library runs in WAL mode, where a writer and a reader coexist
    and the reader sees each commit as it lands. The window's connection stays
    read-only for the duration: the screen is modal and every setting on it is
    disabled while the run is going.

    That is also why the job, and not a prepared run, is what this takes. The
    plan has to be made against the library the run will actually write to, on
    the thread that will write to it.

    Signals:
        progressed: A :class:`~pylot_bem.batch.BatchEvent` per step, and
            repeatedly during each solve.
        completed: The final :class:`~pylot_bem.batch.BatchOutcome`.
        failed: A traceback, when the run raised rather than returning. A step
            that fails does **not** come through here -- it is in the outcome,
            because the batch carried on past it.
    """

    progressed = Signal(object)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, path, job: BatchJob, parent=None) -> None:
        super().__init__(parent)
        self._path = path
        self._job = job
        self._lock = threading.Lock()
        self._run: BatchRun | None = None
        # Stop or Kill can be clicked in the moment between start() and the
        # run existing. Remembered rather than dropped: a Kill that silently
        # did nothing is the one click a user will not try twice.
        self._pending = ""

    @property
    def stopping(self) -> bool:
        with self._lock:
            return self._pending == "stop" or (self._run is not None and self._run.stopping)

    def stop(self) -> None:
        """Finish the running solve, store it, and start nothing more."""
        self._request("stop")

    def kill(self) -> None:
        """Terminate the running solve now. Nothing is stored for it."""
        self._request("kill")

    def _request(self, what: str) -> None:
        with self._lock:
            run = self._run
            if run is None:
                self._pending = what
                return
        getattr(run, what)()

    def run(self) -> None:
        try:
            with Pylot.open(self._path) as library:
                run = BatchRun(library, self._job)
                with self._lock:
                    self._run = run
                    pending = self._pending
                if pending:
                    getattr(run, pending)()
                outcome = run.run(progress=self.progressed.emit)
        except Exception:
            self.failed.emit(traceback.format_exc())
        else:
            self.completed.emit(outcome)


class BatchDialog(QDialog):
    """Describe a batch, see what it would cost, and run it.

    Attributes:
        outcome: What the last run did, or ``None`` if none has finished. Kept
            because ``exec()`` returns a dialog code and nothing else, and the
            window puts the summary in its status bar afterwards -- the batch
            is over by then and the screen it was reported on is gone.

    Signals:
        libraryChanged: The batch wrote something. Emitted once, when the run
            ends -- not per step. A tree of seven hundred conditions rebuilt
            after each of fourteen hundred steps would spend the night
            redrawing rather than solving.
    """

    libraryChanged = Signal()

    def __init__(self, library, condition_ids=(), parent: QWidget | None = None) -> None:
        """Set up the screen.

        Args:
            library: The open :class:`~pylot_bem.api.Pylot`. Read only here --
                the run gets its own connection, see :class:`BatchThread`.
            condition_ids: Conditions selected in the tree, offered as the
                third target. Empty disables that choice rather than hiding it,
                so the option is discoverable before there is a selection to
                use it on.
            parent: Qt parent.
        """
        super().__init__(parent)
        self.setLocale(QLocale.c())
        self.ui = Ui_DlgBatch()
        self.ui.setupUi(self)

        self._library = library
        self._selected = tuple(condition_ids)
        self._thread: BatchThread | None = None
        self._problem = ""
        self.outcome: BatchOutcome | None = None
        # Set once, by the first showEvent -- see _size_to_content.
        self._sized = False

        # Read once, not on every keystroke. The preview re-plans as the grid
        # is typed, and a plan reads every mesh in the library -- geometry and
        # all, because that is what a CalculationMesh carries -- to look at two
        # numbers on each. On a finished library that is a third of a second
        # per character. Safe to keep because this screen is modal: the only
        # thing that writes here is its own run, and that re-reads afterwards.
        self._state = LibraryState.of(library)

        self.setWindowTitle("Batch — conditions, meshes and solves")
        self.ui.lblHeading.setText(
            f"<b>{escape(library.info.vessel_name or library.path.stem)}</b> — "
            f"{len(library.conditions())} conditions, {len(library.meshes())} meshes and "
            f"{len(library.results())} results are already in this library. Everything below "
            "is added to it, and nothing in it is changed or removed."
        )

        for caption, _ in LID_MODES:
            self.ui.comboLid.addItem(caption)
        for caption, value in TARGET_CAPTIONS:
            self.ui.comboTargets.addItem(
                f"{caption} ({len(self._selected)})" if value == TARGET_LISTED else caption
            )
        if not self._selected:
            self.ui.comboTargets.model().item(2).setEnabled(False)
        self.ui.spinWorkers.setValue(default_workers(64))

        for widget in (
            self.ui.spinZFrom,
            self.ui.spinZTo,
            self.ui.spinZStep,
            self.ui.spinDirFrom,
            self.ui.spinDirTo,
            self.ui.spinDirStep,
            self.ui.spinDirFullFrom,
            self.ui.spinDirFullTo,
            self.ui.spinDirFullStep,
            self.ui.spinG,
            self.ui.spinDepth,
            self.ui.spinSpeed,
            self.ui.spinLidZ,
            self.ui.spinIterations,
            self.ui.spinWorkers,
            self.ui.spinOmp,
        ):
            widget.valueChanged.connect(self._refresh)
        for line in (self.ui.editHeels, self.ui.editTrims):
            line.textChanged.connect(self._refresh)
        self.ui.editBands.textChanged.connect(self._refresh)
        self.ui.comboLid.currentIndexChanged.connect(self._refresh)
        self.ui.comboTargets.currentIndexChanged.connect(self._refresh)
        self.ui.chkResume.toggled.connect(self._refresh)
        self.ui.chkCreateConditions.toggled.connect(self._creating_toggled)
        self.ui.chkInfiniteDepth.toggled.connect(self._depth_toggled)

        self.ui.btnStart.clicked.connect(self._start)
        self.ui.btnStop.clicked.connect(self._stop)
        self.ui.btnKill.clicked.connect(self._kill)
        self.ui.btnClose.clicked.connect(self.close)
        # Through a lambda, and not connected directly: `clicked` carries the
        # button's `checked` state, and PySide fills a slot's first optional
        # parameter with it. Wired straight through, the click handed `False`
        # to `path` -- so Save wrote to a file called False, raised, and
        # printed a traceback to a stderr the packaged application does not
        # have. It looked exactly like a button that does nothing.
        self.ui.btnSaveJob.clicked.connect(lambda: self.save_job_to_file())
        self.ui.btnLoadJob.clicked.connect(lambda: self.load_job_from_file())

        self.ui.btnStop.setToolTip(
            "Graceful — the solve in flight is finished and stored, then the batch ends"
        )
        self.ui.btnKill.setToolTip(
            "Immediate — the solve in flight is discarded. There is nobody here overnight to "
            "be asked whether part of a grid was worth keeping"
        )

        self._refresh()
        self._size_to_content()

    def _size_to_content(self) -> None:
        """Make room for the **tallest** page, but never more than the screen.

        Wrapped explanation reports a minimum height only once it has a width to
        wrap against, so a dialog full of it opens shorter than the sum of what
        is in it -- SolveDialog carries the same line for the same reason.

        The pages make it more than that line, and worse. ``sizeHint`` describes
        one page and resolves none of the wrapping, so it reported the same 528
        pixels for all five while the Run page -- two progress bars and a log --
        actually needed 558. The dialog stayed at 528, the layout pushed the
        button row past the bottom edge, and Start, Stop and Kill went out of
        reach on the one page you need them.

        So this measures rather than predicts: it opens each page, lets the
        layout settle, and asks how far past the bottom the buttons actually
        landed. That is the number, and no hint of any kind reports it.

        Capped, because asking for 1200 pixels on a 1080-pixel display puts the
        same buttons off-screen with no way back. Under the cap a page scrolls,
        which is what a QToolBox page does.
        """
        screen = self.screen() or QApplication.primaryScreen()
        limit = int(screen.availableGeometry().height() * 0.92) if screen else None

        wanted = self.sizeHint().height()
        if limit is not None:
            wanted = min(wanted, limit)
        self.resize(self.width(), wanted)

        overflow = self._worst_button_overflow()
        if overflow > 0:
            grown = wanted + overflow
            self.resize(self.width(), min(grown, limit) if limit is not None else grown)

    def _worst_button_overflow(self) -> int:
        """How far below the bottom edge the button row lands, at its worst.

        Across every page, because only one is laid out at a time and they are
        of very different heights. The page that was open is put back, so this
        is invisible to whoever is looking at the screen.
        """
        toolbox = self.findChild(QToolBox)
        if toolbox is None or self.layout() is None:
            return 0

        was = toolbox.currentIndex()
        try:
            worst = 0
            for index in range(toolbox.count()):
                toolbox.setCurrentIndex(index)
                self.layout().activate()
                bottom = self.ui.btnStart.mapTo(self, self.ui.btnStart.rect().bottomLeft()).y()
                # The margin below the row, so it is clear of the edge rather
                # than flush against it.
                worst = max(worst, bottom + self.layout().contentsMargins().bottom() - self.height())
            return worst
        finally:
            toolbox.setCurrentIndex(was)
            self.layout().activate()

    def showEvent(self, event) -> None:
        """Size again the first time it is shown.

        Nothing wraps until it has a width, and a widget has no real width
        until it is shown -- so the measurement in ``__init__`` is taken
        against a layout that has not happened yet. Repeating it here is what
        makes the number right. Once only: after that the size is the user's,
        and a dialog that resizes itself every time it is raised is a dialog
        that will not stay where it is put.
        """
        super().showEvent(event)
        if not self._sized:
            self._sized = True
            self._size_to_content()

    # -- reading the screen ------------------------------------------------

    def z_origins(self) -> tuple[float, ...]:
        """The z_origin grid, empty when the conditions are switched off."""
        if not self.ui.chkCreateConditions.isChecked():
            return ()
        return value_range(
            self.ui.spinZFrom.value(), self.ui.spinZTo.value(), self.ui.spinZStep.value()
        )

    def directions(self, *, full_vessel: bool = False) -> tuple[float, ...]:
        """One of the two direction grids, with no duplicate at the wrap-around.

        0 and 360 are the same heading, and solving both costs a full set of
        problems for a second copy of a column that is already there -- the
        same rule, and the same modulo test, as the Solve screen. It is what
        lets the full-vessel row read *0 to 360*, which is how a person says
        "all the way round", and still solve 24 headings rather than 25.

        Args:
            full_vessel: Which row to read. The grids are kept apart because a
                job that heels a hull contains both kinds of mesh, and which
                one a solve gets is derived from the mesh, never chosen.
        """
        spins = (
            (self.ui.spinDirFullFrom, self.ui.spinDirFullTo, self.ui.spinDirFullStep)
            if full_vessel
            else (self.ui.spinDirFrom, self.ui.spinDirTo, self.ui.spinDirStep)
        )
        values = value_range(*(spin.value() for spin in spins))
        if len(values) > 1 and abs((values[-1] - values[0]) % 360.0) < 1e-9:
            values = values[:-1]
        return values

    def bands(self) -> tuple[Band, ...]:
        """The band table, at the job's remesh iterations."""
        return tuple(
            parse_bands(
                self.ui.editBands.toPlainText(), iterations=self.ui.spinIterations.value()
            )
        )

    def targets(self) -> str:
        return TARGET_CAPTIONS[self.ui.comboTargets.currentIndex()][1]

    def job(self) -> BatchJob:
        """Everything on screen, as a job.

        Raises:
            BatchError: If a field cannot be read. The message is the one shown
                beside a disabled Start, so it is written to be read by a user.
        """
        return BatchJob(
            z_origins=self.z_origins(),
            heels=tuple(
                slope_from_degrees(d) for d in parse_numbers(self.ui.editHeels.text(), what="Heel")
            ),
            trims=tuple(
                slope_from_degrees(d) for d in parse_numbers(self.ui.editTrims.text(), what="Trim")
            ),
            bands=self.bands(),
            targets=self.targets(),
            condition_ids=self._selected,
            wave_directions=self.directions(),
            wave_directions_full=self.directions(full_vessel=True),
            water_depth=np.inf
            if self.ui.chkInfiniteDepth.isChecked()
            else self.ui.spinDepth.value(),
            g=self.ui.spinG.value(),
            forward_speed=self.ui.spinSpeed.value(),
            lid=LID_MODES[self.ui.comboLid.currentIndex()][1],
            lid_z=self.ui.spinLidZ.value(),
            workers=self.ui.spinWorkers.value(),
            omp_threads=self.ui.spinOmp.value(),
            resume=self.ui.chkResume.isChecked(),
        )

    # -- the preview -------------------------------------------------------

    def _creating_toggled(self, on: bool) -> None:
        for widget in (
            self.ui.spinZFrom,
            self.ui.spinZTo,
            self.ui.spinZStep,
            self.ui.editHeels,
            self.ui.editTrims,
        ):
            widget.setEnabled(on)
        self._refresh()

    def _depth_toggled(self, infinite: bool) -> None:
        self.ui.spinDepth.setEnabled(not infinite)
        self._refresh()

    def _refresh(self) -> None:
        """Redraw every derived readout from one reading of the screen.

        The plan is made **once** here and handed to the two readouts that need
        it. It is cheap -- the library is read once at construction, not per
        keystroke -- but it is not free, and this runs on every character typed
        into the heels field.
        """
        self.ui.spinLidZ.setEnabled(self.ui.comboLid.currentIndex() == _LID_BELOW)
        try:
            preview, problem = plan(self._library, self.job(), state=self._state), ""
        except BatchError as exc:
            preview, problem = None, str(exc)

        self._show_grid()
        self._show_bands()
        self._show_directions(preview)
        self._show_lid()
        self._show_plan(preview, problem)

    def _show_grid(self) -> None:
        if not self.ui.chkCreateConditions.isChecked():
            self.ui.lblConditionGrid.setText(
                derived("No conditions are created", "the meshes go on the ones already there")
            )
            return
        try:
            z_origins = self.z_origins()
            heels = parse_numbers(self.ui.editHeels.text(), what="Heel")
            trims = parse_numbers(self.ui.editTrims.text(), what="Trim")
        except BatchError as exc:
            self.ui.lblConditionGrid.setText(
                f'<span style="color:{CONFLICT}">{escape(str(exc))}</span>'
            )
            return
        self.ui.lblConditionGrid.setText(
            derived(
                f"<b>{len(z_origins)} × {len(heels)} × {len(trims)} = "
                f"{len(z_origins) * len(heels) * len(trims)} conditions</b>",
                f"z_origin {format_grid(z_origins, limit=4)} m",
            )
        )

    def _show_bands(self) -> None:
        try:
            bands = self.bands()
        except BatchError as exc:
            self.ui.lblBands.setText(f'<span style="color:{CONFLICT}">{escape(str(exc))}</span>')
            return
        self.ui.lblBands.setText(
            "<br>".join(
                f"pct <b>{band.pct:g}</b> — {len(band.periods)} periods, "
                f"{escape(format_grid(band.periods, decimals=1, limit=8))} s"
                for band in bands
            )
        )

    def _show_directions(self, preview) -> None:
        """Both grids, and which conditions of this job get each.

        The two rows are not a preference. Which one a solve uses is derived
        from its mesh -- a symmetric hull at zero heel is a half vessel whose
        port side mirrors its starboard side, and anything heeled is a full
        vessel with nothing to mirror. A grid of heels contains both, which is
        why one row could never have been right.

        The full-vessel row carries a warning, because it is the one setting on
        this screen where being wrong is invisible: mafredo does not refuse a
        heading past 180, it interpolates across whatever was never solved and
        answers confidently. Shown only when this job will actually build a
        full mesh -- a warning that is always on is one nobody reads.
        """
        half = self.directions()
        full = self.directions(full_vessel=True)
        # Asked of the plan rather than worked out again here: it derives this
        # per step by the same rule create_mesh will, and a second opinion in
        # the interface is a second thing to keep in step with storage.
        builds_full = preview is not None and preview.solves_on_a_full_vessel > 0

        self.ui.lblDirList.setText(
            derived(
                f"<b>{len(half)}</b>: {escape(format_grid(half, decimals=1))}",
                "for a symmetric hull at zero heel — the other half is the mirror image "
                "and is filled in on delivery",
            )
        )

        grid = f"<b>{len(full)}</b>: {escape(format_grid(full, decimals=1))}"
        if not builds_full:
            self.ui.lblDirFullList.setText(
                derived(grid, "unused — every condition in this job is meshed as a half vessel")
            )
        elif spans_the_circle(full):
            self.ui.lblDirFullList.setText(
                derived(grid, f"{self._full_vessel_reason()} — the whole circle, as it must be")
            )
        else:
            self.ui.lblDirFullList.setText(
                f'{grid} <span style="color:{INCOMPLETE}">— {self._full_vessel_reason()}, and this '
                f"grid stops at {max(full):g}°. Nothing fills in the rest: the delivered database "
                "is interpolated across the gap and wrong there, with nothing to show why.</span>"
            )

    def _full_vessel_reason(self) -> str:
        """Why this job produces a full-vessel mesh at all."""
        if not self._library.base_shape.is_xz_symmetric:
            return "the hull is not declared symmetric, so every mesh is a full vessel"
        return "heeled conditions get a full mesh"

    def _show_lid(self) -> None:
        mode = LID_MODES[self.ui.comboLid.currentIndex()][1]
        if mode == "none":
            self.ui.lblLidInfo.setText(derived("no lid", "irregular frequencies are not removed"))
        elif mode == "surface":
            self.ui.lblLidInfo.setText(
                derived("z = 0", "panels on the free surface are still experimental in Capytaine")
            )
        elif mode == "below":
            self.ui.lblLidInfo.setText(
                derived(
                    f"z = {self.ui.spinLidZ.value():g} m",
                    "slightly below is more robust, and removes fewer irregular frequencies",
                )
            )
        else:
            # The one thing a batch can do here that the command line cannot:
            # auto needs a mesh and a highest frequency, and by the time each
            # solve starts the batch is holding both.
            self.ui.lblLidInfo.setText(
                derived(
                    "per mesh and per band",
                    "computed as each mesh is built; a band with no irregular frequencies in "
                    "range gets no lid at all",
                )
            )

    def _show_plan(self, preview, problem: str) -> None:
        """Fill the four counts, and say why Start is off when it is."""
        if preview is None:
            for label in (
                self.ui.lblPlanConditions,
                self.ui.lblPlanMeshes,
                self.ui.lblPlanSolves,
                self.ui.lblPlanProblems,
            ):
                label.setText("—")
            self._set_problem(problem)
            return

        self.ui.lblPlanConditions.setText(
            derived(
                f"<b>{preview.conditions_to_create}</b> new",
                f"{preview.conditions_existing} already there",
            )
        )
        self.ui.lblPlanMeshes.setText(
            derived(f"<b>{preview.meshes_to_build}</b> to build", f"{preview.meshes_reused} reused")
        )
        # The full-vessel count is here because it is what explains the
        # problem count: three heels is not three times one heel, it is one
        # half-circle solve and two whole-circle ones.
        on_full = preview.solves_on_a_full_vessel
        self.ui.lblPlanSolves.setText(
            derived(
                f"<b>{preview.solves_to_run}</b> to run",
                f"{on_full} on a full vessel, {preview.solves_skipped} already covered",
            )
        )
        self.ui.lblPlanProblems.setText(
            derived(
                f"<b>{preview.problems:,}</b>",
                f"six radiation per frequency, plus one per direction — "
                f"{preview.directions} headings on a half vessel, {preview.directions_full} on a full one",
            )
        )

        if preview.is_empty:
            self._set_problem(
                "everything this job describes already exists"
                if preview.conditions
                else "no conditions and no meshes were asked for"
            )
            return
        self._problem = ""
        self.ui.lblPlanProblem.setText(
            f'<span style="color:{CLEAN}">Ready. Nothing is written until Start.</span>'
        )
        self.ui.btnStart.setEnabled(not self._running())

    def _set_problem(self, reason: str) -> None:
        """Disable Start and say why (spec 09's second cross-cutting rule)."""
        self._problem = reason
        self.ui.lblPlanProblem.setText(
            f'<span style="color:{INCOMPLETE}">Nothing to start: {escape(reason)}.</span>'
        )
        self.ui.btnStart.setEnabled(False)

    # -- running -----------------------------------------------------------

    def _running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def _start(self) -> None:
        try:
            job = self.job()
            preview = plan(self._library, job, state=self._state)
        except BatchError as exc:
            self._set_problem(str(exc))
            return

        self.ui.textLog.clear()
        self._log(
            f"Starting: {preview.conditions_to_create} conditions, "
            f"{preview.meshes_to_build} meshes, {preview.solves_to_run} solves, "
            f"{preview.problems:,} problems."
        )
        self.ui.progressOverall.setMaximum(max(preview.total_steps, 1))
        self.ui.progressOverall.setValue(0)
        self.ui.progressSolve.setValue(0)
        self._set_running(True)

        self._thread = BatchThread(self._library.path, job, self)
        self._thread.progressed.connect(self._progressed)
        self._thread.completed.connect(self._completed)
        self._thread.failed.connect(self._crashed)
        self._thread.start()

    def _stop(self) -> None:
        if self._thread is not None:
            self._log("Stop: the running solve finishes and is stored; nothing further starts.")
            self._thread.stop()

    def _kill(self) -> None:
        if self._thread is not None:
            self._log(
                "Kill: terminating the workers. The solve in flight is discarded — everything "
                "already stored stays."
            )
            self._thread.kill()

    def _set_running(self, running: bool) -> None:
        self.ui.btnStart.setEnabled(not running and not self._problem)
        self.ui.btnStop.setEnabled(running)
        self.ui.btnKill.setEnabled(running)
        for group in (
            self.ui.groupConditions,
            self.ui.groupBands,
            self.ui.groupDirections,
            self.ui.groupPhysical,
            self.ui.groupLid,
            self.ui.groupParallel,
            self.ui.groupPlan,
        ):
            group.setEnabled(not running)

    def _progressed(self, event) -> None:
        self.ui.progressOverall.setMaximum(max(event.total, 1))
        self.ui.progressOverall.setValue(event.done)

        if event.solve is not None:
            self.ui.progressSolve.setMaximum(max(len(event.solve.requested), 1))
            self.ui.progressSolve.setValue(len(event.solve.solved))
        if event.kind != "solving":
            self._log(_LOG_PREFIX.get(event.kind, "") + event.message)

        # Estimated from finished steps, which are wildly uneven -- a mesh is a
        # second and a solve is minutes -- so this is a running average over
        # whatever mix has happened so far and nothing better. It is still the
        # number somebody deciding whether to wait up needs, and "about" is
        # what keeps it honest.
        remaining = ""
        if event.done and event.done < event.total:
            per = event.elapsed / event.done
            remaining = f" · about {format_duration(per * (event.total - event.done))} left"
        state = "stopping" if self._thread is not None and self._thread.stopping else "running"
        self.ui.lblProgress.setText(
            f"{event.done} of {event.total} steps · {format_duration(event.elapsed)} elapsed"
            f"{remaining} · {state}"
        )

    def _completed(self, outcome: BatchOutcome) -> None:
        self.outcome = outcome
        self._log(summarise(outcome))
        for what, why in outcome.failures:
            self._log(f"  ✗ {what}: {why}")

        colour = CONFLICT if outcome.failures else CLEAN
        ended = "Killed" if outcome.killed else "Stopped" if outcome.stopped else "Finished"
        self.ui.lblProgress.setText(
            f'<span style="color:{colour}">{ended} after {format_duration(outcome.elapsed)} — '
            f"{len(outcome.results_stored)} results stored, {len(outcome.failures)} failures."
            "</span>"
        )
        self.ui.progressSolve.setValue(0)

        # Re-read and re-previewed against the library as it now is, so the
        # counts beside Start describe what running it *again* would do --
        # which after a complete run is nothing, and after a stopped one is the
        # remainder. That is the whole resume story, said in the place a user is
        # already looking. The re-read is the run's own writes arriving: they
        # went through another connection, so nothing here has seen them yet.
        self._state = LibraryState.of(self._library)
        self._set_running(False)
        self._refresh()
        self.libraryChanged.emit()

    def _crashed(self, trace: str) -> None:
        """The run itself died, which is not the same as a step failing.

        A step that raises is caught inside the run and logged; reaching here
        means the batch could not go on at all -- a library that went away, a
        connection that could not be opened. The traceback is shown because
        there is nothing more useful to say about it, and stderr is not visible
        from a window.
        """
        self._set_running(False)
        self._log(trace)
        self.ui.lblProgress.setText(
            f'<span style="color:{CONFLICT}">The batch failed. See the log.</span>'
        )
        self.libraryChanged.emit()

    def _log(self, message: str) -> None:
        self.ui.textLog.appendPlainText(message)

    # -- keeping a job -----------------------------------------------------

    def save_job_to_file(self, *, path=None) -> Path | None:
        """Write what is on screen to a job file.

        A job is four numbers and a table that took a while to get right, and
        it outlives the run: the same one is what you start again after a night
        that ended early, what you send to whoever asked for the library, and
        what says a year later which drafts and periods this file actually
        covers. It is small enough to keep beside the library.

        Args:
            path: Where to write. Asked for when omitted, which is what the
                button does. **Keyword only**: a signal that filled it
                positionally is exactly how this got wired wrong once.

        Returns:
            The path written, or ``None`` if the job could not be read off the
            screen or the user cancelled.
        """
        try:
            job = self.job()
        except BatchError as exc:
            self._set_problem(str(exc))
            QMessageBox.warning(
                self,
                "Could not save the job",
                f"There is nothing complete to save yet.\n\n{exc}",
            )
            return None

        if path is None:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save batch job", self._beside_library(), JOB_FILTER
            )
            if not path:
                return None
        try:
            written = save_job(job, path)
        except OSError as exc:
            QMessageBox.warning(self, "Could not save the job", f"{type(exc).__name__}\n\n{exc}")
            return None

        self._log(f"Job saved to {written}.")
        return written

    def load_job_from_file(self, *, path=None) -> BatchJob | None:
        """Read a job file back onto the screen.

        Refused outright while a batch is running: the settings are what the
        run is executing, and replacing them under it would leave the screen
        describing one job and the workers doing another.

        Args:
            path: The file. Asked for when omitted. **Keyword only**, as on
                :meth:`save_job_to_file` and for the same reason.

        Returns:
            The job loaded, or ``None`` if nothing was.
        """
        if self._running():
            QMessageBox.information(
                self,
                "A batch is running",
                "Stop it before loading another job. What is on screen is what the run is "
                "doing, and the two have to stay the same thing.",
            )
            return None

        if path is None:
            path, _ = QFileDialog.getOpenFileName(
                self, "Load batch job", self._beside_library(), JOB_FILTER
            )
            if not path:
                return None
        try:
            job = load_job(path)
        except BatchError as exc:
            QMessageBox.warning(self, "Could not load the job", f"{exc}")
            return None

        notes = self.fill_from(job)
        self._log(f"Job loaded from {path}.")
        for note in notes:
            self._log(f"  ! {note}")
        if notes:
            # Not a refusal -- the job is loaded and every part that fits is on
            # screen. But a difference between the file and what is about to be
            # solved has to be read before Start, not found in the library
            # afterwards.
            QMessageBox.warning(
                self,
                "Loaded, with differences",
                "The job is loaded, but this screen cannot show all of it exactly:\n\n"
                + "\n\n".join(f"• {note}" for note in notes),
            )
        return job

    def _beside_library(self) -> str:
        """Where the file dialogs open: next to the library, named after it.

        A job belongs to the library it was written for -- its bands are chosen
        against that hull's panel sizes and its drafts against that hull's
        depth -- so that is where it should land by default.
        """
        return str(self._library.path.with_suffix(JOB_SUFFIX))

    # -- odds and ends -----------------------------------------------------

    def fill_from(self, job: BatchJob) -> list[str]:
        """Put a job back on the screen, and say what would not fit.

        The inverse of :meth:`job`, and not quite a total one: a
        :class:`~pylot_bem.batch.BatchJob` holds an explicit list of
        ``z_origins`` and a list of heels and trims, where this screen holds
        from/to/step and two text fields. A job a script built can therefore
        say things no arrangement of these widgets says -- drafts that are not
        evenly spaced, bands at different remesh iterations, conditions listed
        by id that this library has never heard of.

        None of that is an error and none of it is silently dropped. What can
        be shown is shown, and what cannot is **returned**, for the caller to
        put in front of the user. Loading a job that quietly became a different
        job is the one outcome this must not have: the whole reason to save one
        is to run the same thing again.

        Returns:
            A sentence per thing that could not be represented. Empty when the
            screen now says exactly what the job said.
        """
        notes = []

        self.ui.chkCreateConditions.setChecked(bool(job.z_origins))
        if job.z_origins:
            step = self.ui.spinZStep.value()
            if len(job.z_origins) > 1:
                step = round(job.z_origins[1] - job.z_origins[0], 12)
            self.ui.spinZFrom.setValue(min(job.z_origins))
            self.ui.spinZTo.setValue(max(job.z_origins))
            self.ui.spinZStep.setValue(abs(step) or 0.1)
            if self.z_origins() != job.z_origins:
                notes.append(
                    f"Its {len(job.z_origins)} drafts are not an evenly spaced range, and this "
                    f"screen only writes one. It now shows {len(self.z_origins())} — check them "
                    "before starting."
                )

        # Degrees on the way back onto the screen, as on the way off it. `%g`
        # rather than a fixed number of places, so a whole degree reads as "1"
        # and not "1.000000" -- the field is meant to be edited by hand.
        for values, field in ((job.heels, self.ui.editHeels), (job.trims, self.ui.editTrims)):
            field.setText(", ".join(f"{degrees_from_slope(v):g}" for v in values))

        if job.bands:
            self.ui.editBands.setPlainText(format_bands(job.bands))
            iterations = {band.iterations for band in job.bands}
            self.ui.spinIterations.setValue(min(iterations))
            if len(iterations) > 1:
                notes.append(
                    f"Its bands use different remesh iterations ({sorted(iterations)}) and this "
                    f"screen has one for the whole job. It now shows {min(iterations)}."
                )

        if job.targets == TARGET_LISTED:
            known = {condition.id for condition in self._state.conditions}
            self._selected = tuple(i for i in job.condition_ids if i in known)
            self.ui.comboTargets.setItemText(
                2, f"{TARGET_CAPTIONS[2][0]} ({len(self._selected)})"
            )
            self.ui.comboTargets.model().item(2).setEnabled(bool(self._selected))
            missing = len(job.condition_ids) - len(self._selected)
            if missing:
                notes.append(
                    f"{missing} of the {len(job.condition_ids)} conditions it names are not in "
                    "this library. Ids belong to the library they were made in, so a job that "
                    "lists them only means the same thing against the same file."
                )

        self.ui.comboTargets.setCurrentIndex(
            next(i for i, (_, value) in enumerate(TARGET_CAPTIONS) if value == job.targets)
        )
        self.ui.comboLid.setCurrentIndex(
            next(i for i, (_, value) in enumerate(LID_MODES) if value == job.lid)
        )
        self.ui.spinLidZ.setValue(job.lid_z)
        self.ui.chkInfiniteDepth.setChecked(bool(np.isinf(job.water_depth)))
        if not np.isinf(job.water_depth):
            self.ui.spinDepth.setValue(job.water_depth)
        self.ui.spinG.setValue(job.g)
        self.ui.spinSpeed.setValue(job.forward_speed)
        self._fill_directions(job.wave_directions, notes, full_vessel=False)
        # Falls back the way the job does, so what the screen shows is what a
        # run would use rather than an empty row implying no headings at all.
        self._fill_directions(
            job.directions_for(is_xz_symmetric=False), notes, full_vessel=True
        )
        self.ui.spinWorkers.setValue(job.workers or default_workers(64))
        self.ui.spinOmp.setValue(job.omp_threads)
        self.ui.chkResume.setChecked(job.resume)
        self._refresh()
        return notes

    def _fill_directions(self, directions, notes: list[str], *, full_vessel: bool) -> None:
        """Show one direction grid as the from/to/step this screen holds.

        Same shape of problem as the drafts, and same answer: reproduce it
        where it is a range, and say so where it is not rather than quietly
        solving a different set of headings.
        """
        which = "full-vessel" if full_vessel else "half-vessel"
        spins = (
            (self.ui.spinDirFullFrom, self.ui.spinDirFullTo, self.ui.spinDirFullStep)
            if full_vessel
            else (self.ui.spinDirFrom, self.ui.spinDirTo, self.ui.spinDirStep)
        )
        first, last, step_of = spins

        if not directions:
            for spin in spins:
                spin.setValue(0.0)
            return
        step = directions[1] - directions[0] if len(directions) > 1 else 15.0
        first.setValue(directions[0])
        last.setValue(directions[-1])
        step_of.setValue(step)
        if self.directions(full_vessel=full_vessel) != tuple(directions):
            # A grid that wrapped lost its last point on the way out, so the
            # "to" that reproduces it is one step past the last one it kept.
            last.setValue(directions[-1] + step)
            if self.directions(full_vessel=full_vessel) != tuple(directions):
                notes.append(
                    f"Its {len(directions)} {which} wave directions are not an evenly spaced "
                    f"range, and this screen only writes one. It now shows "
                    f"{len(self.directions(full_vessel=full_vessel))}."
                )

    def closeEvent(self, event) -> None:
        """Refuse to close over a running batch, or kill it on request.

        The same rule as the Solve screen, with one more thing at stake: this
        thread holds a connection to the library and writes to it between
        solves, so closing the window over a running batch would orphan a
        worker pool *and* leave the file being written to by a thread nothing
        has a handle on.
        """
        if self._thread is not None and self._thread.isRunning():
            answer = QMessageBox.question(
                self,
                "A batch is running",
                "Killing the workers now loses the solve in flight. Everything already stored "
                "stays, and running the same job again continues from there. Close anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._thread.kill()
            self._thread.wait(30_000)
        event.accept()


# What each kind of event looks like in the log. A night's run is read the
# morning after by scrolling, so failures and warnings have to be findable
# without reading every line.
_LOG_PREFIX = {
    "condition": "+ ",
    "mesh": "  + ",
    "solve": "  = ",
    "skip": "  · ",
    "warning": "  ! ",
    "failed": "  ✗ ",
}
