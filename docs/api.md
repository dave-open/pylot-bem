# pylot-bem — API reference

```python
from pylot_bem import Pylot
```

Mesh a hull at a floating condition, solve it with Capytaine, store the result.
`Pylot` **is a** [`pylot_db.Library`](../../pylot-db) — it adds meshing and
solving to the same object, so every read method is already on it, and a file
written here opens as a plain `Library` on a machine with no solver installed.
That split is the point, and a test enforces it.

Everything on `Library` is documented in `pylot-db`; this covers what
`pylot-bem` adds.

[Units](#units-and-conventions) · [`Pylot`](#pylot--building) · [Batch](#batch--many-of-them-at-once) · [Workspace](#workspace--editing-a-copy) · [Plotting](#plotting) · [The application](#the-application) · [Solving](#free-functions) · [Errors](#errors)

---

## Build a library

```python
from pylot_bem import Pylot, SolveSettings
import numpy as np

d = Pylot.create_new("tanker.pylot", "tanker.stl", "stern, centerline, keel",
                     is_xz_symmetric=True)

condition = d.create_condition(z_origin=-12.0, condition_id="design")
mesh      = d.create_mesh(condition, pct=2.0)
result    = d.run_solve(mesh, SolveSettings(
    omegas=[2 * np.pi / T for T in (12.0, 16.0, 20.0)],
    wave_directions=[0.0, 45.0, 90.0, 135.0, 180.0],
))

print(d.validate() or "clean")
d.close()
```

`Pylot` writes **in place**: each step commits to `tanker.pylot` as it goes, and `d.close()` is the moment the work is in the file and the file is on its own. That is what you want on a local disk. For a library in a folder a sync client watches, see [`Workspace`](#workspace--editing-a-copy).

Runnable versions are in [`../examples/`](../examples/).

---

## Units and conventions

Getting one of these wrong produces plausible output, which is why they are stated first.

| | | |
|---|---|---|
| **Length** | metres, everywhere | The only conversion is `scale` at mesh import |
| **`z_origin`** | metres, **negative** when floating | Height of the vessel origin above the waterplane. **Not the naval draft** — they differ by wherever the origin sits, and there is no `draft` argument anywhere |
| **`heel`, `trim`** | **slopes**, `sin(radians(deg))` | Degrees appear only in the CLI and the UI, both via `pylot_bem.angles`. **`sin`, not `tan`** — the slope is the z-component of a *unit* axis vector, which is what makes the domain a unit disc. `heel=5` is a slope of 5, which is outside that domain and raises |
| **sign of `heel`, `trim`** | a **positive rotation about the axis**, right-hand rule | Positive `heel` (about **+x**) puts **starboard down**; positive `trim` (about **+y**) puts the **bow down**. The frame is right-handed with z up and x forward, so **+y is port** |
| **Frequency** | `omega` [rad/s] | Periods in seconds are a UI convention: `omega = 2*pi/T` |
| **Wave direction** | degrees, **direction of travel** | Where the wave is going. Conversion from Capytaine is `×180/π`, no offset |
| **Density** | **t/m³** (1.025) | **Not a solve input.** Every solve runs at 1 t/m³; results are stored per unit density and scaled on delivery. Converted to SI at the Capytaine boundary |
| **Water depth** | metres, `np.inf` for infinite | |
| **Application point** | derived, stored **vessel-local** | Centre of the *submerged* bounds. You never supply it |
| **Phase origin** | `(x, y)` only | The diffraction origin. z is meaningless and is not carried |

The valid domain for a condition is `trim² + heel² ≤ 1` — a unit disc. Outside it, `transform` raises `ValueError`.

### Density is applied on delivery, not on solving

Added mass, damping and the excitation force are **exactly** linear in water density — measured, bitwise, to 0 ULP ([`test_rho_scaling.py`](../tests/test_rho_scaling.py)). Density enters linear potential flow only through the linearised Bernoulli pressure `p = −ρ ∂φ/∂t`; the potential problem itself contains no ρ.

So every solve runs at **ρ = 1 t/m³** and results are stored **per unit density**:

- `SolveSettings` has no `rho`, and neither does `Result`. There is nothing to get wrong.
- `rho` is **not** part of the assembly key and **not** a matching filter. One library serves salt water, fresh water and anything else.
- `to_hyddb1`, `assemble`, `deliver` and `Library.hyddb` take a **required** `rho`. No default — a forgotten argument would hand back a database wrong by 2.5% that looks entirely plausible.

### Half the circle in, all of it out

A delivered database always covers the **full 360°**, even when only 0–180 was solved. For an XZ-symmetric body at zero heel the port half is the mirror image, so the interface solves half and `to_hyddb1` fills in the rest — verified against a full-circle solve to 0.000% (spec 04 §8).

It happens only when the *floating body* is symmetric: the hull declared symmetric **and** the condition unheeled. `assemble` works that out from the condition; call `to_hyddb1` directly and you pass `is_xz_symmetric` yourself, defaulting to `False`.

Do not skip it on a half-circle database. mafredo does not refuse a heading past 180 — it interpolates across the unsolved half and returns a confident, wrong number.

```python
salt  = library.hyddb("design", rho=1.025)
fresh = library.hyddb("design", rho=1.000)   # same stored result, nothing re-solved
```

`Library.result_dataset()` gives you the raw stored dataset: SI **and** per unit density, so it is neither tonnes nor the density you want. `assemble` applies both conversions.

---


## `Pylot` — building

```python
from pylot_bem import Pylot
```

Everything on [`Library`](#library--everything-a-library-can-do), plus:

### `Pylot.create_new(path, mesh_file, origin_description, *, is_xz_symmetric, scale=1.0, vessel_name="", description="", probe_xy=None)`

Create a library from a hull file. Any format `pymeshlab` reads; STL in practice.

- **`origin_description`** — where `(0, 0, 0)` sits on the vessel, e.g. *"stern, centerline, keel"*. Required, and the one thing in a library that cannot be recovered later.
- **`is_xz_symmetric`** — required, no default. A **declaration by the modeller**; nothing can derive it. The tanker fixture reports a 28 m deviation on a nearest-vertex mirror test while describing a surface symmetric to under a millimetre, because its *tessellation* is not mirrored. Declaring it halves every mesh and quarters the memory.
- **`scale`** — multiplied into the file's coordinates. `0.001` for a model in millimetres. The only unit conversion in the system.
- **`vessel_name`** — defaults to the mesh file's stem.

Refuses a **half mesh** here, at the earliest point you can still pick a different file. Refuses to overwrite an existing library.

### `create_condition(*, z_origin, heel=0.0, trim=0.0, label="", condition_id=None) -> FloatingCondition`

Add a floating condition and **derive its application point** from the submerged geometry. That derivation is why this is not `add_condition` — it needs the meshing stack.

Slopes, not degrees. Raises `MeshPipelineError` if nothing is submerged.

A blank `label` becomes `condition_name(z_origin, heel, trim)` — `z-4.70_h-1.00_t2.00`: metres, then two angles in **degrees**, two decimals each, every number carrying the letter of what it is. The alternative shown everywhere a condition appears is its generated id, and a batch of seven hundred uuids is unreadable. It is a **label and never an id**: ids are opaque and nothing may parse one (ADR-4), while a label is display only, parsed by nothing, and correctable afterwards.

### `condition_name(z_origin, heel, trim) -> str`

That derivation on its own, for anyone building labels to match. The letters are for the eye — nothing parses this, here or anywhere.

### `create_mesh(condition, *, pct=2.0, iterations=20, mesh_id=None) -> CalculationMesh`

Build a calculation mesh at a condition and store it. `condition` may be the object or its id.

- **`pct`** — regrid target as a percentage of the bounding-box diagonal. Lower is finer. **The knob that matters**: solver cost is quadratic in the panel count.
- **`iterations`** — isotropic remeshing iterations.

`is_xz_symmetric` on the result is **derived** from the base shape *and* the condition's heel, never accepted. A heeled condition always gets a full mesh. When it is true the stored mesh is **half a vessel**.

### `run_solve(mesh, settings, *, label="", result_id=None, progress=None) -> Result`

Solve a mesh and store the result. `mesh` may be the object or its id.

One [`SolveSettings`](#solvesettings) drives both the solve and the metadata recorded against the result, so the two cannot disagree; the returned dataset is cross-checked against it and a mismatch raises `SolverError`.

`progress(done, total)` is called after each **frequency** — not each problem, because the influence matrices are cached across a frequency's problems and the first does nearly all the work. **Raising from it cancels**: the exception propagates out and nothing is stored.

### `store_result(mesh, dataset, settings, *, label="", result_id=None) -> Result`

The second half of `run_solve`, for a dataset you already have. Use it when you drove the frequencies yourself — through [`PoolSolve`](#poolsolve), so the run could be watched and cancelled — and arrive holding a dataset rather than a request.

The same checks apply: the dataset is compared against `settings` and against `SOLVE_RHO_SI`, so a result cannot be recorded against physical conditions it was not computed at. The **frequency grid is deliberately not checked** — a stopped run yields a complete result over a shorter grid, and the grid recorded is the one in the dataset.

### `base_shape_at(condition) -> MeshGeometry`

The **whole** hull, placed in diffraction space at a condition.

The base shape is stored vessel-local, so on its own it says nothing about where the water is. Placed at a condition its z is measured from the waterplane — which is the only frame in which drawing the hull, its calculation mesh and the waterline in one picture means anything.

Not the calculation mesh: nothing is cut and nothing is regridded, so this is the dry side too, and it is a **full vessel** even where the mesh is a half.

### `application_point_in_diffraction_space(condition) -> FloatArray`

The stored vessel-local application point, converted with the condition's transform. The solver wants it in diffraction space; the library stores it vessel-local. This is the only place that conversion is written, and you need it if you call `solve()` yourself — passing the stored point straight through puts the moment reference out by the draft.

### `close()`

Close the library. **This is when your work is in the file.** A `Pylot` is in WAL mode while it is open, and until then the newest commits can be only in the `-wal` beside it: copy the main file alone and they are missing.

`close()` also switches the file back from WAL to a rollback journal (`PRAGMA journal_mode = DELETE`), so a file at rest is an ordinary single file. It is worth doing because WAL is recorded in the file's header — a library that was ever opened for writing keeps asking for `-wal` and `-shm` files every time it is opened, even by something that only wants to look.

**Best effort, and never an error.** The switch needs this to be the only connection, so it is skipped at once — `busy_timeout` is 0, nothing waits — when another is open, and skipped for a library opened `read_only`. Whichever connection closes last does it; a file it could not reach is left as it was, and is exactly as valid.

**Every `open()` / `close()` pair rewrites the file, even if the script only reads.** Opening puts the file in WAL mode and `close()` puts it back, and both write its header. That changes the file's modification time **and its content hash**: a sync client uploads it again, and a [`Workspace`](#workspace--editing-a-copy) — or the application — holding unsaved changes to the same file will report it as changed by someone else at its next `save()` (`SourceChangedError`). A script that only reads should use `Library.open(path, read_only=True)` from `pylot_db` (`Pylot.open(path, read_only=True)` does the same), which changes neither the modification time nor the hash and creates no `-wal` or `-shm`. (With a `-wal` already beside the file, which no library saved by the application has, it opens `mode=ro` instead so that it reads that too.)

---


## Batch — many of them at once

```python
from pylot_bem.batch import (
    Band, BatchJob, BatchRun, load_job, parse_bands, plan, save_job, value_range,
)
from pylot_bem.angles import slope_from_degrees
```

Fill in a grid of conditions, mesh each one at several resolutions, and solve
each mesh over the periods that resolution can carry. Built for a run nobody is
watching, which is what decides its behaviour.

```python
job = BatchJob(
    z_origins=value_range(-4.7, -0.1, 0.1),                        # 47
    heels=tuple(slope_from_degrees(d) for d in (-1, 0, 1)),        #  3
    trims=tuple(slope_from_degrees(d) for d in (-2, -1, 0, 1, 2)), #  5
    bands=parse_bands("1 -> 1, 2, 3, 4\n2 -> 5, 6, 7, 8, 9, 10, 12"),
    wave_directions=tuple(float(d) for d in range(0, 181, 15)),
)

preview = plan(library, job)
print(preview.conditions_to_create, preview.meshes_to_build, preview.problems)
#   705            1410            147345

outcome = BatchRun(library, job).run(progress=lambda event: print(event.message))
print(len(outcome.results_stored), "stored,", len(outcome.failures), "failed")
```

A job is data, so it can be [saved and loaded](#save_jobjob-path---path--load_jobpath---batchjob):

```python
save_job(job, "tanker.pylotjob")
BatchRun(library, load_job("tanker.pylotjob")).run()
```

### `Band(pct, periods, iterations=20)`

One mesh resolution and the periods solved on it. Panel size sets the shortest
wave a mesh can resolve and solver cost is quadratic in the panel count, so a
grid spanning 1 s to 12 s on one mesh either wastes hours at the long end or
returns confident nonsense at the short one. `omegas` is the periods as an
ascending frequency grid.

### `BatchJob(...)`

The whole job as one frozen value. The grid (`z_origins` × `heels` × `trims`)
creates conditions; the `bands` mesh and solve them; either half may be empty.
Slopes, not degrees — the same rule as everywhere else. `targets` picks which
conditions the bands run on:

| | |
|---|---|
| `TARGET_GRID` | the grid above, **including entries that already exist** — which is what makes a second run continue rather than target nothing |
| `TARGET_ALL` | that grid *and* every other condition in the library |
| `TARGET_LISTED` | `condition_ids`, and nothing else |

**Two heading grids, and which one a solve gets is derived from its mesh.**
`wave_directions` is for a half-vessel mesh, `wave_directions_full` for a full
one; empty falls back to the first. A symmetric hull at zero heel mirrors its
port side, so 0–180 is exact; heel it and the mesh is a full vessel needing the
whole circle. A grid of heels contains both, so one setting could never be right
for a whole job — and `directions_for(is_xz_symmetric=...)` is the only way to
ask, for the same reason symmetry itself is derived and never set.

`lid` is a **mode** (`"none"`, `"surface"`, `"below"`, `"auto"`) rather than a
position, because `auto` has no answer until a mesh exists — which in a batch is
halfway through the run. It is resolved per mesh and per band. The CLI refuses
`auto` for exactly this reason; a batch is holding the mesh by then.

`resume=True` is the default and is the whole point. See below.

### `parse_bands(text)` · `parse_numbers(text, *, what)` · `value_range(start, stop, step)`

`parse_bands` reads the table the way a job gets written down — `1 -> 1, 2, 3, 4`
per line, `:` as well as `->`, `#` for a note — and keeps the order written.
`parse_numbers` takes commas or whitespace, plus `4..20..0.5` ranges. Both raise
`BatchError` with a sentence written for a user.

`value_range` includes `stop` when the step lands on it: *0.1 to 4.7 step 0.1* is
the 47 values you counted, not the 46 `arange` returns, and the results are
rounded so `-4.6000000000005` never reaches a `z_origin` column.

### `plan(library, job, *, state=None) -> BatchPlan`

Walks the job against the library and changes nothing. Reports
`conditions_to_create` / `conditions_existing`, `meshes_to_build` /
`meshes_reused`, `solves_to_run` / `solves_skipped` / `solves_on_a_full_vessel`,
`problems`, `directions` / `directions_full` and `total_steps`.

`problems` is summed per step, not multiplied out: a full-vessel solve carries
more headings than a half-vessel one, and a job with three heels contains both.
A single figure would under-count the typical job by nearly 40%.

**There is no memory or panel estimate**, deliberately: those come out of a
regrid that has not run, and an invented figure beside real ones is
indistinguishable from them. `BatchRun` logs each mesh's own as it is built.

`state` is a `LibraryState.of(library)` you already read, for a caller planning
the same library over and over. A `CalculationMesh` carries its geometry, so
`Library.meshes()` decodes every vertex array in the file to answer a question
about `pct` — fine once, and a third of a second per keystroke on the batch
screen, which is why that screen reads it once. Scripts should omit it.

### `save_job(job, path) -> Path` · `load_job(path) -> BatchJob`

Keep a job. It is four numbers and a table that took a while to get right, it
outlives the run, and it is what says a year later which drafts and periods a
library actually covers.

```python
save_job(job, "tanker.pylotjob")
again = load_job("tanker.pylotjob")     # == job
```

JSON, with `.pylotjob` added when the path has no suffix and never substituted
for one you chose. The whole 705-condition job above is 29 lines, because number
lists stay on one line each — the drafts and the periods are the half worth
editing by hand:

```json
{
  "pylot_batch_job": 1,
  "z_origins": [ -4.7, -4.6, -4.5, … ],
  "heels_deg": [ -1.0, 0.0, 1.0 ],
  "bands": [ { "pct": 1.0, "iterations": 20, "periods": [ 1.0, 2.0, 3.0, 4.0 ] } ],
  "water_depth": null,
  …
}
```

- **Angles are written in degrees**, with the unit in the key. A job file is a
  human-facing boundary and that is the rule at every one of them. The round trip
  is `sin(asin(x))` — about one ULP, five orders of magnitude tighter than the
  1e-3 at which two conditions are the same condition.
- **Infinite depth is `null`**, not `Infinity`: that is what Python's JSON writes
  for it and it is not valid JSON, so a file carrying it reads back here and
  nowhere else.
- **Missing fields load as defaults**, which is what makes one worth hand-editing.
  Present-and-wrong is refused, `targets` and `lid` by `BatchJob` itself.
- **`condition_ids` only mean something against the library they came from.** The
  batch screen says how many of them it found.

`load_job` raises `BatchError` naming the file for a missing or unknown version
marker, unreadable JSON, or a binary file — and recognises a `.pylot` library
specifically, since it sits in the same folder under a name one letter away.

`job_to_dict` / `job_from_dict` are the same conversion without the file, for
putting a job in some other container.

### `BatchRun(library, job)`

`run(progress=None)` blocks and returns a `BatchOutcome`; `stop()` and `kill()`
are safe from another thread. It executes the plan made at construction, so the
counts you previewed are the work that happens.

| | |
|---|---|
| `stop()` | the running solve finishes and is stored; nothing further starts |
| `kill()` | the running solve's workers are terminated and **nothing is stored for it** |

Kill discards where the Solve screen offers to keep, because there is nobody
watching an overnight run to be asked — the CLI takes the same view of an
interrupt.

**A step that raises does not end the run.** It is recorded in
`BatchOutcome.failures` as `(what, why)` and the next step starts. One `z_origin`
above the waterline costs that condition and no other.

**Running the same job again resumes it.** A condition within
`pylot_db.validation.CONDITION_TOLERANCE` of a requested one is reused — the
validator would otherwise report the pair as duplicates — a mesh at the same
`pct` and `iterations` is reused, and a solve is skipped when an existing result
on that mesh covers **every** one of the band's frequencies. Every one, not some:
skipping on a partial match is how a database quietly ends up with holes.

`progress` gets a `BatchEvent` (`kind`, `message`, `done`, `total`, `elapsed`,
`solve`) per step and repeatedly during each solve. `kind` is `"condition"`,
`"mesh"`, `"solve"`, `"skip"`, `"warning"`, `"failed"` or `"solving"`.

> **From a thread, open your own connection.** `sqlite3` refuses a connection
> used from a thread other than the one that opened it. Every pylot library runs
> in WAL mode, so a second `Pylot.open(path)` on the worker thread writes while
> the first goes on reading — which is what `pylot_bem.app.batch.BatchThread`
> does. Inside a [`Workspace`](#workspace--editing-a-copy) the same holds, and
> `path` is `workspace.library.path`, the **working copy**: that is the file
> `BatchThread` opens, and the workspace notices the worker's commits and marks
> itself unsaved. `BatchRun` itself is unchanged and still writes to whatever
> library it is handed, in place.

---


## Workspace — editing a copy

```python
from pylot_bem import Workspace
from pylot_bem.workspace import (
    Recovery, SourceChangedError, SourceLockedError, WorkspaceError, default_work_root,
)
```

A library open for editing the way a text editor opens a file. **Qt-free**: it is what the application does with a library, and it is here so a script can do the same.

**`Pylot`, `BatchRun` and the command line write in place.** They open the file you name, in WAL mode, and every commit goes into it as it happens; [`close()`](#close) is when the work is in the file. That is right on a local disk and wrong in a folder Nextcloud or OneDrive is watching, where the `-wal` and `-shm` beside the library are uploaded half written — and two copies of a database that disagree about what is in the log are a corrupt database. Nothing about those three changed, except that `Pylot.close()` now makes a best effort to leave the file as a single file — at the price that every `open()` / `close()` pair rewrites the file's header, which [`close()`](#close) spells out.

A `Workspace` never opens your file for editing. It copies it to a private folder on a local disk, gives you a `Pylot` on the copy, and **`save()` is the only moment the original is touched**:

```python
with Workspace.open("V:/vessels/tanker.pylot") as w:          # copied to a local working folder
    condition = w.library.create_condition(z_origin=-5.0)     # w.library is a Pylot, on the copy
    print(w.dirty)                                            # True
    try:
        w.save()                                              # tanker.pylot replaced, atomically
    except SourceChangedError:                                # someone else changed it meanwhile
        w.save_as("V:/vessels/tanker-mine.pylot")             # keep both
    except SourceLockedError as exc:                          # in use by another program, or read-only
        print(exc.reason)                                     # nothing was written; w still has every change
```

**Leaving the `with` block discards whatever was not saved**, as closing an editor and choosing *Discard* does: `close()` deletes the working copy. A script that wants its work kept ends with `save()`.

For a script pointed at a synced folder that leaves two honest choices: work on a **local path** with `Pylot` and put the finished file where it is going, or go **through `Workspace`**.

### `Workspace.open(path, *, work_root=None) -> Workspace`

Open an existing library for editing. `path` is read once, to make the copy, and not held open afterwards. Raises `LibraryError` for a file that is missing, is not a library or is from another schema version — the refusals of `Library.open` — and `WorkspaceError` for a file that keeps changing while it is being copied, or whose `-wal` and main file do not agree with each other.

A library written by an older version can have a `-wal` beside it holding commits the main file does not have. Copying the main file alone would lose them, so a non-empty `-wal` is copied too and replayed on the copy; the original is only read. Its leftover `-wal`, `-shm` and `-journal` are set aside by the first `save()` that gets as far as the swap, but only for the length of one attempt at it: an attempt that fails puts them straight back, and they are deleted once a swap has worked.

### `Workspace.create(path, mesh_file, origin_description, *, work_root=None, **options) -> Workspace`

Create a library and write it to `path` **straight away**. `options` are those of [`Pylot.create_new`](#pylot--building) — `is_xz_symmetric` is still required. The library is built in a working copy and saved at once, so `path` exists and the workspace starts clean: there is no untitled state. Raises `LibraryError` if `path` exists — checked before anything is touched, and again just before the swap, since building the snapshot takes a while.

### `Workspace.recoverable(work_root=None) -> list[Recovery]` · `Workspace.recover(recovery) -> Workspace`

The unsaved work earlier sessions left behind — see [Crash recovery](#crash-recovery).

### `library` · `path` · `working_path` · `work_dir` · `name` · `closed`

| | |
|---|---|
| `library` | The [`Pylot`](#pylot--building) on the working copy. Do the work through this. `sqlite3` refuses a connection used from another thread, so a worker opens its own connection to `library.path` — see [the note under `BatchRun`](#batchrunlibrary-job) |
| `path` | The file `save()` writes. `None` only for a recovered session whose work never had a file, which `save()` refuses and `save_as()` cures |
| `working_path` | The private copy every change is made to. `library.path` |
| `work_dir` | The private folder holding the copy and its session record |
| `name` | The file's name, for a title bar |
| `closed` | Whether `close()` has run |

### `dirty`

Whether there is anything `save()` would write that the file does not have. **Sticky**: once a commit has been seen it stays `True` until a save, even if what was added has since been deleted — the question is *did the copy change*, not *does it differ*. It sees every writer — the window's connection and a batch worker's alike — because it watches the file from a connection of its own.

Cheap enough to poll, and **polling is what makes work recoverable**: the first time it answers `True` it is also written to the session record that [crash recovery](#crash-recovery) reads. The application polls on a timer. A script that never asks looks, after a crash, like a session with nothing to lose. Writing the record is a safety net and never raises: if it fails (a full disk, say) it is tried again on the next poll, until it has worked — `True` after a change and `False` again after a save alike.

### `save(*, force=False)`

Replace the original with the working copy. Safe to call while a batch is committing to the copy: what is written is one consistent snapshot, and anything committed while it was being taken still counts as unsaved afterwards.

| Raises | When |
|---|---|
| `SourceChangedError` | The original changed since this workspace last read or wrote it — including while `save()` was waiting for a file that was in use. `force=True` overwrites it anyway — for when the user has been told and chose to |
| `SourceLockedError` | The original could not be replaced: it is read-only, or another program kept it open — or kept its `-wal`, `-shm` or `-journal` from being moved aside, which is retried in the same way — through `REPLACE_BUDGET` (8) seconds. Nothing was written, the original is exactly as it was, and every change is still in the workspace, so trying again or saving elsewhere loses nothing |
| `WorkspaceError` | There is no file yet (use `save_as`), the workspace is closed, or the snapshot failed its checks |

**A `save()` that raises leaves the original exactly as it was** — not only the main file but, for a library written by an older version, the `-wal` beside it, which can hold commits the main file does not have. That is what steps 5 and 6 below are arranged to guarantee.

What it does, in order, and why each step is there:

1. **`VACUUM INTO` a staging file** — one consistent snapshot of the copy even while a batch is committing to it, and a plain rollback-mode file with no `-wal`. Copying the file instead loses whatever is still only in the `-wal`; `Connection.backup` keeps the WAL flag in the header.
2. **Verify the snapshot** — a single-file SQLite header, the library's own schema check, `PRAGMA quick_check` — before it can go near the original.
3. **Copy it beside the original** as `~tanker.pylot.<random>.tmp`, and `fsync`.
4. **Check the original is unchanged** since it was opened — by size and modification time, and when those differ by SHA-256, because a sync client rewrites modification times without changing a byte, and an alarm about a change that is not one teaches people to click through the real ones. A file that has disappeared is not a change: nothing is there to overwrite. The check is made before the snapshot (so a stale save fails at once), again once the copy is beside the original, and **again before every attempt at step 6**.
5. **Set aside a stale `-wal`, `-shm` and `-journal`** beside the original, by renaming each to `~tanker.pylot-wal.<random>.tmp` (and so on) next to it. They belong to the old file, and SQLite would replay them onto the new one. They are moved and not deleted because step 6 can still fail. This is part of *each attempt* at step 6, immediately before its `os.replace`, and not something done once for the whole wait: an attempt that fails puts them back straight away, before it waits, and they are deleted only once an attempt has worked.
6. **`os.replace`**, retried for `REPLACE_BUDGET` seconds. On Windows it fails for as long as *anything* — an antivirus scanner, a sync client, DAVE — has the original open, and the same goes for a sidecar that step 5 cannot move: that fails the attempt and is retried like a locked original. The wait can be seconds long, which is why step 4 is repeated inside it: a change that lands during the wait raises `SourceChangedError` and is not overwritten.

The original is therefore the old file or the whole new one, never half of anything, and no handle is held on it between saves. After a save the workspace is clean and remembers the file as it now is, so a second save does not object to the first. Two threads calling `save()` are serialised and the second is compared against what the first wrote.

If the *process* dies inside an attempt — after step 5 set the sidecars aside and before the swapped-out files are deleted; that is one attempt's worth of exposure, not the whole wait — they stay where they are, as `~tanker.pylot-wal.<random>.tmp` (and `-shm`, `-journal`) beside a library written by an older version. **Nothing deletes or restores them automatically, and they may hold commits the main file does not have** — the same goes for a set-aside sidecar that a failed attempt could not put back, or that could not be deleted after a successful one. If the library then seems to lack recent work from an older version, rename each back to its old name (`tanker.pylot-wal` and so on) before opening it. `~tanker.pylot.<random>.tmp` still beside the original (same `<random>`) means the swap did not happen and they belong back; gone means it most likely did and they belong to the old file — but see below before deleting them, and check that the library has the work you expect.

The half-copied `~tanker.pylot.<random>.tmp` itself is different: it is safe to delete, and the next `save()` (or `save_as()`) to that file deletes it once it is more than ten minutes old (`<random>` is 8 hex digits; a younger file is left alone, because another window may still be writing it). The set-aside `~tanker.pylot-wal.<random>.tmp` files are **never** swept, because they may be the only copy of some commits — which is also why an absent `~tanker.pylot.<random>.tmp` is not proof that the swap happened.

### `save_as(path)`

Write the working copy to a new file, which becomes the workspace's `path`; the file it came from is left as it was. Anything already at `path` is replaced — whether that is intended is for whoever chose the name. The changed-on-disk check does not apply to a destination this workspace never read, except when it is the file it already has, which is just `save()`.

### `close()`

Close the library and **delete the working copy**. Whoever calls it has already decided what happens to unsaved changes; they are gone afterwards. Safe to call twice; `with` calls it.

### Where the copies live

Not the system temporary folder — some systems clear that at boot, and these copies are what a crash recovers from — and not beside the library, which is the synced folder this exists to stay out of.

| | `default_work_root()` |
|---|---|
| Windows | `%LOCALAPPDATA%\pylot-bem\work` |
| macOS | `~/Library/Application Support/pylot-bem/work` |
| elsewhere | `$XDG_STATE_HOME/pylot-bem/work`, or `~/.local/state/pylot-bem/work` |

Set the environment variable `PYLOT_BEM_WORK_DIR` (`pylot_bem.workspace.WORK_DIR_ENV`) to move all of them — to a bigger drive for a very large library, or to a temporary folder for a test run — or pass `work_root=` to `open`, `create` and `recoverable`. Each workspace gets a folder of its own, named with 32 random lowercase hexadecimal characters; the copy is inside it, beside a `session.json` and a `session.lock`, and while a save runs, the staging file. Room for about twice the library is needed there, and room for one more copy beside the original while a save runs.

**Only such folders are ever looked at.** `recoverable()` reads, locks and deletes folders whose names have that shape and leaves everything else in the work root alone — files, other folders, anything — so `PYLOT_BEM_WORK_DIR` may point at a folder that already has other things in it.

### Crash recovery

With an explicit save, hours of batch results exist only in the copy until somebody saves. So the copy lives in a folder that survives the process, with a small session record beside it, and a lock the operating system releases when the process dies however it dies.

```python
for recovery in Workspace.recoverable():                # dead sessions that held unsaved work
    print(recovery.source, recovery.updated)
    with Workspace.recover(recovery) as w:              # comes back dirty
        w.save()                                        # or w.save_as(...)
```

`Recovery` carries `work_dir`, `source` (the file the work was being done on, or `None`), `working_path`, `updated` (when the session last recorded its state) and `fingerprint` (what the original was when that session last read or wrote it, or `None` if the record no longer says), and `discard() -> bool`, which throws the work away.

**`discard()` takes the session's lock first.** It returns `False` and deletes nothing if a running session has taken the folder since it was listed — a stale `Recovery` must not be able to delete work somebody is looking at — and `True` if it deleted the folder or the folder was already gone.

`recoverable()` offers a session when nothing holds its lock any more and it had recorded changes; a dead session with nothing to lose is deleted there rather than offered, and one that is only a minute old with no record yet is left alone as a session being born. It looks only at [session folders](#where-the-copies-live) — the 32-hexadecimal-character names — in the folder currently in force, so recover or discard before moving `PYLOT_BEM_WORK_DIR`.

`recover()` opens the copy as unsaved changes. Its `save()` compares the original with what it was when that session last read or wrote it, so if the file has moved on in the meantime, saving says so with `SourceChangedError`. **If the record lost that fingerprint but knows the file, the comparison fails closed:** the baseline is one nothing on disk can match, so the first `save()` raises `SourceChangedError` (unless the file has since disappeared) and the caller chooses — `save(force=True)` to overwrite, `save_as()` to keep both — instead of the check being skipped because the evidence went missing. The application asks *Overwrite / Save As / Cancel*; after an answer the saved file is the baseline as usual. `recover()` raises `WorkspaceError` if another running session has taken the folder meanwhile, and `LibraryError` if the copy will not open — its folder is then left alone, untouched, so it can be salvaged by hand: copy the whole folder before doing anything to it, and keep the `-wal` and `-shm` beside the `.pylot` (the newest changes can exist only in the `-wal`; SQLite replays it when the file is next opened, and normally deletes it when that connection closes, which is why the copy comes first).

### Exceptions

All in `pylot_bem.workspace`.

| | |
|---|---|
| `WorkspaceError` | Opening or saving failed for a reason a person can act on. A `LibraryError`, so everything that already reports a library that will not open reports these too; the message is written to be shown as it stands |
| `SourceChangedError` | The file on disk is no longer the one this workspace was opened from — or, for a recovered session whose record lost the fingerprint, cannot be shown to be. `.path` |
| `SourceLockedError` | The file cannot be replaced right now. Nothing was written and the original is exactly as it was. `.path`, and `.reason` — the message without the path |

Both of the last two are `WorkspaceError`s.

---


## Plotting

```python
from pylot_bem.plotting import show, show_condition, to_polydata, to_vedo
```

Built on **`vedo`**, which is the 3D display already in the stack (spec 07 §1) and what the application commits to (spec 06 §2). `vedo` *is* VTK: every object here wraps a `vtkPolyData`.

**Deliberately not exported from `pylot_bem`.** Importing `vedo` costs ~0.4 s and pulls in the whole of VTK, which the CLI has no use for.

| | |
|---|---|
| `to_vedo(mesh, *, color=…, alpha=1.0, wireframe=False) -> vedo.Mesh` | Anything with `vertices` and `faces`: a `BaseShape`, a `CalculationMesh`, a `MeshGeometry` |
| `to_polydata(mesh) -> vtkPolyData` | **What a Qt VTK widget embeds.** Hand it to a `vtkPolyDataMapper` — no plotter involved. Single precision, like every `vtkPoints` |
| `waterplane(mesh, *, margin=0.15) -> vedo.Mesh` | A translucent plane at `z = 0`, sized per axis |
| `show(*items, title=…, azimuth=-50, elevation=-20, interactive=True, screenshot=None) -> vedo.Plotter` | A window. `interactive=False` renders offscreen, which is what makes `screenshot` work headless |
| `show_condition(library, condition, *, mesh=None, probes=True, application_point=True, …)` | Hull, waterplane, calculation mesh, probes and application point in one scene |

> **Mind the frame.** Nothing in a vertex array says whether it is vessel-local or diffraction-space, and a `BaseShape` is the former while a `CalculationMesh` is the latter. Drawing both at once is only meaningful once the hull is placed — `Pylot.base_shape_at(condition)`, which is what `show_condition` does.

The camera defaults are not cosmetic: `vedo` resets to a **plan view**, where a hull is a silhouette and its draft is invisible. The defaults give a three-quarter view from just under the waterplane.

Adding to this module? Spec 07 §3.2: import from `vtkmodules.*`, never `import vtk` — the top-level shim eagerly imports everything and breaks when another distribution supplies its own build, which `pymeshup` does.

`pylot_bem.polydata.to_polydata(mesh)` is the same conversion **without vedo**, which is what the application embeds. Keeping it separate is not tidiness: VTK's Qt widget needs `vtkmodules.vtkRenderingOpenGL2` imported or its render window is the abstract base class that draws nothing, and the two modules have different needs from that point on.

---

## The application

```bash
uv run pylot-bem                 # or: uv run python -m pylot_bem.app
uv run pylot-bem tanker.pylot    # opening a library at startup
```

A window for building and inspecting libraries: a tree of **library → condition → mesh → result**, a 3D view, property panes, and tabs for Results, Databases, Inspect, Match and Validation. See the `pylot` specification, `06_ui_and_integration.md` and `09_ui_options.md`.

**It is a client of this API and nothing more.** Every action it performs is one call on `Pylot` — on the working copy a [`Workspace`](#workspace--editing-a-copy) holds for it, which also does the opening, saving and recovering; where something was missing — `set_info`, `store_result` — the answer was to put it here, not to reach past it. Anything the window had to work out for itself, every other caller would have had to work out too. Unlike the window, `Pylot`, `BatchRun` and the command line work on the file itself.

The property panes and dialogs are generated from Qt Designer files in `pylot_bem/app/guis/`; edit those and run `guis/regenerate.py`. The test suite parses the source for every `objectName` the code reads and checks each one still exists, so renaming a widget in Designer fails a test rather than a user's click.

---


## Free functions

### Solving — `pylot_bem`

#### `SolveSettings`
```python
SolveSettings(omegas, wave_directions=(), water_depth=inf, g=9.81,
              forward_speed=0.0, lid_z=None, lid_radius=None)
```
Property: `lid_mode`, **derived** from `lid_z` (`None`, `"free_surface"` at 0, else `"below_free_surface"`).

**There is no `rho`.** Every solve runs at `SOLVE_RHO = 1 t/m³`; accepting a density here would let a caller store a result that is not normalised, which nothing downstream could detect.

Every field is an **input**, not a constant. The previous implementation pinned water depth inside accessor functions, which made that dimension unusable for matching.

The lid is a **solver** setting, not geometry — it is generated at solve time from the final mesh and never stored.

#### `solve(vertices, faces, *, is_xz_symmetric, application_point, settings, name="vessel", progress=None) -> xr.Dataset`

`application_point` is in **diffraction space** — use `Pylot.application_point_in_diffraction_space`.

Returns `added_mass`, `radiation_damping` and, when directions were given, `excitation_force`. The Froude-Krylov and diffraction components are checked against the excitation identity and then dropped: only the excitation is needed downstream, and dropping them removes a third of the complex data.

#### `solver_provenance(dataset) -> (name, version)`
Taken from what actually ran, never hard-coded.

#### `auto_lid_z(vertices, faces, *, is_xz_symmetric, omega_max, g=9.81) -> float | None`

Where Capytaine would put a lid for a frequency grid. **Strictly negative, or `None`.**

`None` is not a failure: outside the formula's domain there are no irregular frequencies in range and no lid is needed. Long periods are low frequencies, so it is the *long* end of a grid that leaves the domain.

Beware what Capytaine returns there — not the NaN you would expect, but **`0.0`**, because `min(0.0, nan)` is `0.0` in Python. Passed on unexamined that is an instruction to lid the *free surface*: a real setting, with real cost, that nobody asked for. Hence the sign test, and a test pinning Capytaine's behaviour so a future version changing it fails loudly.

#### `PoolSolve(vertices, faces, *, is_xz_symmetric, application_point, settings, workers=None, omp_threads=1)`

One solve, in a worker pool, that can be watched and stopped. `run(progress=None)` blocks and returns a `SolveOutcome`; `stop()` and `kill()` are safe from another thread, which is the point of it.

| | Drops | Latency | Keeps |
|---|---|---|---|
| `stop()` | queued frequencies | one frequency | everything finished |
| `kill()` | the worker processes | immediate | everything already returned |

`SolveOutcome.killed` says which tier ended it. What came back is equally complete either way — the unit of work is a frequency and a frequency that returned returned whole — but the *intent* differs, and the application keeps a stopped run silently while asking about a terminated one (spec 09 §F).

One frequency per task, because that is the set of problems sharing influence matrices — Capytaine's cache holds exactly one entry, so splitting a frequency across workers would repeat the O(N²) assembly for every problem. `default_workers(n)` clamps to the frequency count and to the machine.

A separate **process**, not a thread: the Fortran matrix assembly holds the GIL for its whole duration, so a worker thread would freeze a user interface just as thoroughly as no thread at all. Terminating a process is also the only thing that interrupts a Fortran call.

`SolveOutcome` carries `requested`, `solved`, `failed` (`{omega: message}`), `elapsed`, `stopped`, `dataset`, and the properties `complete` and `missing`. Under several workers a cancelled run leaves **holes**, not a prefix — which is why it reports a set and not a count. Hand the dataset to [`store_result`](#store_resultmesh-dataset-settings--label-result_idnone---result).

### Meshing — `pylot_bem`

| | |
|---|---|
| `load_mesh_file(path, *, scale=1.0) -> (vertices, faces)` | Read a hull file. Use it to inspect one *before* committing to a library |
| `check_full_mesh(vertices)` | Refuses a half mesh. Judged against the beam, not against exact zero — a cut leaves residue on its own plane |
| `application_point_for(base_shape, transform) -> FloatArray` | Centre of the submerged bounds, vessel-local. `y` is **exactly zero** for a symmetric hull without heel, whatever the bounds say |
| `submerged_summary(base_shape, transform) -> SubmergedSummary` | `wetted_area`, `lo`/`hi` submerged bounds, `waterline_length`. Display only — nothing computes from them. **No volume**: the waterline cut leaves an open surface and pymeshlab refuses one rather than returning a number that would be wrong by whatever the missing waterplane contributes |
| `build_mesh(base_shape, transform, *, pct=2.0, iterations=20) -> MeshGeometry` | Geometry only, no storage |

### Estimates — `pylot_bem`

Three numbers to look at *before* starting a run that takes minutes.

| | |
|---|---|
| `solved_panels(mesh) -> int` | What the solver actually works with. **Doubles for a symmetric mesh.** Takes a `CalculationMesh` or a `MeshGeometry` |
| `influence_matrix_bytes(panels) -> int` | Peak memory for one solver process |
| `format_memory(panels) -> str` | The same figure as `~128 MB` or `<1 MB`. A formatter and not a number, because rounded to whole megabytes a small mesh reads `~0 MB`, which looks like a broken calculation rather than a small one |
| `shortest_reliable_period(vertices, faces) -> float` | Shorter waves still solve, and are wrong by an amount nothing downstream detects |

---

## Errors

| | Raised when |
|---|---|
| `LibraryError` | The file is not a library, is from a newer schema, an id is unknown, or a deletion would orphan something |
| `WorkspaceError` | A [`Workspace`](#workspace--editing-a-copy) could not open or save for a reason a person can act on. A `LibraryError`, so a handler for that catches it |
| `SourceChangedError` | `Workspace.save()`: the file was changed by someone else since it was opened — including during the wait for a file in use. A `WorkspaceError` |
| `SourceLockedError` | `Workspace.save()`: the file is read-only, or stayed open in another program for `REPLACE_BUDGET` seconds. A `WorkspaceError`; nothing was written and the original is exactly as it was |
| `AssemblyError` | A key is unknown, in conflict, or incomplete |
| `MeshPipelineError` | A half mesh, nothing submerged, a regrid that produced no faces, or a hull whose topology defeats one of the mesh filters — most often *not two manifold*. A `PyMeshLabException` never escapes: nothing above this layer has a reason to know a mesh library is underneath, and one that got out reached the application as a traceback on a stderr a windowed build does not have |
| `SolverError` | The excitation identity failed, the problems are not frequency-major, or the dataset disagrees with the settings |
| `ValueError` | Slopes outside the valid domain; a non-positive `scale` |
| `BridgeError` | A dataset the bridge cannot convert, or a non-positive `rho` |
| `sqlite3.IntegrityError` | An id is already used |

---

