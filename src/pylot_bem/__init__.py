"""Write side of the hydrodynamic database.

Create libraries, floating conditions and calculation meshes; solve radiation
and diffraction problems with Capytaine in-process; assemble the results.

Depends on :mod:`pylot_db`, never the reverse.  Does not depend on DAVE.

:class:`Pylot` is the entry point and **is** a
:class:`~pylot_db.storage.Library`, so everything on the read side is on it
too::

    from pylot_bem import Pylot, SolveSettings

    d = Pylot.create_new("tanker.pylot", "tanker.stl", "stern, centerline, keel",
                         is_xz_symmetric=True)
    condition = d.create_condition(z_origin=-5.0)
    mesh = d.create_mesh(condition)
    result = d.run_solve(mesh, SolveSettings(omegas=[0.4, 0.5, 0.6]))

Looking at any of it is :mod:`pylot_bem.plotting`, which is **not** imported
here: it pulls in the whole of VTK, and the CLI has no use for that::

    from pylot_bem.plotting import show_condition

See ``docs/api.md`` for the reference and ``docs/spec/11_api.md`` for why.
"""

from pylot_bem.api import Pylot
from pylot_bem.estimates import influence_matrix_bytes, shortest_reliable_period, solved_panels
from pylot_bem.geometry import load_mesh_file
from pylot_bem.mesh_pipeline import (
    MeshGeometry,
    MeshPipelineError,
    application_point_for,
    build_mesh,
    check_full_mesh,
)
from pylot_bem.solver import Progress, SolverError, SolveSettings, solve, solver_provenance

__all__ = [
    "MeshGeometry",
    "MeshPipelineError",
    "Progress",
    "Pylot",
    "SolveSettings",
    "SolverError",
    "application_point_for",
    "build_mesh",
    "check_full_mesh",
    "influence_matrix_bytes",
    "load_mesh_file",
    "shortest_reliable_period",
    "solve",
    "solved_panels",
    "solver_provenance",
]
