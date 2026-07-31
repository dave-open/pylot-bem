"""Base shape + floating condition + density -> a solver-ready calculation mesh.

Ported from ``reference/pylot-prototype/capytaine_and_pymeshup.py``, with two
changes that matter:

- the two half-space cuts are **reordered** so the submerged bounds can be read
  between them (see :func:`build_mesh`);
- the retry heuristic is gone. The prototype re-ran the regrid with a halved
  percentage when the face count did not increase, comparing against the
  *input* face count, which made output resolution depend on input density and
  broke determinism. One regrid call, exactly as configured.

See the pylot specification, ``03_mesh_pipeline.md``.
"""

from dataclasses import dataclass

import numpy as np
from pylot_db.entities import BaseShape, FloatArray, IntArray
from pylot_db.frames import decompose, is_xz_symmetric
from pymeshup import Volume

__all__ = [
    "MeshGeometry",
    "MeshPipelineError",
    "SubmergedSummary",
    "application_point_for",
    "build_mesh",
    "check_full_mesh",
    "submerged_summary",
]


class MeshPipelineError(Exception):
    """The pipeline could not produce a usable mesh."""


@dataclass(frozen=True, eq=False, slots=True)
class MeshGeometry:
    """The geometry the pipeline produces, before it is given an identity.

    Attributes:
        vertices: ``(N, 3)`` diffraction-space coordinates [m].
        faces: ``(M, 3)`` triangle vertex indices.
        is_xz_symmetric: Whether this is a **half** vessel, to be paired with a
            reflection-symmetric solve.
    """

    vertices: FloatArray
    faces: IntArray
    is_xz_symmetric: bool


@dataclass(frozen=True, eq=False, slots=True)
class SubmergedSummary:
    """What the wetted part of a hull measures, for display only.

    Spec 02 section 1: nothing computes from these. They exist so a user can
    look at a condition and see whether it is the one they meant.

    **There is no volume**, and its absence is deliberate. The waterline cut
    leaves an *open* surface, and pymeshlab refuses a volume for one rather
    than returning a number from the divergence theorem that would be wrong by
    however much the missing waterplane would have contributed. Closing it
    would mean generating a lid, which is a solver construct
    (spec 04 section 2) and has no business in a display field. A displacement
    that is quietly wrong is worse than one that is absent.

    Attributes:
        wetted_area: Area of the submerged surface [m2]. Exact -- it is a sum
            over the faces that survived the cut.
        lo: ``(3,)`` lower submerged bounds, **diffraction space** [m].
        hi: ``(3,)`` upper submerged bounds, **diffraction space** [m].
    """

    wetted_area: float
    lo: FloatArray
    hi: FloatArray

    @property
    def waterline_length(self) -> float:
        """Length of the submerged part along x [m]."""
        return float(self.hi[0] - self.lo[0])


def _as_volume(vertices: FloatArray, faces: IntArray) -> Volume:
    volume = Volume()
    volume.set_vertices_and_faces(np.asarray(vertices, dtype=float), np.asarray(faces))
    return volume


def _geometry_of(volume: Volume) -> tuple[FloatArray, IntArray]:
    vertices = np.asarray(volume.vertices, dtype=float)
    faces = np.asarray(volume.ms.current_mesh().face_matrix(), dtype=np.int64)
    return vertices, faces


def check_full_mesh(vertices: FloatArray) -> None:
    """Refuse a half mesh.

    ``use_symmetry`` is derived from the condition and the pipeline cuts the
    half itself, so a pre-halved input would be cut **again** -- silently
    producing a quarter vessel at any condition with ``heel == 0``, and a wrong
    displacement at every other one. Nothing downstream could detect it.

    Takes vertices rather than a :class:`~pylot_db.entities.BaseShape` so it
    can also run at **import**, before a base shape exists, which is where spec
    02 section 1 asks for it -- the earliest point a user can still pick a
    different file.

    Args:
        vertices: ``(N, 3)`` vessel-local coordinates.

    Raises:
        MeshPipelineError: If the geometry lies on one side of ``y = 0``.
    """
    y = np.asarray(vertices, dtype=float)[:, 1]
    span = float(y.max() - y.min())
    if span <= 0.0:
        raise MeshPipelineError(f"the base shape has no width: every vertex is at y = {y.min()}")

    # Measured against the beam, not against exact zero. A half mesh is made by
    # *cutting* one, and a cut leaves floating-point residue on the plane it
    # cut at -- halving the tanker fixture gives y.max() = 3.6e-15, not 0. An
    # exact test passes that mesh, the pipeline cuts it again, and the result
    # is a quarter vessel with no symptom other than half the displacement.
    #
    # The two sides of a real hull are within a factor of a few of each other;
    # the residue is 1e-16 of the beam. Anything between is not a shape.
    smaller_side = min(max(-y.min(), 0.0), max(y.max(), 0.0))
    if smaller_side <= 1e-6 * span:
        raise MeshPipelineError(
            f"the base shape lies on one side of y = 0 (y from {y.min()} to "
            f"{y.max()}), which means a half mesh was supplied. A full mesh is "
            "required: symmetry is derived from the floating condition and the half "
            "is cut here, so a pre-halved shape would be cut twice"
        )


def _submerged_volume(base_shape: BaseShape, transform: FloatArray) -> Volume:
    """Transform into diffraction space and keep the wetted part.

    Raises:
        MeshPipelineError: If nothing is left below the waterplane.
    """
    placed = _as_volume(base_shape.vertices, base_shape.faces).transform(np.asarray(transform))
    wetted = placed.cut_at_waterline()

    # pymeshup returns an *empty* mesh rather than raising: zero faces and
    # degenerate bounds where min > max. Left alone, that surfaces much later
    # as an opaque failure inside pymeshlab or the solver.
    if len(np.asarray(wetted.ms.current_mesh().face_matrix())) == 0:
        trim, heel, z_origin = decompose(transform)
        lo = base_shape.vertices.min(axis=0)
        hi = base_shape.vertices.max(axis=0)
        raise MeshPipelineError(
            f"nothing lies below the waterplane at trim={trim}, heel={heel}, "
            f"z_origin={z_origin}. The base shape spans x {lo[0]}..{hi[0]}, "
            f"y {lo[1]}..{hi[1]}, z {lo[2]}..{hi[2]} in vessel coordinates; "
            "check the sign of z_origin, which is the height of the vessel origin "
            "above the waterplane and is negative for a normally floating vessel"
        )
    return wetted


def application_point_for(base_shape: BaseShape, transform: FloatArray) -> FloatArray:
    """The moment reference for a condition, derived from its submerged geometry.

    The centre of the **submerged** bounding box, in all three axes, taken
    after the waterline cut and before any symmetry cut. Both sides of that
    ordering matter: before the waterline cut the bounds include dry structure,
    and after an XZ cut the y-bounds describe half a vessel, which would put
    the point off centreline for every symmetric hull.

    Takes a **transform** rather than a ``FloatingCondition``: a condition
    cannot be constructed without its application point, so a signature taking
    one would be circular.

    Args:
        base_shape: The vessel geometry, vessel-local.
        transform: ``(4, 4)`` floating-condition transform.

    Returns:
        ``(3,)`` **vessel-local** application point. ``y`` is **exactly zero**
        when the base shape is declared XZ-symmetric and the condition has no
        heel, whatever the bounds say.

        Note which frame that is. In *diffraction* space the centre sits at
        mid-draft, so its z is negative. Converted to vessel-local the sign
        follows the origin convention: for the usual keel origin it comes out
        **positive**, roughly half the draft above the keel.

    Raises:
        MeshPipelineError: If the base shape is a half mesh, or nothing is
            submerged at this condition.
    """
    check_full_mesh(base_shape.vertices)
    transform = np.asarray(transform, dtype=float)

    x_lo, x_hi, y_lo, y_hi, z_lo, z_hi = _submerged_volume(base_shape, transform).bounds
    y = (y_lo + y_hi) / 2

    if is_xz_symmetric(base_shape.is_xz_symmetric, decompose(transform).heel):
        # A hull the modeller declared symmetric, floating without heel, is
        # symmetric *by definition*. Whatever offset the bounds report is an
        # artefact of how the surface happens to be modelled -- the tanker
        # fixture is out by 2 mm on a 58 m beam -- and putting the moment
        # reference off the centreline for that reason would be wrong.
        #
        # The same derived condition as the mesh half-cut, so a mesh that is
        # cut in half and the point moments are taken about always agree.
        y = 0.0

    centre_in_diffraction = np.array([(x_lo + x_hi) / 2, y, (z_lo + z_hi) / 2, 1.0])

    # Stored vessel-local: the only representation comparable across
    # conditions, and the frame the runtime and the user both work in.
    return (np.linalg.inv(transform) @ centre_in_diffraction)[:3]


def submerged_summary(base_shape: BaseShape, transform: FloatArray) -> SubmergedSummary:
    """Measure the wetted part of a hull at a floating condition.

    The same waterline cut :func:`application_point_for` makes, read for its
    dimensions instead of its centre -- which is why the bounds here explain
    that point rather than merely accompanying it.

    Args:
        base_shape: The vessel geometry, vessel-local.
        transform: ``(4, 4)`` floating-condition transform.

    Returns:
        The summary, in **diffraction space**.

    Raises:
        MeshPipelineError: If nothing is submerged at this condition.
    """
    wetted = _submerged_volume(base_shape, np.asarray(transform, dtype=float))
    x_lo, x_hi, y_lo, y_hi, z_lo, z_hi = wetted.bounds
    measures = wetted.ms.get_geometric_measures()
    return SubmergedSummary(
        wetted_area=float(measures["surface_area"]),
        lo=np.array([x_lo, y_lo, z_lo], dtype=float),
        hi=np.array([x_hi, y_hi, z_hi], dtype=float),
    )


def build_mesh(
    base_shape: BaseShape,
    transform: FloatArray,
    *,
    pct: float = 2.0,
    iterations: int = 20,
) -> MeshGeometry:
    """Produce a calculation mesh for one floating condition.

    The order is load-bearing twice over. The transform is applied **first**,
    so the waterline cut happens at the diffraction-space waterplane ``z = 0``,
    which is what makes the cut mean anything. And the waterline cut comes
    **before** the symmetry cut, so :func:`application_point_for` can read the
    bounds of the whole submerged volume between them.

    The prototype cuts XZ first. The two are half-space operations and
    commute, so the geometry is identical either way -- a test asserts that, so
    it is recorded as a fact rather than assumed.

    Args:
        base_shape: The vessel geometry, vessel-local. Must be a full mesh.
        transform: ``(4, 4)`` floating-condition transform.
        pct: Regrid target as a percentage of the bounding-box diagonal. Lower
            is finer.
        iterations: Isotropic remeshing iterations. A genuine convergence knob,
            not a cosmetic one.

    Returns:
        The diffraction-space geometry, and whether it is a half vessel.

    Raises:
        MeshPipelineError: If the base shape is a half mesh, or nothing is
            submerged at this condition.
    """
    check_full_mesh(base_shape.vertices)
    transform = np.asarray(transform, dtype=float)

    use_symmetry = is_xz_symmetric(base_shape.is_xz_symmetric, decompose(transform).heel)

    wetted = _submerged_volume(base_shape, transform)
    if use_symmetry:
        wetted = wetted.cut_at_xz()  # keeps negative y
    regridded = wetted.regrid(iterations=iterations, pct=pct)

    vertices, faces = _geometry_of(regridded)
    if len(faces) == 0:
        raise MeshPipelineError(f"the regrid at pct={pct}, iterations={iterations} produced no faces")

    return MeshGeometry(vertices=vertices, faces=faces, is_xz_symmetric=use_symmetry)
