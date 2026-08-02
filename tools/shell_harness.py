"""Offscreen exercise of the XMB shell. Real engine, no display, no pytest.

    venv/Scripts/python.exe tools/shell_harness.py

`tests/` is core-only by convention -- no display needed, no Qt. This is the
other half: it drives the actual widgets through synthesised key and mouse
events and asserts on what the shell did, which is the only way to catch a
crossbar and an item column quietly fighting over the same pixels.

It never writes settings. The folder it opens for the empty-library case is
passed with `remember=False`, and volume and speed are put back before the
controller flushes on shutdown.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent, QMouseEvent  # noqa: E402
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

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASSED if condition else FAILED).append(name)
    mark = "ok" if condition else "XX"
    print(f"  [{mark}] {name}{'  -- ' + detail if detail else ''}")


def press(window: MainWindow, code: Qt.Key, mods=Qt.NoModifier) -> None:
    window.keyPressEvent(QKeyEvent(QEvent.KeyPress, code, mods))


def _mouse(kind, x: int, y: int, button=Qt.LeftButton) -> QMouseEvent:
    point = QPointF(x, y)
    return QMouseEvent(kind, point, point, button, button, Qt.NoModifier)


def click(stage, x: int, y: int) -> None:
    stage.mousePressEvent(_mouse(QEvent.MouseButtonPress, x, y))


def drag(stage, x: int, y: int) -> None:
    """Press, move and release on the same spot -- enough to drive a slider."""
    stage.mousePressEvent(_mouse(QEvent.MouseButtonPress, x, y))
    stage.mouseMoveEvent(_mouse(QEvent.MouseMove, x, y))
    stage.mouseReleaseEvent(_mouse(QEvent.MouseButtonRelease, x, y, Qt.NoButton))


def main() -> int:
    app = QApplication(sys.argv)
    saved = settings_mod.load()

    engine = AudioEngine(volume=saved.volume, speed=saved.speed)
    engine.start()
    print(f"stream: {engine.sample_rate} Hz")

    controller = PlayerController(engine, saved)
    window = MainWindow(controller)
    window.resize(980, 640)
    window.show()
    controller.start()
    app.processEvents()

    stage = window.stage
    bar, column, transport = stage.bar, stage.column, window.transport

    if not controller.tracks:
        print("no playable tracks in the saved folder -- nothing to drive")
        controller.shutdown()
        return 1

    page = stage.page

    print("\n-- structure")
    check("starts on Now Playing", bar.index == CAT_NOW)
    check("now playing shows the page, not a list", page.isVisible() and not column.isVisible())
    check("transport has no speed control", not hasattr(transport, "speed"))
    check("paints", not window.grab().isNull())

    print("\n-- crossbar nav")
    press(window, Qt.Key_Right)
    check("right -> Music", bar.index == CAT_MUSIC)
    press(window, Qt.Key_Right)
    check("right -> Settings", bar.index == CAT_SETTINGS)
    check("settings column built, no presets", column.count == 4)
    press(window, Qt.Key_Right)
    check("clamps at the last category", bar.index == CAT_SETTINGS)
    press(window, Qt.Key_Backspace)
    check("backspace steps left", bar.index == CAT_MUSIC)
    check("music column mirrors the library", column.count == len(controller.tracks))

    print("\n-- item nav")
    press(window, Qt.Key_Down)
    press(window, Qt.Key_Down)
    check("down moves the cursor", column.index == 2, f"index={column.index}")
    press(window, Qt.Key_Up)
    check("up moves back", column.index == 1)
    press(window, Qt.Key_End)
    check("End -> last item", column.index == column.count - 1)
    press(window, Qt.Key_Home)
    check("Home -> first item", column.index == 0)
    press(window, Qt.Key_Up)
    check("clamps at the top", column.index == 0)

    print("\n-- the cursor is remembered per category")
    for _ in range(3):
        press(window, Qt.Key_Down)
    music_at = column.index
    press(window, Qt.Key_Right)
    check("settings opens on its own cursor", column.index == 0)
    press(window, Qt.Key_Left)
    check("music cursor restored", column.index == music_at, f"{column.index}")

    print("\n-- geometry: the selection never moves")
    row = column.row_y()
    check("selected item sits on the crossbar row", column._item_y(column.index) == row)
    check("bar and column agree on the row", bar.row_y() == row)
    check("column hit-test finds the selection", column.hit(QPoint(400, row)) == column.index)
    check("column ignores the icon gutter", column.hit(QPoint(40, row)) is None)
    check("bar stops short of the column", bar.hit(QPoint(400, row)) is None)
    check("bar finds the active category", bar.hit(QPoint(theme.FOCUS_X, row)) == bar.index)
    furthest = theme.FOCUS_X + (len(window.stage.bar._categories) - 1) * theme.CATEGORY_SPACING
    check(
        "the last category clears the item column",
        furthest + theme.CATEGORY_ICON_SMALL // 2 < theme.ITEM_X - theme.ITEM_MARKER_GAP,
        f"{furthest} vs {theme.ITEM_X}",
    )

    print("\n-- activation")
    press(window, Qt.Key_Home)
    press(window, Qt.Key_Return)
    app.processEvents()
    check("enter on a track plays it", controller.index == 0 and engine.is_playing)
    check("transport titles it", transport.title.text() == controller.tracks[0].title)

    print("\n-- mouse")
    click(stage, 400, row + theme.ITEM_SPACING)
    check("click selects a row", column.index == 1, f"index={column.index}")
    click(stage, 400, row)
    app.processEvents()
    check("click on the selected row opens it", controller.index == 1)
    click(stage, theme.FOCUS_X + theme.CATEGORY_SPACING, row)
    check("click on a category switches to it", bar.index == CAT_SETTINGS)

    print("\n-- settings")
    press(window, Qt.Key_Home)
    check("folder row names the folder", column._items[0].value == controller.folder.name)
    check("no speed rows left here", not any(i.label == "Nightcore" for i in column._items))

    print("\n-- the speed slider: no mode to discover")
    bar.set_index(CAT_NOW)
    app.processEvents()

    # Start from the middle. Reading the saved speed instead would make these
    # checks pass or fail depending on where the user last left the slider.
    controller.set_speed(1.05)
    app.processEvents()

    before = engine.speed
    press(window, Qt.Key_Down)
    check(
        "down slows it, with nothing pressed first",
        engine.speed < before,
        f"{before:.3f} -> {engine.speed:.3f}",
    )
    press(window, Qt.Key_Up)
    press(window, Qt.Key_Up)
    check("up speeds it up", engine.speed > before)
    check("...and the page stays put", bar.index == CAT_NOW)

    for _ in range(200):  # walk it off the end
        press(window, Qt.Key_Up)
    check(
        "clamps at nightcore",
        abs(engine.speed - settings_mod.NIGHTCORE_SPEED) < 1e-6,
        f"{engine.speed:.3f}",
    )
    for _ in range(200):
        press(window, Qt.Key_Down)
    check(
        "clamps at daycore",
        abs(engine.speed - settings_mod.DAYCORE_SPEED) < 1e-6,
        f"{engine.speed:.3f}",
    )

    press(window, Qt.Key_Right)
    check("left/right are still category nav", bar.index == CAT_MUSIC)
    # Music restores its own cursor, so step from wherever it left off.
    was = column.index
    press(window, Qt.Key_Down)
    check(
        "down is list nav once there's a list",
        column.index == was + 1,
        f"{was} -> {column.index}",
    )
    bar.set_index(CAT_NOW)
    app.processEvents()

    print("\n-- dragging the slider")
    track = page.track_rect()
    check("the page has a track", track is not None)
    drag(stage, track.right(), track.center().y())
    check(
        "dragging to the right end is nightcore",
        abs(engine.speed - settings_mod.NIGHTCORE_SPEED) < 1e-6,
        f"{engine.speed:.3f}",
    )
    drag(stage, track.left(), track.center().y())
    check(
        "dragging to the left end is daycore",
        abs(engine.speed - settings_mod.DAYCORE_SPEED) < 1e-6,
        f"{engine.speed:.3f}",
    )
    drag(stage, track.center().x(), track.center().y())
    midpoint = (settings_mod.MIN_SPEED + settings_mod.MAX_SPEED) / 2
    check(
        "dragging to the middle lands between them",
        abs(engine.speed - midpoint) < 0.02,
        f"{engine.speed:.3f} vs {midpoint:.3f}",
    )

    print("\n-- transport")
    before = controller.index
    transport.next_pressed.emit()
    app.processEvents()
    check("next advances", controller.index == (before + 1) % len(controller.tracks))
    transport.seek_requested.emit(20.0)
    check("seek posted to the mixer", engine.mixer._seek_request is not None)
    transport.volume_requested.emit(0.42)
    check("volume applied", abs(engine.volume - 0.42) < 1e-6)
    transport.play_pressed.emit()
    check("play/pause toggles", not engine.is_playing)

    print("\n-- the page reflects the engine")
    bar.set_index(CAT_NOW)
    controller.set_speed(1.10)
    app.processEvents()
    state = page.state
    check("the readout shows the speed", state.speed_text == "1.10x")
    check(
        "the handle sits proportionally along the track",
        abs(state.fraction - 0.6) < 0.01,
        f"fraction={state.fraction:.3f}",
    )
    check("the title is the song", state.title == controller.current.title)
    check(
        "the info block gives the warped length",
        "plays in" in state.lines[0] and "1.10x" in state.lines[0],
        state.lines[0],
    )
    check(
        "...and where the track sits in the library",
        f"of {len(controller.tracks)}" in state.lines[1],
        state.lines[1],
    )
    controller.set_speed(1.0)
    app.processEvents()
    check(
        "no warped length at 1.00x -- it would just repeat itself",
        "plays in" not in page.state.lines[0],
        page.state.lines[0],
    )
    check("paints the page", not window.grab().isNull())

    print("\n-- chrome")
    window.toggle_fullscreen()
    app.processEvents()
    check("fullscreen drops the resize margin", window._layout.contentsMargins().left() == 0)
    window.toggle_fullscreen()
    app.processEvents()
    check(
        "normal restores it",
        window._layout.contentsMargins().left() == theme.RESIZE_MARGIN,
    )
    check("left edge is a grip", bool(window._edges_at(QPoint(2, 300))))
    check("the interior is not", not window._edges_at(QPoint(400, 300)))

    print("\n-- resize")
    for width, height in ((720, 480), (1600, 900), (980, 640)):
        window.resize(width, height)
        app.processEvents()
        check(f"paints at {width}x{height}", not window.grab().isNull())
        check(f"children fill the stage at {width}", bar.size() == stage.size())

    print("\n-- the minimum window still fits its contents")
    # Fixed widths in the transport row used to add up to 773 px against 629
    # available, and Qt resolved that by drawing the readouts on top of the
    # sliders. Assert the row can actually shrink instead.
    window.resize(*theme.WINDOW_MINIMUM)
    bar.set_index(CAT_NOW)
    app.processEvents()
    window.layout().activate()

    inner = window.width() - 2 * theme.RESIZE_MARGIN - 2 * theme.TRANSPORT_MARGIN
    check(
        "the transport row fits",
        transport.layout().itemAt(1).minimumSize().width() <= inner,
        f"needs {transport.layout().itemAt(1).minimumSize().width()}, has {inner}",
    )
    check(
        "the volume readout clears its slider",
        transport.volume_value.x() > transport.volume.geometry().right(),
    )
    check(
        "nothing overruns the right margin",
        transport.volume_value.geometry().right()
        <= transport.width() - theme.TRANSPORT_MARGIN,
    )
    check("the title shrank rather than overflowed", transport.title.width() > 0)

    bar.set_index(CAT_NOW)
    app.processEvents()
    check("the page still has a usable track", page.track_rect() is not None)
    check("paints at the minimum size", not window.grab().isNull())

    # The art is sized by the gutter rather than by leftover vertical room, so
    # unlike the header art it replaced, no supported window size drops it. The
    # hint under the slider has to stay on screen at the minimum too, or the
    # "no mode to discover" claim quietly stops being true.
    for width, height in ((720, 480), (980, 640), (1600, 900)):
        window.resize(width, height)
        app.processEvents()
        art = page.art_rect()
        check(f"art shows at {width}x{height}", art is not None, f"{art}")
        hint_top = page.row_y() + theme.NP_HINT
        check(
            f"the key hint is on screen at {width}x{height}",
            hint_top + 18 <= page.height(),
            f"hint bottom {hint_top + 18} vs stage {page.height()}",
        )
        # NOTE: don't add text-width assertions here. This harness runs under
        # QT_QPA_PLATFORM=offscreen, which has no font database -- QFontMetrics
        # returns fallback widths roughly 2.5x too wide (the hint measures 148px
        # offscreen against 60px real). Anything that depends on how wide text
        # actually is has to be checked by looking at a render.
        #
        # It cuts one way safely: `track_rect` subtracts the DAYCORE/NIGHTCORE
        # advances, so offscreen it comes out *narrower* than reality. A track
        # that survives here survives on screen.

    print("\n-- empty library")
    folder = controller.folder
    controller.open_folder(Path(__file__).parent, remember=False)
    app.processEvents()
    bar.set_index(CAT_MUSIC)
    check("music column is empty", column.count == 0)
    check("and says why", "No playable MP3s" in column._empty_text)
    check("paints when empty", not window.grab().isNull())

    # Put everything back before shutdown flushes settings to disk.
    controller.open_folder(folder, remember=False)
    controller.set_speed(saved.speed)
    controller.set_volume(saved.volume)
    controller.shutdown()

    total = len(PASSED) + len(FAILED)
    print(f"\n{len(PASSED)}/{total} passed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
