"""Everything scales linearly with water density. Exactly.

Water density enters linear potential flow in **one** place: the linearised
Bernoulli pressure ``p = -rho * dphi/dt``. The boundary value problem for the
potential -- Laplace, the free-surface condition, the body condition -- has no
``rho`` in it at all. So added mass, radiation damping and the excitation force
are each ``rho`` times an integral that does not depend on ``rho``.

That is what lets a library be solved once and delivered at any density, so it
is asserted **bitwise**, not to a tolerance.

Measuring it needs care, and getting it wrong the first time is instructive:
comparing two separate solves shows a deviation of about 1e-3 in finite depth,
which looks like imperfect linearity and is not. Each fresh ``BEMSolver``
builds its own ``Delhommeau`` green function, and in **finite depth** two of
those differ by ~1e-5 -- the Prony decomposition is recomputed per instance and
is not bit reproducible. Two runs at the *same* density differ by just as much,
which is what identified it. Infinite depth is reproducible to 3e-16.

So the first half drives Capytaine through **one** solver instance. That is the
honest comparison, not a thumb on the scale: ``rho`` never enters those
matrices, which is the whole claim.

The second half checks the other side of the same coin -- that *we* apply the
density correctly on the way out. ``solve`` has no ``rho`` at all; results are
stored per unit density and scaled in the bridge.
"""

import numpy as np
import pytest
from hull import make_base_shape

import capytaine as cpt
from pylot_bem.capytaine_mesh import to_capytaine_mesh
from pylot_bem.mesh_pipeline import application_point_for, build_mesh
from pylot_bem.solver import SOLVE_RHO, SOLVE_RHO_SI, SolveSettings, solve
from pylot_db.frames import transform, transform_points
from pylot_db.hyddb import DOF_ORDER, STORED_RHO, BridgeError, to_hyddb1

COARSE = {"pct": 20.0, "iterations": 5}
DESIGN = transform(trim=0.0, heel=0.0, z_origin=-4.0)
OMEGAS = (0.5, 0.9)
DIRECTIONS = (0.0, 45.0, 90.0, 135.0)

RHO_LOW, RHO_HIGH = 0.5, 2.0
FACTOR = RHO_HIGH / RHO_LOW

QUANTITIES = ("added_mass", "radiation_damping", "excitation_force")
MOMENTS = ["Roll", "Pitch", "Yaw"]


@pytest.fixture(scope="module")
def geometry():
    base = make_base_shape(is_xz_symmetric=False)
    mesh = build_mesh(base, DESIGN, **COARSE)
    point = transform_points(application_point_for(base, DESIGN), DESIGN)
    return mesh, point


def at_two_densities(geometry, water_depth):
    """The same problem post-processed at two densities, from one solver.

    One ``BEMSolver`` means the influence matrices are assembled once and
    cached, so both densities share a potential exactly -- which is the claim,
    not a shortcut around it.
    """
    mesh, point = geometry
    body = cpt.FloatingBody(
        mesh=to_capytaine_mesh(mesh.vertices, mesh.faces, is_xz_symmetric=mesh.is_xz_symmetric),
        dofs=cpt.rigid_body_dofs(rotation_center=point),
    )
    solver = cpt.BEMSolver()

    def run(rho):
        problems = []
        for omega in OMEGAS:
            common = {"body": body, "omega": omega, "rho": rho * 1000.0, "water_depth": water_depth}
            problems += [cpt.RadiationProblem(radiating_dof=d, **common) for d in body.dofs]
            problems += [
                cpt.DiffractionProblem(wave_direction=np.radians(d), **common) for d in DIRECTIONS
            ]
        return cpt.assemble_dataset([solver.solve(p, _check_wavelength=False) for p in problems])

    return run(RHO_LOW), run(RHO_HIGH)


# --------------------------------------------------------------------------
# The solver: infinite depth
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def deep(geometry):
    return at_two_densities(geometry, np.inf)


@pytest.mark.parametrize("quantity", QUANTITIES)
def test_infinite_depth_scales_exactly(deep, quantity):
    low, high = deep

    assert np.array_equal(high[quantity].values, low[quantity].values * FACTOR)


def test_the_comparison_is_not_two_arrays_of_zeros(deep):
    """The guard. Every assertion here would hold trivially on an empty solve."""
    low, _ = deep

    for quantity in QUANTITIES:
        assert np.abs(low[quantity].values).max() > 0.0
    assert low["added_mass"].shape[0] == len(OMEGAS)
    assert low["excitation_force"].shape[1] == len(DIRECTIONS)


def test_the_excitation_phase_does_not_move(deep):
    """Density scales the amplitude and must not touch the phase. A phase shift
    would make the whole idea unusable, and would not show up in a magnitude
    comparison.
    """
    low, high = deep
    a, b = low["excitation_force"].values, high["excitation_force"].values
    big = np.abs(a) > 1e-9 * np.abs(a).max()

    assert np.abs(np.angle(b[big] / a[big])).max() < 1e-15


@pytest.mark.parametrize("quantity", QUANTITIES)
def test_the_moments_scale_like_the_forces(deep, quantity):
    """Roll, Pitch and Yaw are moments, and an integral of pressure times a
    lever arm. The lever arm has no density in it either.
    """
    low, high = deep

    a = low[quantity].sel(influenced_dof=MOMENTS).values
    b = high[quantity].sel(influenced_dof=MOMENTS).values
    assert np.array_equal(b, a * FACTOR)


# --------------------------------------------------------------------------
# The solver: shallow water, a different potential problem entirely
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def shallow(geometry):
    return at_two_densities(geometry, 8.0)


@pytest.mark.parametrize("quantity", QUANTITIES)
def test_shallow_water_scales_exactly(shallow, quantity):
    """8 m of water over a 4 m draft. Shallow water changes the Green function
    completely and leaves the density dependence alone.
    """
    low, high = shallow

    assert np.array_equal(high[quantity].values, low[quantity].values * FACTOR)


def test_shallow_water_really_is_shallow(shallow, deep):
    """The premise. If the finite-depth Green function were quietly falling
    back to the infinite-depth one, the test above would prove nothing new.
    """
    shallow_low, _ = shallow
    deep_low, _ = deep

    heave_shallow = float(shallow_low["added_mass"].sel(omega=0.5, radiating_dof="Heave", influenced_dof="Heave"))
    heave_deep = float(deep_low["added_mass"].sel(omega=0.5, radiating_dof="Heave", influenced_dof="Heave"))

    assert abs(heave_shallow / heave_deep - 1.0) > 0.1, "shallow water changed the answer substantially"


# --------------------------------------------------------------------------
# And that we apply it correctly on the way out
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def stored(geometry):
    """One solve, through the public API. It has no ``rho``: results are per
    unit density and the density is applied on delivery.
    """
    mesh, point = geometry
    return solve(
        mesh.vertices,
        mesh.faces,
        is_xz_symmetric=mesh.is_xz_symmetric,
        application_point=point,
        settings=SolveSettings(omegas=OMEGAS, wave_directions=DIRECTIONS),
    )


def test_a_solve_is_normalised_to_the_stored_density(stored):
    """The premise everything downstream scales from, asserted rather than
    intended. ``SolveSettings`` has no ``rho`` to get wrong, and this is what
    turns that from a convention into a guarantee.
    """
    assert float(stored["rho"]) == SOLVE_RHO_SI
    assert SOLVE_RHO == STORED_RHO, "the solver and the bridge must agree on the reference"


def test_delivering_at_the_stored_density_changes_nothing(stored):
    """rho = 1 is the identity. If it were not, the normalisation and the
    scaling would disagree and every database would be off by a constant.
    """
    plain = to_hyddb1(stored, rho=STORED_RHO)

    raw = stored["added_mass"].sel(
        omega=OMEGAS[0], radiating_dof=list(DOF_ORDER), influenced_dof=list(DOF_ORDER)
    ).values
    # kg -> mt is the only conversion left once the density factor is 1.
    assert np.allclose(plain.amass(OMEGAS[0]), raw * 1e-3)


@pytest.mark.parametrize("rho", [0.5, 1.0, 1.025, 2.0])
def test_delivery_scales_the_database_linearly(stored, rho):
    reference = to_hyddb1(stored, rho=STORED_RHO)
    delivered = to_hyddb1(stored, rho=rho)

    for omega in OMEGAS:
        assert np.allclose(delivered.amass(omega), reference.amass(omega) * rho)
        assert np.allclose(delivered.damping(omega), reference.damping(omega) * rho)
        for direction in DIRECTIONS:
            assert np.allclose(delivered.force(omega, direction), reference.force(omega, direction) * rho)


def test_delivery_leaves_the_phase_alone(stored):
    """Density is an amplitude, and a phase shift would not show up in any
    magnitude comparison.
    """
    reference = to_hyddb1(stored, rho=STORED_RHO)
    delivered = to_hyddb1(stored, rho=2.0)

    a = reference.force(OMEGAS[0], DIRECTIONS[1])
    b = delivered.force(OMEGAS[0], DIRECTIONS[1])
    big = np.abs(a) > 1e-9 * np.abs(a).max()

    assert np.abs(np.angle(b[big] / a[big])).max() < 1e-12


@pytest.mark.parametrize("bad", [0.0, -1.025])
def test_a_density_of_zero_or_less_is_refused(stored, bad):
    """Not hypothetical: a forgotten variable is far more likely to be 0 than
    to be 1.025, and a database of zeros reads as a solver failure.
    """
    with pytest.raises(BridgeError, match="positive"):
        to_hyddb1(stored, rho=bad)
