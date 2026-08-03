"""The three commands, driven as a user would drive them.

Every test calls ``main(argv)`` with a real library on disk and checks the file
afterwards. Nothing is mocked -- a CLI that only ever ran against a fake would
be exactly the illusory coverage spec 08 section 3 exists to prevent.
"""

import numpy as np
import pytest
from hull import make_base_shape
from pylot_bem.angles import slope_from_degrees
from pylot_bem.cli import UsageError, main, parse_range

from pylot_db.storage import Library
from pylot_db.validation import validate


@pytest.fixture
def library_path(tmp_path):
    """An empty library with a base shape -- created the way the UI would."""
    base = make_base_shape()
    path = tmp_path / "boxboat.pylot"
    with Library.create(
        path,
        vessel_name="Boxboat",
        origin_description="stern, centerline, keel",
        vertices=base.vertices,
        faces=base.faces,
        is_xz_symmetric=base.is_xz_symmetric,
    ):
        pass
    return path


def run(*argv):
    return main([str(a) for a in argv])


# --------------------------------------------------------------------------
# Range parsing
# --------------------------------------------------------------------------


def test_a_range_is_inclusive_of_its_end():
    assert parse_range("4:8:1", what="x") == [4.0, 5.0, 6.0, 7.0, 8.0]


def test_a_range_that_does_not_land_on_its_end_stops_short():
    assert parse_range("4:8:3", what="x") == [4.0, 7.0]


def test_a_comma_list_is_accepted():
    assert parse_range("4,6.5,20", what="x") == [4.0, 6.5, 20.0]


def test_a_single_value_is_accepted():
    assert parse_range("8", what="x") == [8.0]


def test_values_come_back_sorted_and_deduplicated():
    assert parse_range("8,4,8", what="x") == [4.0, 8.0]


@pytest.mark.parametrize("text", ["4:8", "4:8:1:2", "", "a,b", "4:8:0", "4:8:-1"])
def test_nonsense_ranges_are_refused_by_name(text):
    with pytest.raises(UsageError, match="--periods"):
        parse_range(text, what="--periods")


# --------------------------------------------------------------------------
# condition
# --------------------------------------------------------------------------


def test_creating_a_condition(library_path, capsys):
    assert run("condition", library_path, "--id", "design", "--z-origin", -4.0) == 0

    with Library.open(library_path) as library:
        (condition,) = library.conditions()
        assert condition.id == "design"
        assert condition.z_origin == pytest.approx(-4.0)
        assert np.allclose(condition.application_point, [30.0, 0.0, 2.0], atol=1e-9)

    out = capsys.readouterr().out
    assert "design" in out
    assert "application pt" in out


def test_degrees_go_in_and_slopes_are_stored(library_path):
    """The conversion happens at the very edge and nowhere else (spec 01 section 7).

    At 30 degrees rather than 5: ``sin`` and ``tan`` agree to three decimals
    at small angles, so a 5 degree case could not tell the correct conversion
    apart from the one this used to do.
    """
    assert run("condition", library_path, "--id", "heeled", "--z-origin", -4.0, "--heel", 30.0) == 0

    with Library.open(library_path) as library:
        condition = library.condition("heeled")
        assert condition.heel == pytest.approx(slope_from_degrees(30.0))
        assert condition.heel == pytest.approx(np.sin(np.radians(30.0)))
        assert condition.heel != pytest.approx(np.tan(np.radians(30.0)), abs=1e-6), "sin, not tan"
        assert condition.heel != pytest.approx(30.0), "degrees must never reach storage"


def test_there_is_no_draft_flag(library_path, capsys):
    """z_origin is not the naval draft, and they differ by wherever the origin
    sits. An unrecognised flag is a much better outcome than a silently
    different number.
    """
    with pytest.raises(SystemExit) as excinfo:
        # --z-origin supplied too, so the *only* complaint is about --draft.
        run("condition", library_path, "--z-origin", -4.0, "--draft", -4.0)
    assert excinfo.value.code == 2

    err = capsys.readouterr().err
    assert "unrecognized arguments: --draft" in err


def test_z_origin_is_required(library_path):
    with pytest.raises(SystemExit) as excinfo:
        run("condition", library_path)
    assert excinfo.value.code == 2


def test_an_id_collision_is_refused_not_overwritten(library_path, capsys):
    run("condition", library_path, "--id", "design", "--z-origin", -4.0)
    assert run("condition", library_path, "--id", "design", "--z-origin", -5.0) == 1

    assert "already used" in capsys.readouterr().err
    with Library.open(library_path) as library:
        assert library.condition("design").z_origin == pytest.approx(-4.0), "unchanged"


def test_an_out_of_domain_condition_is_refused_with_a_reason(library_path, capsys):
    """Out of domain now means the *combination*, not one extreme angle.

    Since a slope is the sine of the angle it can never itself exceed 1, so no
    single value in degrees can leave the unit disc on its own -- 60 degrees
    of heel and 60 of trim together give 0.75 + 0.75, which does.

    This used to be asserted with a heel of 89.999 degrees, which was refused
    only because ``tan`` turned it into a slope of 57295. Under ``sin`` that
    is an ordinary, if extreme, condition -- see the test below.
    """
    assert run("condition", library_path, "--z-origin", -4.0, "--heel", 60.0, "--trim", 60.0) == 1
    assert "slope" in capsys.readouterr().err


def test_an_extreme_but_real_angle_is_accepted(library_path):
    """The other side of the same change.

    A vessel at 60 degrees of heel is unusual but perfectly real, and the unit
    disc admits it. Under ``tan`` the slope came out as 1.73 and it was
    refused as out-of-domain, which made a whole range of valid conditions
    unreachable from both the CLI and the UI.
    """
    assert run("condition", library_path, "--id", "extreme", "--z-origin", -4.0, "--heel", 60.0) == 0

    with Library.open(library_path) as library:
        assert library.condition("extreme").heel == pytest.approx(np.sin(np.radians(60.0)))


def test_a_generated_id_is_used_when_none_is_given(library_path):
    assert run("condition", library_path, "--z-origin", -4.0) == 0
    with Library.open(library_path) as library:
        (condition,) = library.conditions()
        assert len(condition.id) == 32


# --------------------------------------------------------------------------
# mesh
# --------------------------------------------------------------------------


def test_adding_a_mesh(library_path, capsys):
    run("condition", library_path, "--id", "design", "--z-origin", -4.0)
    assert run("mesh", library_path, "--condition", "design", "--id", "m1", "--pct", 20, "--iterations", 5) == 0

    with Library.open(library_path) as library:
        (mesh,) = library.meshes()
        assert mesh.id == "m1"
        assert mesh.condition_id == "design"
        assert mesh.is_xz_symmetric is True

    out = capsys.readouterr().out
    assert "half vessel" in out, "a half mesh must say so, or the count reads as a bug"
    assert "reliable above" in out, "the resolution limit belongs before the solve"
    assert "per worker" in out


def test_a_mesh_for_an_unknown_condition_is_refused(library_path, capsys):
    assert run("mesh", library_path, "--condition", "ghost") == 1
    assert "no condition" in capsys.readouterr().err


def test_a_heeled_condition_produces_a_whole_hull(library_path, capsys):
    run("condition", library_path, "--id", "heeled", "--z-origin", -4.0, "--heel", 3.0)
    run("mesh", library_path, "--condition", "heeled", "--id", "m1", "--pct", 20, "--iterations", 5)

    with Library.open(library_path) as library:
        assert library.meshes()[0].is_xz_symmetric is False
    assert "half vessel" not in capsys.readouterr().out


# --------------------------------------------------------------------------
# solve
# --------------------------------------------------------------------------


@pytest.fixture
def meshed(library_path):
    run("condition", library_path, "--id", "design", "--z-origin", -4.0)
    run("mesh", library_path, "--condition", "design", "--id", "m1", "--pct", 20, "--iterations", 5)
    return library_path


def test_solving_stores_a_result(meshed, capsys):
    assert run("solve", meshed, "--mesh", "m1", "--periods", "7,9", "--directions", "0,90,180", "--id", "r1") == 0

    with Library.open(meshed) as library:
        (result,) = library.results()
        assert result.id == "r1"
        assert result.mesh_id == "m1"
        assert result.condition_id == "design", "taken from the mesh, not asked for"
        assert result.solver_name == "Capytaine"
        assert result.has_radiation and result.has_diffraction
        assert validate(library) == []

    assert "stored" in capsys.readouterr().out


def test_periods_are_converted_to_omega(meshed):
    run("solve", meshed, "--mesh", "m1", "--periods", "7,9", "--id", "r1")

    with Library.open(meshed) as library:
        stored = sorted(library.results()[0].omegas)
        assert stored == pytest.approx(sorted(2 * np.pi / np.array([7.0, 9.0])))


def test_the_cost_is_printed_before_the_solve_runs(meshed, capsys):
    run("solve", meshed, "--mesh", "m1", "--periods", "7,9", "--directions", "0,90", "--id", "r1")
    out = capsys.readouterr().out

    assert "problems        16" in out, "2 frequencies x (6 dofs + 2 directions)"
    assert "memory" in out
    assert out.index("problems") < out.index("frequency 1/"), "cost first, then the work"


def test_the_solve_order_is_stated_because_it_looks_reversed(meshed, capsys):
    """Ascending period is descending omega, and solving is frequency-major."""
    run("solve", meshed, "--mesh", "m1", "--periods", "5:9:2", "--id", "r1")
    assert "longest period first (9" in capsys.readouterr().out


def test_a_grid_beyond_the_mesh_resolution_warns(meshed, capsys):
    run("solve", meshed, "--mesh", "m1", "--periods", "1,2", "--id", "r1")
    assert "exceed this mesh's resolution" in capsys.readouterr().out


def test_physical_settings_are_echoed_and_stored(meshed, capsys):
    run("solve", meshed, "--mesh", "m1", "--periods", "8", "--depth", 50, "--speed", 1.5, "--id", "r1")

    with Library.open(meshed) as library:
        result = library.results()[0]
        assert (result.water_depth, result.forward_speed) == (50.0, 1.5)

    out = capsys.readouterr().out
    assert "depth           50.0 m" in out
    assert "1.5 m/s" in out


def test_there_is_no_rho_flag(meshed, capsys):
    """Results are stored per unit density and scaled when a database is
    delivered, so there is no density to choose at solve time. An unrecognised
    flag is a better outcome than a value that would be quietly ignored.
    """
    with pytest.raises(SystemExit) as excinfo:
        run("solve", meshed, "--mesh", "m1", "--periods", "8", "--rho", 1.025)
    assert excinfo.value.code == 2

    assert "unrecognized arguments: --rho" in capsys.readouterr().err


def test_a_radiation_only_solve_needs_no_directions(meshed):
    assert run("solve", meshed, "--mesh", "m1", "--periods", "8", "--id", "r1") == 0
    with Library.open(meshed) as library:
        result = library.results()[0]
        assert result.has_radiation is True
        assert result.has_diffraction is False


def test_a_lid_is_recorded(meshed):
    assert (
        run(
            "solve",
            meshed,
            "--mesh",
            "m1",
            "--periods",
            "8",
            "--directions",
            "0",
            "--lid",
            "below",
            "--lid-z",
            -0.2,
            "--id",
            "r1",
        )
        == 0
    )
    with Library.open(meshed) as library:
        result = library.results()[0]
        # Not "below", which is what --lid is spelled. lid_mode is a
        # LidMode, and this test used to assert the CLI's own flag value --
        # a string outside that Literal, stored with nothing to catch it.
        # It is now derived from lid_z, so the two cannot disagree.
        assert result.lid_mode == "below_free_surface"
        assert result.lid_z == pytest.approx(-0.2)


def test_an_unknown_mesh_is_refused(meshed, capsys):
    assert run("solve", meshed, "--mesh", "ghost", "--periods", "8") == 1
    assert "no mesh" in capsys.readouterr().err


def test_a_bad_period_range_is_refused_before_solving(meshed, capsys):
    assert run("solve", meshed, "--mesh", "m1", "--periods", "nonsense") == 1
    assert "--periods" in capsys.readouterr().err

    with Library.open(meshed) as library:
        assert library.results() == [], "nothing was written"


def test_an_unimplemented_lid_mode_says_so_rather_than_guessing(meshed, capsys):
    assert run("solve", meshed, "--mesh", "m1", "--periods", "8", "--lid", "auto") == 1
    assert "not implemented" in capsys.readouterr().err


# --------------------------------------------------------------------------
# The whole flow, and batching by running it again
# --------------------------------------------------------------------------


def test_three_commands_build_a_usable_library(library_path):
    """Phase 6's exit criterion: condition, mesh and solve from the command line."""
    assert run("condition", library_path, "--id", "design", "--z-origin", -4.0) == 0
    assert run("mesh", library_path, "--condition", "design", "--id", "m1", "--pct", 20, "--iterations", 5) == 0
    assert run("solve", library_path, "--mesh", "m1", "--periods", "7,9", "--directions", "0,90,180", "--id", "r1") == 0

    from pylot_db.assembly import assemble, databases

    with Library.open(library_path) as library:
        assert validate(library) == []
        (view,) = databases(library)
        assert view.usable
        assert assemble(library, view.key, rho=1.025).n_frequencies == 2


def test_batching_is_running_it_again(library_path):
    """The reason there is no grid syntax: a loop already does it, and the ids
    the caller passes in mean nothing has to be parsed back out of stdout.
    """
    for index, z_origin in enumerate((-3.0, -4.0, -5.0)):
        assert run("condition", library_path, "--id", f"d{index}", "--z-origin", z_origin) == 0
        assert (
            run("mesh", library_path, "--condition", f"d{index}", "--id", f"m{index}", "--pct", 20, "--iterations", 5)
            == 0
        )
        assert (
            run(
                "solve",
                library_path,
                "--mesh",
                f"m{index}",
                "--periods",
                "8",
                "--directions",
                "0,90,180",
                "--id",
                f"r{index}",
            )
            == 0
        )

    with Library.open(library_path) as library:
        assert len(library.conditions()) == 3
        assert validate(library) == []
        assert all(view.usable for view in __import__("pylot_db.assembly", fromlist=["databases"]).databases(library))


def test_a_missing_library_is_refused(tmp_path, capsys):
    assert main(["condition", str(tmp_path / "nope.pylot"), "--z-origin", "-4"]) == 1
    assert "does not exist" in capsys.readouterr().err


def test_a_small_mesh_does_not_report_zero_memory(meshed, capsys):
    """ "~0 MB" reads as a broken calculation rather than a small number.

    The rounding moved to :func:`pylot_bem.estimates.format_memory` when the
    application needed the same figure about the same mesh. Two copies of it
    would eventually disagree, which is exactly what ``estimates`` exists to
    prevent -- so this asserts the command line really uses the shared one.
    """
    from pylot_bem.estimates import format_memory

    run("mesh", meshed, "--condition", "design", "--id", "m2", "--pct", 20, "--iterations", 5)
    assert "~0 MB" not in capsys.readouterr().out

    assert format_memory(10) == "<1 MB"
    assert format_memory(2000) == "~128 MB"
    assert format_memory(10000) == "~3.2 GB"
