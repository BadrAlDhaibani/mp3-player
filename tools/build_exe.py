"""Build the standalone `XMB Player.exe`.

    venv/Scripts/python.exe tools/build_exe.py

Produces `dist/XMB Player/XMB Player.exe` and
`dist/XMB-Player-<version>-windows.zip`.

The version is `mp3player.__version__` and nothing else: it names the zip, it is
stamped into the exe's Windows version resource (right-click ▸ Properties ▸
Details), and it is what `QApplication.applicationVersion()` reports at runtime.
Two releases are therefore distinguishable by filename, by file properties and
from inside the running app, which was not true of any build before v1.1.0.

**One folder, not one file.** `--onefile` looks tidier and costs several seconds
on *every single launch*: it unpacks the whole ~120 MB of Qt into a temp
directory before Python starts. This app opens its audio stream and sounds a
startup swell in the first frame -- an app that sells a console boot cannot
spend four seconds before the window exists. See the decisions log in CLAUDE.md.

This is for distribution only. Development still runs the live source through
`run.bat` or the desktop shortcut: a build is 30-60 s, which would dominate the
edit-run loop if it sat in the middle of it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD = ROOT / "build"

# Run as a script, so `sys.path[0]` is `tools/` and the package is invisible.
# Importing it is safe and cheap by construction: `mp3player/__init__.py` has no
# imports of its own, precisely so that reading a version out of it cannot drag
# Qt or numpy into a build script.
sys.path.insert(0, str(ROOT))
from mp3player import __version__  # noqa: E402

NAME = "XMB Player"
ZIP_NAME = f"XMB-Player-{__version__}-windows.zip"

# The first data files this build has ever carried. They are added twice on
# purpose: `--add-data` puts them inside the bundle, where a frozen app can find
# its own licence at runtime, and `copy_licences` puts them at the top of the
# app folder, where someone who unzips a release will actually see them. The
# GPL asks that the licence travel with the binary; a copy buried in
# `_internal/` next to 400 DLLs satisfies the letter and not the point.
LICENCE_FILES = ["LICENSE", "THIRD_PARTY_NOTICES.md"]

# Third-party texts that do *not* ship themselves. Most dependencies carry their
# licence into the bundle inside their own package directory -- libsndfile's
# LGPL-2.1 arrives as `_soundfile_data/COPYING` and numpy's BSD as part of its
# dist-info -- but two do not, and both are ones whose licence requires a copy
# to travel with the binary rather than a link to it:
#
#   Qt/PySide6   LGPLv3 sec.4(b) wants the combined work accompanied by a copy of
#                *both* the LGPL and the GPL it incorporates by reference. The
#                PySide6 wheels ship only `LicenseRef-Qt-Commercial.txt`, which
#                is the other side of the dual licence and not the one in use.
#   PortAudio    MIT, and MIT asks that the notice be included in all copies.
#                The wheel ships a README and no licence file at all.
#
# Checked in rather than fetched at build time, so a release cannot depend on
# gnu.org being reachable. See THIRD_PARTY_NOTICES.md for which is which.
LICENCE_DIR = "licenses"

# We import exactly three Qt modules. PySide6_Addons brings in WebEngine, Quick,
# 3D, Charts and the rest, and PyInstaller will happily pack every one of them
# into a folder the user then has to download. Excluded by name rather than by
# uninstalling the addons package, which would break nothing today and confuse
# whoever next runs `pip install -r requirements.txt`.
EXCLUDE = [
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickControls2",
    "PySide6.QtQuickWidgets",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtGraphs",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtDesigner",
    "PySide6.QtUiTools",
    "PySide6.QtTest",
    # Nothing here is a dependency; they are just commonly installed and large.
    "tkinter",
    "matplotlib",
    "pytest",
    "IPython",
]

# soundfile and sounddevice each ship a DLL next to the package rather than
# importing it, so nothing in the bytecode points at libsndfile or PortAudio.
# `--collect-binaries` is what walks the package directory and finds them; leave
# them out and the build succeeds and the exe dies on the first import.
COLLECT_BINARIES = ["soundfile", "sounddevice"]


def human_size(path: Path) -> str:
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return f"{total / 1e6:.0f} MB"


def version_quad() -> tuple[int, int, int, int]:
    """`"1.1.0"` -> `(1, 1, 0, 0)`.

    A Windows version resource is four 16-bit integers and will not take
    anything else, so a pre-release suffix (`1.2.0rc1`) is truncated to the
    numeric run rather than crashing the build. The *string* fields below keep
    the real value, which is the one anyone reads.
    """
    parts: list[int] = []
    for chunk in __version__.split(".")[:4]:
        digits = ""
        for char in chunk:
            if not char.isdigit():
                break
            digits += char
        parts.append(int(digits) if digits else 0)
    while len(parts) < 4:
        parts.append(0)
    return parts[0], parts[1], parts[2], parts[3]


def write_version_resource(folder: Path) -> Path:
    """Write the `VSVersionInfo` literal PyInstaller's `--version-file` wants.

    Generated rather than checked in, so it cannot drift from `__version__`.
    It lives in a temp directory rather than in `build/`, because `--clean`
    empties the work path and this file has to survive until PyInstaller reads
    it.
    """
    major, minor, patch, extra = version_quad()
    quad = f"({major}, {minor}, {patch}, {extra})"
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={quad},
    prodvers={quad},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', ''),
        StringStruct('FileDescription', 'XMB Player'),
        StringStruct('FileVersion', '{__version__}'),
        StringStruct('InternalName', '{NAME}'),
        StringStruct('LegalCopyright',
                     'Copyright (C) 2026 Badr Al-Dhaibani. GPL-2.0-or-later.'),
        StringStruct('OriginalFilename', '{NAME}.exe'),
        StringStruct('ProductName', 'XMB Player'),
        StringStruct('ProductVersion', '{__version__}'),
      ]),
    ]),
    # 0x0409 is en-US, 1200 is the UTF-16 codepage -- and it must agree with
    # the '040904B0' above or Windows shows the properties tab empty.
    VarFileInfo([VarStruct('Translation', [0x0409, 1200])]),
  ],
)
"""
    path = folder / "version_info.txt"
    path.write_text(text, encoding="utf-8")
    return path


def copy_licences(folder: Path) -> None:
    """Put the licence files where someone who unzips a release will see them."""
    for name in LICENCE_FILES:
        shutil.copy2(ROOT / name, folder / name)
    shutil.copytree(ROOT / LICENCE_DIR, folder / LICENCE_DIR, dirs_exist_ok=True)


def build(version_file: Path) -> Path:
    for stale in (BUILD, DIST / NAME):
        if stale.exists():
            shutil.rmtree(stale)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        # No console window. `run.bat` is the launcher that has one, and it runs
        # the source rather than this.
        "--windowed",
        "--name",
        NAME,
        "--distpath",
        str(DIST),
        "--workpath",
        str(BUILD),
        "--specpath",
        str(BUILD),
        "--version-file",
        str(version_file),
    ]
    for module in EXCLUDE:
        command += ["--exclude-module", module]
    for package in COLLECT_BINARIES:
        command += ["--collect-binaries", package]
    for name in LICENCE_FILES:
        # `os.pathsep` is what PyInstaller splits on, so it is the separator
        # rather than a hardcoded ";" that happens to be right on Windows.
        command += ["--add-data", f"{ROOT / name}{os.pathsep}."]
    command += ["--add-data", f"{ROOT / LICENCE_DIR}{os.pathsep}{LICENCE_DIR}"]
    command.append(str(ROOT / "mp3player" / "app.py"))

    print("  ".join(command[:6]), "...\n")
    started = time.monotonic()
    subprocess.run(command, check=True, cwd=ROOT)
    print(f"\nbuilt in {time.monotonic() - started:.0f}s")
    return DIST / NAME


def zip_up(folder: Path) -> Path:
    archive = DIST / ZIP_NAME
    archive.unlink(missing_ok=True)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for item in sorted(folder.rglob("*")):
            if item.is_file():
                # Rooted at the app folder, so unzipping gives you one folder
                # and not a hundred loose DLLs wherever you happened to be.
                bundle.write(item, Path(NAME) / item.relative_to(folder))
    return archive


def main() -> int:
    print(f"XMB Player {__version__}\n")

    # Stale zips from earlier versions would otherwise pile up in dist/ and
    # `XMB-Player-1.0.0-windows.zip` sitting next to `1.1.0` is exactly the
    # confusion the version stamp exists to end.
    for old in DIST.glob("XMB-Player-*windows.zip"):
        if old.name != ZIP_NAME:
            print(f"removing stale {old.name}")
            old.unlink()

    with tempfile.TemporaryDirectory(prefix="xmb-build-") as scratch:
        folder = build(write_version_resource(Path(scratch)))

    exe = folder / f"{NAME}.exe"
    if not exe.is_file():
        print(f"no exe at {exe}")
        return 1

    copy_licences(folder)

    archive = zip_up(folder)
    print(f"\n  {exe}    ({human_size(folder)} unpacked)")
    print(f"  {archive}    ({archive.stat().st_size / 1e6:.0f} MB zipped)")
    print("\nRun it once before shipping it -- a missing DLL only shows up then.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
