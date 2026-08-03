"""Three commands: create a condition, add a mesh, run a calculation.

That is the whole surface. End users work in the UI; anything more than these
three is the Python package used directly; batching is running the command
again. See the pylot specification, ``10_cli.md`` for why the scope is a decision rather than
a first cut.

Built on ``argparse`` -- three commands do not justify a dependency.

**This module holds no logic.** It parses arguments, converts degrees and
periods at the boundary, and prints. Everything it does is one call on
:class:`~pylot_bem.api.Pylot`; when it started growing its own physics -- the
resolution limit, the panel-count doubling, the diffraction-space conversion --
that was the signal those belonged in the API instead. It is kept thin on
purpose, as a check that the API is complete: anything the CLI has to work out
for itself, every other caller would have to work out too.
"""

import argparse
import sqlite3
import sys
from collections.abc import Sequence

import numpy as np
from pylot_db.storage import LibraryError

from pylot_bem.angles import slope_from_degrees
from pylot_bem.api import Pylot
from pylot_bem.estimates import format_memory, shortest_reliable_period, solved_panels
from pylot_bem.mesh_pipeline import MeshPipelineError
from pylot_bem.solver import SolverError, SolveSettings

__all__ = ["main"]


class UsageError(Exception):
    """The arguments were understood but cannot be acted on."""


def parse_range(text: str, *, what: str) -> list[float]:
    """Read ``START:STOP:STEP`` or a comma-separated list.

    Args:
        text: The argument as typed.
        what: Name used in error messages.

    Returns:
        The values, ascending, with duplicates removed.

    Raises:
        UsageError: If the text is not a range or a list, or is empty.
    """
    try:
        if ":" in text:
            parts = [float(p) for p in text.split(":")]
            if len(parts) != 3:
                raise UsageError(f"{what} range must be START:STOP:STEP, got {text!r}")
            start, stop, step = parts
            if step <= 0:
                raise UsageError(f"{what} step must be positive, got {step}")
            # inclusive of STOP when it lands on the grid, within rounding
            count = int(np.floor((stop - start) / step + 1e-9)) + 1
            values = [start + i * step for i in range(max(count, 0))]
        else:
            values = [float(p) for p in text.split(",") if p.strip()]
    except ValueError as exc:
        raise UsageError(f"{what} must be numbers, got {text!r}") from exc

    values = sorted(set(values))
    if not values:
        raise UsageError(f"{what} is empty")
    return values


def _add_condition(library: Pylot, args: argparse.Namespace) -> None:
    condition = library.create_condition(
        # Degrees at the boundary, slopes everywhere inside (pylot-db's spec 01 section 7).
        # Through the shared helper, not inline: this was its own copy of the
        # conversion, and it was wrong in the same way twice over.
        trim=slope_from_degrees(args.trim),
        heel=slope_from_degrees(args.heel),
        z_origin=args.z_origin,
        label=args.label,
        condition_id=args.id,
    )
    point = condition.application_point

    print(f"condition {condition.id}")
    print(f"  z_origin        {condition.z_origin:g} m")
    print(f"  heel, trim      {args.heel:g}, {args.trim:g} deg")
    print(f"  application pt  ({point[0]:.3f}, {point[1]:.3f}, {point[2]:.3f}) m, vessel-local")


def _add_mesh(library: Pylot, args: argparse.Namespace) -> None:
    mesh = library.create_mesh(args.condition, pct=args.pct, iterations=args.iterations, mesh_id=args.id)
    half = " (half vessel, mirrored by the solver)" if mesh.is_xz_symmetric else ""

    print(f"mesh {mesh.id} for condition {mesh.condition_id}")
    print(f"  panels          {len(mesh.faces)}{half}")
    print(f"  memory          {format_memory(solved_panels(mesh))} per worker")
    print(f"  reliable above  {shortest_reliable_period(mesh.vertices, mesh.faces):.2f} s period")


def _run_solve(library: Pylot, args: argparse.Namespace) -> None:
    mesh = library.mesh(args.mesh)

    periods = parse_range(args.periods, what="--periods")
    directions = parse_range(args.directions, what="--directions") if args.directions else []
    settings = SolveSettings(
        omegas=tuple(2 * np.pi / period for period in periods),
        wave_directions=tuple(directions),
        water_depth=args.depth,
        g=args.g,
        forward_speed=args.speed,
        lid_z=_lid_z(args),
    )

    limit = shortest_reliable_period(mesh.vertices, mesh.faces)
    print(f"solving mesh {mesh.id}")
    print(f"  periods         {len(periods)}: {min(periods):g} to {max(periods):g} s")
    print(f"  directions      {len(directions)}")
    print(f"  depth           {args.depth} m")
    print(f"  speed, g        {args.speed} m/s, {args.g} m/s2")
    print("  density         stored per unit; applied when a database is delivered")
    print(f"  lid             {args.lid}")
    print(f"  problems        {len(settings.omegas) * (6 + len(directions))}")
    print(f"  memory          {format_memory(solved_panels(mesh))}")
    if min(periods) < limit:
        print(f"  WARNING         periods below {limit:.2f} s exceed this mesh's resolution")
    # Frequency-major, so ascending omega -- the reverse of ascending period.
    print(f"  order           longest period first ({max(periods):g} s)")
    print()

    result = library.run_solve(mesh, settings, result_id=args.id, progress=_report)
    print(f"\nresult {result.id} stored ({result.solver_name} {result.solver_version})")


def _report(done: int, total: int) -> None:
    """One line, rewritten in place. A solve is minutes of silence otherwise."""
    print(f"\r  frequency {done}/{total}", end="", flush=True)


def _lid_z(args: argparse.Namespace) -> float | None:
    if args.lid == "none":
        return None
    if args.lid == "surface":
        return 0.0
    if args.lid == "below":
        return args.lid_z
    raise UsageError("--lid auto is not implemented yet; use surface or below")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pylot",
        description=(
            "Build hydrodynamic databases. Three commands: create a floating "
            "condition, add a calculation mesh, run a solve. Anything more, use "
            "the Python package directly."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    condition = commands.add_parser("condition", help="create a floating condition")
    condition.add_argument("library", help="library file")
    condition.add_argument(
        "--z-origin",
        type=float,
        required=True,
        dest="z_origin",
        help="height of the vessel origin above the waterplane [m]; negative when submerged. "
        "This is NOT the naval draft",
    )
    condition.add_argument("--heel", type=float, default=0.0, help="heel [degrees]")
    condition.add_argument("--trim", type=float, default=0.0, help="trim [degrees]")
    condition.add_argument("--id", default=None, help="identifier; generated when omitted")
    condition.add_argument("--label", default="", help="display name; never parsed")
    condition.set_defaults(handler=_add_condition)

    mesh = commands.add_parser("mesh", help="add a calculation mesh")
    mesh.add_argument("library", help="library file")
    mesh.add_argument("--condition", required=True, help="condition id")
    mesh.add_argument("--pct", type=float, default=2.0, help="regrid target [%%]; lower is finer")
    mesh.add_argument("--iterations", type=int, default=20, help="remeshing iterations")
    mesh.add_argument("--id", default=None, help="identifier; generated when omitted")
    mesh.set_defaults(handler=_add_mesh)

    run = commands.add_parser("solve", help="run a calculation")
    run.add_argument("library", help="library file")
    run.add_argument("--mesh", required=True, help="mesh id")
    run.add_argument("--periods", required=True, help="wave periods [s]: START:STOP:STEP or a comma list")
    run.add_argument(
        "--directions",
        default=None,
        help="wave directions [degrees], direction of travel; omit for radiation only",
    )
    run.add_argument("--depth", type=float, default=np.inf, help="water depth [m]; omit for infinite")
    run.add_argument("--speed", type=float, default=0.0, help="forward speed [m/s]")
    run.add_argument("--g", type=float, default=9.81, help="gravity [m/s2]")
    run.add_argument(
        "--lid",
        choices=("none", "surface", "below", "auto"),
        default="none",
        help="irregular-frequency removal",
    )
    run.add_argument("--lid-z", type=float, default=-0.1, dest="lid_z", help="lid position [m]")
    run.add_argument("--id", default=None, help="identifier; generated when omitted")
    run.set_defaults(handler=_run_solve)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command.

    Returns:
        ``0`` done, ``1`` refused with a stated reason, ``2`` bad usage
        (argparse exits with that itself).
    """
    args = build_parser().parse_args(argv)

    try:
        with Pylot.open(args.library) as library:
            args.handler(library, args)
    except KeyboardInterrupt:
        # Nothing is written until a solve finishes, so an interrupt leaves the
        # library untouched. The GUI can offer to keep a partial result because
        # there is someone to ask; here there is not.
        print("\ninterrupted; nothing was written", file=sys.stderr)
        return 1
    except sqlite3.IntegrityError:
        print(
            f"error: the id {args.id!r} is already used in {args.library}. Ids are refused, never replaced",
            file=sys.stderr,
        )
        return 1
    except (LibraryError, MeshPipelineError, SolverError, UsageError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
