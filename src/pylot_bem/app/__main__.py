"""``python -m pylot_bem.app``.

The ``if __name__`` guard is not decoration. Solving spawns worker processes
(spec 06 section 6.3) and Windows has no ``fork``, so every worker re-imports
the parent's ``__main__`` -- which is *this file* when the application is
started this way. Without the guard each worker would open its own window.
"""

from pylot_bem.app import main

if __name__ == "__main__":
    raise SystemExit(main())
