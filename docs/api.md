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

[Units](#units-and-conventions) · [`Pylot`](#pylot--building) · [Plotting](#plotting) · [The application](#the-application) · [Solving](#free-functions) · [Errors](#errors)

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
uv run pylot-app                 # or: uv run python -m pylot_bem.app
uv run pylot-app tanker.pylot    # opening a library at startup
```

A window for building and inspecting libraries: a tree of **library → condition → mesh → result**, a 3D view, property panes, and tabs for Results, Databases, Inspect, Match and Validation. See the `pylot` specification, `06_ui_and_integration.md` and `09_ui_options.md`.

**It is a client of this API and nothing more.** Every action it performs is one call on `Pylot`; where something was missing — `set_info`, `store_result` — the answer was to put it here, not to reach past it. Anything the window had to work out for itself, every other caller would have had to work out too.

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
| `AssemblyError` | A key is unknown, in conflict, or incomplete |
| `MeshPipelineError` | A half mesh, nothing submerged, or a regrid that produced no faces |
| `SolverError` | The excitation identity failed, the problems are not frequency-major, or the dataset disagrees with the settings |
| `ValueError` | Slopes outside the valid domain; a non-positive `scale` |
| `BridgeError` | A dataset the bridge cannot convert, or a non-positive `rho` |
| `sqlite3.IntegrityError` | An id is already used |

---

