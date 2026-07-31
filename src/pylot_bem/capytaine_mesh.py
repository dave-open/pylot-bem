"""Turning stored geometry into a Capytaine mesh.

Kept apart from the pipeline on purpose: a mesh loaded from a library must be
solvable without re-running the pipeline that built it. The pipeline produces
geometry; this turns geometry into a solver object.

See ``docs/spec/03_mesh_pipeline.md`` section 4.
"""

import capytaine as cpt
import numpy as np
from capytaine.meshes.symmetric import ReflectionSymmetricMesh

from pylot_db.entities import FloatArray, IntArray

__all__ = ["to_capytaine_mesh"]


def to_capytaine_mesh(
    vertices: FloatArray, faces: IntArray, *, is_xz_symmetric: bool, name: str | None = None
) -> cpt.Mesh | ReflectionSymmetricMesh:
    """Build the mesh Capytaine solves on.

    Capytaine expects **quadrilateral** faces. A triangle is passed as a
    *degenerate quad* with the last vertex repeated, ``(v1, v2, v3, v3)``. This
    looks like a bug to anyone who has not seen it before, which is why it has
    a comment on it here and a sentence in the spec.

    Args:
        vertices: ``(N, 3)`` diffraction-space coordinates.
        faces: ``(M, 3)`` triangle vertex indices.
        is_xz_symmetric: When true the geometry is a **half** vessel and is
            wrapped so the solver reconstructs the whole body from it.
        name: Optional mesh name, passed through to Capytaine.

    Returns:
        A mesh, reflection-symmetric when ``is_xz_symmetric``.
    """
    faces = np.asarray(faces, dtype=int)
    quads = np.column_stack([faces, faces[:, 2]])  # (v1, v2, v3, v3)

    mesh = cpt.Mesh(vertices=np.asarray(vertices, dtype=float), faces=quads, name=name)

    if is_xz_symmetric:
        # The half is reflected in the XZ plane, so the result *is* the whole
        # body -- the solver simply exploits the block structure.
        mesh = ReflectionSymmetricMesh(mesh, plane=cpt.meshes.geometry.xOz_Plane, name=name)
    return mesh
