"""One object for building a library.

:class:`Pylot` **is** a :class:`~pylot_db.storage.Library` -- it adds meshing
and solving to it rather than wrapping it, so every read method is already
there and there is exactly one name for one file on disk.

    from pylot_bem import Pylot
    from pylot_bem.solver import SolveSettings

    d = Pylot.create_new("tanker.pylot", "tanker.stl", "stern, centerline, keel",
                         is_xz_symmetric=True)
    d.add_probe(20.0, -5.0)

    condition = d.create_condition(z_origin=-5.0)
    mesh = d.create_mesh(condition, pct=2.0)
    result = d.run_solve(mesh, SolveSettings(omegas=[0.4, 0.5, 0.6]))

Everything hangs off ``d``; the entities stay frozen plain data and every
method takes an entity **or its id** interchangeably.

What this layer is for is the **derivations**, not the convenience. Three of
them span the two packages, so before this existed each caller had to get them
right on its own:

- the application point is computed from the submerged geometry and stored
  vessel-local, then converted **back** into diffraction space to solve;
- ``is_xz_symmetric`` follows from the base shape and the condition's heel;
- the physical settings of a solve and the physical settings recorded against
  its result have to be the same numbers.

See ``docs/spec/11_api.md``.
"""

from pathlib import Path
from typing import Self

import numpy as np
import xarray as xr
from pylot_db.entities import CalculationMesh, FloatArray, FloatingCondition, Result
from pylot_db.frames import transform, transform_points
from pylot_db.storage import Library

from pylot_bem.geometry import load_mesh_file
from pylot_bem.mesh_pipeline import MeshGeometry, application_point_for, build_mesh, check_full_mesh
from pylot_bem.solver import SOLVE_RHO_SI, Progress, SolverError, SolveSettings, solve, solver_provenance

__all__ = ["Pylot"]

# The dataset's own record of what was solved, against what we asked for.
# Compared, not read: a mismatch means the request and the run disagree, and
# reading it back would hide that instead of reporting it.
#
# `rho` is in here even though SolveSettings has none -- precisely because it
# has none. It is the check that the stored result really is normalised to
# SOLVE_RHO, which is the assumption every delivery then scales from.
_SETTING_COORDS = ("rho", "g", "water_depth", "forward_speed")


class Pylot(Library):
    """A hydrodynamic library that can also be built.

    Adds the calculation stack to :class:`~pylot_db.storage.Library`. Opening
    one of these needs ``capytaine`` and ``pymeshup`` installed; opening the
    same file as a ``Library`` does not, which is the whole point of the split
    (ADR-7).

    :meth:`~pylot_db.storage.Library.open` and
    :meth:`~pylot_db.storage.Library.create` are inherited unchanged and return
    a ``Pylot``.
    """

    # -- creation ----------------------------------------------------------

    @classmethod
    def create_new(
        cls,
        path: str | Path,
        mesh_file: str | Path,
        origin_description: str,
        *,
        is_xz_symmetric: bool,
        scale: float = 1.0,
        vessel_name: str = "",
        description: str = "",
        probe_xy: FloatArray | None = None,
    ) -> Self:
        """Create a library from a mesh file.

        Args:
            path: Library file to create. Must not already exist.
            mesh_file: The hull, in any format ``pymeshlab`` reads. Must be a
                **full** mesh -- see :func:`~pylot_bem.mesh_pipeline.check_full_mesh`.
            origin_description: Where ``(0, 0, 0)`` sits on the vessel, e.g.
                *"stern, centerline, keel"*. Required, and the one thing in a
                library that cannot be recovered later.
            is_xz_symmetric: Whether the hull is symmetric about its XZ plane.
                **Required, with no default**: it is a declaration by the
                modeller and nothing can derive it. The tanker fixture reports
                a 28 m deviation on a nearest-vertex mirror test while
                describing a surface symmetric to under a millimetre, because
                its *tessellation* is not mirrored.
            scale: Multiplied into the file's coordinates. ``0.001`` for a
                model drawn in millimetres.
            vessel_name: Display name. Defaults to the mesh file's stem.
            description: Free text.
            probe_xy: ``(P, 2)`` surface probes. Defaults to the bounding-box
                corners.

        Returns:
            The open library.

        Raises:
            LibraryError: If ``path`` exists or ``origin_description`` is blank.
            MeshPipelineError: If the file is a half mesh. Checked **here**,
                at the earliest point the user can still pick a different file,
                rather than at the first condition.
        """
        mesh_file = Path(mesh_file)
        vertices, faces = load_mesh_file(mesh_file, scale=scale)
        check_full_mesh(vertices)

        return cls.create(
            path,
            vessel_name=vessel_name or mesh_file.stem,
            origin_description=origin_description,
            vertices=vertices,
            faces=faces,
            is_xz_symmetric=is_xz_symmetric,
            description=description,
            probe_xy=probe_xy,
        )

    # -- building ----------------------------------------------------------

    def create_condition(
        self,
        *,
        z_origin: float,
        heel: float = 0.0,
        trim: float = 0.0,
        label: str = "",
        condition_id: str | None = None,
    ) -> FloatingCondition:
        """Add a floating condition, deriving its application point.

        The reason this is not
        :meth:`~pylot_db.storage.Library.add_condition`: the application point
        comes from the *submerged* geometry, so computing it needs the meshing
        stack, which :mod:`pylot_db` may not import. It is the one derivation
        that has to live on this side.

        Args:
            z_origin: Height of the vessel origin above the waterplane [m],
                **negative** for a normally floating vessel. This is not the
                naval draft -- the two differ by wherever the origin sits.
            heel: Heel **slope**, not degrees. ``tan(radians(deg))``.
            trim: Trim **slope**, not degrees.
            label: Human display only.
            condition_id: Explicit id; generated when omitted.

        Returns:
            The stored condition.

        Raises:
            ValueError: If the slopes are outside the valid domain.
            MeshPipelineError: If nothing is submerged at this condition.
        """
        pose = transform(trim=trim, heel=heel, z_origin=z_origin)
        return self.add_condition(
            trim=trim,
            heel=heel,
            z_origin=z_origin,
            application_point=application_point_for(self.base_shape, pose),
            label=label,
            condition_id=condition_id,
        )

    def create_mesh(
        self,
        condition: FloatingCondition | str,
        *,
        pct: float = 2.0,
        iterations: int = 20,
        mesh_id: str | None = None,
    ) -> CalculationMesh:
        """Build a calculation mesh at a condition and store it.

        Args:
            condition: The condition, or its id.
            pct: Regrid target as a percentage of the bounding-box diagonal.
                Lower is finer.
            iterations: Isotropic remeshing iterations.
            mesh_id: Explicit id; generated when omitted.

        Returns:
            The stored mesh. It is a **half** vessel when
            ``is_xz_symmetric`` is true.

        Raises:
            MeshPipelineError: If nothing is submerged, or the regrid produces
                no faces.
        """
        condition = self.condition(condition)
        geometry = build_mesh(self.base_shape, condition.transform, pct=pct, iterations=iterations)
        return self.add_mesh(
            condition_id=condition.id,
            vertices=geometry.vertices,
            faces=geometry.faces,
            pct=pct,
            iterations=iterations,
            mesh_id=mesh_id,
        )

    def run_solve(
        self,
        mesh: CalculationMesh | str,
        settings: SolveSettings,
        *,
        label: str = "",
        result_id: str | None = None,
        progress: Progress | None = None,
    ) -> Result:
        """Solve a mesh and store the result.

        The physical settings reach both the solver and the stored metadata
        from **one** :class:`~pylot_bem.solver.SolveSettings`. Calling
        :func:`~pylot_bem.solver.solve` and
        :meth:`~pylot_db.storage.Library.add_result` separately means passing
        density, gravity, depth and speed twice, and a result recording a
        density it was not solved at is unmatchable forever with nothing to
        show why.

        The result is stored **per unit density**: the solve runs at
        :data:`~pylot_bem.solver.SOLVE_RHO` and nothing else, and the density
        is applied when a database is delivered. So there is no ``rho`` here,
        and one solve serves every density.

        Args:
            mesh: The mesh, or its id.
            settings: The physical conditions. ``lid_mode`` is derived from
                ``lid_z`` rather than passed, and there is no density.
            label: Human display only.
            result_id: Explicit id; generated when omitted.
            progress: Called ``(done, total)`` after each solved **frequency**.
                Raising from it cancels; nothing is stored.

        Returns:
            The stored result metadata.

        Raises:
            SolverError: If the excitation identity fails, or the dataset
                disagrees with ``settings`` about what was solved.
        """
        mesh = self.mesh(mesh)
        dataset = solve(
            mesh.vertices,
            mesh.faces,
            is_xz_symmetric=mesh.is_xz_symmetric,
            application_point=self.application_point_in_diffraction_space(mesh.condition_id),
            settings=settings,
            progress=progress,
        )
        return self.store_result(mesh, dataset, settings, label=label, result_id=result_id)

    def store_result(
        self,
        mesh: CalculationMesh | str,
        dataset: xr.Dataset,
        settings: SolveSettings,
        *,
        label: str = "",
        result_id: str | None = None,
        truncated: bool = False,
    ) -> Result:
        """Store a dataset that has already been solved.

        The second half of :meth:`run_solve`, separated because the application
        does not use the first half: it drives the frequencies itself through
        :class:`~pylot_bem.pool.PoolSolve`, so that a solve can be watched and
        cancelled, and arrives here holding a dataset rather than a request.

        Separated rather than duplicated for the reason :meth:`run_solve`
        exists at all -- the checks below are what stop a result being recorded
        against physical conditions it was not computed at, and a second copy
        of them in the interface would be the copy that goes out of date.

        The dataset may cover **fewer frequencies than ``settings`` asked for**
        and that is not an error: a stopped run yields a complete result over a
        shorter grid (spec 06 section 6.4), and the grid recorded is the one in
        the dataset. Everything else in ``settings`` is checked to match.

        Args:
            mesh: The mesh solved, or its id.
            dataset: What the solver returned.
            settings: The settings it was solved with.
            label: Human display only.
            result_id: Explicit id; generated when omitted.
            truncated: Whether the run was cut short. The dataset's grid is
                what was solved; this records that more had been asked for,
                which nothing else can tell.

        Returns:
            The stored result metadata.

        Raises:
            SolverError: If the dataset disagrees with ``settings`` about the
                physical conditions, or was not solved per unit density.
        """
        mesh = self.mesh(mesh)
        _check_dataset_matches(dataset, settings)

        solver_name, solver_version = solver_provenance(dataset)
        return self.add_result(
            mesh_id=mesh.id,
            data=dataset,
            water_depth=settings.water_depth,
            g=settings.g,
            forward_speed=settings.forward_speed,
            lid_mode=settings.lid_mode,
            lid_z=settings.lid_z,
            lid_radius=settings.lid_radius,
            solver_name=solver_name,
            solver_version=solver_version,
            label=label,
            result_id=result_id,
            truncated=truncated,
        )

    # -- geometry ----------------------------------------------------------

    def base_shape_at(self, condition: FloatingCondition | str) -> MeshGeometry:
        """The **whole** hull, placed in diffraction space at a condition.

        The base shape is stored vessel-local, so on its own it says nothing
        about where the water is. Placed at a condition its z is measured from
        the waterplane, which is what lets a 3D view draw the hull, the
        waterline and a calculation mesh in one scene.

        Not the calculation mesh: nothing is cut and nothing is regridded, so
        this is the dry side as well as the wet one, and it is a full vessel
        even where the mesh is a half. Use :meth:`create_mesh` for something to
        solve, and this for something to look at.

        Args:
            condition: The condition, or its id.

        Returns:
            The geometry, with ``is_xz_symmetric`` false -- it is a full hull
            whatever the condition allows.
        """
        base = self.base_shape
        return MeshGeometry(
            vertices=transform_points(base.vertices, self.condition(condition).transform),
            faces=base.faces,
            is_xz_symmetric=False,
        )

    # -- derivations -------------------------------------------------------

    def application_point_in_diffraction_space(self, condition: FloatingCondition | str) -> FloatArray:
        """The condition's application point, converted with its transform.

        Stored **vessel-local**, because that is the only frame comparable
        across conditions and the one the runtime and the user work in. The
        solver wants it in **diffraction space**. This is the only place that
        conversion is written, and it is public because anyone calling
        :func:`~pylot_bem.solver.solve` directly needs exactly this value --
        passing the stored point straight through puts the moment reference at
        the wrong height by the draft.

        Args:
            condition: The condition, or its id.

        Returns:
            ``(3,)`` in diffraction space.
        """
        condition = self.condition(condition)
        return transform_points(condition.application_point, condition.transform)


def _check_dataset_matches(dataset: xr.Dataset, settings: SolveSettings) -> None:
    """Confirm the dataset was solved at the settings we are about to record.

    Cheap, and it closes the one gap this class exists to close. Everything
    else about a result is taken from the dataset -- ``has_radiation``, the
    frequency grid, the solver version -- so the physical settings being passed
    alongside it is the only place the two can drift apart.

    Density is checked against :data:`~pylot_bem.solver.SOLVE_RHO_SI` rather
    than against a setting, because there is no setting: a stored result is
    per unit density and everything downstream scales from that. This is what
    makes it true rather than merely intended.
    """
    expected = {
        "rho": SOLVE_RHO_SI,
        "g": settings.g,
        "water_depth": settings.water_depth,
        "forward_speed": settings.forward_speed,
    }
    for name in _SETTING_COORDS:
        if name not in dataset.coords:
            continue
        # forward_speed is a scalar coordinate at zero and a *dimension* once
        # it is not, so float() is not safe on it.
        values = np.unique(np.atleast_1d(np.asarray(dataset.coords[name].values, dtype=float)))
        if values.size != 1 or not np.isclose(values[0], expected[name], rtol=1e-9, equal_nan=False):
            raise SolverError(
                f"the dataset reports {name} = {values.tolist()} but the solve was set up "
                f"with {expected[name]}. Storing it would record a result against physical "
                "conditions it was not computed at, which makes it unmatchable"
            )
