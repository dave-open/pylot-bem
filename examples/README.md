# Examples

Four runnable scripts. Start with `01`, which writes the library `02` reads.

```bash
uv run python examples/01_build_a_library.py
```

| | | Runs in | Writes |
|---|---|---|---|
| [`01_build_a_library.py`](01_build_a_library.py) | The whole write path: hull file → probes → conditions → meshes → solves | ~2 s | `output/tanker.pylot` |
| [`02_match_and_deliver.py`](02_match_and_deliver.py) | The runtime side. Match a vessel's pose, get a `Hyddb1`. **Imports `pylot_db` only** | <1 s | — |
| [`03_conflicts_and_cleanup.py`](03_conflicts_and_cleanup.py) | Two results that disagree, and how you resolve it | ~2 s | `output/conflict.pylot` |
| [`04_progress_and_cancellation.py`](04_progress_and_cancellation.py) | A progress bar, and stopping a solve from another thread | ~3 s | `output/progress.pylot` |
| [`05_look_at_it.py`](05_look_at_it.py) | Meshes out, the `Hyddb1` out, and a 3D view | ~1 s | `output/design.png` |

They all use `packages/pylot-bem/tests/assets/tanker.stl` — a real 333 × 58 × 28 m hull. Point `HULL` at your own file to use something else; `SCALE` is there for a model drawn in millimetres.

Everything is **deliberately coarse** so you can change a number and run it again. Real settings are `pct=2.0, iterations=20` (the defaults) and a frequency grid that covers the periods you care about. Cost is quadratic in the panel count, so `pct` is the knob that matters.

`output/` is gitignored. The scripts delete and rewrite their own library each run — a library is never overwritten in place.

## Things worth trying

| Change | What you should see |
|---|---|
| Drop a period in `01` to 8 s | Capytaine warns that the mesh cannot resolve it. `shortest_reliable_period` said so first, before anything was spent |
| `IS_XZ_SYMMETRIC = False` in `01` | Meshes double in size, memory quadruples, results are the same. The declaration is worth real money |
| Add `heel=0.05` to a condition in `01` | That mesh becomes a full vessel and its application point moves off the centreline — symmetry is derived from the condition, not just the hull |
| `pct=1.0` in `04` | A solve slow enough to watch properly |
| Change `RHO` in `02` | The same database, scaled. Density is a delivery choice, not a filter — nothing is re-solved |
| Change `water_depth` in `02`'s section 5 | No candidates, and a reason. Depth *is* a hard filter |
| Change the yaw or position in `02`'s last section | Nothing at all. Matching depends on `z_origin`, `heel` and `trim` and nothing else — exactly, not approximately |
| `HEEL = 1.5, TRIM = 1.5` in `02` | Refused: outside the unit disc. Three slopes can be checked; a 4×4 had no wrong value |
| Delete `run-fine` instead of trimming `run-coarse` in `03` | The other resolution. Nothing picks between them for you |
| `show_condition(..., mesh=False)` in `05` | Just the hull and the water. The orange wireframe is the half vessel that was actually solved |
| Add `heel` to the condition in `05` | The mesh becomes a full vessel and the waterline cuts the hull at an angle |

## Where things are documented

- [`docs/api.md`](../docs/api.md) — the reference: every public name, with its units
- [`docs/spec/11_api.md`](../docs/spec/11_api.md) — why the API is shaped this way
- [`docs/spec/01_reference_frames_and_conditions.md`](../docs/spec/01_reference_frames_and_conditions.md) — read this before trusting any number you get out

## The three traps

Each one produces plausible output when you get it wrong, which is why they are worth stating before you start.

**`z_origin` is not the draft.** It is the height of the vessel origin above the waterplane, negative for a normally floating vessel. They coincide only when the origin is on the keel. There is no `draft` argument anywhere, on purpose.

**`heel` and `trim` are slopes.** `tan(radians(degrees))`. Degrees appear only in the CLI and the UI. `heel=5` is not five degrees, it is a slope of 5 — and outside the valid domain, so it raises. `heel=0.05` is about 2.9°.

**Wave direction is where the wave is going**, not where it comes from. Conversion from Capytaine is `×180/π` with no offset.
