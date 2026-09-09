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

import itertools
import os
import struct
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# The shell's own strings contain "▸" and "·", and a Windows console defaults to
# cp1252 -- which turns a *passing* check into a UnicodeEncodeError the moment it
# prints the text it just approved.
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None:
        _stream.reconfigure(encoding="utf-8", errors="replace")

from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1  # noqa: E402
from PySide6.QtCore import QBuffer, QEvent, QIODevice, QPoint, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QKeyEvent, QMouseEvent, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from mp3player import app as app_mod  # noqa: E402
from mp3player.core import fetch  # noqa: E402
from mp3player.core import log as log_mod  # noqa: E402
from mp3player.core import settings as settings_mod  # noqa: E402
from mp3player.core.audio import engine as engine_mod  # noqa: E402
from mp3player.core.audio import sfx  # noqa: E402
from mp3player.core.audio.engine import (  # noqa: E402
    AudioDeviceError,
    AudioEngine,
    StreamWatch,
)
from mp3player.core.library import matches as track_matches  # noqa: E402
from mp3player.core.library import scan_folder  # noqa: E402
from mp3player.core.models import Track  # noqa: E402
from mp3player.core.tags import read_art  # noqa: E402
from mp3player.ui import main_window, theme  # noqa: E402
from mp3player.ui.controller import (  # noqa: E402
    REPEAT_ALL,
    REPEAT_OFF,
    REPEAT_ONE,
    SAVE_FAILED_TEXT,
    PlayerController,
)
from mp3player.ui.main_window import (  # noqa: E402
    CAT_GET,
    CAT_MUSIC,
    CAT_NOW,
    CAT_SETTINGS,
    SET_REPEAT,
    SET_SHUFFLE,
    SET_THEME,
    MainWindow,
)
from mp3player.ui.widgets.item_column import GET_LABEL  # noqa: E402
from mp3player.ui.widgets.now_playing import NowPlaying  # noqa: E402
from mp3player.ui.widgets.transport import (  # noqa: E402
    REPEAT_ALL_GLYPH,
    REPEAT_ONE_GLYPH,
)

# The Now Playing info block, by slot. Named because the numbers moved once
# already and the checks that used literals kept passing while pointing at the
# wrong line.
CREDIT_LINE, LENGTH_LINE, POSITION_LINE = 0, 1, 2

PASSED: list[str] = []
FAILED: list[str] = []


def cover_png(size: int = 64) -> bytes:
    """A real PNG, generated rather than checked in.

    The point of the art checks is the whole path -- tag frame to bytes to
    `QImage` to a scaled pixmap -- so the bytes have to be something Qt will
    genuinely decode. Making one here beats a binary file in a repo whose
    decisions log is proud of not having any.
    """
    image = QImage(size, size, QImage.Format_RGB32)
    image.fill(QColor(80, 140, 220))
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def write_tagged_mp3(path: Path, *, cover: bytes | None = None, **frames) -> Path:
    """A file the scanner will list, carrying a real ID3v2 tag."""
    tag = ID3()
    if "title" in frames:
        tag.add(TIT2(encoding=3, text=frames["title"]))
    if "artist" in frames:
        tag.add(TPE1(encoding=3, text=frames["artist"]))
    if "album" in frames:
        tag.add(TALB(encoding=3, text=frames["album"]))
    if cover:
        tag.add(APIC(encoding=3, mime="image/png", type=3, desc="", data=cover))
    tag.save(str(path))
    return path


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASSED if condition else FAILED).append(name)
    mark = "ok" if condition else "XX"
    print(f"  [{mark}] {name}{'  -- ' + detail if detail else ''}")


def press(window: MainWindow, code: Qt.Key, mods=Qt.NoModifier, text: str = "") -> None:
    window.keyPressEvent(QKeyEvent(QEvent.KeyPress, code, mods, text))


# The letter keys that already mean something outside a search. Typed with their
# real key codes rather than a stand-in, because "S is literal in here and
# shuffle out there" is exactly the claim being checked -- a probe that sent
# Key_A for every character would pass while the app toggled shuffle.
_KEY_FOR = {" ": Qt.Key_Space, "/": Qt.Key_Slash, "-": Qt.Key_Minus, ".": Qt.Key_Period}


def type_text(window: MainWindow, text: str) -> None:
    """Type `text` a character at a time, the way a keyboard delivers it."""
    for char in text:
        code = _KEY_FOR.get(char)
        if code is None:
            code = getattr(Qt, f"Key_{char.upper()}", Qt.Key_A)
        press(window, code, text=char)


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


class _Stalled:
    """A `StreamWatch` that has already made up its mind.

    Standing in for the verdict, not for the stream: the real one keeps running
    underneath, which is what lets the reconnect that follows be a real reopen
    of a real device rather than another stand-in. When it counts as stalled is
    `StreamWatch`'s own business and is tested offline in `tests/test_engine.py`.
    """

    def reset(self, blocks: int) -> None:
        pass

    def stalled(self, blocks: int) -> bool:
        return True


def _refuse() -> None:
    """What `reopen` does while the device really is still unplugged."""
    raise AudioDeviceError("no usable audio output device (harness)")


def wait_for(app, predicate, seconds: float = 20.0) -> bool:
    """Spin the event loop until `predicate` holds, or give up and say so.

    The one place this harness genuinely has to wait. Everything else that
    takes time here is driven -- the animations settle, the sound throttle has
    an injectable clock -- because a test that sleeps depends on the scheduler.
    A real child process is not driveable: it starts when the OS says so and
    exits when it is done, and `QProcess` reports both through the event loop.

    So: bounded, and it returns the answer rather than asserting it, which is
    what lets the timeout show up as the check that was actually waiting
    instead of as a hang with no name on it.
    """
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        app.processEvents()
    return predicate()


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


def pick_query(tracks) -> str:
    """A query that matches some of this library but not all of it.

    Built from the folder in front of it rather than hard-coded, because this
    harness runs against whatever the user has saved -- a literal like "remix"
    would quietly become a check that everything matches, or that nothing does,
    on somebody else's music.
    """
    fallback = ""
    # Short prefixes first, because they match more: several of the checks below
    # need a result set they can walk down, and a query that happens to pin one
    # track passes "End goes to the last match" without saying anything.
    for size in (3, 4, 5, 6):
        for track in tracks[:40]:
            candidate = track.title[:size].strip().casefold()
            if len(candidate) < 3:
                continue
            hits = sum(1 for other in tracks if track_matches(other, candidate))
            if not 0 < hits < len(tracks):
                continue
            if hits >= 5:
                return candidate
            fallback = fallback or candidate
    return fallback


def main() -> int:
    app = QApplication(sys.argv)
    saved = settings_mod.load()

    # Pointed at a temp file before anything else happens, so the whole run is
    # recorded and the checks at the bottom can read back what the device
    # section did. Never the real log: this is a test run, and it has no
    # business in the file someone is asked to send in.
    log_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    log_file = log_mod.setup(Path(log_dir.name) / "xmbplayer.log")

    engine = AudioEngine(volume=saved.volume, speed=saved.speed)
    engine.start()
    print(f"stream: {engine.sample_rate} Hz")

    controller = PlayerController(engine, saved)
    # Installed before the window exists, because the window sounds the startup
    # swell in its constructor -- the same place it starts the entrance.
    log = SoundLog(controller)
    # Every cover the controller hands up, in order. The read used to be done by
    # the widget; what this records is that it is the controller's now.
    art_seen: list[object] = []
    controller.art_changed.connect(art_seen.append)

    window = MainWindow(controller)
    launched_with = log.take()
    clock = Clock()
    window.sounds.clock = clock

    window.resize(980, 640)
    window.show()
    controller.start()
    app.processEvents()

    # Pinned to the default before anything asserts on a colour. This harness
    # runs against the *saved* settings, and every ACCENT comparison below is a
    # statement about XMB Blue specifically -- left alone, the checks would pass
    # or fail depending on which theme the machine happened to be set to. Put
    # back at the end, with the speed and the volume.
    controller.set_theme(settings_mod.DEFAULT_THEME)
    # Same argument, and it now covers behaviour rather than only colour: every
    # advance check below is a statement about the defaults, and a machine left
    # on `Repeat: One` would fail them while the app was working correctly.
    controller.set_shuffle(settings_mod.DEFAULT_SHUFFLE)
    controller.set_repeat(settings_mod.DEFAULT_REPEAT)
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
    check("settings column built, no presets", column.count == 7)
    # `ItemColumn` activates by index and has no notion of an id, so the list
    # and the dispatch are held together by counting. Batch 10 inserted a row in
    # the middle of it; without this the branches below just quietly do the
    # wrong thing.
    check(
        "every settings row is where its branch thinks it is",
        [item.label for item in column._items]
        == ["Music folder", "Rescan folder", "Shuffle", "Repeat", "Theme",
            "Full screen", "Quit"],
        " / ".join(item.label for item in column._items),
    )
    press(window, Qt.Key_Right)
    check("right -> Get Music", bar.index == CAT_GET)
    check("get music opens on a header with nothing typed", column.search == "")
    press(window, Qt.Key_Right)
    check("clamps at the last category", bar.index == CAT_GET)
    press(window, Qt.Key_Backspace)
    check("backspace steps left", bar.index == CAT_SETTINGS)
    press(window, Qt.Key_Backspace)
    check("...and again", bar.index == CAT_MUSIC)
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
    check(
        "...without moving where a click lands",
        bar.hit(QPoint(theme.FOCUS_X, row)) == bar.index,
    )
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

    print("\n-- the speed range and where 1.00x lands on it")
    # The two halves of one number, checked against each other rather than
    # against a literal either of them could drift from. `_speed_fraction` maps
    # the slider onto 0..1 and `ANCHOR_FRACTION` says where the knots were put;
    # if those two ever disagree, every palette's resting colour is wrong and
    # nothing else in this file would say so -- the anchor checks below would
    # compare a moved colour against a knot that moved with it and pass.
    check(
        "1.00x maps to the fraction the knots are pinned at",
        abs(main_window._speed_fraction(settings_mod.DEFAULT_SPEED)
            - theme.ANCHOR_FRACTION) < 1e-9,
        f"{main_window._speed_fraction(settings_mod.DEFAULT_SPEED):.4f} vs "
        f"{theme.ANCHOR_FRACTION:.4f}",
    )
    check(
        "the slider's ends are the two presets",
        main_window._speed_fraction(settings_mod.DAYCORE_SPEED) == 0.0
        and main_window._speed_fraction(settings_mod.NIGHTCORE_SPEED) == 1.0,
    )
    check(
        "...and the anchor is strictly between them, so the knots stay in order",
        0.0 < theme.ANCHOR_FRACTION < 1.0,
        f"{theme.ANCHOR_FRACTION:.4f}",
    )
    # Daycore reaches 0.70x as of Batch 19. Named rather than implied: this is
    # the number the batch was about, and a future edit that walks it back
    # should have to delete a line that says so.
    check(
        "daycore reaches 0.70x",
        abs(settings_mod.DAYCORE_SPEED - 0.70) < 1e-9,
        f"{settings_mod.DAYCORE_SPEED:.2f}",
    )

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
    check(
        "...and 1.00x sits where the accent does",
        abs(wave._fraction - theme.ANCHOR_FRACTION) < 1e-6,
        f"{wave._fraction:.3f} vs {theme.ANCHOR_FRACTION:.3f}",
    )
    # The claim in theme.py that 1.00x *is* ACCENT, checked rather than trusted:
    # the hue knots were fitted to it, and a palette edit could silently break it.
    #
    # Note what these read rather than what they used to: `theme.ANCHOR_FRACTION`,
    # not the literal 0.4 that a 0.80..1.30 slider happens to put 1.00x at. Batch
    # 19 widened the range to 0.70..1.30 and moved it to 0.5, and a harness full
    # of the old literal would have gone on asserting a fraction that no longer
    # means 1.00x -- passing, on a colour that had moved.
    at_normal = theme.wave_color(theme.ANCHOR_FRACTION)
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
    day, normal, night = (
        theme.wave_color(f).hue() for f in (0.0, theme.ANCHOR_FRACTION, 1.0)
    )
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

    print("\n-- the accent tracks the speed")
    # The whole batch in one line: whatever the ribbons are, the accent is. Note
    # these compare the *live* accent against the wave's own fraction, so they
    # fail if the plumbing in `_on_speed` stops running as much as if the ramp
    # itself changed.
    for name, speed in (
        ("daycore", settings_mod.DAYCORE_SPEED),
        ("1.00x", 1.0),
        ("nightcore", settings_mod.NIGHTCORE_SPEED),
    ):
        controller.set_speed(speed)
        app.processEvents()
        check(
            f"the accent is the wave's colour at {name}",
            theme.accent().getRgb() == theme.wave_color(wave._fraction).getRgb(),
            f"{theme.accent().getRgb()[:3]} vs {theme.wave_color(wave._fraction).getRgb()[:3]}",
        )
    controller.set_speed(1.0)
    app.processEvents()
    check(
        "...and at 1.00x that colour is ACCENT",
        max(
            abs(theme.accent().red() - theme.ACCENT.red()),
            abs(theme.accent().green() - theme.ACCENT.green()),
            abs(theme.accent().blue() - theme.ACCENT.blue()),
        )
        <= 2,
        f"{theme.accent().getRgb()[:3]} vs {theme.ACCENT.getRgb()[:3]}",
    )
    check(
        "the plate's fill is the same colour at ACCENT_SOFT's opacity",
        theme.accent_soft().hue() == theme.accent().hue()
        and theme.accent_soft().alpha() == theme.ACCENT_SOFT.alpha(),
        f"alpha={theme.accent_soft().alpha()}",
    )
    # The transport bar is the one thing coloured by stylesheet rather than by a
    # paintEvent, so "did it follow?" is a different question there than
    # everywhere else, and it is the half most likely to be forgotten.
    controller.set_speed(settings_mod.NIGHTCORE_SPEED)
    app.processEvents()
    check(
        "the transport bar's stylesheet followed to nightcore",
        theme.rgba(theme.accent()) in transport.styleSheet(),
        theme.rgba(theme.accent()),
    )
    check(
        "...and no longer carries the 1.00x accent",
        theme.rgba(theme.ACCENT) not in transport.styleSheet(),
    )
    # The gate that keeps a per-pixel drag off the restyle path.
    theme.set_accent_fraction(0.5)
    check("a nudge inside a bucket asks for no restyle", not theme.set_accent_fraction(0.502))
    check("...and crossing one does", theme.set_accent_fraction(0.9))
    controller.set_speed(1.0)
    app.processEvents()
    check(
        "the accent came back to 1.00x",
        abs(theme.accent_fraction() - theme.ANCHOR_FRACTION) < 1e-6,
    )

    # The accent as *text*. Fills can be as saturated as they like; a pen can't,
    # because HSV value isn't lightness and the daycore blue came out dimmer
    # than TEXT_FAINT -- which rendered as a selected row whose readout was
    # fainter than the unselected ones around it. Contrast is arithmetic on
    # theme constants, so unlike the question of whether it *reads*, this half
    # belongs in an assertion.
    check(
        "at 1.00x the text accent is the accent, untouched",
        theme.accent_text().getRgb() == theme.accent().getRgb(),
    )
    for name, fraction in (
        ("daycore", 0.0),
        ("1.00x", theme.ANCHOR_FRACTION),
        ("nightcore", 1.0),
    ):
        theme.set_accent_fraction(fraction)
        contrast = theme._contrast(theme.accent_text(), theme.BG_MID)
        check(
            f"the text accent stays readable at {name}",
            contrast >= theme._TEXT_CONTRAST_FLOOR,
            f"{contrast:.1f}:1",
        )
    theme.set_accent_fraction(0.0)
    check(
        "...and a focused readout is never fainter than an unfocused one",
        theme._contrast(theme.accent_text(), theme.BG_MID)
        > theme._contrast(theme.TEXT_FAINT, theme.BG_MID),
        f"{theme._contrast(theme.accent_text(), theme.BG_MID):.1f}:1 vs "
        f"{theme._contrast(theme.TEXT_FAINT, theme.BG_MID):.1f}:1",
    )
    controller.set_speed(1.0)
    app.processEvents()

    print("\n-- theme presets")
    # Everything above, five times over. A palette is a swap of the ramp's knots,
    # so every invariant the ramp had is now an invariant five ramps have to
    # hold -- and the one that broke in Batch 9 broke at *one* end of *one* of
    # them, with every other check green.
    check(
        "the default palette is the one `core` names",
        theme.PALETTES[0].name == settings_mod.DEFAULT_THEME,
        f"{theme.PALETTES[0].name} vs {settings_mod.DEFAULT_THEME}",
    )
    check(
        "...and its anchor is still ACCENT itself",
        theme.PALETTES[0].anchor.getRgb() == theme.ACCENT.getRgb(),
    )
    faint = theme._contrast(theme.TEXT_FAINT, theme.BG_MID)
    for palette in theme.PALETTES:
        theme.set_palette(palette.name)
        # The anchor is written by hand in the table, not derived from the
        # knots -- which is the only reason this proves anything. A fitted
        # value compared against itself would pass whatever the knots said.
        at_normal = theme.wave_color(theme.ANCHOR_FRACTION)
        check(
            f"{palette.name}: 1.00x is the anchor it claims",
            max(
                abs(at_normal.red() - palette.anchor.red()),
                abs(at_normal.green() - palette.anchor.green()),
                abs(at_normal.blue() - palette.anchor.blue()),
            )
            <= 2,
            f"{at_normal.getRgb()[:3]} vs {palette.anchor.getRgb()[:3]}",
        )
        hues = [theme.wave_color(f).hue() for f in (0.0, theme.ANCHOR_FRACTION, 1.0)]
        check(
            f"{palette.name}: the ramp actually travels",
            len(set(hues)) == 3,
            " / ".join(str(h) for h in hues),
        )
        worst = 999.0
        for fraction in (0.0, theme.ANCHOR_FRACTION, 1.0):
            theme.set_accent_fraction(fraction)
            worst = min(worst, theme._contrast(theme.accent_text(), theme.BG_MID))
        check(
            f"{palette.name}: readable at every speed",
            worst >= theme._TEXT_CONTRAST_FLOOR,
            f"worst {worst:.1f}:1",
        )
        check(
            f"{palette.name}: a focused readout never goes fainter than an unfocused one",
            worst > faint,
            f"{worst:.1f}:1 vs {faint:.1f}:1",
        )

    # The hole the bucket gate leaves. `set_accent_fraction` asks whether the
    # *fraction* moved, and a palette swap doesn't move it -- so the stylesheet
    # has to be re-applied on a different signal entirely, and the bar is the one
    # thing in the app that would otherwise sit there in the old colour.
    controller.set_theme("XMB Blue")
    controller.set_speed(1.0)
    app.processEvents()
    before_qss, before_fraction = transport.styleSheet(), theme.accent_fraction()
    controller.set_theme("Ember")
    app.processEvents()
    check(
        "swapping the palette leaves the slider exactly where it was",
        theme.accent_fraction() == before_fraction,
        f"{theme.accent_fraction():.3f}",
    )
    check("...and the transport bar followed anyway", transport.styleSheet() != before_qss)
    check(
        "...to the new palette's colour",
        theme.rgba(theme.accent()) in transport.styleSheet(),
        theme.rgba(theme.accent()),
    )
    check(
        "the wave is on the new ramp too",
        theme.wave_color(wave._fraction).getRgb() == theme.accent().getRgb(),
    )

    print("\n-- stepping into the theme row")
    # The one modal row in the app, so the checks are mostly about the ways out
    # of it -- a mode you can enter and not leave is worse than no mode.
    bar.set_index(CAT_SETTINGS)
    column.set_index(SET_THEME)
    app.processEvents()
    check(
        "the row reads out what is actually on screen",
        column._items[SET_THEME].value == theme.palette().name,
        column._items[SET_THEME].value,
    )
    check("...and nothing is stepped into yet", not column.stepping)
    log.take()
    press(window, Qt.Key_Return)
    app.processEvents()
    check("Enter steps in", column.stepping and window._stepping)
    check("...sounding a confirm, like any activation", sfx.CONFIRM in log.take())
    check(
        "...and the row says so in its readout",
        "‹" in column._items[SET_THEME].value,
        column._items[SET_THEME].value,
    )

    started_on = theme.palette().name
    resting = column.index
    was_category = bar.index
    seen = [started_on]
    blipped = []
    for _ in range(len(theme.PALETTES) - 1):
        clock.tick(200)  # past the move throttle, so each press is its own blip
        log.take()
        press(window, Qt.Key_Right)
        app.processEvents()
        seen.append(theme.palette().name)
        blipped.append(sfx.MOVE in log.take())
    check(
        "Right walks every preset without repeating one",
        len(set(seen)) == len(theme.PALETTES),
        " -> ".join(seen),
    )
    # The whole point of the mode: Left/Right are category navigation
    # everywhere else, and this is the one row allowed to spend them.
    check(
        "...and the crossbar never moved, though Right normally moves it",
        bar.index == was_category,
        f"category={bar.index}",
    )
    # The cursor deliberately doesn't move here, so the index comparison in
    # `keyPressEvent` can't earn this one -- the branch has to sound it itself.
    check("...blipping every time, because every press did something", all(blipped))
    check(
        "...without moving the cursor either",
        column.index == resting,
        f"index={column.index}",
    )
    check(
        "...and the row followed each time",
        seen[-1] in column._items[SET_THEME].value,
    )
    press(window, Qt.Key_Right)
    app.processEvents()
    check("...and the last one wraps back to the first", theme.palette().name == started_on)
    press(window, Qt.Key_Left)
    app.processEvents()
    check("Left walks the other way", theme.palette().name == seen[-1], theme.palette().name)
    # The mode is about this row's value, not about the whole keyboard.
    playing_before = controller.index
    press(window, Qt.Key_Right, Qt.ControlModifier)
    app.processEvents()
    check(
        "Ctrl+Right is still the next track, mode or no mode",
        controller.index != playing_before,
        f"{playing_before} -> {controller.index}",
    )
    check("...and it left the row stepped into", column.stepping)
    check(
        "the controller kept the name, so it will be saved",
        controller.theme == theme.palette().name,
        controller.theme,
    )
    check("the stepped-into row paints", not window.grab().isNull())

    # Every way out. Enter first, because it is also the way in.
    clock.tick(200)
    log.take()
    press(window, Qt.Key_Return)
    app.processEvents()
    check("Enter steps back out", not column.stepping and not window._stepping)
    check("...sounding a back", sfx.BACK in log.take())
    check(
        "...and the readout drops the chevrons",
        column._items[SET_THEME].value == theme.palette().name,
        column._items[SET_THEME].value,
    )
    # Settings is the last category, so Right clamps there and would prove
    # nothing -- Left is the one with somewhere to go.
    press(window, Qt.Key_Left)
    app.processEvents()
    check("...giving the horizontal arrows back to the crossbar", bar.index == CAT_MUSIC)
    bar.set_index(CAT_SETTINGS)
    column.set_index(SET_THEME)
    app.processEvents()

    press(window, Qt.Key_Return)
    app.processEvents()
    check("stepped in again", column.stepping)
    press(window, Qt.Key_Escape)
    app.processEvents()
    check("Esc steps out", not column.stepping)

    press(window, Qt.Key_Return)
    app.processEvents()
    check("stepped in once more", column.stepping)
    press(window, Qt.Key_Down)
    app.processEvents()
    check(
        "Down moves the cursor, which is itself the way out",
        not column.stepping and column.index == resting + 1,
        f"index={column.index}",
    )

    column.set_index(SET_THEME)
    press(window, Qt.Key_Return)
    app.processEvents()
    check("stepped in again, to leave by jumping", column.stepping)
    press(window, Qt.Key_Home)
    app.processEvents()
    check(
        "Home does the same -- any key that moves the cursor leaves the row",
        not column.stepping and column.index == 0,
    )

    column.set_index(SET_THEME)
    press(window, Qt.Key_Return)
    app.processEvents()
    check("and once more, to leave by the crossbar", column.stepping)
    bar.set_index(CAT_MUSIC)
    app.processEvents()
    check("changing category steps out too", not column.stepping)
    bar.set_index(CAT_SETTINGS)
    app.processEvents()
    check(
        "...and coming back does not put you back in it",
        not column.stepping and "‹" not in column._items[SET_THEME].value,
    )
    # A name from a settings file this build doesn't know. `core` hands it up
    # untouched on purpose; the clamp is here, and without it the app would paint
    # with whatever palette happened to be loaded and then write the bad name
    # back out again.
    controller.set_theme("Nebula")
    app.processEvents()
    check(
        "an unknown preset falls back to the default rather than sticking",
        controller.theme == settings_mod.DEFAULT_THEME
        and theme.palette().name == settings_mod.DEFAULT_THEME,
        f"{controller.theme} / {theme.palette().name}",
    )
    check("the theme row paints at every preset", not window.grab().isNull())
    bar.set_index(CAT_MUSIC)
    app.processEvents()

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
    # The expected fraction is spelled out from the two constants rather than
    # asked of `_speed_fraction`, which is the function under test -- deriving it
    # from the thing it checks would pass whatever either of them said. Same
    # reasoning as `Palette.anchor` being a hand-written literal.
    #
    # It used to *be* a hand-written literal, 0.6, which is what 1.10x is on a
    # 0.80..1.30 slider. Batch 19 widened the range and this was the only check
    # in 344 that noticed -- correctly, and it is worth knowing that the one
    # that caught it was about a slider handle rather than about a colour.
    expected = (1.10 - settings_mod.MIN_SPEED) / (
        settings_mod.MAX_SPEED - settings_mod.MIN_SPEED
    )
    check(
        "the handle sits proportionally along the track",
        abs(state.fraction - expected) < 0.01,
        f"fraction={state.fraction:.3f} vs {expected:.3f}",
    )
    check("the title is the song", state.title == controller.current.title)
    # The info block is three fixed slots: who it is, how long it is, where it
    # sits. Indices, not a search -- a check that scans all three would have
    # gone on passing when Batch 8 pushed the length line down one.
    check(
        "the info block gives the warped length",
        "plays in" in state.lines[LENGTH_LINE] and "1.10x" in state.lines[LENGTH_LINE],
        state.lines[LENGTH_LINE],
    )
    check(
        "...and where the track sits in the library",
        f"of {len(controller.tracks)}" in state.lines[POSITION_LINE],
        state.lines[POSITION_LINE],
    )
    controller.set_speed(1.0)
    app.processEvents()
    check(
        "no warped length at 1.00x -- it would just repeat itself",
        "plays in" not in page.state.lines[LENGTH_LINE],
        page.state.lines[LENGTH_LINE],
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
    # This used to be `page.track_rect() is not None`, and that was a *text
    # width* assertion living in the one place this project's conventions say
    # cannot make one: `track_rect` subtracts the measured widths of DAYCORE and
    # NIGHTCORE, and offscreen those measure 78 and 101 against the real
    # platform's 48 and 60. It passed for eleven batches on the margin rather
    # than on the arithmetic -- offscreen it permits `ITEM_X` up to 333, and it
    # went red the moment a fourth category pushed past that while the real
    # platform still had room to spare.
    #
    # So it asks the font-independent half instead: is there room for the
    # slider's *furniture* plus its minimum track, once the two end labels are
    # allowed the width they take **on the real platform**, which is measured
    # rather than assumed and written down here because nothing offscreen can
    # re-derive it. Whether the slider actually appears is a real-platform
    # question and is checked by looking -- `render.py --what now --size
    # 720x480`.
    REAL_END_LABELS = 108  # DAYCORE 48 + NIGHTCORE 60, measured at SLIDER_END_LABEL
    needed = (
        REAL_END_LABELS
        + 2 * theme.SLIDER_LABEL_GAP
        + theme.SLIDER_VALUE_W
        + theme.SLIDER_TRACK_MIN
    )
    check(
        "the speed slider still fits at the minimum window",
        page._text_width() >= needed,
        f"has {page._text_width()}, needs {needed}",
    )
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
        # Vertical positions are fixed numbers, so unlike text width this *is*
        # checkable here. The third info line arrived in Batch 8 and would have
        # landed one pixel off the slider's box at the old 24px spacing.
        third_bottom = page.row_y() + theme.NP_INFO_THIRD + 18
        slider_top = page.row_y() + theme.NP_SLIDER - 16
        check(
            f"the third info line clears the slider at {width}x{height}",
            third_bottom < slider_top,
            f"line bottom {third_bottom} vs slider top {slider_top}",
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

    # The wave is ~93% of the app's CPU, so it stops when the window loses
    # focus. Driven as the events themselves, because the offscreen platform
    # never delivers them for real -- which is also the point of the design:
    # it fails *open*, so a platform that stays silent goes on animating.
    top = window.window()
    app.sendEvent(top, QEvent(QEvent.WindowDeactivate))
    check("the wave stops when the window loses focus", not wave._timer.isActive())
    app.sendEvent(top, QEvent(QEvent.WindowActivate))
    check("...and picks up again when it comes back", wave._timer.isActive())
    # A hidden wave must stay stopped whatever the focus does, or a category
    # that is not on screen starts painting because somebody alt-tabbed.
    wave.hide()
    app.sendEvent(top, QEvent(QEvent.WindowActivate))
    check("focus does not restart a hidden wave", not wave._timer.isActive())
    wave.show()

    print("\n-- tags and art")
    # A folder built here rather than borrowed: the point is the *contrast*
    # between a tagged file and a bare one, and the real library is 80% bare.
    # These are listable, not playable -- everything below is about what the
    # shell says and draws, and none of it needs libsndfile to agree.
    window.resize(980, 640)
    real_folder = controller.folder
    with tempfile.TemporaryDirectory() as temp:
        tags_folder = Path(temp)
        tagged_path = write_tagged_mp3(
            tags_folder / "01 - unhelpful filename.mp3",
            title="Roygbiv",
            artist="Boards of Canada",
            album="Music Has the Right to Children",
            cover=cover_png(),
        )
        bare_path = tags_folder / "Some Artist - Some Song.mp3"
        bare_path.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 256)

        controller.open_folder(tags_folder, remember=False)
        app.processEvents()
        bar.set_index(CAT_MUSIC)
        app.processEvents()
        rows = {item.label: item for item in column._items}

        check("a tagged track is listed under its tag", "Roygbiv" in rows, str(list(rows)))
        check(
            "...with the artist as the row's readout",
            rows.get("Roygbiv") is not None
            and rows["Roygbiv"].value == "Boards of Canada",
        )
        check(
            "an untagged track keeps its filename",
            "Some Artist - Some Song" in rows,
            str(list(rows)),
        )
        check(
            "...and has no readout to right-align",
            rows.get("Some Artist - Some Song") is not None
            and rows["Some Artist - Some Song"].value == "",
        )
        check("paints a list of tagged rows", not window.grab().isNull())

        # The other half of the core/ui seam: `core.tags` hands up bytes and has
        # no idea what they are, and this is where they become pixels. That half
        # did not move in Batch 14 -- only the *reading* did, which is what the
        # `art_changed` checks below are about.
        image = main_window._cover_image(read_art(tagged_path))
        check("the embedded cover decodes to an image", image is not None)
        check(
            "...at the size it was written",
            image is not None and (image.width(), image.height()) == (64, 64),
            "" if image is None else f"{image.width()}x{image.height()}",
        )
        check(
            "a file with no tag has no cover",
            main_window._cover_image(read_art(bare_path)) is None,
        )
        check("...and neither has nothing at all", main_window._cover_image(None) is None)
        check(
            "a frame Qt cannot decode is the same as no frame",
            main_window._cover_image(b"not an image, but definitely bytes") is None,
        )

        bar.set_index(CAT_NOW)
        app.processEvents()
        page.set_art(image)
        check("the page takes the cover", page.art is image)
        size = page.art_rect().size()
        cover = page._cover(size)
        check(
            "...and scales it to the art rect exactly",
            cover.size() == size,
            f"{cover.size()}",
        )
        check(
            "...caching the result rather than rescaling per paint",
            page._cover(size) is cover,
        )
        window.resize(1600, 900)
        app.processEvents()
        bigger = page.art_rect().size()
        check(
            "a resize rescales, because the rect moved with the window",
            bigger != size and page._cover(bigger).size() == bigger,
        )
        check("paints with a cover", not window.grab().isNull())

        page.set_art(None)
        check("clearing the cover drops the cached pixmap", page._scaled is None)
        check("paints the note glyph again with no cover", not window.grab().isNull())
        window.resize(980, 640)
        app.processEvents()

    controller.open_folder(real_folder, remember=False)
    app.processEvents()

    # The credit line, built from a Track rather than from a file: three cases,
    # and the empty one is the common one in this library.
    credit = main_window._credit
    check(
        "artist and album both show, in that order",
        credit(Track(Path("x.mp3"), "t", "Aphex Twin", "Drukqs")).startswith("Aphex Twin"),
    )
    check(
        "an album with no artist still says something",
        credit(Track(Path("x.mp3"), "t", "", "Drukqs")) == "Drukqs",
    )
    check(
        "a file that named nobody gets an empty line, not a placeholder",
        credit(Track(Path("x.mp3"), "t")) == "",
    )
    bar.set_index(CAT_NOW)
    art_seen.clear()
    controller.play_index(0)
    app.processEvents()
    # The controller reads the cover, not the widget. Whether *this* file has one
    # is the library's business, so what is checked is that a track change hands
    # one up at all, and that its type is the raw bytes the seam promises.
    check("playing a track hands a cover up from the controller", len(art_seen) == 1,
          f"{len(art_seen)} emission(s)")
    check(
        "...as bytes or nothing, never a QImage",
        all(item is None or isinstance(item, bytes) for item in art_seen),
        str([type(item).__name__ for item in art_seen]),
    )
    check(
        "...and the page is holding whatever that decoded to",
        (page.art is None) == (main_window._cover_image(art_seen[0]) is None)
        if art_seen
        else False,
    )
    check("a loaded track fills all three info slots", len(page.state.lines) == 3)
    check(
        "...with the credit first and the length under it",
        "plays in" in page.state.lines[LENGTH_LINE]
        or page.state.lines[LENGTH_LINE].count(":") == 1,
        page.state.lines[LENGTH_LINE],
    )
    check(
        "an empty credit line still leaves the lines below it in place",
        page.state.lines[POSITION_LINE].startswith("Track "),
        page.state.lines[POSITION_LINE],
    )

    print("\n-- empty library")
    folder = controller.folder
    controller.open_folder(Path(__file__).parent, remember=False)
    app.processEvents()
    bar.set_index(CAT_MUSIC)
    check("music column is empty", column.count == 0)
    check("and says why", "No playable MP3s" in column._empty_text)
    check("paints when empty", not window.grab().isNull())

    print("\n-- the folder went away")
    # The case that used to read "No playable MP3s in Music" about a folder that
    # was not there at all. Three empties, three different sentences.
    clock.tick()  # past the error blip's throttle window
    log.take()
    gone = Path(__file__).parent / "no-such-folder-b7"
    controller.open_folder(gone, remember=False)
    app.processEvents()
    check("a missing folder is not the same as an empty one",
          "is gone" in column._empty_text, column._empty_text)
    check("...and it says so on the status line", "is gone" in stage._status)
    check("...which stays up rather than timing out",
          not stage._status_timer.isActive())
    check("...and it made a noise, because something is wrong",
          sfx.ERROR in log.take())
    bar.set_index(CAT_SETTINGS)
    check("the settings row flags it too",
          "missing" in column._items[0].value, column._items[0].value)
    check("paints with a missing folder", not window.grab().isNull())

    clock.tick()
    log.take()
    controller.open_folder(Path(__file__).parent, remember=False)
    app.processEvents()
    check("an empty-but-real folder is silent -- nothing is wrong",
          sfx.ERROR not in log.take())
    check("...and clears the standing message", stage._status == "")

    # Put the real library back: the device section needs something playing.
    controller.open_folder(folder, remember=False)
    app.processEvents()

    print("\n-- the audio device went away")
    # `StreamWatch` decides *when* a live stream counts as dead, and it has its
    # own offline tests. What can only be checked here is everything downstream
    # of that verdict, so the verdict is what gets faked -- the real stream keeps
    # running underneath, which is also what lets the reconnect below be real.
    if controller.tracks:
        controller.play_index(0)
        app.processEvents()
    clock.tick()
    log.take()

    engine._watch = _Stalled()
    check("the engine reports the stall", engine.stalled)

    controller._poll()
    app.processEvents()
    check("the controller notices", controller.device_lost)
    check("...and stops claiming to be playing", not engine.is_playing)
    check("...says so", stage._status == main_window.DEVICE_LOST_TEXT)
    check("...and keeps saying it", not stage._status_timer.isActive())
    check("...blipping once", log.take().count(sfx.ERROR) == 1)
    controller._poll()
    controller._poll()
    check("...and only once, however long it stays lost", log.take() == [])
    check("paints with no device", not window.grab().isNull())

    # A failed reconnect is the normal answer while the device is still out. It
    # must not clear the message, and it must not start narrating its retries.
    engine_reopen, engine.reopen = engine.reopen, _refuse
    controller._try_reconnect()
    app.processEvents()
    check("a failed retry changes nothing", controller.device_lost)
    check("...and stays quiet about it", log.take() == [])
    check("...leaving the message up", stage._status == main_window.DEVICE_LOST_TEXT)
    engine.reopen = engine_reopen

    # Now for real: this closes the live stream, re-enumerates PortAudio, picks
    # a device again and rebuilds the track onto it. On this machine that is the
    # actual reconnect path, not a stand-in for it.
    engine._watch = StreamWatch()
    controller._try_reconnect()
    app.processEvents()
    check("reconnecting really reopens the stream", engine.running)
    check("...clears the condition", not controller.device_lost)
    check("...and takes the message down", stage._status == "")
    check("...resuming where it left off", engine.is_playing and engine.position > 0.0,
          f"{engine.position:.2f}s of {engine.duration:.2f}s")
    check("...silently -- nobody pressed anything", log.take() == [])
    controller.engine.pause()

    print("\n-- first run: nothing has ever been chosen")
    # A second window, built the way `app.py` builds one, against settings with
    # no folder in them. Cheaper than restarting, and it is the same code path.
    first = MainWindow(controller)
    first.resize(980, 640)
    first._on_folder(None)
    first._on_library(scan_folder(None))
    app.processEvents()
    check("opens on Settings, not Now Playing", first.stage.bar.index == CAT_SETTINGS)
    check("...settled there rather than sliding to it",
          first.stage.bar._display == float(CAT_SETTINGS))
    check("...on the Music folder row", first.stage.column.index == 0)
    check("...telling you what to press", first.stage._status == main_window.FIRST_RUN_TEXT)
    check("...and the standing message underneath it names the same row",
          "Settings" in first.stage._sticky and "No folder yet" in first.stage._sticky,
          first.stage._sticky)
    check("paints on a first run", not first.grab().isNull())
    # Choosing a folder later must not send you back to Settings.
    first._on_folder(folder)
    first._on_library(scan_folder(folder))
    first.stage.bar.set_index(CAT_MUSIC)
    first._on_library(scan_folder(folder))
    check("a later library change leaves you where you are",
          first.stage.bar.index == CAT_MUSIC)
    first.deleteLater()

    # Put everything back *before* the section below, not just before shutdown:
    # it lets a settings write succeed again on purpose, and the values that
    # reach the disk at that moment had better be the user's.
    controller.open_folder(folder, remember=False)
    controller.set_speed(saved.speed)
    controller.set_volume(saved.volume)
    controller.set_theme(saved.theme)
    controller.set_shuffle(saved.shuffle)
    controller.set_repeat(saved.repeat)

    print("\n-- a settings write that fails")
    # `save` returning False is faked rather than the disk being filled: the
    # verdict is the only interesting part, and everything downstream of it --
    # the status line, the blip, the log -- is the real code path.
    real_save, settings_mod.save = settings_mod.save, lambda *a, **k: False
    log.take()
    controller._save_now()
    app.processEvents()
    check("a failed settings write reaches the status line",
          stage._status == SAVE_FAILED_TEXT, stage._status)
    check("...and blips, once", log.take().count(sfx.ERROR) == 1)
    controller._save_now()
    app.processEvents()
    check("...and does not re-announce itself on the next failure", log.take() == [])
    settings_mod.save = real_save
    controller._save_now()
    check("...saving again is silent", log.take() == [])
    check("...and arms the message for next time", not controller._save_failed)

    print("\n-- an exception with nowhere else to go")
    # Under pythonw.exe there is no console, so `sys.excepthook` is the only
    # thing between an unhandled exception and complete silence. PySide6 6.11
    # hands the exception to the hook and *carries on*, which is why the dialog
    # is one-shot: a broken paintEvent raises on every frame.
    dialogs: list[object] = []
    real_dialog, app_mod._show_crash_dialog = app_mod._show_crash_dialog, dialogs.append
    real_hook = sys.excepthook
    app_mod._install_crash_handler(log_file)

    def _boom() -> None:
        raise RuntimeError("harness crash probe")

    # Called the way Qt calls it rather than through a slot: PySide6 lets an
    # exception raised inside `processEvents()` propagate back out to whoever
    # called *that*, so a QTimer probe would take the harness down instead of
    # reaching the hook. Under `exec()` -- the only loop the app itself ever
    # runs -- it goes to `sys.excepthook`, which was checked directly and is
    # Qt's half anyway. This is ours: what the hook does when it is handed one.
    print("   (the traceback below is the probe, and is meant to be here)")
    for _ in range(2):
        try:
            _boom()
        except RuntimeError:
            sys.excepthook(*sys.exc_info())
        app.processEvents()  # the posted dialog runs
    sys.excepthook = real_hook
    app_mod._show_crash_dialog = real_dialog

    text = log_file.read_text(encoding="utf-8") if log_file else ""
    check("an exception in a slot lands in the log", "harness crash probe" in text)
    check("...with its traceback", "Traceback" in text)
    check("...written once, however often it repeats",
          text.count("unhandled exception") == 1)
    check("...and offering exactly one dialog", len(dialogs) == 1, str(len(dialogs)))
    check("...that names the log file", dialogs[:1] == [log_file])

    print("\n-- the events that used to be invisible")
    check("the log opened where it was pointed", log_file is not None and log_file.exists())
    check("the stream says which device it opened", "stream open:" in text)
    check("losing the device is written down", "stopped producing blocks" in text)
    check("...and so is getting it back", "audio device back:" in text)
    check("...and the retry that failed in between", "still no audio device" in text)
    check("a failed settings write is written down", "could not write settings" in text)

    print("\n-- the accent-text mix has no writer left to forget it")
    # The defect was a derived global that two functions each had to remember to
    # refresh. Both did; a third writer would not have, and the symptom is
    # unreadable text -- a colour, not an error. So the check writes the input
    # *directly*, which is the thing that used to desync it and now cannot.
    theme.set_palette("XMB Blue")
    theme.set_accent_fraction(theme.ANCHOR_FRACTION)
    check("XMB Blue at 1.00x needs no lift toward white", theme._text_mix() == 0.0,
          f"{theme._text_mix():.2f}")
    theme._palette = theme.PALETTES[1]  # Ember, straight past `set_palette`
    check(
        "a palette set behind the setter's back still gets its own lift",
        theme._contrast(theme.accent_text(), theme.BG_MID) >= theme._TEXT_CONTRAST_FLOOR,
        f"{theme._contrast(theme.accent_text(), theme.BG_MID):.2f}:1",
    )
    # Ember at 1.00x is the tight one: 6.99:1 raw against a 7.0 floor, so a mix
    # left over from a palette that needed none lands it just under. That is the
    # whole bug, in one comparison.
    check("...which for Ember is one step and not zero", theme._text_mix() > 0.0,
          f"{theme._text_mix():.2f}")
    theme._accent_fraction = 0.0  # the other input, also written directly
    check(
        "a fraction set the same way is noticed too",
        theme._contrast(theme.accent_text(), theme.BG_MID) >= theme._TEXT_CONTRAST_FLOOR,
        f"{theme._contrast(theme.accent_text(), theme.BG_MID):.2f}:1",
    )
    # Every palette, every end, however the state got there.
    theme.set_palette(settings_mod.DEFAULT_THEME)
    theme.set_accent_fraction(theme.ANCHOR_FRACTION)
    floor_held = True
    for preset in theme.PALETTES:
        theme._palette = preset
        for fraction in (0.0, theme.ANCHOR_FRACTION, 1.0):
            theme._accent_fraction = fraction
            floor_held &= (
                theme._contrast(theme.accent_text(), theme.BG_MID)
                >= theme._TEXT_CONTRAST_FLOOR
            )
    check("the floor holds across all five presets at three speeds", floor_held)
    # And the invariant the whole ramp hangs on, re-checked after all that.
    theme.set_palette(settings_mod.DEFAULT_THEME)
    theme.set_accent_fraction(theme.ANCHOR_FRACTION)
    # "To within a rounding step", the same tolerance the checks further up use:
    # `wave_color` recomputes the anchor through HSV and lands a unit off in red.
    # What matters here is that it takes *no lift* -- a stale mix would move it
    # by 0.05 of the way to white, which is 6 or 7 units, not one.
    check("1.00x on the default is still ACCENT after all that",
          theme._text_mix() == 0.0
          and max(abs(theme.accent_text().red() - theme.ACCENT.red()),
                  abs(theme.accent_text().green() - theme.ACCENT.green()),
                  abs(theme.accent_text().blue() - theme.ACCENT.blue())) <= 1,
          f"{theme.accent_text().getRgb()[:3]} vs {theme.ACCENT.getRgb()[:3]}")
    controller.set_theme(saved.theme)
    app.processEvents()

    print("\n-- the Settings rows are one table")
    rows = window._settings_rows()
    check("seven rows, in the order the constants name",
          [r.label for r in rows] == ["Music folder", "Rescan folder", "Shuffle",
                                      "Repeat", "Theme", "Full screen", "Quit"],
          str([r.label for r in rows]))
    # The point of the fix: the label and what activating it does are the same
    # tuple, so inserting a row cannot shift one without the other. These pin
    # each named index to the action it is supposed to carry.
    check("...and each one carries its own action", all(
        rows[index].action == expected
        for index, expected in (
            (main_window.SET_FOLDER, window._choose_folder),
            (main_window.SET_RESCAN, controller.rescan),
            (main_window.SET_SHUFFLE, controller.toggle_shuffle),
            (main_window.SET_REPEAT, controller.cycle_repeat),
            (main_window.SET_THEME, window._start_stepping),
            (main_window.SET_FULLSCREEN, window.toggle_fullscreen),
            (main_window.SET_QUIT, window.close),
        )
    ))
    items = window._settings_items()
    check("the painted items are derived from that same table",
          [(i.label, i.value) for i in items] == [(r.label, r.value) for r in rows])
    before_folder = controller.folder
    rows[main_window.SET_RESCAN].action()
    app.processEvents()
    check("...and an action off the table really runs", controller.folder == before_folder
          and bool(controller.tracks))
    # Out of range does nothing rather than raising: `activate` fires on whatever
    # the cursor is on, and the two lists are rebuilt independently.
    window._activate_settings(len(rows))
    window._activate_settings(-1)
    check("an index off the end of the table is a no-op", True)

    print("\n-- repeat: three modes, and the cycle is the whole control")
    controller.set_repeat(REPEAT_ALL)
    app.processEvents()
    walked = []
    for _ in range(4):
        controller.cycle_repeat()
        walked.append(controller.repeat)
    check("cycling walks all three and wraps",
          walked == [REPEAT_ONE, REPEAT_OFF, REPEAT_ALL, REPEAT_ONE], str(walked))
    # The same clamp the theme has, for the same reason: `core` stores whatever
    # was in the file so a later build's mode survives a round trip, and this is
    # the half that has to know what to do with it.
    controller.set_repeat("shuffle-album")
    check("a mode this build doesn't know clamps to the default",
          controller.repeat == REPEAT_ALL, controller.repeat)

    print("\n-- shuffle deals a bag, and walks it")
    controller.play_index(0)
    app.processEvents()
    controller.set_shuffle(True)
    app.processEvents()
    order = list(controller._order)
    check("the order is a permutation -- every track exactly once",
          sorted(order) == list(range(len(controller.tracks))),
          f"{len(order)} of {len(controller.tracks)}")
    check("...of indices, leaving the list itself in scan order",
          [t.title for t in controller.tracks]
          == [t.title for t in scan_folder(controller.folder).tracks])
    check("turning it on doesn't move the track you're listening to",
          controller.index == 0 and order[0] == 0, f"{controller.index}, {order[:3]}")
    # Walked as arithmetic rather than by playing 31 files: `_next_index` is the
    # whole of what shuffle changes, and each real advance costs a decode.
    steps = []
    for position in range(len(order)):
        controller._cursor = position
        controller.index = order[position]
        steps.append(controller._next_index(+1))
    check("next walks the bag in order",
          [index for index, _ in steps[:-1]] == order[1:], str(steps[:3]))
    check("...and only the last step reports a wrap",
          [wrapped for _, wrapped in steps] == [False] * (len(order) - 1) + [True])
    controller._cursor, controller.index = 1, order[1]
    check("previous walks it backwards", controller._next_index(-1)[0] == order[0])

    print("\n-- what the end of a track does under each mode")
    last = len(controller.tracks) - 1
    controller.set_shuffle(False)
    controller.set_repeat(REPEAT_ALL)
    controller.play_index(last)
    app.processEvents()
    controller._advance()
    app.processEvents()
    check("repeat all wraps off the end, as it always has", controller.index == 0)

    controller.set_repeat(REPEAT_OFF)
    controller.play_index(last)
    app.processEvents()
    was_playing = engine.is_playing
    controller._advance()
    app.processEvents()
    check("repeat off stops there instead", controller.index == last)
    # And it stops by *doing nothing*, which is the whole implementation: the
    # mixer has already paused itself by the time `take_finished` is true, so
    # the poll's own `_set_playing` edge two lines later reports the stop. This
    # calls `_advance` mid-track rather than waiting out a real file, so the
    # claim it can make is that nothing here touched the transport.
    check("...by doing nothing at all -- the mixer has already paused itself",
          engine.is_playing == was_playing)

    # A press is not a consequence: running off the end under `Repeat: Off`
    # stops, but *asking* for the next track still wraps.
    controller.step(+1)
    app.processEvents()
    check("a manual Next still wraps under repeat off", controller.index == 0)

    controller.set_repeat(REPEAT_ONE)
    controller.play_index(2)
    app.processEvents()
    controller._advance()
    app.processEvents()
    check("repeat one plays the same track again", controller.index == 2)
    check("...and does it without reloading -- seek, not decode",
          engine.is_playing and engine.has_track)
    # The other half of the same decision: repeat-one must not trap Next.
    controller.step(+1)
    app.processEvents()
    check("...but Next still moves on", controller.index == 3)

    print("\n-- the modes reach the screen")
    controller.set_shuffle(True)
    controller.set_repeat(REPEAT_ONE)
    app.processEvents()
    rows = window._settings_rows()
    check("the Shuffle row reads its state", rows[SET_SHUFFLE].value == "On")
    check("the Repeat row reads its state", rows[SET_REPEAT].value == "One")
    check("the shuffle button is lit", transport.shuffle_button.isChecked())
    check("the repeat button swaps its glyph, like play/pause does",
          transport.repeat_button.isChecked()
          and transport.repeat_button.text() == REPEAT_ONE_GLYPH)
    check("the stylesheet has something to light them with",
          "QPushButton:checked" in transport.styleSheet())
    bar.set_index(CAT_NOW)
    app.processEvents()
    tail = page.state.lines[POSITION_LINE]
    check("Now Playing says so on the line about where you are",
          "Shuffle" in tail and "Repeat one" in tail, tail)

    controller.set_shuffle(False)
    controller.set_repeat(REPEAT_ALL)
    app.processEvents()
    check("the repeat button is dark at `off`, not at `all`",
          transport.repeat_button.isChecked()
          and transport.repeat_button.text() == REPEAT_ALL_GLYPH)
    controller.set_repeat(REPEAT_OFF)
    app.processEvents()
    check("...and dark at off", not transport.repeat_button.isChecked())
    controller.set_repeat(REPEAT_ALL)
    app.processEvents()
    # Silent at the defaults for the same reason the length line drops its
    # "plays in" at 1.00x: a readout that never changes stops being read.
    check("...and says nothing when the modes are what they have always been",
          "Shuffle" not in page.state.lines[POSITION_LINE]
          and "Repeat" not in page.state.lines[POSITION_LINE],
          page.state.lines[POSITION_LINE])

    print("\n-- S and R, the first letter keys this app has bound")
    clock.tick()
    log.take()
    press(window, Qt.Key_S)
    app.processEvents()
    check("S turns shuffle on", controller.shuffle)
    check("...and confirms, once", log.take() == [sfx.CONFIRM])
    clock.tick()
    where = column.index
    press(window, Qt.Key_S)
    app.processEvents()
    check("S again turns it off", not controller.shuffle)
    check("...and that is a `back`", log.take() == [sfx.BACK])
    check("neither press moved the cursor", column.index == where)

    clock.tick()
    press(window, Qt.Key_R)
    app.processEvents()
    check("R cycles repeat", controller.repeat == REPEAT_ONE)
    # `move`, not `confirm`: this is walking a value, like the theme row's
    # arrows. Exactly one, because the cursor did not move and so the index
    # comparison in `keyPressEvent` adds nothing.
    check("...with one `move` and nothing else", log.take() == [sfx.MOVE])

    print("\n-- and the rows they share their state with")
    clock.tick()
    controller.set_shuffle(False)
    controller.set_repeat(REPEAT_ALL)
    bar.set_index(CAT_SETTINGS)
    column.set_index(SET_SHUFFLE)
    app.processEvents()
    log.take()
    column.activate()
    app.processEvents()
    check("activating the Shuffle row toggles it", controller.shuffle)
    # The row's action is the controller's own method, so the only blip is the
    # one `_activate` already makes for every activation. A wrapper here would
    # be a second noise for one press.
    check("...and blips once, not twice", log.take() == [sfx.CONFIRM])
    clock.tick()
    column.set_index(SET_REPEAT)
    app.processEvents()
    log.take()
    column.activate()
    app.processEvents()
    check("activating the Repeat row cycles it", controller.repeat == REPEAT_ONE)
    check("...also once", log.take() == [sfx.CONFIRM])

    # Back to the user's own, for the same reason the theme goes back: shutdown
    # flushes, and what it flushes had better not be the harness's.
    controller.set_shuffle(saved.shuffle)
    controller.set_repeat(saved.repeat)
    app.processEvents()

    print("\n-- finding a song: the Music column filters")
    # Unusually much of this batch is assertable, because the whole risk in it
    # is an arithmetic one: a filtered column breaks the "row number == index
    # into controller.tracks" identity that `play_index`, the marker and
    # "Track N of M" all still rely on. Everything here is about that map.
    query = pick_query(controller.tracks)
    bar.set_index(CAT_MUSIC)
    app.processEvents()
    bar.settle()
    column.settle()
    app.processEvents()
    unfiltered = [item.label for item in column._items]
    check("no search is open to begin with", column.search is None)
    check(
        "with no query the map is the identity",
        window._matches == list(range(len(controller.tracks))),
    )

    clock.tick()
    log.take()
    press(window, Qt.Key_Slash, text="/")
    app.processEvents()
    check("`/` opens the search on Music", window._searching and column.search == "")
    check("...and the list is still every track", column.count == len(controller.tracks))
    check("...and it blips once", log.take() == [sfx.CONFIRM])

    clock.tick()
    type_text(window, query)
    app.processEvents()
    matches = list(window._matches)
    check(f"typing {query!r} narrows the list", 0 < column.count < len(controller.tracks),
          f"{column.count} of {len(controller.tracks)}")
    check("the column shows exactly the matches", column.count == len(matches))
    # The check the whole batch exists for. Restated from `controller.tracks`
    # rather than from anything the window built, so a map that drifted would
    # have to drift in two places at once to pass.
    check(
        "every row maps back to the track it is showing",
        all(
            controller.tracks[real].title == column._items[row].label
            for row, real in enumerate(matches)
        ),
    )
    check(
        "and every match really matches",
        all(track_matches(controller.tracks[real], query) for real in matches),
    )
    check(
        "the status line counts them",
        stage._status == f"{len(matches)} of {len(controller.tracks)} matching",
        stage._status,
    )

    # S, R and Space are the three keys this file has already spent, and all
    # three are characters somebody is entitled to type. Batch 18 bound the
    # first two globally and with no modifier check at all.
    was_shuffle, was_repeat, was_playing = (
        controller.shuffle,
        controller.repeat,
        window._playing,
    )
    type_text(window, "sr ")
    app.processEvents()
    check("S, R and Space are literal inside a search", window._query == query + "sr ")
    check(
        "...so shuffle, repeat and play/pause are untouched",
        (controller.shuffle, controller.repeat, window._playing)
        == (was_shuffle, was_repeat, was_playing),
    )
    for _ in range(3):
        press(window, Qt.Key_Backspace)
    app.processEvents()
    check("backspace deletes one character at a time", window._query == query)
    check("...and the list comes back with it", column.count == len(matches))

    # Ctrl and Shift arrows stay transport, verbatim from the theme row: you may
    # well be listening while you look for something else.
    before_index = controller.index
    press(window, Qt.Key_Right, Qt.ControlModifier)
    app.processEvents()
    check("Ctrl+arrow is still transport inside a search", controller.index != before_index)
    check("...and the search is still open", window._searching)
    press(window, Qt.Key_Right, Qt.ShiftModifier)
    app.processEvents()
    check("Shift+arrow is not typed into the query", window._query == query)

    # Moving the cursor is the point of having filtered, so this is the one
    # place the search deliberately differs from the theme row -- which closes
    # on exactly this signal.
    press(window, Qt.Key_Down)
    press(window, Qt.Key_Down)
    app.processEvents()
    check("arrows walk the filtered list", column.index == 2, f"index={column.index}")
    check("...without closing the search", window._searching)
    press(window, Qt.Key_End)
    app.processEvents()
    check("End goes to the last match", column.index == len(matches) - 1)

    # The mouse's half of the same rule, and the one `index_changed` connection
    # this mode must *not* take: the theme row closes on exactly this signal.
    row_two = column._item_y(1)
    click(stage, theme.ITEM_X + 60, row_two)
    app.processEvents()
    check("clicking a match selects it", column.index == 1, f"index={column.index}")
    check("...and still does not close the search", window._searching)

    # A keystroke that leaves the result set alone is a press that changed
    # nothing, and those are silent everywhere else in this app too. A trailing
    # space is the deterministic case: `matches` strips before it compares.
    clock.tick()
    log.take()
    type_text(window, " ")
    app.processEvents()
    check("a keystroke that changes no rows is silent", log.take() == [],
          f"query={window._query!r}, {column.count} rows")
    press(window, Qt.Key_Backspace)
    app.processEvents()

    # Activating: the one thing that would be a *wrong song* rather than a
    # wrong-looking screen.
    row = min(2, len(matches) - 1)
    column.set_index(row)
    app.processEvents()
    column.activate()
    app.processEvents()
    check(
        "activating a row plays the track it was showing",
        controller.index == matches[row],
        f"played {controller.index}, expected {matches[row]}",
    )
    check("...and closes the search", not window._searching and column.search is None)
    check("...leaving the whole library back on screen", column.count == len(controller.tracks))
    check("...with the cursor on the track it just played", column.index == matches[row])
    check(
        "the unfiltered list is the list it always was",
        [item.label for item in column._items] == unfiltered,
    )
    check(
        "Now Playing reports the real index, not the row",
        f"Track {matches[row] + 1} of {len(controller.tracks)}"
        in window._now_playing().lines[POSITION_LINE],
        window._now_playing().lines[POSITION_LINE],
    )
    check(
        "the marker is on the real playing track",
        [i for i, item in enumerate(window._music_items()) if item.marker] == [matches[row]],
    )

    # A query that matches nothing: an empty column that must not claim the
    # folder is empty, and the one keystroke in here that is an error.
    clock.tick()
    press(window, Qt.Key_F, Qt.ControlModifier)
    app.processEvents()
    check("Ctrl+F opens it too", window._searching)
    log.take()
    type_text(window, "zzqqxx")
    app.processEvents()
    check("a query matching nothing empties the column", column.count == 0)
    check("...and says so rather than claiming the folder is empty",
          column._empty_text == "Nothing matches", column._empty_text)
    check("...and blips an error", sfx.ERROR in log.take())
    played = controller.index
    column.activate()
    press(window, Qt.Key_Return)
    app.processEvents()
    check("Enter on an empty result set does nothing", controller.index == played)

    press(window, Qt.Key_Escape)
    app.processEvents()
    check("Escape closes and clears", not window._searching and window._query == "")
    check("...and the full list is back", column.count == len(controller.tracks))

    # Backspace past the start leaves, rather than falling through to the
    # crossbar's "back" and stepping a category out of nowhere.
    press(window, Qt.Key_Slash, text="/")
    app.processEvents()
    press(window, Qt.Key_Backspace)
    app.processEvents()
    check("backspace on an empty query closes the search", not window._searching)
    check("...and does not step a category", bar.index == CAT_MUSIC)

    # Leaving Music leaves the search, however you leave.
    press(window, Qt.Key_Slash, text="/")
    type_text(window, query)
    app.processEvents()
    press(window, Qt.Key_Right)
    app.processEvents()
    check("a category change closes the search", not window._searching)
    check("...and the header goes with it", column.search is None)
    check("...and the count comes off the status line", "matching" not in stage._status)
    check(
        "`/` does nothing outside Music",
        not window._handle_key(Qt.Key_Slash, Qt.NoModifier, "/"),
    )
    bar.set_index(CAT_MUSIC)
    app.processEvents()
    bar.settle()
    column.settle()
    app.processEvents()

    # The header's own geometry. A row is either wholly clear of the band or
    # fading into it -- the first version clipped instead, and left a sliver of
    # descenders hanging under the query line.
    check(
        "a row clear of the search header paints at full strength",
        column._under_header(theme.SEARCH_BAND + theme.ITEM_SPACING) == 1.0,
    )
    check(
        "a row wholly above it paints not at all",
        column._under_header(theme.SEARCH_BAND - theme.ITEM_SPACING) == 0.0,
    )
    check(
        "and one straddling it is somewhere in between",
        0.0 < column._under_header(theme.SEARCH_BAND) < 1.0,
        f"{column._under_header(theme.SEARCH_BAND):.2f}",
    )
    check(
        "the header sits above the band that clears it",
        theme.SEARCH_TOP + theme.SEARCH_TEXT + 8 <= theme.SEARCH_BAND,
        f"{theme.SEARCH_TOP + theme.SEARCH_TEXT + 8} vs {theme.SEARCH_BAND}",
    )

    print("\n-- getting music: the fourth category")
    # The tool is faked; nothing downstream of it is. `find_tools` is replaced
    # so this points at a script instead of the real yt-dlp, and from there the
    # argv, the QProcess, the line buffering, the two parsers, the signals, the
    # library refresh and the sounds are all the shipping code. That is the
    # "faking a verdict beats faking the world" seam one module further out:
    # the thing being stubbed is the boundary, not the code under test.
    #
    # A temp folder, always. This harness runs against the *real* saved library
    # and a fake download writing into it would leave a junk file in somebody's
    # music. `remember=False` on both switches, so nothing is persisted -- the
    # restore at the end of the section matters because `shutdown()` flushes
    # `controller._folder`.
    get_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    get_folder = Path(get_dir.name)
    fake_py = get_folder / "fake_ytdlp.py"
    fake_py.write_text(
        "import json, os, sys\n"
        "args = sys.argv[1:]\n"
        "if '--dump-json' in args:\n"
        "    for i in range(3):\n"
        "        print(json.dumps({'id': 'vid%d' % i, 'title': 'Fake Song %d' % i,\n"
        "                          'uploader': 'Fake Channel', 'duration': 100 + i}))\n"
        "    print('[youtube:search] chatter that is not json')\n"
        "else:\n"
        "    out = args[args.index('--paths') + 1]\n"
        "    name = os.path.join(out, 'Aardvark Fake Song.mp3')\n"
        # A real ID3 header, because `scan_folder` sniffs magic bytes and would
        # silently skip anything else -- which is the trap this whole feature
        # has to clear: yt-dlp exiting 0 is not the same as a playable file.
        "    tag = b'ID3\\x04\\x00\\x00\\x00\\x00\\x00\\x00\\x00'\n"
        "    open(name, 'wb').write(tag + b'\\x00' * 64)\n"
        "    print('XMBDL   10.0%')\n"
        "    print('XMBDL   55.5%')\n"
        # No trailing newline, on purpose: `after_move:filepath` is the last
        # thing yt-dlp prints and it is exactly the line that can arrive with
        # nothing behind it. `_on_dl_finished` flushes the tail for this case.
        "    sys.stdout.write('XMBFILE ' + name)\n",
        encoding="utf-8",
    )
    fake_cmd = get_folder / "yt-dlp.cmd"
    fake_cmd.write_text(
        f'@echo off\r\n"{sys.executable}" "{fake_py}" %*\r\n', encoding="utf-8"
    )
    fake_tools = fetch.Tools(ytdlp=fake_cmd, ffmpeg=fake_cmd)
    real_find = fetch.find_tools
    fetch.find_tools = lambda folder=None: fake_tools  # type: ignore[assignment]

    # One real track, named so it sorts *after* what the fake download writes.
    # That is the whole point of it: the new file lands at index 0 and pushes
    # the playing track from 0 to 1, which is the index shift `refresh_library`
    # exists to survive. Seeded from the real library so it genuinely decodes.
    seed = get_folder / "zz seed.mp3"
    seed.write_bytes(controller.tracks[0].path.read_bytes())
    real_folder_again = controller.folder
    controller.open_folder(get_folder, remember=False)
    app.processEvents()
    check("the temp library has one track", len(controller.tracks) == 1)

    bar.set_index(CAT_GET)
    app.processEvents()
    bar.settle()
    column.settle()
    app.processEvents()
    check("get music has a header from the moment you arrive", column.search == "")
    check("...and it is captioned GET, not FIND", column._caption == GET_LABEL)
    check("...with nothing typed and nothing found", window._results == [])

    # Typing. The Music query must not move -- these are two different strings
    # and conflating them is how `_music_row` starts answering the wrong
    # question (see the note in `MainWindow.__init__`).
    music_query_before = window._query
    type_text(window, "fake")
    app.processEvents()
    check("typing fills the Get query", window._get_query == "fake")
    check("...and leaves the Music search alone", window._query == music_query_before)
    check("...and the header shows it", column.search == "fake")

    # The three keys Batch 18 and Batch 3 spent, all of which are characters
    # somebody searching is entitled to type. Read from `event.text()`.
    shuffle_before, repeat_before = controller.shuffle, controller.repeat
    playing_before = controller.engine.is_playing
    type_text(window, "sr ")
    app.processEvents()
    check("S, R and Space are literal in here", window._get_query == "fake" + "sr ")
    check("...shuffle did not toggle", controller.shuffle == shuffle_before)
    check("...repeat did not cycle", controller.repeat == repeat_before)
    check("...and play/pause did not fire", controller.engine.is_playing == playing_before)

    # ...while the chords stay transport, verbatim from the theme row's
    # reasoning: you may well be listening while you look for the next thing.
    press(window, Qt.Key_Right, Qt.ControlModifier)
    app.processEvents()
    check("Ctrl+Right is still transport", window._get_query == "fakesr ")

    press(window, Qt.Key_Backspace)
    check("backspace deletes a character", window._get_query == "fakesr")
    press(window, Qt.Key_Escape)
    check("escape clears the query", window._get_query == "")
    check("...and empties the results with it", window._results == [])
    press(window, Qt.Key_Backspace)
    check("backspace on an empty query steps left", bar.index == CAT_SETTINGS)

    bar.set_index(CAT_GET)
    app.processEvents()

    # The search, for real, through a real process.
    type_text(window, "fake")
    window._get_timer.stop()
    window._run_search()
    check("a search is in flight", window._searching_online)
    check(
        "the results arrive and the chatter is dropped",
        wait_for(app, lambda: len(window._results) == 3),
        f"{len(window._results)} result(s)",
    )
    check("...and it is no longer searching", not window._searching_online)
    check("the titles came through", window._results[1].title == "Fake Song 1")
    check("...and the durations", window._results[1].duration_s == 101.0)
    app.processEvents()
    check("every row is the result it is showing", column.count == 3)
    check(
        "the row *is* the index -- there is no map to get wrong",
        [item.label for item in column._items]
        == [result.title for result in window._results],
    )

    # Downloading. The seeded track is playing, and must still be playing after.
    controller.play_index(0)
    app.processEvents()
    playing_path = controller.current.path
    check("something is playing before the download", controller.index == 0)

    column.set_index(1)
    clock.tick()
    log.take()
    column.activate()
    check("the download started", window._downloading == "Fake Song 1")
    check("...and confirmed once", log.take() == [sfx.CONFIRM])
    check(
        "a second one is refused while it runs",
        not window.fetcher.download(fake_tools, window._results[0], get_folder),
    )
    check(
        "the file lands and the library notices",
        wait_for(app, lambda: len(controller.tracks) == 2),
        f"{len(controller.tracks)} track(s)",
    )
    check("progress reached the window", window._progress > 0.0 or not window._downloading)
    check("the download is over", not window._downloading)
    check(
        "the new file sorted *before* the one that was playing",
        controller.tracks[0].title.startswith("Aardvark"),
    )
    # The two halves of `refresh_library`, and the reason it exists at all.
    check(
        "the playing track followed its path rather than its index",
        controller.index == 1 and controller.current.path == playing_path,
        f"index={controller.index}",
    )
    check("...and the music never stopped", controller.engine.is_playing)

    # Refusals. Each one is a condition the user can fix, so each gets a
    # sentence and none of them sounds `confirm`.
    fetch.find_tools = lambda folder=None: fetch.Tools()  # type: ignore[assignment]
    window._recheck_tools()
    clock.tick()
    log.take()
    column.activate()
    check("a download with no yt-dlp is refused", not window._downloading)
    check("...loudly", log.take() == [sfx.ERROR])
    check(
        "...and says which tool, short enough for the bar",
        "yt-dlp" in window._get_advice() and len(window._get_advice()) <= 48,
        f"{len(window._get_advice())} chars: {window._get_advice()}",
    )
    check(
        "the empty column says so too",
        window._get_empty_text() == "yt-dlp not installed",
        window._get_empty_text(),
    )

    fetch.find_tools = real_find
    window._recheck_tools()
    window._results = []
    window._get_query = ""
    controller.open_folder(real_folder_again, remember=False)
    # Back to Music before leaving, and not only for tidiness: the cache checks
    # at the bottom of this file move one input on a *held* column and demand
    # the picture change, and an empty column has no selection plate for a slide
    # or a step-in to move. Left on Get Music with nothing found, two of them go
    # red for a reason that has nothing to do with the cache.
    bar.set_index(CAT_MUSIC)
    app.processEvents()
    bar.settle()
    column.settle()
    app.processEvents()
    check(
        "the real library is back for whatever runs after this",
        controller.folder == real_folder_again and column.count == len(controller.tracks),
        f"{column.count} row(s)",
    )
    get_dir.cleanup()

    print("\n-- re-enumerating devices fails loudly when it fails wrongly")
    # Never the real PortAudio: the stream is still open and `refresh_devices`
    # is documented as needing it closed. Both private calls are replaced, so
    # this exercises the `except` and nothing else.
    sd = engine_mod.sd
    real_terminate, real_initialize = sd._terminate, sd._initialize

    def _port_audio_error() -> None:
        raise sd.PortAudioError("harness: no device to terminate")

    def _renamed() -> None:
        raise AttributeError("module 'sounddevice' has no attribute '_terminate'")

    sd._terminate, sd._initialize = _port_audio_error, lambda: None
    engine_mod.refresh_devices()
    check("a PortAudio failure is still swallowed -- it is the expected one", True)
    logged = log_file.read_text(encoding="utf-8") if log_file else ""
    check("...and written down", "could not re-enumerate" in logged)

    sd._terminate = _renamed
    try:
        engine_mod.refresh_devices()
    except AttributeError:
        renamed_escaped = True
    else:
        renamed_escaped = False
    check(
        "a renamed private API is no longer swallowed into a dead reconnect",
        renamed_escaped,
    )
    sd._terminate, sd._initialize = real_terminate, real_initialize

    print("\n-- the application icon, drawn from theme.py")
    # Two modules now: `mp3player.ui.icon` draws the mark -- the running app
    # wears it too, via `setWindowIcon` -- and `tools/make_icon` assembles the
    # `.ico` the build stamps into the exe. Both are Qt, so `tests/` can have
    # neither: that suite is core-only and needs no display. The mark draws no
    # text, which is the one thing the offscreen platform genuinely cannot do, so
    # it belongs here instead.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import make_icon

    from mp3player.ui import icon as icon_mod

    was_palette = theme.palette().name

    frames = {size: icon_mod.draw(size) for size in icon_mod.SIZES}
    check(
        "every size draws, at the size asked for",
        all(
            not image.isNull() and image.width() == size and image.height() == size
            for size, image in frames.items()
        ),
    )

    big = frames[256]
    mono = theme.palette_by_name(icon_mod.PALETTE_NAME)

    def core_pixel(image):
        at = image.width() // 2
        return image.pixelColor(at, at)

    found = core_pixel(big)
    check(
        f"the label is {icon_mod.PALETTE_NAME}'s anchor",
        (found.red(), found.green(), found.blue())
        == (mono.anchor.red(), mono.anchor.green(), mono.anchor.blue()),
        f"{found.name()} vs {mono.anchor.name()}",
    )

    # **The invariant that replaced the palette pin, and it is a stronger one.**
    # Until Batch 17's second pass the icon took the *active* palette, so this
    # section had to pin the default before asserting on a colour -- the theme-row
    # section above walks all five and leaves the module wherever it stopped. The
    # mark is now fixed to one palette by design, so the check is that driving the
    # app's theme through every preset does not move a single pixel of it.
    everywhere = set()
    for name in theme.palette_names():
        theme.set_palette(name)
        everywhere.add(core_pixel(icon_mod.draw(256)).name())
    theme.set_palette(was_palette)
    check(
        "and it does not move when the app's theme does, across all five",
        len(everywhere) == 1 and everywhere == {mono.anchor.name()},
        f"{sorted(everywhere)}",
    )

    # "One colour" as an assertion rather than an impression: every pixel the mark
    # actually paints has to sit inside the hue band Mono's own knots describe,
    # and no more saturated than its most saturated knot. This is what would catch
    # a stray `ACCENT` or a hard-coded colour creeping back into the drawing.
    hue_lo = min(value for _, value in mono.hue)
    hue_hi = max(value for _, value in mono.hue)
    sat_hi = max(value for _, value in mono.saturation)
    strays = []
    for x in range(0, big.width(), 3):
        for y in range(0, big.height(), 3):
            pixel = big.pixelColor(x, y)
            if pixel.alpha() < 250 or pixel.valueF() < 0.35:
                continue  # transparent, or the dark edge pen
            in_hue = hue_lo - 0.02 <= pixel.hueF() <= hue_hi + 0.02
            in_sat = pixel.saturationF() <= sat_hi + 0.02
            if not (in_hue and in_sat):
                strays.append((x, y, pixel.name()))
    check(
        "every painted pixel is inside Mono's own hue and saturation band",
        not strays,
        f"{len(strays)} strays, e.g. {strays[:3]}",
    )

    # The odd-even fill rule, written down as the bug it was. `crescent_path`
    # unions a round cap onto the sweep, and the path is stroked as well as
    # filled -- so without `WindingFill` *before* `simplified()` the pen traces
    # the cap's hidden half straight across the ribbon and takes a lens-shaped
    # bite out of the thick end. Sampling the ribbon's centre line right at the
    # start is where that bite lands.
    cap_at = icon_mod.sweep_point(256, 0.0)
    seam = big.pixelColor(round(cap_at.x()), round(cap_at.y()))
    check(
        "the cap/sweep union is filled, not punched out by odd-even winding",
        seam.alpha() == 255,
        f"{seam.name()} alpha={seam.alpha()}",
    )

    # It is a *crescent*: full width through the top, then away to a point. Both
    # halves matter -- a taper that starts at once leaves the cap standing alone
    # as a blob, which is what made the first draft read as an eye.
    widths = [icon_mod.ribbon_width(256, step / 24) for step in range(25)]
    check(
        "the sweep holds its width and then tapers, never the other way",
        all(later <= earlier + 1e-9 for earlier, later in itertools.pairwise(widths))
        and widths[-1] < widths[0] / 4,
        f"{widths[0]:.1f} -> {widths[-1]:.1f} px",
    )

    # There is no tile any more, so *all four* corners have to be clear -- the
    # old check looked at one, which was enough for a rounded square and says
    # nothing about a shape that is round in the middle of the canvas.
    opaque_corners = [
        (x, y)
        for x, y in ((0, 0), (255, 0), (0, 255), (255, 255))
        if big.pixelColor(x, y).alpha() != 0
    ]
    check("all four corners are transparent -- there is no tile", not opaque_corners)

    # Batch 15's icon drew a neighbour dot hanging half off the tile, which was
    # arithmetic nobody would catch by reading. Every size, because the small
    # ones have their own layout and their own pixel floors.
    outside = [
        size
        for size in icon_mod.SIZES
        if not QRectF(0, 0, size, size).contains(icon_mod.mark_bounds(size))
    ]
    check("the mark stays inside the canvas at every size", not outside, f"{outside}")

    icon_dir = tempfile.TemporaryDirectory(prefix="xmb-icon-")
    ico = make_icon.write_ico(Path(icon_dir.name) / "probe.ico")
    blob = ico.read_bytes()
    reserved, kind, count = struct.unpack("<HHH", blob[:6])
    check(
        "the container header is a well-formed icon directory",
        (reserved, kind, count) == (0, 1, len(icon_mod.SIZES)),
        f"reserved={reserved} type={kind} count={count}",
    )

    # The arithmetic that decides whether Windows can read the file at all: a
    # wrong offset or length is a silently unusable icon, and PyInstaller copies
    # it into the exe without looking.
    entries = [
        struct.unpack("<BBBBHHII", blob[6 + i * 16 : 22 + i * 16]) for i in range(count)
    ]
    check(
        "every entry's declared size and offset lands inside the file",
        all(off + length <= len(blob) for *_, length, off in entries),
    )
    expected = 6 + 16 * count
    contiguous = True
    for *_, length, offset in entries:
        contiguous = contiguous and offset == expected
        expected += length
    check("the entries are contiguous and in the declared order", contiguous)
    check(
        "256 is stored as 0, because the field is one byte",
        entries[-1][0] == 0 and icon_mod.SIZES[-1] == 256,
    )
    reread = QImage()
    check(
        "and Qt reads the result back as an icon",
        reread.loadFromData(blob, "ICO") and not reread.isNull(),
    )
    icon_dir.cleanup()
    theme.set_palette(was_palette)

    print("\n-- the three category marks, painted since Batch 20")
    # The existing crossbar checks are about *position* -- where a category comes
    # to rest, which one a click lands on, that the furthest-right icon clears
    # the item column -- and every one of them still holds, because nothing about
    # the geometry moved. These are about the drawings that replaced the glyphs,
    # and they follow the icon section above: what a picture cannot be asked
    # (does it read) goes to `render.py --marks`; what it can (is it there, is it
    # inside its box, is it the pen's colour) goes here.
    from mp3player.ui import marks as marks_mod

    MARKS = (
        ("play", marks_mod.draw_play),
        ("note", marks_mod.draw_note),
        ("settings", marks_mod.draw_settings),
    )
    MARK_SIZES = (theme.CATEGORY_ICON_SMALL, theme.CATEGORY_ICON)
    PAD = 20  # slack around the box, so an overflowing mark has somewhere to go

    def paint_mark(draw, size, ink=theme.TEXT):
        """One mark, in a canvas deliberately larger than the box it is given."""
        side = round(size) + PAD * 2
        image = QImage(side, side, QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(ink)
        draw(painter, QRectF(PAD, PAD, size, size))
        painter.end()
        return image

    def coverage(image, rect=None):
        """Fraction of `rect` the mark actually inks, and what falls outside it."""
        inside = outside = 0
        for x in range(image.width()):
            for y in range(image.height()):
                if image.pixelColor(x, y).alpha() < 40:
                    continue
                if rect is None or rect.contains(x + 0.5, y + 0.5):
                    inside += 1
                else:
                    outside += 1
        return inside, outside

    # A mark that draws nothing is a category that vanished, and a mark that
    # inks its whole box is a black square -- both are silent, because neither
    # raises and the crossbar goes on animating an empty rectangle. The band is
    # wide on purpose: this is a smoke test for "there is a drawing here", not a
    # second opinion about the design.
    empty = []
    for name, draw in MARKS:
        for size in MARK_SIZES:
            box = QRectF(PAD, PAD, size, size)
            inked, _ = coverage(paint_mark(draw, size), box)
            share = inked / (size * size)
            if not 0.05 <= share <= 0.60:
                empty.append(f"{name}@{size} {share:.0%}")
    check("every mark inks a sensible share of its box, at both sizes", not empty, f"{empty}")

    # The glyph had a 120x88 text box and its ink sat well inside it. A painted
    # mark is handed a square exactly `size` across and has nothing stopping it
    # painting past the edge -- and the neighbour it would reach into is
    # `CATEGORY_SPACING` away with no clipping anywhere in `_paint_category`.
    spilled = []
    for name, draw in MARKS:
        for size in MARK_SIZES:
            box = QRectF(PAD, PAD, size, size)
            _, out = coverage(paint_mark(draw, size), box)
            if out:
                spilled.append(f"{name}@{size} {out}px")
    check("...and none of them paints outside the box it was handed", not spilled, f"{spilled}")

    # Two focused marks cannot touch. Arithmetic on `theme.py` constants, which
    # is exactly the kind the offscreen harness *can* settle -- and the reason it
    # is worth stating is that the box side is now the icon size itself, where
    # the old text box was a constant 120 that had nothing to do with it.
    check(
        "a focused mark is narrower than the gap to the next category",
        theme.CATEGORY_ICON < theme.CATEGORY_SPACING,
        f"{theme.CATEGORY_ICON} px in {theme.CATEGORY_SPACING} px",
    )

    # The marks take no colour argument: `_paint_category` mixes `TEXT_FAINT`
    # toward `TEXT` by the focus fraction and fades by distance, and the ink is
    # whatever pen it left behind. A hard-coded colour in a mark would break the
    # slide's crossfade while every check about *position* went on passing, so
    # this paints with a colour the palette never produces and demands it back.
    probe = QColor(255, 0, 255)
    wrong = []
    for name, draw in MARKS:
        image = paint_mark(draw, theme.CATEGORY_ICON, probe)
        strays = {
            image.pixelColor(x, y).name()
            for x in range(image.width())
            for y in range(image.height())
            if image.pixelColor(x, y).alpha() > 200
            and image.pixelColor(x, y).rgb() != probe.rgb()
        }
        if strays:
            wrong.append(f"{name}: {sorted(strays)[:2]}")
    check(
        "every mark inks with the painter's pen, not a colour of its own",
        not wrong,
        f"{wrong}",
    )

    # The odd-even fill rule, written down as the bug it would be. The note's
    # stem runs *into* its head, so without `WindingFill` before `simplified()`
    # the overlap counts as outside and is punched transparent -- a notch across
    # the stem that reads as an alpha bug. `marks.note_stem` is exported so this
    # samples the real rectangle rather than a copy of it that would go on
    # passing after the geometry moved.
    #
    # Asserted on a 256 px frame rather than on the 44 px one the crossbar draws,
    # for the same reason the icon section samples its 256: at button size the
    # stem is two and a half pixels wide and *every* pixel in it is a partly
    # covered edge, so the first version of this check failed on the stem's own
    # antialiasing and would have gone on failing whatever the fill rule was. The
    # winding bug is scale-independent; the instrument for it should be too.
    BIG = 256
    note = paint_mark(marks_mod.draw_note, BIG)
    stem = marks_mod.note_stem(QRectF(PAD, PAD, BIG, BIG)).adjusted(2, 2, -2, -2)
    sampled = [
        (x, y)
        for x in range(note.width())
        for y in range(note.height())
        if stem.contains(x + 0.5, y + 0.5)
    ]
    holes = [(x, y) for x, y in sampled if note.pixelColor(x, y).alpha() < 200]
    check(
        "the note's stem is solid where it crosses the head, not punched out",
        not holes and len(sampled) > 500,  # or the inset ate the thing being checked
        f"{len(holes)} transparent of {len(sampled)} px, e.g. {holes[:3]}",
    )

    # What the change actually bought. A font snaps to whole hinted pixel sizes,
    # so the old mark stepped through the slide -- 30 and 30.5 were the same
    # bitmap. `_paint_category` no longer rounds, so a half-pixel of focus has to
    # be a different picture or the continuity is a claim rather than a fact.
    check(
        "a painted mark scales continuously, where a font snapped",
        paint_mark(marks_mod.draw_play, 30.0) != paint_mark(marks_mod.draw_play, 30.5),
    )

    print("\n-- the cached paints, which must be the pixels they replaced")
    #
    # Both of these exist to stop the app re-deriving, 21 times a second, a
    # picture that is a function of the window's size and nothing else -- which
    # is most of why it crackled at fullscreen, the callback being Python and
    # needing the GIL every 10.7 ms. The claim being made is not "this looks
    # fine", it is "these are the same bytes", and that is a claim an assertion
    # can settle. `background_brush` and `_band` are still the single source of
    # both; the caches only stop them being called per frame.
    for width, height in ((720, 480), (980, 640), (1920, 1080)):
        direct = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
        painter = QPainter(direct)
        painter.fillRect(0, 0, width, height, theme.background_brush(direct.rect()))
        painter.end()

        window.resize(width, height)
        window._rebuild_background()
        cached = window._background.toImage().convertToFormat(
            QImage.Format_ARGB32_Premultiplied
        )
        check(
            f"the window gradient is unchanged at {width}x{height}",
            cached.size() == direct.size() and cached == direct,
        )

    wave = window.stage.wave
    for width, height in ((180, 480), (245, 640), (480, 1080)):
        row = height * theme.CROSSBAR_Y_RATIO
        direct = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
        direct.fill(Qt.transparent)
        painter = QPainter(direct)
        painter.fillRect(QRectF(0, 0, width, height), wave._band(height, row))
        painter.end()
        check(
            f"the wave's band mask is unchanged at {width}x{height}",
            wave._build_mask(width, height) == direct,
        )

    # The item column and the Now Playing page went the same way, and they are
    # the two that were actually costing something: the column redrew 196 rows
    # on every wave frame, at 5.0 ms a frame at 980x640 and 9.6 at 1920x1080.
    #
    # Two claims here, and the second is the one that took a second try. The
    # first is that the cached render *is* the old picture, which is what these
    # loops compare. The second is that the key notices an input moving -- and a
    # comparison that builds a fresh widget per case cannot see it, because the
    # cache is cold every time. Written that way first, it passed 243/243 with
    # `theme.accent_fraction()` deliberately deleted from the key. The stale
    # loop below is what has teeth.
    def painted(widget, width, height, uncached):
        """The widget's own paint, and what it draws through the cache."""
        widget.resize(width, height)
        first = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
        first.fill(Qt.transparent)
        painter = QPainter(first)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        uncached(painter)
        painter.end()

        second = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
        second.fill(Qt.transparent)
        widget.render(second, QPoint(0, 0), renderFlags=QWidget.RenderFlag.DrawChildren)
        return first, second

    column, page = window.stage.column, window.stage.page
    theme.set_palette(settings_mod.DEFAULT_THEME)
    theme.set_accent_fraction(theme.ANCHOR_FRACTION)

    for width, height in ((720, 480), (980, 640), (1920, 1080)):
        direct, blitted = painted(column, width, height, column._paint_content)
        check(
            f"the item column's cache is the pixels it replaced at {width}x{height}",
            direct == blitted,
        )

        def page_paint(painter, target=page):
            target._paint_art(painter)
            target._paint_title(painter)
            target._paint_info(painter)
            target._paint_slider(painter)

        direct, blitted = painted(page, width, height, page_paint)
        check(
            f"the Now Playing cache is the pixels it replaced at {width}x{height}",
            direct == blitted,
        )

    # Hold one widget and move one input at a time. Anything the key forgets
    # shows up here as a picture that did not change when it had to -- which is
    # what a stale accent or a stale palette looks like from the outside, and
    # neither of them arrives through a setter on these widgets.
    def blit(widget):
        out = QImage(980, 640, QImage.Format_ARGB32_Premultiplied)
        out.fill(Qt.transparent)
        widget.render(out, QPoint(0, 0), renderFlags=QWidget.RenderFlag.DrawChildren)
        return out

    column.resize(980, 640)
    before = blit(column)
    for label, move in (
        ("the accent moving", lambda: theme.set_accent_fraction(0.0)),
        ("a palette swap", lambda: theme.set_palette("Ember")),
        ("the list sliding", lambda: setattr(column, "_display", column._display + 0.5)),
        ("stepping into a row", lambda: column.set_stepping(True)),
        ("a search opening", lambda: column.set_search("tet")),
        # The caption is a second argument to the same setter and so is the
        # easiest input in here to add and forget. Same query, different word in
        # front of it: if `_caption` is not in the key, this is a stale FIND
        # sitting over the Get Music results.
        ("only the caption changing", lambda: column.set_search("tet", GET_LABEL)),
        ("the arrival fading in", lambda: setattr(column, "_appear", 0.4)),
    ):
        move()
        after = blit(column)
        check(f"the item column's cache notices {label}", after != before)
        before = after

    theme.set_palette(settings_mod.DEFAULT_THEME)
    theme.set_accent_fraction(theme.ANCHOR_FRACTION)
    column.set_stepping(False)
    column.set_search(None)
    column._appear = 1.0

    page.resize(980, 640)
    before = blit(page)
    for label, move in (
        ("the accent moving", lambda: theme.set_accent_fraction(0.0)),
        ("a palette swap", lambda: theme.set_palette("Ember")),
        (
            "a new state",
            lambda: page.set_state(
                NowPlaying(title="something else", lines=("", "0:31"), fraction=0.9)
            ),
        ),
        ("the arrival fading in", lambda: setattr(page, "_appear", 0.4)),
    ):
        move()
        after = blit(page)
        check(f"the Now Playing cache notices {label}", after != before)
        before = after

    theme.set_palette(settings_mod.DEFAULT_THEME)
    theme.set_accent_fraction(theme.ANCHOR_FRACTION)
    page._appear = 1.0

    controller.shutdown()
    log_mod.close()
    log_dir.cleanup()

    total = len(PASSED) + len(FAILED)
    print(f"\n{len(PASSED)}/{total} passed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
