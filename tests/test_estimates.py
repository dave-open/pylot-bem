"""What a solve will cost, and where a mesh stops being trustworthy.

These were written inside the CLI first. They are tested here because they are
now API: the application shows the same three numbers, and two copies of the
same derivation would eventually disagree about the same mesh.
"""

import numpy as np
import pytest
from hull import make_base_shape

from pylot_bem.estimates import (
    BYTES_PER_PANEL_SQUARED,
    influence_matrix_bytes,
    shortest_reliable_period,
    solved_panels,
)
from pylot_bem.mesh_pipeline import build_mesh
from pylot_db.entities import CalculationMesh
from pylot_db.frames import transform

DESIGN = transform(trim=0.0, heel=0.0, z_origin=-4.0)


def make_mesh(faces, is_xz_symmetric):
    return CalculationMesh(
        id="m",
        condition_id="c",
        vertices=np.zeros((3, 3)),
        faces=np.zeros((faces, 3), dtype=int),
        is_xz_symmetric=is_xz_symmetric,
        pct=2.0,
        iterations=20,
    )


# --------------------------------------------------------------------------
# The doubling trap
# --------------------------------------------------------------------------


def test_a_symmetric_mesh_costs_twice_its_face_count():
    """A half vessel is mirrored by the solver, so the solver sees both halves.

    CalculationMesh says this trap "belongs in one function, not at each call
    site" -- and the CLI had it written out at two.
    """
    assert solved_panels(make_mesh(100, is_xz_symmetric=True)) == 200
    assert solved_panels(make_mesh(100, is_xz_symmetric=False)) == 100


def test_it_reads_a_mesh_geometry_too():
    """The pipeline's output and the stored entity are different types with the
    same two fields, and the estimate is wanted before storing as well as after.
    """
    geometry = build_mesh(make_base_shape(), DESIGN, pct=20.0, iterations=5)

    assert geometry.is_xz_symmetric is True
    assert solved_panels(geometry) == 2 * len(geometry.faces)


# --------------------------------------------------------------------------
# Memory
# --------------------------------------------------------------------------


def test_memory_is_quadratic_in_the_panel_count():
    assert influence_matrix_bytes(1000) == 4 * influence_matrix_bytes(500)
    assert influence_matrix_bytes(1) == BYTES_PER_PANEL_SQUARED


def test_a_realistic_mesh_lands_in_a_believable_range():
    """5000 panels is an ordinary hull. Two dense complex matrices of that size
    are 800 MB -- the number that decides how many workers a machine can carry.
    """
    assert 0.7e9 < influence_matrix_bytes(5000) < 0.9e9


# --------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------


def test_a_finer_mesh_is_trustworthy_at_shorter_periods():
    """The property that matters, checked against real meshes rather than the
    formula -- which would only be the formula written twice.
    """
    base = make_base_shape()
    coarse = build_mesh(base, DESIGN, pct=20.0, iterations=5)
    fine = build_mesh(base, DESIGN, pct=5.0, iterations=5)

    coarse_limit = shortest_reliable_period(coarse.vertices, coarse.faces)
    fine_limit = shortest_reliable_period(fine.vertices, fine.faces)

    assert len(fine.faces) > len(coarse.faces), "the premise: pct actually refined it"
    assert fine_limit < coarse_limit


def test_the_limit_is_a_wave_period_of_a_plausible_size():
    """A coarse mesh of a 60 m box: panels of a few metres, so a handful of
    seconds. Sub-second or minutes would both mean the dispersion relation or
    the panel radius went in wrong.
    """
    limit = shortest_reliable_period(*_geometry(build_mesh(make_base_shape(), DESIGN, pct=20.0, iterations=5)))
    assert 2.0 < limit < 20.0


def test_it_scales_with_the_square_root_of_panel_size():
    """Deep water: omega^2 = g k, so period goes as sqrt(wavelength) and a mesh
    scaled up by four is trustworthy to twice the period. Asserted on a scaled
    copy of one mesh, so nothing but the size changes.
    """
    mesh = build_mesh(make_base_shape(), DESIGN, pct=20.0, iterations=5)
    once = shortest_reliable_period(mesh.vertices, mesh.faces)
    four_times = shortest_reliable_period(mesh.vertices * 4.0, mesh.faces)

    assert four_times == pytest.approx(2.0 * once, rel=1e-9)


def _geometry(mesh):
    return mesh.vertices, mesh.faces
