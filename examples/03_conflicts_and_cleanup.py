"""Two results that disagree, and how you resolve it.

    uv run python examples/03_conflicts_and_cleanup.py

**This is the main loop of building a database, not an error path.** You solve
a grid, look at it, re-solve part of it with a finer mesh, and then decide
which run to keep. Where two results make competing claims about the same
frequency, that is unresolved work -- so the library reports it, names both
contributors, and produces nothing until you have chosen.

Nothing here picks a winner by rule. The previous implementation did, and
produced confident output from ambiguous input; that is the failure this whole
design exists to remove.

Self-contained: writes its own ``examples/output/conflict.pylot``.
"""

from pathlib import Path

import numpy as np
from pylot_db import AssemblyError

from pylot_bem import Pylot, SolveSettings

HULL = Path(__file__).parents[1] / "tests" / "assets" / "tanker.stl"
LIBRARY = Path(__file__).parent / "output" / "conflict.pylot"

COARSE_PERIODS = [14.0, 18.0, 22.0]
FINE_PERIODS = [18.0, 22.0, 26.0]  # overlaps the first run at 18 and 22
DIRECTIONS = [0.0, 90.0]


def omegas(periods):
    return tuple(2 * np.pi / period for period in periods)


def main() -> None:
    LIBRARY.parent.mkdir(exist_ok=True)
    LIBRARY.unlink(missing_ok=True)

    library = Pylot.create_new(LIBRARY, HULL, "stern, centerline, keel", is_xz_symmetric=True)
    library.create_condition(z_origin=-12.0, condition_id="design")

    # Two meshes at the same condition. Solving one grid on each is entirely
    # legitimate -- a database may span meshes, and often should: a coarse
    # mesh for long waves and a fine one for short.
    coarse = library.create_mesh("design", pct=10.0, iterations=5, mesh_id="coarse")
    fine = library.create_mesh("design", pct=6.0, iterations=5, mesh_id="fine")
    print(f"meshes        coarse {len(coarse.faces)} faces, fine {len(fine.faces)} faces")

    library.run_solve(coarse, SolveSettings(omegas=omegas(COARSE_PERIODS), wave_directions=tuple(DIRECTIONS)),
                      result_id="run-coarse")
    library.run_solve(fine, SolveSettings(omegas=omegas(FINE_PERIODS), wave_directions=tuple(DIRECTIONS)),
                      result_id="run-fine")
    print(f"solved        run-coarse at {COARSE_PERIODS} s")
    print(f"              run-fine   at {FINE_PERIODS} s")

    # 1. What the library says ---------------------------------------------
    view = library.databases()[0]
    print(f"\ndatabase      {view.key.condition_id}: {len(view.coverage)} frequencies from {list(view.result_ids)}")
    print(f"  usable      {view.usable}")

    print("\n  omega    period   radiation        diffraction")
    for coverage in view.coverage:
        marker = "  <- conflict" if coverage.conflicted else ""
        print(
            f"  {coverage.omega:.4f}  {2 * np.pi / coverage.omega:5.1f} s   "
            f"{','.join(coverage.radiation):22} {','.join(coverage.diffraction):22}{marker}"
        )

    # Conflicts and gaps are reported separately because the remedies are
    # different: a conflict is a decision to make, a gap is work still to do.
    print(f"\n  conflicts   {[c.describe() for c in view.conflicts]}")
    print(f"  incomplete  {[c.describe() for c in view.incomplete]}")

    for finding in library.validate():
        print(f"  validate    {finding}")

    # 2. Nothing comes out until it is resolved ----------------------------
    try:
        library.assemble(view.key, rho=1.025)
    except AssemblyError as exc:
        print(f"\nassemble      refused: {str(exc)[:120]}...")

    # Matching still ranks it -- hiding a conflicted condition would only make
    # it harder to understand why nothing was selected.
    candidate = library.select(z_origin=-12.0, water_depth=np.inf, forward_speed=0.0).best
    print(f"select        ranked it anyway: rms {candidate.rms_error:.3f} m, usable {candidate.usable}")

    # 3. Compare, then choose ----------------------------------------------
    #
    # The runs were expensive, so look at what actually differs before
    # deleting either. Here the finer mesh is the one to keep.
    # result_dataset() gives you Capytaine's own dataset, which is SI -- kg,
    # not tonnes, and per unit density. Both conversions happen
    # in assemble(). Divide by 1000 here to compare like with like.
    overlap = sorted(set(omegas(COARSE_PERIODS)) & set(omegas(FINE_PERIODS)))
    print("\n  omega   period   heave added mass [t]")
    for omega in overlap:
        values = [
            float(
                library.result_dataset(result_id)["added_mass"].sel(
                    omega=omega, radiating_dof="Heave", influenced_dof="Heave"
                )
            )
            / 1000.0
            for result_id in ("run-coarse", "run-fine")
        ]
        print(
            f"  {omega:.4f}  {2 * np.pi / omega:5.1f} s   coarse {values[0]:10.0f}   fine {values[1]:10.0f}"
            f"   {abs(values[1] / values[0] - 1):.1%} apart"
        )

    # 4. Resolve ------------------------------------------------------------
    #
    # Deletion is irreversible and the data was expensive, so ask what it
    # would do first. A result over a shorter grid is still a complete result.
    plan = library.plan_frequency_deletion("run-coarse", overlap)
    print("\nplan")
    for result_id, dropped in plan.frequencies_removed.items():
        print(f"  trim        {result_id}: drop {[round(2 * np.pi / w, 1) for w in dropped]} s")
    print(f"  remove      {list(plan.results_removed) or 'nothing'}")
    print("              (a result whose every frequency would go is removed outright --")
    print("               an empty result is not a state worth representing)")

    library.delete_frequencies("run-coarse", overlap)

    view = library.databases()[0]
    print(f"\nafter         {len(view.coverage)} frequencies, usable {view.usable}")
    print(f"  validate    {library.validate() or 'clean'}")

    hyddb = library.hyddb("design", rho=1.025)
    print(f"  assembled   {len(hyddb.frequencies)} frequencies: {np.round(2 * np.pi / hyddb.frequencies, 1).tolist()} s")
    print("              one from the coarse run, three from the fine one -- a database may span meshes")

    library.close()


if __name__ == "__main__":
    main()
