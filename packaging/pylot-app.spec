# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the standalone application (docs/README.md).

    uv run pyinstaller packaging/pylot-app.spec --noconfirm

Produces ``dist/pylot/pylot.exe`` -- a folder build (COLLECT), not one file:
onefile self-extracts to a temp dir on every launch, which is a slow start
for an app this size and a needless flag for antivirus. Zip the folder to
distribute it.

Capytaine and pymeshup both ship compiled extensions that PyInstaller's
static analysis cannot see on its own -- capytaine picks its Fortran core at
runtime with ``importlib.import_module(f"...Delhommeau_{precision}")``
(``capytaine/green_functions/delhommeau.py``), a string PyInstaller never
evaluates. ``collect_all`` pulls each package in whole -- code, compiled
extensions and data -- rather than hand-listing hidden imports: a hand-listed
set from an older capytaine (capytaine/capytaine#324) is already stale, naming
``green_functions.libs.XieDelhommeau_*`` modules that do not exist in 2.3+,
because ``XieDelhommeau`` there is a plain subclass of ``Delhommeau`` reusing
its compiled core.

VTK and PySide6 need no such treatment: PyInstaller carries a PySide6 hook
itself, and ``pyinstaller-hooks-contrib`` (installed alongside pyinstaller,
see the ``build`` dependency group) carries one per ``vtkmodules`` submodule.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).parent

datas = []
binaries = []
hiddenimports = []
for package in ("capytaine", "pymeshup"):
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

a = Analysis(
    [str(ROOT / "packaging" / "run_app.py")],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={
        # The application embeds VTK for 3D, not a matplotlib Qt canvas, but
        # the Inspect tab's plot is matplotlib (pyproject.toml) -- only the
        # Qt backend it actually uses, not every backend capytaine's own spec
        # pulled in for an interactive IPython session.
        "matplotlib": {"backends": ["QtAgg"]},
    },
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="pylot",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="pylot",
)
