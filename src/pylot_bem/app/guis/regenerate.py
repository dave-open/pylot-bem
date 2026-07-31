"""Convert every ``.ui`` in this folder into ``../forms/<name>_ui.py``.

    uv run python packages/pylot-bem/src/pylot_bem/app/guis/regenerate.py

The ``.ui`` files are the source. Edit them in Qt Designer, run this, and
commit both -- the generated modules are checked in so that installing the
package does not need ``pyside6-uic`` on the machine.

``test_app_forms.py`` runs this into a temporary folder and compares, so a
``.ui`` edited without regenerating fails the suite rather than being silently
ignored at runtime.
"""

import shutil
import subprocess
import sys
from pathlib import Path

GUIS = Path(__file__).parent
FORMS = GUIS.parent / "forms"

# The generated header carries the Qt version that produced it, which differs
# between machines and says nothing about the widgets. Dropped so a comparison
# is about the interface, not the toolchain.
HEADER_MARKER = "################################################################################"


def generated_name(ui_file: Path) -> str:
    return f"{ui_file.stem}_ui.py"


def uic() -> str:
    """Where ``pyside6-uic`` is.

    Looked up beside the running interpreter before ``PATH``, so a virtual
    environment converts with its own PySide6 rather than whichever one happens
    to be installed system-wide.
    """
    beside = Path(sys.executable).parent / "pyside6-uic.exe"
    if beside.exists():
        return str(beside)
    found = shutil.which("pyside6-uic")
    if found is None:
        raise RuntimeError("pyside6-uic is not on PATH and not beside the interpreter")
    return found


def convert(ui_file: Path, into: Path) -> Path:
    """Run ``pyside6-uic`` on one file and return what it wrote."""
    output = into / generated_name(ui_file)
    subprocess.run([uic(), str(ui_file), "-o", str(output)], check=True, capture_output=True)
    return output


def body(source: str) -> str:
    """The generated module without its version header.

    Everything up to and including the second banner line is the ``pyside6-uic``
    preamble.
    """
    parts = source.split(HEADER_MARKER)
    return parts[-1].strip() if len(parts) > 1 else source.strip()


def ui_files() -> list[Path]:
    return sorted(GUIS.glob("*.ui"))


def main() -> int:
    FORMS.mkdir(exist_ok=True)
    for ui_file in ui_files():
        output = convert(ui_file, FORMS)
        print(f"{ui_file.name} -> forms/{output.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
