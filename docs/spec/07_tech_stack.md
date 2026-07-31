# 07 — Tech stack

## 0. Platform — **DECIDED**

**Windows is the target.** Linux is nice to have and is never a reason to complicate anything: where a portable solution costs more than a Windows-specific one, take the Windows one.

Consequences that actually bite:

| Area | Windows fact | Where it lands |
|---|---|---|
| Process start | No `fork`. Every worker is a `spawn` — re-imports the module and re-pickles its arguments | Spec 06 §6.2 — a fixed per-group cost, and the reason to reuse pooled workers |
| Killing workers | No process groups, no `SIGKILL` to a tree. Needs a **Job object** or explicit recursive termination | Spec 06 §6.3 — build this first; the naive version orphans workers |
| Paths | Case-insensitive, backslashes, 260-char limit unless long paths are enabled | One of the reasons library storage is a **single SQLite file** rather than a tree of generated names (spec 02 §5) |
| Shell | PowerShell, per `CLAUDE.md` | Tooling and CLI docs |

CI runs on Windows. A Linux-only test failure is a bug report, not a release blocker.

**No portability abstraction layer.** Do not add one speculatively; if Linux support is ever wanted, port then.

## 1. Dependencies

| Package | Version | Role |
|---|---|---|
| Python | `>= 3.14` | Pinned in `.python-version`. Chosen for the typing features |
| **capytaine** | `>= 2.3.1` | BEM solver, **in-process** (ADR-1) |
| **pymeshup** | `>= 26.3.4` | Mesh transform, cutting, regrid (ADR-2) |
| **numba** | `>= 0.60` | Not used directly — a **resolver floor**, see §3.1 |
| **vedo** | `>= 2026.6.1` | Mesh display |
| **mafredo** | `>= 2026.7.1` | `Hyddb1` — the runtime database object. Carries `phase_origin`, `create_from_data`, and the corrected layout/direction docstrings (spec 04 §7) |
| **xarray** | | Result datasets |
| **numpy** | | Held at 2.4.6 by numba — see §5 |
| h5netcdf | | `Hyddb1.save_as` default engine |

Resolved versions are in §5. **DAVEcore is not a dependency of either package** — neither depends on DAVE (ADR-8).

### Removed

**`fleetmaster`** — the external executable, its settings file, its path setting, its version gate and its output parsing. See ADR-1.

### 1.1 Owned dependencies — `mafredo`, `pymeshup`, `dave`

**All three are owned and controlled by this project.** None is a third party. This changes how several problems below are solved: the correct fix for a defect in an owned dependency is **in that dependency**, not a workaround here.

The rule that follows: *do not accumulate compensating code in this package for behaviour we can correct at source.* The previous implementation carried workarounds for exactly such issues (§3.2), which is how a defect becomes permanent.

The one change that blocked this spec has **landed and is published**: **mafredo 2026.7.1 on public PyPI** carries the `(x, y)` phase origin relative to the force application point (spec 01 §5.4.1), `create_from_data` (spec 04 §7), corrected layout and wave-direction docstrings, and `ValueError` in place of bare asserts. See `mafredo_bug_report.md`.

Floor is `mafredo>=2026.7.1`. **Replace the hand-edited 2026.7.0 in `dave-development/.venv`** with the published release — a local edit to `site-packages` is invisible to every other machine.

**Cross-repo discipline.** Ownership removes the negotiation, not the coordination. Each owned dependency needs a **version floor** in `pyproject.toml` bumped in the same change that relies on the new behaviour, so a stale checkout fails at install rather than at runtime with a wrong-phase database.

### 1.2 Storage dependency

Storage is **SQLite** (spec 02 §5), and `sqlite3` is in the standard library — **no new dependency**. The directory alternative would have needed a YAML library.

## 2. Licensing

Capytaine was **GPL-3** and has been **relicensed to Apache 2.0**. This is the fact that unblocks the whole architecture: under GPL-3 it could not be bundled with DAVE, which is why the previous design pushed it behind `fleetmaster.exe`.

**Action:** confirm the Apache 2.0 licence on the exact version pinned before shipping, and record the finding. The architecture depends on it.

## 3. Known traps

### 3.1 The numba floor (already diagnosed in pylot)

`pymeshup` → `cadquery` pulls in an unpinned `numba`. Without a floor, uv backtracks to `numba 0.53.1` (no Python ≥ 3.12 wheel) chasing the newest numpy, then fails to build it. Pinning a modern numba makes uv drop numpy to a compatible version instead.

**Keep `numba>=0.60` as an explicit dependency**, with the comment explaining why. It looks removable and is not.

### 3.2 VTK imports — resolved, no action

An earlier draft of this spec listed a "VTK conflict between `pymeshup` and DAVE" as a known trap. **That was an overstatement and is withdrawn.**

The evidence was one commit on the `hyddb` branch, `95bdc532`, whose subject reads *"update vtk import more specifically to avoid crash with vtk from pymeshup"*. The diff is a single line in `DAVE/visual_helpers/overlay_actor.py`:

```diff
- from vtk import vtkCommand
+ from vtkmodules.vtkCommonCore import VTK_UNSIGNED_CHAR, vtkCommand
```

This is the routine `vtk` → `vtkmodules` narrowing. The top-level `vtk` package is a shim that eagerly imports every VTK module, which is fragile when another distribution supplies its own VTK build; importing the specific submodule avoids the eager load. The fix is correct and already applied.

**No ongoing risk, and nothing to change in `pymeshup`.** The only durable lesson is a coding convention, which DAVE already follows elsewhere: **import from `vtkmodules.*`, never `import vtk`.**

### 3.3 A lid silently disables symmetry

`docs/user_manual/body.rst` (v2.3.1): *"Currently, meshes with a symmetry are not supported, in the sense that the computation will be done without using the symmetries when a lid is added."*

Nothing warns. A symmetric solve that gains a lid silently becomes several times more expensive. See spec 04 §2.1 — and **re-check it on every Capytaine upgrade**, since the documentation says this should improve.

### 3.4 Complex values do not survive netCDF

netCDF has no complex type; Capytaine force data is complex. Split on write, merge on read, at the persistence boundary only (spec 02 §5.3). Cover with a save→load→compare test.

### 3.5 `mafredo` warns where it should raise

`Hyddb1.create_from_capytaine_dataset` calls `_check_dimensions()` and emits a **warning** on mismatch rather than raising. A malformed database therefore passes silently.

**Largely sidestepped.** With the bridge on `create_from_data` (spec 04 §7), that converter is no longer on the production path — it survives only as the equivalence reference in test 2. And `set_data` runs **no** dimension check at all, so the answer here is our own shape validation at the call site (spec 04 §7.6), not a change in `mafredo`.

Still worth making it raise if `mafredo` is touched again for another reason, but this is now a low-priority tidy rather than a defect on our path.

### 3.6 `pymeshup` is a heavy dependency

**Confirmed by resolution, no longer an inference:** `uv sync` on `pylot-bem` installs `cadquery 2.8.0` and its stack. It is a real transitive dependency.

**We own `pymeshup`, which reframes the fallback.** If the weight is unacceptable, the answer is not to abandon it for raw `pymeshlab` and reimplement `transform` / `cut_at_waterline` / `cut_at_xz` / `regrid` here — it is to make `cadquery` **optional in `pymeshup`**, since this pipeline uses none of it. That keeps `pylot` as executable reference code and keeps the geometry operations in the package that owns them.

Check first whether the pipeline's call set (`Volume`, `transform`, `cut_at_*`, `regrid`, `bounds`) touches `cadquery` at all. If it does not, an extras split is a small change with a large payoff.

## 4. Package split — **DECIDED**

Per `PACKAGES.md`: **two packages**, so end users are not forced to install the calculation stack.

| | **`pylot_db`** — read side | **BEM package** — write side |
|---|---|---|
| Depends on | numpy, xarray, mafredo, storage lib | `pylot_db` **+** capytaine, pymeshup, cadquery, numba |
| Open a library, retrieve contents | **X** | |
| Build `mafredo.Hyddb1` from a database | **X** | |
| **Matching / selection** | **X** | |
| Plotting and visualisation | **X** | |
| Create or modify a library | | **X** |
| Create floating conditions | | **X** |
| Create meshes and results | | **X** |
| UI, CLI | | **X** |

### Why the surface-probe decision matters here

The two documents fit together: **probe matching is what makes this split possible.** The scoring I previously proposed needed the base shape transformed and cut at the waterline for every selection — i.e. `pymeshup` at runtime, in the read package, defeating the whole point. Probe evaluation is a matrix-vector product on stored numbers.

**Test this, don't assume it:** an import-guard test asserting `pylot_db` imports cleanly with capytaine and pymeshup absent. Without it, a stray import in a rarely-taken branch silently re-couples the packages and nobody notices until an end user's install breaks.

### Consequences for the rest of the specs

| Spec | Package |
|---|---|
| 01 transforms, 02 domain model & storage (read), 05 matching | `pylot_db` |
| 02 write path & validation, 03 mesh pipeline, 04 solver | BEM package |
| 06 Part A — standalone app and CLI | BEM package |
| 06 Part B — DAVE node, visuals, `prepare_for_fd` | **Deferred** |

Spec 01's transforms are needed by both and belong in `pylot_db`; the BEM package imports them.

**Neither package depends on DAVE.** With DAVE integration postponed, nothing in the current scope does — `select()` takes a `(4,4)` matrix (spec 05 §3), not a `Frame`. Keep it that way when Part B is resumed: the DAVE side depends on `pylot_db`, never the reverse.

### Names and location — **DECIDED**

| | Distribution | Import |
|---|---|---|
| Read side | `pylot-db` | `pylot_db` |
| Write side | `pylot-bem` | `pylot_bem` |

Deliberately **not** `dave-*`, despite that being the house convention in `dave-development/packages/`: a `dave-` prefix on a package that must never import DAVE misleads an end user installing it standalone.

**They live in their own repository** (`C:/dev/pylot`), not as workspace members of `dave-development` — they are independent of it in every sense: separate git repo, separate `.venv`, and every dependency resolving from public PyPI.

Both packages share that repository as a two-member uv workspace, since they are developed in lockstep and `pylot-bem` depends on `pylot-db`. One consequence to note: **`setuptools_scm` gives both the same version**, taken from the repository's git tags. Fine while they release together; split the repository if they ever need to diverge.

### This resolves §3.6

The `pymeshup` weight objection largely dissolves: it is a dependency of the **write** package only. End users installing `pylot_db` never see `cadquery`. Making it optional inside `pymeshup` becomes an optimisation for engineers, not a distribution blocker.

## 5. Environment status — **resolved**

The two packages live in an **independent repository**, `C:/dev/pylot`, unrelated to `dave-development`: its own git repo, its own uv workspace, its own `.venv`. Every dependency resolves from **public PyPI** — no `davelab` index is needed, because `mafredo` is published there.

```bash
uv sync
uv run pytest
```

Resolved and verified working:

| | |
|---|---|
| capytaine | 2.3.1 |
| pymeshup | 26.7.0 |
| mafredo | 2026.7.1 |
| numba | 0.66.0 |
| **numpy** | **2.4.6** |
| vedo / vtk | 2026.6.1 / 9.6.2 |
| cadquery | 2.8.0 (transitive, via pymeshup) |
| xarray, scipy | 2026.7.0, 1.18.0 |

> **numpy is held at 2.4.6 by `numba`**, where `dave-development` runs 2.5.1. Harmless today — separate environments — but worth knowing before DAVE integration: **`numba` is a dependency of `pylot-bem` only**, so a DAVE installation taking `pylot-db` alone is not constrained by it. The package split protects DAVE's numpy floor as a side effect. Do not "tidy" numba up into the shared layer.

**`setuptools_scm` needs `root = "../.."`** in each package. It defaults to the package directory and does not search upward, so a workspace layout fails to build without it — with an error that points at git metadata rather than at configuration.

## 6. Reference code to port

`pylot` is proof-of-concept quality and should be **ported, not imported**:

| From | To | Change |
|---|---|---|
| `transformations.py` | Library core | Port as-is; add validation (spec 01 §3.4) and rename `draft` per spec 01 §3.5 |
| `capytaine_and_pymeshup.py :: _make_calculation_mesh` | Mesh pipeline | Take the base shape as a parameter — the current version ignores its argument and re-calls `_give_baseshape()`. Also **swap the two cuts** (waterline before XZ) to expose the submerged bounds, per spec 03 §1 |
| `ExampleRunner.run_radiation` / `run_diffraction` | Solver | Combine into one assembled dataset (spec 04 §5) |

Keep `pylot` as the living reference for experiments; do not make production code depend on it.
