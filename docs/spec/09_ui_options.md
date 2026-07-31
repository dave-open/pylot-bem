# 09 — UI option inventory

Every user-settable option and every displayed field of the standalone application (spec 06 Part A), for mockup purposes. Not a layout proposal — an inventory.

Conventions used throughout:

- **(D)** = derived and **read-only**. Never a widget the user can set. Showing derived values is the point; letting them be edited is how the previous design lost its invariants.
- **(A)** = advanced; hide behind an *Advanced* disclosure, not on the main path.
- Units are the **display** units. Storage units are spec 01/02's and differ deliberately — heel and trim are stored as slopes and shown in degrees (spec 01 §7).
- **DECIDED** marks a ruling made during review. `[DECIDE]` marks what is still open.

**All lengths are metres.** The only conversion in the application is at STL import (§A).

---

## A. Library

| Option | Type | Default | Notes |
|---|---|---|---|
| Library file / folder | path | — | New / Open / Save As |
| Vessel name | text | — | |
| Description | multi-line text | — | |
| Origin description | text | — | Where `(0,0,0)` sits on the vessel. Free text, but **prompt for it** — it is the only human record of the frame, and getting it wrong invalidates every condition |
| Base shape file | path | — | Import |
| Import scale | choice or factor | 1.0 (m → m) | **DECIDED.** The library is always metres; conversion happens **only here**. Offer mm/cm/m/ft, and **show the resulting bounds live** so the user can sanity-check the choice before accepting |
| Base shape | **(D)** | | Panel count, bounds (Lx/Ly/Lz), XZ-symmetric? |

> **Base shape is immutable once any mesh or result exists** (spec 02 §1). The UI must *disable* re-import at that point with a reason shown, not warn-and-proceed.

### A.1 Import checks — DECIDED

- **Show the bounds during import**, before accepting. This is what makes the scale choice checkable rather than a guess.
- **Render with backface colouring.** An inverted normal is a real failure that is otherwise completely invisible; a differently-coloured backface makes it obvious at a glance. Applies to the base shape and to every calculation mesh (§L).
- **A full mesh is required.** Supplying a half mesh and relying on symmetry is **not acceptable** — the pipeline derives symmetry from the floating condition and cuts the half itself (spec 03 §1). A mesh lying entirely on one side of `y = 0` is almost certainly a half mesh; flag it at import.
- **Closedness is not checked.** It was in an earlier draft and is not useful: after the waterline cut nothing is closed anyway.

## B. Surface probes

Spec 05 §2.2. The single most under-appreciated screen — probes are what matching runs on.

| Option | Type | Default | Notes |
|---|---|---|---|
| Probe table | editable list of `(x, y)` | bounding-box corners of the base shape | Add / remove / reset to default |
| Probe z per condition | **(D)** | | Recomputed for every condition; shown in the condition view |
| Reset to defaults | action | | |

> Editing probes **recomputes every condition's probe z**. Say so before applying, and report how many conditions changed (spec 06 §3).

**DECIDED:** a probe outside the waterplane extent of a condition is **fine**. Do not check for it, do not flag it. A probe is a point on the *waterplane*, not on the hull.

## C. Floating conditions

| Option | Type | Unit | Default | Notes |
|---|---|---|---|---|
| Label | text | | auto | Human-only (ADR-4). Never parsed. **The only editable field on a condition** — see below |
| Id | text | | generated | **DECIDED: offer it.** Optional; blank generates a uuid4. Ids are opaque and nothing parses one, which is exactly what makes a typed one safe — but unlike a label it is **permanent**, because meshes and results point at it. A collision is refused *in the dialog*, with its reason, rather than as an exception after the work has run |
| `z_origin` | float | m | — | The distance the vessel origin sits above the waterplane. Called *draft* colloquially — decide the field label, but the API name is `z_origin` (spec 01 §3.5) |
| Heel | float | **deg** | 0 | Stored as a slope |
| Trim | float | **deg** | 0 | Stored as a slope |
| Application point | **(D)** | m | | `(x, y, z)`, vessel-local, from submerged bounds (spec 01 §5.4.2) |
| Symmetry | **(D)** | | | Yes/no **with the reason** — e.g. *"no: heel ≠ 0"*. Never a checkbox (spec 01 §4) |
| Probe z values | **(D)** | m | | One per probe |
| Submerged volume / wetted area / waterline length | **(D)** | | | Display and sanity check only — nothing computes from them (spec 02 §1) |
| Out-of-domain warning | **(D)** | | | Heel/trim slopes have a valid domain (spec 01 §3.4); show the refusal, do not silently clamp |

**DECIDED:** no bulk / grid creation of conditions in the UI. One at a time. (Duplicate detection within the 1e-3 tolerance still applies on create — spec 02 §4.)

**DECIDED: a condition is never editable, meshes or no meshes.** `z_origin`, heel and trim are what every mesh and result below were computed *against*, so changing one would not update that work — it would invalidate it, silently, with the results still sitting there looking valid. To float the vessel differently, make another condition; the creation dialog derives the application point and the wetted measurements as they are typed, so it is cheap.

This settles the question the mockup raised about a condition that has no meshes yet. Editability that depends on what happens to hang off a row is a rule users have to learn, and it is wrong the moment the first mesh is built.

**The label is the one exception**, and by design rather than oversight: it is display only and **no behaviour may parse it** (ADR-4), so nothing can be invalidated by it changing. `Library.set_condition_label` is the only mutator a condition has. Refusing to fix a typo would be strictness with no invariant behind it.

## D. Calculation mesh

| Option | Type | Unit | Default | Notes |
|---|---|---|---|---|
| Target reduction `pct` | float | % | **2** | The primary quality/cost knob. Label it in the user's terms, not pymeshlab's |
| Iterations | int | | **20** | |
| Use symmetry | **(D)** | | | Derived from the condition (spec 01 §4). Shown, not chosen |
| Panel count | **(D)** | | | **Half the vessel when symmetric** — label it so, or it reads as a factor-2 bug (spec 02 §1) |
| Largest panel radius | **(D)** | m | | |
| Highest reliably solvable frequency | **(D)** | s (period) | | From `minimal_computable_wavelength`. Capytaine's own mesh-resolution warning, surfaced **before** the solve instead of as a log warning during it |
| Estimated memory | **(D)** | MB | | `≈ 2 × 16 × N²` bytes, per worker (spec 06 §6.5) |
| Id | text | | generated | Optional, as §C. The mesh id is what the Results table, the Databases tab and every validation finding show, so naming it is the cheapest readability there is |
| Create / delete | action | | | Separate from Solve (spec 06 §4) |

## E. Solve settings

| Option | Type | Unit | Default | Notes |
|---|---|---|---|---|
| Frequency grid | from / to / count or step, **or** explicit list | **s (period)** | — | **DECIDED: the user enters periods in seconds.** Storage and the solver stay in omega; convert at the widget. Show the resulting list and count, and flag anything beyond the mesh's solvable limit (§D) |
| Wave directions | from / to / step | **deg** | **0…180 for a symmetric mesh, 0…360 otherwise** | **DECIDED.** The default follows the mesh: a symmetric body's port half is the mirror of its starboard half, so solving it computes numbers already known and doubles the run. The readout says which case applies and that the rest is mirrored on delivery (spec 04 §8). Solving past 180 anyway is allowed and flagged as redundant — it is wasteful, not wrong, and refusing it would be the tool overruling the user |
| — the wrap-around | | | | **0 and 360 are the same heading**, so a grid that comes back to where it started drops its last point. Not a preference: the duplicate costs a full set of problems and leaves the stored result with two identical direction columns. Checked modulo 360, so −180…180 loses its duplicate too |
| Water depth | infinite / value | m | infinite | Must be a real input — the previous implementation hard-coded it and made the dimension unmatchable (spec 04 §4) |
| ~~Water density `rho`~~ | — | — | — | **Not a solve setting** (spec 04 §4). Results are stored per unit density and scaled on delivery, so density is chosen where a database is *used* — the match view (§J) and the inspect view (§I) — never here. One library serves every density |
| `g` | float (A) | m/s² | 9.81 | |
| Forward speed | float | m/s | 0 | |
| Total problems | **(D)** | | | `n_frequencies × (6 + n_directions)`. The honest cost number, shown before Start |
| Result id | text | | generated | Optional, as §C. A duplicate disables **Start** rather than failing after the solve — which on a real hull is minutes spent on a refusal |

> **Periods in, omega stored.** Sorting, grouping and progress are all frequency-major (spec 06 §6.2) — note that ascending period is *descending* omega, so the order the user sees the grid solved in is the reverse of the order they typed it. Either sort the display or say which way it runs; a progress list that appears to start at the end reads as a bug.

### E.1 Parallelism (A)

| Option | Type | Default | Notes |
|---|---|---|---|
| Worker processes | int | **7** | One process per frequency (spec 06 §6.2). Clamp to the frequency count — more is pure waste |
| OpenMP threads per worker | int | **1** | Must be set explicitly, or workers oversubscribe the machine (spec 06 §6.5) |
| Estimated peak memory | **(D)** | | `workers × per-worker`. Show it **next to the worker spinbox**, live |

> 7 × 1 puts all parallelism in the process layer and leaves a core for the UI. It presumes an 8-core machine — **clamp to the actual core count** rather than shipping 7 as an absolute, and keep both fields adjustable, since memory (§D) can bind before cores do.

### E.2 Irregular-frequency removal (lid) — DECIDED to expose

**The lid is a solver setting, not a mesh property** — an artificial numerical construct introduced only for the solve (spec 04 §2). It belongs on this screen, beside water depth, and it is regenerated on each solve rather than stored.

Capytaine offers exactly two knobs (`meshes/meshes.py:773`), so expose exactly two:

| Option | Type | Default | Notes |
|---|---|---|---|
| Lid | choice: **None** / At free surface / Below free surface / Auto | None | |
| Lid depth | float, m | −0.1 | *Below free surface* only. Panels **on** the free surface are still experimental in Capytaine, so slightly below is more robust but removes fewer irregular frequencies |
| Lid resolution (A) | float, m | mean hull face radius | `faces_max_radius` |
| Lid panel count | **(D)** | | |
| Panels actually solved | **(D)** | | See below — the number that matters |

Two things the mockup must reflect:

- **A lid disables symmetry in the solve** (spec 04 §2.1). On a symmetric condition, turning the lid on silently trades away the symmetry speedup. **Show the panel count that will actually be solved, with and without** — that is the difference between an informed choice and a checkbox users tick because it sounds safe.
- **Auto is now coherent.** `lowest_lid_position(omega_max)` reads `omega_max` straight off the frequency grid on this same screen. When the lid lived on the mesh this coupled two entities and could go stale; as a solve setting it is self-contained, so **auto is a real mode, not a workaround**. Show the resulting depth.

> **Trap: auto has no answer outside its domain — and does not say so.** `arctanh(π·g·p/ω_max²)` needs `π·g·p < ω_max²` — for a 100 × 30 m hull, `ω_max > 1.04 rad/s` (periods under 6.1 s). Since long periods are low frequencies, it is the **long end** of a grid that leaves the domain, and physically it means *there are no irregular frequencies in this range and no lid is needed*. Display that sentence.
>
> **Corrected against Capytaine 2.3.1, which does not return the NaN this section originally assumed.** `lowest_lid_position` is `z_lid = 0.0` followed by `z_lid = min(z_lid, z_lid_comp)`, and `min(0.0, nan)` is **`0.0`** in Python — the comparison is false, so the first argument wins. Out of domain it therefore hands back zero, which is a valid-looking instruction to put a lid **on the free surface**: a real setting, with real cost, that the user did not ask for and that Capytaine still considers experimental. That is worse than a NaN, because nothing downstream can detect it.
>
> So the test is on the **sign**, not on `isfinite`: a genuine answer is `-arctanh(x)/(π·p)` with `0 < x < 1` and is strictly negative, so zero can only mean the minimum never moved. `pylot_bem.solver.auto_lid_z` returns `None` there, and `test_solver.py` pins Capytaine's behaviour so that a future version returning NaN fails loudly rather than changing the meaning of a stored lid.

### E.3 Frequency bands

A frequency-dependent lid is expressed as **two results on the same mesh** (spec 04 §2.2): the low band without a lid (symmetric, cheap), the high band with one. `[DECIDE]` whether the UI offers a helper that computes the split point from the hull's first irregular frequency and sets up both solves, or leaves the user to run two solves.

## F. Solve run

| Element | Notes |
|---|---|
| **Start** | Disabled with a stated reason when the mesh is missing or settings are invalid |
| **Stop** | Graceful: queued frequencies dropped, running ones finish. **Show the expected wait — about one frequency**, since groups run concurrently. Solves run seconds to minutes, so this number matters (spec 06 §6.5.1) |
| **Kill** | Immediate. Running frequencies are lost |
| Progress | Frequencies done / total, elapsed, ETA. **Per frequency, not per problem** — the first problem at each frequency carries nearly all the cost, so a per-problem bar stalls then jumps (spec 06 §6.5.1) |
| Which frequencies are done | Not just a count — the actual grid, marked. Under parallel workers the completed set has **holes** (spec 06 §6.4) |
| On cancel | **DECIDED, and it differs by tier.** **Stop always keeps, and does not ask.** **Kill asks**, with Discard as the default button. See below |
| Failures | A frequency that failed must be visible, not silently missing from the grid |
| Log | Solver diagnostics and warnings, in the UI (spec 06 §6.6) |

> **Keeping is the default because the decision cannot be made on this screen.** Whether a shorter grid is worth having is answered by *looking at the curves* — which requires the result to exist. Asking before the user can see anything makes them guess, and a solve is minutes: guessing wrong costs the run, while an unwanted result costs one click to delete. So a graceful **Stop keeps silently**.
>
> **Kill is the exception, and not because the numbers are different.** What already came back is equally complete either way — the unit of work is a frequency, and a frequency that returned returned whole. The difference is intent: someone reaching for the emergency handle usually wants out, not a shorter grid. So that tier asks, names the missing frequencies (*"keep 4 of 7"* is not answerable without knowing which four), and defaults to Discard.
>
> Either way a kept short result records what happened in its **label** — human text nothing parses (ADR-4), reading *"stopped after 4 of 7 frequencies"* or *"terminated after…"*. The grid it carries *is* the grid solved, so nothing downstream is misled by the absence of a structured flag; what the label adds is that more had been asked for.

## G. Results

Table columns — this list *is* the requirement that "users must be able to see what was actually solved" (spec 06 §4):

| Column | Notes |
|---|---|
| Mesh | Which mesh, and its `pct` — results are **not** filtered by mesh selection (spec 06 §4) |
| Condition | |
| Period range and count | Displayed as periods, per §E |
| Direction range and count | |
| Water depth / forward speed | |
| Label | The result's name, editable at any time. **The only mutable field a result has** — everything else is a record of what was computed, and a record that can be edited is not one |
| Truncated? | **DECIDED: a field on the result**, not a sentence in its label. Forced by wanting to rename results: the label cannot be both the human name and the record that a run was cut short. Nothing is misled without it — `omegas` *is* the grid solved — but what was *asked for* is stored nowhere else, so it cannot be derived |
| Solver version | From the dataset, not hard-coded (spec 04 §6) |
| Date | |
| Delete | Refuse or cascade explicitly if referenced (spec 08 Phase 4) |

## H. Assembled databases

| Element | Notes |
|---|---|
| List by key | Condition × depth × forward speed (spec 02 §3). **Not density** — every database serves every density (spec 04 §4) |
| Contributing results | Which results feed each database |
| **Complete / incomplete** | Incomplete is a first-class state, shown, not an error at use time |
| **Conflicts** | Where two results cover the same frequency, the key produces **no database** until resolved (spec 02 §3.1). List the conflicting frequencies and both contributors, with what differs — `pct`, lid, solve date |
| Resolve | Jump straight from a conflict to the comparison plot (§I) and then to deletion (§I.1). Conflict → compare → delete is the main loop of building a database, not an error path |
| Frequency provenance | For a clean key, which result each frequency came from |

**DECIDED:** no export. The library file is the deliverable; `pylot_db` reads it directly (spec 07 §4). This removes the last argument for a directory layout in spec 02 §5.2.

## I. Inspect, plot and edit

**Plotting works on results, not only on assembled databases.** That is what makes a conflict resolvable: the user has to see two competing runs on the same axes before deciding which to delete (spec 02 §3.2).

| Option | Notes |
|---|---|
| Source | A database **or** one or more **results** — overlaying two results is the comparison view |
| Quantity | Added mass / radiation damping / **excitation force** — the only three stored (spec 04 §3) |
| DOF pair | For 6×6 quantities |
| Wave direction | For force RAOs |
| Amplitude / phase | Phase is where application-point errors show up — make it easy to reach |
| Water density | Scales every plotted amplitude [t/m³]. Not a filter; two results at different densities do not exist (spec 04 §4) |
| **X axis** | **Frequency [rad/s] or period [s]** — a toggle on the plot. Entry is always periods (§E); inspection is often easier in omega |
| Difference | When two results are overlaid, offer their difference. A 2% spread and a 40% spread are different decisions |
| Plot | Any quantity against the x axis. Via `mafredo`'s existing plotting where it fits (spec 06 §3) |

### I.1 Removing superseded data — DECIDED

Results are not append-only. The user must be able to remove data by any combination of:

- **floating condition**
- **calculation mesh**
- **frequency**

**Frequency-level deletion is the significant one.** It means a stored result's frequency grid is *editable*, not fixed at solve time — which is consistent, because a result over a shorter grid is still a complete result (spec 06 §6.4), but it needs to be stated in spec 02 as a supported maintenance operation.

Requirements:

- Delete whole frequencies only — never part of one, or the DOF/direction coverage goes ragged.
- **Preview before applying:** how many results and frequencies are affected, **which conflicts this resolves**, and which keys become incomplete as a result (§H). Trading a conflict for a silent gap is not a fix.
- Record it. A database that lost a frequency should say so, not just be quietly shorter.
- **Never offer "resolve all conflicts automatically".** That is the withdrawn precedence rule of spec 02 §3.1 under another name.

### I.2 Merge — DECIDED

Select several results, right-click, **Merge**. It does one of two things, and **the results decide which**:

- **Combine** — they agree on the mesh and on every setting (depth, speed, `g`, lid, wave directions, which quantities they carry), so a single result covering the union of their grids records exactly what they did. The originals are replaced. This is the one that removes clutter.
- **Trim** — they differ somewhere, so one result could not record both. They stay as they are and only the contested frequencies are given up.

Whether folding two results into one throws information away is a **fact about them, not a preference**, so it is not offered as a choice. `Library.combination_differences` is the single rule: the dialog calls it to explain, and `combine_results` calls it to refuse, so a screen cannot offer what storage would reject.

**Trimming is what protects provenance.** A `Result` carries one `mesh_id`, one lid and one date, so a result built from several that disagree would have to claim one of them for frequencies solved under the others — and the usual reason two results exist is that they were solved on *different meshes*. Where they agree on all of it, there is nothing left to protect and combining is free.

Combining writes the new result **before** deleting the originals. Interrupted in between, the library keeps a redundant result — a conflict, visible and fixable — rather than a hole.

**It does not pick the primary** in either mode, which keeps it clear of the rule §I.1 forbids. Even when combining, a frequency both results cover is supplied by the primary: they agree on every setting so the numbers should match, but they are separate solver runs and Capytaine is not bit-reproducible in finite depth (spec 04), so it stays a choice. The user chooses, and the screen exists to inform that choice: what each result keeps, what it loses, and — *simulated through the same `coverage_of` that will judge it afterwards, not predicted by a second rule* — what the database becomes. Where trimming would trade a conflict for a **gap**, it says so and names the frequencies.

Refused, with a reason, when the selection spans more than one assembly key: different conditions, depths or speeds are different physical situations, so neither result supersedes the other and there is nothing to resolve.

## J. Match view

Exercises spec 05 with no vessel and no DAVE. Worth building early.

**DECIDED: the match view does not pick a winner.** It lists **all** available conditions sorted ascending by RMS probe error, and the user selects one to inspect. No threshold, no pass/fail, no "best match" label.

| Option | Type | Unit | Notes |
|---|---|---|---|
| Trial `z_origin` / heel / trim | float | m, **deg** | The normal entry path |
| Paste 4×4 transform | text (A) | | The actual interface (spec 05 §3). Useful for reproducing a real case |
| Water depth / forward speed | | | **Hard filters** — non-matching conditions are excluded, not scored (spec 05 §3) |
| Water density | float | **t/m³** | **Not a filter.** It scales the delivered database and excludes nothing (spec 04 §4). Put `t/m³` in the label and keep it visually apart from the filters above, or it reads as a fourth one |
| Sorted list | **(D)** | | Condition, **RMS probe error**, max probe error. Ascending by RMS |
| Per-probe error | **(D)** | m | Signed, for the selected condition. The sign tells you which way the mismatch runs |

> This removes the acceptance threshold from spec 05 §2.3 entirely — see the consequence noted there for the deferred DAVE runtime, which is the only caller that ever needed one.

## K. Validation

| Element | Notes |
|---|---|
| Run | Spec 02 §6 |
| Findings | Structured and grouped by severity, each linking to the entity it concerns. A corrupted library is **displayed**, not crashed on (spec 06 §7) |

## L. 3D view

| Toggle | Default | Notes |
|---|---|---|
| Base shape | on | **Opaque, with backface colouring** — shows normal direction (§A.1). See below. Shown **on its own, vessel-local, when the library root is selected** — the one level with no condition, hence no waterplane, and the natural place to check the hull's normals before anything is built on it |
| Calculation mesh | on | For the selected condition, drawn **in wireframe over the hull** |
| Lid mesh | on | When present (§E.2) |
| Waterplane | on | |
| Surface probes | on | Coloured by z error against the trial condition — the cheapest and most informative check in the application (spec 06 §5) |
| Application point | on | Marker |

> Backface colouring replaces a separate "show normals" toggle. It is always on and costs nothing, where a toggle would be off exactly when it was needed.

> **The hull is opaque, and that is what makes backface colouring work.** An earlier draft drew it see-through so the calculation mesh inside would show. Through a translucent hull you are always looking at the inside of its far side, so **every** face renders in the backface colour and an inverted normal — the one thing the colour exists to reveal — is invisible again. Depth peeling corrects the ordering and does not touch the problem, because the problem is not ordering.
>
> So: opaque hull, calculation mesh drawn over it as a wireframe with a coincident-topology offset (the mesh is a regrid of the wetted surface and sits exactly on it, so without the offset the two z-fight). To look inside, switch the base shape off in the View menu — which is what the toggle is for.

## M. Application preferences

| Option | Notes |
|---|---|
| Default worker processes / OpenMP threads | The per-solve settings in §E.1 default from here |
| Default library folder | |
| Default `pct` / iterations | 2 / 20 |
| Angle display | **DECIDED:** heel and trim are shown in **degrees**. Slopes are never shown in the UI at all — not as a secondary readout |

---

## Cross-cutting rules for the mockup

1. **Derived fields are never editable.** Application point, symmetry, probe z, panel counts. If a mockup shows one of these in an editable-looking box, the implementation will eventually make it editable.
2. **Every refusal states its reason.** Disabled *Start*, disabled base-shape re-import, out-of-domain heel. A greyed-out button with no explanation generates support questions forever.
3. **Units in labels, always** — `t/m³`, `s`, `deg`, `m`. Unit errors are the most likely catastrophic failure in this application, and the only unit conversion in it is at STL import.
4. **Cost is shown before it is incurred.** Problem count, estimated memory, and the mesh's solvable frequency limit all belong *next to Start*, not in a log afterwards.
5. **No "case", "candidate" or "POA"** anywhere in the UI (spec 00 §1).

## Still open after this review

| Ref | Question |
|---|---|
| §E.3 | Whether to offer a **band split helper** — no lid low, lid high, assembled into one database (spec 04 §2.2) |
| 04 §2.2 | Whether frequency bands must be **non-overlapping** (recommended) or the lidded result wins an overlap |
| 10 §4 | Which **characters** an id may contain. Now live rather than theoretical: users type them. Currently only stripped of surrounding space and checked for uniqueness |

Answered while building: **§F** (Stop keeps silently, Kill asks), **§C** (a condition is never editable; its label always is), **§E.2**'s NaN trap (Capytaine returns 0.0, not NaN), **§L** (the hull is opaque, or backface colouring says nothing).
