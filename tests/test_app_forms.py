"""The contract between the ``.ui`` files and the code that fills them.

The point of putting the property panes and dialogs in Qt Designer is that the
arrangement can be changed without touching Python. What *cannot* change
silently is an ``objectName``: rename one in Designer and the pane still builds,
still lays out, and raises ``AttributeError`` the moment a user selects the
thing it describes.

So two checks, and they are different:

1. every ``.ui`` has a generated module, and regenerating produces the same
   thing -- a ``.ui`` edited without running ``regenerate.py`` fails here
   rather than being silently ignored at runtime;
2. every ``self.ui.<name>`` the code reads exists on the widget the generator
   produced. Discovered by parsing the source, so a widget added to the code
   is covered without anyone remembering to list it.

The second is the one that earns its place. It is derived from the code rather
than written out, which means it cannot fall behind it.
"""

import ast
from pathlib import Path

import pytest
from PySide6.QtWidgets import QDialog, QWidget

from pylot_bem.app import dialogs, merge, properties
from pylot_bem.app.guis import regenerate

FILLERS = (properties, dialogs, merge)


def test_every_ui_file_has_a_generated_module():
    for ui_file in regenerate.ui_files():
        generated = regenerate.FORMS / regenerate.generated_name(ui_file)
        assert generated.exists(), f"{ui_file.name} has never been converted; run regenerate.py"


def test_there_are_ui_files_at_all():
    """The check above passes vacuously against an empty folder."""
    assert len(regenerate.ui_files()) >= 11


def test_the_generated_modules_are_up_to_date(tmp_path):
    """Regenerate into a temporary folder and compare.

    Ignoring the header, which carries the Qt version that produced it and
    would make this fail on a machine with a different PySide6 for a reason
    that has nothing to do with the interface.
    """
    stale = []
    for ui_file in regenerate.ui_files():
        fresh = regenerate.convert(ui_file, tmp_path)
        committed = regenerate.FORMS / regenerate.generated_name(ui_file)
        if regenerate.body(fresh.read_text(encoding="utf-8")) != regenerate.body(
            committed.read_text(encoding="utf-8")
        ):
            stale.append(ui_file.name)
    assert not stale, f"edited without regenerating: {stale}. Run guis/regenerate.py"


def test_the_comparison_can_actually_fail(tmp_path):
    """Sanity-check the mechanism above rather than only its outcome.

    Comparing two files after stripping a header is exactly the shape of test
    that passes because both sides came out empty.
    """
    ui_file = regenerate.ui_files()[0]
    fresh = regenerate.convert(ui_file, tmp_path)
    body = regenerate.body(fresh.read_text(encoding="utf-8"))

    assert len(body) > 200, "the body is being stripped to nothing"
    assert body != regenerate.body("# -*- coding: utf-8 -*-\nsomething else\n")


def ui_attributes_by_class(module) -> dict[str, tuple[str, set[str]]]:
    """``{class: (Ui_class, {name, ...})}`` for every ``self.ui.<name>`` read.

    Parsed rather than introspected: the attributes are reached at runtime only
    when the branch that reads them runs, and half of them are on a code path
    that needs a solved library.
    """
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    found = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        ui_class, names = None, set()
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Name)
                and inner.func.id.startswith("Ui_")
            ):
                ui_class = inner.func.id
            if (
                isinstance(inner, ast.Attribute)
                and isinstance(inner.value, ast.Attribute)
                and inner.value.attr == "ui"
                and isinstance(inner.value.value, ast.Name)
                and inner.value.value.id == "self"
            ):
                names.add(inner.attr)
        if ui_class is not None:
            found[node.name] = (ui_class, names)
    return found


ALL_CLASSES = [
    (module, name, ui_class, names)
    for module in FILLERS
    for name, (ui_class, names) in ui_attributes_by_class(module).items()
]


def test_the_parser_found_the_classes():
    """Otherwise the parametrised test below runs zero cases and passes."""
    names = {name for _, name, _, _ in ALL_CLASSES}
    assert {"LibraryPane", "ConditionPane", "MeshPane", "ResultPane", "SolveDialog", "MergeDialog"} <= names
    assert all(names for *_, names in ALL_CLASSES), "a class was found with no widgets read"


@pytest.mark.parametrize(
    ("module", "name", "ui_class", "names"),
    ALL_CLASSES,
    ids=[f"{name}" for _, name, _, _ in ALL_CLASSES],
)
def test_every_widget_the_code_reads_exists_in_the_ui_file(qapp, module, name, ui_class, names):
    form = getattr(module, ui_class)()
    host = QDialog() if ui_class.startswith("Ui_Dlg") else QWidget()
    form.setupUi(host)

    missing = sorted(attribute for attribute in names if not hasattr(form, attribute))
    assert not missing, (
        f"{name} reads {missing} which {ui_class} does not define. "
        "An objectName was renamed in Qt Designer, or the widget was removed."
    )


def test_a_missing_widget_would_be_caught(qapp):
    """The check above is only worth something if absence is detectable."""
    from pylot_bem.app.forms.prop_library_ui import Ui_PropLibrary

    form = Ui_PropLibrary()
    form.setupUi(QWidget())

    assert hasattr(form, "editVesselName")
    assert not hasattr(form, "editSomethingNobodyNamed")
