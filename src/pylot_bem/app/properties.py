"""The property panes: one per kind of thing the tree can hold.

Each pane is a thin filler over a widget generated from a ``.ui`` file in
``guis/``. **Nothing here builds a layout**, on purpose: the arrangement is
meant to be fine-tuned in Qt Designer, and a pane that constructed its own
widgets would put that arrangement back into Python where it cannot be. The
code's contract with the designer file is the set of ``objectName`` values it
reads, and ``test_app_properties.py`` checks every one of them exists.

The panes are also where spec 09's two cross-cutting rules land:

- **derived fields are never editable** -- they are ``QLabel``, and there is no
  code path that writes one back;
- **every refusal states its reason** -- a disabled button carries the reason
  in the label beside it, not in a tooltip nobody opens.

Filling a pane reads from the library and never writes to it. The panes emit a
signal instead and let :mod:`pylot_bem.app.window` do the writing, so an action
that needs a confirmation dialog is not buried three widgets deep.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QListWidgetItem, QTableWidgetItem, QWidget

from pylot_bem.app.formatting import (
    INCOMPLETE,
    degrees_from_slope,
    derived,
    escape,
    format_depth,
    format_grid,
    format_point,
    format_range,
    period_from_omega,
    symmetry_reason,
)
from pylot_bem.app.forms.prop_condition_ui import Ui_PropCondition
from pylot_bem.app.forms.prop_library_ui import Ui_PropLibrary
from pylot_bem.app.forms.prop_mesh_ui import Ui_PropMesh
from pylot_bem.app.forms.prop_result_ui import Ui_PropResult
from pylot_bem.app.forms.prop_selection_ui import Ui_PropSelection
from pylot_bem.estimates import format_memory, shortest_reliable_period, solved_panels
from pylot_bem.mesh_pipeline import MeshPipelineError, submerged_summary

__all__ = [
    "ConditionPane",
    "LibraryPane",
    "MeshPane",
    "ResultPane",
    "SelectionPane",
]


class LibraryPane(QWidget):
    """The root of the tree: identity, base shape, probes, health.

    Signals:
        identityEdited: The three text fields, as typed.
        probesEdited: The probe table, as ``(P, 2)``.
        validateRequested: Run validation and show it.
    """

    identityEdited = Signal(str, str, str)
    probesEdited = Signal(object)
    validateRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ui = Ui_PropLibrary()
        self.ui.setupUi(self)

        self.ui.btnApplyIdentity.clicked.connect(self._apply_identity)
        self.ui.btnProbeApply.clicked.connect(self._apply_probes)
        self.ui.btnProbeAdd.clicked.connect(self._add_probe_row)
        self.ui.btnProbeRemove.clicked.connect(self._remove_probe_row)
        self.ui.btnProbeReset.clicked.connect(self._reset_probes)
        self.ui.btnValidate.clicked.connect(self.validateRequested)
        self._library = None

    def display(self, library) -> None:
        self._library = library
        info = library.info
        base = library.base_shape

        self.ui.editVesselName.setText(info.vessel_name)
        self.ui.editDescription.setText(info.description)
        self.ui.editOrigin.setText(info.origin_description)

        lo, hi = base.bounds
        self.ui.lblCounts.setText(f"{len(base.vertices)} vertices, {len(base.faces)} faces")
        self.ui.lblBounds.setText(
            derived(
                f"{hi[0] - lo[0]:.2f} × {hi[1] - lo[1]:.2f} × {hi[2] - lo[2]:.2f}",
                f"x {lo[0]:.2f}…{hi[0]:.2f}, y {lo[1]:.2f}…{hi[1]:.2f}, z {lo[2]:.2f}…{hi[2]:.2f}",
            )
        )
        self.ui.lblSymmetry.setText(
            derived(
                "yes" if base.is_xz_symmetric else "no",
                "declared at import — nothing can derive it",
            )
        )
        self._fill_probes(library.probe_xy)
        self.ui.lblProbeWarning.setText(
            f"Applying an edit recomputes the probe z of all {len(library.conditions())} conditions. "
            "You will be told how many change before it happens."
        )

    def show_findings(self, findings) -> None:
        """Summarise a validation run beside the button that started it."""
        if not findings:
            self.ui.lblHealth.setText("No findings.")
            return
        counts: dict[str, int] = {}
        for finding in findings:
            counts[str(finding.severity)] = counts.get(str(finding.severity), 0) + 1
        summary = ", ".join(f"{count} {name}" for name, count in sorted(counts.items()))
        self.ui.lblHealth.setText(f"<b>{escape(summary)}</b> — see the Validation tab.")

    # -- probe table -------------------------------------------------------

    def _fill_probes(self, probe_xy) -> None:
        table = self.ui.tableProbes
        table.setRowCount(len(probe_xy))
        for row, (x, y) in enumerate(probe_xy):
            table.setItem(row, 0, QTableWidgetItem(f"{x:.3f}"))
            table.setItem(row, 1, QTableWidgetItem(f"{y:.3f}"))

    def probe_table_values(self) -> list[list[float]]:
        """What the table currently holds.

        Raises:
            ValueError: If a cell is not a number. Surfaced rather than
                skipped: a probe silently dropped for a typo would change every
                condition's ranking with nothing to show why.
        """
        table = self.ui.tableProbes
        values = []
        for row in range(table.rowCount()):
            cells = []
            for column in (0, 1):
                item = table.item(row, column)
                text = "" if item is None else item.text().strip()
                try:
                    cells.append(float(text))
                except ValueError as exc:
                    axis = "xy"[column]
                    raise ValueError(f"probe {row + 1} has {axis} = {text!r}, which is not a number") from exc
            values.append(cells)
        return values

    def _add_probe_row(self) -> None:
        table = self.ui.tableProbes
        row = table.rowCount()
        table.insertRow(row)
        table.setItem(row, 0, QTableWidgetItem("0.000"))
        table.setItem(row, 1, QTableWidgetItem("0.000"))

    def _remove_probe_row(self) -> None:
        rows = sorted({index.row() for index in self.ui.tableProbes.selectedIndexes()}, reverse=True)
        for row in rows:
            self.ui.tableProbes.removeRow(row)

    def _reset_probes(self) -> None:
        if self._library is None:
            return
        from pylot_db.probes import default_probe_xy

        self._fill_probes(default_probe_xy(self._library.base_shape.vertices))

    def _apply_identity(self) -> None:
        self.identityEdited.emit(
            self.ui.editVesselName.text(),
            self.ui.editDescription.text(),
            self.ui.editOrigin.text(),
        )

    def _apply_probes(self) -> None:
        self.probesEdited.emit(self.probe_table_values())


class ConditionPane(QWidget):
    """One floating condition, and what can be done to it.

    Signals:
        labelEdited: The label as typed.
        createMeshRequested: Open the mesh dialog for this condition.
        removeRequested: Delete it, with whatever hangs off it.
    """

    labelEdited = Signal(str)
    createMeshRequested = Signal()
    removeRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ui = Ui_PropCondition()
        self.ui.setupUi(self)
        self.ui.btnApplyLabel.clicked.connect(lambda: self.labelEdited.emit(self.ui.editLabel.text()))
        self.ui.btnCreateMesh.clicked.connect(self.createMeshRequested)
        self.ui.btnRemoveCondition.clicked.connect(self.removeRequested)

    def display(self, library, condition) -> None:
        self.ui.editLabel.setText(condition.label)
        self.ui.lblId.setText(f"<b>{escape(condition.id)}</b>")

        self.ui.lblZOrigin.setText(
            derived(f"{condition.z_origin:.3f}", "the vessel origin above the waterplane, not the draft")
        )
        self.ui.lblHeel.setText(f"{degrees_from_slope(condition.heel):.3f}")
        self.ui.lblTrim.setText(f"{degrees_from_slope(condition.trim):.3f}")

        self.ui.lblApplicationPoint.setText(
            derived(format_point(condition.application_point), "vessel-local, from the submerged bounds")
        )
        symmetric, reason = symmetry_reason(library.base_shape.is_xz_symmetric, condition.heel)
        self.ui.lblSymmetry.setText(derived("yes" if symmetric else "<b>no</b>", reason))
        self.ui.lblProbeZ.setText(derived(format_grid(condition.probes[:, 2], decimals=3), "one per probe"))
        self.ui.lblSubmerged.setText(self._submerged_text(library, condition))

        meshes = library.meshes(condition.id)
        results = [r for r in library.results() if r.condition_id == condition.id]
        self.ui.lblRemoveHint.setText(
            f"Removing takes its {len(meshes)} mesh(es) and {len(results)} result(s) with it, "
            "and says so before it does."
        )

    @staticmethod
    def _submerged_text(library, condition) -> str:
        """The wetted measurements, or why there are none.

        A condition can be stored and later be un-meshable -- nothing checks
        the geometry again on open. Showing the refusal here is cheaper than
        letting it surface as a failed mesh build.
        """
        try:
            summary = submerged_summary(library.base_shape, condition.transform)
        except MeshPipelineError as exc:
            return f'<span style="color:#b04040">not measurable — {escape(str(exc).split(".")[0])}</span>'
        return derived(
            f"{summary.wetted_area:,.0f} m² wetted, {summary.waterline_length:.2f} m at the waterline",
            f"submerged bounds z {summary.lo[2]:.2f}…{summary.hi[2]:.2f} m — no volume: "
            "the cut hull is an open surface",
        )


class MeshPane(QWidget):
    """One calculation mesh: what it cost, and what has been solved on it.

    Signals:
        solveRequested: Open the solve dialog for this mesh.
        removeRequested: Delete it.
        resultActivated: A solution in the list was double-clicked; carries its id.
    """

    solveRequested = Signal()
    removeRequested = Signal()
    resultActivated = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ui = Ui_PropMesh()
        self.ui.setupUi(self)
        self.ui.btnSolve.clicked.connect(self.solveRequested)
        self.ui.btnRemoveMesh.clicked.connect(self.removeRequested)
        self.ui.listSolutions.itemDoubleClicked.connect(
            lambda item: self.resultActivated.emit(item.data(Qt.ItemDataRole.UserRole))
        )

    def display(self, library, mesh) -> None:
        self.ui.lblId.setText(f"<b>{escape(mesh.id)}</b>")
        self.ui.lblSettings.setText(derived(f"pct {mesh.pct:g} %, {mesh.iterations} iterations", "lower is finer"))
        self.ui.lblCondition.setText(f"<b>{escape(mesh.condition_id)}</b>")

        panels = solved_panels(mesh)
        half = "half vessel — the solver mirrors it" if mesh.is_xz_symmetric else "full vessel"
        self.ui.lblFaces.setText(derived(f"{len(mesh.faces)}", half))
        self.ui.lblPanels.setText(derived(f"{panels}", "what the solver actually works with"))

        symmetric, reason = symmetry_reason(
            library.base_shape.is_xz_symmetric, library.condition(mesh.condition_id).heel
        )
        self.ui.lblSymmetry.setText(derived("yes" if symmetric else "no", reason))
        self.ui.lblReliable.setText(
            derived(
                f"{shortest_reliable_period(mesh.vertices, mesh.faces):.2f} s period",
                "shorter waves solve, and are wrong",
            )
        )
        self.ui.lblMemory.setText(derived(format_memory(panels), "per worker"))

        self.ui.listSolutions.clear()
        results = [r for r in library.results() if r.mesh_id == mesh.id]
        for result in results:
            periods = sorted(period_from_omega(w) for w in result.omegas)
            item = QListWidgetItem(f"{result.id}  —  {format_range(periods)} s, {len(periods)} frequencies")
            item.setData(Qt.ItemDataRole.UserRole, result.id)
            self.ui.listSolutions.addItem(item)
        if not results:
            self.ui.listSolutions.addItem(QListWidgetItem("Nothing solved on this mesh yet."))

        self.ui.lblConflict.setText(self._conflict_text(library, mesh))

    @staticmethod
    def _conflict_text(library, mesh) -> str:
        ours = {r.id for r in library.results() if r.mesh_id == mesh.id}
        for view in library.databases():
            conflicts = view.conflicts
            if conflicts and ours.intersection(view.result_ids):
                omegas = ", ".join(f"{period_from_omega(c.omega):.2f} s" for c in conflicts)
                return (
                    f'<span style="color:#b04040">Results on this mesh overlap at {escape(omegas)}, '
                    f"which is why condition <b>{escape(view.key.condition_id)}</b> produces no "
                    "database. Compare them in Inspect, then delete the loser.</span>"
                )
        return ""


class ResultPane(QWidget):
    """One solver run, exactly as it was solved.

    Signals:
        labelEdited: The label as typed. A result's only mutable field.
        inspectRequested: Plot it.
        deleteFrequenciesRequested: Open the frequency-deletion dialog.
        removeRequested: Delete the whole result.
    """

    labelEdited = Signal(str)
    inspectRequested = Signal()
    deleteFrequenciesRequested = Signal()
    removeRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ui = Ui_PropResult()
        self.ui.setupUi(self)
        self.ui.btnApplyLabel.clicked.connect(lambda: self.labelEdited.emit(self.ui.editLabel.text()))
        self.ui.btnInspect.clicked.connect(self.inspectRequested)
        self.ui.btnDeleteFrequencies.clicked.connect(self.deleteFrequenciesRequested)
        self.ui.btnRemoveResult.clicked.connect(self.removeRequested)

    def display(self, library, result) -> None:
        periods = sorted(period_from_omega(w) for w in result.omegas)
        self.ui.editLabel.setText(result.label)
        self.ui.lblId.setText(f"<b>{escape(result.id)}</b>")
        self.ui.lblPeriods.setText(derived(format_range(periods), f"{len(periods)} frequencies"))
        self.ui.lblDirections.setText(
            derived(
                format_range(result.wave_directions, decimals=1),
                f"{len(result.wave_directions)}, direction of travel",
            )
        )
        self.ui.lblPhysical.setText(
            f"depth {format_depth(result.water_depth)} · speed {result.forward_speed:g} m/s · g {result.g:g}"
        )
        self.ui.lblLid.setText(self._lid_text(result))

        mesh = library.mesh(result.mesh_id)
        self.ui.lblMesh.setText(derived(f"<b>{escape(mesh.id)}</b>", f"pct {mesh.pct:g}, {len(mesh.faces)} faces"))
        self.ui.lblSolver.setText(f"{escape(result.solver_name)} {escape(result.solver_version)}")

        carries = [
            name
            for name, present in (("radiation", result.has_radiation), ("diffraction", result.has_diffraction))
            if present
        ]
        self.ui.lblCoverage.setText(derived(" and ".join(carries) or "nothing", "what assembly can take from it"))

        # Truncation is a field now, not a sentence in the label: the label
        # is the human name and cannot be both (spec 09 section G).
        self.ui.lblNote.setText(
            f'<span style="color:{INCOMPLETE}">Truncated — the run was cut short, so this covers fewer frequencies than were asked for. A shorter grid is still a complete result.</span>'
            if result.truncated
            else ""
        )
        self.ui.lblDatabase.setText(self._database_text(library, result))

    @staticmethod
    def _lid_text(result) -> str:
        if result.lid_mode is None:
            return derived("none", "no irregular-frequency removal")
        where = "at the free surface" if result.lid_mode == "free_surface" else f"at z = {result.lid_z:g} m"
        return derived(f"{result.lid_mode} ({where})", "symmetry was not used — a lid disables it")

    @staticmethod
    def _database_text(library, result) -> str:
        for view in library.databases():
            if result.id in view.result_ids:
                if view.conflicts:
                    state = "in conflict — no database until it is resolved"
                elif view.incomplete:
                    state = "incomplete"
                else:
                    state = "usable"
                key = view.key
                return derived(
                    f"<b>{escape(key.condition_id)}</b> at depth {format_depth(key.water_depth)}, "
                    f"speed {key.forward_speed:g} m/s",
                    state,
                )
        return "none"


class SelectionPane(QWidget):
    """Several results at once — the pane that exists to make comparison easy.

    Selecting more than one result is how a conflict gets resolved
    (pylot-db's spec 02 section 3.2), so the multi-selection is a first-class state rather
    than a fallback that shows nothing.

    Signals:
        compareRequested: Send the selection to the Inspect tab.
        mergeRequested: Resolve their overlap by trimming.
        removeRequested: Delete all of them.
    """

    compareRequested = Signal()
    mergeRequested = Signal()
    removeRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ui = Ui_PropSelection()
        self.ui.setupUi(self)
        self.ui.btnCompare.clicked.connect(self.compareRequested)
        self.ui.btnMerge.clicked.connect(self.mergeRequested)
        self.ui.btnRemoveSelected.clicked.connect(self.removeRequested)

    def display(self, library, results) -> None:
        self.ui.lblHeading.setText(f"<b>{len(results)} results selected</b>")
        self.ui.listSelected.clear()
        for result in results:
            periods = sorted(period_from_omega(w) for w in result.omegas)
            mesh = library.mesh(result.mesh_id)
            self.ui.listSelected.addItem(
                f"{result.id}  —  {format_range(periods)} s, pct {mesh.pct:g}"
            )

        keys = {(r.condition_id, r.forward_speed, r.water_depth) for r in results}
        self.ui.lblTogether.setText(
            derived(
                f"{len(keys)} database{'' if len(keys) == 1 else 's'} touched",
                ", ".join(sorted({r.condition_id for r in results})),
            )
        )
        self.ui.lblNote.setText(
            "Same database, so these are directly comparable — and where they overlap in "
            "frequency, this is the conflict to resolve."
            if len(keys) == 1
            else "Different databases. They can still be plotted together, but they describe "
            "different physical situations, so a difference between them is not something to fix."
        )
        # Merging only means anything within one database: elsewhere neither
        # result supersedes the other and there is nothing to resolve.
        self.ui.btnMerge.setEnabled(len(keys) == 1 and len(results) > 1)

    def show_nothing(self) -> None:
        self.ui.lblHeading.setText("<b>Nothing selected</b>")
        self.ui.listSelected.clear()
        self.ui.lblTogether.setText("—")
        self.ui.lblNote.setText("Open a library, or pick something in the tree.")
        self.ui.btnCompare.setEnabled(False)
        self.ui.btnMerge.setEnabled(False)
        self.ui.btnRemoveSelected.setEnabled(False)
