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
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox, QWidget

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
        self.ui.btnSaveJob.clicked.connect(self.save_job_to_file)
        self.ui.btnLoadJob.clicked.connect(self.load_job_from_file)

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
        """Take the layout's own height, but never more than the screen has.

        Two columns of wrapped explanation report a minimum height only once
        they have a width to wrap against, so the dialog opens shorter than the
        sum of what is in it and the group boxes draw over each other --
        SolveDialog carries the same line for the same reason.

        Capped, which SolveDialog does not need to be: this screen is half again
        as tall, and asking for 1260 pixels on a 1080-pixel display puts Start,
        Stop and Kill below the bottom edge with no way to reach them. Under the
        cap the log gives up its space first, which is the part that can be
        scrolled.
        """
        wanted = self.sizeHint().height()
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            wanted = min(wanted, int(screen.availableGeometry().height() * 0.92))
        self.resize(self.width(), wanted)

    # -- reading the screen ------------------------------------------------

    def z_origins(self) -> tuple[float, ...]:
        """The z_origin grid, empty when the conditions are switched off."""
        if not self.ui.chkCreateConditions.isChecked():
            return ()
        return value_range(
            self.ui.spinZFrom.value(), self.ui.spinZTo.value(), self.ui.spinZStep.value()
        )

    def directions(self) -> tuple[float, ...]:
        """The direction grid, with no duplicate at the wrap-around.

        0 and 360 are the same heading, and solving both costs a full set of
        problems for a second copy of a column that is already there -- the
        same rule, and the same modulo test, as the Solve screen.
        """
        values = value_range(
            self.ui.spinDirFrom.value(), self.ui.spinDirTo.value(), self.ui.spinDirStep.value()
        )
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
        self.ui.spinLidZ.setEnabled(self.ui.comboLid.currentIndex() == _LID_BELOW)
        self._show_grid()
        self._show_bands()
        self._show_directions()
        self._show_lid()
        self._show_plan()

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

    def _show_directions(self) -> None:
        """The grid, and what decides whether half the circle is enough.

        A heeled condition gets a full mesh whatever the hull is, and a full
        mesh has no port half to mirror -- so the answer depends on the job's
        heels, not on the library alone. It is worth a sentence here because
        this is the one setting where getting it wrong is invisible: half a
        circle solved on an asymmetric body delivers a database mafredo will
        interpolate across and answer confidently from.
        """
        directions = self.directions()
        if not self._library.base_shape.is_xz_symmetric:
            why = "the hull is not declared symmetric, so every mesh is a full vessel — solve the whole circle"
        elif self._any_heeled():
            why = "heeled conditions get a full mesh, and a full mesh has no half to mirror — those need the whole circle"
        else:
            why = "symmetric and unheeled — the other half is the mirror image and is filled in on delivery"
        self.ui.lblDirList.setText(
            derived(f"<b>{len(directions)}</b>: {escape(format_grid(directions, decimals=1))}", why)
        )

    def _any_heeled(self) -> bool:
        """Whether any condition this job touches is heeled.

        From the grid when it creates conditions, and from the library when it
        does not -- in both cases the conditions that will actually be meshed.
        """
        if self.ui.chkCreateConditions.isChecked():
            try:
                return any(abs(d) > 0 for d in parse_numbers(self.ui.editHeels.text(), what="Heel"))
            except BatchError:
                return False
        return any(condition.heel != 0.0 for condition in self._library.conditions())

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

    def _show_plan(self) -> None:
        """Fill the four counts, and say why Start is off when it is."""
        try:
            preview = plan(self._library, self.job(), state=self._state)
        except BatchError as exc:
            for label in (
                self.ui.lblPlanConditions,
                self.ui.lblPlanMeshes,
                self.ui.lblPlanSolves,
                self.ui.lblPlanProblems,
            ):
                label.setText("—")
            self._set_problem(str(exc))
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
        self.ui.lblPlanSolves.setText(
            derived(
                f"<b>{preview.solves_to_run}</b> to run",
                f"{preview.solves_skipped} already covered",
            )
        )
        self.ui.lblPlanProblems.setText(
            derived(
                f"<b>{preview.problems:,}</b>",
                "six radiation per frequency, plus one per direction",
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

    def save_job_to_file(self, path=None) -> Path | None:
        """Write what is on screen to a job file.

        A job is four numbers and a table that took a while to get right, and
        it outlives the run: the same one is what you start again after a night
        that ended early, what you send to whoever asked for the library, and
        what says a year later which drafts and periods this file actually
        covers. It is small enough to keep beside the library.

        Args:
            path: Where to write. Asked for when omitted, which is what the
                button does.

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

    def load_job_from_file(self, path=None) -> BatchJob | None:
        """Read a job file back onto the screen.

        Refused outright while a batch is running: the settings are what the
        run is executing, and replacing them under it would leave the screen
        describing one job and the workers doing another.

        Args:
            path: The file. Asked for when omitted.

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
        self._fill_directions(job.wave_directions, notes)
        self.ui.spinWorkers.setValue(job.workers or default_workers(64))
        self.ui.spinOmp.setValue(job.omp_threads)
        self.ui.chkResume.setChecked(job.resume)
        self._refresh()
        return notes

    def _fill_directions(self, directions, notes: list[str]) -> None:
        """Show a direction grid as the from/to/step this screen holds.

        Same shape of problem as the drafts, and same answer: reproduce it
        where it is a range, and say so where it is not rather than quietly
        solving a different set of headings.
        """
        if not directions:
            self.ui.spinDirStep.setValue(0.0)
            self.ui.spinDirFrom.setValue(0.0)
            self.ui.spinDirTo.setValue(0.0)
            return
        step = directions[1] - directions[0] if len(directions) > 1 else 15.0
        self.ui.spinDirFrom.setValue(directions[0])
        # A grid that wrapped lost its last point on the way out, so the "to"
        # that reproduces it is one step past the last one it kept.
        self.ui.spinDirTo.setValue(directions[-1])
        self.ui.spinDirStep.setValue(step)
        if self.directions() != tuple(directions):
            self.ui.spinDirTo.setValue(directions[-1] + step)
            if self.directions() != tuple(directions):
                notes.append(
                    f"Its {len(directions)} wave directions are not an evenly spaced range, and "
                    f"this screen only writes one. It now shows {len(self.directions())}."
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
