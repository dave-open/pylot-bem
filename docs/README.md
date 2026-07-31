# pylot-bem documentation

The write side: mesh a hull at a floating condition, solve it with Capytaine,
assemble the results. Carries the command line and the standalone application.

| | |
|---|---|
| [`manual.md`](manual.md) | The application, screen by screen. Assumes you know Capytaine |
| [`api.md`](api.md) | The reference. What to call, what comes back, and in which units |
| [`../examples/`](../examples/) | Runnable scripts, smallest first |

## The specification

The design documents — the mesh pipeline, the solver, the command line, the
application, and the reference frames and storage model this package inherits
from `pylot-db` — live in the **`pylot`** repository under `docs/spec/`, and
cover both packages. They are cited throughout the source by filename, so a
docstring reading *the pylot specification, `03_mesh_pipeline.md` section 4*
names a file you will find there.

They are deliberately not copied here. A specification written for two packages
does not survive being cut in half — a good part of it argues about the boundary
*between* the packages — and a copy that drifts is worse than a reference that
points somewhere.

**If you read one document first, make it
`01_reference_frames_and_conditions.md`.** The frame conventions are what the
previous attempt got wrong, and everything else assumes them.
