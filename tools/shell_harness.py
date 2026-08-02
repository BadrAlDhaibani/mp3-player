"""Offscreen exercise of the XMB shell. Real engine, no display, no pytest.

    venv/Scripts/python.exe tools/shell_harness.py

`tests/` is core-only by convention -- no display needed, no Qt. This is the
other half: it drives the actual widgets through synthesised key and mouse
events and asserts on what the shell did, which is the only way to catch a
crossbar and an item column quietly fighting over the same pixels.

Animations are checked by driving their clocks (`settle()`, or the tween's own
`setCurrentTime`) rather than by sleeping. Waiting out real milliseconds makes
the result depend on when the event loop happened to get a turn, which is how
you write a test that passes on your machine and nowhere else.

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
from mp3player.core.audio import sfx  # noqa: E402
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


class SoundLog:
    """Records every sound the shell asks for, and passes it through.

    Wraps `PlayerController.play_sfx`, which is the only route the UI has to the
    engine -- so this sees exactly what a real run would play, throttle and all,
    without knowing anything about how the window decided it.
    """

    def __init__(self, controller) -> None:
        self.calls: list[tuple[str, float]] = []
        self._forward = controller.play_sfx
        controller.play_sfx = self._record

    def _record(self, name: str, gain: float = 1.0) -> None:
        self.calls.append((name, gain))
        self._forward(name, gain)

    def take_calls(self) -> list[tuple[str, float]]:
        calls, self.calls = self.calls, []
        return calls

    def take(self) -> list[str]:
        return [name for name, _ in self.take_calls()]


class Clock:
    """A hand-driven millisecond clock for the sound throttle.

    Sleeping through 60 ms to prove a blip is allowed again would make the
    result depend on when the event loop got a turn -- the same reason the
    animations are driven rather than waited out. Starts far from zero so the
    throttle's "has it been long enough" is answered against a real timestamp
    even for whatever played before this was installed.
    """

    def __init__(self, start: float = 1e7) -> None:
        self.ms = float(start)

    def __call__(self) -> float:
        return self.ms

    def tick(self, ms: float = 1000.0) -> None:
        self.ms += ms


def main() -> int:
    app = QApplication(sys.argv)
    saved = settings_mod.load()

    engine = AudioEngine(volume=saved.volume, speed=saved.speed)
    engine.start()
    print(f"stream: {engine.sample_rate} Hz")

    controller = PlayerController(engine, saved)
    # Installed before the window exists, because the window sounds the startup
    # swell in its constructor -- the same place it starts the entrance.
    log = SoundLog(controller)

    window = MainWindow(controller)
    launched_with = log.take()
    clock = Clock()
    window.sounds.clock = clock

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

    wave = stage.wave

    print("\n-- structure")
    check("starts on Now Playing", bar.index == CAT_NOW)
    check("now playing shows the page, not a list", page.isVisible() and not column.isVisible())
    check("transport has no speed control", not hasattr(transport, "speed"))
    check("paints", not window.grab().isNull())
    # Siblings paint in creation order, so the wave being constructed first is
    # the whole of what puts it behind everything else. Nothing else enforces it.
    order = stage.children()
    check(
        "the wave is under every other stage child",
        all(order.index(wave) < order.index(other) for other in (bar, column, page)),
    )
    check("the wave ignores the mouse", wave.testAttribute(Qt.WA_TransparentForMouseEvents))

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

    print("\n-- motion: the offset animates, the resting layout doesn't move")
    # The two geometry functions above are the resting ones on purpose. These
    # check the other half: that something actually slides, and that it lands.
    bar.set_index(CAT_MUSIC)
    column.settle()
    column.set_index(0)
    column.set_index(min(4, column.count - 1))
    check("the column slides rather than jumping", column._display != column.index,
          f"display={column._display:.2f} index={column.index}")
    check(
        "...while the row it will rest on is already the crossbar row",
        column._item_y(column.index) == column.row_y(),
    )
    check(
        "...and hit-testing uses that resting layout, not the moving one",
        column.hit(QPoint(400, column.row_y())) == column.index,
    )
    column.settle()
    check("settling lands exactly on the target", column._display == float(column.index))
    check(
        "...and the painted row is then the resting row",
        column._paint_y(column.index) == float(column.row_y()),
    )

    bar.set_index(CAT_SETTINGS)
    check("the crossbar slides too", bar._display != bar.index, f"{bar._display:.2f}")
    check("...without moving where a click lands", bar.hit(QPoint(theme.FOCUS_X, row)) == bar.index)
    bar.settle()
    check("and it settles", bar._display == float(bar.index))

    print("\n-- motion: a category's content flies in")
    check("stepping to Settings started an entrance", column._appear < 1.0,
          f"appear={column._appear:.2f}")
    column.settle()
    check("...which settles at fully arrived", column._appear == 1.0)
    bar.set_index(CAT_NOW)
    bar.settle()
    check("the page gets one as well", page._appear < 1.0, f"appear={page._appear:.2f}")
    page.settle()
    check("...and settles too", page._appear == 1.0)
    check(
        "the hidden half was settled rather than left animating",
        column._appear == 1.0 and column._display == float(column.index),
    )
    bar.set_index(CAT_MUSIC)
    bar.settle()
    column.settle()

    print("\n-- the wave")
    check("the wave paints", not wave.grab().isNull())
    controller.set_speed(settings_mod.NIGHTCORE_SPEED)
    app.processEvents()
    check("its hue follows the speed to nightcore", abs(wave._fraction - 1.0) < 1e-6,
          f"{wave._fraction:.3f}")
    controller.set_speed(settings_mod.DAYCORE_SPEED)
    app.processEvents()
    check("...and to daycore", abs(wave._fraction) < 1e-6, f"{wave._fraction:.3f}")
    controller.set_speed(1.0)
    app.processEvents()
    check("...and 1.00x sits where the accent does", abs(wave._fraction - 0.4) < 1e-6)
    # The claim in theme.py that 1.00x *is* ACCENT, checked rather than trusted:
    # the hue knots were fitted to it, and a palette edit could silently break it.
    at_normal = theme.wave_color(0.4)
    check(
        "the wave at 1.00x is the accent colour",
        max(
            abs(at_normal.red() - theme.ACCENT.red()),
            abs(at_normal.green() - theme.ACCENT.green()),
            abs(at_normal.blue() - theme.ACCENT.blue()),
        )
        <= 2,
        f"{at_normal.getRgb()[:3]} vs {theme.ACCENT.getRgb()[:3]}",
    )
    day, normal, night = (theme.wave_color(f).hue() for f in (0.0, 0.4, 1.0))
    check(
        "daycore, normal and nightcore are three distinct hues",
        len({day, normal, night}) == 3,
        f"{day} / {normal} / {night}",
    )
    check(
        "...and nightcore is the one off toward violet",
        night > day > normal,
        f"night={night} day={day} normal={normal}",
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

    print("\n-- sound: what makes a noise")
    # The blips have been tested since Batch 2; what is new here is *when* they
    # fire. Every check below is really about which presses are silent, because
    # that is the half a synthesizer test can't see -- a player that blips at
    # the end of every track, or against the end of every list, is one that
    # sounds broken while every sound in it is correct.
    check("launching plays the startup swell", launched_with == [sfx.STARTUP],
          f"{launched_with}")
    log.take()  # whatever the sections above made; the map starts here

    clock.tick()
    press(window, Qt.Key_Right)
    check("a crossbar step blips", log.take() == [sfx.MOVE], f"now {bar.index}")
    clock.tick()
    press(window, Qt.Key_Down)
    check("so does a row", log.take() == [sfx.MOVE])
    clock.tick()
    press(window, Qt.Key_Home)
    log.take()
    clock.tick()
    press(window, Qt.Key_Up)
    check("...but a press that goes nowhere is silent", log.take() == [])

    clock.tick()
    press(window, Qt.Key_Down)
    press(window, Qt.Key_Down)
    check("two moves in the same instant are one blip", log.take() == [sfx.MOVE])
    clock.tick()
    press(window, Qt.Key_Down)
    check("...and the next one once time has passed", log.take() == [sfx.MOVE])

    clock.tick()
    press(window, Qt.Key_Return)
    app.processEvents()
    check("Enter confirms", log.take() == [sfx.CONFIRM])
    clock.tick()
    press(window, Qt.Key_Space)
    check("space pausing sounds back", log.take() == [sfx.BACK])
    clock.tick()
    press(window, Qt.Key_Space)
    check("...and starting again confirms", log.take() == [sfx.CONFIRM])

    # The one the controller could not get right on its own: `step(+1)` is both
    # of these, and only one of them is something the user did.
    clock.tick()
    was = controller.index
    engine.mixer._finished = True
    controller._poll()
    app.processEvents()
    check("a track ending advances the list", controller.index != was)
    check("...in silence -- nobody pressed anything", log.take() == [])
    clock.tick()
    press(window, Qt.Key_Right, Qt.ControlModifier)
    app.processEvents()
    check("...while pressing Next for the same move blips", log.take() == [sfx.MOVE])

    row = column.row_y()
    clock.tick()
    click(stage, 400, row + theme.ITEM_SPACING)
    check("a click that selects blips", log.take() == [sfx.MOVE])
    clock.tick()
    click(stage, 400, row)
    app.processEvents()
    check("a click on the selection confirms", log.take() == [sfx.CONFIRM])
    clock.tick()
    click(stage, theme.FOCUS_X, row)
    check("clicking the category you're already on is silent", log.take() == [])

    print("\n-- sound: the speed slider ticks, quietly and not forever")
    bar.set_index(CAT_NOW)
    app.processEvents()
    controller.set_speed(1.05)  # straight to the controller: no tick of its own
    log.take()

    clock.tick()
    press(window, Qt.Key_Up)
    calls = log.take_calls()
    check("adjusting the speed ticks", [name for name, _ in calls] == [sfx.MOVE], f"{calls}")
    check(
        "...at less than a navigation blip",
        bool(calls) and calls[0][1] < 1.0,
        f"gain {calls[0][1] if calls else '-'}",
    )
    for _ in range(200):  # walk it into the clamp
        clock.tick()
        press(window, Qt.Key_Up)
    log.take()
    clock.tick()
    press(window, Qt.Key_Up)
    check(
        "a slider already at nightcore stops ticking",
        log.take() == [],
        f"speed {engine.speed:.3f}",
    )
    controller.set_speed(1.0)
    app.processEvents()

    clock.tick()
    controller.failed.emit("harness")
    check("a failure is audible, not just printed", log.take() == [sfx.ERROR])

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

    print("\n-- perf: the wave is the only thing running when nothing happens")
    # The budget is one frame at WAVE_FPS. The first version of the wave blew
    # straight through it -- 25 ms against 33 -- by stroking each ribbon with a
    # wide soft pen. Assert the fix stays fixed; the number, not the intent.
    budget = 1000 / theme.WAVE_FPS
    window.resize(1600, 900)
    app.processEvents()
    wave.reset_stats()
    for _ in range(60):
        wave.update()
        app.processEvents()
    check(
        f"a wave frame at 1600x900 costs well under {budget:.0f} ms",
        0.0 < wave.average_render_ms < budget / 3,
        f"{wave.average_render_ms:.2f} ms over {wave._frames} frames",
    )
    check(
        "a hidden wave stops its timer entirely",
        (wave.hide(), not wave._timer.isActive())[1],
    )
    wave.show()
    check("...and starts it again when shown", wave._timer.isActive())
    # Coarse is a decision, not a default: a precise timer would raise the
    # system-wide timer resolution for the sake of 9 more fps nobody can see.
    check("the wave's timer is deliberately coarse", wave._timer.timerType() == Qt.CoarseTimer)

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
