# 06 — Standalone UI (and deferred DAVE integration)

> **Scope decision.** DAVE integration is **postponed**. The deliverable is a **dedicated application, separate from DAVE**, for building and inspecting hydrodynamic libraries. Part B records the DAVE work for later; build none of it now.

---

# Part A — The standalone application

## 1. Why this is the better first target

Not merely a deferral — it improves the design:

- **It forces the DAVE-free boundary to be real.** `pylot_db` and the BEM package have no reason to reach into DAVE if nothing DAVE-shaped is present while they are built. A boundary tested from day one is a boundary that holds; ADR-7's import guard stops being aspirational.
- **The creation workflow is where the domain risk is.** Meshing, solving, assembling and inspecting are what the previous attempt got structurally wrong. A dedicated UI exercises exactly that, with no node lifecycle, scene serialisation or undo semantics in the way.
- **Faster feedback.** No `.ui` regeneration into DAVE's forms, no scene round-trip, no workspace registration.

**The application lives in the BEM package** (spec 07 §4) — it is the write side.

## 2. Toolkit

**PySide6**, following the existing project convention: designer `.ui` files in a `guis` folder, converted with `pyside6-uic`. Not because the standalone app needs the same toolkit, but because Part B eventually does, and rewriting the widgets then would waste the work.

3D view: **`vedo`** (already in the stack, spec 07 §1) rather than DAVE's VTK layer.

**A CLI ships alongside — DECIDED**, and it is deliberately tiny: three commands, for the two expensive scriptable steps (meshing and solving) plus the condition they hang off. See spec 10. Everything else is the Python API or this application; library setup is interactive work and stays here.

## 3. What it must do

Straight from `PACKAGES.md`'s write-side column:

| Area | Function |
|---|---|
| **Library** | Create; open; import a base shape **with a unit conversion and live bounds** (spec 09 §A); edit `vessel_name`, `description`, `origin_description` |
| **Probes** | Show and edit `probe_xy` (spec 05 §2.2). Defaults to bounding-box corners. Editing recomputes every condition's probe z — **say so before applying** |
| **Conditions** | Create by `z_origin`/heel/trim, one at a time; list; delete. Show the derived application point, read-only |
| **Meshes** | Create for a condition at a chosen `pct`/`iterations`; show in 3D; delete |
| **Results** | Solve a mesh over a **period**/direction grid at chosen `rho`/depth/speed, with an optional **lid** (spec 04 §2); show progress; delete |
| **Databases** | Show assembled databases by key (spec 02 §3), which results contribute, and which keys are **incomplete** or **in conflict** |
| **Resolve** | Conflict → compare the competing results on one plot → delete the loser, whole or per frequency (spec 02 §3.2). **This is the main loop of building a database**, not an error path |
| **Inspect** | Plot any quantity against frequency or period, for a database **or for competing results overlaid**; remove superseded data by condition / mesh / frequency (spec 02 §5.5) |
| **Validate** | Run `validate()` (spec 02 §6) and show the structured findings. **With no export (spec 09 §H) this is the only diagnostic a broken library has** |
| **Match** | Enter a trial `z_origin`/heel/trim, see **all** conditions sorted by probe error — exercises spec 05 with no DAVE |

That last row is worth building early: it is the only way to see matching behave before there is a vessel to match against, and it costs one form over an existing function.

> **Spec 09 is the field-by-field inventory** of every option and derived display listed here — written for mockup work.

## 4. Operational rules — salvaged

> **The shape of the application follows from ADR-9.** This is not a wizard that walks a user from base shape to database once. It is an **explore → compare → prune** loop: solve a variant, look at it, solve another, decide which to keep, delete the rest. Every screen should assume the library contains work in progress, including competing results, rather than a finished set.

These came out of the previous work's dock design, which was its strongest part. They hold here.

- Two lists: **conditions / meshes** and **results**.
- Selecting a mesh **does not filter** the results list — all results stay visible so resolution variants can be compared side by side. With ADR-9 this rule stops being a convenience and becomes load-bearing: comparing competing results is how conflicts get resolved.
- The results table shows which mesh each result belongs to.
- **Separate mesh and solve actions**, reflecting the real order of work.
- Mesh settings (`pct`, `iterations`, symmetry) appear **only** behind an explicit *Mesh Settings* button — not as a popup on every *Show mesh* / *Create mesh*.
- After meshing, show the mesh in the 3D view.
- Per result, show the solved **omega** and **wave-direction** counts and ranges. Users must be able to see what was actually solved.
- Symmetry is **derived and read-only** (spec 01 §4) — displayed with its reason, never as a checkbox.

### 4.1 Naming

Use the spec 00 vocabulary throughout: *condition*, *calculation mesh*, *result*, *library*, *surface probe*. Do not carry "case", "candidate" or "POA" into the new UI.

## 5. Visuals

- The **base shape**, with **backface colouring** — an inverted normal is a real failure and otherwise completely invisible. Always on, not a toggle (spec 09 §L).
- A stored **calculation mesh** for the selected condition, with the waterplane drawn, and its **lid** when present.
- The **surface probes** as points, with their z error against the trial condition. Cheapest and most informative check in the application: probes on the surface means a good match; one hanging above or below shows exactly where the mismatch is.
- The **application point** as a marker.

## 6. Solving is long-running

The one genuinely new UI problem — the previous design never faced it, because `fleetmaster.exe` was a subprocess and blocking was somebody else's problem. In-process Capytaine (ADR-1) runs on the caller's thread.

### 6.1 What Capytaine actually offers — verified against v2.3.1 source

**There is no cancellation mechanism.** A grep of all 73 source files for `KeyboardInterrupt|signal\.|SIGINT|timeout|cancel|abort` returns nothing; likewise in the Fortran. No callbacks, no hooks, no timeouts.

But `solve_all` is thinner than it looks. At `n_jobs=1` (the default) it is a plain list comprehension (`bem/solver.py:253-257`):

```python
if n_jobs == 1:  # force sequential resolution
    problems = sorted(problems)
    if progress_bar:
        problems = track(problems, ...)
    results = [self._solve_and_catch_errors(pb, ..., _check_wavelength=False) for pb in problems]
```

Sorting, a `rich` progress bar, and per-problem error catching. Nothing else. **We can write that loop ourselves.**

And the `n_jobs != 1` branch is equally thin — and tells us how Capytaine itself thinks about parallelism:

```python
groups_of_problems = LinearPotentialFlowProblem._group_for_parallel_resolution(problems)
parallel = joblib.Parallel(return_as="generator", n_jobs=n_jobs)
groups_of_results = parallel(joblib.delayed(self.solve_all)(grp, n_jobs=1, progress_bar=False, ...)
                             for grp in groups_of_problems)
results = [res for grp in groups_of_results for res in grp]
```

with (`bem/problems_and_results.py:257`):

```python
groups_of_indices = problems_params.groupby(
    ["body_name", "water_depth", "omega", "rho", "g"]).groups.values()
```

**The unit of parallelism is one frequency.** Each group holds every DOF and every wave direction at one omega, is sent whole to one worker, and is solved there **sequentially** — precisely so it hits that worker's matrix cache. `joblib`'s default backend is `loky`, i.e. **processes**.

### 6.2 Own the group loop — parallel by frequency

This grouping is the same fact that drives §6.3 and §6.4, so adopt it as *our* structure rather than nesting inside `solve_all`:

```python
groups = [problems_at(w) for w in omegas]        # we generate the problems; group at the source
with ProcessPoolExecutor(max_workers=n_workers) as pool:
    futures = {pool.submit(_solve_group, grp): w for grp, w in zip(groups, omegas)}
    for fut in as_completed(futures):
        ...                                      # report progress, collect, check cancel
```

where `_solve_group` builds its own `BEMSolver` and calls `solve_all(grp, n_jobs=1, progress_bar=False)`.

Three reasons to own it rather than pass `n_jobs`:

1. **Cancellation.** `shutdown(cancel_futures=True)` drops pending groups; killing the pool stops running ones. Nested inside `solve_all` we would be terminating a process tree we did not create.
2. **Progress.** `as_completed` reports each frequency as it lands. `solve_all`'s own bar writes `rich` output to stdout.
3. **No joblib.** `concurrent.futures` is stdlib; joblib is an optional Capytaine dependency.

We reproduce the grouping key ourselves — we generate the problems, so grouping by omega is free and does not depend on a private static method.

> **Windows is the target platform (spec 07 §0), and it has no `fork`.** Every worker is a fresh `spawn`: it re-imports Capytaine and receives the body and mesh **re-pickled per group**. That is a fixed per-group cost paid `n_omega` times, and it is the one thing that could make fine-grained grouping a net loss on a small mesh. Two consequences:
>
> - **Reuse workers across groups** — a pool, not a process per group. `ProcessPoolExecutor` does this by default; do not defeat it.
> - **Measure the spawn + pickle cost against the solve time of one frequency** before choosing a default worker count. If a frequency solves in less time than a worker takes to start, parallelism is noise.
>
> Coarser grouping (several frequencies per task) is the fallback if that cost dominates. It costs nothing in cache terms — a worker solving several frequencies sequentially still hits the size-1 cache within each — but it coarsens cancellation and partial-result granularity. Only do it if measurement demands it.

**Grouping by frequency is what preserves the caches.** Capytaine's caches live on the solver object, and one group is exactly the set of problems that share influence matrices:

| Cache | Where | Effect |
|---|---|---|
| Influence matrices S, K | `lru_cache` on `solver.engine.build_matrices`, **size 1** | Skips the O(N²) Fortran assembly |
| LU decomposition | `LUSolverWithCache`, keyed by matrix identity | Changelog: *"diminishing the total computation time up to 40%"* |
| Green-function tabulation | On the `Delhommeau` object, persisted to disk | Unaffected |

One solver instance per group, and all three work.

> **Frequency-contiguity is load-bearing.** The matrix cache is **size 1**. Every problem at a given omega — all six radiation DOFs plus every wave direction — must run consecutively in one process or the cache thrashes and the O(N²) assembly is repeated for *every single problem*. Sequential `solve_all` gets this from `sorted()` (`__lt__` orders on `(body, free_surface, water_depth, omega, …)`); we get it from the grouping. **Never split a frequency across workers, and never interleave frequencies within one.** Either would look like a harmless reordering and would be catastrophic.

Inside a group we can still call `solve_all(grp, n_jobs=1)`, which keeps Capytaine's per-problem error catching (`try/except` → `pb.make_failed_results_container(e)`) for free. Pass `progress_bar=False`, or set `CAPYTAINE_PROGRESS_BAR=0`; `rich` writing to a worker's stdout is not useful.

### 6.3 Cancellation granularity, and why it forces a process

Cooperative cancellation can only act **between problems**. Inside one `solve()`, time goes to two opaque calls: the f2py Fortran `build_matrices` (O(N²)) and `scipy.linalg.lu_factor` (O(N³)). Neither can be interrupted.

Worse for a thread: the Fortran extension has **no `!f2py threadsafe` directive anywhere in the source**, so f2py does not emit `Py_BEGIN_ALLOW_THREADS` and **the GIL is held for the whole matrix assembly**. A worker *thread* would therefore freeze the UI for the duration of a single problem's assembly — the exact thing the worker was for. (SciPy's LU does release the GIL; the Fortran half does not.)

**Therefore: a separate process. DECIDED** — this is no longer a judgement call.

It buys three things:

1. **True immediate cancellation.** Terminating the process kills the Fortran call mid-flight. The OS provides the interruption capability Capytaine lacks.
2. **The UI never blocks**, regardless of the GIL.
3. **Crash isolation.** A fault in the native code takes down a worker, not the application.

**The worker pool of §6.2 subsumes this.** A pool with `max_workers=1` is still a separate process, so there is no second code path for the sequential case — parallelism becomes a *setting*, not an architecture.

Two-tier cancel:

| Tier | Action | Latency | Partial results |
|---|---|---|---|
| **Stop** | `shutdown(cancel_futures=True)` — queued groups dropped, running groups finish | one frequency | Complete and keepable |
| **Kill** | Terminate the worker processes | immediate | Running frequencies lost; already-returned ones intact |

Report the expected wait for **Stop** so the choice is informed. Note that Stop's latency is one *frequency*, not one problem — with `n_workers` groups in flight, that is up to `n_workers` frequencies still finishing.

> **Killing must actually kill (Windows).** `ProcessPoolExecutor.shutdown()` does **not** terminate a running task — it waits for it. Kill therefore needs an explicit mechanism: a **Job object** with kill-on-close, or recursive termination of the worker PIDs. An orphaned worker holding ~800 MB and a full core is the worst failure mode in this design, and the naive implementation produces it. Build and test the kill path first, not last.

### 6.4 Partial results are worth keeping

Because the unit of work is a frequency, a cancelled run has **complete coverage of every frequency it finished** — all DOFs and all directions. The partial output is not ragged; it is a valid result over a shorter omega grid, and spec 02 §3 already assembles databases from multiple results.

Under a parallel pool, completed frequencies are **not contiguous** — with 4 workers on a 20-frequency grid, cancelling may leave a grid with a hole in it. That is still a valid result (nothing requires a uniform omega spacing), but the UI must **show which frequencies were kept**, not just a count.

So offer *"keep what was solved"* on cancel. It is a genuine feature: solve coarsely, watch it, stop when the interesting band is covered.

> **DECIDED, and split by tier (spec 09 §F).** A graceful **Stop keeps silently**; only **Kill** asks, defaulting to Discard. Whether a shorter grid is worth having is answered by looking at the curves, which needs the result to exist — asking first makes the user guess, and a wrong guess costs the run while an unwanted result costs one click. Kill is the exception because it is the emergency handle, not because what came back is any less complete. `SolveOutcome` therefore records `killed` as well as `stopped`, so the caller does not have to remember which button was pressed.

This **refines** spec 02 §5.4 rather than contradicting it. The rule is that a result is never partially *written*; a shorter omega grid is a complete result, not a partial one. Requirements:

- Keep only **whole frequencies**, never a partial one — otherwise the DOF/direction coverage really is ragged.
- Record on the result that it was truncated, and the grid actually solved.
- Discarding is still the default; keeping is an explicit choice.

### 6.5 Worker count — the two knobs interact

There are **two** layers of parallelism, and they multiply:

1. **Processes** — one per frequency group (§6.2).
2. **OpenMP threads** inside the Fortran, controlled by `OMP_NUM_THREADS`.

Left alone, `n_workers` processes each spawn `cpu_count` OpenMP threads and oversubscribe the machine badly. **Workers must set `OMP_NUM_THREADS` explicitly** — as an environment variable before the worker imports Capytaine, not after.

The split between them is a genuine trade-off and should be **measured, not guessed**: OpenMP scales the O(N³) LU well but shares one copy of the matrices; processes scale perfectly but each holds its own.

> **Memory is the binding constraint on `n_workers`.** Each worker holds two dense complex matrices — about `2 × 16 × N²` bytes, so **~800 MB at 5000 panels, per worker**. Four workers on that mesh need ~3.2 GB before anything else. The UI must make this visible (§UI list) rather than let a user pick 16 and swap the machine to a halt.

### 6.5.1 Measured timings — the machinery is justified

**A solve is seconds for a small mesh and runs into minutes for a larger one.** That settles what was previously guesswork, and it validates the design rather than trimming it: at minutes per solve, users *will* want to stop a run, and discarding everything when they do is expensive.

Consequences that follow directly:

- **Cancellation is worth its complexity.** At 200 ms it would not have been. Both tiers earn their place.
- **Keep-what-was-solved is worth offering** (§6.4). Binning tens of minutes of work to change one setting is the behaviour that makes users avoid the Stop button.
- **The memory ceiling binds before the core count does** on exactly the meshes that take minutes — they are the ones with the panel counts (§6.5). Worker count must be memory-aware, not just `cpu_count`-aware.
- **The orphaned-worker failure of §6.3 gets worse**, not better: a leaked worker on a large mesh holds ~800 MB and a full core for minutes. Build the kill path first.

> **Work within a frequency group is very unevenly distributed.** The first problem at a given omega pays the O(N²) matrix assembly and the O(N³) LU; the remaining problems at that omega — the other DOFs and every wave direction — reuse both caches and are comparatively instant. So a group is *one expensive solve plus a tail of cheap ones*, and:
>
> - **Report progress per frequency, never per problem.** A per-problem bar would crawl and then jump by forty steps, which reads as a hang followed by a glitch.
> - **Estimate remaining time from completed frequencies**, which are uniform, rather than from problem counts, which are not.
> - **Graceful Stop latency ≈ one frequency**, not one problem — and because groups run concurrently, adding workers does not extend it. Show that estimate on the Stop button.

> **Sizing caution.** Assembly is O(N²) and the LU is O(N³), so the jump from seconds to minutes is steep in panel count. Mesh density `pct` (spec 03) is the knob users reach for first and the one that decides which regime they are in — show the projected cost before Start (spec 09 §D), not after.

### 6.6 Remaining requirements

- Progress is reported **per frequency**, with the total known up front. **Not per problem** — see §6.5.1; work within a group is very unevenly distributed and a per-problem bar misreports it.
- A solver failure surfaces its diagnostics in the UI, not only on stderr. A group that fails must not silently vanish from the omega grid.

## 7. Tests

1. The CLI performs the whole flow: create library → condition → mesh → solve → assemble → validate.
2. Probe edit recomputes all conditions and the UI reports what changed.
3. Validation findings render; a deliberately corrupted library is displayed, not crashed on.
4. Match view ranks a fixture library correctly for a given trial condition.
5. Cancelling a solve leaves the library byte-identical. **Under §6.4's ruling this is the Kill-then-Discard path**, since Stop now keeps; both are tested, and the byte comparison is on the file, not on a result count — a write that was rolled back or left a page dirty is exactly what a count misses.
5a. **Kill during a solve leaves no surviving worker process** — assert on the PIDs, not on the UI returning to idle. This is the test that catches the orphaned-worker failure of §6.3.
6. The application imports and starts with DAVE **not installed**.

---

# Part B — DAVE integration (deferred)

> Not scheduled. Recorded so nothing in Parts A or specs 01–05 forecloses it.

## 8. The node

- Node class with a **bare constructor** (no library assigned).
- API properties via getters/setters: `library`, `parent` (a `Frame`), `origin`, `offset` (user alignment correction, spec 05 §3.1 — *not* the application point).
- Register (`init`, `DAVE_xxx`), then `make_proplist.py` to regenerate node documentation from docstrings.
- **Scene warning** when no library is assigned.
- Must survive `scene.copy()` — if copy works, save and undo work too.
- `Scene.new_xxxxx()` returning the new node; the scene must be **unchanged** if arguments are faulty.

The node passes its frame's global transform to `select()` (spec 05 §3) as a plain `(4,4)`. No DAVE type crosses into `pylot_db`.

**Open when resumed:** new node type vs extending `WaveInteraction1`; the library path being set before the library exists (the previous attempt stored absolute paths in scenes, which do not survive moving between machines); and where the DAVE-side code lives, given that the node needs only `pylot_db` while any creation UI pulls the BEM stack.

## 9. GUI

Add to the new-node context menu via the `.ui` file and the `run.bat` conversion entry; register an icon; node editor as a `NodeEditor` widget in `widget_nodeprops`, applying changes through **`run_code`**.

Widgets built for Part A are reusable here — the reason Part A uses PySide6.

## 10. Visuals and runtime

Base shape and calculation mesh displayed temporarily, as with the shear/bending line preview.

### 10.1 Correction to the previous preview rule

The previous design required stored meshes to be "global" and **not move** with the vessel. That followed only from its incorrect claim that meshes were stored in world coordinates.

A calculation mesh lives in **diffraction space**, defined relative to the vessel by the floating condition. To display it: diffraction → vessel-local (`T⁻¹`) → world. It therefore **moves with the vessel, correctly** — vessel-attached geometry, not world-anchored.

The meaningful check is whether the stored mesh at its condition agrees with where the vessel currently floats. That is spec 05's match quality, shown geometrically — and the surface probes show it more directly.

### 10.2 Runtime

`prepare_for_fd` consumes the top of a `Ranking` (spec 05 §4), and a poor match produces a model warning.

**This is where the acceptance rule gets decided.** Spec 05 §2.3 removed the threshold — the match view ranks and the user chooses, so nothing in Part A needs one. Automatic selection does. Decide it here, against a real vessel, not in the abstract.

## 11. Tests when resumed

1. Node round-trips through `scene.copy()`, save/load and undo.
2. `new_xxx()` with faulty arguments leaves the scene unchanged.
3. Scene warning when no library is assigned.
4. Node editor applies changes via `run_code`.
5. `prepare_for_fd` handles both node types; a poor match produces a model warning.
6. Old scenes containing `WaveInteraction1` still load unchanged.
