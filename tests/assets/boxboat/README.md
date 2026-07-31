# Boxboat Hydrodynamic Database Notes

This document explains the physical meaning of the main datasets in `boxboat_lib.h5`.

## Scope

The hydrodynamic case groups in this file store linear frequency-domain coefficients and wave loads for a rigid body with 6 degrees of freedom (DOF):

1. Surge (translation in x)
2. Sway (translation in y)
3. Heave (translation in z)
4. Roll (rotation about x)
5. Pitch (rotation about y)
6. Yaw (rotation about z)

For the load datasets in this file, a typical shape is:

- `(15, 16, 6)` = `(frequency, wave_direction, dof)`

So for `Froude_Krylov_force`:

- axis 0 (length 15): frequencies (`omega`)
- axis 1 (length 16): wave directions (`wave_direction`)
- axis 2 (length 6): DOF component (`influenced_dof`)

## Main Fields

### `Froude_Krylov_force`

Wave force/moment contribution from integrating the undisturbed incident-wave pressure over the wetted hull.

Physical interpretation: direct pressure loading from the incoming wave, without diffraction correction.

In this file: complex-valued dataset with shape `(N_omega, N_dir, 6)`.

### `diffraction_force`

Wave force/moment contribution caused by wave scattering around the body.

Physical interpretation: extra load induced because the body modifies the surrounding wave field.

In this file: complex-valued dataset with shape `(N_omega, N_dir, 6)`.

### `excitation_force`

Total wave excitation force/moment on the fixed body.

Physical relation:

`excitation_force = Froude_Krylov_force + diffraction_force`

In this file: complex-valued dataset with shape `(N_omega, N_dir, 6)`.

### `added_mass`

Frequency-dependent hydrodynamic inertia matrix.

Physical interpretation: apparent extra mass/inertia from accelerated surrounding water.

In this file: real-valued dataset with shape `(N_omega, 6, 6)` over `(omega, radiating_dof, influenced_dof)`.

### `radiation_damping`

Frequency-dependent radiation damping matrix.

Physical interpretation: damping from energy radiated away as outgoing waves when the body oscillates.

In this file: real-valued dataset with shape `(N_omega, 6, 6)` over `(omega, radiating_dof, influenced_dof)`.

### `radiating_dof`

DOF index/label of the imposed motion mode used in radiation problems.

Physical interpretation in matrix form:

- `radiating_dof = j`: the body oscillates in mode `j`
- `influenced_dof = i`: resulting hydrodynamic force/moment component is measured in mode `i`

So matrix elements `A_ij(omega)` (`added_mass`) and `B_ij(omega)` (`radiation_damping`) describe coupling from motion mode `j` to load component `i`.

## Notes on Coordinates and Units

- `omega` is angular frequency in rad/s.
- `wave_direction` in this file is stored in radians.
- Force entries correspond to translational DOFs (Surge, Sway, Heave).
- Moment entries correspond to rotational DOFs (Roll, Pitch, Yaw).
- Complex load values encode amplitude and phase.

## Practical h5web Tip

If you view `Froude_Krylov_force` as a heatmap and set:

- x = `D0`
- y = `D1`

then you see one `15 x 16` slice for a fixed `D2` index.
Changing `D2` switches between DOF components:

- 0 Surge
- 1 Sway
- 2 Heave
- 3 Roll
- 4 Pitch
- 5 Yaw
