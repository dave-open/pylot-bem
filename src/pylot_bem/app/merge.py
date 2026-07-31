"""Resolving an overlap between results, by trimming rather than combining.

Its own module because it is the one screen that *simulates* the library
before touching it, and that is more code than a filler.

**Nothing is recomputed and no result is created.** One of the selection is
nominated the *primary* and keeps everything it has; the others keep only the
frequencies it does not cover. The overlap goes away, the key assembles, and
every frequency goes on pointing at the mesh, lid and date it was actually
solved with.

That last point is why merging does not mean *combining*. A
:class:`~pylot_db.entities.Result` carries one ``mesh_id``, one lid and one
date, so a single result built from several would have to claim one of them for
frequencies that came from the others -- and the usual reason two results exist
is that they were solved on **different meshes**, which is exactly the
distinction that would be lost.

What this screen does not do is pick the winner. That is the decision spec 02
section 3.2 reserves for the user; this exists to inform it, by showing what
each result would keep, what it would lose, and -- simulated, not promised --
what the database becomes.
"""

from dataclasses import replace

import numpy as np
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView, QDialog, QDialogButtonBox, QHeaderView, QTableWidgetItem, QWidget

from pylot_bem.app.dialogs import wire_button_box
from pylot_bem.app.formatting import CLEAN, CONFLICT, INCOMPLETE, escape, format_grid, period_from_omega
from pylot_bem.app.forms.dlg_merge_ui import Ui_DlgMerge
from pylot_db.assembly import OMEGA_TOLERANCE, coverage_of
from pylot_db.storage import combination_differences

__all__ = ["MergeDialog"]


def _covers(omegas, omega) -> bool:
    """Whether ``omega`` is already in ``omegas``, within the assembly tolerance."""
    return any(abs(float(omega) - float(other)) <= OMEGA_TOLERANCE for other in omegas)


class MergeDialog(QDialog):
    """Fold several results into one, or trim their overlap where it cannot.

    Two outcomes, and **the results decide which**, not a setting:

    - they agree on the mesh and every physical setting, so folding them into
      one loses nothing and the originals are replaced -- *combine*;
    - they differ somewhere, so a single result could not record both, and only
      the contested frequencies are given up -- *trim*.

    Whether combining throws information away is a fact about the results, not
    a preference, so offering it as a choice would be offering to be wrong.
    """

    def __init__(self, library, results, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ui = Ui_DlgMerge()
        self.ui.setupUi(self)
        wire_button_box(self)

        self._library = library
        self._results = list(results)
        self._problem = self._check()
        # Asked of storage, which is what will enforce it. A dialog with its
        # own copy of the rule could offer something the library then refuses.
        self._differences = [] if self._problem else combination_differences(self._results)
        self.combining = not self._problem and not self._differences

        for result in self._results:
            self.ui.comboPrimary.addItem(self._name(result), result.id)
        self.ui.comboPrimary.currentIndexChanged.connect(self._refresh)

        table = self.ui.tableEffect
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._refresh()

    @staticmethod
    def _name(result) -> str:
        return f"{result.label} ({result.id})" if result.label else result.id

    def _check(self) -> str:
        """Why these results cannot be merged, or blank.

        Two results only contest anything if they feed the **same** database.
        Different conditions, depths or forward speeds are different physical
        situations: neither supersedes the other and there is nothing to
        resolve, so this refuses rather than quietly trimming real data.
        """
        if len(self._results) < 2:
            return "Select at least two results to merge."
        if len({self._key_of(r) for r in self._results}) > 1:
            return (
                "These results feed different databases — different conditions, depths or "
                "forward speeds. They describe different physical situations, so neither "
                "supersedes the other and there is nothing to resolve."
            )
        return ""

    @staticmethod
    def _key_of(result) -> tuple:
        return (result.condition_id, result.forward_speed, result.water_depth)

    # -- the plan ----------------------------------------------------------

    def primary_id(self) -> str:
        return self.ui.comboPrimary.currentData()

    def plan(self) -> dict[str, list[float]]:
        """``{result_id: omegas to remove}``, for everything but the primary.

        Empty when combining: nothing is trimmed then, the originals are
        replaced whole.
        """
        if self._problem or self.combining:
            return {}
        primary = next(r for r in self._results if r.id == self.primary_id())
        covered = [float(w) for w in primary.omegas]

        dropping: dict[str, list[float]] = {}
        for result in self._results:
            if result.id == primary.id:
                continue
            contested = [
                float(w)
                for w in result.omegas
                if any(abs(float(w) - c) <= OMEGA_TOLERANCE for c in covered)
            ]
            if contested:
                dropping[result.id] = contested
        return dropping

    def _survivors(self, dropping) -> list:
        """The library's results for this key, as they would be afterwards.

        Hypothetical :class:`~pylot_db.entities.Result` objects handed to
        :func:`~pylot_db.assembly.coverage_of`, which is why that function takes
        results rather than reading a library: the outcome is *computed* by the
        same rule that will judge it afterwards, not predicted by a second one.
        """
        survivors = []
        for result in self._results:
            gone = dropping.get(result.id, [])
            kept = np.array(
                [w for w in result.omegas if not any(abs(float(w) - g) <= OMEGA_TOLERANCE for g in gone)],
                dtype=float,
            )
            if kept.size:
                survivors.append(replace(result, omegas=kept))

        # Results on the same key that were not selected still contribute, and
        # can still be in conflict afterwards. Leaving them out would let this
        # promise a clean database it cannot deliver.
        chosen = {r.id for r in self._results}
        key = self._key_of(self._results[0])
        survivors.extend(
            other
            for other in self._library.results()
            if other.id not in chosen and self._key_of(other) == key
        )
        return survivors

    # -- display -----------------------------------------------------------

    def _primary(self):
        return next(r for r in self._results if r.id == self.primary_id())

    def union(self) -> list[float]:
        """Every frequency the combined result would cover, ascending."""
        seen: list[float] = []
        for result in self._results:
            for omega in result.omegas:
                if not any(abs(float(omega) - s) <= OMEGA_TOLERANCE for s in seen):
                    seen.append(float(omega))
        return sorted(seen)

    def _refresh(self) -> None:
        if self._problem:
            self.ui.lblHeading.setText(f'<span style="color:{CONFLICT}">{escape(self._problem)}</span>')
            self.ui.tableEffect.setRowCount(0)
            self.ui.lblOutcome.setText("—")
            self._set_ok(False, self._problem)
            return

        where = f"on condition <b>{escape(self._results[0].condition_id)}</b>"
        if self.combining:
            self.ui.lblHeading.setText(
                f"{len(self._results)} results {where}. They agree on the mesh and on every "
                "setting, so they can be <b>folded into one</b> covering all their frequencies."
            )
            self._fill_combine()
            self.ui.lblOutcome.setText(self._combine_outcome())
            self._set_ok(True, "")
            return

        dropping = self.plan()
        self.ui.lblHeading.setText(
            f"{len(self._results)} results {where}. They differ in how they were computed, so one "
            "result could not record both — they stay as they are and only the overlap is resolved."
        )
        self._fill_effect(dropping)
        self.ui.lblOutcome.setText(self._outcome_text(dropping))
        self._set_ok(
            bool(dropping),
            "they do not overlap, so there is nothing to resolve, and they cannot be combined "
            "either: " + "; ".join(self._differences),
        )

    def _fill_combine(self) -> None:
        """One row per contributor, with what it brings to the union."""
        table = self.ui.tableEffect
        table.setRowCount(len(self._results))
        primary = self._primary()
        covered = [float(w) for w in primary.omegas]

        for row, result in enumerate(self._results):
            if result.id == primary.id:
                brings = [float(w) for w in result.omegas]
                shared: list[float] = []
                role = "primary — supplies any frequency they share"
            else:
                brings, shared = [], []
                for omega in result.omegas:
                    target = brings if not _covers(covered, omega) else shared
                    target.append(float(omega))
                role = "folded in"
                covered.extend(brings)

            values = (
                self._name(result),
                role,
                format_grid(sorted(period_from_omega(w) for w in brings)) if brings else "nothing new",
                format_grid(sorted(period_from_omega(w) for w in shared)) if shared else "—",
            )
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(value))

    def _combine_outcome(self) -> str:
        union = self.union()
        periods = sorted(period_from_omega(w) for w in union)
        lines = [
            f"One result covering {len(union)} frequencies: {escape(format_grid(periods))} s.",
            f'<span style="color:{CLEAN}">Nothing is lost. They record the same mesh, the same '
            "settings and the same wave directions, so the combined result records exactly what "
            "they did.</span>",
        ]

        primary = self._primary()
        contested = sorted(
            float(w)
            for w in primary.omegas
            if any(
                _covers([float(o) for o in other.omegas], w)
                for other in self._results
                if other.id != primary.id
            )
        )
        if contested:
            where = ", ".join(f"{period_from_omega(w):.2f} s" for w in contested)
            lines.append(
                f'<span style="color:{INCOMPLETE}">{escape(where)} is covered more than once, and '
                "the primary supplies it. They agree on every setting so the numbers should match "
                "— but they are separate runs, and Capytaine is not bit-reproducible in finite "
                "depth, so this is still a choice.</span>"
            )
        return "<br>".join(lines)

    def _set_ok(self, enabled: bool, reason: str) -> None:
        """Enable Merge, and say why not beside the button when it is off.

        Spec 09's second cross-cutting rule. The reason was previously in the
        heading for one case and the outcome box for the other, which is two
        places a reader has to know to look -- and a greyed-out button with the
        explanation somewhere else reads as a broken button.
        """
        button = self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok)
        button.setText("Combine" if self.combining else "Merge")
        button.setEnabled(enabled)

        if not enabled:
            hint = f'<span style="color:{INCOMPLETE}">Cannot merge: {escape(reason)}.</span>'
        elif self.combining:
            hint = (
                "The originals are deleted once the combined result is written. That order is "
                "deliberate: interrupted in between, the library keeps a redundant result — which "
                "is a conflict, visible and fixable — rather than a hole."
            )
        else:
            hint = (
                "Removing frequencies cannot be undone — the data was minutes of solving. "
                "A result that would lose every frequency is removed entirely."
            )
        self.ui.lblFooterHint.setText(hint)

    def _fill_effect(self, dropping) -> None:
        table = self.ui.tableEffect
        table.setRowCount(len(self._results))
        for row, result in enumerate(self._results):
            gone = dropping.get(result.id, [])
            kept = [
                float(w)
                for w in result.omegas
                if not any(abs(float(w) - g) <= OMEGA_TOLERANCE for g in gone)
            ]
            primary = result.id == self.primary_id()
            periods = sorted(period_from_omega(w) for w in kept)
            lost = sorted(period_from_omega(w) for w in gone)

            values = (
                self._name(result),
                "primary — keeps everything" if primary else "fills the gaps",
                format_grid(periods) if kept else "nothing — the result is removed",
                format_grid(lost) if lost else "—",
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if not kept:
                    cell.setForeground(QColor(CONFLICT))
                table.setItem(row, column, cell)

    def _outcome_text(self, dropping) -> str:
        if not dropping:
            return (
                f'<span style="color:{CLEAN}">These results do not overlap — there is '
                "nothing to resolve, and nothing would be removed.</span>"
            )

        before = coverage_of([r for r in self._library.results() if self._key_of(r) == self._key_of(self._results[0])])
        after = coverage_of(self._survivors(dropping))

        was = sum(1 for c in before if c.conflicted)
        now = sum(1 for c in after if c.conflicted)
        was_gaps = {round(c.omega, 9) for c in before if not c.conflicted and not c.complete}
        new_gaps = [
            c for c in after if not c.conflicted and not c.complete and round(c.omega, 9) not in was_gaps
        ]

        removed = sum(len(v) for v in dropping.values())
        lines = [f"Removes {removed} frequencies from {len(dropping)} result(s)."]

        if was and not now:
            lines.append(
                f'<span style="color:{CLEAN}">Resolves the conflict: {was} contested '
                "frequencies become clean and the database can be assembled.</span>"
            )
        elif now:
            lines.append(
                f'<span style="color:{INCOMPLETE}">{now} frequencies are still contested '
                "afterwards, by results outside this selection.</span>"
            )

        if new_gaps:
            where = ", ".join(f"{period_from_omega(c.omega):.2f} s" for c in new_gaps)
            lines.append(
                f'<span style="color:{CONFLICT}">Leaves a gap at {escape(where)} — the primary '
                "does not supply everything the trimmed result did. Trading a conflict for a gap "
                "is not a fix: choose the other result as primary, or delete frequencies "
                "individually instead.</span>"
            )
        return "<br>".join(lines)
