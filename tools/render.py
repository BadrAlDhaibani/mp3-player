"""Render a screen at one or more speeds, on the real platform, and look at it.

    venv/Scripts/python.exe tools/render.py out.png
    venv/Scripts/python.exe tools/render.py out.png --what music --size 720x480
    venv/Scripts/python.exe tools/render.py out.png --what now --speed 1.30
    venv/Scripts/python.exe tools/render.py out.png --what settings --select 2
    venv/Scripts/python.exe tools/render.py out.png --theme all

The third leg of the stool. `shell_harness.py` asserts where things come to
rest, `filmstrip.py` shows what happens on the way, and this shows what a screen
actually *looks like* — which is the only thing that has ever caught a colour or
a width problem, because the offscreen harness has no font database and no
opinion about whether anything reads.

Deliberately *not* offscreen: it needs the real fonts, and it is for looking at
rather than asserting on. `--speed` and `--theme` may both be given more than
once (speed defaults to daycore / 1.00x / nightcore, theme to whatever is saved),
and the frames are stacked theme-major with both written on each — the accent
and the wave both track the slider, so most questions about either are really
questions about several frames side by side. `--theme all` is every preset.

It found the Batch 9 bug: at daycore the *selected* row's artist was fainter
than the unselected ones around it, because a saturated blue at V=1.0 is darker
to the eye than a cyan at V=1.0. Every one of the 178 checks passed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtGui import QColor, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from mp3player.core import settings as settings_mod  # noqa: E402
from mp3player.core.audio.engine import AudioEngine  # noqa: E402
from mp3player.ui import theme  # noqa: E402
from mp3player.ui.controller import PlayerController  # noqa: E402
from mp3player.ui.main_window import (  # noqa: E402
    CAT_MUSIC,
    CAT_NOW,
    CAT_SETTINGS,
    MainWindow,
)

CATEGORIES = {"now": CAT_NOW, "music": CAT_MUSIC, "settings": CAT_SETTINGS}
DEFAULT_SPEEDS = (settings_mod.DAYCORE_SPEED, 1.0, settings_mod.NIGHTCORE_SPEED)


def label_for(speed: float) -> str:
    if abs(speed - settings_mod.DAYCORE_SPEED) < 1e-6:
        return f"daycore  {speed:.2f}x"
    if abs(speed - settings_mod.NIGHTCORE_SPEED) < 1e-6:
        return f"nightcore  {speed:.2f}x"
    return f"{speed:.2f}x"


def stack(shots, path: Path) -> None:
    """One frame per speed, top to bottom, each captioned. Same idea as the
    filmstrip: the comparison is the point, so they go in one file."""
    width, height = shots[0][1].width(), shots[0][1].height()
    sheet = QPixmap(width, height * len(shots))
    sheet.fill(QColor(0, 0, 0))

    painter = QPainter(sheet)
    for row, (label, shot) in enumerate(shots):
        painter.drawPixmap(0, row * height, shot)
        painter.setPen(QColor(255, 220, 120))
        painter.drawText(10, row * height + 18, label)
        painter.setPen(QColor(255, 255, 255, 70))
        painter.drawLine(0, row * height, width, row * height)
    painter.end()

    sheet.save(str(path))
    print(f"wrote {path}  ({sheet.width()}x{sheet.height()}, {len(shots)} frame(s))")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", nargs="?", default="render.png")
    parser.add_argument("--what", choices=tuple(CATEGORIES), default="music")
    parser.add_argument("--size", default="x".join(str(n) for n in theme.WINDOW_DEFAULT))
    parser.add_argument(
        "--speed",
        type=float,
        action="append",
        help="repeatable; defaults to daycore, 1.00x and nightcore",
    )
    parser.add_argument(
        "--theme",
        action="append",
        help="repeatable; a preset name or `all`. Defaults to the saved one.",
    )
    parser.add_argument(
        "--select", type=int, default=4, help="which row to put the cursor on"
    )
    parser.add_argument(
        "--step",
        action="store_true",
        help="step into the selected settings row, so the outline shows",
    )
    parser.add_argument(
        "--play", action="store_true", default=True,
        help="load a track, so the marker and the transport have something to say",
    )
    args = parser.parse_args()

    width, height = (int(n) for n in args.size.lower().split("x"))
    speeds = args.speed or list(DEFAULT_SPEEDS)
    themes = args.theme or []
    if any(name.lower() == "all" for name in themes):
        themes = list(theme.palette_names())

    app = QApplication(sys.argv)
    saved = settings_mod.load()
    # Silent: this renders pictures, and the startup swell is not one of them.
    engine = AudioEngine(volume=0.0, speed=saved.speed)
    engine.start()
    controller = PlayerController(engine, saved)
    # Never write settings from a tool that only renders pictures. Set before
    # anything can trigger a save, not after.
    controller._save_now = lambda: None

    window = MainWindow(controller)
    window.resize(width, height)
    window.show()
    controller.start()
    app.processEvents()

    stage = window.stage
    # `set_index` drives `_on_category` through the crossbar's signal, so the
    # window rebuilds the column itself -- no need to poke at its state.
    stage.bar.set_index(CATEGORIES[args.what])
    app.processEvents()
    stage.bar.settle()
    stage.column.settle()
    stage.page.settle()
    app.processEvents()

    if args.play and controller.tracks:
        controller.play_index(0)
        if args.what != "now":
            stage.column.set_index(max(0, min(args.select, stage.column.count - 1)))
            stage.column.settle()
        app.processEvents()

    if args.step and args.what == "settings":
        # Through `activate` rather than by setting the flag, so this renders
        # the state the app actually reaches rather than one arranged for it.
        stage.column.activate()
        app.processEvents()

    shots = []
    # Theme-major: the interesting comparison down a column is one palette
    # travelling, and the interesting one between blocks is the same speed in a
    # different palette. `themes` empty means "leave whatever is saved alone",
    # which is the single-palette case and captions itself with the name anyway.
    for name in themes or [theme.palette().name]:
        controller.set_theme(name)
        for speed in speeds:
            controller.set_speed(speed)
            # The wave runs on its own timer, so give it turns to catch up
            # rather than grabbing mid-frame.
            for _ in range(4):
                app.processEvents()
            caption = f"{theme.palette().name}  ·  {label_for(speed)}"
            shots.append((caption, window.grab()))

    stack(shots, Path(args.out))

    controller.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
