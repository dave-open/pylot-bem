"""The example scripts actually run.

Examples rot faster than anything else in a repository: they are the first
thing a rename breaks and the last thing anyone runs. These execute each one
for real and then check the library it claims to have produced, so an example
that runs but writes something broken fails too.

Executed in-process with :func:`runpy.run_path` rather than as subprocesses --
importing Capytaine four times costs more than everything the examples do.

They write to ``examples/output/``, which is where they write when a person
runs them. That is deliberate: a test against a temporary copy would not catch
an example that only works from a particular directory.
"""

import ast
import runpy
from pathlib import Path

import pytest

from pylot_db.storage import Library

EXAMPLES = Path(__file__).parents[1] / "examples"


def run_example(name: str) -> None:
    script = EXAMPLES / name
    assert script.exists(), f"{script} is missing"
    runpy.run_path(str(script), run_name="__main__")


def check(library_name: str, *, conditions: int, results: int) -> Library:
    """Open what an example wrote and confirm it is a working library."""
    path = EXAMPLES / "output" / library_name
    assert path.exists(), f"{path} was not written"

    with Library.open(path) as library:
        assert library.validate() == [], "the example produced a library with findings"
        assert len(library.conditions()) == conditions
        assert len(library.results()) == results
        assert all(view.usable for view in library.databases())
        return library


@pytest.fixture(scope="module")
def built():
    """Example 01, run once. Example 02 reads what it writes."""
    run_example("01_build_a_library.py")


def test_01_builds_a_library_that_validates(built):
    check("tanker.pylot", conditions=3, results=3)


def test_01_produces_three_meshes_a_solver_can_use(built):
    with Library.open(EXAMPLES / "output" / "tanker.pylot") as library:
        meshes = library.meshes()

    assert len(meshes) == 3
    assert all(mesh.is_xz_symmetric for mesh in meshes), "upright conditions on a symmetric hull"
    assert all(len(mesh.faces) > 0 for mesh in meshes)


def test_02_matches_and_delivers(built, capsys):
    run_example("02_match_and_deliver.py")
    out = capsys.readouterr().out

    # The example's whole point: the middle draft wins, and the hard filter
    # excludes rather than ranks. Asserted on the output because that is what
    # a reader sees -- a script that runs but prints nothing useful has failed.
    assert "best          design" in out
    assert "in 40 m water 0 candidates" in out, "depth is a hard filter"
    assert "(= 1.025 / 1.000, exactly)" in out, "density is not -- it is a delivery choice"


def imported_modules(script: Path) -> set[str]:
    """The top-level modules a script imports, read from its syntax tree.

    Not a text search: every one of these names appears in the prose of the
    example that must not import them, which is exactly the sort of thing a
    grep-based check gets wrong in both directions.
    """
    tree = ast.parse(script.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_02_needs_no_calculation_stack():
    """It imports pylot_db only, which is the whole point of the split: a
    library is built once where the solver is installed, and read everywhere.
    """
    imported = imported_modules(EXAMPLES / "02_match_and_deliver.py")

    assert "pylot_db" in imported, "the premise: it does read a library"
    assert not imported & {"pylot_bem", "capytaine", "pymeshup", "DAVE"}


def test_the_import_check_can_tell_the_two_sides_apart():
    """The guard on the guard. If imported_modules returned nothing useful,
    the assertion above would hold for every file in the repository.
    """
    assert "pylot_bem" in imported_modules(EXAMPLES / "01_build_a_library.py")


def test_03_reaches_a_conflict_and_resolves_it(capsys):
    run_example("03_conflicts_and_cleanup.py")
    out = capsys.readouterr().out

    assert "usable      False" in out, "it has to actually get into conflict"
    assert "assemble      refused" in out
    assert "usable True" in out, "and out of it again"

    check("conflict.pylot", conditions=1, results=2)


def test_05_retrieves_meshes_the_database_and_renders(built, capsys, tmp_path):
    """Run headless -- interactive=True would block the suite on a window."""
    namespace = runpy.run_path(str(EXAMPLES / "05_look_at_it.py"), run_name="not_main")
    namespace["main"](interactive=False)
    out = capsys.readouterr().out

    assert "placed z    -12.0 to 16.0 m" in out, "the hull is placed in diffraction space"
    assert "half vessel=True" in out
    assert "Hyddb1 for design" in out

    png = EXAMPLES / "output" / "design.png"
    assert png.exists() and png.stat().st_size > 5000


def test_04_reports_progress_and_cancels(capsys):
    run_example("04_progress_and_cancellation.py")
    out = capsys.readouterr().out

    assert "cancelled   after" in out
    assert "results       ['run1']" in out, "the cancelled run stored nothing"

    check("progress.pylot", conditions=1, results=1)


def test_06_batches_a_grid_survives_a_bad_step_and_resumes(capsys):
    """All three of the example's claims, asserted on what a reader sees.

    Two conditions solved out of three asked for, the third refused with its
    reason -- and the same job run again writing nothing. An example that ran
    but quietly did none of what its docstring promises has failed.
    """
    run_example("06_batch_overnight.py")
    out = capsys.readouterr().out

    assert "created       2 conditions, 4 meshes, 4 results" in out
    assert "nothing lies below the waterplane" in out, "the bad step names its reason"
    assert "second pass   wrote 0 results" in out, "running it again must not duplicate"
    assert "reused 2 conditions, skipped 4 solves" in out
    assert "loads back    identical" in out, "the job it saved is the job it ran"

    # Two conditions, two bands each: the third never got off the ground.
    check("batch.pylot", conditions=2, results=4)
    assert (EXAMPLES / "output" / "batch.pylotjob").exists()
