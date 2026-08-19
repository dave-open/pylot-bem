"""Entry point for the PyInstaller build of the standalone application.

Solving spawns worker processes (:mod:`pylot_bem.pool`, spec 06 section 6.3).
Windows has no ``fork``, so every worker re-executes this script -- normally
that means Python re-importing ``__main__``, but in a frozen build
``sys.executable`` *is* the bundled ``pylot.exe``, so a worker would relaunch
the whole application instead of becoming a worker. Calling
``multiprocessing.freeze_support()`` first, as the very first statement after
the guard, is what tells a frozen relaunch to run the worker and exit instead
(see the ``multiprocessing`` docs). It is a no-op everywhere else, including
``uv run pylot-bem``, so this script -- not ``pylot_bem.app.__main__`` -- is
the PyInstaller entry point.
"""

import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()

    from pylot_bem.app import main

    raise SystemExit(main())
