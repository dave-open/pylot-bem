"""Get the meshes out, get the database out, and look at them.

    uv run python examples/05_look_at_it.py

Three things the application needs and a script can use directly:

- **the meshes**, including the base shape placed at a floating condition, so
  a hull and its calculation mesh can be drawn in the same picture;
- **the database**, as a ``mafredo.Hyddb1``, straight from a condition;
- **a 3D view**, via ``vedo`` -- which is VTK, so the same geometry goes into
  a Qt widget with no plotter involved.

Opens a window and writes ``examples/output/design.png``. Run
``main(interactive=False)`` on a headless machine to get only the PNG.

Run ``01_build_a_library.py`` first.
"""

from pathlib import Path

import numpy as np

from pylot_bem import Pylot, solved_panels
from pylot_bem.plotting import show, show_condition, to_polydata, to_vedo

LIBRARY = Path(__file__).parent / "output" / "tanker.pylot"
SCREENSHOT = Path(__file__).parent / "output" / "design.png"

CONDITION = "design"
RHO = 1.025  # t/m3, applied on delivery -- the solve stored none


def main(interactive: bool = True) -> None:
    if not LIBRARY.exists():
        raise SystemExit(f"{LIBRARY} not found -- run examples/01_build_a_library.py first")

    with Pylot.open(LIBRARY) as library:
        # 1. The meshes -----------------------------------------------------
        #
        # The base shape is the hull as imported, in VESSEL coordinates. Its z
        # is measured from wherever the origin sits -- here the keel -- so on
        # its own it says nothing about where the water is.
        base = library.base_shape
        lo, hi = base.bounds
        print(f"base shape    {len(base.vertices)} vertices, {len(base.faces)} faces")
        print(f"  vessel z    {lo[2]:.1f} to {hi[2]:.1f} m (from the origin: {library.info.origin_description})")

        # Placed at a condition it lands in DIFFRACTION space, where z = 0 is
        # the waterplane. Now the numbers mean something: negative is wet.
        placed = library.base_shape_at(CONDITION)
        print(f"  placed z    {placed.vertices[:, 2].min():.1f} to {placed.vertices[:, 2].max():.1f} m (0 is the water surface)")
        print(f"  full hull   is_xz_symmetric={placed.is_xz_symmetric} -- nothing is cut, both sides are kept")

        # A calculation mesh is what was solved: wetted only, and half a vessel
        # when the condition allows it.
        mesh = library.meshes(CONDITION)[0]
        print(f"\nmesh {mesh.id:14} {len(mesh.faces)} faces, half vessel={mesh.is_xz_symmetric}")
        print(f"  z           {mesh.vertices[:, 2].min():.1f} to {mesh.vertices[:, 2].max():.1f} m -- wetted only")
        print(f"  y           {mesh.vertices[:, 1].min():.1f} to {mesh.vertices[:, 1].max():.1f} m -- the solver mirrors it")
        print(f"  solver sees {solved_panels(mesh)} panels")

        # 2. The database ---------------------------------------------------
        #
        # Straight from the condition. assemble() wants an AssemblyKey and
        # deliver() goes through matching; neither is what you want when you
        # already know which condition you mean.
        #
        # rho is required and is NOT a filter: results are stored per unit
        # density, so it selects nothing and scales everything. There is no
        # default, because a forgotten density is a database wrong by 2.5%
        # that looks entirely plausible.
        hyddb = library.hyddb(CONDITION, rho=RHO)
        print(f"\nhyddb         {type(hyddb).__name__} for {CONDITION}")
        print(f"  periods     {np.round(2 * np.pi / hyddb.frequencies, 1).tolist()} s")
        print(f"  directions  {np.round(hyddb.wave_directions, 1).tolist()} deg")
        print(f"  phase org   {np.round(hyddb.phase_origin, 2).tolist()} m")
        print(f"  amass       {hyddb.amass(hyddb.frequencies[0]).shape} in t and t.m2")

        # Same library, any density -- nothing is re-solved:
        fresh = library.hyddb(CONDITION, rho=1.000)
        print(f"  at 1.000    heave added mass x{float(hyddb.amass(hyddb.frequencies[0])[2, 2] / fresh.amass(fresh.frequencies[0])[2, 2]):.3f}")

        # A condition with databases at more than one depth or speed IS
        # ambiguous, and nothing picks for you -- pass the one you want:
        #     library.hyddb("design", rho=RHO, water_depth=50.0)

        # 3. Look at it -----------------------------------------------------
        #
        # Hull, waterplane, calculation mesh, probes and application point, all
        # in diffraction space -- the only frame in which putting them in one
        # picture means anything.
        print(f"\nwriting       {SCREENSHOT}")
        show_condition(library, CONDITION, interactive=interactive, screenshot=SCREENSHOT)

        # Any one mesh on its own, in whatever frame it happens to be in:
        if interactive:
            show(to_vedo(base, color="#8fa8bf"), title="base shape, vessel coordinates")

        # 4. For the UI -----------------------------------------------------
        #
        # vedo is VTK. This is what a Qt VTK widget renders -- hand it to a
        # vtkPolyDataMapper and no plotter is involved at all.
        polydata = to_polydata(mesh)
        print(f"\npolydata      {type(polydata).__name__}: {polydata.GetNumberOfPoints()} points, "
              f"{polydata.GetNumberOfCells()} cells")


if __name__ == "__main__":
    main()
