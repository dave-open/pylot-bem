"""Degrees in, slopes out, and the difference between sin and tan.

The conversion was ``tan`` for the life of the project, in two independent
copies -- the application's and the CLI's. It is ``sin``: a slope is the
z-component of the vessel's own *unit* axis vector, so it is the change in z
per unit length **along the axis**, not per unit horizontal distance.
"""

import numpy as np
import pytest

from pylot_bem.angles import degrees_from_slope, slope_from_degrees, spans_the_circle
from pylot_db.frames import check_domain, decompose, transform


@pytest.mark.parametrize("degrees", [0.0, 1.0, 5.0, 15.0, 30.0, 45.0, 60.0, 89.0, -30.0])
def test_degrees_round_trip(degrees):
    assert degrees_from_slope(slope_from_degrees(degrees)) == pytest.approx(degrees, abs=1e-9)


@pytest.mark.parametrize("degrees", [1.0, 5.0, 15.0, 30.0, 45.0, 60.0, -30.0])
def test_the_slope_is_the_sine_not_the_tangent(degrees):
    assert slope_from_degrees(degrees) == pytest.approx(np.sin(np.radians(degrees)))
    if degrees != 0.0:
        assert slope_from_degrees(degrees) != pytest.approx(np.tan(np.radians(degrees)), abs=1e-6)


def test_the_slope_is_the_z_of_the_rotated_unit_axis():
    """The definition, checked against the transform rather than restated.

    This is what makes it ``sin``: ``transform`` puts ``heel`` straight into a
    column of a rotation matrix, and those columns are unit vectors.
    """
    for degrees in (5.0, 30.0, 45.0, 60.0):
        slope = slope_from_degrees(degrees)
        t = transform(trim=0.0, heel=slope, z_origin=0.0)
        y_axis = t[:3, 1]

        assert np.linalg.norm(y_axis) == pytest.approx(1.0), "columns of a rotation are unit vectors"
        assert y_axis[2] == pytest.approx(slope)
        # The angle actually achieved is the angle asked for.
        assert np.degrees(np.arcsin(y_axis[2])) == pytest.approx(degrees)


def test_a_45_degree_condition_is_representable():
    """Under ``tan`` this was refused outright.

    ``tan(45 deg)`` is exactly 1.0, and ``check_domain`` rejects
    ``abs(trim) >= 1``. So a vessel at 45 degrees of trim -- nothing unusual
    about it -- could not be entered at all. Under ``sin`` the slope is 0.707
    and it is an ordinary interior point of the unit disc.
    """
    slope = slope_from_degrees(45.0)
    assert slope == pytest.approx(np.sqrt(0.5))
    assert np.tan(np.radians(45.0)) == pytest.approx(1.0), "which check_domain refuses"

    check_domain(trim=slope, heel=0.0)  # must not raise
    assert decompose(transform(trim=slope, heel=0.0, z_origin=-4.0)).trim == pytest.approx(slope)


def test_tan_would_have_stored_a_different_angle_than_was_asked_for():
    """The user-visible consequence, stated as a number.

    30 degrees typed under the old conversion was stored as 0.5774, which is
    the sine of 35.26 degrees -- the vessel floated 5 degrees off what was
    asked for, and every mesh and solve below it inherited that.
    """
    asked = 30.0
    stored_under_tan = np.tan(np.radians(asked))
    angle_actually_achieved = np.degrees(np.arcsin(stored_under_tan))

    assert angle_actually_achieved == pytest.approx(35.264, abs=1e-3)
    assert degrees_from_slope(slope_from_degrees(asked)) == pytest.approx(asked)


def test_small_angles_are_why_this_survived():
    """Below about 5 degrees the two agree to three decimals."""
    assert slope_from_degrees(2.0) == pytest.approx(np.tan(np.radians(2.0)), abs=1e-4)
    # ... and diverge visibly well before the domain edge.
    assert abs(slope_from_degrees(40.0) - np.tan(np.radians(40.0))) > 0.19


@pytest.mark.parametrize("slope", [-1.0, 1.0])
def test_the_domain_edge_gives_a_right_angle_not_a_nan(slope):
    assert degrees_from_slope(slope) == pytest.approx(90.0 * np.sign(slope))


@pytest.mark.parametrize("slope", [1.0 + 1e-12, -1.0 - 1e-12, 2.0])
def test_a_slope_past_the_edge_is_clamped_rather_than_nan(slope):
    """A stored slope cannot legitimately exceed 1, but it is read back off a
    matrix and can land a few ulps over. ``arcsin`` would return nan, and a
    nan reaching a widget shows as "nan deg" long after the cause is gone.
    """
    assert np.isfinite(degrees_from_slope(slope))
    assert abs(degrees_from_slope(slope)) == pytest.approx(90.0)


# --------------------------------------------------------------------------
# Whether a heading grid goes all the way round
# --------------------------------------------------------------------------


def test_half_the_compass_does_not_span_it():
    """The case the whole check exists for: 0-180 on a full vessel."""
    assert not spans_the_circle([0.0, 45.0, 90.0, 135.0, 180.0])
    assert not spans_the_circle(list(range(0, 181, 15)))


def test_the_whole_compass_spans_it_without_its_wrap_around_point():
    """A grid that reaches all the way round deliberately omits 360: it is the
    same heading as 0, and solving both stores a duplicate column. So the test
    is the arc covered *plus one more step*, which is how a reader counts it.
    """
    assert spans_the_circle(list(range(0, 360, 15)))
    assert spans_the_circle(list(range(0, 360, 45)))
    assert spans_the_circle([-180.0, -90.0, 0.0, 90.0]), "and it does not assume it starts at 0"


def test_two_opposite_headings_span_it_coarsely_and_that_is_the_honest_answer():
    """``[0, 180]`` has a 180-degree gap either way round, so it *is* uniform
    over the circle — a terrible grid, but not a one-sided one. This function
    answers coverage, not resolution, and pinning the surprising case keeps a
    later reader from 'fixing' it into something that reports a lopsided grid
    and a symmetric one the same way.
    """
    assert spans_the_circle([0.0, 180.0])
    assert not spans_the_circle([0.0, 90.0, 180.0]), "270 is never solved"


def test_a_grid_too_short_to_have_a_step_spans_nothing():
    assert not spans_the_circle([0.0])
    assert not spans_the_circle([])
