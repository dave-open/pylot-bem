"""Hulls used by the pylot-bem tests: an analytic box and a real tanker.

The same boxboat as the pylot-db tests: 60 x 20 x 10, symmetric about y, origin
at stern / centerline / keel. Small enough to work out the right answer by
hand, which is what makes the assertions worth anything.
"""

from pathlib import Path

import numpy as np
from pylot_db.entities import BaseShape
from pymeshup import Load

BOX_VERTICES = np.array(
    [
        [0.0, -10.0, 0.0],
        [60.0, -10.0, 0.0],
        [60.0, 10.0, 0.0],
        [0.0, 10.0, 0.0],
        [0.0, -10.0, 10.0],
        [60.0, -10.0, 10.0],
        [60.0, 10.0, 10.0],
        [0.0, 10.0, 10.0],
    ]
)

# Outward-facing triangles.
BOX_FACES = np.array(
    [
        [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
        [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7],
    ]
)  # fmt: skip


def make_base_shape(vertices=None, faces=None, is_xz_symmetric=True):
    vertices = BOX_VERTICES if vertices is None else vertices
    faces = BOX_FACES if faces is None else faces
    return BaseShape(
        vertices=np.asarray(vertices, dtype=float),
        faces=np.asarray(faces),
        is_xz_symmetric=is_xz_symmetric,
        probe_xy=np.zeros((4, 2)),
    )


TANKER_STL = Path(__file__).parent / "assets" / "tanker.stl"


def load_tanker(is_xz_symmetric=True):
    """A real hull: 328 x 58 x 28 m, 246 vertices, 488 faces.

    Nominally symmetric about y, and **not precisely so**: the shape differs by
    under a millimetre at the beam extremes, and the *tessellation* is not
    mirrored at all -- vertices sit in entirely different places on each side.

    That is what makes it the right fixture for symmetry. ``is_xz_symmetric``
    is a **declaration by the modeller**, not something derivable from the
    geometry: a nearest-vertex mirror test on this hull reports a 28 m
    deviation while the surface it describes is symmetric to under a
    millimetre.
    """
    volume = Load(str(TANKER_STL))
    return BaseShape(
        vertices=np.asarray(volume.vertices, dtype=float),
        faces=np.asarray(volume.ms.current_mesh().face_matrix()),
        is_xz_symmetric=is_xz_symmetric,
        probe_xy=np.zeros((4, 2)),
    )
