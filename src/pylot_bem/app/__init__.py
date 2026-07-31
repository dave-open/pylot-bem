"""The standalone application (spec 06 Part A).

    uv run pylot-app
    uv run python -m pylot_bem.app

A dedicated window for building and inspecting hydrodynamic libraries, with no
DAVE anywhere in it. That is not only a deferral: a boundary tested from the
first day is a boundary that holds, and nothing here may import DAVE for the
same reason :mod:`pylot_db` may not import Capytaine.

The application is a **client of the Python API and nothing more**. Every
action it performs is one call on :class:`~pylot_bem.api.Pylot`, and where it
needed something that was not there -- editing the library's identity fields,
storing what a pooled solve returned -- the answer was to put it on the API,
not to reach past it. Anything the window has to work out for itself, every
other caller would have to work out too.

Module map:

===============  ============================================================
``window``       the shell: docks, menus, and what happens when
``tree``         the library tree, and the context menus that act on it
``properties``   the property panes, filled from ``guis/*.ui``
``dialogs``      new library, new condition, create mesh, solve, trim
``tabs``         Results, Databases, Inspect, Match, Validation
``viewport``     the 3D view, VTK in a Qt widget
``solving``      a solve on a worker thread
``formatting``   every unit conversion between storage and the screen
===============  ============================================================
"""

import sys

__all__ = ["main", "run"]


def run(path: str | None = None) -> int:
    """Open the window and run the event loop.

    Args:
        path: A library to open at startup.

    Returns:
        The Qt exit code.
    """
    from PySide6.QtWidgets import QApplication

    from pylot_bem.app.window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("pylot")

    window = MainWindow()
    window.show()
    if path:
        window.open_path(path)
    return app.exec()


def main(argv: list[str] | None = None) -> int:
    """Console-script entry point.

    One optional argument, a library to open. There are no options: the
    application is not a command-line tool, and the command line that *is* one
    is :mod:`pylot_bem.cli`.
    """
    argv = sys.argv[1:] if argv is None else argv
    return run(argv[0] if argv else None)
