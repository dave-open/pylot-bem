"""The library tree: every entity in the file, in the order it was derived.

    library
      condition            z_origin / heel / trim in their own columns
        calculation mesh
          result

Four levels, because that *is* the domain: a result is solved on a mesh, a mesh
is built at a condition, a condition is defined against the base shape. Nesting
them is the cheapest possible statement of what depends on what, and it makes
the delete cascades legible before they are triggered.

Two things about it are deliberate and easy to undo by accident:

- **Results are multi-selectable.** Comparing two competing results is how a
  conflict gets resolved (spec 02 section 3.2), so it is the main loop of the
  application rather than a power-user gesture.
- **The tree is not a filter.** Selecting a mesh does not narrow the Results
  tab (spec 06 section 4). The tree is for picking something to act on; the
  tab below is for seeing what exists.

The coloured dot on a result is the state of the *database it feeds*, not of
the result itself -- a perfectly good result is marked red when another result
contests the same frequency, which is exactly the thing the user has to go and
resolve.
"""

from PySide6.QtCore import QItemSelectionModel, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QMenu, QTreeWidget, QTreeWidgetItem

from pylot_bem.app.formatting import CLEAN, CONFLICT, INCOMPLETE, degrees_from_slope, format_range, period_from_omega

__all__ = ["LibraryTree", "Node"]

# What a row is. Carried on the item rather than inferred from its depth, so
# the context menu and the property pane agree without either counting parents.
type Node = tuple[str, str]

_KIND_ROLE = Qt.ItemDataRole.UserRole


def _dot(colour: str, size: int = 10) -> QIcon:
    """A filled circle, for the database-state marker."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(colour))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(1, 1, size - 2, size - 2)
    painter.end()
    return QIcon(pixmap)


class LibraryTree(QTreeWidget):
    """Every entity in the open library.

    Signals:
        selectionSummary: ``(kind, ids)`` for the current selection. Named
            away from ``selectionChanged``, which ``QAbstractItemView``
            already has as a protected virtual -- shadowing it with a
            ``Signal`` breaks the view's own bookkeeping. ``kind``
            is ``"library"``, ``"condition"``, ``"mesh"``, ``"result"``,
            ``"results"`` for several at once, or ``""`` for none.
        newConditionRequested: From the library row.
        createMeshRequested: ``condition_id``.
        solveRequested: ``mesh_id``.
        inspectRequested: ``[result_id, ...]``.
        mergeRequested: ``[result_id, ...]``, two or more.
        deleteFrequenciesRequested: ``result_id``.
        removeRequested: ``(kind, id)`` -- confirmation belongs to the window.
        validateRequested: From the library row.
    """

    selectionSummary = Signal(str, list)
    newConditionRequested = Signal()
    createMeshRequested = Signal(str)
    solveRequested = Signal(str)
    inspectRequested = Signal(list)
    mergeRequested = Signal(list)
    deleteFrequenciesRequested = Signal(str)
    removeRequested = Signal(str, str)
    validateRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setColumnCount(4)
        # The degree sign rather than "deg" only because the three numeric
        # columns are taken out of the name's width and the tree is narrow.
        # The unit still has to be there (spec 09 rule 3) -- the abbreviation
        # is what gives way, never the unit.
        self.setHeaderLabels(["Name", "z₀ [m]", "Heel [°]", "Trim [°]"])
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setUniformRowHeights(True)
        self.setAlternatingRowColors(True)

        self.customContextMenuRequested.connect(self._show_menu)
        self.itemSelectionChanged.connect(self._emit_selection)

        self._library = None
        self._dots = {"usable": _dot(CLEAN), "incomplete": _dot(INCOMPLETE), "conflict": _dot(CONFLICT)}

    # -- filling -----------------------------------------------------------

    def rebuild(self, library, *, keep: list[str] | None = None) -> None:
        """Rebuild from scratch, restoring the selection by id.

        Rebuilding wholesale rather than patching in place: every action in the
        application can change the shape of the tree -- deleting a condition
        removes meshes and results, and solving changes another result's
        database state -- so an incremental update would have to know about all
        of them. The tree is small enough that correctness is worth more than
        the redraw.
        """
        keep = keep if keep is not None else self.selected_ids()
        self._library = library
        self.clear()
        if library is None:
            return

        states = self._database_states(library)

        root = QTreeWidgetItem(self, [library.info.vessel_name or library.path.stem, "", "", ""])
        root.setData(0, _KIND_ROLE, ("library", "library"))
        root.setToolTip(0, str(library.path))

        results_by_mesh: dict[str, list] = {}
        for result in library.results():
            results_by_mesh.setdefault(result.mesh_id, []).append(result)

        for condition in library.conditions():
            item = QTreeWidgetItem(
                root,
                [
                    condition.label or condition.id,
                    f"{condition.z_origin:.2f}",
                    f"{degrees_from_slope(condition.heel):.2f}",
                    f"{degrees_from_slope(condition.trim):.2f}",
                ],
            )
            item.setData(0, _KIND_ROLE, ("condition", condition.id))

            for mesh in library.meshes(condition.id):
                mesh_item = QTreeWidgetItem(mesh_label(mesh))
                mesh_item.setData(0, _KIND_ROLE, ("mesh", mesh.id))
                item.addChild(mesh_item)

                for result in results_by_mesh.get(mesh.id, []):
                    result_item = QTreeWidgetItem(result_label(result))
                    result_item.setData(0, _KIND_ROLE, ("result", result.id))
                    state = states.get(result.id)
                    if state is not None:
                        result_item.setIcon(0, self._dots[state])
                        result_item.setToolTip(0, f"the database this feeds is {state}")
                    mesh_item.addChild(result_item)

        self.expandAll()
        # The three numbers size to their contents and the name takes what is
        # left. Sizing every column to its contents instead pushes heel and
        # trim off the edge of the dock behind a scrollbar, which is where the
        # only reason to have them as columns quietly disappears.
        header = self.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.select_ids(keep)

    @staticmethod
    def _database_states(library) -> dict[str, str]:
        """Per result, the state of the database it contributes to."""
        states = {}
        for view in library.databases():
            state = "conflict" if view.conflicts else "incomplete" if view.incomplete else "usable"
            for result_id in view.result_ids:
                states[result_id] = state
        return states

    # -- selection ---------------------------------------------------------

    def selected_nodes(self) -> list[Node]:
        return [item.data(0, _KIND_ROLE) for item in self.selectedItems() if item.data(0, _KIND_ROLE)]

    def selected_ids(self) -> list[str]:
        return [node[1] for node in self.selected_nodes()]

    def select_ids(self, ids: list[str]) -> None:
        """Re-select by id after a rebuild. Missing ids are simply dropped."""
        wanted = set(ids)
        self.clearSelection()
        first = None
        for item in self._walk():
            node = item.data(0, _KIND_ROLE)
            if node and node[1] in wanted:
                item.setSelected(True)
                first = first or item
        if first is not None:
            # NoUpdate, or this throws the selection away again: under
            # ExtendedSelection the plain setCurrentItem is ClearAndSelect, so
            # restoring two results after a rebuild would leave one.
            self.setCurrentItem(first, 0, QItemSelectionModel.SelectionFlag.NoUpdate)
        self._emit_selection()

    def _walk(self):
        stack = [self.topLevelItem(i) for i in range(self.topLevelItemCount())]
        while stack:
            item = stack.pop()
            yield item
            stack.extend(item.child(i) for i in range(item.childCount()))

    def _emit_selection(self) -> None:
        nodes = self.selected_nodes()
        if not nodes:
            self.selectionSummary.emit("", [])
            return
        kinds = {kind for kind, _ in nodes}
        if len(nodes) > 1:
            # A mixed selection is not a thing any pane can show, so it is
            # reported as what it has in common: several results, or nothing.
            kind = "results" if kinds == {"result"} else ""
            self.selectionSummary.emit(kind, [node_id for _, node_id in nodes])
            return
        kind, node_id = nodes[0]
        self.selectionSummary.emit(kind, [node_id])

    # -- context menu ------------------------------------------------------

    def _show_menu(self, position) -> None:
        item = self.itemAt(position)
        if item is None:
            return
        node = item.data(0, _KIND_ROLE)
        if not node:
            return
        kind, node_id = node

        # Each node's own kind, not the clicked one's. Written as
        # `if kind == "result"` this was a constant: ctrl-clicking a mesh and a
        # result then right-clicking the result handed Merge and Remove a mesh
        # id, which they look up as a result and fail on.
        selected = [i for node_kind, i in self.selected_nodes() if node_kind == "result"]
        menu = QMenu(self)

        if kind == "library":
            menu.addAction("New condition…", self.newConditionRequested.emit)
            menu.addSeparator()
            menu.addAction("Validate library", self.validateRequested.emit)
        elif kind == "condition":
            menu.addAction("Create mesh…", lambda: self.createMeshRequested.emit(node_id))
            menu.addAction("New condition…", self.newConditionRequested.emit)
            menu.addSeparator()
            menu.addAction("Remove condition…", lambda: self.removeRequested.emit(kind, node_id))
        elif kind == "mesh":
            menu.addAction("Solve…", lambda: self.solveRequested.emit(node_id))
            menu.addSeparator()
            menu.addAction("Remove mesh…", lambda: self.removeRequested.emit(kind, node_id))
        elif kind == "result":
            targets = selected if len(selected) > 1 and node_id in selected else [node_id]
            label = "Compare in Inspect…" if len(targets) > 1 else "Inspect…"
            menu.addAction(label, lambda: self.inspectRequested.emit(targets))
            if len(targets) > 1:
                menu.addAction("Merge…", lambda: self.mergeRequested.emit(targets))
            menu.addAction("Delete frequencies…", lambda: self.deleteFrequenciesRequested.emit(node_id))
            menu.addSeparator()
            menu.addAction(
                f"Remove {len(targets)} results…" if len(targets) > 1 else "Remove result…",
                lambda: [self.removeRequested.emit("result", target) for target in targets],
            )

        menu.exec(self.viewport().mapToGlobal(position))


def mesh_label(mesh) -> list[str]:
    """The four columns of a mesh row.

    Short on purpose. The tree is narrow and its first column carries three
    levels of indent, so anything more than an identity and one number is
    elided into uselessness -- and the full settings are one click away on the
    property pane, and in the Results table, already.

    z_origin, heel and trim are blank below a condition: they belong to the
    condition, and repeating them down the subtree would read as though a mesh
    could carry its own.
    """
    return [f"{mesh.id} · {len(mesh.faces)} faces", "", "", ""]


def result_label(result) -> list[str]:
    """A result row, by its label where it has one.

    Same rule as a condition: the id is a stable handle, the label is what a
    person calls it. A result that has been named should read by that name
    here, or naming it achieves nothing visible.
    """
    periods = sorted(period_from_omega(w) for w in result.omegas)
    name = result.label or result.id
    return [f"{name} · {format_range(periods, decimals=0)} s", "", "", ""]
