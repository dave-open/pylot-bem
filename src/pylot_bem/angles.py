"""Degrees at a user-facing boundary, slopes everywhere behind it.

Storage and every API use **slopes**; degrees appear only where a human types
or reads one -- the application and the CLI (``CLAUDE.md``). Both of those
boundaries need the same pair of conversions, so they live here rather than in
either of them: the CLI had its own inline copy, and when the relationship
below turned out to be wrong it had to be corrected in two places, which is
the argument for one.

**The slope is the sine of the angle, not its tangent.**

A slope is the z-component of the vessel's own unit axis vector after the
rotation (pylot-db's spec 01 section 3.1), so for a rotation of ``a`` it is
``sin(a)`` -- the change in z per unit length **along the axis**, not per unit
length horizontally. ``tan`` is the change in z per unit *horizontal* distance,
which is a different quantity and was what this used to compute.

Two things make the distinction concrete rather than pedantic:

- the valid domain is ``trim**2 + heel**2 <= 1``, a **unit disc**, which is
  exactly the statement that both are components of one unit vector. Under
  ``tan`` a 45 degree trim gives a slope of 1.0 and is *refused* as
  out-of-domain, though nothing is wrong with a vessel at 45 degrees;
- under ``tan`` the error grows with the angle, so a condition entered as 30
  degrees was stored as 0.577, which is the sine of **35.3** degrees. The
  vessel floated at an angle the user never asked for, and every mesh and
  solve below it inherited that.

They agree to three decimal places below about 5 degrees, which is why this
survived: the small-angle cases anyone would check by eye looked right.
"""

import numpy as np

__all__ = ["degrees_from_slope", "slope_from_degrees", "spans_the_circle"]


def slope_from_degrees(angle: float) -> float:
    """Degrees as typed by a user, as the slope that gets stored.

    Args:
        angle: Heel or trim in degrees.

    Returns:
        The slope: the sine of the angle, dimensionless.
    """
    return float(np.sin(np.radians(angle)))


def degrees_from_slope(slope: float) -> float:
    """A stored heel or trim slope, in degrees.

    The interface never shows a slope -- not even as a secondary readout
    (spec 09 section M).

    Args:
        slope: Heel or trim slope. ``abs(slope) <= 1`` for any real condition,
            since it is one component of a unit vector.

    Returns:
        The angle in degrees.
    """
    # Clamped because arcsin is undefined past 1 and would return nan. A stored
    # slope cannot legitimately exceed 1, but it is read back off a matrix and
    # can land a few ulps over after a round trip -- and a nan reaching a
    # widget shows as "nan deg" long after the cause is out of sight.
    return float(np.degrees(np.arcsin(np.clip(slope, -1.0, 1.0))))


def spans_the_circle(directions) -> bool:
    """Whether a heading grid covers the whole compass.

    The question a **full-vessel** solve has to answer. An XZ-symmetric body at
    zero heel has a port half that is the mirror of its starboard half, so
    solving 0-180 and filling in the rest on delivery is exact. A full vessel
    has no half to mirror -- and the delivered database still covers 360
    degrees, because mafredo does not refuse a heading past 180. It interpolates
    across whatever was never solved and answers confidently.

    So this is not a preference. On a full vessel a half grid is a database that
    is wrong over half the compass with nothing anywhere saying so, which is
    why both the Solve screen and the batch runner ask this and say something
    when the answer is no.

    Measured as *the arc covered, plus one more step* -- because a grid that
    spans the circle deliberately omits its wrap-around point: 0 and 360 are
    the same heading and solving both stores a duplicate column. So 0..345 in
    steps of 15 covers the circle and 0..180 does not, which is exactly how a
    reader would count it.

    Args:
        directions: Headings [degrees], ascending. Fewer than two cannot span
            anything.

    Returns:
        Whether the grid reaches the whole way round.
    """
    values = [float(d) for d in directions]
    if len(values) < 2:
        return False
    # The last step rather than the first: an uneven grid is judged on the gap
    # it actually leaves at the wrap-around, which is the one that matters.
    step = values[-1] - values[-2]
    return (max(values) - min(values)) + step >= 360.0 - 1e-9
