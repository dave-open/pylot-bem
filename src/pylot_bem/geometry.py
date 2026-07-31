"""Reading a hull from a file.

The **only** unit conversion in the whole system happens here. Lengths are
metres everywhere else (``CLAUDE.md``), and a mesh file carries no units at
all, so the one place a millimetre model can be corrected is at import --
``scale=0.001``.

Separate from :mod:`pylot_bem.api` because the application needs to load a file
and look at it -- bounds, face count, whether it is a half mesh -- **before**
committing to a library. Creating the library is the irreversible step; showing
the user what they picked is not.
"""

from pathlib import Path

import numpy as np
from pymeshup import Load

from pylot_db.entities import FloatArray, IntArray

__all__ = ["load_mesh_file"]


def load_mesh_file(path: str | Path, *, scale: float = 1.0) -> tuple[FloatArray, IntArray]:
    """Read a mesh file and return its vertices and faces.

    Any format ``pymeshlab`` reads; STL in practice.

    Args:
        path: The file to read.
        scale: Multiplied into every coordinate. ``0.001`` for a model drawn in
            millimetres. Applied to the vertices directly rather than through a
            transform, so it cannot be confused with a floating condition.

    Returns:
        ``(N, 3)`` float vertices [m] and ``(M, 3)`` integer triangle indices.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If ``scale`` is not positive. A zero or negative scale
            collapses or mirrors the hull, and the result would still mesh and
            still solve.
    """
    if scale <= 0.0:
        raise ValueError(f"scale must be positive, got {scale}; a negative scale mirrors the hull")

    volume = Load(str(Path(path)))
    vertices = np.asarray(volume.vertices, dtype=float) * float(scale)
    faces = np.asarray(volume.ms.current_mesh().face_matrix(), dtype=np.int64)
    return vertices, faces
