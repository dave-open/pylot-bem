"""Spec 06 section 7: the standalone application.

Every test builds a **real** ``MainWindow`` against a **real** library on a
real solved fixture. Nothing is mocked except the two modal dialogs that would
otherwise wait for a human -- and where one is stubbed, the assertion is on
what the application then *did* to the library, never on the stub.

The six items spec 06 section 7 asks for are named in the test names, so that a
missing one is visible rather than assumed. Item 1 (the whole flow through the
CLI) is ``test_cli.py`` and item 5a (kill leaves no worker) is ``test_pool.py``,
where the process ids are.

The fixture is built once: three conditions, three meshes, and results arranged
so the library holds one **usable** database, one in **conflict** and one
**incomplete**. That is not a contrivance -- a library with competing results
in it is the normal state of one being built (ADR-9), and a fixture with only
clean data would leave the screens that matter untested.
"""

import shutil
import time

import numpy as np
import pytest
from hull import BOX_FACES, BOX_VERTICES
from pylot_db.probes import probes_for_condition
from pylot_db.storage import Library, LibraryError
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QDialogButtonBox, QMessageBox

from pylot_bem.api import Pylot
from pylot_bem.app.dialogs import LID_AUTO, LID_BELOW, CreateMeshDialog, NewConditionDialog, SolveDialog
from pylot_bem.app.formatting import degrees_from_slope, period_from_omega, slope_from_degrees
from pylot_bem.app.window import MainWindow
from pylot_bem.solver import SolveSettings

COARSE = {"pct": 20.0, "iterations": 5}
DIRECTIONS = (0.0, 90.0)

# Two grids that overlap at 0.6, which is what puts the "design" key in
# conflict. Chosen to overlap: resolving that is the main loop of the
# application (spec 06 section 4), so the fixture has to contain one.
FINE = (0.5, 0.6)
COARSE_GRID = (0.6, 0.7)


@pytest.fixture(scope="module")
def library_path(tmp_path_factory):
    """A real library, solved, holding all three database states."""
    path = tmp_path_factory.mktemp("app") / "fixture.pylot"
    library = Pylot.create(
        path,
        vessel_name="Boxboat",
        origin_description="stern, centerline, keel",
        vertices=BOX_VERTICES,
        faces=BOX_FACES,
        is_xz_symmetric=True,
    )

    ballast = library.create_condition(z_origin=-2.0, condition_id="ballast", label="Ballast")
    design = library.create_condition(z_origin=-4.0, condition_id="design", label="Design")
    library.create_condition(z_origin=-6.0, heel=slope_from_degrees(2.0), condition_id="loaded", label="Loaded")

    ballast_mesh = library.create_mesh(ballast, **COARSE, mesh_id="ballast-mesh")
    design_mesh = library.create_mesh(design, **COARSE, mesh_id="design-mesh")

    # usable
    library.run_solve(
        ballast_mesh, SolveSettings(omegas=FINE, wave_directions=DIRECTIONS), result_id="ballast-run"
    )
    # in conflict: two results on one key, overlapping at omega 0.6
    library.run_solve(
        design_mesh, SolveSettings(omegas=FINE, wave_directions=DIRECTIONS), result_id="design-fine"
    )
    library.run_solve(
        design_mesh, SolveSettings(omegas=COARSE_GRID, wave_directions=DIRECTIONS), result_id="design-coarse"
    )
    # incomplete: radiation only, so every frequency lacks diffraction
    library.run_solve(design_mesh, SolveSettings(omegas=(0.9,)), result_id="design-radiation")
    library.close()
    return path


@pytest.fixture
def path(library_path, tmp_path):
    """A private copy, so a test that deletes something cannot affect another."""
    copy = tmp_path / "library.pylot"
    shutil.copy(library_path, copy)
    return copy


@pytest.fixture
def isolated_settings(tmp_path):
    """A real ``QSettings``, backed by a private file rather than the
    developer's actual registry.

    Every ``MainWindow`` built in this module is given one explicitly.
    Recent Files persists through ``QSettings``, and a ``MainWindow`` built
    without an override reaches for the real ``dave-open/pylot`` key -- which
    a test run must never read from or write to.
    """
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


@pytest.fixture
def window(qapp, path, isolated_settings):
    main = MainWindow(settings=isolated_settings)
    main.show()
    main.open_path(path)
    yield main
    main.close()


def pump(qapp, predicate, timeout=120.0):
    """Run the event loop until something becomes true."""
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()
    return predicate()


def tree_rows(window):
    """``[(depth, kind, id), ...]`` for the whole tree."""
    rows = []

    def walk(item, depth):
        kind, node_id = item.data(0, Qt.ItemDataRole.UserRole)
        rows.append((depth, kind, node_id))
        for i in range(item.childCount()):
            walk(item.child(i), depth + 1)

    for i in range(window.tree.topLevelItemCount()):
        walk(window.tree.topLevelItem(i), 0)
    return rows


# --------------------------------------------------------------------------
# Spec 06 section 7 item 6: it starts with DAVE not installed
# --------------------------------------------------------------------------


def test_the_application_starts_with_dave_not_installed(qapp, path, isolated_settings):
    """Item 6. The boundary spec 06 section 1 says a dedicated app makes real.

    Asserted the only way that means anything: DAVE genuinely is not importable
    here, and the window opens a library anyway.
    """
    import importlib.util

    assert importlib.util.find_spec("DAVE") is None, (
        "DAVE is installed in this environment, so this test proves nothing. "
        "The application must not need it; run the suite without it."
    )

    main = MainWindow(settings=isolated_settings)
    main.show()
    main.open_path(path)
    assert main.library is not None
    assert len(main.library.results()) == 4
    main.close()


def test_no_module_in_the_application_imports_dave():
    """The import guard of ADR-7, pointed at the application.

    ``pylot_db`` has its own; this is the other half. The window may import the
    calculation stack -- it is the write side -- but DAVE is out for every
    package here.
    """
    import ast
    from pathlib import Path

    import pylot_bem.app

    root = Path(pylot_bem.app.__file__).parent
    offenders = []
    for source in root.rglob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            if any(name.split(".")[0] == "DAVE" for name in names):
                offenders.append(source.name)
    assert not offenders, f"these import DAVE: {sorted(set(offenders))}"


# --------------------------------------------------------------------------
# The tree, and what the selection drives
# --------------------------------------------------------------------------


def test_the_tree_holds_the_whole_library_four_levels_deep(window):
    rows = tree_rows(window)
    kinds_by_depth = {depth: kind for depth, kind, _ in rows}

    assert kinds_by_depth[0] == "library"
    assert kinds_by_depth[1] == "condition"
    assert kinds_by_depth[2] == "mesh"
    assert kinds_by_depth[3] == "result"
    assert {node_id for _, kind, node_id in rows if kind == "condition"} == {"ballast", "design", "loaded"}
    assert {node_id for _, kind, node_id in rows if kind == "result"} == {
        "ballast-run",
        "design-fine",
        "design-coarse",
        "design-radiation",
    }


def test_a_condition_with_no_mesh_is_still_in_the_tree(window):
    """A library in progress is the normal case, not a broken one."""
    rows = tree_rows(window)
    assert (1, "condition", "loaded") in rows
    assert not [r for r in rows if r[1] == "mesh" and r[2].startswith("loaded")]


def test_selecting_a_condition_shows_the_condition_pane_and_draws_it(window):
    window.tree.select_ids(["design"])

    assert window.panes.currentWidget() is window.condition_pane
    assert "design" in window.condition_pane.ui.lblId.text()
    # The viewport really built a scene, not merely accepted the call.
    assert set(window.viewport._actors) >= {"base", "waterplane", "probes", "application_point"}
    assert "mesh" not in window.viewport._actors, "no mesh is selected, so none is drawn"


def test_selecting_a_mesh_adds_the_mesh_to_the_scene(window):
    window.tree.select_ids(["design-mesh"])

    assert window.panes.currentWidget() is window.mesh_pane
    assert "mesh" in window.viewport._actors
    assert "half vessel" in window.mesh_pane.ui.lblFaces.text()

    mesh = window.library.mesh("design-mesh")
    assert str(len(mesh.faces)) in window.mesh_pane.ui.lblFaces.text()
    assert str(2 * len(mesh.faces)) in window.mesh_pane.ui.lblPanels.text(), (
        "a half mesh solves twice its faces"
    )


def test_selecting_several_results_gives_the_comparison_pane(window):
    window.tree.select_ids(["design-fine", "design-coarse"])

    assert window.panes.currentWidget() is window.selection_pane
    assert "2 results selected" in window.selection_pane.ui.lblHeading.text()
    assert "Same database" in window.selection_pane.ui.lblNote.text()
    assert window.selection_pane.ui.listSelected.count() == 2


def test_the_results_table_is_not_filtered_by_the_tree(window):
    """Spec 06 section 4, the rule that becomes load-bearing under ADR-9.

    Comparing competing results is how a conflict is resolved, so the table
    below must keep showing all of them whatever the tree is pointing at.
    """
    everything = window.results_tab.table.rowCount()
    assert everything == 4

    for selection in (["ballast"], ["design-mesh"], ["design-fine"]):
        window.tree.select_ids(selection)
        assert window.results_tab.table.rowCount() == everything


def test_the_tree_marks_each_result_with_its_database_state(window):
    """The dot is the state of the database the result *feeds*, not its own."""
    states = window.tree._database_states(window.library)

    assert states["ballast-run"] == "usable"
    assert states["design-fine"] == "conflict"
    assert states["design-coarse"] == "conflict"


# --------------------------------------------------------------------------
# The 3D view
# --------------------------------------------------------------------------


def test_the_viewport_has_a_real_opengl_render_window(window):
    """The test that catches a viewport which draws nothing and says nothing.

    VTK's object factory hands back the **abstract** ``vtkRenderWindow`` unless
    ``vtkmodules.vtkRenderingOpenGL2`` has been imported for its side effect.
    That base class accepts every actor, raises nothing, and renders no pixels
    -- indistinguishable from an empty library. Asserting on the class is the
    only cheap way to tell the two apart, and it is why the import exists.
    """
    assert window.viewport.render_window.GetClassName() != "vtkRenderWindow", (
        "the OpenGL backend is not registered, so this viewport would draw nothing"
    )


def test_the_viewport_declines_to_draw_where_it_cannot_and_says_why(window):
    """Offscreen, initialising VTK is an access violation, not an exception.

    So it must not be attempted. The suite runs on exactly that platform, which
    is what makes this reachable rather than theoretical.
    """
    from PySide6.QtGui import QGuiApplication

    if QGuiApplication.platformName() not in ("offscreen", "minimal", "vnc"):
        pytest.skip("this only applies to a platform with no native window")

    assert window.viewport.unavailable
    assert "offscreen" in window.viewport.unavailable
    # Everything that is not the drawing still works.
    window.tree.select_ids(["design-mesh"])
    assert set(window.viewport._actors) >= {"base", "mesh", "waterplane"}


def test_the_camera_view_up_is_not_degenerate(window):
    """A zero view up renders an empty window, silently.

    VTK's default camera looks along -z, so setting the view up to +z *after*
    ``ResetCamera`` makes the two parallel and ``OrthogonalizeViewUp`` leaves
    ``(0, 0, 0)``. Every actor is still present and correct, no warning is
    raised, and nothing is drawn. Offscreen there are no pixels to check, so
    the camera itself is what this asserts on -- and it is enough, because the
    degenerate vector is the whole failure.
    """
    window.tree.select_ids(["design"])
    camera = window.viewport._renderer.GetActiveCamera()

    view_up = np.asarray(camera.GetViewUp(), dtype=float)
    assert np.linalg.norm(view_up) > 0.5, f"degenerate view up {view_up}, so the scene renders empty"

    direction = np.asarray(camera.GetDirectionOfProjection(), dtype=float)
    assert abs(float(np.dot(view_up, direction))) < 0.99, "view up is parallel to the view direction"


def test_the_camera_frames_what_is_in_the_scene(window):
    """It has to be looking at the hull, not merely holding a valid vector."""
    window.tree.select_ids(["design"])
    renderer = window.viewport._renderer
    camera = renderer.GetActiveCamera()

    x_lo, x_hi, y_lo, y_hi, z_lo, z_hi = renderer.ComputeVisiblePropBounds()
    centre = np.array([(x_lo + x_hi) / 2, (y_lo + y_hi) / 2, (z_lo + z_hi) / 2])
    focal = np.asarray(camera.GetFocalPoint(), dtype=float)
    diagonal = float(np.linalg.norm([x_hi - x_lo, y_hi - y_lo, z_hi - z_lo]))

    assert np.linalg.norm(focal - centre) < diagonal, "the camera is pointed away from the scene"
    assert diagonal > 1.0, "there is nothing in the scene, so framing it proves nothing"


def test_hiding_a_layer_hides_its_actor(window):
    window.tree.select_ids(["design-mesh"])
    assert window.viewport._actors["mesh"].GetVisibility()

    window.layer_actions["mesh"].setChecked(False)
    assert not window.viewport._actors["mesh"].GetVisibility()

    window.layer_actions["mesh"].setChecked(True)
    assert window.viewport._actors["mesh"].GetVisibility()


def test_a_hidden_layer_stays_hidden_when_the_scene_is_rebuilt(window):
    """Otherwise the View menu and the scene disagree after every click."""
    window.layer_actions["waterplane"].setChecked(False)
    window.tree.select_ids(["design-mesh"])

    assert not window.viewport._actors["waterplane"].GetVisibility()


def test_the_hull_is_drawn_with_a_backface_colour(window):
    """Spec 09 section L: an inverted normal is otherwise invisible."""
    window.tree.select_ids(["design"])
    back = window.viewport._actors["base"].GetBackfaceProperty()

    assert back is not None, "no backface property, so an inverted normal would look correct"
    assert back.GetColor() != window.viewport._actors["base"].GetProperty().GetColor()


def test_the_scene_is_built_in_diffraction_space(window):
    """The waterplane is z = 0 only if the hull was placed first.

    A base shape drawn vessel-local would sit with its keel at zero and the
    whole condition would be invisible, which is the mistake this checks for.
    """
    window.tree.select_ids(["design"])
    bounds = window.viewport._actors["base"].GetBounds()
    condition = window.library.condition("design")

    assert bounds[4] == pytest.approx(condition.z_origin, abs=1e-6), "z_min should be the placed keel"
    assert bounds[5] > 0.0, "the hull should stick out above the waterplane"


# --------------------------------------------------------------------------
# Units: degrees on screen, slopes in storage
# --------------------------------------------------------------------------


def test_heel_is_shown_in_degrees_and_stored_as_a_slope(window):
    loaded = window.library.condition("loaded")
    assert loaded.heel == pytest.approx(slope_from_degrees(2.0))

    window.tree.select_ids(["loaded"])
    shown = window.condition_pane.ui.lblHeel.text()

    assert shown.startswith("2.0"), f"expected degrees, got {shown!r}"
    assert loaded.heel != pytest.approx(2.0), "the slope and the degrees must not be the same number"


def test_a_heeled_condition_reports_a_full_mesh_with_the_reason(window):
    window.tree.select_ids(["loaded"])
    text = window.condition_pane.ui.lblSymmetry.text()

    assert "no" in text
    assert "heel" in text, "a bare 'no' sends the user looking for a checkbox that does not exist"


def test_periods_are_shown_where_omega_is_stored(window):
    window.tree.select_ids(["ballast-run"])
    result = window.library.result("ballast-run")

    assert tuple(result.omegas) == pytest.approx(FINE)
    shown = window.result_pane.ui.lblPeriods.text()
    longest = period_from_omega(min(FINE))
    assert f"{longest:.2f}" in shown, f"expected periods in {shown!r}"


# --------------------------------------------------------------------------
# Spec 06 section 7 item 2: a probe edit, announced
# --------------------------------------------------------------------------


def test_editing_probes_recomputes_every_condition_and_reports_what_changed(window, monkeypatch):
    """Item 2. Asserted on the library, not on the dialog being shown.

    The dialog is stubbed to answer Apply; everything checked afterwards is
    what the application then did to the stored conditions.
    """
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Apply)

    before = {c.id: c.probes.copy() for c in window.library.conditions()}
    window.tree.select_ids(["library"])
    window.library_pane._add_probe_row()

    table = window.library_pane.ui.tableProbes
    table.item(table.rowCount() - 1, 0).setText("30.0")
    table.item(table.rowCount() - 1, 1).setText("5.0")
    window.library_pane._apply_probes()

    after = {c.id: c.probes for c in window.library.conditions()}
    assert len(window.library.probe_xy) == len(before["design"]) + 1

    for condition_id, probes in after.items():
        assert len(probes) == len(before[condition_id]) + 1, f"{condition_id} was not recomputed"
        # The new probe's z solves onto the waterplane for that condition,
        # which is the whole point of recomputing rather than appending.
        expected = probes_for_condition(window.library.condition(condition_id).transform, window.library.probe_xy)
        assert probes == pytest.approx(expected)

    message = window.statusBar().currentMessage()
    assert "conditions changed" in message
    assert "3" in message, f"the count of affected conditions is missing from {message!r}"


def test_the_probe_report_counts_only_conditions_that_actually_change(window, monkeypatch):
    """Re-applying the same probes changes nothing, and must say so.

    A count that was really "the number of conditions" would read 3 here too,
    so this is what tells the two apart.
    """
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Apply)

    window.tree.select_ids(["library"])
    window.library_pane._apply_probes()

    assert "0 of 3 conditions changed" in window.statusBar().currentMessage()


def test_a_probe_that_is_not_a_number_is_refused_rather_than_dropped(window):
    window.tree.select_ids(["library"])
    table = window.library_pane.ui.tableProbes
    table.item(0, 0).setText("not a number")

    with pytest.raises(ValueError, match="not a number"):
        window.library_pane.probe_table_values()


# --------------------------------------------------------------------------
# Spec 06 section 7 item 3: validation renders, corruption is displayed
# --------------------------------------------------------------------------


def test_validation_findings_render(window):
    """Item 3, first half. The fixture is genuinely inconsistent."""
    findings = window.validation_tab.run()

    assert findings, "the fixture holds a conflict and an incomplete key; validate should say so"
    assert window.validation_tab.table.rowCount() == len(findings)
    assert window.validation_tab.table.item(0, 0).text() in {"error", "warning"}
    assert "design" in " ".join(
        window.validation_tab.table.item(row, 2).text() for row in range(window.validation_tab.table.rowCount())
    )


def test_a_corrupted_library_is_displayed_not_crashed_on(qapp, path, isolated_settings):
    """Item 3, second half.

    The base shape blob is replaced with rubbish, which is about as broken as a
    library can be while still opening: every screen that touches geometry
    fails. The application must still come up, still list the results, and say
    what is wrong.
    """
    import sqlite3

    connection = sqlite3.connect(path)
    connection.execute("UPDATE base_shape SET vertices = ? WHERE id = 1", (b"not an array",))
    connection.commit()
    connection.close()

    main = MainWindow(settings=isolated_settings)
    main.show()
    main.open_path(path)

    assert main.library is not None, "the window gave up on a library it could still show"
    assert "damaged" in main.statusBar().currentMessage().lower()
    assert main.tabs.currentWidget() is main.validation_tab
    # The screens that do not need geometry still work, which is the point.
    assert main.results_tab.table.rowCount() == 4
    main.close()


def test_validation_that_itself_fails_is_reported_not_raised(qapp, path, isolated_settings):
    import sqlite3

    connection = sqlite3.connect(path)
    connection.execute("UPDATE base_shape SET vertices = ? WHERE id = 1", (b"rubbish",))
    connection.commit()
    connection.close()

    main = MainWindow(settings=isolated_settings)
    main.open_path(path)
    findings = main.validation_tab.run()

    assert findings == []
    assert "could not complete" in main.validation_tab.summary.text().lower()
    main.close()


# --------------------------------------------------------------------------
# Spec 06 section 7 item 4: the match view ranks
# --------------------------------------------------------------------------


def test_the_match_view_ranks_the_fixture_correctly(window):
    """Item 4. The trial sits exactly on 'design', so the order is knowable.

    Ascending by RMS probe error means: design first at zero, then ballast and
    loaded ordered by how far their waterplane is from the trial's.
    """
    tab = window.match_tab
    tab.z_origin.setValue(-4.0)
    tab.heel.setValue(0.0)
    tab.trim.setValue(0.0)
    tab.rank()

    ranked = [tab.table.item(row, 0).text() for row in range(tab.table.rowCount())]
    errors = [float(tab.table.item(row, 1).text()) for row in range(tab.table.rowCount())]

    assert ranked[0] == "design"
    assert errors[0] == pytest.approx(0.0, abs=1e-9)
    assert errors == sorted(errors), "the list must be ascending by RMS error"

    # design is in conflict and is ranked anyway, with its reason: spec 09 J
    # ranks unusable candidates rather than hiding them. `loaded` is a
    # different case and is absent -- it has no results, so it has no
    # assembly key and there is nothing it could ever deliver.
    assert ranked == ["design", "ballast"], ranked
    assert not window.library.databases() or all(
        view.key.condition_id != "loaded" for view in window.library.databases()
    ), "loaded is absent from the ranking because it has no database, not because it scored badly"


def test_the_match_view_ranks_a_different_trial_differently(window):
    """Otherwise the test above could pass against a fixed order."""
    tab = window.match_tab
    tab.z_origin.setValue(-2.0)
    tab.rank()

    assert tab.table.item(0, 0).text() == "ballast"
    assert float(tab.table.item(0, 1).text()) == pytest.approx(0.0, abs=1e-9)


def test_the_match_view_says_why_a_candidate_is_unusable(window):
    window.match_tab.z_origin.setValue(-4.0)
    window.match_tab.rank()

    rows = {
        window.match_tab.table.item(row, 0).text(): window.match_tab.table.item(row, 4).text()
        for row in range(window.match_tab.table.rowCount())
    }
    assert rows["ballast"] == "yes"
    assert rows["design"].startswith("no —"), "a conflicted candidate must carry its reason"


def test_density_is_not_a_filter_in_the_match_view(window):
    """Spec 04 section 4: every database serves every density."""
    tab = window.match_tab
    tab.z_origin.setValue(-4.0)
    tab.rank()
    before = tab.table.rowCount()

    tab.rho.setValue(1.025)
    tab.rank()
    assert tab.table.rowCount() == before

    tab.rho.setValue(0.5)
    tab.rank()
    assert tab.table.rowCount() == before, "changing the density excluded a condition"


# --------------------------------------------------------------------------
# Databases and the conflict loop
# --------------------------------------------------------------------------


def test_the_databases_tab_shows_all_three_states(window):
    tab = window.databases_tab
    states = {tab.table.item(row, 0).text(): tab.table.item(row, 5).text() for row in range(tab.table.rowCount())}

    assert states["ballast"] == "usable"
    assert states["design"].startswith("conflict")


def test_a_conflict_offers_the_comparison_that_resolves_it(window):
    tab = window.databases_tab
    row = next(r for r in range(tab.table.rowCount()) if tab.table.item(r, 0).text() == "design")
    tab.table.selectRow(row)

    assert tab.button.isEnabled()
    assert "conflict" in tab.note.text().lower()

    tab._compare()
    assert window.tabs.currentWidget() is window.inspect_tab
    assert set(window.inspect_tab._result_ids) >= {"design-fine", "design-coarse"}


def test_deleting_the_contested_frequency_resolves_the_conflict(window):
    """The main loop of building a library, run end to end.

    Not "the button was clicked" -- the library really loses the frequency and
    the key really becomes usable afterwards.
    """
    contested = [view for view in window.library.databases() if view.conflicts]
    assert contested, "the fixture must start in conflict for this to mean anything"
    omegas = [c.omega for c in contested[0].conflicts]

    window.library.delete_frequencies("design-coarse", omegas)
    window.refresh()

    design = next(v for v in window.library.databases() if v.key.condition_id == "design")
    assert not design.conflicts
    assert window.databases_tab.table.rowCount() == 2, "one key per condition that has results"
    states = {
        window.databases_tab.table.item(r, 0).text(): window.databases_tab.table.item(r, 5).text()
        for r in range(window.databases_tab.table.rowCount())
    }
    assert not states["design"].startswith("conflict")


def test_the_frequency_dialog_previews_what_it_removes(window, qapp):
    from pylot_bem.app.dialogs import DeleteFrequenciesDialog

    dialog = DeleteFrequenciesDialog(window.library, window.library.result("design-coarse"), window)
    dialog._check_contested()

    chosen = dialog.chosen_omegas()
    assert chosen == pytest.approx([0.6]), "only the contested frequency should be ticked"
    assert "Resolves the conflict" in dialog._preview_text()
    dialog.close()


def test_the_frequency_dialog_warns_when_a_deletion_leaves_a_gap(window):
    """Trading a conflict for a silent gap is not a fix (spec 09 section I.1)."""
    from pylot_bem.app.dialogs import DeleteFrequenciesDialog

    dialog = DeleteFrequenciesDialog(window.library, window.library.result("ballast-run"), window)
    dialog._set_all(Qt.CheckState.Checked)

    text = dialog._preview_text()
    assert "nothing at" in text, f"no gap warning in {text!r}"
    dialog.close()


# --------------------------------------------------------------------------
# Inspect
# --------------------------------------------------------------------------


def test_inspect_plots_two_results_on_one_pair_of_axes(window):
    window.inspect_tab.show_results(window.library, ["design-fine", "design-coarse"])
    axes = window.inspect_tab.figure.axes[0]

    assert len(axes.lines) == 2
    assert {line.get_label() for line in axes.lines} == {"design-fine", "design-coarse"}


def test_density_scales_the_plotted_amplitude_and_nothing_else(window):
    """The claim the whole storage design rests on, checked where it is shown."""
    tab = window.inspect_tab
    tab.show_results(window.library, ["ballast-run"])

    tab.rho.setValue(1.0)
    at_one = tab.figure.axes[0].lines[0].get_ydata().copy()
    tab.rho.setValue(2.0)
    at_two = tab.figure.axes[0].lines[0].get_ydata().copy()

    assert at_two == pytest.approx(at_one * 2.0)
    assert abs(at_one).max() > 0, "a plot of zeros would satisfy any scaling"


def test_the_x_axis_switches_between_period_and_frequency(window):
    tab = window.inspect_tab
    tab.show_results(window.library, ["ballast-run"])

    periods = tab.figure.axes[0].lines[0].get_xdata().copy()
    tab.x_axis.setCurrentIndex(1)
    omegas = tab.figure.axes[0].lines[0].get_xdata().copy()

    assert sorted(omegas) == pytest.approx(sorted(FINE))
    assert sorted(periods) == pytest.approx(sorted(period_from_omega(w) for w in FINE))


def test_excitation_force_can_be_plotted_as_phase(window):
    tab = window.inspect_tab
    tab.show_results(window.library, ["ballast-run"])
    tab.quantity.setCurrentText("Excitation force")

    assert tab.direction.count() == len(DIRECTIONS)
    assert tab.phase.isEnabled()
    tab.phase.setChecked(True)
    assert "phase" in tab.figure.axes[0].get_ylabel()


def test_a_result_without_diffraction_is_reported_not_plotted_empty(window):
    """design-radiation carries no excitation force; saying so beats a blank."""
    tab = window.inspect_tab
    tab.show_results(window.library, ["design-radiation"])
    tab.quantity.setCurrentText("Excitation force")

    assert not tab.figure.axes[0].lines
    assert "excitation_force" in tab.heading.text()


# --------------------------------------------------------------------------
# Deletion shows its blast radius
# --------------------------------------------------------------------------


def test_removing_a_condition_states_what_goes_with_it(window, monkeypatch):
    seen = {}

    def spy(self, question, detail):
        seen["question"], seen["detail"] = question, detail
        return False

    monkeypatch.setattr(MainWindow, "_confirm", spy)
    window.remove("condition", "design")

    assert "design-mesh" in seen["detail"]
    assert "design-fine" in seen["detail"]
    assert window.library.condition("design"), "declining must not delete anything"


def test_removing_a_condition_really_cascades_when_confirmed(window, monkeypatch):
    monkeypatch.setattr(MainWindow, "_confirm", lambda *a: True)
    window.remove("condition", "design")

    assert {c.id for c in window.library.conditions()} == {"ballast", "loaded"}
    assert {m.id for m in window.library.meshes()} == {"ballast-mesh"}
    assert {r.id for r in window.library.results()} == {"ballast-run"}
    assert window.results_tab.table.rowCount() == 1, "the views followed the deletion"


# --------------------------------------------------------------------------
# The dialogs, without their event loops
# --------------------------------------------------------------------------


def test_the_new_condition_dialog_derives_as_it_is_typed(window):
    dialog = NewConditionDialog(window.library, window)
    dialog.ui.spinZOrigin.setValue(-4.0)

    assert "(30.000, 0.000, 2.000)" in dialog.ui.lblApplicationPoint.text()
    assert "1200" in dialog.ui.lblSubmerged.text() or "m²" in dialog.ui.lblSubmerged.text()
    dialog.close()


def test_the_new_condition_dialog_refuses_a_condition_out_of_the_water(window):
    dialog = NewConditionDialog(window.library, window)
    dialog.ui.spinZOrigin.setValue(5.0)

    assert "below the waterplane" in dialog.ui.lblProblem.text()
    assert not dialog.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
    dialog.close()


def test_the_new_condition_dialog_warns_about_a_duplicate(window):
    dialog = NewConditionDialog(window.library, window)
    dialog.ui.spinZOrigin.setValue(-4.0)

    assert "already" in dialog.ui.lblProblem.text()
    dialog.close()


def test_the_new_condition_dialog_converts_degrees_to_slopes(window):
    dialog = NewConditionDialog(window.library, window)
    dialog.ui.spinHeel.setValue(10.0)
    values = dialog.values()

    assert values["heel"] == pytest.approx(slope_from_degrees(10.0))
    assert degrees_from_slope(values["heel"]) == pytest.approx(10.0)
    dialog.close()


def test_the_create_mesh_dialog_shows_symmetry_as_derived(window):
    symmetric = CreateMeshDialog(window.library, window.library.condition("design"), window)
    heeled = CreateMeshDialog(window.library, window.library.condition("loaded"), window)

    assert "Half vessel" in symmetric.ui.lblSymmetry.text()
    assert "Full vessel" in heeled.ui.lblSymmetry.text()
    assert "heel" in heeled.ui.lblSymmetry.text()
    symmetric.close()
    heeled.close()


def test_the_solve_dialog_shows_the_cost_before_start(window):
    dialog = SolveDialog(window.library, window.library.mesh("design-mesh"), window)
    dialog.ui.spinPeriodFrom.setValue(8.0)
    dialog.ui.spinPeriodTo.setValue(16.0)
    dialog.ui.spinPeriodStep.setValue(4.0)
    dialog.ui.spinDirFrom.setValue(0.0)
    dialog.ui.spinDirTo.setValue(180.0)
    dialog.ui.spinDirStep.setValue(90.0)

    assert dialog.periods() == pytest.approx([8.0, 12.0, 16.0])
    assert dialog.directions() == pytest.approx([0.0, 90.0, 180.0])
    # 3 frequencies x (6 dofs + 3 directions)
    assert "27" in dialog.ui.lblCostProblems.text()
    assert "workers" in dialog.ui.lblCostMemory.text()
    dialog.close()


def test_a_lid_doubles_the_panels_and_says_why(window):
    """Spec 04 section 2.1: a lid disables symmetry, which is not obvious.

    The number is what matters. A user who turns the lid on because it sounds
    safe has silently traded the symmetry speedup away, and the only honest
    way to say so is the panel count they will actually pay for.
    """
    mesh = window.library.mesh("design-mesh")
    assert mesh.is_xz_symmetric, "this test is about losing symmetry, so there has to be some"

    dialog = SolveDialog(window.library, mesh, window)
    assert str(2 * len(mesh.faces)) in dialog.ui.lblCostPanels.text()
    assert "symmetry is off" not in dialog.ui.lblCostPanels.text()

    dialog.ui.comboLid.setCurrentIndex(LID_BELOW)
    assert str(4 * len(mesh.faces)) in dialog.ui.lblCostPanels.text()
    assert "symmetry is off" in dialog.ui.lblCostPanels.text()
    assert dialog.ui.spinLidZ.isEnabled()
    dialog.close()


def test_the_auto_lid_says_when_no_lid_is_needed(window):
    """Spec 09 section E.2's NaN trap, surfaced as the sentence it means."""
    dialog = SolveDialog(window.library, window.library.mesh("design-mesh"), window)
    # Long periods are low frequencies, and that is where arctanh leaves its
    # domain -- physically, where there are no irregular frequencies to
    # remove at all. The trap is that the formula returns NaN rather than
    # saying so, and a NaN fed to generate_lid produces a lid at an
    # undefined depth and no error.
    dialog.ui.spinPeriodFrom.setValue(20.0)
    dialog.ui.spinPeriodTo.setValue(20.0)
    dialog.ui.comboLid.setCurrentIndex(LID_AUTO)

    assert dialog.lid_z() is None
    assert "no irregular frequencies" in dialog.ui.lblLidInfo.text()
    dialog.close()


def test_the_auto_lid_gives_a_depth_where_it_has_one(window):
    dialog = SolveDialog(window.library, window.library.mesh("design-mesh"), window)
    dialog.ui.spinPeriodFrom.setValue(2.0)
    dialog.ui.spinPeriodTo.setValue(2.0)
    dialog.ui.comboLid.setCurrentIndex(LID_AUTO)

    z = dialog.lid_z()
    assert z is not None and z < 0.0
    assert "z =" in dialog.ui.lblLidInfo.text()
    dialog.close()


def test_the_solve_dialog_warns_below_the_mesh_resolution_limit(window):
    dialog = SolveDialog(window.library, window.library.mesh("design-mesh"), window)
    dialog.ui.spinPeriodFrom.setValue(0.5)
    dialog.ui.spinPeriodTo.setValue(0.5)

    assert "below it" in dialog.ui.lblCostReliable.text()
    dialog.close()


# --------------------------------------------------------------------------
# Spec 06 section 7 item 5: cancelling leaves the library byte-identical
# --------------------------------------------------------------------------


def test_a_real_solve_through_the_dialog_stores_a_result(window, qapp):
    """The real path, end to end: the dialog drives the pool and stores.

    Two frequencies on the coarse box, which is a couple of seconds. Slow
    enough to be a real Capytaine run in real worker processes, small enough to
    run every time.
    """
    dialog = SolveDialog(window.library, window.library.mesh("ballast-mesh"), window)
    dialog.ui.spinPeriodFrom.setValue(8.0)
    dialog.ui.spinPeriodTo.setValue(12.0)
    dialog.ui.spinPeriodStep.setValue(4.0)
    dialog.ui.spinWorkers.setValue(2)

    stored = []
    dialog.resultStored.connect(stored.append)
    dialog._start()

    assert pump(qapp, lambda: dialog.ui.btnStart.isEnabled()), "the solve never returned"
    assert stored, f"nothing was stored: {dialog.ui.lblProgress.text()}"
    result = window.library.result(stored[0])

    assert len(result.omegas) == 2
    assert sorted(period_from_omega(w) for w in result.omegas) == pytest.approx([8.0, 12.0])
    assert result.solver_name == "Capytaine"
    assert result.created_at, "the solve date is what tells two competing results apart"
    dialog.close()


def test_stopping_a_solve_keeps_what_was_solved_without_asking(window, qapp, monkeypatch):
    """DECIDED: a graceful stop keeps, and does not ask.

    Whether a shorter grid is worth having is not answerable from the solve
    screen -- it is answered by looking at the curves in Inspect, which needs
    the result to exist. Deleting an unwanted one is a click; re-solving a
    discarded one is minutes.

    The question is stubbed to *fail loudly* rather than to answer, so a
    regression that starts asking again shows up as an error and not as a
    silently different default.
    """

    def must_not_ask(self, outcome):
        raise AssertionError("a graceful stop must not ask whether to keep")

    monkeypatch.setattr(SolveDialog, "_keep_partial", must_not_ask)

    dialog = SolveDialog(window.library, window.library.mesh("ballast-mesh"), window)
    dialog.ui.spinPeriodFrom.setValue(6.0)
    dialog.ui.spinPeriodTo.setValue(18.0)
    dialog.ui.spinPeriodStep.setValue(3.0)
    dialog.ui.spinWorkers.setValue(1)

    stored = []
    dialog.resultStored.connect(stored.append)
    dialog._start()

    assert pump(qapp, lambda: dialog.ui.progressBar.value() >= 1), "no frequency ever completed"
    dialog._stop()

    assert pump(qapp, lambda: dialog.ui.btnStart.isEnabled()), "the solve never returned"
    assert stored, "a stopped run must keep what it solved"

    result = window.library.result(stored[0])
    assert 0 < len(result.omegas) < 5, f"expected a short grid, got {len(result.omegas)}"
    assert result.truncated, "a run that was cut short has to say so"
    assert result.label == "", "the label belongs to whoever names this result, not to the solver"
    dialog.close()


def test_terminating_a_solve_asks_and_discarding_leaves_the_library_byte_identical(
    window, qapp, monkeypatch, path
):
    """Item 5, under the decided rule: kill is the tier that asks.

    Someone reaching for the emergency handle usually wants out, so this is
    where the question belongs -- and Discard means *untouched*, asserted on
    the **bytes of the file**. A write that was rolled back, or one that left a
    page dirty, is exactly the failure a result count would miss.
    """
    asked = []

    def decline(self, outcome):
        asked.append(outcome)
        return False

    monkeypatch.setattr(SolveDialog, "_keep_partial", decline)
    before = path.read_bytes()

    dialog = SolveDialog(window.library, window.library.mesh("ballast-mesh"), window)
    dialog.ui.spinPeriodFrom.setValue(6.0)
    dialog.ui.spinPeriodTo.setValue(18.0)
    dialog.ui.spinPeriodStep.setValue(3.0)
    dialog.ui.spinWorkers.setValue(1)

    stored = []
    dialog.resultStored.connect(stored.append)
    dialog._start()

    # Kill once the first frequency has landed, so there is something to offer
    # and the answer actually matters. Driven off the progress bar rather than
    # the thread's signals: connecting to those after start() races a thread
    # that is already running.
    assert pump(qapp, lambda: dialog.ui.progressBar.value() >= 1), "no frequency ever completed"
    dialog._kill()

    assert pump(qapp, lambda: dialog.ui.btnStart.isEnabled()), "the solve never returned"
    assert asked, "a terminated run must ask before discarding minutes of work"
    assert asked[0].killed and asked[0].solved, "it was asked about a run that had produced something"
    assert not stored, "declining must store nothing"
    assert "Discarded" in dialog.ui.lblProgress.text()
    assert path.read_bytes() == before, "the library file changed after a discarded solve"
    dialog.close()


def test_keeping_a_terminated_solve_stores_the_shorter_grid(window, qapp, monkeypatch):
    """The other answer, and the reason the question is worth asking.

    A terminated run still has complete coverage of every frequency that came
    back, so what it produced is a valid result over a shorter grid rather than
    a ragged one -- and it says which it was in its label, human text that
    nothing parses (ADR-4).
    """
    monkeypatch.setattr(SolveDialog, "_keep_partial", lambda self, outcome: True)

    dialog = SolveDialog(window.library, window.library.mesh("ballast-mesh"), window)
    dialog.ui.spinPeriodFrom.setValue(6.0)
    dialog.ui.spinPeriodTo.setValue(18.0)
    dialog.ui.spinPeriodStep.setValue(3.0)
    dialog.ui.spinWorkers.setValue(1)

    stored = []
    dialog.resultStored.connect(stored.append)
    dialog._start()

    assert pump(qapp, lambda: dialog.ui.progressBar.value() >= 1), "no frequency ever completed"
    dialog._kill()

    assert pump(qapp, lambda: dialog.ui.btnStart.isEnabled()), "the solve never returned"
    assert stored, "nothing was stored"

    result = window.library.result(stored[0])
    assert 0 < len(result.omegas) < 5, f"expected a short grid, got {len(result.omegas)}"
    assert result.truncated
    dialog.close()


def test_a_complete_solve_is_never_questioned(window, qapp, monkeypatch):
    """Neither tier applies when nothing was cut short."""

    def must_not_ask(self, outcome):
        raise AssertionError("a complete solve must not ask whether to keep")

    monkeypatch.setattr(SolveDialog, "_keep_partial", must_not_ask)

    dialog = SolveDialog(window.library, window.library.mesh("ballast-mesh"), window)
    dialog.ui.spinPeriodFrom.setValue(10.0)
    dialog.ui.spinPeriodTo.setValue(14.0)
    dialog.ui.spinPeriodStep.setValue(4.0)
    dialog.ui.spinWorkers.setValue(2)

    stored = []
    dialog.resultStored.connect(stored.append)
    dialog._start()

    assert pump(qapp, lambda: dialog.ui.btnStart.isEnabled()), "the solve never returned"
    assert stored
    assert not window.library.result(stored[0]).truncated, "nothing was cut short"
    dialog.close()


def test_the_solve_dialog_reports_a_frequency_that_failed(window):
    """Spec 06 section 6.6: a failed frequency must not vanish from the grid.

    The **outcome** is synthetic here, and deliberately so. The only frequency
    Capytaine genuinely refuses is zero, and the period spinbox cannot express
    it -- an infinite period. A real worker failure is exercised in
    ``test_pool.py``, which is where the pool lives; what this covers is the
    part only the dialog has, which is whether a reported failure reaches the
    screen or is quietly dropped between the pool and the user.
    """
    from pylot_bem.pool import SolveOutcome

    dialog = SolveDialog(window.library, window.library.mesh("ballast-mesh"), window)
    requested = (0.5, 0.6)
    dialog._settings = dialog.settings()
    dialog._fill_chips(requested)

    outcome = SolveOutcome(
        requested=requested,
        solved=(0.5,),
        failed={0.6: "SolverError: diffraction problems at zero frequency are not defined"},
        elapsed=1.0,
        dataset=None,
    )
    dialog._progressed(outcome)
    dialog._completed(outcome)

    chips = [dialog.ui.listGrid.item(i).text() for i in range(dialog.ui.listGrid.count())]
    assert any(chip.startswith("✗") for chip in chips), chips
    assert any(chip.startswith("✓") for chip in chips), chips
    log = dialog.ui.textLog.toPlainText()
    assert "FAILED" in log
    assert "not defined" in log, "the reason must reach the user, not only the fact"
    dialog.close()


# --------------------------------------------------------------------------
# Nothing derived is editable
# --------------------------------------------------------------------------


def test_derived_readouts_are_labels_and_not_inputs(window):
    """Spec 09 cross-cutting rule 1, checked structurally.

    A mockup that shows a derived value in an editable-looking box eventually
    becomes an implementation where it is editable. These are QLabel, and a
    QLabel has no setter a user can reach.
    """
    from PySide6.QtWidgets import QLabel

    window.tree.select_ids(["design"])
    for name in ("lblApplicationPoint", "lblSymmetry", "lblProbeZ", "lblZOrigin", "lblHeel", "lblTrim"):
        widget = getattr(window.condition_pane.ui, name)
        assert isinstance(widget, QLabel), f"{name} is a {type(widget).__name__}, which a user can type into"


def test_the_library_pane_offers_no_way_to_replace_the_base_shape(window):
    """Immutable once anything exists (spec 02 section 1), so there is no button."""
    names = [name for name in dir(window.library_pane.ui) if name.startswith("btn")]
    assert not any("base" in name.lower() or "import" in name.lower() for name in names), names


# --------------------------------------------------------------------------
# Opening and closing
# --------------------------------------------------------------------------


def test_the_window_starts_with_nothing_open_and_says_so(qapp, isolated_settings):
    main = MainWindow(settings=isolated_settings)
    assert main.library is None
    assert not main.tree.isEnabled()
    assert "No library open" in main.statusBar().currentMessage()
    main.close()


def test_opening_something_that_is_not_a_library_is_reported(qapp, tmp_path, monkeypatch, isolated_settings):
    seen = []
    monkeypatch.setattr(MainWindow, "_problem", lambda self, title, exc: seen.append((title, str(exc))))

    rubbish = tmp_path / "notalibrary.pylot"
    rubbish.write_bytes(b"this is not a database")

    main = MainWindow(settings=isolated_settings)
    main.open_path(rubbish)

    assert seen, "opening a non-library said nothing"
    assert main.library is None
    main.close()


def test_closing_a_library_releases_it(window, path):
    window.close_library()

    assert window.library is None
    assert window.tree.topLevelItemCount() == 0
    assert not window.tabs.isEnabled()
    # The file is no longer held, so it can be reopened.
    with Library.open(path) as reopened:
        assert len(reopened.results()) == 4


# --------------------------------------------------------------------------
# What a condition will and will not let you change
# --------------------------------------------------------------------------


def test_a_conditions_label_can_be_changed(window):
    """The only part of one that can. Nothing parses a label (ADR-4)."""
    window.tree.select_ids(["design"])
    window.condition_pane.ui.editLabel.setText("Design draft, summer")
    window.condition_pane.ui.btnApplyLabel.click()

    assert window.library.condition("design").label == "Design draft, summer"
    # And it really reached storage, not just the widget.
    with Library.open(window.library.path) as reopened:
        assert reopened.condition("design").label == "Design draft, summer"


def test_renaming_a_condition_changes_nothing_else(window):
    """Which is the whole reason it is allowed."""
    before = window.library.condition("design")
    results_before = {r.id: r.omegas.tolist() for r in window.library.results()}

    window.library.set_condition_label("design", "something else")
    after = window.library.condition("design")

    assert after.z_origin == before.z_origin
    assert after.heel == before.heel and after.trim == before.trim
    assert np.array_equal(after.application_point, before.application_point)
    assert np.array_equal(after.probes, before.probes)
    assert {r.id: r.omegas.tolist() for r in window.library.results()} == results_before


def test_there_is_no_widget_for_z_origin_heel_or_trim(window):
    """Editing those would invalidate every mesh and result below, so the pane
    offers no way to try: they are QLabel, and a QLabel has no setter a user
    can reach. Spec 09's first cross-cutting rule, at the place it matters most.
    """
    from PySide6.QtWidgets import QLabel

    window.tree.select_ids(["design"])
    for name in ("lblZOrigin", "lblHeel", "lblTrim"):
        assert isinstance(getattr(window.condition_pane.ui, name), QLabel)

    editable = [name for name in dir(window.condition_pane.ui) if name.startswith(("edit", "spin"))]
    assert editable == ["editLabel"], f"the pane can edit {editable}; only the label may be editable"


# --------------------------------------------------------------------------
# OK and Cancel actually work
# --------------------------------------------------------------------------
#
# A QDialogButtonBox emits `accepted` and `rejected`; on its own it does not
# close the dialog. Qt Designer normally writes that connection into the .ui
# file, so a hand-written .ui has buttons that silently do nothing -- and every
# other test here calls `values()` directly and never presses a button, so the
# whole suite was green while New condition and Create mesh could not be
# confirmed or cancelled at all. Reported from the running application.


def button_box_dialogs(window):
    """Every dialog with an OK/Cancel box, ready to press."""
    from pylot_bem.app.dialogs import DeleteFrequenciesDialog, NewLibraryDialog

    return {
        "new library": NewLibraryDialog(window),
        "new condition": NewConditionDialog(window.library, window),
        "create mesh": CreateMeshDialog(window.library, window.library.condition("design"), window),
        "delete frequencies": DeleteFrequenciesDialog(
            window.library, window.library.result("design-fine"), window
        ),
    }


def test_ok_accepts_every_dialog_that_has_one(window):
    from PySide6.QtWidgets import QDialog

    for name, dialog in button_box_dialogs(window).items():
        dialog.show()
        ok = dialog.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok)
        assert ok is not None, f"{name} has no OK button"
        ok.setEnabled(True)  # some are disabled until their input is valid
        ok.click()

        assert dialog.result() == QDialog.DialogCode.Accepted, f"OK does nothing in {name}"
        assert not dialog.isVisible(), f"{name} stayed open after OK"
        dialog.close()


def test_cancel_closes_every_dialog_that_has_one(window):
    """Asserted on the dialog *closing*, not on its result code.

    `QDialog.Rejected` is 0, which is also the result of a dialog nobody has
    answered -- so a Cancel button wired to nothing satisfies a result check
    perfectly. The dialog is shown first and the assertion is that it is no
    longer visible, which only `reject()` can bring about.
    """
    from PySide6.QtWidgets import QDialog

    for name, dialog in button_box_dialogs(window).items():
        dialog.show()
        assert dialog.isVisible(), f"{name} did not open, so closing it proves nothing"

        cancel = dialog.ui.buttonBox.button(QDialogButtonBox.StandardButton.Cancel)
        assert cancel is not None, f"{name} has no Cancel button"
        cancel.click()

        assert not dialog.isVisible(), f"Cancel does nothing in {name}"
        assert dialog.result() == QDialog.DialogCode.Rejected
        dialog.close()


def test_creating_a_condition_through_the_dialog_stores_it(window, monkeypatch):
    """End to end through the button, not around it.

    The bug was between the button and the code, so a test that calls
    `values()` itself would still have passed.
    """
    created = {}

    class Confirmed(NewConditionDialog):
        def exec(self):
            self.ui.spinZOrigin.setValue(-7.5)
            self.ui.editLabel.setText("Half load")
            created["values"] = self.values()
            self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok).click()
            return self.result()

    monkeypatch.setattr("pylot_bem.app.window.NewConditionDialog", Confirmed)
    before = {c.id for c in window.library.conditions()}
    window.new_condition()

    new = {c.id for c in window.library.conditions()} - before
    assert len(new) == 1, "the condition was not created"
    condition = window.library.condition(new.pop())
    assert condition.z_origin == pytest.approx(-7.5)
    assert condition.label == "Half load"
    assert condition.id in window.tree.selected_ids(), "the new condition is selected in the tree"


def test_cancelling_the_condition_dialog_creates_nothing(window, monkeypatch):
    from PySide6.QtWidgets import QDialog

    class Cancelled(NewConditionDialog):
        def exec(self):
            self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Cancel).click()
            return self.result()

    monkeypatch.setattr("pylot_bem.app.window.NewConditionDialog", Cancelled)
    before = {c.id for c in window.library.conditions()}
    window.new_condition()

    assert {c.id for c in window.library.conditions()} == before
    assert Cancelled(window.library, window).exec() == QDialog.DialogCode.Rejected


def test_creating_a_mesh_through_the_dialog_stores_it(window, monkeypatch):
    class Confirmed(CreateMeshDialog):
        def exec(self):
            self.ui.spinPct.setValue(25.0)
            self.ui.spinIterations.setValue(4)
            self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok).click()
            return self.result()

    monkeypatch.setattr("pylot_bem.app.window.CreateMeshDialog", Confirmed)
    before = {m.id for m in window.library.meshes()}
    window.create_mesh("loaded")

    new = {m.id for m in window.library.meshes()} - before
    assert len(new) == 1, "the mesh was not created"
    mesh = window.library.mesh(new.pop())
    assert mesh.condition_id == "loaded"
    assert mesh.pct == pytest.approx(25.0)
    assert not mesh.is_xz_symmetric, "loaded is heeled, so its mesh is a full vessel"


def test_cancelling_the_mesh_dialog_creates_nothing(window, monkeypatch):
    class Cancelled(CreateMeshDialog):
        def exec(self):
            self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Cancel).click()
            return self.result()

    monkeypatch.setattr("pylot_bem.app.window.CreateMeshDialog", Cancelled)
    before = {m.id for m in window.library.meshes()}
    window.create_mesh("loaded")

    assert {m.id for m in window.library.meshes()} == before


# --------------------------------------------------------------------------
# Naming things
# --------------------------------------------------------------------------
#
# Ids are opaque -- nothing parses one (ADR-4) -- which is exactly what makes a
# hand-typed one safe. What it costs is permanence: unlike a label an id cannot
# be corrected afterwards, because meshes and results point at it.


def test_a_typed_id_is_used_for_a_new_mesh(window, monkeypatch):
    class Named(CreateMeshDialog):
        def exec(self):
            self.ui.editId.setText("loaded-coarse")
            self.ui.spinPct.setValue(25.0)
            self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok).click()
            return self.result()

    monkeypatch.setattr("pylot_bem.app.window.CreateMeshDialog", Named)
    window.create_mesh("loaded")

    assert window.library.mesh("loaded-coarse").condition_id == "loaded"
    assert "loaded-coarse" in [row[2] for row in tree_rows(window)]


def test_a_blank_id_still_generates_one(window, monkeypatch):
    class Unnamed(CreateMeshDialog):
        def exec(self):
            self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok).click()
            return self.result()

    monkeypatch.setattr("pylot_bem.app.window.CreateMeshDialog", Unnamed)
    before = {m.id for m in window.library.meshes()}
    window.create_mesh("loaded")

    new = {m.id for m in window.library.meshes()} - before
    assert len(new) == 1
    assert len(new.pop()) == 32, "a generated id is a uuid4 hex"


def test_a_duplicate_mesh_id_is_refused_before_it_is_tried(window):
    """Spec 09 rule 2: the refusal states its reason.

    Storage would refuse the collision anyway, but as an exception after the
    regrid has already run — which on a real hull is a wait for nothing.
    """
    dialog = CreateMeshDialog(window.library, window.library.condition("loaded"), window)
    ok = dialog.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok)
    assert ok.isEnabled()

    dialog.ui.editId.setText("design-mesh")
    assert not ok.isEnabled()
    assert "already used" in dialog.ui.lblIdProblem.text()
    assert dialog.values()["mesh_id"] is None, "a refused id must not reach the library"

    dialog.ui.editId.setText("design-mesh-2")
    assert ok.isEnabled()
    assert dialog.ui.lblIdProblem.text() == ""
    assert dialog.values()["mesh_id"] == "design-mesh-2"
    dialog.close()


def test_a_typed_id_is_used_for_a_new_condition(window, monkeypatch):
    class Named(NewConditionDialog):
        def exec(self):
            self.ui.spinZOrigin.setValue(-9.0)
            self.ui.editId.setText("half-load")
            self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok).click()
            return self.result()

    monkeypatch.setattr("pylot_bem.app.window.NewConditionDialog", Named)
    window.new_condition()

    assert window.library.condition("half-load").z_origin == pytest.approx(-9.0)


def test_a_duplicate_condition_id_is_refused_with_its_reason(window):
    dialog = NewConditionDialog(window.library, window)
    dialog.ui.spinZOrigin.setValue(-9.0)
    ok = dialog.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok)
    assert ok.isEnabled()

    dialog.ui.editId.setText("design")
    assert not ok.isEnabled()
    assert "already used" in dialog.ui.lblProblem.text()
    dialog.close()


def test_an_id_is_stripped_of_surrounding_space(window):
    dialog = CreateMeshDialog(window.library, window.library.condition("loaded"), window)
    dialog.ui.editId.setText("  spaced  ")

    assert dialog.values()["mesh_id"] == "spaced"
    dialog.close()


def test_a_typed_result_id_is_used(window, qapp):
    dialog = SolveDialog(window.library, window.library.mesh("ballast-mesh"), window)
    dialog.ui.editId.setText("ballast-fine")
    dialog.ui.spinPeriodFrom.setValue(10.0)
    dialog.ui.spinPeriodTo.setValue(14.0)
    dialog.ui.spinPeriodStep.setValue(4.0)
    dialog.ui.spinWorkers.setValue(2)

    stored = []
    dialog.resultStored.connect(stored.append)
    dialog._start()

    assert pump(qapp, lambda: dialog.ui.btnStart.isEnabled()), "the solve never returned"
    assert stored == ["ballast-fine"]
    assert window.library.result("ballast-fine").mesh_id == "ballast-mesh"
    dialog.close()


def test_a_duplicate_result_id_refuses_start(window):
    """Refused before the solve, not after — a solve is minutes."""
    dialog = SolveDialog(window.library, window.library.mesh("ballast-mesh"), window)
    assert dialog.ui.btnStart.isEnabled()

    dialog.ui.editId.setText("design-fine")
    assert not dialog.ui.btnStart.isEnabled()
    assert "already used" in dialog.ui.lblIdProblem.text()

    dialog.ui.editId.setText("something-else")
    assert dialog.ui.btnStart.isEnabled()
    dialog.close()


# --------------------------------------------------------------------------
# Wave directions follow the mesh
# --------------------------------------------------------------------------


def test_a_symmetric_mesh_defaults_to_half_the_circle(window):
    """Solving past 180 on a symmetric hull computes numbers already known.

    The port half is the mirror image and is filled in on delivery
    (spec 04 §8), so solving it doubles the run for nothing.
    """
    mesh = window.library.mesh("design-mesh")
    assert mesh.is_xz_symmetric

    dialog = SolveDialog(window.library, mesh, window)
    assert dialog.ui.spinDirTo.value() == pytest.approx(180.0)
    assert dialog.directions() == pytest.approx([0.0, 45.0, 90.0, 135.0, 180.0])
    assert "mirror image" in dialog.ui.lblDirList.text()
    dialog.close()


def test_an_asymmetric_mesh_defaults_to_the_whole_circle(window, monkeypatch):
    """A heeled condition has no port/starboard symmetry to exploit."""

    class Full(CreateMeshDialog):
        def exec(self):
            self.ui.editId.setText("loaded-mesh")
            self.ui.spinPct.setValue(25.0)
            self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok).click()
            return self.result()

    monkeypatch.setattr("pylot_bem.app.window.CreateMeshDialog", Full)
    window.create_mesh("loaded")

    mesh = window.library.mesh("loaded-mesh")
    assert not mesh.is_xz_symmetric, "loaded is heeled, so there is no symmetry"

    dialog = SolveDialog(window.library, mesh, window)
    assert dialog.ui.spinDirTo.value() == pytest.approx(360.0)
    assert "not symmetric" in dialog.ui.lblDirList.text()
    dialog.close()


def test_the_wrap_around_direction_is_dropped(window, monkeypatch):
    """0 and 360 are the same heading.

    Solving both costs a full set of problems for a duplicate column, and
    leaves the stored result with two identical directions.
    """

    class Full(CreateMeshDialog):
        def exec(self):
            self.ui.editId.setText("loaded-mesh")
            self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok).click()
            return self.result()

    monkeypatch.setattr("pylot_bem.app.window.CreateMeshDialog", Full)
    window.create_mesh("loaded")

    dialog = SolveDialog(window.library, window.library.mesh("loaded-mesh"), window)
    dialog.ui.spinDirFrom.setValue(0.0)
    dialog.ui.spinDirTo.setValue(360.0)
    dialog.ui.spinDirStep.setValue(45.0)

    assert dialog.directions() == pytest.approx([0, 45, 90, 135, 180, 225, 270, 315])
    assert 360.0 not in dialog.directions()
    dialog.close()


def test_a_half_open_direction_range_keeps_its_endpoint(window):
    """Only a grid that comes back to where it started loses a point."""
    dialog = SolveDialog(window.library, window.library.mesh("design-mesh"), window)
    dialog.ui.spinDirFrom.setValue(0.0)
    dialog.ui.spinDirTo.setValue(180.0)
    dialog.ui.spinDirStep.setValue(45.0)

    assert dialog.directions()[-1] == pytest.approx(180.0), "180 is not a duplicate of 0"
    dialog.close()


def test_a_symmetric_mesh_solved_past_180_says_it_is_redundant(window):
    """Refusing would be wrong — it is the user's call and it is not incorrect,
    merely wasteful. Saying so is not.
    """
    dialog = SolveDialog(window.library, window.library.mesh("design-mesh"), window)
    dialog.ui.spinDirTo.setValue(360.0)

    assert "redundant" in dialog.ui.lblDirList.text()
    dialog.close()


# --------------------------------------------------------------------------
# The root shows the base shape; results can be renamed
# --------------------------------------------------------------------------


def test_selecting_the_library_draws_the_base_shape(window):
    """The one level with no condition, so no water and no calculation mesh.

    Worth having anyway: it is where the hull's own normals can be checked
    before anything is built on it.
    """
    window.tree.select_ids(["design"])
    assert "waterplane" in window.viewport._actors

    window.tree.select_ids(["library"])
    assert set(window.viewport._actors) == {"base"}, "vessel-local geometry, so no waterplane"

    bounds = window.viewport._actors["base"].GetBounds()
    lo, _hi = window.library.base_shape.bounds
    assert bounds[4] == pytest.approx(lo[2], abs=1e-6), "drawn vessel-local, not placed at a condition"


def test_a_result_can_be_renamed_and_the_tree_follows(window):
    window.tree.select_ids(["design-fine"])
    window.result_pane.ui.editLabel.setText("fine grid, no lid")
    window.result_pane.ui.btnApplyLabel.click()

    assert window.library.result("design-fine").label == "fine grid, no lid"
    labels = []

    def walk(item):
        labels.append(item.text(0))
        for i in range(item.childCount()):
            walk(item.child(i))

    walk(window.tree.topLevelItem(0))
    assert any("fine grid, no lid" in text for text in labels), labels


def test_renaming_a_result_changes_nothing_it_records(window):
    """A label is display only, so it cannot invalidate what was computed."""
    before = window.library.result("design-fine")
    window.library.set_result_label("design-fine", "renamed")
    after = window.library.result("design-fine")

    assert np.array_equal(after.omegas, before.omegas)
    assert np.array_equal(after.wave_directions, before.wave_directions)
    assert (after.mesh_id, after.condition_id) == (before.mesh_id, before.condition_id)
    assert after.created_at == before.created_at
    assert after.truncated == before.truncated


def test_a_renamed_result_still_shows_its_id(window):
    """The id is what every other screen and every finding refers to, so the
    pane must keep showing it -- a name that hides the handle is worse than no
    name.
    """
    window.library.set_result_label("design-fine", "fine grid")
    window.tree.select_ids(["design-fine"])

    assert "design-fine" in window.result_pane.ui.lblId.text()
    assert window.result_pane.ui.editLabel.text() == "fine grid"


def test_truncation_is_a_field_and_not_the_label(window):
    """Spec 09 §G. The label cannot be both the human name and the record that
    a run was cut short, and renaming must not erase the second.
    """
    window.library.set_result_label("design-fine", "whatever I like")
    window.tree.select_ids(["design-fine"])

    assert window.library.result("design-fine").truncated is False
    assert window.result_pane.ui.lblNote.text() == ""

    columns = window.results_tab.COLUMNS
    assert "Truncated" in columns
    assert "Label" in columns


# --------------------------------------------------------------------------
# Merging: combine where nothing is lost, trim where something would be
# --------------------------------------------------------------------------
#
# Which of the two happens is decided by the results, not by a setting.
# Whether folding two results into one throws information away is a fact about
# them: if they record the same mesh, the same settings and the same wave
# directions, the combined result records exactly what they did.


def merge_dialog(window, ids):
    from pylot_bem.app.merge import MergeDialog

    return MergeDialog(window.library, [window.library.result(i) for i in ids], window)


def lidded_twin(window, result_id="lidded", omegas=(0.6, 0.8)):
    """A result on the same mesh that differs only in its lid.

    Enough to make combining lossy — a single result records one lid — so the
    dialog must trim instead. Built by re-storing an existing dataset rather
    than solving: what is under test is the rule, not the physics.
    """
    library = window.library
    dataset = library.result_dataset("design-fine").sel(omega=[0.5, 0.6]).assign_coords(omega=list(omegas))
    return library.add_result(
        mesh_id="design-mesh",
        data=dataset,
        water_depth=float("inf"),
        lid_mode="free_surface",
        lid_z=0.0,
        result_id=result_id,
    )


# -- combine ---------------------------------------------------------------


def test_matching_results_are_combined_into_one(window, monkeypatch):
    """design-fine and design-coarse agree on everything but their grids.

    So one result covering 0.5-0.7 records exactly what the two of them did,
    and the clutter goes away with no information lost.
    """
    from pylot_bem.app.merge import MergeDialog

    dialog = merge_dialog(window, ["design-fine", "design-coarse"])
    assert dialog.combining, "same mesh, same settings, same directions"
    assert dialog.union() == pytest.approx([0.5, 0.6, 0.7])
    dialog.close()

    class Chosen(MergeDialog):
        def exec(self):
            self.ui.comboPrimary.setCurrentIndex(self.ui.comboPrimary.findData("design-fine"))
            self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok).click()
            return self.result()

    monkeypatch.setattr("pylot_bem.app.merge.MergeDialog", Chosen)
    before = {r.id for r in window.library.results()}
    window.merge_results(["design-fine", "design-coarse"])

    remaining = {r.id for r in window.library.results()}
    assert "design-fine" not in remaining and "design-coarse" not in remaining
    combined = window.library.result((remaining - before).pop())
    assert sorted(combined.omegas) == pytest.approx([0.5, 0.6, 0.7])
    assert combined.mesh_id == "design-mesh"
    assert combined.condition_id == "design"

    design = next(v for v in window.library.databases() if v.key.condition_id == "design")
    assert not design.conflicts, "one result cannot contest itself"


def test_the_combined_result_keeps_the_settings_they_agreed_on(window):
    library = window.library
    before = library.result("design-fine")
    combined = library.combine_results(["design-fine", "design-coarse"], primary="design-fine")

    assert combined.mesh_id == before.mesh_id
    assert combined.water_depth == before.water_depth
    assert combined.g == before.g
    assert combined.forward_speed == before.forward_speed
    assert combined.lid_mode == before.lid_mode
    assert np.array_equal(combined.wave_directions, before.wave_directions)
    assert combined.solver_name == before.solver_name


def test_the_primary_supplies_a_frequency_they_both_cover(window):
    """They agree on every setting, so the numbers should match — but they are
    separate runs and Capytaine is not bit-reproducible in finite depth, so
    which one supplies 0.6 is still a choice.
    """
    library = window.library
    fine = library.result_dataset("design-fine").sel(omega=0.6)["added_mass"].values.copy()

    combined = library.combine_results(["design-fine", "design-coarse"], primary="design-fine")
    merged = library.result_dataset(combined.id).sel(omega=0.6)["added_mass"].values

    assert np.array_equal(merged, fine)


def test_combining_is_refused_when_anything_differs(window):
    """The rule lives in storage, so a caller cannot talk its way past it."""
    lidded_twin(window)

    with pytest.raises(LibraryError, match="cannot be combined"):
        window.library.combine_results(["design-fine", "lidded"], primary="design-fine")

    # A different condition means a different mesh, which is the first thing
    # combination_differences reports.
    with pytest.raises(LibraryError, match="the mesh solved"):
        window.library.combine_results(["design-fine", "ballast-run"], primary="design-fine")


def test_a_combined_result_is_truncated_if_any_contributor_was(window):
    library = window.library
    library.add_result(
        mesh_id="design-mesh",
        data=library.result_dataset("design-fine").sel(omega=[0.5]).assign_coords(omega=[1.1]),
        water_depth=float("inf"),
        result_id="short",
        truncated=True,
    )
    combined = library.combine_results(["design-fine", "short"], primary="design-fine")

    assert combined.truncated, "the grid is still short of what was asked for"


def test_the_combined_result_is_written_before_the_originals_go(window, monkeypatch):
    """Interrupted between the two, a library keeps a redundant result — a
    conflict, visible and fixable — rather than a hole.
    """
    library = window.library
    seen = []
    real_delete = type(library).delete_result

    def watched(self, result_id):
        seen.append({r.id for r in self.results()})
        return real_delete(self, result_id)

    monkeypatch.setattr(type(library), "delete_result", watched)
    library.combine_results(["design-fine", "design-coarse"], primary="design-fine")

    assert seen, "nothing was deleted"
    assert len(seen[0]) == 5, "the combined result existed before the first deletion"


# -- trim ------------------------------------------------------------------


def test_results_that_differ_are_trimmed_instead(window, monkeypatch):
    """A single result records one lid, so these cannot be folded together."""
    from pylot_bem.app.merge import MergeDialog

    lidded_twin(window)
    dialog = merge_dialog(window, ["design-fine", "lidded"])

    assert not dialog.combining
    assert dialog.plan() == {"lidded": pytest.approx([0.6])}, "only the contested frequency"
    assert "differ in how they were computed" in dialog.ui.lblHeading.text()
    dialog.close()

    class Chosen(MergeDialog):
        def exec(self):
            self.ui.comboPrimary.setCurrentIndex(self.ui.comboPrimary.findData("design-fine"))
            self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok).click()
            return self.result()

    monkeypatch.setattr("pylot_bem.app.merge.MergeDialog", Chosen)
    window.merge_results(["design-fine", "lidded"])

    assert sorted(window.library.result("design-fine").omegas) == pytest.approx([0.5, 0.6])
    assert sorted(window.library.result("lidded").omegas) == pytest.approx([0.8])
    assert window.library.result("lidded").lid_mode == "free_surface", "provenance survives a trim"


def test_the_other_primary_trims_the_other_way(window):
    """Otherwise the test above could pass against a fixed rule."""
    lidded_twin(window)
    dialog = merge_dialog(window, ["design-fine", "lidded"])

    dialog.ui.comboPrimary.setCurrentIndex(dialog.ui.comboPrimary.findData("design-fine"))
    assert dialog.plan() == {"lidded": pytest.approx([0.6])}

    dialog.ui.comboPrimary.setCurrentIndex(dialog.ui.comboPrimary.findData("lidded"))
    assert dialog.plan() == {"design-fine": pytest.approx([0.6])}
    dialog.close()


def test_a_trim_creates_and_destroys_nothing(window, monkeypatch):
    from pylot_bem.app.merge import MergeDialog

    lidded_twin(window)
    before = {r.id for r in window.library.results()}

    class Chosen(MergeDialog):
        def exec(self):
            self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok).click()
            return self.result()

    monkeypatch.setattr("pylot_bem.app.merge.MergeDialog", Chosen)
    window.merge_results(["design-fine", "lidded"])

    assert {r.id for r in window.library.results()} == before


# -- refusals --------------------------------------------------------------


def test_cancelling_a_merge_changes_nothing(window, monkeypatch):
    from pylot_bem.app.merge import MergeDialog

    class Cancelled(MergeDialog):
        def exec(self):
            self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Cancel).click()
            return self.result()

    monkeypatch.setattr("pylot_bem.app.merge.MergeDialog", Cancelled)
    before = {r.id: sorted(r.omegas) for r in window.library.results()}
    window.merge_results(["design-fine", "design-coarse"])

    assert {r.id: sorted(r.omegas) for r in window.library.results()} == before


def test_merging_across_databases_is_refused_with_its_reason(window):
    """Different conditions are different physical situations, so neither
    supersedes the other and there is nothing to resolve.
    """
    dialog = merge_dialog(window, ["design-fine", "ballast-run"])
    ok = dialog.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok)

    assert not ok.isEnabled()
    assert "different databases" in dialog.ui.lblHeading.text()
    assert dialog.plan() == {}
    dialog.close()


def test_results_that_neither_overlap_nor_match_have_nothing_to_do(window):
    """design-radiation carries no directions and no diffraction, so it cannot
    be combined; and it does not overlap, so there is nothing to trim either.
    """
    dialog = merge_dialog(window, ["design-fine", "design-radiation"])

    assert not dialog.combining
    assert dialog.plan() == {}
    assert not dialog.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
    dialog.close()


def test_a_disabled_merge_says_why_beside_the_button(window):
    """Spec 09 rule 2. Reported from the running application: OK was greyed
    out and the reason was in the heading or the outcome box depending on the
    case, which is two places a reader has to know to look.
    """
    across = merge_dialog(window, ["design-fine", "ballast-run"])
    assert not across.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
    assert "Cannot merge" in across.ui.lblFooterHint.text()
    assert "different databases" in across.ui.lblFooterHint.text()
    across.close()

    apart = merge_dialog(window, ["design-fine", "design-radiation"])
    assert not apart.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
    assert "Cannot merge" in apart.ui.lblFooterHint.text()
    assert "do not overlap" in apart.ui.lblFooterHint.text()
    apart.close()


def test_the_button_says_which_of_the_two_it_will_do(window):
    combining = merge_dialog(window, ["design-fine", "design-coarse"])
    assert combining.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok).text() == "Combine"
    assert "Nothing is lost" in combining.ui.lblOutcome.text()
    combining.close()

    lidded_twin(window)
    trimming = merge_dialog(window, ["design-fine", "lidded"])
    assert trimming.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok).text() == "Merge"
    assert "Removes 1 frequencies" in trimming.ui.lblOutcome.text()
    # design-coarse is not in this selection and still covers 0.6, so the
    # conflict is not fully resolved -- and the dialog says so rather than
    # claiming a clean database it cannot deliver.
    assert "still contested" in trimming.ui.lblOutcome.text()
    trimming.close()


def test_merge_is_offered_only_for_several_results_on_one_database(window):
    window.tree.select_ids(["design-fine", "design-coarse"])
    assert window.selection_pane.ui.btnMerge.isEnabled()

    window.tree.select_ids(["design-fine", "ballast-run"])
    assert not window.selection_pane.ui.btnMerge.isEnabled(), "different databases"


def test_the_context_menu_never_hands_merge_a_mesh(window):
    """A mixed ctrl-click selection used to leak the mesh id.

    ``selected`` filtered on the *clicked* node's kind, which is a constant, so
    every selected row came through whatever it was — and a mesh id looked up
    as a result raises.
    """
    window.tree.select_ids(["design-mesh", "design-fine"])
    kinds = {kind for kind, _ in window.tree.selected_nodes()}
    assert kinds == {"mesh", "result"}, "the fixture needs a genuinely mixed selection"

    results_only = [i for kind, i in window.tree.selected_nodes() if kind == "result"]
    assert results_only == ["design-fine"]

    before = {r.id: sorted(r.omegas) for r in window.library.results()}
    window.merge_results(window.tree.selected_ids())
    assert {r.id: sorted(r.omegas) for r in window.library.results()} == before


def test_every_dock_can_be_reopened_after_it_is_closed(window):
    """A dock's close button used to be one-way.

    Qt puts a close button on every dock and offers nothing that reopens one,
    so closing Properties or Data hid it for the life of the process — the
    panes kept working, they were simply unreachable. Asserted per dock, and
    the hidden state is asserted first so that a reopen which never had
    anything to undo cannot pass.
    """
    assert set(window.docks) == {"Library", "Properties", "Data"}

    for title, dock in window.docks.items():
        action = dock.toggleViewAction()
        assert action.text() == title

        dock.close()
        assert not dock.isVisible(), f"{title} did not close, so reopening it proves nothing"
        assert not action.isChecked(), "the menu entry disagrees with what is on screen"

        action.trigger()
        assert dock.isVisible(), f"{title} could not be reopened"
        assert action.isChecked()


def test_the_view_menu_offers_a_panel_toggle_for_each_dock(window):
    """The action has to be reachable, not merely to exist.

    ``toggleViewAction`` works whether or not anyone put it in a menu, so a
    test that only triggers it would pass with the menu missing entirely —
    which is the bug this is about.
    """
    view = window.menus["View"]
    assert [action.text() for action in window.menuBar().actions()] == ["&File", "&View", "&Help"]
    assert view.menuAction() in window.menuBar().actions(), "the View menu is not on the menu bar"

    panels = window.menus["Panels"]
    assert panels.menuAction() in view.actions(), "Panels is not under View"

    assert [action.text() for action in panels.actions()] == list(window.docks)
    for action in panels.actions():
        assert action.isCheckable()


# --------------------------------------------------------------------------
# Recent files
# --------------------------------------------------------------------------


def test_opening_a_library_adds_it_to_recent_files(window, path):
    """The ``window`` fixture already opened ``path`` once."""
    assert window._recent_files() == [str(path)]

    actions = window.recent_menu.actions()
    assert actions[0].text() == str(path)
    assert actions[0].isEnabled()


def test_recent_files_move_to_the_front_when_reopened(qapp, library_path, tmp_path, isolated_settings):
    first = tmp_path / "first.pylot"
    second = tmp_path / "second.pylot"
    shutil.copy(library_path, first)
    shutil.copy(library_path, second)

    main = MainWindow(settings=isolated_settings)
    main.open_path(first)
    main.open_path(second)
    assert main._recent_files() == [str(second), str(first)]

    main.open_path(first)
    assert main._recent_files() == [str(first), str(second)], "reopening moves it to the front, not a duplicate"
    main.close()


def test_recent_files_are_capped(qapp, isolated_settings):
    """Plain bookkeeping, fed strings directly rather than real libraries --
    none of ``MAX_RECENT_FILES`` plus a few need to exist on disk for what
    this checks: that the list does not grow without bound.
    """
    main = MainWindow(settings=isolated_settings)
    for i in range(main.MAX_RECENT_FILES + 3):
        main._remember_recent_file(f"library-{i}.pylot")

    recent = main._recent_files()
    assert len(recent) == main.MAX_RECENT_FILES
    assert recent[0] == f"library-{main.MAX_RECENT_FILES + 2}.pylot", "most recent first"
    assert "library-0.pylot" not in recent, "the oldest three should have fallen off"
    main.close()


def test_a_missing_recent_file_is_forgotten_when_opening_it_fails(window, path, monkeypatch):
    """``_problem`` is stubbed the same way ``test_opening_something_that_is_
    not_a_library_is_reported`` does it, above -- the real one shows a modal
    ``QMessageBox`` and there is nobody offscreen to click it.
    """
    monkeypatch.setattr(MainWindow, "_problem", lambda self, title, exc: None)
    assert window._recent_files() == [str(path)]

    window.close_library()  # SQLite holds the file open; Windows refuses to delete it otherwise
    path.unlink()
    window.open_path(path)

    assert window._recent_files() == [], "a moved or deleted file cannot be reopened from this menu ever again"
    placeholder = window.recent_menu.actions()[0]
    assert placeholder.text() == "No recent files"
    assert not placeholder.isEnabled()


def test_a_library_that_fails_to_open_for_another_reason_stays_in_recent_files(window, path, monkeypatch):
    """Only a genuinely missing file is dropped -- see ``open_path``'s own
    reasoning. A library this schema version refuses is still the user's
    file and still worth being able to find again.

    Not asserted through ``window.library``: a failed ``open_path`` leaves it
    exactly as it was -- here, still the fixture's own open library, since a
    refusal never calls ``_adopt`` -- so that alone would not distinguish a
    genuine refusal from ``Pylot.open`` having silently ignored the mutation
    below. ``_problem`` is spied on instead, the same way the CLI-adjacent
    tests already do, to prove a refusal actually happened.
    """
    seen = []
    monkeypatch.setattr(MainWindow, "_problem", lambda self, title, exc: seen.append(str(exc)))

    import sqlite3

    connection = sqlite3.connect(path)
    connection.execute("PRAGMA user_version = 999")
    connection.commit()
    connection.close()

    window.open_path(path)

    assert seen, "the fixture needs a genuine refusal, not a successful open"
    assert window._recent_files() == [str(path)], "the file still exists; it should not have been forgotten"


def test_a_recent_file_action_reopens_it(window, path, library_path, tmp_path):
    """The point of the whole feature: the menu entry itself reopens the
    library, not merely records that it was opened once.
    """
    other = tmp_path / "other.pylot"
    shutil.copy(library_path, other)
    window.open_path(other)
    assert window.library.path == other
    assert window._recent_files() == [str(other), str(path)]

    action = next(action for action in window.recent_menu.actions() if action.text() == str(path))
    action.trigger()

    assert window.library.path == path
    assert window._recent_files() == [str(path), str(other)], "reopening moved it back to the front"


def test_clear_recent_files(window, path):
    assert window._recent_files() == [str(path)]

    clear = next(action for action in window.recent_menu.actions() if action.text() == "Clear recent files")
    clear.trigger()

    assert window._recent_files() == []
    placeholder = window.recent_menu.actions()[0]
    assert placeholder.text() == "No recent files"


def test_recent_files_menu_starts_with_no_clear_action_when_empty(qapp, isolated_settings):
    main = MainWindow(settings=isolated_settings)
    assert [action.text() for action in main.recent_menu.actions()] == ["No recent files"]
    main.close()


def test_recent_files_persist_across_windows_through_the_real_settings_backend(qapp, path, tmp_path):
    """Not just a Python list on the instance -- proof it survives the window
    that wrote it being gone, by giving a second, independent ``MainWindow``
    the same on-disk settings file rather than sharing any Python object.
    """
    settings_path = str(tmp_path / "shared-settings.ini")

    first = MainWindow(settings=QSettings(settings_path, QSettings.Format.IniFormat))
    first.open_path(path)
    first.close()

    second = MainWindow(settings=QSettings(settings_path, QSettings.Format.IniFormat))
    assert second._recent_files() == [str(path)]
    assert second.recent_menu.actions()[0].text() == str(path)
    second.close()
