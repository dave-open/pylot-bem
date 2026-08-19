"""Turning stored values into what the interface shows.

Every conversion the application performs is here, because the units it
displays are deliberately **not** the units it stores (pylot-db's spec 01 section 7,
spec 09):

======================  ==================  ====================
Quantity                Stored              Shown
======================  ==================  ====================
Heel, trim              slope               degrees
Frequency               omega [rad/s]       period [s]
Length                  metres              metres
Density                 not stored at all   t/m3, on delivery
======================  ==================  ====================

Collecting them means the conversion appears once per direction rather than at
every widget, which is what stops a screen quietly showing a slope labelled
"deg". The functions are plain and take no Qt types, so they are testable
without a display.

Rich text is used for derived readouts: a value followed by the *reason* for it
in a muted colour. Spec 09's cross-cutting rule 2 -- every refusal states its
reason -- extends naturally to every derived number stating where it came from.
"""

import numpy as np
from pylot_db.entities import FloatArray

# Re-exported rather than defined here. The CLI converts degrees at its own
# boundary and must not import the application package to do it, so the pair
# lives in :mod:`pylot_bem.angles`; every caller in this package goes on
# importing it from here, alongside the other display conversions.
from pylot_bem.angles import degrees_from_slope, slope_from_degrees, spans_the_circle

__all__ = [
    "CLEAN",
    "CONFLICT",
    "INCOMPLETE",
    "MUTED",
    "degrees_from_slope",
    "derived",
    "escape",
    "format_depth",
    "format_grid",
    "format_point",
    "format_range",
    "omega_from_period",
    "period_from_omega",
    "slope_from_degrees",
    "spans_the_circle",
    "symmetry_reason",
]

# Grey enough to recede next to a value, dark enough to read on either theme.
MUTED = "#888888"

# The three states an assembly key can be in (pylot-db's spec 02 section 3), used wherever
# one is shown: the dot beside a result in the tree, the pill in the Databases
# tab, the severity of a finding. One definition, because a user learns these
# three colours once and then reads them everywhere.
#
# Deliberately not the hull/mesh/sea colours of :mod:`pylot_bem.plotting`:
# those say what a thing *is*, these say whether it is *usable*, and a palette
# that conflates the two makes an orange mesh look like a warning.
CLEAN = "#23705a"
INCOMPLETE = "#9a6b12"
CONFLICT = "#b93425"


def period_from_omega(omega: float) -> float:
    """Wave period [s] from angular frequency [rad/s]."""
    return float(2 * np.pi / omega)


def omega_from_period(period: float) -> float:
    """Angular frequency [rad/s] from wave period [s]."""
    return float(2 * np.pi / period)


def escape(text: str) -> str:
    """Make text safe to drop into a rich-text label.

    Labels carry user-entered values -- a vessel name, a condition label, a
    solver message. A stray ``<`` would otherwise silently swallow the rest of
    the line.
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def derived(value: str, why: str = "") -> str:
    """A derived readout: the value, then why it is that.

    Args:
        value: Already formatted, and already escaped if it came from a user.
        why: The reason, shown muted. Escaped here.

    Returns:
        Rich text for a ``QLabel``.
    """
    if not why:
        return value
    return f'{value} <span style="color:{MUTED}">{escape(why)}</span>'


def format_point(point: FloatArray, *, decimals: int = 3) -> str:
    """A 3-vector as ``(x, y, z)``."""
    x, y, z = (float(v) for v in np.asarray(point, dtype=float).ravel()[:3])
    return f"({x:.{decimals}f}, {y:.{decimals}f}, {z:.{decimals}f})"


def format_range(values, *, decimals: int = 2, unit: str = "") -> str:
    """``lo - hi`` for a grid, or the single value when there is one.

    Deliberately not a count: spec 06 section 6.4 requires the *grid* to be
    visible, because a cancelled run leaves holes in it and a count hides them.
    Use :func:`format_grid` where the individual values matter.
    """
    values = np.asarray(values, dtype=float).ravel()
    if values.size == 0:
        return "none"
    suffix = f" {unit}" if unit else ""
    if values.size == 1:
        return f"{values[0]:.{decimals}f}{suffix}"
    return f"{values.min():.{decimals}f} – {values.max():.{decimals}f}{suffix}"


def format_depth(depth: float) -> str:
    """Water depth, with ``inf`` spelled out."""
    return "infinite" if np.isinf(depth) else f"{depth:g} m"


def symmetry_reason(base_is_symmetric: bool, heel: float) -> tuple[bool, str]:
    """Whether a mesh at this condition is a half vessel, and why.

    Spec 01 section 4 makes symmetry derived and spec 09 section C requires the
    *reason* to be shown with it. A bare "no" invites a user to go looking for
    the checkbox that turned it off; there isn't one, and the reason says so.

    Args:
        base_is_symmetric: What the modeller declared about the hull.
        heel: The condition's heel **slope**.

    Returns:
        ``(symmetric, reason)``.
    """
    if not base_is_symmetric:
        return False, "the hull is not declared symmetric — full vessel"
    if heel != 0.0:
        return False, f"heel ≠ 0 ({degrees_from_slope(heel):.2f} deg) — full vessel"
    return True, "hull declared symmetric, heel = 0 — half vessel, mirrored by the solver"


def format_grid(values, *, decimals: int = 2, limit: int = 12) -> str:
    """Every value, comma separated, truncated past ``limit``."""
    values = np.asarray(values, dtype=float).ravel()
    shown = ", ".join(f"{v:.{decimals}f}" for v in values[:limit])
    if values.size > limit:
        shown += f", … ({values.size} in all)"
    return shown or "none"
