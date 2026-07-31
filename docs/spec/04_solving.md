# 04 — Solving

> Split from a single *Solver and results* document when the two packages became
> separate repositories. What is here is driving Capytaine. Turning what it
> returns into a delivered database is
> `pylot-db`'s `docs/spec/04_results_and_delivery.md`.

Capytaine is called **in-process** (ADR-1). Reference: `pylot/capytaine_and_pymeshup.py`.

## 1. Body construction

```python
body = cpt.FloatingBody(
    mesh=mesh,
    lid_mesh=lid_mesh,          # generated here from the solve settings — §2
    dofs=cpt.rigid_body_dofs(rotation_center=application_point_diffraction),
    name=name,
)
```

`rotation_center` **is** the application point (spec 01 §5.2). It does not move the mesh and does not affect the phase origin.

It is read from the **condition** (spec 01 §5.4.3), stored vessel-local, and converted to diffraction space with `T` at this call site — the only place that conversion happens:

```python
ap_local = condition.application_point                     # stored, vessel-local
application_point_diffraction = (condition.transform @ [*ap_local, 1.0])[:3]
```

## 2. The lid — a solver setting, not geometry

A lid is an **artificial numerical construct introduced only for the solver**: it removes irregular frequencies and it is not part of the vessel. It therefore lives with the solve settings, alongside `water_depth` — **not** on the `CalculationMesh`.

```python
lid_mesh = mesh.generate_lid(z=lid_z, faces_max_radius=lid_radius)   # or None
body = cpt.FloatingBody(mesh=mesh, lid_mesh=lid_mesh, dofs=..., name=name)
```

| Setting | Meaning |
|---|---|
| `lid_mode` | `None` (default) / at free surface / below free surface / auto |
| `lid_z` | `0.0` at the surface; a small negative value below it |
| `lid_radius` | `faces_max_radius`; defaults to the mean hull face radius |

**Generated at solve time, never stored.** `generate_lid` is deterministic given the hull mesh and these two numbers, and it is cheap — a clip plus a rectangle mesh. Storing the geometry would be a cached derived value with a second copy to keep consistent.

Four facts from the v2.3.1 source and documentation that must survive into the implementation:

1. **Panels on the free surface are still experimental.** A lid at `z = 0` is the efficient choice; slightly below (e.g. `−0.1`) is the robust one: *"The lower the lid, the more robust the computation, but also the less irregular frequencies are removed."*
2. **Auto** is `mesh.lowest_lid_position(omega_max)` — the lowest lid still removing every irregular frequency below `omega_max`. Since `omega_max` is a solve setting and the lid is now one too, this is a **self-contained** calculation.
3. **The lid need not cover the whole interior free surface, nor connect to the hull.** Partial coverage is valid; more coverage removes irregular frequencies more effectively.
4. **Normals must point down**, into the fluid. Capytaine flips them itself for a horizontal lid with normals up.

> **Trap: `lowest_lid_position` returns NaN outside its domain.** It computes `arctanh(π·g·p/ω_max²)`, which requires `π·g·p < ω_max²` — for a 100 × 30 m hull, `ω_max > 1.04 rad/s` (periods under 6.1 s). Below that, numpy yields NaN and `generate_lid(z=NaN)` produces a corrupt mesh. Physically it means *there are no irregular frequencies in this range and no lid is needed*. **Detect it and say that**; never pass the value through.

### 2.1 A lid disables symmetry in the solve — the dominant cost

`docs/user_manual/body.rst`, v2.3.1: *"Currently, meshes with a symmetry are not supported, in the sense that the computation will be done without using the symmetries when a lid is added."*

Nothing fails and nothing warns — the solve silently stops exploiting `ReflectionSymmetricMesh` and gets several times more expensive. The physics stays correct: a `ReflectionSymmetricMesh` *is* the whole body, only its block structure goes unused.

> An earlier draft claimed the opposite from the changelog line that `generate_lid` *"should now work with reflection symmetric meshes without losing the symmetry"*. Both are true and they concern different things: the **generator** preserves the mesh object's symmetric structure; the **solver** ignores symmetry whenever a lid is present. Only the second costs anything.

Consequences:

- Turning a lid on for a symmetric condition trades away the symmetry speedup. Show that cost where the choice is made (spec 09 §E.2).
- It makes lid-vs-no-lid a genuine cost decision, which §2.2 turns to account.
- **Re-check on every Capytaine upgrade.** The documentation says this *"should be improved… in a future version"*, and that upgrade changes the economics.

### 2.2 Frequency dependence — two results, not a varying lid

The required lid depth depends on frequency: `first_irregular_frequency_estimate` (`bodies/bodies.py:1139`) uses the **lid depth** as the effective draft, returning `inf` for a lid at `z ≈ 0`. Deeper lid → lower first irregular frequency → less protection.

The dependence is **monotonic and one-sided**, so one lid chosen for `omega_max` covers every frequency below it. A per-frequency lid is never needed for correctness.

Where a frequency-dependent lid *is* wanted, it needs no new machinery now that the lid is a solve setting — **two results on the same mesh**:

- the low band **without** a lid — symmetric, hence cheap (§2.1);
- the high band **with** a lid — the only band that has irregular frequencies at all;
- assembled into one database by spec 02 §3, which merges complementary results per frequency.

The natural split point is the hull's own `first_irregular_frequency_estimate` with no lid: below it a lid buys nothing and costs the symmetry speedup.

**The bands must not overlap.** Overlapping frequencies put the key in conflict and produce no database until the user resolves it (spec 02 §3.1) — which is correct here too: at a frequency covered both with and without a lid, only one answer is right, and nothing in the settings says which.

## 3. The two problems

| Problem | Yields |
|---|---|
| **Radiation** | Added mass and damping (6×6 per frequency) |
| **Diffraction** | Wave exciting forces. Capytaine yields `Froude_Krylov_force`, `diffraction_force` and `excitation_force` (complex, per mode); **only `excitation_force` is kept** |

**Keep only `excitation_force`.** It is the only quantity the database needs, and `Hyddb1` consumes only it. `Froude_Krylov_force` and `diffraction_force` are dropped at the persistence boundary — roughly a third less complex force data to store, split and merge (spec 02 §5.3).

> `excitation_force == Froude_Krylov_force + diffraction_force` remains a **free correctness check on the whole chain** — capytaine computes all three whether or not we keep them. Assert it **at solve time**, on the in-memory results, before discarding the components. It costs nothing and it is the cheapest check in this specification that something has gone structurally wrong.

Typically both run on the same omega grid, but that is **not required**.

## 4. Inputs

| Input | Notes |
|---|---|
| `mesh` | Depends on a floating condition (spec 03) |
| `water_depth` | `None`/`inf` for infinite |
| `forward_speed` | Default `0` |
| ~~`rho`~~ | **Not a setting.** Every solve runs at `SOLVE_RHO = 1 t/m³`; see below |
| `g` | e.g. 9.81 |
| `omegas` | Both problems |
| `wave_directions` | Diffraction only |

> **`rho` crosses a units boundary here — DECIDED.** Storage and the UI work in **t/m³** (1.025); Capytaine is an SI code whose `rho` defaults to `1000.0` kg/m³; and `mafredo` divides by 1000 to reach kN and mt. Those three only fit together if **Capytaine is run in SI**, so the conversion happens once, at this call.
>
> **Solves run at ρ = 1 t/m³ and nothing else — DECIDED, and measured.** Density enters linear potential flow in exactly one place: the linearised Bernoulli pressure `p = −ρ ∂φ/∂t`. Laplace, the free-surface condition and the body condition contain no ρ at all, so added mass, damping and the excitation force are each ρ times an integral that does not depend on it.
>
> Verified rather than assumed: at ρ = 2.0 the results are **bitwise** 4× those at ρ = 0.5 — 0 ULP, on a real hull, in shallow water, for every dof including the three moments, with the excitation phase unmoved to 5e-17 rad (`packages/pylot-bem/tests/test_rho_scaling.py`).
>
> So a result is stored **per unit density** and multiplied when a database is delivered. Three consequences:
>
> - `SolveSettings` has **no** `rho`. Accepting one would let a caller store a result that is not normalised, and nothing downstream could detect it.
> - `Result` has no `rho` either — there is nothing to record, so a stored result cannot be wrong about the density it was computed at.
> - **ρ leaves the assembly key** (spec 02 §3) and stops being a hard filter in matching (spec 05 §2.1). One library now serves salt water, fresh water and anything else. Before this, a library solved for salt water had nothing at all to offer a fresh-water simulation.
>
> `to_hyddb1`, `assemble`, `deliver` and `Library.hyddb` all take a **required** `rho`. No default: every quantity is linear in it and the stored numbers carry none, so a forgotten argument hands back a database wrong by about 2.5% that looks entirely plausible.
>
> The prototype passed `1.025` straight in. That works by linearity — outputs arrive in kN and mt directly — but it is a *different* convention from `mafredo`'s, and mixing the two scales an entire database by 1000 with nothing to show for it. Running in SI also keeps the §7.2 equivalence test meaningful, which is the whole safety net for the conversions.

> These are **physical inputs, not hard-coded constants.** The previous implementation pinned `water_depth = inf` and `water_level = 0` inside accessor functions, which made those dimensions unusable for matching.

## 5. Solve both, assemble once

```python
problems = (
    [cpt.RadiationProblem(body=body, radiating_dof=dof, omega=w, rho=rho, g=g,
                          water_depth=water_depth)
     for dof in body.dofs for w in omegas]
    + [cpt.DiffractionProblem(body=body, omega=w, wave_direction=d, rho=rho, g=g,
                              water_depth=water_depth)
       for d in wave_directions for w in omegas]
)

results = cpt.BEMSolver().solve_all(problems)
dataset = cpt.assemble_dataset(results)
```

> **In the application, generate the problems grouped by frequency and dispatch one group per worker process** (spec 06 §6.2), so the run is cancellable, reports progress and scales. Each worker calls `solve_all(group, n_jobs=1, progress_bar=False)`, which keeps Capytaine's per-problem error handling. **All problems at one omega must stay together in one process**, or the size-1 influence-matrix cache thrashes and every problem rebuilds its O(N²) matrices.

**Assemble radiation and diffraction results into a single dataset.** `mafredo` requires `added_mass`, `radiation_damping` *and* the force variables from one dataset (§7). `pylot` keeps them in separate methods for demonstration; production must combine them.

## 6. Output dataset

Per `DATABASE_DEFINITION.md`:

**Coordinates** — `omega` (with derived `freq`, `period`, `wavenumber`, `wavelength`), `wave_direction`, `influenced_dof`, `radiating_dof`, plus scalars `g`, `rho`, `body_name`, `water_depth`, `forward_speed`.

**Data variables** — `added_mass`, `radiation_damping`, `excitation_force`.

Capytaine also produces `diffraction_force` and `Froude_Krylov_force`. They are used for the solve-time identity check (§3) and then **dropped**.

**Attributes** — `creation_of_dataset`, `capytaine_version`.

### Provenance

Read `capytaine_version` from the dataset attributes and store it as `solver_name` / `solver_version` on the Result (spec 02) — e.g. `Capytaine 2.3.1`. Do not hard-code it; take what actually ran.


## 9. Contract

**Input:** `CalculationMesh` + physical settings + `application_point`
**Output:** `Result` — `xarray.Dataset` plus provenance and the settings actually used

**Guarantees**

1. No subprocess, no temp settings file, no stdout parsing.
2. Settings reach the solver unchanged; the values used are recorded on the Result.
3. A solver failure raises with diagnostics; it never yields a partial Result.
4. The dataset carries both radiation and diffraction variables, or the Result is explicitly marked incomplete.

## 10. Tests

1. `excitation_force == Froude_Krylov_force + diffraction_force` within tolerance, asserted **at solve time** before the components are discarded (§3).
1a. A stored Result carries `excitation_force` and **not** the two components.
2. **Route equivalence:** a single-result fixture built through `create_from_data` equals one built through `create_from_capytaine_dataset` — added mass, damping, force amplitude and phase, and direction values. This is the safety net for every conversion in §7.2.
2a. **Layout:** a fixture with unequal counts (e.g. 12 frequencies, 36 directions) round-trips; a deliberately transposed array is rejected at our call site, not silently accepted (§7.3).
2b. **Units:** added mass in mt and damping/force in kN — assert against a hand-computed value for a simple shape, not only against the other route.
3. `application_point` changes the rotational added mass but **not** the force RAO phases (the direct check of spec 01 §5.3 — this is the test the previous design most needed and never had).
4. Settings round trip: values recorded on the Result equal those passed in.
5. Provenance: `solver_version` matches the installed Capytaine.
6. Small-mesh, few-frequency smoke run completes in CI-acceptable time.
7. **Phase-origin offset:** a database built with an off-origin application point reproduces the same physical force at a point as one built with `rotation_center` at the phase origin, **once the stored `phase_origin` is applied by the consumer** (§7.5 — mafredo stores it, it does not apply it).
8. **Wave-direction convention (§7.4) — regression guard:** the same body solved at `x = 0` and `x = +d` shows the excitation phase at direction 0 **lagging** for the further body, confirming waves travel toward +x. Asserts that a future capytaine change, or a stray offset in our conversion, cannot silently flip headings.

> Test 3 is the highest-value test in this specification. `pylot`'s `main()` already sets up the comparison (`rotation_center=(0,0,0)` vs `(5,0,0)`); turn it into an assertion.
