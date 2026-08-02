"""Render one animation as a filmstrip, on the real platform, and look at it.

    venv/Scripts/python.exe tools/filmstrip.py out.png            # a row step
    venv/Scripts/python.exe tools/filmstrip.py out.png --what bar
    venv/Scripts/python.exe tools/filmstrip.py out.png --ms 190 --curve OutQuad

The other half of `shell_harness.py`. That one asserts where things come to
rest; this one shows what happens on the way, which is the part no assertion
has ever caught. Frames are evenly spaced through the tween with its clock
driven by hand -- never by sleeping -- and tiled top to bottom with the time on
each, so the question "is this duration doing anything" is answered by whether
consecutive frames differ.

It found the Batch 6 easing numbers: a single row step was still travelling at
54 ms and pixel-identical from 81 ms to 190, which is how 190 became 140.

Deliberately *not* offscreen -- it needs the real font database, and it is for
looking at rather than for asserting on. `--curve` and `--ms` override the
theme so an alternative can be rendered and compared without editing anything.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QEasingCurve, QRect  # noqa: E402
from PySide6.QtGui import QColor, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from mp3player.core import settings as settings_mod  # noqa: E402
from mp3player.core.audio.engine import AudioEngine  # noqa: E402
from mp3player.ui import theme  # noqa: E402
from mp3player.ui.controller import PlayerController  # noqa: E402
from mp3player.ui.main_window import CAT_MUSIC, CAT_SETTINGS, MainWindow  # noqa: E402

BAND_ABOVE, BAND_HEIGHT = 110, 300  # the crop, around the crossbar row


def frames(window, app, tween, start, count):
    """`count` frames evenly spaced through `tween`, cropped to the band."""
    band = QRect(0, max(0, window.stage.column.row_y() - BAND_ABOVE),
                 window.width(), BAND_HEIGHT)
    start()
    shots = []
    for index in range(count):
        at = round(index * tween.duration() / (count - 1))
        tween.setCurrentTime(at)
        app.processEvents()
        shots.append((at, window.grab().copy(band)))
    return shots


def tile(shots, path: Path) -> None:
    width, height = shots[0][1].width(), shots[0][1].height()
    sheet = QPixmap(width, height * len(shots))
    sheet.fill(QColor(0, 0, 0))

    painter = QPainter(sheet)
    for row, (at, shot) in enumerate(shots):
        painter.drawPixmap(0, row * height, shot)
        painter.setPen(QColor(255, 220, 120))
        painter.drawText(8, row * height + 16, f"{at} ms")
        painter.setPen(QColor(255, 255, 255, 60))
        painter.drawLine(0, row * height, width, row * height)
    painter.end()

    sheet.save(str(path))
    print(f"wrote {path}  ({sheet.width()}x{sheet.height()}, {len(shots)} frames)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", nargs="?", default="filmstrip.png")
    parser.add_argument("--what", choices=("item", "bar", "appear"), default="item")
    parser.add_argument("--step", type=int, default=1, help="rows to travel")
    parser.add_argument("--frames", type=int, default=8)
    parser.add_argument("--ms", type=int, help="override the theme's duration")
    parser.add_argument("--curve", help="a QEasingCurve.Type name, e.g. OutQuad")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    saved = settings_mod.load()
    # Silent: this renders pictures, and the startup swell is not one of them.
    engine = AudioEngine(volume=0.0, speed=saved.speed)
    engine.start()
    controller = PlayerController(engine, saved)
    window = MainWindow(controller)
    window.resize(*theme.WINDOW_DEFAULT)
    window.show()
    controller.start()
    app.processEvents()

    stage = window.stage
    bar, column = stage.bar, stage.column
    for tween in (bar._slide, column._slide, column._arrival, stage.page._arrival):
        if args.curve:
            tween.setEasingCurve(getattr(QEasingCurve, args.curve))
        if args.ms:
            tween.setDuration(args.ms)

    bar.set_index(CAT_MUSIC)
    bar.settle()
    column.settle()
    app.processEvents()

    if args.what == "item":
        target = min(args.step, max(0, column.count - 1))
        shots = frames(window, app, column._slide,
                       lambda: (column.set_index(0), column.set_index(target)),
                       args.frames)
    elif args.what == "bar":
        shots = frames(window, app, bar._slide,
                       lambda: bar.set_index(CAT_SETTINGS), args.frames)
    else:
        shots = frames(window, app, column._arrival, column.enter, args.frames)

    tile(shots, Path(args.out))

    # Never write settings from a tool that only renders pictures.
    controller._save_now = lambda: None
    controller.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
