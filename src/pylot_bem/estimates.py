"""What a solve will cost, and where a mesh stops being trustworthy.

Three numbers a user needs *before* starting a run that takes minutes. They
were written inside the CLI first, which made them unavailable to anything
else -- the same derivation would have been rewritten for the application, and
the two could then disagree about the same mesh.

Nothing here touches Capytaine or ``pymeshup``; it is arithmetic on a mesh. It
lives in this package only because :mod:`pylot_db` has no business estimating
the cost of a solver it may not import.
"""

import numpy as np

from pylot_db.entities import FloatArray, IntArray

__all__ = [
    "BYTES_PER_PANEL_SQUARED",
    "PANELS_PER_WAVELENGTH",
    "format_memory",
    "influence_matrix_bytes",
    "shortest_reliable_period",
    "solved_panels",
]

# Spec 06 section 6.5: two dense complex matrices, 2 * 16 * N^2 bytes.
BYTES_PER_PANEL_SQUARED = 32

# Capytaine warns when the largest panel exceeds wavelength/8, so the shortest
# wavelength a mesh can represent is eight times its largest face radius.
PANELS_PER_WAVELENGTH = 8

# Deep water: omega^2 = g * k, and k = 2 * pi / wavelength.
GRAVITY = 9.81


def solved_panels(mesh) -> int:
    """How many panels the solver actually works with.

    A symmetric mesh is stored as a **half** vessel and mirrored by the solver,
    so its cost is twice its face count. :class:`~pylot_db.entities.CalculationMesh`
    says that trap "belongs in one function, not at each call site" -- this is
    that function.

    Args:
        mesh: Anything carrying ``faces`` and ``is_xz_symmetric``: a
            :class:`~pylot_db.entities.CalculationMesh` or a
            :class:`~pylot_bem.mesh_pipeline.MeshGeometry`.

    Returns:
        The panel count the solver sees.
    """
    return len(mesh.faces) * (2 if mesh.is_xz_symmetric else 1)


def influence_matrix_bytes(panels: int) -> int:
    """Peak memory for one solver process, in bytes.

    Two dense complex matrices of ``panels x panels``. This is per **worker**:
    a pooled solve multiplies it by the worker count, which is the number that
    decides how many workers a machine can carry.
    """
    return BYTES_PER_PANEL_SQUARED * int(panels) ** 2


def format_memory(panels: int) -> str:
    """Influence-matrix memory for a panel count, in units a reader can act on.

    A formatter rather than a number because the number alone misleads: rounded
    to whole megabytes a small mesh reads "~0 MB", which looks like a broken
    calculation instead of a small one.

    Here rather than in either caller because both the command line and the
    application show this figure, about the same mesh, and two copies of the
    rounding would eventually disagree.
    """
    megabytes = influence_matrix_bytes(panels) / 1e6
    if megabytes < 1:
        return "<1 MB"
    if megabytes < 1000:
        return f"~{megabytes:.0f} MB"
    return f"~{megabytes / 1000:.1f} GB"


def shortest_reliable_period(vertices: FloatArray, faces: IntArray) -> float:
    """The shortest wave period this mesh can be trusted for [s].

    A panel has to be small against the wave it is resolving. Capytaine warns
    at eight panels per wavelength; inverting that for the mesh's *largest*
    face gives the shortest wave it still represents, and the deep-water
    dispersion relation turns that into a period.

    Surfaced **before** a solve rather than as a warning during one: it is the
    number that decides whether a frequency grid is worth running at all.

    Args:
        vertices: ``(N, 3)`` mesh coordinates [m].
        faces: ``(M, 3)`` triangle indices.

    Returns:
        The period [s]. Shorter periods will still solve, and their results
        will be wrong by an amount nothing downstream can detect.
    """
    a, b, c = vertices[faces[:, 0]], vertices[faces[:, 1]], vertices[faces[:, 2]]
    centres = (a + b + c) / 3
    radius = float(np.max([np.linalg.norm(v - centres, axis=1) for v in (a, b, c)]))
    wavelength = PANELS_PER_WAVELENGTH * radius
    omega = np.sqrt(2 * np.pi * GRAVITY / wavelength)
    return float(2 * np.pi / omega)
