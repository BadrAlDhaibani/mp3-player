"""Render a screen at one or more speeds, on the real platform, and look at it.

    venv/Scripts/python.exe tools/render.py out.png
    venv/Scripts/python.exe tools/render.py out.png --what music --size 720x480
    venv/Scripts/python.exe tools/render.py out.png --what now --speed 1.30
    venv/Scripts/python.exe tools/render.py out.png --what settings --select 2
    venv/Scripts/python.exe tools/render.py out.png --theme all
    venv/Scripts/python.exe tools/render.py out.png --status "Could not save settings"
    venv/Scripts/python.exe tools/render.py out.png --what now --shuffle --repeat one
    venv/Scripts/python.exe tools/render.py out.png --find tetris
    venv/Scripts/python.exe tools/render.py out.png --marks

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

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from mp3player.core import fetch
from mp3player.core import settings as settings_mod
from mp3player.core.audio.engine import AudioEngine
from mp3player.ui import marks as marks_mod
from mp3player.ui import theme
from mp3player.ui.controller import REPEAT_MODES, PlayerController
from mp3player.ui.main_window import (
    CAT_GET,
    CAT_MUSIC,
    CAT_NOW,
    CAT_SETTINGS,
    MainWindow,
)

CATEGORIES = {
    "now": CAT_NOW,
    "music": CAT_MUSIC,
    "settings": CAT_SETTINGS,
    "get": CAT_GET,
}
DEFAULT_SPEEDS = (settings_mod.DAYCORE_SPEED, 1.0, settings_mod.NIGHTCORE_SPEED)


def label_for(speed: float) -> str:
    if abs(speed - settings_mod.DAYCORE_SPEED) < 1e-6:
        return f"daycore  {speed:.2f}x"
    if abs(speed - settings_mod.NIGHTCORE_SPEED) < 1e-6:
        return f"nightcore  {speed:.2f}x"
    return f"{speed:.2f}x"


def stack(shots, path: Path, across: bool = False, caption: bool = True) -> None:
    """One frame per speed, top to bottom, each captioned. Same idea as the
    filmstrip: the comparison is the point, so they go in one file.

    `across` lays them left to right instead, and `caption` turns off the label
    and the divider. Both are for shots that end up somewhere other than in
    front of whoever rendered them -- a caption is an affordance for looking at
    a comparison, and it reads as tool output on a page."""
    width, height = shots[0][1].width(), shots[0][1].height()
    n = len(shots)
    sheet = QPixmap(width * n, height) if across else QPixmap(width, height * n)
    sheet.fill(QColor(0, 0, 0))

    painter = QPainter(sheet)
    for row, (label, shot) in enumerate(shots):
        x, y = (row * width, 0) if across else (0, row * height)
        painter.drawPixmap(x, y, shot)
        if caption:
            painter.setPen(QColor(255, 220, 120))
            painter.drawText(x + 10, y + 18, label)
            painter.setPen(QColor(255, 255, 255, 70))
            if across:
                painter.drawLine(x, 0, x, height)
            else:
                painter.drawLine(0, y, width, y)
    painter.end()

    sheet.save(str(path))
    print(f"wrote {path}  ({sheet.width()}x{sheet.height()}, {len(shots)} frame(s))")


# -- the candidate sheet ---------------------------------------------------
#
# `--marks` answers a different question from the rest of this tool: not "does
# this screen read" but "which of these should the screen have". It needs no
# controller, no engine and no window -- only the real fonts, so the current
# glyphs can be set beside the drawings and compared for weight.

MARK_CELL = 88  # the crossbar's own text box height, so a glyph is at true scale
MARK_ZOOM = 2
MARK_LABEL_W = 168


def _mark_cell(size: float, ink: QColor, draw=None, glyph: str = "") -> QImage:
    """One mark or one glyph, drawn the way `_paint_category` draws it."""
    image = QImage(MARK_CELL, MARK_CELL, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)
    painter.setPen(ink)
    if draw is not None:
        offset = (MARK_CELL - size) / 2
        draw(painter, QRectF(offset, offset, size, size))
    else:
        painter.setFont(theme.font(round(size), family=theme.GLYPH_FAMILY))
        painter.drawText(QRectF(0, 0, MARK_CELL, MARK_CELL), Qt.AlignCenter, glyph)
    painter.end()
    return image


def marks_sheet(path: Path) -> None:
    """Every mark at both real sizes, blown up, over the real background.

    The two sizes are the only two that matter: `CATEGORY_ICON_SMALL` is what
    every unselected category wears and `CATEGORY_ICON` is the selection, and
    the whole reason the app icon has a second drawing below 24 px is that a
    mark can be fine at one and mush at the other. Nearest-neighbour on the
    blow-up, so what is on screen is what is in the file rather than what a
    smooth scale wishes were there.
    """
    # Each mark beside the glyph it replaced. The comparison outlived the choice
    # it was built for: the glyphs are what the marks have to hold their weight
    # against, so this stays the sheet to look at after touching any of them.
    rows = [
        ("Now Playing  ·  was ▶", None, "▶"),
        ("Now Playing  ·  painted", marks_mod.draw_play, ""),
        ("Music  ·  was ♪", None, "♪"),
        ("Music  ·  painted", marks_mod.draw_note, ""),
        ("Settings  ·  was ⚙", None, "⚙"),
        ("Settings  ·  painted", marks_mod.draw_settings, ""),
        # The fourth category has no glyph it replaced -- it never had one. It
        # is on the sheet for the comparison that outlived the choice: its
        # weight has to hold against the three above it.
        ("Get Music  ·  painted", marks_mod.draw_get, ""),
    ]

    zoomed = MARK_CELL * MARK_ZOOM
    gap = 16
    width = MARK_LABEL_W + (MARK_CELL + zoomed) * 2 + gap * 5
    height = len(rows) * (zoomed + gap) + gap

    sheet = QPixmap(width, height)
    # The colour the window actually has on the crossbar row: `CROSSBAR_Y_RATIO`
    # is 0.44 and `background_brush` puts BG_MID at 0.45, so the row sits within
    # a hair of it. Filling with the whole gradient instead would run the bottom
    # rows out into BG_BOTTOM and compare marks against different backgrounds.
    sheet.fill(theme.BG_MID)

    painter = QPainter(sheet)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
    for row, (label, draw, glyph) in enumerate(rows):
        y = gap + row * (zoomed + gap)
        painter.setPen(theme.TEXT_DIM)
        painter.setFont(theme.font(14))
        painter.drawText(QRectF(gap, y, MARK_LABEL_W, zoomed), Qt.AlignVCenter, label)

        x = MARK_LABEL_W + gap * 2
        # Unfocused takes TEXT_FAINT and focused takes TEXT -- the two ends of
        # the mix `_paint_category` runs, so these are the real colours and not
        # an approximation of them.
        for size, ink in (
            (theme.CATEGORY_ICON_SMALL, theme.TEXT_FAINT),
            (theme.CATEGORY_ICON, theme.TEXT),
        ):
            cell = QPixmap.fromImage(_mark_cell(size, ink, draw, glyph))
            painter.drawPixmap(x, y + (zoomed - MARK_CELL) // 2, cell)
            x += MARK_CELL + gap
            painter.drawPixmap(
                x, y, cell.scaled(zoomed, zoomed, Qt.IgnoreAspectRatio, Qt.FastTransformation)
            )
            x += zoomed + gap

    painter.setPen(QColor(255, 220, 120))
    painter.setFont(theme.font(13))
    painter.drawText(
        QRect(MARK_LABEL_W + gap * 2, 2, width, 14),
        Qt.AlignLeft,
        f"{theme.CATEGORY_ICON_SMALL} px (unfocused)"
        f"{' ' * 44}{theme.CATEGORY_ICON} px (focused)",
    )
    painter.end()

    sheet.save(str(path))
    print(f"wrote {path}  ({sheet.width()}x{sheet.height()}, {len(rows)} mark(s))")


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
        "--status",
        help="put a message on the status line -- the one place a sentence from "
             "somewhere else lands, and the one drawn in the small font",
    )
    parser.add_argument(
        "--play", action="store_true", default=True,
        help="load a track, so the marker and the transport have something to say",
    )
    parser.add_argument(
        "--track", type=int, default=0,
        help="which track to load. Worth setting when the cover is in the shot: "
             "most of a real library is untagged and draws the note glyph.",
    )
    parser.add_argument(
        "--volume", type=float, default=0.0,
        help="0 by default, because this renders pictures and the startup swell "
             "is not one of them. Raise it when the readout is in the shot -- "
             "`VOL 0%%` with the slider pinned left looks like a broken build.",
    )
    parser.add_argument(
        "--shuffle", action="store_true",
        help="turn shuffle on, so the lit button and the Now Playing tail are "
             "in the shot",
    )
    parser.add_argument(
        "--repeat", choices=REPEAT_MODES,
        help="the repeat mode. `all` is the default and says nothing on the "
             "page; `one` and `off` are the two that do",
    )
    parser.add_argument(
        "--find",
        help="open the Music search and type this. The query is unbounded text "
             "sitting next to a track list, so it wants looking at long, at one "
             "match and at none.",
    )
    parser.add_argument(
        "--get",
        help="with `--what get`, put this in the query line. Nothing is "
             "searched -- there is no network in here -- so the results come "
             "from `--results` below and this is only the header.",
    )
    parser.add_argument(
        "--results", type=int, default=0,
        help="with `--what get`, how many stand-in results to list. The point "
             "of the shot is the row layout in 280 px, not what the rows say.",
    )
    parser.add_argument(
        "--marks", action="store_true",
        help="the category marks at both real sizes, beside the glyphs they "
             "replaced. Opens no audio device and builds no window -- it is a "
             "question about three drawings, not about a screen.",
    )
    parser.add_argument(
        "--across", action="store_true",
        help="lay the frames left to right instead of stacking them",
    )
    parser.add_argument(
        "--no-caption", action="store_true",
        help="drop the speed/theme label and the divider -- for a shot that ends "
             "up on a page rather than in front of you",
    )
    args = parser.parse_args()

    width, height = (int(n) for n in args.size.lower().split("x"))
    speeds = args.speed or list(DEFAULT_SPEEDS)
    themes = args.theme or []
    if any(name.lower() == "all" for name in themes):
        themes = list(theme.palette_names())

    app = QApplication(sys.argv)

    if args.marks:
        marks_sheet(Path(args.out))
        return 0

    saved = settings_mod.load()
    # Silent by default: this renders pictures, and the startup swell is not one
    # of them. `--volume` is for when the transport's readout is in the shot.
    engine = AudioEngine(volume=args.volume, speed=saved.speed)
    engine.start()
    controller = PlayerController(engine, saved)
    # Never write settings from a tool that only renders pictures. Set before
    # anything can trigger a save, not after.
    controller._save_now = lambda: None

    window = MainWindow(controller)
    window.resize(width, height)
    window.show()
    controller.start()
    # After `start`, which emits the saved values -- these have to be the last
    # word or a shot asked for `--repeat one` would render whatever was saved.
    controller.set_shuffle(args.shuffle)
    controller.set_repeat(args.repeat or saved.repeat)
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
        controller.play_index(max(0, min(args.track, len(controller.tracks) - 1)))
        if args.what != "now":
            stage.column.set_index(max(0, min(args.select, stage.column.count - 1)))
            stage.column.settle()
        app.processEvents()

    if args.find is not None and args.what == "music":
        # Through the same two calls a keypress makes, rather than by setting
        # the flag and the string -- this renders the state the app reaches.
        window._begin_search()
        window._set_query(args.find)
        # Re-applied, because typing puts the cursor back on the top match --
        # and a shot with rows *above* the header is the one that says whether
        # the list is really clipped below it.
        stage.column.set_index(max(0, min(args.select, stage.column.count - 1)))
        stage.column.settle()
        app.processEvents()

    if args.what == "get":
        # Stand-in results rather than a real search: this tool opens no socket,
        # and the question a shot of this screen answers is whether a title and
        # a right-aligned duration survive 280 px -- which is a layout question
        # and does not care what the rows say. Titles run long on purpose, since
        # a YouTube title is the least bounded string the app has ever drawn.
        window._results = [
            fetch.Result(
                video_id=f"id{n}",
                title=f"{n + 1}. Extended Nightcore Mix (Full Album, HQ Remaster)",
                uploader="A Channel With A Fairly Long Name",
                duration_s=225 + n * 47,
            )
            for n in range(max(0, args.results))
        ]
        window._get_query = args.get or ""
        window._refresh_column(reset=True)
        stage.column.set_index(max(0, min(args.select, stage.column.count - 1)))
        stage.column.settle()
        app.processEvents()

    if args.step and args.what == "settings":
        # Through `activate` rather than by setting the flag, so this renders
        # the state the app actually reaches rather than one arranged for it.
        stage.column.activate()
        app.processEvents()

    if args.status:
        stage.set_status(args.status)
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

    stack(shots, Path(args.out), across=args.across, caption=not args.no_caption)

    controller.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
