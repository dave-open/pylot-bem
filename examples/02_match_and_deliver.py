"""Match a vessel's pose to a stored condition and get a database out.

    uv run python examples/02_match_and_deliver.py

This is the **runtime** side -- what a simulation does every time it needs
hydrodynamics for a vessel that is floating somewhere in particular.

Note the import: ``pylot_db`` only. No capytaine, no pymeshup, no DAVE. A
library is built once on a machine with the solver installed and read
everywhere else. That split is enforced by a test, not by convention.

Run ``01_build_a_library.py`` first.
"""

from pathlib import Path

import numpy as np
from pylot_db import Library, condition_from_global, decompose, transform

LIBRARY = Path(__file__).parent / "output" / "tanker.pylot"

# How the vessel is floating. Three numbers -- that is the whole of what a
# match depends on. heel and trim are SLOPES, not degrees.
Z_ORIGIN = -11.6
HEEL = 0.0
TRIM = 0.004

# The physical boundary conditions of the simulation. These are HARD FILTERS,
# not preferences: a database computed at a different water depth is not a
# worse match, it is an invalid one.
WATER_DEPTH = np.inf
FORWARD_SPEED = 0.0

# Density is NOT a filter. Results are stored per unit density and scaled when
# a database is delivered, so one library serves every density -- it selects
# nothing and scales everything.
RHO = 1.025  # t/m3


def main() -> None:
    if not LIBRARY.exists():
        raise SystemExit(f"{LIBRARY} not found -- run examples/01_build_a_library.py first")

    with Library.open(LIBRARY) as library:
        print(f"{library.info.vessel_name}: {len(library.conditions())} conditions, {len(library.results())} results")
        print(f"origin        {library.info.origin_description}")

        # 1. Rank -----------------------------------------------------------
        #
        # Nothing is dropped for scoring badly and there is no acceptance
        # threshold: choosing among the candidates is your business, not the
        # library's.
        ranking = library.select(
            z_origin=Z_ORIGIN,
            heel=HEEL,
            trim=TRIM,
            water_depth=WATER_DEPTH,
            forward_speed=FORWARD_SPEED,
        )

        print(f"\nvessel        z_origin {Z_ORIGIN:.2f} m, heel {HEEL:+.4f}, trim {TRIM:+.4f} (slopes)")

        # max_error is a MAGNITUDE. The signed error at worst_probe is the one
        # that tells you which way the mismatch runs, so print that.
        print("  condition   rms [m]   worst probe    error [m]   usable")
        for candidate in ranking.candidates:
            signed = candidate.probe_errors[candidate.worst_probe]
            print(
                f"  {candidate.condition.id:11} {candidate.rms_error:7.3f}   "
                f"{candidate.worst_probe:11}   {signed:+9.3f}   "
                f"{'yes' if candidate.usable else candidate.reason}"
            )

        best = ranking.best
        print(f"\nbest          {best.condition.id}")
        print(f"  per probe   {np.round(best.probe_errors, 3).tolist()} m")
        print("              positive means the probe sits above the water surface")

        # 2. Deliver --------------------------------------------------------
        #
        # Built on demand, not during ranking: a match view lists every
        # candidate and you open one, so assembling a database per row would
        # make browsing cost the size of the whole library.
        selection = library.deliver(best, rho=RHO)
        hyddb = selection.hyddb

        # Already know which condition you want? Skip the ranking entirely --
        # library.hyddb(condition, rho=1.025) assembles it directly. deliver(rho=1.025) is for when
        # matching chose for you, and it also carries the application point.
        direct = library.hyddb(best.condition.id, rho=RHO)
        assert np.allclose(direct.amass(direct.frequencies[0]), hyddb.amass(hyddb.frequencies[0]))

        print(f"\ndatabase      {type(hyddb).__name__} from {best.key.condition_id}")
        print(f"  omegas      {np.round(hyddb.frequencies, 4).tolist()} rad/s")
        print(f"  directions  {np.round(hyddb.wave_directions, 1).tolist()} deg, direction of travel")
        print(f"  amass       {hyddb.amass(hyddb.frequencies[0]).shape} matrix in t and t.m2, mafredo dof order")
        print(f"  force       {hyddb.force(hyddb.frequencies[0], 90.0).shape} complex, kN and kN.m per m of wave")
        print("              (the example mesh is deliberately coarse -- shapes, not values)")

        # Where the forces apply, in VESSEL coordinates -- the frame you place
        # things in. The phase origin is separate and is metadata mafredo
        # carries: it says where the incoming wave phase is referenced, which
        # is the diffraction origin, not this point.
        print(f"\n  applied at  {np.round(selection.application_point, 3).tolist()} m, vessel-local")
        print(f"  phase org   {np.round(hyddb.phase_origin, 3).tolist()} m, relative to that point")

        # 3. Alignment offset ------------------------------------------------
        #
        # For when your vessel model and the library were built about different
        # origins. It corrects the stored point; it is not the point itself.
        shifted = library.deliver(best, rho=RHO, offset=(0.0, 0.0, 1.5))
        print(f"\n  +1.5 m z    {np.round(shifted.application_point, 3).tolist()} m")

        # 4. Density is a delivery choice, not a filter ----------------------
        #
        # Results are stored per unit density and scaled on the way out, so one
        # library serves salt water, fresh water and anything else. Nothing is
        # re-solved and there is no second database.
        fresh = library.deliver(best, rho=1.000).hyddb
        salt_heave = float(hyddb.amass(hyddb.frequencies[0])[2, 2])
        fresh_heave = float(fresh.amass(fresh.frequencies[0])[2, 2])

        print("\nfresh water   the same database, delivered at 1.000 t/m3")
        print(f"  heave am    {salt_heave:.0f} -> {fresh_heave:.0f} t")
        print(f"  ratio       {salt_heave / fresh_heave:.6f}  (= {RHO} / 1.000, exactly)")

        # 5. A hard filter that DOES exclude ---------------------------------
        #
        # Water depth and forward speed genuinely change the physics, so a
        # result computed at another one is invalid rather than approximate. An
        # empty ranking carries a reason instead of raising: failing to select
        # is an outcome to handle, not an error in the middle of a simulation.
        shallow = library.select(z_origin=Z_ORIGIN, water_depth=40.0, forward_speed=FORWARD_SPEED)
        print(f"\nin 40 m water {len(shallow.candidates)} candidates")
        print(f"              {shallow.reason}")

        # 6. If you are holding a transform ---------------------------------
        #
        # A simulation knows where the vessel *is*: a full 4x4, somewhere out
        # at sea on some heading. Project it onto a floating condition and hand
        # over what comes out.
        #
        # Yaw and horizontal position drop out exactly -- row 2 of a yaw matrix
        # is [0, 0, 1] and a horizontal move touches rows 0 and 1, so neither
        # can reach the only number matching reads. That is why select takes
        # three scalars rather than sixteen numbers of which it ignores
        # thirteen.
        c, s = np.cos(np.radians(125.0)), np.sin(np.radians(125.0))
        yaw = np.eye(4)
        yaw[0, 0], yaw[0, 1], yaw[1, 0], yaw[1, 1] = c, -s, s, c
        move = np.eye(4)
        move[:3, 3] = [1500.0, -800.0, 0.0]
        g = move @ yaw @ transform(trim=TRIM, heel=HEEL, z_origin=Z_ORIGIN)

        scalars = decompose(condition_from_global(g))
        elsewhere = library.select(**scalars._asdict(), water_depth=WATER_DEPTH, forward_speed=FORWARD_SPEED)

        print("\nat (1500, -800), heading 125 deg")
        # + 0.0 turns a negative zero back into zero, which is only cosmetic.
        print(f"  projected   z_origin {scalars.z_origin:.2f} m, heel {scalars.heel + 0.0:+.4f}, trim {scalars.trim:+.4f}")
        print(f"  matches     {elsewhere.best.condition.id}, rms {elsewhere.best.rms_error:.3f} m -- the same, exactly")


if __name__ == "__main__":
    main()
