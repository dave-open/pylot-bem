"""The three dialogs: import a base shape, build a mesh, run a solve.

Each is a filler over a ``.ui`` file, like the property panes, and for the same
reason -- these are the screens most worth fine-tuning in Designer.

What they have in common is spec 09's fourth cross-cutting rule: **cost is
shown before it is incurred**. The import dialog shows the bounds the chosen
unit produces before the library is created; the solve dialog shows the problem
count, the peak memory and the mesh's resolution limit before Start. All three
numbers are cheap, and all three are useless in a log afterwards.
"""

from dataclasses import replace
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFileDialog, QListWidgetItem, QMessageBox, QWidget

from pylot_bem.app.formatting import (
    CLEAN,
    CONFLICT,
    INCOMPLETE,
    derived,
    escape,
    format_grid,
    format_point,
    omega_from_period,
    period_from_omega,
    slope_from_degrees,
    symmetry_reason,
)
from pylot_bem.app.forms.dlg_create_mesh_ui import Ui_DlgCreateMesh
from pylot_bem.app.forms.dlg_delete_frequencies_ui import Ui_DlgDeleteFrequencies
from pylot_bem.app.forms.dlg_new_condition_ui import Ui_DlgNewCondition
from pylot_bem.app.forms.dlg_new_library_ui import Ui_DlgNewLibrary
from pylot_bem.app.forms.dlg_solve_ui import Ui_DlgSolve
from pylot_bem.app.solving import SolveThread
from pylot_bem.estimates import format_memory, shortest_reliable_period, solved_panels
from pylot_bem.geometry import load_mesh_file
from pylot_bem.mesh_pipeline import MeshPipelineError, application_point_for, check_full_mesh, submerged_summary
from pylot_bem.pool import PoolSolve, default_workers
from pylot_bem.solver import SolveSettings, auto_lid_z
from pylot_db.frames import check_domain, transform

__all__ = [
    "UNITS",
    "CreateMeshDialog",
    "DeleteFrequenciesDialog",
    "NewConditionDialog",
    "NewLibraryDialog",
    "SolveDialog",
]

# Spec 09 section A: the library is always metres and this is the only
# conversion in the application. Offered as named units rather than a factor
# so that "×0.001" cannot be typed as "×0.01".
UNITS = (
    ("metres (×1)", 1.0),
    ("millimetres (×0.001)", 0.001),
    ("centimetres (×0.01)", 0.01),
    ("feet (×0.3048)", 0.3048),
)

# The lid choices Capytaine actually offers (spec 09 section E.2). Exactly two
# knobs exist, so exactly four modes are meaningful and no more.
LID_NONE, LID_SURFACE, LID_BELOW, LID_AUTO = range(4)
LID_CHOICES = ("None", "At free surface", "Below free surface", "Auto")


def chosen_id(text: str, taken) -> tuple[str | None, str]:
    """Read a typed id, or say why it cannot be used.

    Ids are **opaque**: nothing in the system parses one, and no behaviour may
    depend on one (ADR-4). That is precisely what makes a hand-typed id safe --
    it can say whatever a user finds useful without anything downstream coming
    to rely on it. The previous implementation encoded parameters in names and
    then parsed them back, which is the failure this rule exists to prevent;
    letting a human choose the string is not that, as long as no code ever
    reads meaning out of it.

    What a typed id costs is **permanence**. Unlike a label it cannot be
    corrected afterwards: meshes and results point at it, so changing one would
    mean re-pointing everything that refers to it. Blank is therefore a fine
    answer and the placeholder says so.

    Args:
        text: The field as typed.
        taken: Ids already in use for this kind of entity.

    Returns:
        ``(id, problem)``. ``id`` is ``None`` when the field is blank -- let
        one be generated -- or when ``problem`` is set.
    """
    wanted = text.strip()
    if not wanted:
        return None, ""
    if wanted in set(taken):
        return None, f"{wanted!r} is already used. Ids are unique and an existing one is never replaced."
    return wanted, ""


def wire_button_box(dialog: QDialog) -> None:
    """Make OK and Cancel do something.

    A ``QDialogButtonBox`` emits ``accepted`` and ``rejected``; on its own it
    does **not** close the dialog. Qt Designer normally writes the connection
    to ``accept()`` / ``reject()`` into the ``.ui`` file's ``<connections>``
    block, so a dialog laid out in Designer appears to work by magic -- and one
    whose ``.ui`` was written by hand silently has buttons that do nothing.
    That is exactly what happened here.

    Connected in **Python** rather than added to the ``.ui`` on purpose. These
    files exist to be reopened and re-saved in Designer, and a connection is
    the easiest thing in one to drop by accident. Here it cannot be lost, and
    it is visible to anyone reading the dialog.
    """
    dialog.ui.buttonBox.accepted.connect(dialog.accept)
    dialog.ui.buttonBox.rejected.connect(dialog.reject)


class NewLibraryDialog(QDialog):
    """Import a base shape and create a library around it.

    The one screen where a base shape is chosen, because it is immutable once
    any mesh or result exists (spec 02 section 1) and in practice that means
    immediately. So the checks happen here, where the user can still pick a
    different file: the bounds under the chosen unit, and the refusal of a half
    mesh.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ui = Ui_DlgNewLibrary()
        self.ui.setupUi(self)
        wire_button_box(self)

        for label, _ in UNITS:
            self.ui.comboUnits.addItem(label)
        self.ui.chkSymmetric.setChecked(False)

        self.ui.btnBrowseMesh.clicked.connect(self._browse_mesh)
        self.ui.btnBrowseLibrary.clicked.connect(self._browse_library)
        self.ui.editMeshFile.editingFinished.connect(self._reload)
        self.ui.comboUnits.currentIndexChanged.connect(self._refresh)
        self.ui.editOrigin.textChanged.connect(self._refresh)
        self.ui.editLibraryFile.textChanged.connect(self._refresh)

        self._vertices = None
        self._faces = None
        self._problem = ""
        self._refresh()

    # -- state -------------------------------------------------------------

    @property
    def scale(self) -> float:
        return UNITS[self.ui.comboUnits.currentIndex()][1]

    def values(self) -> dict:
        """Exactly the arguments :meth:`~pylot_bem.api.Pylot.create_new` takes."""
        return {
            "path": Path(self.ui.editLibraryFile.text().strip()),
            "mesh_file": Path(self.ui.editMeshFile.text().strip()),
            "origin_description": self.ui.editOrigin.text().strip(),
            "is_xz_symmetric": self.ui.chkSymmetric.isChecked(),
            "scale": self.scale,
            "vessel_name": self.ui.editVesselName.text().strip(),
            "description": self.ui.editDescription.text().strip(),
        }

    def preview_geometry(self):
        """The scaled vertices and faces, or ``None`` if nothing loaded."""
        if self._vertices is None:
            return None
        return self._vertices * self.scale, self._faces

    # -- loading -----------------------------------------------------------

    def _browse_mesh(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Base shape", "", "Meshes (*.stl *.obj *.ply *.off);;All files (*)"
        )
        if path:
            self.ui.editMeshFile.setText(path)
            self._reload()

    def _browse_library(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "New library", "", "pylot library (*.pylot)")
        if path:
            self.ui.editLibraryFile.setText(path)

    def _reload(self) -> None:
        """Read the file once, at scale 1.

        Re-reading on every change of unit would re-parse the file to multiply
        it by a constant. The checks below are all scale-invariant -- a half
        mesh is a half mesh in any unit -- so the raw geometry is kept and
        scaled for display.
        """
        text = self.ui.editMeshFile.text().strip()
        self._vertices = self._faces = None
        self._problem = ""

        if not text:
            self._refresh()
            return
        try:
            self._vertices, self._faces = load_mesh_file(Path(text), scale=1.0)
        except Exception as exc:
            self._problem = f"{type(exc).__name__}: {exc}"
        else:
            if not self.ui.editVesselName.text().strip():
                self.ui.editVesselName.setText(Path(text).stem)
            if not self.ui.editLibraryFile.text().strip():
                self.ui.editLibraryFile.setText(str(Path(text).with_suffix(".pylot")))
        self._refresh()

    def _refresh(self) -> None:
        geometry = self.preview_geometry()
        if geometry is None:
            for label in (self.ui.lblBoundsX, self.ui.lblBoundsY, self.ui.lblBoundsZ, self.ui.lblCounts):
                label.setText("—")
            self.ui.lblChecks.setText(
                f'<span style="color:{CONFLICT}">{escape(self._problem)}</span>'
                if self._problem
                else "Choose a base shape file."
            )
            self._set_ok(False, "no base shape chosen")
            return

        vertices, faces = geometry
        lo, hi = vertices.min(axis=0), vertices.max(axis=0)
        for label, axis in ((self.ui.lblBoundsX, 0), (self.ui.lblBoundsY, 1), (self.ui.lblBoundsZ, 2)):
            label.setText(derived(f"{lo[axis]:.2f} … {hi[axis]:.2f}", f"L {hi[axis] - lo[axis]:.2f}"))
        self.ui.lblCounts.setText(f"{len(vertices)} vertices, {len(faces)} faces")

        try:
            check_full_mesh(vertices)
        except MeshPipelineError as exc:
            self.ui.lblChecks.setText(f'<span style="color:{CONFLICT}">✗ {escape(str(exc))}</span>')
            self._set_ok(False, "the file is a half mesh")
            return

        self.ui.lblChecks.setText(
            f'<span style="color:{CLEAN}">✓ Full mesh — vertices on both sides of y = 0.</span>'
        )
        if not self.ui.editOrigin.text().strip():
            self._set_ok(False, "origin description is required")
        elif not self.ui.editLibraryFile.text().strip():
            self._set_ok(False, "no library file chosen")
        elif Path(self.ui.editLibraryFile.text().strip()).exists():
            self._set_ok(False, "that library file already exists")
        else:
            self._set_ok(True, "")

    def _set_ok(self, enabled: bool, reason: str) -> None:
        """Enable Create, and say why not when it is off (spec 09 rule 2)."""
        button = self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok)
        button.setText("Create library")
        button.setEnabled(enabled)
        self.ui.lblFooterHint.setText(
            "The only moment a base shape is chosen. It is fixed for the life of the library."
            if enabled
            else f'<span style="color:{INCOMPLETE}">Cannot create: {escape(reason)}.</span>'
        )


class CreateMeshDialog(QDialog):
    """Pick ``pct`` and ``iterations`` for one condition.

    Two settings and one derived fact, which is the whole screen. There is
    deliberately no cost preview: the panel count comes out of the regrid and
    cannot be known before it runs, and an invented estimate beside two real
    numbers would be indistinguishable from them.
    """

    def __init__(self, library, condition, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ui = Ui_DlgCreateMesh()
        self.ui.setupUi(self)
        wire_button_box(self)

        self._library = library
        self._condition = condition
        self.ui.editId.textChanged.connect(self._check_id)
        self.setWindowTitle(f"Create mesh — condition {condition.id}")
        self.ui.lblHeading.setText(
            f"Condition <b>{escape(condition.id)}</b> — z_origin {condition.z_origin:.2f} m"
        )

        symmetric, reason = symmetry_reason(library.base_shape.is_xz_symmetric, condition.heel)
        self.ui.lblSymmetry.setText(derived("<b>Half vessel</b>" if symmetric else "<b>Full vessel</b>", reason))

    def values(self) -> dict:
        """Exactly the arguments :meth:`~pylot_bem.api.Pylot.create_mesh` takes."""
        return {
            "pct": self.ui.spinPct.value(),
            "iterations": self.ui.spinIterations.value(),
            "mesh_id": chosen_id(self.ui.editId.text(), self._taken())[0],
        }

    def _taken(self):
        return [mesh.id for mesh in self._library.meshes()]

    def _check_id(self) -> None:
        _value, problem = chosen_id(self.ui.editId.text(), self._taken())
        self.ui.lblIdProblem.setText(
            f'<span style="color:{CONFLICT}">{escape(problem)}</span>' if problem else ""
        )
        self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok).setEnabled(not problem)


class NewConditionDialog(QDialog):
    """One floating condition, entered in degrees and metres.

    Everything below the entry fields is derived and recomputed as it is
    typed -- including the waterline cut, which is what makes a wrong sign on
    ``z_origin`` say *nothing lies below the waterplane* immediately rather
    than at the first mesh. The cut is the same one the condition will be
    created with, so the preview cannot disagree with the result.

    One at a time, deliberately: spec 09 section C rules out bulk creation.
    """

    def __init__(self, library, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ui = Ui_DlgNewCondition()
        self.ui.setupUi(self)
        wire_button_box(self)
        self._library = library

        for widget in (self.ui.spinZOrigin, self.ui.spinHeel, self.ui.spinTrim):
            widget.valueChanged.connect(self._refresh)
        self.ui.editId.textChanged.connect(self._refresh)
        self._refresh()

    def values(self) -> dict:
        """Exactly the arguments :meth:`~pylot_bem.api.Pylot.create_condition` takes."""
        return {
            "z_origin": self.ui.spinZOrigin.value(),
            # Degrees at the boundary, slopes everywhere inside (spec 01 §7).
            "heel": slope_from_degrees(self.ui.spinHeel.value()),
            "trim": slope_from_degrees(self.ui.spinTrim.value()),
            "label": self.ui.editLabel.text().strip(),
            "condition_id": chosen_id(self.ui.editId.text(), self._taken())[0],
        }

    def _taken(self):
        return [condition.id for condition in self._library.conditions()]

    def _refresh(self) -> None:
        values = self.values()
        base = self._library.base_shape

        _value, id_problem = chosen_id(self.ui.editId.text(), self._taken())
        if id_problem:
            self.ui.lblProblem.setText(f'<span style="color:{CONFLICT}">{escape(id_problem)}</span>')
            self._set_ok(False)
            return

        symmetric, reason = symmetry_reason(base.is_xz_symmetric, values["heel"])
        self.ui.lblSymmetry.setText(derived("yes" if symmetric else "<b>no</b>", reason))

        try:
            check_domain(trim=values["trim"], heel=values["heel"])
            pose = transform(trim=values["trim"], heel=values["heel"], z_origin=values["z_origin"])
            point = application_point_for(base, pose)
            summary = submerged_summary(base, pose)
        except (ValueError, MeshPipelineError) as exc:
            self.ui.lblApplicationPoint.setText("—")
            self.ui.lblSubmerged.setText("—")
            self.ui.lblProblem.setText(f'<span style="color:{CONFLICT}">{escape(str(exc))}</span>')
            self._set_ok(False)
            return

        self.ui.lblApplicationPoint.setText(derived(format_point(point), "vessel-local"))
        self.ui.lblSubmerged.setText(
            derived(
                f"{summary.wetted_area:,.0f} m² wetted, {summary.waterline_length:.2f} m at the waterline",
                "display only — nothing computes from it",
            )
        )
        self.ui.lblProblem.setText(self._duplicate_warning(values))
        self._set_ok(True)

    def _duplicate_warning(self, values) -> str:
        """Say when this is the condition next door, before it is created.

        Storage refuses a duplicate within 1e-3 (spec 02 section 4). Saying so
        here turns a refusal into a choice.
        """
        for existing in self._library.conditions():
            close = (
                abs(existing.z_origin - values["z_origin"]) <= 1e-3
                and abs(existing.heel - values["heel"]) <= 1e-3
                and abs(existing.trim - values["trim"]) <= 1e-3
            )
            if close:
                return (
                    f'<span style="color:{INCOMPLETE}">Condition <b>{escape(existing.id)}</b> is already '
                    "at these values within the 1e-3 tolerance, so this will be refused.</span>"
                )
        return ""

    def _set_ok(self, enabled: bool) -> None:
        self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok).setEnabled(enabled)


class DeleteFrequenciesDialog(QDialog):
    """Trim a result's frequency grid.

    The significant maintenance operation of spec 09 section I.1, and the
    reason a stored result's grid is editable at all: a result over a shorter
    grid is still a *complete* result, so removing the frequencies one of two
    competing runs should not have covered resolves the conflict without
    throwing away the frequencies they do not contest.

    The preview says **which conflicts this resolves and which frequencies go
    missing entirely**, because trading a conflict for a silent gap is not a
    fix.
    """

    def __init__(self, library, result, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ui = Ui_DlgDeleteFrequencies()
        self.ui.setupUi(self)
        wire_button_box(self)

        self._library = library
        self._result = result
        self._contested = self._contested_omegas()

        self.setWindowTitle(f"Delete frequencies — {result.id}")
        self.ui.lblHeading.setText(
            f"Result <b>{escape(result.id)}</b> covers {len(result.omegas)} frequencies."
        )

        for omega in sorted(result.omegas, key=lambda w: -w):
            contested = any(abs(omega - other) <= 1e-9 for other in self._contested)
            item = QListWidgetItem(f"{'⚠ ' if contested else ''}{period_from_omega(omega):.3f} s")
            item.setData(Qt.ItemDataRole.UserRole, float(omega))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.ui.listFrequencies.addItem(item)

        self.ui.listFrequencies.itemChanged.connect(self._refresh)
        self.ui.btnCheckConflicted.clicked.connect(self._check_contested)
        self.ui.btnCheckNone.clicked.connect(lambda: self._set_all(Qt.CheckState.Unchecked))
        self._refresh()

    def _contested_omegas(self) -> list[float]:
        """Frequencies where another result claims the same quantity."""
        contested = []
        for view in self._library.databases():
            if self._result.id not in view.result_ids:
                continue
            contested.extend(c.omega for c in view.conflicts)
        return contested

    def chosen_omegas(self) -> list[float]:
        items = (self.ui.listFrequencies.item(i) for i in range(self.ui.listFrequencies.count()))
        return [
            item.data(Qt.ItemDataRole.UserRole)
            for item in items
            if item.checkState() == Qt.CheckState.Checked
        ]

    def _set_all(self, state) -> None:
        self.ui.listFrequencies.blockSignals(True)
        for i in range(self.ui.listFrequencies.count()):
            self.ui.listFrequencies.item(i).setCheckState(state)
        self.ui.listFrequencies.blockSignals(False)
        self._refresh()

    def _check_contested(self) -> None:
        self.ui.listFrequencies.blockSignals(True)
        for i in range(self.ui.listFrequencies.count()):
            item = self.ui.listFrequencies.item(i)
            omega = item.data(Qt.ItemDataRole.UserRole)
            contested = any(abs(omega - other) <= 1e-9 for other in self._contested)
            item.setCheckState(Qt.CheckState.Checked if contested else Qt.CheckState.Unchecked)
        self.ui.listFrequencies.blockSignals(False)
        self._refresh()

    def _refresh(self, *_args) -> None:
        self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(self.chosen_omegas()))
        self.ui.lblPreview.setText(self._preview_text())

    def _preview_text(self) -> str:
        """What the current ticks would do, as rich text.

        Separate from the widget it fills so the preview can be asserted on
        without reading it back out of a label.
        """
        chosen = self.chosen_omegas()
        if not chosen:
            return "Nothing ticked, so nothing would be removed."

        plan = self._library.plan_frequency_deletion(self._result.id, chosen)
        lines = []
        if plan.results_removed:
            lines.append(
                f'<span style="color:{CONFLICT}">Every frequency is ticked, so the result itself is '
                "removed — an empty result is not a state worth keeping.</span>"
            )
        else:
            lines.append(f"Removes {len(chosen)} of {len(self._result.omegas)} frequencies from this result.")

        resolved = [w for w in chosen if any(abs(w - other) <= 1e-9 for other in self._contested)]
        if resolved:
            where = ", ".join(f"{period_from_omega(w):.2f} s" for w in resolved)
            lines.append(
                f'<span style="color:{CLEAN}">Resolves the conflict at {escape(where)}.</span>'
            )

        orphaned = self._would_become_missing(chosen)
        if orphaned:
            where = ", ".join(f"{period_from_omega(w):.2f} s" for w in orphaned)
            lines.append(
                f'<span style="color:{INCOMPLETE}">Leaves the database with nothing at {escape(where)} — '
                "a gap, not a fix. Solve those elsewhere, or leave them here.</span>"
            )
        return "<br>".join(lines)

    def _would_become_missing(self, chosen) -> list[float]:
        """Frequencies whose only contributor is the one being trimmed."""
        missing = []
        for view in self._library.databases():
            if self._result.id not in view.result_ids:
                continue
            for coverage in view.coverage:
                if not any(abs(coverage.omega - w) <= 1e-9 for w in chosen):
                    continue
                suppliers = set(coverage.radiation) | set(coverage.diffraction)
                if suppliers <= {self._result.id}:
                    missing.append(coverage.omega)
        return missing


class SolveDialog(QDialog):
    """Set up a solve, run it, and store what comes back.

    The only long-running screen in the application, and the reason
    :mod:`pylot_bem.pool` exists. Three things it must get right:

    - **progress is per frequency** (spec 06 section 6.5.1), and the grid is
      shown rather than a count, because under several workers the completed
      set has holes;
    - **Stop and Kill cost different things** and both say so on the button;
    - a **failed frequency is visible**. A grid that quietly came back short is
      how a database ends up incomplete with nothing to show why.

    Signals:
        resultStored: The id of the result written, when one was.
    """

    resultStored = Signal(str)

    def __init__(self, library, mesh, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ui = Ui_DlgSolve()
        self.ui.setupUi(self)

        self._library = library
        self._mesh = mesh
        self._thread: SolveThread | None = None
        self._settings: SolveSettings | None = None
        self._chips: dict[float, QListWidgetItem] = {}

        self.setWindowTitle(f"Solve — mesh {mesh.id}")
        condition = library.condition(mesh.condition_id)
        self.ui.lblHeading.setText(
            f"Mesh <b>{escape(mesh.id)}</b> at condition <b>{escape(condition.id)}</b> — "
            f"{len(mesh.faces)} faces, pct {mesh.pct:g}"
        )

        for choice in LID_CHOICES:
            self.ui.comboLid.addItem(choice)
        self.ui.spinWorkers.setValue(default_workers(64))
        self.ui.editId.textChanged.connect(self._refresh)

        # How far round the compass to go, from the mesh rather than a
        # constant. A symmetric body's port half is the mirror of its
        # starboard half, so solving it computes numbers already known and
        # doubles the run for nothing; an asymmetric one genuinely needs the
        # whole circle. The endpoint is dropped either way -- see
        # `directions`.
        self.ui.spinDirTo.setValue(180.0 if mesh.is_xz_symmetric else 360.0)

        for widget in (
            self.ui.spinPeriodFrom,
            self.ui.spinPeriodTo,
            self.ui.spinPeriodStep,
            self.ui.spinDirFrom,
            self.ui.spinDirTo,
            self.ui.spinDirStep,
            self.ui.spinG,
            self.ui.spinDepth,
            self.ui.spinLidZ,
        ):
            widget.valueChanged.connect(self._refresh)
        self.ui.spinWorkers.valueChanged.connect(self._refresh)
        self.ui.comboLid.currentIndexChanged.connect(self._refresh)
        self.ui.chkInfiniteDepth.toggled.connect(self._depth_toggled)

        self.ui.btnStart.clicked.connect(self._start)
        self.ui.btnStop.clicked.connect(self._stop)
        self.ui.btnKill.clicked.connect(self._kill)
        self.ui.btnClose.clicked.connect(self.close)

        self._refresh()

    # -- settings ----------------------------------------------------------

    def periods(self) -> list[float]:
        """The period grid, ascending, as typed."""
        start = self.ui.spinPeriodFrom.value()
        stop = self.ui.spinPeriodTo.value()
        step = self.ui.spinPeriodStep.value()
        if step <= 0 or stop < start:
            return [start]
        count = int(np.floor((stop - start) / step + 1e-9)) + 1
        return [start + i * step for i in range(max(count, 1))]

    def directions(self) -> list[float]:
        """The direction grid, with no duplicate at the wrap-around.

        0 and 360 are the same heading. Solving both costs a full set of
        problems -- six radiation plus every frequency -- for a second copy
        of a column that is already there, and leaves the stored result with
        two identical directions for every consumer to trip over. So a grid
        that comes back round to where it started drops its last point.

        Checked modulo 360 rather than against 360 exactly, so -180..180
        loses its duplicate too.
        """
        start = self.ui.spinDirFrom.value()
        stop = self.ui.spinDirTo.value()
        step = self.ui.spinDirStep.value()
        if step <= 0 or stop < start:
            return [start]
        count = int(np.floor((stop - start) / step + 1e-9)) + 1
        values = [start + i * step for i in range(max(count, 1))]
        if len(values) > 1 and abs((values[-1] - values[0]) % 360.0) < 1e-9:
            values = values[:-1]
        return values

    def lid_z(self) -> float | None:
        """The lid position for the chosen mode, or ``None`` for no lid."""
        mode = self.ui.comboLid.currentIndex()
        if mode == LID_NONE:
            return None
        if mode == LID_SURFACE:
            return 0.0
        if mode == LID_BELOW:
            return self.ui.spinLidZ.value()
        return auto_lid_z(
            self._mesh.vertices,
            self._mesh.faces,
            is_xz_symmetric=self._mesh.is_xz_symmetric,
            omega_max=max(omega_from_period(t) for t in self.periods()),
            g=self.ui.spinG.value(),
        )

    def settings(self) -> SolveSettings:
        return SolveSettings(
            # Frequency-major, so ascending omega -- the reverse of the
            # ascending periods above (spec 09 section E).
            omegas=tuple(sorted(omega_from_period(t) for t in self.periods())),
            wave_directions=tuple(self.directions()),
            water_depth=np.inf if self.ui.chkInfiniteDepth.isChecked() else self.ui.spinDepth.value(),
            g=self.ui.spinG.value(),
            forward_speed=self.ui.spinSpeed.value(),
            lid_z=self.lid_z(),
        )

    def _taken(self):
        return [result.id for result in self._library.results()]

    def _depth_toggled(self, infinite: bool) -> None:
        self.ui.spinDepth.setEnabled(not infinite)
        self._refresh()

    def _refresh(self) -> None:
        periods = self.periods()
        directions = self.directions()

        self.ui.lblPeriodList.setText(derived(format_grid(periods), f"{len(periods)} frequencies"))
        self.ui.lblDirList.setText(
            derived(format_grid(directions, decimals=1), self._direction_note(directions))
        )

        mode = self.ui.comboLid.currentIndex()
        self.ui.spinLidZ.setEnabled(mode == LID_BELOW)
        self.ui.lblLidInfo.setText(self._lid_text(mode))

        panels = solved_panels(self._mesh)
        # A lid disables the reflection symmetry, so the mesh the solver
        # actually works with doubles (spec 04 section 2.1). Shown rather than
        # discovered afterwards: it is the difference between an informed
        # choice and a checkbox that sounds safe.
        lidded = mode != LID_NONE and self._mesh.is_xz_symmetric
        workers = self.ui.spinWorkers.value()
        effective = panels * 2 if lidded else panels

        self.ui.lblCostProblems.setText(f"<b>{len(periods) * (6 + len(directions))}</b>")
        self.ui.lblCostPanels.setText(
            derived(f"<b>{effective}</b>", "symmetry is off — a lid disables it" if lidded else "")
        )
        self.ui.lblCostMemory.setText(
            f"<b>{format_memory(effective)}</b> × {workers} workers = "
            f"<b>{format_memory_total(effective, workers)}</b>"
        )

        limit = shortest_reliable_period(self._mesh.vertices, self._mesh.faces)
        shortest = min(periods)
        if shortest < limit:
            self.ui.lblCostReliable.setText(
                f'<span style="color:{INCOMPLETE}"><b>{limit:.2f} s</b> — the grid starts at '
                f"{shortest:.2f} s, below it. Those frequencies will solve, and be wrong.</span>"
            )
        else:
            self.ui.lblCostReliable.setText(derived(f"<b>{limit:.2f} s</b>", f"shortest asked for {shortest:.2f} s"))

        self.ui.btnStop.setToolTip(f"Graceful — expect about one frequency, with {workers} in flight")

        _value, id_problem = chosen_id(self.ui.editId.text(), self._taken())
        self.ui.lblIdProblem.setText(
            f'<span style="color:{CONFLICT}">{escape(id_problem)}</span>' if id_problem else ""
        )
        self.ui.btnStart.setEnabled(not id_problem)

    def _direction_note(self, directions) -> str:
        """What the grid covers, and what fills in the rest."""
        count = f"{len(directions)}, direction of travel"
        if not self._mesh.is_xz_symmetric:
            return f"{count} — the hull is not symmetric here, so the whole circle is solved"
        if max(directions) <= 180.0 + 1e-9:
            return f"{count} — the other half is the mirror image and is filled in on delivery"
        return f"{count} — past 180 is the mirror of what is already solved, so this is redundant work"

    def _lid_text(self, mode: int) -> str:
        if mode == LID_NONE:
            return derived("no lid", "irregular frequencies are not removed")
        if mode == LID_SURFACE:
            return derived(
                "z = 0",
                "panels on the free surface are still experimental in Capytaine",
            )
        if mode == LID_BELOW:
            return derived(
                f"z = {self.ui.spinLidZ.value():g} m",
                "slightly below is more robust, and removes fewer irregular frequencies",
            )
        z = self.lid_z()
        if z is None:
            return (
                f'<span style="color:{CLEAN}">There are no irregular frequencies in this range '
                "and no lid is needed.</span>"
            )
        return derived(f"z = {z:.3f} m", "from the highest frequency on this screen")

    # -- running -----------------------------------------------------------

    def _start(self) -> None:
        self._settings = self.settings()
        self.ui.textLog.clear()
        self._fill_chips(self._settings.omegas)
        self._set_running(True)

        pool = PoolSolve(
            self._mesh.vertices,
            self._mesh.faces,
            is_xz_symmetric=self._mesh.is_xz_symmetric,
            application_point=self._library.application_point_in_diffraction_space(self._mesh.condition_id),
            settings=self._settings,
            workers=self.ui.spinWorkers.value(),
            omp_threads=self.ui.spinOmp.value(),
        )
        self._thread = SolveThread(pool, self)
        self._thread.progressed.connect(self._progressed)
        self._thread.completed.connect(self._completed)
        self._thread.failed.connect(self._crashed)
        self._thread.start()

    def _stop(self) -> None:
        if self._thread is not None:
            self._log("Stop: queued frequencies dropped; the running ones finish and are kept.")
            self._thread.stop()

    def _kill(self) -> None:
        if self._thread is not None:
            self._log(
                "Kill: terminating the workers. Frequencies in flight are lost; "
                "you will be asked whether to keep the rest."
            )
            self._thread.kill()

    def _set_running(self, running: bool) -> None:
        # Not simply `not running`: Start is also refused while the typed
        # result id collides, and finishing a run must not re-enable it.
        self.ui.btnStart.setEnabled(
            not running and not chosen_id(self.ui.editId.text(), self._taken())[1]
        )
        self.ui.btnStop.setEnabled(running)
        self.ui.btnKill.setEnabled(running)
        for group in (self.ui.groupPeriods, self.ui.groupDirections, self.ui.groupPhysical,
                      self.ui.groupLid, self.ui.groupParallel):
            group.setEnabled(not running)

    def _fill_chips(self, omegas) -> None:
        """One chip per frequency, in the order the user reads them.

        Ascending **period**, which is descending omega -- the reverse of the
        order they are solved in. Sorted for the display rather than left in
        solve order, because a progress list that appears to start at the end
        reads as a bug (spec 09 section E).
        """
        self.ui.listGrid.clear()
        self._chips = {}
        for omega in sorted(omegas, key=lambda w: -w):
            item = QListWidgetItem(f"{period_from_omega(omega):.2f} s")
            item.setData(Qt.ItemDataRole.UserRole, omega)
            self.ui.listGrid.addItem(item)
            self._chips[omega] = item

    def _progressed(self, outcome) -> None:
        done = len(outcome.solved)
        total = len(outcome.requested)
        self.ui.progressBar.setMaximum(total)
        self.ui.progressBar.setValue(done)

        for omega in outcome.solved:
            chip = self._chips.get(omega)
            if chip is not None:
                chip.setText(f"✓ {period_from_omega(omega):.2f} s")
        for omega in outcome.failed:
            chip = self._chips.get(omega)
            if chip is not None:
                chip.setText(f"✗ {period_from_omega(omega):.2f} s")

        # Estimated from completed frequencies, which are uniform in cost,
        # rather than from problems, which are not (spec 06 section 6.5.1).
        remaining = ""
        if done and done < total:
            per = outcome.elapsed / done
            remaining = f" · about {per * (total - done):.0f} s left"
        state = "stopping" if outcome.stopped else "solving"
        self.ui.lblProgress.setText(
            f"{done} of {total} frequencies · {outcome.elapsed:.0f} s elapsed{remaining} · {state}"
        )

    def _completed(self, outcome) -> None:
        self._set_running(False)
        for omega, message in sorted(outcome.failed.items()):
            self._log(f"FAILED at {period_from_omega(omega):.2f} s: {message}")

        if outcome.dataset is None:
            self._log("Nothing was solved; nothing stored.")
            self.ui.lblProgress.setText("Nothing solved.")
            return

        # A short grid is kept without asking, and only a **terminated** run is
        # questioned. Whether the data is worth keeping is not a question
        # anybody can answer from this screen -- it is answered by looking at
        # the curves in Inspect, which needs the result to exist first. And an
        # unwanted result is one click to delete, where a discarded one is
        # another solve. Kill is the exception because it is the emergency
        # handle: someone reaching for it usually wants out, not a shorter grid.
        if outcome.killed and not outcome.complete and not self._keep_partial(outcome):
            self._log("Discarded. The library is unchanged.")
            self.ui.lblProgress.setText("Discarded.")
            return

        settings = replace(self._settings, omegas=tuple(outcome.solved))
        result = self._library.store_result(
            self._mesh,
            outcome.dataset,
            settings,
            result_id=chosen_id(self.ui.editId.text(), self._taken())[0],
            # A field rather than a sentence in the label, which belongs to
            # whoever names this result (spec 09 section G).
            truncated=not outcome.complete,
        )
        self._log(f"Stored result {result.id} over {len(outcome.solved)} frequencies.")
        self.ui.lblProgress.setText(f"Stored <b>{escape(result.id)}</b>.")
        self.resultStored.emit(result.id)

    def _keep_partial(self, outcome) -> bool:
        """Ask, after a **terminated** run only.

        A run that stopped gracefully is kept without a question: every
        frequency it finished is complete over every degree of freedom and
        every wave direction, and whether the result is worth having is decided
        by looking at it in Inspect -- which it has to exist to allow. Deleting
        one is a click; re-solving a discarded one is minutes.

        Kill is different, and not because the numbers are: someone who reached
        for the emergency handle usually wanted out. So this asks, and the
        missing frequencies are named, because "keep 4 of 7" is not a decision
        anyone can make without knowing which four.
        """
        missing = ", ".join(f"{period_from_omega(w):.2f} s" for w in outcome.missing)
        box = QMessageBox(self)
        box.setWindowTitle("Keep what was solved?")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(
            f"The solve was terminated. {len(outcome.solved)} of {len(outcome.requested)} "
            "frequencies came back."
        )
        box.setInformativeText(
            f"Missing: {missing}.\n\nEach frequency that finished is complete over every degree of "
            "freedom and every wave direction, so keeping them stores a valid result over a shorter "
            "grid. Discarding leaves the library exactly as it was."
        )
        keep = box.addButton("Keep what was solved", QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton("Discard", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(discard)
        box.exec()
        return box.clickedButton() is keep

    def _crashed(self, trace: str) -> None:
        self._set_running(False)
        self._log(trace)
        self.ui.lblProgress.setText(f'<span style="color:{CONFLICT}">The solve failed. See the log.</span>')

    def _log(self, message: str) -> None:
        self.ui.textLog.appendPlainText(message)

    def closeEvent(self, event) -> None:
        """Refuse to close over a running solve, or kill it on request.

        Closing the window would drop the only handle on the worker processes,
        which is precisely the orphaned-worker failure spec 06 section 6.3
        calls the worst in the design.
        """
        if self._thread is not None and self._thread.isRunning():
            answer = QMessageBox.question(
                self,
                "A solve is running",
                "Killing the workers now loses the frequencies in flight. Close anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._thread.kill()
            self._thread.wait(10_000)
        event.accept()


def format_memory_total(panels: int, workers: int) -> str:
    """Peak memory across the pool.

    Its own function because the multiplication is the number that matters:
    four workers on a 5000-panel mesh need about 3.2 GB before anything else,
    and a per-worker figure alone lets a user pick sixteen and swap the machine
    to a halt (spec 06 section 6.5).
    """
    from pylot_bem.estimates import influence_matrix_bytes

    total = influence_matrix_bytes(panels) * workers / 1e6
    if total < 1:
        return "<1 MB"
    if total < 1000:
        return f"~{total:.0f} MB"
    return f"~{total / 1000:.1f} GB"
