"""Fixtures for the pylot-bem tests.

The geometry lives in ``hull.py`` next door, uniquely named on purpose:
the tests directories are on sys.path so shared modules can be imported
under ``--import-mode=importlib``, and two packages both exposing a module
called ``conftest`` shadow each other.
"""

import os

import pytest

from hull import load_tanker, make_base_shape

# Before anything imports Qt. The application tests build real windows, real
# VTK render windows and real property panes -- they are not mocked, because a
# widget test that never instantiates the widget cannot catch a renamed
# objectName, which is the failure this whole arrangement exists to catch.
#
# ``setdefault`` so a developer can watch them: QT_QPA_PLATFORM= runs on screen.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    """One QApplication for the whole session. Qt permits exactly one."""
    from PySide6.QtWidgets import QApplication

    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture
def boxboat():
    """The full, symmetric boxboat."""
    return make_base_shape()


@pytest.fixture
def asymmetric_boxboat():
    """The same geometry, declared asymmetric, so symmetry is never used."""
    return make_base_shape(is_xz_symmetric=False)


@pytest.fixture(scope="session")
def tanker():
    """A real hull, declared symmetric though its mesh is not precisely so."""
    return load_tanker()


@pytest.fixture(scope="session")
def asymmetric_tanker():
    """The same hull, declared asymmetric, so the whole form is meshed."""
    return load_tanker(is_xz_symmetric=False)
