"""Running Capytaine, in-process.

The solver boundary is a **function**, not a process: mesh plus physical
settings in, result dataset out (ADR-3). Capytaine is called directly, which
the Apache 2.0 relicence made possible and which removed the whole
``fleetmaster.exe`` layer -- its settings file, path setting, stdout scraping
and version gate (ADR-1).

See ``docs/spec/04_solver_and_results.md``.
"""

from collections.abc import Callable
from dataclasses import dataclass
from itertools import groupby

import capytaine as cpt
import numpy as np
import xarray as xr

from pylot_bem.capytaine_mesh import to_capytaine_mesh
from pylot_db.entities import FloatArray, IntArray, LidMode

__all__ = [
    "KG_PER_TONNE",
    "SOLVE_RHO",
    "SOLVE_RHO_SI",
    "Progress",
    "SolveSettings",
    "SolverError",
    "auto_lid_z",
    "solve",
]

type Progress = Callable[[int, int], None]

# Storage and the user interface work in t/m3 (1.025); Capytaine is an SI code
# whose rho defaults to 1000.0 kg/m3, and mafredo's converter divides by 1000
# to reach kN and mt. Those two facts only fit together if Capytaine is run in
# SI, so the conversion happens here, at the boundary, once.
#
# The prototype passed 1.025 straight in. That works by linearity -- the
# outputs come out in kN and mt directly -- but it is a different convention
# from mafredo's, and combining the two silently scales an entire database by
# 1000.
KG_PER_TONNE = 1000.0

# Every solve runs at this density, and there is no way to ask for another.
#
# Density enters linear potential flow in exactly one place -- the linearised
# Bernoulli pressure ``p = -rho dphi/dt``. Laplace, the free-surface condition
# and the body condition contain no rho at all, so added mass, damping and the
# excitation force are each rho times an integral that does not depend on it.
# Measured, not assumed: doubling rho gives **bitwise** doubled results, 0 ULP,
# including the moments and with the excitation phase unmoved
# (``tests/test_rho_scaling.py``).
#
# So a result is stored **per unit density** and multiplied on delivery. One
# solve then serves fresh water, salt water and anything else, and density
# stops being something a stored database can be wrong about.
#
# 1 t/m3 rather than some other reference because it makes the delivery factor
# numerically equal to the density in the unit the whole system uses.
SOLVE_RHO = 1.0
SOLVE_RHO_SI = SOLVE_RHO * KG_PER_TONNE


class SolverError(Exception):
    """The solve could not be completed, or its output failed a self-check."""


@dataclass(frozen=True, slots=True)
class SolveSettings:
    """The physical conditions of a solve.

    Every one of these is an **input**, not a constant. The previous
    implementation pinned ``water_depth = inf`` and ``water_level = 0`` inside
    accessor functions, which made those dimensions unusable for matching.

    **There is no rho.** Not an oversight and not a hard-coded constant of the
    old kind: results scale exactly linearly with density (see
    :data:`SOLVE_RHO`), so every solve runs at 1 t/m3 and the density is
    applied when a database is delivered. Accepting one here would let a
    caller store a result that is not normalised, which nothing downstream
    could detect.

    Attributes:
        omegas: Frequency grid [rad/s]. Both problem types.
        wave_directions: Wave directions [deg], **direction of travel**
            (spec 04 section 7.4). Diffraction only; empty means radiation only.
        water_depth: [m]. ``inf`` for infinite depth.
        g: Gravitational acceleration [m/s2].
        forward_speed: [m/s].
        lid_z: Lid position [m] for irregular-frequency removal, or ``None``
            for no lid. A solver setting, not geometry (spec 04 section 2).
        lid_radius: Lid ``faces_max_radius`` [m]; ``None`` uses the mean hull
            face radius.
    """

    omegas: tuple[float, ...]
    wave_directions: tuple[float, ...] = ()
    water_depth: float = np.inf
    g: float = 9.81
    forward_speed: float = 0.0
    lid_z: float | None = None
    lid_radius: float | None = None

    @property
    def lid_mode(self) -> LidMode | None:
        """The stored lid mode, **derived** from ``lid_z``.

        The two are not independent facts: a lid at ``z = 0`` *is* a
        free-surface lid. Storage keeps both columns, so deriving one from the
        other here is what stops them disagreeing -- the same reason
        ``is_xz_symmetric`` is derived rather than accepted.
        """
        if self.lid_z is None:
            return None
        return "free_surface" if self.lid_z == 0.0 else "below_free_surface"


def build_body(
    vertices: FloatArray,
    faces: IntArray,
    *,
    is_xz_symmetric: bool,
    application_point: FloatArray,
    lid_z: float | None = None,
    lid_radius: float | None = None,
    name: str = "vessel",
) -> cpt.FloatingBody:
    """Assemble the body Capytaine solves on.

    ``rotation_center`` **is** the application point (spec 01 section 5.2). It
    does not move the mesh and it does not affect the phase origin -- the
    previous implementation's ``mesh_translation = -POA`` step did both, which
    is the defect this whole design exists to remove.

    Args:
        vertices: ``(N, 3)`` **diffraction-space** coordinates.
        faces: ``(M, 3)`` triangle indices.
        is_xz_symmetric: Whether the geometry is a half vessel.
        application_point: ``(3,)`` in **diffraction space**. The caller
            converts from the stored vessel-local value with ``T``; that is the
            only place the conversion happens.
        lid_z: Lid position, or ``None`` for no lid.
        lid_radius: Lid face radius; ``None`` for Capytaine's default.
        name: Body name, carried into the dataset.

    Returns:
        The body, with six rigid-body degrees of freedom.
    """
    mesh = to_capytaine_mesh(vertices, faces, is_xz_symmetric=is_xz_symmetric, name=name)

    lid_mesh = None
    if lid_z is not None:
        # Generated from the *final* hull mesh, so it inherits the floating
        # condition and the hull resolution without being told either.
        lid_mesh = mesh.generate_lid(z=lid_z, faces_max_radius=lid_radius)

    return cpt.FloatingBody(
        mesh=mesh,
        lid_mesh=lid_mesh,
        dofs=cpt.rigid_body_dofs(rotation_center=np.asarray(application_point, dtype=float)),
        name=name,
    )


def auto_lid_z(
    vertices: FloatArray,
    faces: IntArray,
    *,
    is_xz_symmetric: bool,
    omega_max: float,
    g: float = 9.81,
) -> float | None:
    """Where Capytaine would put a lid for a frequency grid, or ``None``.

    Wraps ``Mesh.lowest_lid_position``, which reads the highest frequency
    straight off the grid the user has just entered -- so *auto* is a real mode
    here rather than a workaround (spec 09 section E.2). It became one when the
    lid moved from the mesh to the solve settings: on the mesh the two entities
    could go stale against each other, and as a solve setting they cannot.

    Args:
        vertices: ``(N, 3)`` diffraction-space coordinates.
        faces: ``(M, 3)`` triangle indices.
        is_xz_symmetric: Whether the geometry is a half vessel.
        omega_max: Highest frequency in the grid [rad/s].
        g: Gravitational acceleration [m/s2].

    Returns:
        The lid position [m], **strictly negative**, or ``None`` when the
        formula has no answer.

        ``None`` is not a failure. ``arctanh(pi*g*p/omega_max**2)`` needs
        ``pi*g*p < omega_max**2``, and outside that domain there is no answer --
        which physically means *there are no irregular frequencies in this
        range and no lid is needed*. Long periods are low frequencies, so it is
        the **long** end of a grid that leaves the domain.

    .. note::
        Capytaine does not return the NaN one would expect there. Its loop is
        ``z_lid = 0.0`` followed by ``z_lid = min(z_lid, z_lid_comp)``, and
        ``min(0.0, nan)`` is ``0.0`` in Python -- the comparison is false, so
        the first argument wins. Out of domain it therefore hands back
        **zero**, which is a valid-looking instruction to put a lid *on the
        free surface*: a real setting, with real cost, that the user did not
        ask for and that Capytaine still considers experimental.

        That is why the test here is ``z >= 0`` and not ``isfinite``. A genuine
        answer is strictly negative -- ``-arctanh(x)/(pi*p)`` with ``0 < x < 1``
        cannot be anything else -- so zero can only mean the minimum never
        moved. Measured against Capytaine 2.3.1, not read off the docs.
    """
    mesh = to_capytaine_mesh(vertices, faces, is_xz_symmetric=is_xz_symmetric, name="lid_probe")
    with np.errstate(invalid="ignore", divide="ignore"):
        z = mesh.lowest_lid_position(float(omega_max), g=g)
    return None if not np.isfinite(z) or z >= 0.0 else float(z)


def make_problems(body: cpt.FloatingBody, settings: SolveSettings) -> list:
    """Every problem the settings call for, **grouped by frequency**.

    Ordering is not cosmetic. Capytaine's influence-matrix cache holds exactly
    one entry, and every problem at one frequency shares those matrices, so
    keeping them adjacent is the difference between assembling the O(N^2)
    matrices once per frequency and once per problem.

    It is also **load-bearing**. ``BEMSolver.solve_all`` sorts the problems it
    is given -- by ``(body, free_surface, water_depth, omega, ...)``, which
    happens to be frequency-major, so this ordering used to be a redundant
    agreement with Capytaine. :func:`solve` now drives the problems itself in
    order to report progress, so nothing re-sorts them and this is the only
    thing keeping the cache warm.

    Args:
        body: The floating body.
        settings: The physical conditions.

    Returns:
        A flat list of problems, frequency-major.
    """
    problems = []
    for omega in settings.omegas:
        common = {
            "body": body,
            "omega": omega,
            "rho": SOLVE_RHO_SI,
            "g": settings.g,
            "water_depth": settings.water_depth,
            "forward_speed": settings.forward_speed,
        }
        problems += [cpt.RadiationProblem(radiating_dof=dof, **common) for dof in body.dofs]
        problems += [
            cpt.DiffractionProblem(wave_direction=np.radians(direction), **common)
            for direction in settings.wave_directions
        ]
    return problems


def solve(
    vertices: FloatArray,
    faces: IntArray,
    *,
    is_xz_symmetric: bool,
    application_point: FloatArray,
    settings: SolveSettings,
    name: str = "vessel",
    progress: Progress | None = None,
) -> xr.Dataset:
    """Solve the radiation and diffraction problems and assemble one dataset.

    Radiation and diffraction go into a **single** dataset: ``mafredo`` needs
    added mass, damping *and* the force variables together, and the prototype's
    separate methods cannot be handed over as they are.

    Args:
        vertices: ``(N, 3)`` diffraction-space coordinates.
        faces: ``(M, 3)`` triangle indices.
        is_xz_symmetric: Whether the geometry is a half vessel.
        application_point: ``(3,)`` in diffraction space.
        settings: The physical conditions.
        name: Body name.
        progress: Called ``(done, total)`` after each **frequency**, counting
            from one, where ``total`` is ``len(settings.omegas)``. A solve runs
            for minutes, so anything driving it needs to say so.

            Per frequency and not per problem, because the influence matrices
            are cached across a frequency's problems: the first does the work
            and the rest are nearly free, so a per-problem count reads as a
            hang followed by a jump (spec 06 section 6.5.1).

            **Raising from it cancels the solve.** The exception propagates out
            of this function untouched and nothing is stored, which makes a
            flag set from another thread a complete cancel mechanism with no
            machinery of its own. It therefore stops at a **frequency**
            boundary. Finer than that is what the worker pool buys: a single
            problem is a Fortran call that cannot be interrupted at all.

    Returns:
        A dataset carrying ``added_mass``, ``radiation_damping`` and (when wave
        directions were given) ``excitation_force``. The Froude-Krylov and
        diffraction components are checked and then dropped -- only the
        excitation is needed downstream, and dropping them removes a third of
        the complex data from storage.

    Raises:
        SolverError: If the excitation identity does not hold, which means
            something has gone structurally wrong in the chain.
    """
    body = build_body(
        vertices,
        faces,
        is_xz_symmetric=is_xz_symmetric,
        application_point=application_point,
        lid_z=settings.lid_z,
        lid_radius=settings.lid_radius,
        name=name,
    )

    problems = make_problems(body, settings)
    dataset = cpt.assemble_dataset(_solve_each(problems, progress))

    _check_excitation_identity(dataset)
    return dataset.drop_vars(
        [v for v in ("Froude_Krylov_force", "diffraction_force") if v in dataset],
    )


def _solve_each(problems: list, progress: Progress | None) -> list:
    """Drive the problems, reporting once per **frequency**.

    ``BEMSolver.solve_all`` is not used because it offers no progress hook and
    re-sorts its input. Two things it does have to be reproduced:

    - **The pre-flight warnings.** Capytaine checks the whole problem set
      against the mesh resolution and the estimated first irregular frequency,
      and names the offending frequencies. Both are worth more than our own
      resolution estimate and are run here, once, over every problem. They are
      private methods, so ``test_solver.py`` asserts the warnings still reach a
      caller -- a rename in a future Capytaine has to fail loudly rather than
      silently take them away.
    - **Skipping the per-problem check**, which would otherwise repeat the same
      warning once per problem.

    ``solve`` is called rather than ``_solve_and_catch_errors``: a problem that
    fails should stop the run, not become a ``FailedResult`` that reaches
    storage as a database full of NaN.

    **Per frequency, not per problem** (spec 06 section 6.5.1, measured). The
    influence matrices are assembled once per frequency and cached for the rest
    of that frequency's problems, so the first problem in a group does nearly
    all the work and the remaining seven or forty finish immediately. A
    per-problem count reports that as a hang followed by a glitch.
    """
    solver = cpt.BEMSolver()
    cpt.BEMSolver._check_wavelength_and_mesh_resolution(problems)
    cpt.BEMSolver._check_wavelength_and_irregular_frequencies(problems)

    groups = [list(group) for _, group in groupby(problems, key=lambda p: float(p.omega))]
    _check_grouping(groups, problems)

    results = []
    for done, group in enumerate(groups, start=1):
        results += [solver.solve(problem, _check_wavelength=False) for problem in group]
        if progress is not None:
            progress(done, len(groups))
    return results


def _check_grouping(groups: list, problems: list) -> None:
    """Confirm each frequency is one contiguous run.

    ``groupby`` only groups *adjacent* equal keys, so a frequency appearing in
    two places would silently become two groups -- overstating the progress
    total and, far worse, rebuilding the O(N^2) matrices for it. That is the
    property :func:`make_problems` exists to provide, checked rather than
    assumed now that nothing downstream re-sorts.
    """
    if len({float(p.omega) for p in problems}) != len(groups):
        raise SolverError(
            f"{len(groups)} frequency groups for {len({float(p.omega) for p in problems})} "
            "distinct frequencies, so the problems are not frequency-major. Every "
            "repeat of a frequency reassembles the influence matrices for it"
        )


def _check_excitation_identity(dataset: xr.Dataset, rtol: float = 1e-8) -> None:
    """``excitation == Froude_Krylov + diffraction``.

    A free correctness check on the whole chain: Capytaine computes all three
    whether or not we keep them, so this costs nothing and is the cheapest
    signal in this module that something is structurally wrong. Run **before**
    the components are dropped, because afterwards it cannot be run at all.
    """
    needed = {"excitation_force", "Froude_Krylov_force", "diffraction_force"}
    if not needed <= set(dataset.data_vars):
        return  # radiation-only solve: nothing to check

    excitation = dataset["excitation_force"].values
    parts = dataset["Froude_Krylov_force"].values + dataset["diffraction_force"].values

    if not np.allclose(excitation, parts, rtol=rtol):
        worst = float(np.abs(excitation - parts).max())
        raise SolverError(
            "excitation_force != Froude_Krylov_force + diffraction_force "
            f"(worst absolute difference {worst}). Capytaine computes all three "
            "from the same solve, so a mismatch means the dataset assembly or "
            "the problem set is wrong, not the physics"
        )


def solver_provenance(dataset: xr.Dataset) -> tuple[str, str]:
    """The solver name and version that actually ran.

    Taken from the dataset attributes rather than hard-coded, so a library
    always records what produced it.
    """
    return "Capytaine", str(dataset.attrs.get("capytaine_version", "unknown"))
