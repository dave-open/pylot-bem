"""pylot_db's complex-value encoding must be capytaine's.

``separate_complex_values`` was ported into ``pylot_db`` because capytaine is
the calculation stack and pylot_db may not import it (ADR-7). A port is only
safe if it stays identical, and this is the one package where both
implementations can be compared -- so the check lives here, not there.

Without it the two could drift and the failure would be silent: files that
capytaine and mafredo can no longer read, written by a package whose own tests
still pass.
"""

import numpy as np
import xarray as xr
from capytaine.io.xarray import separate_complex_values as capytaine_separate
from mafredo.helpers import merge_complex_values
from pylot_db.blobs import dataset_from_bytes, dataset_to_bytes
from pylot_db.blobs import separate_complex_values as ours

DOFS = ["Surge", "Sway", "Heave", "Roll", "Pitch", "Yaw"]


def make_dataset():
    """Unequal frequency and direction counts, so a transposition cannot hide."""
    rng = np.random.default_rng(11)
    n_omega, n_dir = 5, 7
    return xr.Dataset(
        {
            "added_mass": (("omega", "radiating_dof", "influenced_dof"), rng.random((n_omega, 6, 6))),
            "excitation_force": (
                ("omega", "wave_direction", "influenced_dof"),
                rng.random((n_omega, n_dir, 6)) + 1j * rng.random((n_omega, n_dir, 6)),
            ),
        },
        coords={
            "omega": np.linspace(0.2, 2.0, n_omega),
            "wave_direction": np.linspace(0.0, 300.0, n_dir),
            "radiating_dof": DOFS,
            "influenced_dof": DOFS,
        },
    )


def test_our_separation_is_identical_to_capytaines():
    dataset = make_dataset()
    assert ours(dataset).identical(capytaine_separate(dataset))


def test_capytaine_can_read_what_we_write():
    """The point of matching the encoding: our files stay readable elsewhere."""
    dataset = make_dataset()
    recovered = merge_complex_values(ours(dataset))
    assert recovered["excitation_force"].dtype == complex
    assert np.allclose(recovered["excitation_force"].values, dataset["excitation_force"].values)


def test_a_full_round_trip_through_bytes_preserves_the_complex_values():
    dataset = make_dataset()
    recovered = dataset_from_bytes(dataset_to_bytes(dataset))

    assert recovered["excitation_force"].dtype == complex
    assert np.allclose(recovered["excitation_force"].values, dataset["excitation_force"].values)
    assert np.allclose(recovered["added_mass"].values, dataset["added_mass"].values)
    assert list(recovered["influenced_dof"].values) == DOFS


def test_a_dataset_with_no_complex_values_is_left_alone():
    """The guard: the separation must not invent a complex axis where none is needed."""
    real_only = xr.Dataset({"added_mass": (("omega",), np.array([1.0, 2.0]))}, coords={"omega": [0.1, 0.2]})
    assert "complex" not in ours(real_only).coords
    assert ours(real_only).identical(capytaine_separate(real_only))
