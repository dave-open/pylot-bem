"""Many conditions, meshes and solves from one description.

Building a library one screen at a time is the right way to *explore* a vessel,
and the wrong way to fill in the forty drafts, three heels and five trims a
finished library needs. That is a night of unattended work, and unattended work
has requirements the interactive path does not:

- **one bad step must not end the run.** A condition whose ``z_origin`` lifts
  the hull clear of the water, a regrid that produces no faces, a solve that
  raises -- each is recorded and the batch moves on. A job that abandons 704
  conditions because the first was out of the water is worse than no job at all;
- **running it again must resume, not duplicate.** A condition already at those
  values is reused rather than added beside itself, a mesh at the same ``pct``
  and ``iterations`` is reused, and a solve whose frequencies a result already
  covers is skipped. So the answer to a night that ended early is to start the
  same job again;
- **the cost is known before it is incurred** (spec 09's fourth cross-cutting
  rule). :func:`plan` walks the whole job against the library and counts what it
  would create, without creating any of it -- and :meth:`BatchRun.run` then
  executes *that* plan, so the preview and the run cannot disagree.

The unit of the second half is a :class:`Band`: one mesh resolution and the
periods solved on it. Short waves need panels that long waves do not, so a real
library is meshed twice and each mesh carries the part of the frequency grid it
can resolve --

    1.0 %  ->   1, 2, 3, 4 s
    2.0 %  ->   5, 6, 7, 8, 9, 10, 12 s

which is one :class:`Band` per line, applied to every condition in the job.

Nothing here is a second implementation of anything. Conditions go through
:meth:`~pylot_bem.api.Pylot.create_condition`, meshes through
:meth:`~pylot_bem.api.Pylot.create_mesh`, and every solve through
:class:`~pylot_bem.pool.PoolSolve` and
:meth:`~pylot_bem.api.Pylot.store_result` -- the same path the Solve screen
takes, so a batched result is indistinguishable from one solved by hand.
"""

import json
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Self

import numpy as np
from pylot_db.assembly import OMEGA_TOLERANCE
from pylot_db.entities import CalculationMesh, FloatingCondition
from pylot_db.storage import LibraryError
from pylot_db.validation import CONDITION_TOLERANCE

from pylot_bem.angles import degrees_from_slope, slope_from_degrees
from pylot_bem.api import Pylot
from pylot_bem.estimates import format_memory, shortest_reliable_period, solved_panels
from pylot_bem.mesh_pipeline import MeshPipelineError
from pylot_bem.pool import PoolSolve, SolveOutcome, default_workers
from pylot_bem.solver import SolverError, SolveSettings, auto_lid_z

__all__ = [
    "JOB_SUFFIX",
    "JOB_VERSION",
    "LID_CHOICES",
    "TARGETS",
    "TARGET_ALL",
    "TARGET_GRID",
    "TARGET_LISTED",
    "Band",
    "BatchError",
    "BatchEvent",
    "BatchJob",
    "BatchOutcome",
    "BatchPlan",
    "BatchRun",
    "LibraryState",
    "PlannedCondition",
    "PlannedSolve",
    "format_bands",
    "job_from_dict",
    "job_to_dict",
    "load_job",
    "parse_bands",
    "parse_numbers",
    "plan",
    "save_job",
    "value_range",
]


class BatchError(Exception):
    """A job that cannot be read or cannot be run.

    Raised for a malformed description -- an unreadable band table, an empty
    grid, an unknown lid mode. **Never** raised for a step that failed: those
    are collected in :class:`BatchOutcome` and the run continues.
    """


#: Which conditions the bands apply to. :data:`TARGET_GRID` is the grid this
#: job describes -- *including* the entries that turned out to exist already,
#: which is what makes running the same job twice continue rather than skip
#: everything the second time.
TARGET_GRID = "grid"
TARGET_ALL = "all"
TARGET_LISTED = "listed"
TARGETS = (TARGET_GRID, TARGET_ALL, TARGET_LISTED)

#: The lid modes, as the Solve screen and the command line spell them. Carried
#: as a *mode* rather than as a position because ``auto`` has no position until
#: the mesh exists -- which in a batch is halfway through the run.
LID_CHOICES = ("none", "surface", "below", "auto")


def value_range(start: float, stop: float, step: float) -> tuple[float, ...]:
    """``start`` to ``stop`` inclusive, in steps of ``step``.

    Inclusive of ``stop`` when it lands on the grid within rounding, which is
    what makes *0.1 to 4.7 in steps of 0.1* the 47 values a reader counts
    rather than the 46 a naive ``arange`` returns.

    Args:
        start: First value.
        stop: Last value, included when the step lands on it.
        step: Spacing. Non-positive, or a ``stop`` below ``start``, gives just
            ``start`` -- a degenerate range is one value, not zero and not an
            error, so a half-typed dialog previews something sensible.

    Returns:
        The values, ascending, rounded to 12 decimals. Rounded because
        ``start + i * step`` on a tenth-metre grid produces ``-4.6000000000005``
        for the value a user typed as part of *0.1 steps*, and a ``z_origin``
        is stored exactly as given and read back for the life of the library.
        No physical quantity here is meaningful at 1e-12, so nothing real is
        lost.
    """
    if step <= 0 or stop < start:
        return (float(start),)
    count = int(np.floor((stop - start) / step + 1e-9)) + 1
    return tuple(round(start + i * step, 12) for i in range(max(count, 1)))


def parse_numbers(text: str, *, what: str) -> tuple[float, ...]:
    """Read a list of numbers, with ``lo..hi..step`` expanded.

    Commas, whitespace or both separate the values, so *-1, 0, 1* and *-1 0 1*
    are the same thing. Any item may instead be a range::

        4..20..0.5      the 33 values from 4 to 20

    Written ``..`` rather than the command line's ``START:STOP:STEP`` because a
    colon already separates a band from its periods and one character cannot
    mean both.

    Args:
        text: The field as typed.
        what: Name used in the error message.

    Returns:
        The values, ascending, with duplicates removed.

    Raises:
        BatchError: If an item is not a number or a range, or nothing is left.
    """
    values: list[float] = []
    for item in text.replace(",", " ").split():
        if ".." in item:
            parts = item.split("..")
            if len(parts) != 3:
                raise BatchError(f"{what}: a range is lo..hi..step, got {item!r}")
            try:
                low, high, step = (float(p) for p in parts)
            except ValueError as exc:
                raise BatchError(f"{what}: a range is lo..hi..step, got {item!r}") from exc
            if step <= 0:
                raise BatchError(f"{what}: the step of {item!r} must be positive")
            values.extend(value_range(low, high, step))
            continue
        try:
            values.append(float(item))
        except ValueError as exc:
            raise BatchError(f"{what}: {item!r} is not a number") from exc

    unique = sorted({round(v, 12) for v in values})
    if not unique:
        raise BatchError(f"{what} is empty")
    return tuple(unique)


@dataclass(frozen=True, slots=True)
class Band:
    """One mesh resolution and the periods solved on it.

    The pairing is the point. Panel size sets the shortest wave a mesh can
    resolve -- :func:`~pylot_bem.estimates.shortest_reliable_period` puts a
    number on it -- and solver cost is quadratic in the panel count, so a grid
    that reaches from 1 s to 12 s on one mesh either wastes hours at the long
    end or returns confident nonsense at the short one. A band says *these
    periods, on a mesh this fine*, and a job is a list of them.

    Attributes:
        pct: Regrid target as a percentage of the bounding-box diagonal, as
            :meth:`~pylot_bem.api.Pylot.create_mesh` takes it. Lower is finer.
        periods: Wave periods [s]. Converted to omega on the way to the solver;
            periods here because that is what a user has an opinion about.
        iterations: Isotropic remeshing iterations.
    """

    pct: float
    periods: tuple[float, ...]
    iterations: int = 20

    @property
    def omegas(self) -> tuple[float, ...]:
        """The periods as an ascending frequency grid [rad/s].

        Ascending omega is *descending* period: the solver is frequency-major
        and the pool submits in this order.
        """
        return tuple(sorted(2 * np.pi / period for period in self.periods))


def parse_bands(text: str, *, iterations: int = 20) -> tuple[Band, ...]:
    """Read the ``pct -> periods`` table.

    One band per line, written the way the job is written down::

        1 -> 1, 2, 3, 4
        2 -> 5, 6, 7, 8, 9, 10, 12

    ``:`` works as well as ``->``. Blank lines and anything after a ``#`` are
    ignored, so a job file can carry a note about why the bands are where they
    are.

    Args:
        text: The table as typed.
        iterations: Remeshing iterations, given to every band. One value for
            the whole table rather than a third column: it is a knob on the
            regrid that is almost never varied between two meshes of the same
            vessel, and a per-line value would make the common case wider to
            read for a case nobody has. :class:`Band` still carries it, because
            it belongs with ``pct`` -- the two together are what a mesh *is*.

    Returns:
        The bands, in the order written -- **not** sorted. The order is the
        order they are meshed and solved in, and a user who put the fine mesh
        first meant to get its results first.

    Raises:
        BatchError: If a line has no separator, or either side is unreadable.
    """
    bands = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue

        separator = "->" if "->" in line else ":" if ":" in line else ""
        if not separator:
            raise BatchError(
                f"line {number}: {line!r} has no separator. A band is "
                "'pct -> periods', for example '2 -> 5, 6, 7'"
            )
        left, right = line.split(separator, 1)

        try:
            pct = float(left.strip())
        except ValueError as exc:
            raise BatchError(f"line {number}: {left.strip()!r} is not a mesh pct") from exc
        if pct <= 0:
            raise BatchError(f"line {number}: a mesh pct must be positive, got {pct:g}")

        periods = parse_numbers(right, what=f"line {number}")
        if periods[0] <= 0:
            raise BatchError(f"line {number}: a period must be positive, got {periods[0]:g} s")
        bands.append(Band(pct=pct, periods=periods, iterations=iterations))

    if not bands:
        raise BatchError("no bands. Write one line per mesh, for example '2 -> 5, 6, 7'")
    return tuple(bands)


def format_bands(bands) -> str:
    """The inverse of :func:`parse_bands`, for filling the field in again."""
    return "\n".join(
        f"{band.pct:g} -> " + ", ".join(f"{period:g}" for period in band.periods) for band in bands
    )


@dataclass(frozen=True, slots=True)
class BatchJob:
    """Everything a batch does, as data.

    Two halves, and either may be empty. The grid
    (``z_origins`` × ``heels`` × ``trims``) creates conditions; the ``bands``
    mesh and solve them. A job with a grid and no bands only adds conditions; a
    job with bands and ``targets=``:data:`TARGET_ALL` only meshes and solves
    the conditions that are already there.

    The solve settings are here once, for the whole job, rather than per band:
    depth, gravity and forward speed are the *physical situation*, and results
    computed at different ones do not belong to the same database
    (pylot-db's spec 02 section 3). Only the frequency grid varies per band,
    which is exactly what a band is for.

        job = BatchJob(
            z_origins=value_range(-4.7, -0.1, 0.1),
            heels=tuple(slope_from_degrees(d) for d in (-1, 0, 1)),
            trims=tuple(slope_from_degrees(d) for d in (-2, -1, 0, 1, 2)),
            bands=(Band(1.0, (1, 2, 3, 4)), Band(2.0, (5, 6, 7, 8, 9, 10, 12))),
            wave_directions=tuple(float(d) for d in range(0, 180, 15)),
        )

    The bands are what a user writes as a two-line table; see
    :func:`parse_bands`.

    Attributes:
        z_origins: Heights of the vessel origin above the waterplane [m],
            **negative** when floating. Not the naval draft -- the two differ
            by wherever the origin sits on the hull, and there is no draft
            anywhere in pylot.
        heels: Heel **slopes**, not degrees. Convert at the boundary with
            :func:`~pylot_bem.angles.slope_from_degrees`.
        trims: Trim **slopes**, not degrees.
        bands: One mesh resolution and its periods, in the order to run them.
        targets: Which conditions the bands apply to -- :data:`TARGET_GRID` for
            the grid above, :data:`TARGET_ALL` for that grid *and* every other
            condition in the library, :data:`TARGET_LISTED` for
            ``condition_ids`` and nothing else.
        condition_ids: The conditions, when ``targets`` is
            :data:`TARGET_LISTED`.
        wave_directions: Wave directions [deg], direction of travel. Empty
            solves radiation only.
        water_depth: [m]. ``inf`` for infinite depth.
        g: Gravitational acceleration [m/s2].
        forward_speed: [m/s].
        lid: Irregular-frequency removal: one of :data:`LID_CHOICES`. ``auto``
            is resolved per mesh and per band, which is the one thing a batch
            can do that the command line cannot -- it has the mesh in hand.
        lid_z: Lid position [m], used when ``lid`` is ``"below"``.
        workers: Solver processes. ``None`` asks
            :func:`~pylot_bem.pool.default_workers`.
        omp_threads: OpenMP threads inside each worker.
        resume: Reuse a matching mesh and skip a solve a result already covers.
            On by default: the point of a batch is that running it again after
            a night that ended early continues rather than duplicates.
    """

    z_origins: tuple[float, ...] = ()
    heels: tuple[float, ...] = (0.0,)
    trims: tuple[float, ...] = (0.0,)
    bands: tuple[Band, ...] = ()
    targets: str = TARGET_GRID
    condition_ids: tuple[str, ...] = ()
    wave_directions: tuple[float, ...] = ()
    water_depth: float = np.inf
    g: float = 9.81
    forward_speed: float = 0.0
    lid: str = "none"
    lid_z: float = -0.1
    workers: int | None = None
    omp_threads: int = 1
    resume: bool = True

    def __post_init__(self) -> None:
        if self.targets not in TARGETS:
            raise BatchError(f"targets must be one of {TARGETS}, got {self.targets!r}")
        if self.lid not in LID_CHOICES:
            raise BatchError(f"lid must be one of {LID_CHOICES}, got {self.lid!r}")

    def settings_for(self, band: Band, lid_z: float | None) -> SolveSettings:
        """The job's physical settings over one band's frequency grid."""
        return SolveSettings(
            omegas=band.omegas,
            wave_directions=tuple(self.wave_directions),
            water_depth=self.water_depth,
            g=self.g,
            forward_speed=self.forward_speed,
            lid_z=lid_z,
        )

    def lid_z_for(self, mesh: CalculationMesh, band: Band) -> float | None:
        """Where the lid goes for this mesh and this band, or ``None``.

        ``auto`` is answered from the mesh and the band's highest frequency,
        which is why it is resolved here and not when the job is written: at
        that point neither exists. ``None`` back from
        :func:`~pylot_bem.solver.auto_lid_z` is not a failure -- it means there
        are no irregular frequencies in range and no lid is needed.
        """
        if self.lid == "none":
            return None
        if self.lid == "surface":
            return 0.0
        if self.lid == "below":
            return self.lid_z
        return auto_lid_z(
            mesh.vertices,
            mesh.faces,
            is_xz_symmetric=mesh.is_xz_symmetric,
            omega_max=max(band.omegas),
            g=self.g,
        )


#: What a saved job is called. Its own suffix rather than ``.json`` so the file
#: dialog can filter on it and so a folder of them reads as what it is -- the
#: body is ordinary JSON either way.
JOB_SUFFIX = ".pylotjob"

#: Bumped when the shape of a saved job changes incompatibly. A file that does
#: not carry it, or carries a version this build does not know, is refused with
#: a sentence rather than half-read -- the same rule the library file follows,
#: for the same reason: a job silently loaded as something other than what was
#: saved is a night spent solving the wrong thing.
JOB_VERSION = 1


def job_to_dict(job: BatchJob) -> dict:
    """A job as plain data, ready for :func:`json.dump`.

    Two things are **not** stored the way :class:`BatchJob` holds them, and both
    are deliberate:

    - **heel and trim are written in degrees.** A job file is read and edited by
      people, and degrees at every human-facing boundary is the rule everywhere
      else in pylot. The round trip is ``sin(asin(x))``, exact to about one ULP
      -- some five orders of magnitude tighter than the 1e-3 at which anything
      here decides two conditions are the same condition. The unit is in the
      key, so a reader cannot mistake one for the other.

      Rounded to 12 places on the way out, because ``asin`` does not quite give
      30 back for the sine of 30 and ``29.999999999999996`` in a file somebody
      typed *1* into reads as a bug in the file. Twelve places of a degree is
      four nanoarcseconds; nothing real is lost;
    - **infinite water depth is ``null``.** ``Infinity`` is what Python's JSON
      writes for it and is not valid JSON, so a file carrying it can be read
      back here and nowhere else.
    """
    return {
        "pylot_batch_job": JOB_VERSION,
        "z_origins": [float(z) for z in job.z_origins],
        "heels_deg": [round(degrees_from_slope(h), 12) for h in job.heels],
        "trims_deg": [round(degrees_from_slope(t), 12) for t in job.trims],
        "bands": [
            {
                "pct": band.pct,
                "iterations": band.iterations,
                "periods": [float(p) for p in band.periods],
            }
            for band in job.bands
        ],
        "targets": job.targets,
        "condition_ids": list(job.condition_ids),
        "wave_directions": [float(d) for d in job.wave_directions],
        "water_depth": None if np.isinf(job.water_depth) else float(job.water_depth),
        "g": job.g,
        "forward_speed": job.forward_speed,
        "lid": job.lid,
        "lid_z": job.lid_z,
        "workers": job.workers,
        "omp_threads": job.omp_threads,
        "resume": job.resume,
    }


def job_from_dict(data: dict) -> BatchJob:
    """The inverse of :func:`job_to_dict`.

    Every field is optional except the version marker: a job file with half of
    it hand-deleted loads as the defaults for what is missing, which is what
    makes one worth editing by hand. What is *present* and wrong is refused --
    ``targets`` and ``lid`` by :class:`BatchJob` itself, everything else here.

    Raises:
        BatchError: If the marker is missing or from another version, or a
            value cannot be read as what it has to be.
    """
    if not isinstance(data, dict) or "pylot_batch_job" not in data:
        raise BatchError(
            "this is not a pylot batch job — it has no 'pylot_batch_job' marker. "
            "A library is a .pylot file and is opened with File → Open library"
        )
    version = data["pylot_batch_job"]
    if version != JOB_VERSION:
        raise BatchError(
            f"this job file is version {version} and this build reads version {JOB_VERSION}"
        )

    def numbers(key: str) -> tuple[float, ...]:
        try:
            return tuple(float(v) for v in data.get(key, ()))
        except (TypeError, ValueError) as exc:
            raise BatchError(f"{key!r} must be a list of numbers") from exc

    try:
        bands = tuple(
            Band(
                pct=float(band["pct"]),
                periods=tuple(float(p) for p in band["periods"]),
                iterations=int(band.get("iterations", 20)),
            )
            for band in data.get("bands", ())
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise BatchError(
            "'bands' must be a list of {pct, periods, iterations} objects"
        ) from exc

    depth = data.get("water_depth")
    defaults = BatchJob()
    return BatchJob(
        z_origins=numbers("z_origins"),
        heels=tuple(slope_from_degrees(d) for d in numbers("heels_deg")) or defaults.heels,
        trims=tuple(slope_from_degrees(d) for d in numbers("trims_deg")) or defaults.trims,
        bands=bands,
        targets=str(data.get("targets", defaults.targets)),
        condition_ids=tuple(str(i) for i in data.get("condition_ids", ())),
        wave_directions=numbers("wave_directions"),
        water_depth=np.inf if depth is None else float(depth),
        g=float(data.get("g", defaults.g)),
        forward_speed=float(data.get("forward_speed", defaults.forward_speed)),
        lid=str(data.get("lid", defaults.lid)),
        lid_z=float(data.get("lid_z", defaults.lid_z)),
        workers=None if data.get("workers") is None else int(data["workers"]),
        omp_threads=int(data.get("omp_threads", defaults.omp_threads)),
        resume=bool(data.get("resume", defaults.resume)),
    )


# A list of nothing but numbers, put back on one line. `json.dumps(indent=2)`
# gives every element its own, which turns 47 drafts into 47 lines of one
# number and the file into something nobody scrolls through -- and the drafts
# and the periods are exactly the part worth editing by hand. Numbers cannot
# contain a quote, so this cannot reach inside a string, and an object or a
# nested list brings a brace or a bracket that stops the match.
_NUMBER_LIST = re.compile(r"\[[\s\d.,eE+-]*\]")


def _compact_number_lists(text: str) -> str:
    return _NUMBER_LIST.sub(lambda m: " ".join(m.group().split()), text)


def save_job(job: BatchJob, path: str | Path) -> Path:
    """Write a job to a file, and return where it went.

    JSON, one key per line, with the number lists kept on one line each -- so
    the file diffs, and so the half of it worth editing by hand can be edited
    by hand.

    Args:
        job: What to save.
        path: Where. :data:`JOB_SUFFIX` is added when there is no suffix at
            all, and never substituted for one the caller chose.

    Returns:
        The path written.
    """
    path = Path(path)
    if not path.suffix:
        path = path.with_suffix(JOB_SUFFIX)
    body = _compact_number_lists(json.dumps(job_to_dict(job), indent=2))
    path.write_text(body + "\n", encoding="utf-8")
    return path


#: A library begins with this, which is SQLite's own file header. Recognised
#: only to give the one wrong file anybody actually picks a useful answer --
#: it sits in the same folder, under a name one letter away.
_SQLITE_HEADER = b"SQLite format 3\x00"


def load_job(path: str | Path) -> BatchJob:
    """Read a job back.

    Raises:
        BatchError: If the file is not a job, is from another version, or
            cannot be read as JSON at all. The message names the file, because
            the usual mistake is picking the library next to it -- and that
            case is recognised and answered rather than reported as a decoding
            error about byte 98, which is true and of no use to anyone.
    """
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise BatchError(f"{path.name} could not be read: {exc}") from exc

    if raw.startswith(_SQLITE_HEADER):
        raise BatchError(
            f"{path.name} is a pylot library, not a batch job. A library is opened with "
            "File → Open library; a job is the small text file saved beside it"
        )
    try:
        data = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise BatchError(f"{path.name} is not a text file, so it is not a batch job") from exc
    except json.JSONDecodeError as exc:
        raise BatchError(f"{path.name} is not readable as JSON: {exc}") from exc
    return job_from_dict(data)


@dataclass(frozen=True, slots=True)
class PlannedCondition:
    """A condition the job will use: an existing one, or one to create.

    Attributes:
        z_origin: [m], negative when floating.
        heel: Heel slope.
        trim: Trim slope.
        existing_id: The condition already at these values, or blank when one
            will be created.
    """

    z_origin: float
    heel: float
    trim: float
    existing_id: str = ""

    @property
    def is_new(self) -> bool:
        return not self.existing_id


@dataclass(frozen=True, slots=True)
class PlannedSolve:
    """One band applied to one condition: a mesh, and a solve on it.

    Attributes:
        condition: Index into :attr:`BatchPlan.conditions`.
        band: The resolution and periods.
        mesh_id: A mesh already at this ``pct`` and ``iterations`` that will be
            reused, or blank when one will be built.
        covered_by: A result already covering every one of the band's
            frequencies on that mesh, or blank when the solve will run.
    """

    condition: int
    band: Band
    mesh_id: str = ""
    covered_by: str = ""

    @property
    def builds_mesh(self) -> bool:
        return not self.mesh_id

    @property
    def solves(self) -> bool:
        return not self.covered_by


@dataclass(frozen=True, slots=True)
class BatchPlan:
    """What a job would do to a library, before it does any of it.

    Produced by :func:`plan` and executed by :meth:`BatchRun.run`, which is the
    whole reason it is a value rather than a summary: the numbers on the screen
    and the work that then happens come from the same list, so the preview
    cannot promise something the run does not do.

    Attributes:
        conditions: Every condition the job touches, new and existing.
        steps: One per condition per band, in run order.
        directions: How many wave directions each solve carries, for the
            problem count.
    """

    conditions: tuple[PlannedCondition, ...] = ()
    steps: tuple[PlannedSolve, ...] = ()
    directions: int = 0

    @property
    def conditions_to_create(self) -> int:
        return sum(1 for c in self.conditions if c.is_new)

    @property
    def conditions_existing(self) -> int:
        return sum(1 for c in self.conditions if not c.is_new)

    @property
    def meshes_to_build(self) -> int:
        return sum(1 for step in self.steps if step.builds_mesh)

    @property
    def meshes_reused(self) -> int:
        return sum(1 for step in self.steps if not step.builds_mesh)

    @property
    def solves_to_run(self) -> int:
        return sum(1 for step in self.steps if step.solves)

    @property
    def solves_skipped(self) -> int:
        return sum(1 for step in self.steps if not step.solves)

    @property
    def problems(self) -> int:
        """Boundary-value problems the solver will run.

        Six radiation problems per frequency plus one per wave direction, the
        same count the Solve screen shows. It is the only honest measure of
        cost available before the meshes exist -- panel counts and memory come
        out of the regrid and cannot be known until it has run.
        """
        return sum(
            len(step.band.periods) * (6 + self.directions) for step in self.steps if step.solves
        )

    @property
    def total_steps(self) -> int:
        """Everything the run will report progress against."""
        return self.conditions_to_create + len(self.steps)

    @property
    def is_empty(self) -> bool:
        return not self.conditions_to_create and not self.meshes_to_build and not self.solves_to_run


@dataclass(frozen=True, slots=True)
class LibraryState:
    """What planning needs to know about a library, read once.

    Reading it is not free. A :class:`~pylot_db.entities.CalculationMesh`
    carries its geometry, so :meth:`~pylot_db.storage.Library.meshes` decodes
    every vertex and face array in the file -- and planning only wants ``pct``
    and ``iterations`` off each one. On a finished library that is a hundred
    megabytes to answer a question about two numbers.

    Which is fine once, and not fine on every keystroke: the batch screen
    re-plans as the grid is typed, so it reads this **once** and hands it back
    to :func:`plan` each time. Safe because that screen is modal and the only
    thing writing to the library while it is open is its own run -- after
    which it reads again.

    Attributes:
        conditions: Every condition in the library.
        meshes_by_condition: Meshes grouped by the condition they were built at.
        results_by_mesh: Results grouped by the mesh they were solved on.
    """

    conditions: tuple[FloatingCondition, ...]
    meshes_by_condition: dict[str, list[CalculationMesh]]
    results_by_mesh: dict[str, list]

    @classmethod
    def of(cls, library: Pylot) -> Self:
        """Read a library. Grouped here so nothing downstream scans a list."""
        meshes_by_condition: dict[str, list[CalculationMesh]] = {}
        for mesh in library.meshes():
            meshes_by_condition.setdefault(mesh.condition_id, []).append(mesh)

        results_by_mesh: dict[str, list] = {}
        for result in library.results():
            results_by_mesh.setdefault(result.mesh_id, []).append(result)

        return cls(
            conditions=tuple(library.conditions()),
            meshes_by_condition=meshes_by_condition,
            results_by_mesh=results_by_mesh,
        )


def plan(library: Pylot, job: BatchJob, *, state: LibraryState | None = None) -> BatchPlan:
    """Walk the job against the library without changing it.

    Every reuse decision is made here, against what is actually stored, so the
    preview and the run agree by construction:

    - a condition within :data:`~pylot_db.validation.CONDITION_TOLERANCE` of a
      requested one is **reused**. Adding a second is not merely wasteful --
      the validator reports the pair as duplicates, so a job run twice would
      leave the library with a finding against it;
    - with ``resume``, a mesh on that condition at the same ``pct`` and
      ``iterations`` is reused, and a solve whose every frequency an existing
      result on that mesh already covers is skipped.

    Args:
        library: The library, read only.
        job: What to do.
        state: A :class:`LibraryState` already read, for a caller planning the
            same library repeatedly. Omit it and one is read here, which is
            what a script wants.

    Returns:
        The plan, in run order: **every condition first**, then every band of
        one condition before moving to the next.

        Conditions first because that is where a grid is wrong. A sign error on
        ``z_origin`` lifts the whole vessel clear of the water, and 705
        conditions refusing in the first minute is a job that can be corrected
        and restarted -- where the same mistake found after the first solve is
        a night already spent. They are also the cheap half: a condition is one
        waterline cut, a solve is minutes.
    """
    state = state if state is not None else LibraryState.of(library)
    existing = state.conditions
    by_condition_id = {condition.id: condition for condition in existing}

    conditions: list[PlannedCondition] = []
    for z_origin in job.z_origins:
        for heel in job.heels:
            for trim in job.trims:
                match = _condition_at(existing, z_origin=z_origin, heel=heel, trim=trim)
                conditions.append(
                    PlannedCondition(
                        z_origin=float(z_origin),
                        heel=float(heel),
                        trim=float(trim),
                        existing_id=match.id if match is not None else "",
                    )
                )

    # A condition the grid already produced must not be targeted twice -- once
    # as a grid entry and once as an existing one -- or every band would run on
    # it twice and the two results would contest each other in the database.
    by_id = {c.existing_id: i for i, c in enumerate(conditions) if c.existing_id}

    if job.targets == TARGET_LISTED:
        targeted = []
        wanted = [i for i in job.condition_ids if i in by_condition_id]
    else:
        targeted = list(range(len(conditions)))
        wanted = [c.id for c in existing] if job.targets == TARGET_ALL else []

    for condition_id in wanted:
        if condition_id in by_id:
            if by_id[condition_id] not in targeted:
                targeted.append(by_id[condition_id])
            continue
        stored = by_condition_id[condition_id]
        by_id[stored.id] = len(conditions)
        targeted.append(len(conditions))
        conditions.append(
            PlannedCondition(
                z_origin=stored.z_origin,
                heel=stored.heel,
                trim=stored.trim,
                existing_id=stored.id,
            )
        )

    steps = []
    for index in targeted:
        planned = conditions[index]
        meshes = state.meshes_by_condition.get(planned.existing_id, [])
        for band in job.bands:
            mesh = _mesh_for(meshes, band) if job.resume else None
            covered = (
                _result_covering(state.results_by_mesh.get(mesh.id, ()), band)
                if job.resume and mesh is not None
                else None
            )
            steps.append(
                PlannedSolve(
                    condition=index,
                    band=band,
                    mesh_id=mesh.id if mesh is not None else "",
                    covered_by=covered.id if covered is not None else "",
                )
            )

    return BatchPlan(
        conditions=tuple(conditions),
        steps=tuple(steps),
        directions=len(job.wave_directions),
    )


def _condition_at(conditions, *, z_origin, heel, trim) -> FloatingCondition | None:
    """The stored condition at these values, within the validator's tolerance.

    The same number :func:`pylot_db.validation` calls a duplicate by, imported
    rather than repeated: a batch that reused at a *tighter* tolerance would
    create pairs the validator then flags, and one that reused at a looser one
    would silently solve at a condition the user did not ask for.
    """
    for condition in conditions:
        if (
            abs(condition.z_origin - z_origin) <= CONDITION_TOLERANCE
            and abs(condition.heel - heel) <= CONDITION_TOLERANCE
            and abs(condition.trim - trim) <= CONDITION_TOLERANCE
        ):
            return condition
    return None


def _mesh_for(meshes, band: Band) -> CalculationMesh | None:
    """A mesh already built at this band's regrid settings.

    Matched on ``pct`` *and* ``iterations``, because those two are what
    :meth:`~pylot_bem.api.Pylot.create_mesh` takes and a mesh is nothing but
    what they produced.
    """
    for mesh in meshes:
        if np.isclose(mesh.pct, band.pct) and mesh.iterations == band.iterations:
            return mesh
    return None


def _result_covering(results, band: Band):
    """A result on that mesh already covering every frequency of the band.

    Every one, not some: a result over half the band leaves the other half
    unsolved, and skipping on a partial match is how a batch would quietly
    produce a database with holes in it. Compared at the assembly tolerance,
    which is the tolerance that decides whether two frequencies are the same
    frequency downstream.
    """
    for result in results:
        stored = [float(w) for w in result.omegas]
        if all(
            any(abs(omega - other) <= OMEGA_TOLERANCE for other in stored) for omega in band.omegas
        ):
            return result
    return None


@dataclass(frozen=True, slots=True)
class BatchEvent:
    """One line of a batch's progress.

    Attributes:
        kind: ``"condition"``, ``"mesh"``, ``"solve"``, ``"skip"``,
            ``"warning"``, ``"failed"`` or ``"solving"`` -- the last being live
            progress *within* the current solve, where ``solve`` carries the
            outcome so far.
        message: A sentence for the log.
        done: Steps finished.
        total: Steps in the plan.
        elapsed: Seconds since the run started.
        solve: The current solve's outcome, on a ``"solving"`` event.
    """

    kind: str
    message: str
    done: int
    total: int
    elapsed: float
    solve: SolveOutcome | None = None


@dataclass(frozen=True, slots=True)
class BatchOutcome:
    """What a batch did.

    Attributes:
        conditions_created: Ids, in the order created.
        meshes_built: Ids.
        results_stored: Ids.
        reused: Conditions matched and meshes reused rather than built.
        skipped: Solves an existing result already covered.
        failures: ``(what, why)`` per step that raised. **A run with failures
            is a run that finished**: the whole point of batching is that the
            hundredth condition does not depend on the first.
        elapsed: Seconds.
        stopped: Whether the run ended early.
        killed: Whether it ended by :meth:`BatchRun.kill` specifically.
    """

    conditions_created: tuple[str, ...] = ()
    meshes_built: tuple[str, ...] = ()
    results_stored: tuple[str, ...] = ()
    reused: int = 0
    skipped: int = 0
    failures: tuple[tuple[str, str], ...] = ()
    elapsed: float = 0.0
    stopped: bool = False
    killed: bool = False


type BatchProgress = Callable[[BatchEvent], None]

# A step that raises must not end the run, but a step that raises
# ``KeyboardInterrupt`` or ``MemoryError`` must -- so the catch is the domain's
# own errors plus the ones a bad hull genuinely produces, not bare Exception.
_STEP_ERRORS = (LibraryError, MeshPipelineError, SolverError, ValueError, ArithmeticError, OSError)


class BatchRun:
    """One job, executed against a library, that can be watched and stopped.

    :meth:`run` blocks for as long as the job takes -- which is the night it
    was written for -- so a user interface calls it on a worker thread.
    :meth:`stop` and :meth:`kill` are safe from another thread, and mean the
    same two things they mean in :class:`~pylot_bem.pool.PoolSolve`, one level
    up:

    ==========  ====================================================
    ``stop()``  the running solve finishes and is stored; no further
                step is started
    ``kill()``  the running solve's workers are terminated and
                **nothing is stored for it**; no further step starts
    ==========  ====================================================

    Kill discards rather than storing what came back, which is where this
    differs from the Solve screen. There the user is sitting in front of the
    dialog and can be asked; a batch running overnight has nobody to ask, and
    silently writing a result over whatever fraction of a grid happened to
    return is how a library ends up with a truncated result nobody chose. The
    command line takes the same view of an interrupt.
    """

    def __init__(self, library: Pylot, job: BatchJob) -> None:
        """Prepare a run and plan it. Nothing is written until :meth:`run`."""
        self._library = library
        self._job = job
        self._plan = plan(library, job)

        self._lock = threading.Lock()
        self._pool: PoolSolve | None = None
        self._stopping = False
        self._killed = False

    @property
    def plan(self) -> BatchPlan:
        """What this run will do. Planned once, at construction."""
        return self._plan

    @property
    def job(self) -> BatchJob:
        return self._job

    # -- control -----------------------------------------------------------

    def stop(self) -> None:
        """Finish the running solve, store it, and start nothing more."""
        with self._lock:
            self._stopping = True

    def kill(self) -> None:
        """Terminate the running solve now. Nothing is stored for it."""
        with self._lock:
            self._stopping = True
            self._killed = True
            pool = self._pool
        if pool is not None:
            pool.kill()

    @property
    def stopping(self) -> bool:
        with self._lock:
            return self._stopping

    @property
    def killed(self) -> bool:
        with self._lock:
            return self._killed

    # -- the run -----------------------------------------------------------

    def run(self, progress: BatchProgress | None = None) -> BatchOutcome:
        """Do the whole job and report what happened.

        Args:
            progress: Called with a :class:`BatchEvent` as each step finishes,
                and repeatedly during a solve. Never called from another
                thread -- it runs on whichever thread called :meth:`run`.

        Returns:
            The outcome, whether or not every step succeeded. **A failed step
            is not an exception**: it is recorded in
            :attr:`BatchOutcome.failures` and the next step starts.
        """
        started = time.perf_counter()
        state = _State(total=self._plan.total_steps)

        def report(kind: str, message: str, solve: SolveOutcome | None = None) -> None:
            if progress is None:
                return
            progress(
                BatchEvent(
                    kind=kind,
                    message=message,
                    done=state.done,
                    total=state.total,
                    elapsed=time.perf_counter() - started,
                    solve=solve,
                )
            )

        # Ids of the conditions as they come to exist, by their index in the
        # plan. A step cannot hold the id of a condition that had not been
        # created when the plan was made, so this is where the two meet.
        ids: dict[int, str] = {
            index: planned.existing_id
            for index, planned in enumerate(self._plan.conditions)
            if planned.existing_id
        }

        for index, planned in enumerate(self._plan.conditions):
            if self.stopping:
                break
            if not planned.is_new:
                state.reused += 1
                continue
            state.done += 1
            try:
                condition = self._library.create_condition(
                    z_origin=planned.z_origin, heel=planned.heel, trim=planned.trim
                )
            except _STEP_ERRORS as exc:
                state.failures.append((_describe(planned), f"{type(exc).__name__}: {exc}"))
                report("failed", f"{_describe(planned)}: {exc}")
                continue
            ids[index] = condition.id
            state.conditions.append(condition.id)
            report("condition", f"condition {condition.id} — {_describe(planned)}")

        for step in self._plan.steps:
            if self.stopping:
                break
            state.done += 1
            condition_id = ids.get(step.condition, "")
            if not condition_id:
                # Its condition failed above, so there is nothing to mesh. Said
                # once as a skip rather than counted again as a failure: one
                # cause, one entry in the report. Still a step, so the progress
                # a user watches reaches its end rather than stopping short by
                # however many bands the bad condition had.
                report(
                    "skip",
                    f"{_describe(self._plan.conditions[step.condition])}: not created, "
                    f"so its pct {step.band.pct:g} mesh was not attempted",
                )
                continue
            self._run_step(step, condition_id, state, report)

        return BatchOutcome(
            conditions_created=tuple(state.conditions),
            meshes_built=tuple(state.meshes),
            results_stored=tuple(state.results),
            reused=state.reused,
            skipped=state.skipped,
            failures=tuple(state.failures),
            elapsed=time.perf_counter() - started,
            stopped=self.stopping,
            killed=self.killed,
        )

    def _run_step(self, step: PlannedSolve, condition_id: str, state: _State, report) -> None:
        """One band on one condition: build or reuse a mesh, then solve it."""
        band = step.band
        where = f"condition {condition_id}, pct {band.pct:g}"

        if step.covered_by:
            state.skipped += 1
            report("skip", f"{where}: already covered by result {step.covered_by}")
            return

        try:
            if step.mesh_id:
                mesh = self._library.mesh(step.mesh_id)
                report("mesh", f"{where}: reusing mesh {mesh.id}")
            else:
                mesh = self._library.create_mesh(
                    condition_id, pct=band.pct, iterations=band.iterations
                )
                state.meshes.append(mesh.id)
                report(
                    "mesh",
                    f"{where}: mesh {mesh.id}, {len(mesh.faces)} faces, "
                    f"{format_memory(solved_panels(mesh))} per worker",
                )
        except _STEP_ERRORS as exc:
            state.failures.append((where, f"{type(exc).__name__}: {exc}"))
            report("failed", f"{where}: {exc}")
            return

        # The one check the Solve screen makes that a job cannot: the mesh's
        # resolution limit is a property of the panels, so it exists only now,
        # halfway through the run. Periods below it still solve, and are wrong
        # by an amount nothing downstream detects -- which in a batch means a
        # library that looks complete and is not. It is a warning and not a
        # refusal because the number is an estimate and the user asked for
        # these periods.
        limit = shortest_reliable_period(mesh.vertices, mesh.faces)
        if min(band.periods) < limit:
            report(
                "warning",
                f"{where}: reliable above {limit:.2f} s, but this band starts at "
                f"{min(band.periods):.2f} s. Those frequencies will solve, and be wrong",
            )

        try:
            settings = self._job.settings_for(band, self._job.lid_z_for(mesh, band))
            outcome = self._solve(mesh, settings, report, where)
        except _STEP_ERRORS as exc:
            state.failures.append((where, f"{type(exc).__name__}: {exc}"))
            report("failed", f"{where}: {exc}")
            return

        # Before the dataset is looked at, not after: a solve where *every*
        # frequency raised returns no dataset, and reporting only that "nothing
        # was solved" would throw away the twelve messages saying why.
        if outcome is not None:
            for omega, message in sorted(outcome.failed.items()):
                state.failures.append((f"{where}, {2 * np.pi / omega:.2f} s", message))
                report("failed", f"{where}, {2 * np.pi / omega:.2f} s: {message}")

        if outcome is None or outcome.dataset is None:
            state.failures.append((where, "nothing was solved"))
            report("failed", f"{where}: nothing was solved, nothing stored")
            return

        try:
            result = self._library.store_result(
                mesh,
                outcome.dataset,
                replace(settings, omegas=tuple(outcome.solved)),
                truncated=not outcome.complete,
            )
        except _STEP_ERRORS as exc:
            state.failures.append((where, f"{type(exc).__name__}: {exc}"))
            report("failed", f"{where}: {exc}")
            return

        state.results.append(result.id)
        short = "" if outcome.complete else f" ({len(outcome.solved)} of {len(outcome.requested)})"
        report("solve", f"{where}: result {result.id} over {len(outcome.solved)} frequencies{short}")

    def _solve(self, mesh, settings, report, where) -> SolveOutcome | None:
        """Run one solve in a pool, kept reachable so it can be killed.

        Returns ``None`` when the pool was killed: the frequencies in flight
        are gone and the ones that returned were never chosen by anybody, so
        the step contributes nothing rather than a result over an arbitrary
        subset of the grid.
        """
        pool = PoolSolve(
            mesh.vertices,
            mesh.faces,
            is_xz_symmetric=mesh.is_xz_symmetric,
            application_point=self._library.application_point_in_diffraction_space(
                mesh.condition_id
            ),
            settings=settings,
            workers=self._job.workers or default_workers(len(settings.omegas)),
            omp_threads=self._job.omp_threads,
        )
        with self._lock:
            if self._killed:  # killed before this step got started
                return None
            self._pool = pool
        try:
            outcome = pool.run(
                progress=lambda snapshot: report(
                    "solving",
                    f"{where}: {len(snapshot.solved)} of {len(snapshot.requested)} frequencies",
                    snapshot,
                )
            )
        finally:
            with self._lock:
                self._pool = None
        with self._lock:
            return None if self._killed else outcome


@dataclass
class _State:
    """The mutable half of a run, kept out of :meth:`BatchRun.run`'s locals."""

    total: int
    done: int = 0
    reused: int = 0
    skipped: int = 0
    conditions: list[str] = field(default_factory=list)
    meshes: list[str] = field(default_factory=list)
    results: list[str] = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)


def _describe(planned: PlannedCondition) -> str:
    """A planned condition in the units a person reads it in.

    Degrees, because a slope in a log line is unreadable, and the log is the
    only record of what an overnight run did.
    """
    return (
        f"z_origin {planned.z_origin:g} m, heel {degrees_from_slope(planned.heel):g}°, "
        f"trim {degrees_from_slope(planned.trim):g}°"
    )
