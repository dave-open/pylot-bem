# 03 — Mesh pipeline

Turns a **base shape** + **floating condition** + **density setting** into a solver-ready **calculation mesh**.

Reference implementation: `pylot/capytaine_and_pymeshup.py :: ExampleRunner._make_calculation_mesh`.

## 1. The pipeline

> **API note.** `Volume.bounds` returns a flat `(xmin, xmax, ymin, ymax, zmin, zmax)`, and `regrid` takes `iterations` first. `cut_at_xz()` keeps **negative y**. Verified against pymeshup 26.7.0.

```python
T = condition.transform                      # spec 01
b = base_shape.transform(T)                  # vessel-local -> diffraction space
b = b.cut_at_waterline()                     # keep the wetted part, z <= 0

submerged_bounds = b.bounds                  # <-- application point derives from this

if use_symmetry:
    b = b.cut_at_xz()                        # keep one half
b = b.regrid(pct=pct, iterations=iterations)

faces = b.ms.current_mesh().face_matrix()
f4 = [(v1, v2, v3, v3) for v1, v2, v3 in faces]     # triangles as degenerate quads
mesh = cpt.Mesh(vertices=b.vertices, faces=f4)

if use_symmetry:
    mesh = ReflectionSymmetricMesh(mesh, plane=xOz_Plane)
```

> **No lid here.** A lid is a numerical device belonging to the solve, not geometry belonging to the vessel — see spec 04 §2. It is generated from this mesh at solve time and never stored.

**The base shape must be a full mesh.** Supplying a half mesh and relying on symmetry is **not supported**: `use_symmetry` is derived from the condition, the pipeline cuts the half itself, and a pre-halved input would be cut again — silently producing a quarter vessel at any condition with `heel == 0`, and a wrong displacement at every other one. Flag a mesh lying entirely on one side of `y = 0` at import (spec 09 §A.1).

**Follow this order.** Two orderings are load-bearing:

1. The transform is applied **first**, so the waterline cut happens at the diffraction-space waterplane `z = 0` — which is what makes the cut meaningful.
2. `cut_at_waterline()` comes **before** `cut_at_xz()`, so `bounds` between them describes the **whole submerged volume**. That is the definition of the application point (spec 01 §5.4.2), and it is wrong on either side: before the waterline cut the bounds include dry structure, and after the XZ cut the y-bounds cover half a vessel.

> **Correction, measured.** An earlier draft said the two cuts "commute, so the resulting geometry is identical". **They do not.** The **bounds** agree exactly — which is all the application point depends on, and the only reason the reorder was made — but the triangulations differ: on the boxboat, 13 vertices one way and 12 the other, and still different after regridding.
>
> So the reorder is safe **for its purpose**, not neutral in general: the solid is the same, the mesh handed to the solver is not the one `pylot`'s ordering would produce. A test asserts both halves of that.

## 2. What is deliberately absent

- **No POA-based translation.** The mesh position is fully determined by `T` (spec 01 §5.1). The previous `mesh_translation = −POA` step is deleted; it moved the phase origin.
- **No re-localisation.** The mesh is stored exactly as solved, in diffraction space.
- **No retry / adaptive remesh.** The previous implementation re-ran the regrid with a halved percentage when the face count did not increase, comparing against the *input* face count. That made output resolution depend on input density and broke determinism. One regrid call, exactly as configured.

## 3. Settings

| Setting | Meaning |
|---|---|
| `pct` | Target edge length as a percentage — mesh density. Lower = finer |
| `iterations` | Isotropic remeshing iterations |
| `use_symmetry` | **Derived**, not user-set: `base.is_XZ_symmetric and heel == 0` (spec 01 §4) |

### On `iterations`

`DATABASE_DEFINITION.md` Appendix shows the same geometry at 1, 2, 4, 20 and 200 iterations: this is a genuine convergence knob, not a cosmetic one. Element regularity improves markedly with more iterations.

- Default **20** (pylot's working value).
- Expose it. The appendix example uses **200** for a converged result.
- Record the value used on the mesh; it is part of mesh identity (spec 02 §4).

## 4. Triangles to quads

Capytaine expects quadrilateral faces. A triangle is passed as a **degenerate quad** with the last vertex repeated: `(v1, v2, v3, v3)`. This is the documented pylot approach — keep it, and keep the comment explaining it, because it looks like a bug to a reader who has not seen it before.

## 5. The application point comes out of this pipeline

The application point is derived from `submerged_bounds` above (spec 01 §5.4.2) — **the centre of the bounds box in all three axes**.

It belongs to the **condition**, not the mesh (spec 01 §5.4.3), and it must be **independent of `pct` and `iterations`**: it is taken before the regrid precisely so that refining a mesh cannot move the moment reference of an existing database.

**Therefore expose the derivation as its own function** — `application_point_for(base_shape, transform)` — running only `transform` + `cut_at_waterline` + `bounds`.

> It takes a **transform, not a `FloatingCondition`**. A condition cannot be constructed without its application point, so the signature written here originally was circular. The full pipeline calls it; so does condition creation, without ever meshing. Assert in a test that the two routes agree, and that two meshes at different `pct` on one condition yield the same point.

### 5.1 Geometric properties are *not* cached

Volume, wetted area and waterline length are computed on demand from the stored mesh (spec 02 §1), not stored on it.

> **Volume is not directly available.** After the waterline cut the mesh is **open** — the waterplane is not capped — and pymeshlab reports no volume for an open mesh. Wetted area is available and is what the tests assert on. Displacement needs the waterplane capped first; treat that as work, not a property lookup. They are **display and sanity-check quantities only** — matching uses surface probes and needs none of them (spec 05 §2.2). Whatever computes them must **double the value when `is_XZ_symmetric`**, since the stored mesh is then a half vessel.

## 6. The lid is not produced here

Irregular-frequency removal uses a **lid mesh**. It is an artificial numerical construct introduced for the solver — it is not part of the vessel and not a property of a calculation mesh. It is generated from the mesh at solve time and never stored. See **spec 04 §2**.

The only thing this pipeline owes it: the mesh handed to the solver must be the *final* one, so a lid generated from it inherits the floating condition and the hull resolution automatically.

## 7. Contract

**Input:** `BaseShape`, `FloatingCondition`, `pct`, `iterations`
**Output:** `CalculationMesh` — diffraction-space vertices/faces, `is_XZ_symmetric`, settings

**Guarantees**

1. **Deterministic — within a process.** Same input and settings → same mesh, in one process. **Across processes it does not hold:** pymeshlab's isotropic remesher settles on one of two results 0.056% apart between runs of an identical script. Everything computed *before* the regrid — bounds, and therefore the application point — is bit-identical every time.
   >
   > Two consequences. **Exact-geometry golden files are not viable**, so regression fixtures assert face counts and bounds, not vertex positions or areas. And spec 03 §5's rule to read the bounds before the regrid, made so refinement could not move an existing database's moment reference, turns out to shield the application point from this as well.
2. **Meaningful failure.** An empty result after the waterline cut (vessel entirely above water, or entirely below with no intersection) raises with the condition and bounding box in the message — never returns an empty mesh. **This must be detected here:** pymeshup returns an empty mesh with degenerate bounds (`min > max`) rather than raising, and left alone that surfaces much later as an opaque pymeshlab error.
3. **Symmetry consistency.** `is_XZ_symmetric` is derived; a symmetric mesh is always paired with `ReflectionSymmetricMesh`.

## 8. Tests

1. Round trip: a box at a known condition produces the expected volume and wetted area within tolerance.
2. Waterline cut at `z = 0` in diffraction space; nothing above `z = 0` survives (tolerance for numerical noise).
3. Symmetry: with `heel == 0` and a symmetric base shape, the half mesh has `y <= 0` throughout and half the expected volume; with `heel != 0`, symmetry is refused.
4. Determinism: build twice, compare vertices and faces exactly.
5. Trim invariance: a trim slope applied to a symmetric shape keeps `is_XZ_symmetric` true.
6. Failure: a condition placing the vessel entirely above water raises.
7. Regression: a fixture base shape at a fixed condition matches a stored reference mesh by volume / wetted area / bounding box.
8. Cut commutativity: waterline-then-XZ and XZ-then-waterline give the same geometry (§1).
9. Application point is independent of `pct` and `iterations`, and `application_point_for()` agrees with the value the full pipeline produces (§5).
10. **Half-mesh input is refused**, not silently cut twice (§1).
11. **No lid leaks into the mesh:** a stored `CalculationMesh` carries hull geometry only, whatever lid settings a later solve uses (§6).

> Reuse the `boxboat` fixtures from the previous work (spec 08 § Salvage), but **regenerate the reference meshes** — the pipeline geometry changes with the corrected transform, so old golden files are not valid.
