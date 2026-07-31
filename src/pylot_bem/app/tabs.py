"""The five tabs below the 3D view.

Unlike the property panes these are built in code and not from ``.ui`` files:
four of the five are a table with a caption, whose only design decision is the
column list, and that list lives better beside the code that fills it than in
XML. The panes are the screens worth fine-tuning; these are the screens worth
reading.

What they are for, in one line each:

============  ==============================================================
Results       Every result in the library, always. **Never filtered by the
              tree** (spec 06 section 4) -- the tree picks what to act on,
              this says what exists.
Databases     Assembly keys and their state. Conflict and incomplete are
              first-class states shown here, not errors raised at use time.
Inspect       Any quantity against frequency or period, for one result or
              several overlaid. Overlaying is how a conflict gets resolved.
Match         Spec 05 with no vessel and no DAVE. Ranks every condition and
              picks none.
Validation    The structured findings. With no export, this is the only
              diagnostic a broken library has.
============  ==============================================================
"""

from typing import ClassVar

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from pylot_db.hyddb import DOF_ORDER, KG_TO_MT, N_TO_KN, STORED_RHO
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pylot_bem.app.formatting import (
    CLEAN,
    CONFLICT,
    INCOMPLETE,
    degrees_from_slope,
    escape,
    format_depth,
    format_range,
    period_from_omega,
    slope_from_degrees,
)

__all__ = [
    "DatabasesTab",
    "InspectTab",
    "MatchTab",
    "ResultsTab",
    "ValidationTab",
]

# What can be plotted. The only three quantities stored (spec 04 section 3),
# with the factor that takes each from the solver's SI output to mafredo's
# delivered units -- the same factors :func:`pylot_db.hyddb.to_hyddb1` applies,
# imported rather than repeated so a plot and a delivered database cannot
# disagree about what a number means.
QUANTITIES = {
    "Added mass": ("added_mass", KG_TO_MT, "mt"),
    "Radiation damping": ("radiation_damping", N_TO_KN, "kN·s/m"),
    "Excitation force": ("excitation_force", N_TO_KN, "kN/m"),
}


def _table(columns: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    table.setAlternatingRowColors(True)
    return table


def _caption(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    return label


def _fill(table: QTableWidget, rows: list[list[str]], *, colours: list[str | None] | None = None) -> None:
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            item = QTableWidgetItem(value)
            if colours is not None and colours[r] is not None:
                item.setForeground(QColor(colours[r]))
            table.setItem(r, c, item)


class ResultsTab(QWidget):
    """Every result, with what was actually solved.

    The column list *is* spec 06 section 4's requirement that "users must be
    able to see what was actually solved". There is no density column, and its
    absence is the point: results are stored per unit density and one of them
    serves every density (spec 04 section 4).
    """

    COLUMNS: ClassVar[list[str]] = [
        "Result", "Label", "Mesh", "pct", "Condition", "Periods [s]", "n",
        "Directions [deg]", "n", "Depth", "Speed [m/s]", "Lid", "Carries",
        "Truncated", "Solver", "Solved",
    ]  # fmt: skip

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.table = _table(self.COLUMNS)
        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addWidget(
            _caption(
                "Every result in the library, always — deliberately not filtered by the tree "
                "selection (spec 06 §4), because comparing results across meshes is how a "
                "resolution is chosen. No density column: results are stored per unit density."
            )
        )

    def display(self, library) -> None:
        rows = []
        for result in library.results():
            mesh = library.mesh(result.mesh_id)
            periods = sorted(period_from_omega(w) for w in result.omegas)
            carries = ", ".join(
                name
                for name, present in (("rad", result.has_radiation), ("diff", result.has_diffraction))
                if present
            )
            rows.append(
                [
                    result.id,
                    result.label,
                    mesh.id,
                    f"{mesh.pct:g}",
                    result.condition_id,
                    format_range(periods),
                    str(len(periods)),
                    format_range(result.wave_directions, decimals=1),
                    str(len(result.wave_directions)),
                    format_depth(result.water_depth),
                    f"{result.forward_speed:g}",
                    result.lid_mode or "none",
                    carries or "nothing",
                    "yes" if result.truncated else "",
                    f"{result.solver_name} {result.solver_version}".strip(),
                    result.created_at[:10],
                ]
            )
        _fill(self.table, rows)


class DatabasesTab(QWidget):
    """Assembly keys, and whether each one can produce a database.

    Signals:
        inspectRequested: Result ids to overlay -- the jump from a conflict
            straight to the comparison that resolves it (spec 09 section H).
    """

    inspectRequested = Signal(list)

    COLUMNS: ClassVar[list[str]] = ["Condition", "Depth", "Speed [m/s]", "Frequencies", "Contributing results", "State"]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.table = _table(self.COLUMNS)
        self.note = _caption("")
        self.button = QPushButton("Compare the contributors in Inspect…")
        self.button.setEnabled(False)
        self.button.clicked.connect(self._compare)

        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        row = QHBoxLayout()
        row.addWidget(self.button)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addWidget(self.note)
        layout.addWidget(
            _caption(
                "Keyed on condition × depth × forward speed. Not density — one database serves "
                "every density. A key in conflict produces no database until it is resolved, and "
                "nothing resolves it for you."
            )
        )

        self.table.itemSelectionChanged.connect(self._selected)
        self._views: list = []

    def display(self, library) -> None:
        self._views = library.databases()
        rows, colours = [], []
        for view in self._views:
            if view.conflicts:
                state, colour = f"conflict at {len(view.conflicts)} frequencies", CONFLICT
            elif view.incomplete:
                state, colour = f"incomplete at {len(view.incomplete)} frequencies", INCOMPLETE
            else:
                state, colour = "usable", CLEAN
            rows.append(
                [
                    view.key.condition_id,
                    format_depth(view.key.water_depth),
                    f"{view.key.forward_speed:g}",
                    str(len(view.coverage)),
                    ", ".join(view.result_ids),
                    state,
                ]
            )
            colours.append(colour)
        _fill(self.table, rows, colours=colours)
        self._selected()

    def _selected(self) -> None:
        view = self.current_view()
        self.button.setEnabled(view is not None and len(view.result_ids) > 1)
        self.note.setText("" if view is None else self._describe(view))

    def current_view(self):
        rows = {index.row() for index in self.table.selectedIndexes()}
        if len(rows) != 1:
            return None
        row = rows.pop()
        return self._views[row] if row < len(self._views) else None

    @staticmethod
    def _describe(view) -> str:
        if view.conflicts:
            where = ", ".join(f"{period_from_omega(c.omega):.2f} s" for c in view.conflicts)
            return (
                f'<span style="color:{CONFLICT}"><b>{escape(view.key.condition_id)} is in conflict and '
                f"produces no database until it is resolved.</b></span><br>Two results claim the same "
                f"quantity at {escape(where)}. Compare them, then delete the loser whole or by frequency."
            )
        if view.incomplete:
            where = ", ".join(
                f"{period_from_omega(c.omega):.2f} s ({c.describe().split(': ', 1)[-1]})"
                for c in view.incomplete
            )
            return (
                f'<span style="color:{INCOMPLETE}"><b>Incomplete.</b></span> Missing at {escape(where)}. '
                "Incomplete is a state, not an error — solve the gap when you need it."
            )
        return f'<span style="color:{CLEAN}">Usable at every frequency it covers.</span>'

    def _compare(self) -> None:
        view = self.current_view()
        if view is not None:
            self.inspectRequested.emit(list(view.result_ids))


class InspectTab(QWidget):
    """Plot a quantity for one result or several overlaid.

    Works on **results**, not only on assembled databases (spec 09 section I).
    That is what makes a conflict resolvable: two competing runs have to be on
    the same axes before either can be deleted.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._library = None
        self._result_ids: list[str] = []

        self.quantity = QComboBox()
        self.quantity.addItems(list(QUANTITIES))
        self.influenced = QComboBox()
        self.influenced.addItems(list(DOF_ORDER))
        self.influenced.setCurrentIndex(2)
        self.radiating = QComboBox()
        self.radiating.addItems(list(DOF_ORDER))
        self.radiating.setCurrentIndex(2)
        self.direction = QComboBox()
        self.x_axis = QComboBox()
        self.x_axis.addItems(["Period [s]", "Frequency [rad/s]"])
        self.phase = QCheckBox("Phase instead of amplitude")
        self.rho = QDoubleSpinBox()
        self.rho.setDecimals(4)
        self.rho.setRange(0.0001, 100.0)
        self.rho.setSingleStep(0.001)
        self.rho.setValue(1.025)

        controls = QFormLayout()
        controls.addRow("Quantity", self.quantity)
        controls.addRow("Influenced DOF", self.influenced)
        controls.addRow("Radiating DOF", self.radiating)
        controls.addRow("Wave direction [deg]", self.direction)
        controls.addRow("X axis", self.x_axis)
        controls.addRow("Density [t/m³]", self.rho)
        controls.addRow("", self.phase)

        self.figure = Figure(figsize=(6, 3), layout="constrained")
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.heading = _caption("Select one or more results in the tree.")

        body = QHBoxLayout()
        body.addLayout(controls, 0)
        body.addWidget(self.canvas, 1)

        layout = QVBoxLayout(self)
        layout.addWidget(self.heading)
        layout.addLayout(body)
        layout.addWidget(
            _caption(
                "Density scales every plotted amplitude and never the phase — that is what makes "
                "one stored result serve every density. Two results at different densities do not exist."
            )
        )

        for widget in (self.quantity, self.influenced, self.radiating, self.direction, self.x_axis):
            widget.currentIndexChanged.connect(self.replot)
        self.rho.valueChanged.connect(self.replot)
        self.phase.toggled.connect(self.replot)

    def show_results(self, library, result_ids: list[str]) -> None:
        self._library = library
        self._result_ids = list(result_ids)
        self._fill_directions()
        self.replot()

    def _fill_directions(self) -> None:
        """Offer the directions the selected results actually have in common."""
        shared = None
        for result_id in self._result_ids:
            directions = set(np.round(self._library.result(result_id).wave_directions, 6))
            shared = directions if shared is None else shared & directions
        current = self.direction.currentText()
        self.direction.blockSignals(True)
        self.direction.clear()
        for value in sorted(shared or []):
            self.direction.addItem(f"{value:g}")
        index = self.direction.findText(current)
        self.direction.setCurrentIndex(max(index, 0))
        self.direction.blockSignals(False)

    def replot(self) -> None:
        self.figure.clear()
        axes = self.figure.add_subplot(111)

        name, factor, unit = QUANTITIES[self.quantity.currentText()]
        excitation = name == "excitation_force"
        self.radiating.setEnabled(not excitation)
        self.direction.setEnabled(excitation)
        self.phase.setEnabled(excitation)

        if not self._result_ids or self._library is None:
            axes.set_title("Nothing selected")
            self.canvas.draw_idle()
            return

        plotted = 0
        for result_id in self._result_ids:
            try:
                x, y = self._series(result_id, name, factor, excitation)
            except (KeyError, ValueError) as exc:
                self.heading.setText(f'<span style="color:{INCOMPLETE}">{escape(str(exc))}</span>')
                continue
            axes.plot(x, y, marker="o", markersize=3, label=result_id)
            plotted += 1

        axes.set_xlabel(self.x_axis.currentText())
        showing_phase = excitation and self.phase.isChecked()
        axes.set_ylabel("phase [rad]" if showing_phase else f"{self.quantity.currentText()} [{unit}]")
        axes.grid(True, alpha=0.3)
        if plotted:
            axes.legend(fontsize="small")
            self.heading.setText(
                f"{plotted} result(s) overlaid at {self.rho.value():g} t/m³. "
                "Where two curves cover the same frequency, that is the conflict to resolve."
                if plotted > 1
                else f"{self._result_ids[0]} at {self.rho.value():g} t/m³."
            )
        self.canvas.draw_idle()

    def _series(self, result_id: str, name: str, factor: float, excitation: bool):
        dataset = self._library.result_dataset(result_id)
        if name not in dataset.data_vars:
            raise KeyError(f"{result_id} carries no {name}")

        omega = np.asarray(dataset["omega"].values, dtype=float)
        array = dataset[name]

        if excitation:
            wanted = float(self.direction.currentText() or 0.0)
            # The dataset holds radians, as Capytaine emits them; the control
            # is in degrees, as everything a user reads is (spec 04 section 7.4).
            #
            # Two selections, not one: `method="nearest"` applies to every
            # dimension in the call, and a nearest-match on the string-valued
            # dof dimension is an error.
            selected = array.sel(influenced_dof=DOF_ORDER[self.influenced.currentIndex()])
            values = selected.sel(wave_direction=np.radians(wanted), method="nearest").values
            if self.phase.isChecked():
                y = np.angle(values)
            else:
                y = np.abs(values) * factor * (self.rho.value() / STORED_RHO)
        else:
            values = array.sel(
                influenced_dof=DOF_ORDER[self.influenced.currentIndex()],
                radiating_dof=DOF_ORDER[self.radiating.currentIndex()],
            ).values
            y = np.real(values) * factor * (self.rho.value() / STORED_RHO)

        x = omega if self.x_axis.currentIndex() == 1 else np.array([period_from_omega(w) for w in omega])
        order = np.argsort(x)
        return x[order], np.asarray(y, dtype=float)[order]


class MatchTab(QWidget):
    """Rank every condition against a trial floating condition.

    Spec 09 section J: this **does not pick a winner**. It lists all of them
    ascending by RMS probe error, unusable ones included with the reason, and
    the user chooses. There is no threshold anywhere in the application.
    """

    COLUMNS: ClassVar[list[str]] = ["Condition", "RMS error [m]", "Max error [m]", "Worst probe", "Usable"]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._library = None

        self.z_origin = QDoubleSpinBox()
        self.z_origin.setRange(-1000.0, 1000.0)
        self.z_origin.setDecimals(3)
        self.z_origin.setValue(-5.0)
        self.heel = QDoubleSpinBox()
        self.heel.setRange(-89.0, 89.0)
        self.heel.setDecimals(3)
        self.trim = QDoubleSpinBox()
        self.trim.setRange(-89.0, 89.0)
        self.trim.setDecimals(3)

        self.infinite_depth = QCheckBox("infinite")
        self.infinite_depth.setChecked(True)
        self.depth = QDoubleSpinBox()
        self.depth.setRange(0.1, 100000.0)
        self.depth.setValue(50.0)
        self.depth.setEnabled(False)
        self.infinite_depth.toggled.connect(lambda on: self.depth.setEnabled(not on))
        self.speed = QDoubleSpinBox()
        self.speed.setRange(0.0, 100.0)
        self.speed.setDecimals(2)
        self.rho = QDoubleSpinBox()
        self.rho.setDecimals(4)
        self.rho.setRange(0.0001, 100.0)
        self.rho.setValue(1.025)

        trial = QFormLayout()
        trial.addRow("z_origin [m]", self.z_origin)
        trial.addRow("Heel [deg]", self.heel)
        trial.addRow("Trim [deg]", self.trim)

        depth_row = QHBoxLayout()
        depth_row.addWidget(self.infinite_depth)
        depth_row.addWidget(self.depth)
        filters = QFormLayout()
        filters.addRow("Depth [m]", depth_row)
        filters.addRow("Speed [m/s]", self.speed)

        delivery = QFormLayout()
        delivery.addRow("Density [t/m³]", self.rho)

        columns = QHBoxLayout()
        for title, form, note in (
            ("Trial condition", trial, "Not the naval draft — z_origin is the vessel origin above the waterplane."),
            ("Hard filters — exclude, never score", filters, "A different depth is not a worse match; it is an invalid one."),
            ("Delivery — scales, excludes nothing", delivery, "One library serves every density. This changes no ranking."),
        ):
            box = QVBoxLayout()
            heading = QLabel(f"<b>{title}</b>")
            box.addWidget(heading)
            box.addLayout(form)
            box.addWidget(_caption(note))
            box.addStretch(1)
            columns.addLayout(box)

        self.table = _table(self.COLUMNS)
        self.probes = _caption("")

        layout = QVBoxLayout(self)
        layout.addLayout(columns)
        layout.addWidget(self.table)
        layout.addWidget(self.probes)
        layout.addWidget(
            _caption(
                "All conditions, ascending by RMS probe error. No threshold and no “best match” "
                "label — the ranking is complete and the choice is yours."
            )
        )

        for widget in (self.z_origin, self.heel, self.trim, self.depth, self.speed):
            widget.valueChanged.connect(self.rank)
        self.infinite_depth.toggled.connect(self.rank)
        self.table.itemSelectionChanged.connect(self._show_probes)
        self._ranking = None

    def display(self, library) -> None:
        self._library = library
        self.rank()

    def rank(self) -> None:
        if self._library is None:
            return
        self._ranking = self._library.select(
            z_origin=self.z_origin.value(),
            # Degrees at the boundary, slopes everywhere inside.
            heel=slope_from_degrees(self.heel.value()),
            trim=slope_from_degrees(self.trim.value()),
            water_depth=np.inf if self.infinite_depth.isChecked() else self.depth.value(),
            forward_speed=self.speed.value(),
        )
        rows, colours = [], []
        for candidate in self._ranking.candidates:
            rows.append(
                [
                    candidate.condition.id,
                    f"{candidate.rms_error:.4f}",
                    f"{candidate.max_error:.4f}",
                    str(candidate.worst_probe),
                    "yes" if candidate.usable else f"no — {candidate.reason}",
                ]
            )
            colours.append(CLEAN if candidate.usable else CONFLICT)
        _fill(self.table, rows, colours=colours)
        if not self._ranking.candidates:
            self.probes.setText(
                f'<span style="color:{INCOMPLETE}">{escape(self._ranking.reason or "nothing matched")}</span>'
            )

    def _show_probes(self) -> None:
        rows = {index.row() for index in self.table.selectedIndexes()}
        if self._ranking is None or len(rows) != 1:
            return
        row = rows.pop()
        if row >= len(self._ranking.candidates):
            return
        candidate = self._ranking.candidates[row]
        errors = ", ".join(f"{value:+.4f}" for value in candidate.probe_errors)
        self.probes.setText(
            f"Signed probe errors for <b>{escape(candidate.condition.id)}</b> [m]: {escape(errors)}. "
            "The sign says which way the mismatch runs — a probe above the water surface is positive."
        )


class ValidationTab(QWidget):
    """The structured findings, grouped by severity.

    Signals:
        ran: The findings, so the library pane can summarise them beside its
            own Validate button without running the check twice.
    """

    ran = Signal(list)

    COLUMNS: ClassVar[list[str]] = ["Severity", "Entity", "Id", "Finding"]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._library = None
        self.button = QPushButton("Run validation")
        self.button.clicked.connect(self.run)
        self.table = _table(self.COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.summary = _caption("Not run yet.")

        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(self.button)
        row.addWidget(self.summary, 1)
        layout.addLayout(row)
        layout.addWidget(self.table)
        layout.addWidget(
            _caption(
                "Storage is one SQLite file, so this is the only diagnostic a broken library has. "
                "A corrupted library is displayed here, not crashed on."
            )
        )

    def display(self, library) -> None:
        self._library = library
        self.table.setRowCount(0)
        self.summary.setText("Not run yet.")

    def run(self) -> list:
        """Validate, show the findings, and report what could not be checked.

        A validation that itself raises is the one case that must not take the
        application down with it: a deliberately corrupted library is the input
        this screen exists for (spec 06 section 7).
        """
        if self._library is None:
            return []
        try:
            findings = self._library.validate()
        except Exception as exc:
            self.table.setRowCount(0)
            self.summary.setText(
                f'<span style="color:{CONFLICT}">Validation could not complete: '
                f"{escape(f'{type(exc).__name__}: {exc}')}</span>"
            )
            return []

        order = {"error": 0, "warning": 1}
        findings = sorted(findings, key=lambda f: (order.get(str(f.severity), 9), f.entity, f.entity_id))
        _fill(
            self.table,
            [[str(f.severity), f.entity, f.entity_id, f.message] for f in findings],
            colours=[CONFLICT if str(f.severity) == "error" else INCOMPLETE for f in findings],
        )
        counts: dict[str, int] = {}
        for finding in findings:
            counts[str(finding.severity)] = counts.get(str(finding.severity), 0) + 1
        self.summary.setText(
            "No findings — the library is consistent."
            if not findings
            else "<b>" + escape(", ".join(f"{n} {name}" for name, n in sorted(counts.items()))) + "</b>"
        )
        self.ran.emit(findings)
        return findings
