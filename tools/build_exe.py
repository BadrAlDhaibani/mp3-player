"""Build the standalone `XMB Player.exe`.

    venv/Scripts/python.exe tools/build_exe.py

Produces `dist/XMB Player/XMB Player.exe` and `dist/XMB-Player-windows.zip`.

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

import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD = ROOT / "build"

NAME = "XMB Player"
ZIP_NAME = "XMB-Player-windows.zip"

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


def build() -> Path:
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
    ]
    for module in EXCLUDE:
        command += ["--exclude-module", module]
    for package in COLLECT_BINARIES:
        command += ["--collect-binaries", package]
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
    folder = build()
    exe = folder / f"{NAME}.exe"
    if not exe.is_file():
        print(f"no exe at {exe}")
        return 1

    archive = zip_up(folder)
    print(f"\n  {exe}    ({human_size(folder)} unpacked)")
    print(f"  {archive}    ({archive.stat().st_size / 1e6:.0f} MB zipped)")
    print("\nRun it once before shipping it -- a missing DLL only shows up then.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
