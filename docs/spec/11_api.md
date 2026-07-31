# 11 — The Python API (write side)

> Split when the two packages became separate repositories. Sections 1, 2, 4
> and 7 appear in both, because each is an argument about the pair and does
> not survive being told in halves. The rest is divided by side.

## 1. One object

```python
from pylot_bem import Pylot, SolveSettings

d = Pylot.create_new("tanker.pylot", "tanker.stl", "stern, centerline, keel",
                     is_xz_symmetric=True, scale=1.0)
d.add_probe(0.0, 5.0)
d.add_probe(20.0, -5.0)

condition = d.create_condition(z_origin=-5.0)
mesh      = d.create_mesh(condition, pct=2.0)
result    = d.run_solve(mesh, SolveSettings(omegas=[0.4, 0.5, 0.6],
                                            wave_directions=[0, 90, 180]))
```

Three properties, each a decision:

**`Pylot` *is* a `Library`, by subclassing.** Not a wrapper around one. One file on disk has one class name, every read method is on the builder for free, and there is no delegation layer to keep in step. `Pylot.open()` and `Pylot.create()` are inherited unchanged and return a `Pylot`, which is what `Self` in the signatures buys.

**Flat, not navigable.** `d.create_mesh(condition)`, never `condition.create_mesh()`. The entities are frozen dataclasses that spec 02 §1 calls plain data, and giving them methods means giving them a live database connection — a mutable twin of every entity. One object carries the behaviour; the rest carry values.

**Entity or id, interchangeably.** `d.create_mesh(condition)` and `d.create_mesh("design")` are the same call. Ids are how the CLI and the application name things; objects are how a script holds them.

## 2. What the API is actually for

Not convenience. **Three derivations span the two packages**, and before this layer existed each caller reimplemented them:

| Derivation | Where it goes wrong |
|---|---|
| **The application point** is computed from *submerged* geometry, stored **vessel-local**, and converted **back** into diffraction space to solve | Passing the stored point straight to `solve()` puts the moment reference out by the draft. Silently — the numbers stay plausible |
| **`is_xz_symmetric`** follows from the base shape *and* the condition's heel | A half-vessel solve at a heeled condition. This is the exact defect ADR-4 records from the previous attempt |
| **The physical settings** must be the same numbers in the solve and in the stored metadata | A result recording a depth it was not computed at is unmatchable forever, and nothing shows why |

The third was live in this codebase until this spec was written. `solve(..., settings)` and `add_result(..., rho=, g=, water_depth=, forward_speed=)` took the physical conditions independently; the CLI and the end-to-end test passed matching values by discipline, not by construction. `Pylot.run_solve` takes **one** `SolveSettings`, feeds both, and cross-checks the returned dataset against it — the dataset carries `rho`, `g`, `water_depth` and `forward_speed` as its own coordinates, so a disagreement is detectable and is now an error.

**Density is now a fourth derivation, solved by removing it.** Results are exactly linear in water density (spec 04 §4, measured bitwise), so every solve runs at 1 t/m³ and the density is applied when a database is delivered. `SolveSettings` has no `rho` and `Result` has no `rho`: there is no field to be wrong in. The check that used to compare the requested density against the dataset's now compares the dataset against `SOLVE_RHO_SI`, which turns "stored per unit density" from a convention of the writing code into a property of the file.

`lid_mode` is the same shape of problem one level down: it is a pure function of `lid_z`, so it is a **property** on `SolveSettings` rather than a second argument. It was previously passed by the CLI as its own flag spelling — `"below"`, a value outside `LidMode`'s `Literal`, stored with nothing to catch it.


## 3.1 Geometry, and looking at it

Retrieval was already there — `base_shape`, `mesh(id)`, `meshes()` — with one gap: the base shape is stored **vessel-local** and a calculation mesh is **diffraction-space**, and nothing in a vertex array says which. Drawing both in one scene needs the hull placed, so `Pylot.base_shape_at(condition)` does that and returns a full vessel, never a half.

`Library.hyddb(condition, rho=...)` is the direct route to a `mafredo.Hyddb1`. It existed only through `assemble(key)` — which means fishing an `AssemblyKey` out of `databases()` first — or through `deliver()`, which goes via matching. Neither is what you want when you already know the condition. `rho` is required and **scales**; `forward_speed` and `water_depth` are optional *filters*, and a condition with several databases is reported with what it has, not resolved by rule (ADR-9).

`pylot_bem.plotting` is `vedo`, so it is VTK. The split that matters is **`to_polydata` for the application, `show` for a script** — a Qt widget renders the polydata directly and never touches a plotter. It is not exported from `pylot_bem`, because importing VTK costs the CLI 0.4 s for nothing.

> This is **not** the application. It is the geometry the application will draw, reachable now, so that Phase 7 inherits a rendering path rather than inventing one.


## 4. Units at the boundary

| | API | Boundary |
|---|---|---|
| Heel, trim | **slopes** | Degrees only in the CLI and the UI |
| Frequency | **omega** [rad/s] | Periods in seconds in the CLI and the UI |
| Density | **t/m³** | Not a solve input at all. Solves run at 1 t/m³; delivery scales |
| Wave direction | **degrees**, direction of travel | Radians inside the dataset, as Capytaine emits them |
| Length | **metres** | `scale` at mesh import — the only unit conversion in the system |

`Result.wave_directions` stored **radians** until this work, contradicting its own docstring, three files from where `to_hyddb1` did the identical conversion correctly. Nothing behavioural depended on it, which is why it survived — and the `pylot_db` fixture fed degrees in, so the round-trip test compared degrees with degrees and passed. The fixture now stores radians like Capytaine does.

> **A fixture that is easier than the real thing tests the fixture.** This is the same failure mode as the categorical dof coordinates found in Phase 5, and both were found only by a test that ran the real path.


## 5. Long solves

`solve()` and `run_solve()` take `progress: Callable[[done, total], None]`.

**Per frequency, never per problem** (spec 06 §6.5.1, measured). The influence matrices are assembled once per frequency and cached for that frequency's remaining problems, so the first problem does nearly all the work and the other seven or forty finish immediately — a per-problem count reports that as a hang followed by a jump.

Providing it means driving the problems ourselves rather than calling `BEMSolver.solve_all`, which has three consequences worth stating:

- **Our frequency-major ordering is now load-bearing.** `solve_all` sorted its input by `(body, free_surface, water_depth, omega, …)`, which is frequency-major, so the ordering in `make_problems` was previously a redundant agreement with Capytaine. Nothing re-sorts now, and a frequency appearing twice rebuilds its O(N²) matrices. Checked, not assumed.
- **Capytaine's two pre-flight checks are run by hand.** They are private methods, so a test asserts both warnings still reach a caller — a rename upstream has to fail loudly rather than quietly remove them. They are **log records**, not `warnings.warn`, so they reach a terminal via `logging.lastResort` and an application that configures logging decides whether its users ever see them.
- **`solve` is called, not `_solve_and_catch_errors`.** A failed problem stops the run instead of becoming a `FailedResult` that reaches storage as a database full of NaN.

**Cancellation is raising from the callback.** No flag, no thread, no machinery: the exception propagates out untouched and nothing is stored. It lands at a **frequency** boundary. Finer than that is what the worker pool buys — a single problem is a Fortran call that cannot be interrupted at all.

## 6. Estimates

Three numbers a user needs *before* starting a run that takes minutes: `solved_panels`, `influence_matrix_bytes`, `shortest_reliable_period`. They were written inside the CLI first, which made them unavailable to the application — the same derivations would have been rewritten there, and the two could then disagree about the same mesh.

`solved_panels` is specifically the doubling trap that `CalculationMesh` says "belongs in one function, not at each call site" — and the CLI had it written out at two.


## 7. Open questions

| Ref | Question | Recommendation |
|---|---|---|
| §1 | `create_new` takes a mesh **file**. Should it also take vertices and faces? | No — `Library.create` already does, and is inherited |
| §2 | `lid_mode` is now derived from `lid_z`, so the stored column is redundant | Drop the column at the next schema change; not worth one on its own |
| §5 | Should `progress` also report the frequency in rad/s, not just a count? | Probably, when the application says what it wants to display |
| §7.1 | **Wave directions cannot be added to a frequency that already has some** | See below — needs a decision before the UI offers "add a direction" |

### 7.1 A diffraction-only solve is not producible

`make_problems` always emits the six radiation problems, so every result from `pylot_bem` carries `has_radiation = True`. Two consequences, measured rather than reasoned:

- **You cannot extend a frequency with another wave direction.** Solving 0° and then 90° at the same omega conflicts on *both* quantities. The diffraction conflict is arguably wrong on its own terms — the two results cover different directions — but `Coverage` is keyed on frequency alone, and `_merge` concatenates diffraction on `omega`, so neither the detection nor the merge supports it. Adding a direction today means deleting that frequency and solving it again with the full set.
- **The complementary case is unreachable from the build side.** Spec 02 §3.1 blesses radiation from one result and diffraction from another at one frequency, and assembly implements it — but nothing in `pylot_bem` can produce a result without radiation. It is reachable only by handing a dataset to `Library.add_result` directly, which is what the `pylot_db` tests do.

Three ways out, none of them free:

1. **A `radiation=False` switch on `SolveSettings`**, making the complementary case producible and letting a user add directions cheaply. Smallest change; leaves the direction conflict as it is.
2. **Key `Coverage` on `(omega, direction)` for diffraction**, so different directions at one frequency are complementary rather than conflicting. Truer to the physics, and it means `_merge` has to combine on two dimensions.
3. **Neither** — declare the direction set fixed per frequency and have the UI say so. Cheapest, and defensible: re-solving six radiation problems is a fraction of a solve that is already minutes long.

Not decided. It matters for the application, which will want an "add a direction" action.
