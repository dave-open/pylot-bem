# 10 — CLI surface

**Three commands.** Create a floating condition, add a mesh, run a calculation.

That is the whole surface, and the scope is a decision rather than a first cut:

- **End users work in the UI.** The CLI is not their route.
- **Anything more than these three, use the Python package directly.** Spec 11 is the full API; a CLI flag for every capability would be a second, worse API that has to be kept in step with the first.

> **The CLI holds no logic** — it parses arguments, converts degrees and periods at the boundary, and prints. Every command is one call on `Pylot`. That is enforced by keeping it thin rather than by a test: when it started growing its own physics (the resolution limit, the panel-count doubling, the diffraction-space conversion), that was the signal those belonged in the API. Anything the CLI has to work out for itself, every other caller would have to work out too — so it doubles as the completeness check on spec 11.
- **Batching is running it again.** A shell loop over drafts is clearer than a grid syntax, and it needs nothing built.

What that removes, deliberately: no library creation, no probe editing, no listing, no database or conflict commands, no deletion, no matching, no validation. Library setup is interactive work — import a mesh, check its bounds and normals, write down where the origin sits — and belongs in the UI. The CLI exists for the two expensive, scriptable steps: **meshing and solving**.

---

## 1. Naming things

A terminal has to say *which* condition. Ids are `uuid4` hex, unusable by hand, and selecting by `label` is what ADR-4 forbids — renaming would break a script.

**The id is the handle, and the user chooses it.** The storage API already accepts explicit ids, so no new machinery:

```bash
pylot condition lib.pylot --id design --z-origin -4.0
pylot mesh      lib.pylot --condition design --id design-fine --pct 2
pylot solve     lib.pylot --mesh design-fine --periods 4:20:1
```

Ids stay opaque to the system — nothing parses them — while meaning something to a person. A generated `uuid4` remains the default when `--id` is omitted.

**This is also why there is no machine-readable output.** The caller already knows every id, because it supplied them, so nothing has to be scraped from stdout. Each command prints what it did, for a human.

## 2. The commands

### `pylot condition <lib>`

```
--z-origin Z        [m] height of the vessel origin above the waterplane; negative when submerged
--heel DEG          default 0
--trim DEG          default 0
--id ID             default: generated
--label TEXT        display only
```

**Degrees in, slopes stored** (spec 01 §7). The help text says degrees on both flags.

> **No `--draft` flag, not even as an alias — DECIDED.** `z_origin` is not the naval draft (spec 01 §3.5). They differ by wherever the origin sits, and a user who means one and gets the other is wrong by that much with nothing to tell them. An unrecognised flag is a far better outcome than a silently different number.

Prints the id and the derived application point.

### `pylot mesh <lib>`

```
--condition ID
--pct P             default 2
--iterations N      default 20
--id ID             default: generated
```

Symmetry is derived from the condition and the base shape, never a flag (spec 01 §4).

Prints the id, the panel count — noting when it is a half vessel — and the highest reliably solvable period, so the cost and the limit are visible before anything is solved with it.

### `pylot solve <lib>`

```
--mesh ID
--periods 4:20:0.5 | 4,6,8,10        [s] START:STOP:STEP or a list
--directions 0:360:30                [deg] direction of travel; omit for radiation only
--depth inf | VALUE                  [m] default inf
--speed V                            [m/s] default 0
--g G                                [m/s2] default 9.81
--lid none|surface|below|auto        default none
--lid-z Z                            [m] with --lid below
--id ID                              default: generated
```

**Periods in seconds** (spec 09 §E), converted to omega at the boundary. Note that ascending period is *descending* omega, and solving is frequency-major, so the grid is solved in the reverse of the order it is typed — the progress output says so rather than looking like it started at the end.

Before starting, prints the problem count, the estimated peak memory and any frequency beyond the mesh's resolution limit. The cost belongs next to the action, not in a log afterwards.

While running, prints `frequency n/N`, rewritten in place. **Per frequency, not per problem** — spec 06 §6.5.1, and the reason is measured there: the influence matrices are cached across a frequency's problems, so a per-problem count reads as a hang followed by a jump.

> **Ctrl-C writes nothing — DECIDED.** The GUI offers *keep what was solved* (spec 06 §6.4) because there is someone to ask. In a terminal there is not, and a flag to decide it in advance is exactly the sort of option this CLI is not having. A run that is interrupted leaves the library untouched; solve a shorter grid instead.
>
> **Not built yet.** The solve runs in-process, so Ctrl-C lands inside a Fortran call and takes effect only when it returns. The API's own cancellation — raising from the `progress` callback — is cooperative and lands at a **frequency** boundary, which is finer than nothing but coarser than the pool. That is acceptable while `--workers` does not exist, and it is the first thing the pool fixes.
>
> This is one reason to keep the **pooled worker path** rather than solving in-process: Ctrl-C then lands on the graceful-stop tier that already exists, instead of inside a Fortran call that cannot be interrupted (spec 06 §6.3).

## 3. Cross-cutting

| | |
|---|---|
| **Library path first**, always, on every command |
| **Exit codes** | `0` done, `1` refused with a stated reason, `2` bad usage |
| **Units in help** | Every flag names its unit. `--depth` says metres, the angles say degrees |
| **Physical inputs are echoed** | Depth and speed appear in the confirmation line. The previous implementation hard-coded them and made both unmatchable |
| **No `--rho`** | Results are stored per unit density and scaled when a database is delivered (spec 04 §4), so there is no density to choose at solve time. Delivery is not a CLI command |
| **Nothing is overwritten** | Ids collide → refused, not replaced |

## 4. Open questions

| Ref | Question | Recommendation |
|---|---|---|
| §1 | Constrain id characters | Printable, no whitespace, so a shell cannot mangle one |
| §2 | `--workers` | **Not offered yet.** The pooled worker path is Phase 7; a flag that does nothing is worse than no flag. Note that `BEMSolver.solve_all` already takes `n_jobs` and groups by frequency through `joblib` — measure that against a hand-built pool first (spec 06 §6.2) |
