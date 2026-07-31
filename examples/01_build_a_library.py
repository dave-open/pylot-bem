"""Build a library from a hull file: the whole write path.

    uv run python examples/01_build_a_library.py

Creates ``examples/output/tanker.pylot`` with three drafts, each meshed and
solved. Example 02 reads it, so run this one first.

Deliberately coarse -- it finishes in seconds so you can change a number and
run it again. For a real library use ``pct=2.0, iterations=20`` (the defaults)
and a frequency grid that covers the periods you care about.
"""

import time
from pathlib import Path

import numpy as np

from pylot_bem import Pylot, SolveSettings, influence_matrix_bytes, shortest_reliable_period, solved_panels

# --- edit these -----------------------------------------------------------

HULL = Path(__file__).parents[1] / "tests" / "assets" / "tanker.stl"
SCALE = 1.0  # 0.001 if your model is drawn in millimetres

# Where the vessel origin sits. There is no way to recover this later, and
# every condition in the library is meaningless without it.
ORIGIN = "stern, centerline, keel"

# A declaration, not a measurement. Nothing can derive it: the tanker's own
# tessellation is not mirrored even though the surface it describes is
# symmetric to under a millimetre.
IS_XZ_SYMMETRIC = True

# z of the vessel origin above the waterplane, in metres. Negative for a
# normally floating vessel. NOT the naval draft -- the two differ by wherever
# the origin sits, which here is the keel, so these happen to coincide.
Z_ORIGINS = {"ballast": -5.0, "design": -12.0, "loaded": -18.0}

DIRECTIONS = [0.0, 45.0, 90.0, 135.0, 180.0]  # degrees, direction of travel

MESH = {"pct": 8.0, "iterations": 5}  # coarse, so this finishes quickly

# A coarse mesh cannot resolve short waves. The script checks these against
# shortest_reliable_period below -- drop one to 8 s to see what happens.
PERIODS = [12.0, 16.0, 20.0]  # seconds

# --------------------------------------------------------------------------

OUTPUT = Path(__file__).parent / "output"
LIBRARY = OUTPUT / "tanker.pylot"


def main() -> None:
    OUTPUT.mkdir(exist_ok=True)
    LIBRARY.unlink(missing_ok=True)  # a library is never overwritten in place

    # 1. Create -----------------------------------------------------------
    #
    # scale is the only unit conversion in the whole system. Everything after
    # this point is metres.
    library = Pylot.create_new(
        LIBRARY,
        HULL,
        ORIGIN,
        is_xz_symmetric=IS_XZ_SYMMETRIC,
        scale=SCALE,
        description="Built by examples/01_build_a_library.py",
    )

    lo, hi = library.base_shape.bounds
    print(f"{library.info.vessel_name}: {len(library.base_shape.faces)} faces")
    print(f"  extent        {hi[0] - lo[0]:.1f} x {hi[1] - lo[1]:.1f} x {hi[2] - lo[2]:.1f} m")
    print(f"  origin        {library.info.origin_description}")

    # 2. Surface probes ---------------------------------------------------
    #
    # Matching scores a condition by placing these on the vessel and reading
    # how far each one ends up from the water surface. The default four are
    # the bounding-box corners, which is usually what you want -- as widely
    # spread as the hull allows. Add your own where the corners sit in open
    # water, as they would on a semi-submersible.
    library.add_probe(x=0.5 * (lo[0] + hi[0]), y=0.0)
    print(f"  probes        {len(library.probe_xy)}")

    # 3. Conditions -------------------------------------------------------
    #
    # heel and trim are SLOPES here, not degrees -- np.tan(np.radians(deg)).
    # Degrees appear only in the CLI and the UI. The application point is
    # derived from the submerged geometry; you never supply it.
    print()
    for name, z_origin in Z_ORIGINS.items():
        condition = library.create_condition(z_origin=z_origin, condition_id=name, label=name.title())
        point = condition.application_point
        print(f"condition {name:9} z_origin {z_origin:6.1f} m   application point ({point[0]:.2f}, {point[1]:.2f}, {point[2]:.2f}) vessel-local")

    # 4. Meshes -----------------------------------------------------------
    #
    # Symmetry is derived from the base shape AND the condition's heel, so a
    # heeled condition always gets a full mesh. You cannot get this wrong.
    print()
    for name in Z_ORIGINS:
        mesh = library.create_mesh(name, **MESH, mesh_id=f"{name}-mesh")
        panels = solved_panels(mesh)
        print(
            f"mesh      {mesh.id:14} {len(mesh.faces):4} faces"
            f"{' (half vessel)' if mesh.is_xz_symmetric else ' (full vessel)'}"
            f"   {panels} panels, {influence_matrix_bytes(panels) / 1e6:.0f} MB"
            f", reliable above {shortest_reliable_period(mesh.vertices, mesh.faces):.1f} s"
        )

    # 5. Solve ------------------------------------------------------------
    #
    # One SolveSettings drives the solve AND the metadata stored against the
    # result, so the two cannot disagree. Frequencies are omega [rad/s];
    # periods in seconds are a UI convention, converted here.
    #
    # Note what is NOT here: a water density. Results scale exactly linearly
    # with it, so every solve runs at 1 t/m3 and the density is applied when a
    # database is delivered. One library then serves salt water, fresh water
    # and anything else -- see example 02.
    settings = SolveSettings(
        omegas=tuple(2 * np.pi / period for period in PERIODS),
        wave_directions=tuple(DIRECTIONS),
        water_depth=np.inf,
        g=9.81,
    )

    # Check the grid against the meshes before spending anything on it. A
    # period below a mesh's limit still solves, and the answer is wrong by an
    # amount nothing downstream can detect -- Capytaine will say so, loudly,
    # once the solve is already under way.
    print()
    limit = max(shortest_reliable_period(m.vertices, m.faces) for m in library.meshes())
    if min(PERIODS) < limit:
        print(f"WARNING       {min(PERIODS):.1f} s is below the coarsest mesh's limit of {limit:.1f} s")
    else:
        print(f"grid          {min(PERIODS):.0f}-{max(PERIODS):.0f} s, all above the coarsest mesh's limit of {limit:.1f} s")

    print()
    for name in Z_ORIGINS:
        started = time.perf_counter()
        result = library.run_solve(
            f"{name}-mesh",
            settings,
            result_id=f"{name}-result",
            # Called once per frequency, not once per problem: the influence
            # matrices are cached across a frequency's problems, so the first
            # does nearly all the work.
            progress=lambda done, total, n=name: print(f"\r  {n:9} frequency {done}/{total}", end="", flush=True),
        )
        print(f"\r  {name:9} solved {len(result.omegas)} frequencies x {len(result.wave_directions)} directions"
              f" in {time.perf_counter() - started:.1f} s")

    # 6. Check what came out ----------------------------------------------
    print()
    findings = library.validate()
    print(f"validate      {findings or 'clean'}")

    for view in library.databases():
        state = "usable" if view.usable else f"NOT usable: {view.conflicts or view.incomplete}"
        print(f"database      {view.key.condition_id:9} {len(view.coverage)} frequencies, {state}")

    library.close()
    print(f"\nwritten to    {LIBRARY}")
    print("next          uv run python examples/02_match_and_deliver.py")


if __name__ == "__main__":
    main()
