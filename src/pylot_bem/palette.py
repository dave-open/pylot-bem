"""What a hull, a mesh and the sea look like.

Five strings, in their own module for one reason: both things that draw need
them, and one of the two -- :mod:`pylot_bem.app.viewport` -- reaches VTK
directly rather than through :mod:`pylot_bem.plotting`, which would pull in
vedo that the application never needs. See :mod:`pylot_bem.polydata`.

These say what a thing **is**. Whether it is *usable* -- clean, incomplete, in
conflict -- is a different question with a different palette, in
:mod:`pylot_bem.app.formatting`. Keeping them apart is what stops an orange
calculation mesh reading as a warning.
"""

__all__ = ["APPLICATION_POINT", "BACKFACE", "CALCULATION_MESH", "HULL", "PROBE", "SEA"]

# Muted enough that a wireframe on top of it stays readable.
HULL = "#8fa8bf"
CALCULATION_MESH = "#e8a33d"
SEA = "#3a6ea5"
PROBE = "#d94f4f"
APPLICATION_POINT = "#2e2e2e"

# The inside of a surface. Unmistakable against the hull colour without reading
# as an error on a mesh simply being looked at from within (spec 09 section L).
BACKFACE = "#b04a3a"
