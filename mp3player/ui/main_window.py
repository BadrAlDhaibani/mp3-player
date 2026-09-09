"""The XMB shell.

This is the file Batch 3 said would be thrown away, and it was: nothing of the
ugly window survives except the signal names it connected to. `PlayerController`
is untouched, which is the only real proof that the seam in CLAUDE.md was worth
drawing -- the whole front end changed and `core/` never noticed.

Layout, top to bottom: the chrome strip (`chrome.py`), the stage (crossbar plus
item column, overlapping siblings), and the transport bar. The stage owns the
mouse and this window owns the keyboard; the two child widgets only paint and
hit-test.

Three categories, decided with the user: Now Playing, Music, Settings.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication, QFileDialog, QVBoxLayout, QWidget

from mp3player.core import fetch, library
from mp3player.core import log as log_mod
from mp3player.core import settings as settings_mod
from mp3player.core.library import ScanResult
from mp3player.ui import marks, theme
from mp3player.ui.chrome import ChromeWindow
from mp3player.ui.controller import (
    REPEAT_ALL,
    REPEAT_OFF,
    REPEAT_ONE,
    SEEK_STEP,
    PlayerController,
)
from mp3player.ui.fetcher import Fetcher
from mp3player.ui.sounds import Sounds
from mp3player.ui.widgets.crossbar import Category, Crossbar
from mp3player.ui.widgets.item_column import GET_LABEL, Item, ItemColumn
from mp3player.ui.widgets.now_playing import NowPlaying, NowPlayingPage
from mp3player.ui.widgets.transport import TransportBar, clock
from mp3player.ui.widgets.wave import WaveBackground

CAT_NOW, CAT_MUSIC, CAT_SETTINGS, CAT_GET = 0, 1, 2, 3

# The Settings rows, by position. `ItemColumn` activates by index and has no
# notion of an id, so anything outside this file that wants to talk about a
# particular row -- the harness does -- says so by name rather than by counting.
#
# These used to be load-bearing: the rows and their dispatch were two lists in
# the same order, and Batch 10 inserting `Theme` in the middle shifted `Full
# screen` and `Quit` so that activating one ran the other's branch. Naming the
# indices made that a rename instead of a silent misfire, but it did not remove
# the requirement that the two lists agree. `_settings_rows` does: the label and
# what activating it does are now one tuple, so there is no second order to keep.
SET_FOLDER, SET_RESCAN, SET_SHUFFLE, SET_REPEAT, SET_THEME, SET_FULLSCREEN, SET_QUIT = (
    range(7)
)


@dataclass(frozen=True, slots=True)
class SettingsRow:
    """A Settings row: what it says, what it says on its right, what it does.

    `action` returns whatever it likes and nothing looks -- `QWidget.close`
    returns a bool, `rescan` returns None, and a row that had to report success
    would be a row with a status line of its own.
    """

    label: str
    value: str
    action: Callable[[], object]


# The marks are painted, not glyphs -- see `ui/marks.py`. A fifth category still
# means moving `theme.ITEM_X`, not just appending here; that constraint is about
# the bar's width and is unaffected by what fills it. Batch 23 moved it once, to
# 400, and the arithmetic for the next one is written out beside the constant.
#
# Get Music is last on purpose. The three before it are things you do with music
# you have, in the order you reach for them; getting more is the outlier, and
# putting it at the far end also keeps every existing category index unchanged --
# a settings file, a harness check or a habit that says "Settings is 2" still
# means what it did.
CATEGORIES = (
    Category(marks.draw_play, "Now Playing"),
    Category(marks.draw_note, "Music"),
    Category(marks.draw_settings, "Settings"),
    Category(marks.draw_get, "Get Music"),
)

STATUS_MS = 6000  # how long a failure line stays up
GET_DEBOUNCE_MS = 600  # typing stops -> a search goes out

_log = log_mod.get("window")
PAGE = 5  # items per PageUp/PageDown
SPEED_STEP = 0.01  # one Up/Down press on the Now Playing page

# Where every "there is no music" sentence points. One destination, spelled the
# same way each time: the row it names is the row the first run opens on.
_SETTINGS_ROW = "Settings ▸ Music folder"

DEVICE_LOST_TEXT = "Audio device lost  --  reconnecting"
FIRST_RUN_TEXT = "Press Enter to choose a music folder"


def empty_reason(error: str | None, folder: Path | None) -> str:
    """Why there is nothing to play. The state, not the cure.

    `core/library` reports which of these it was as a bare token, and this is
    where it becomes words -- once, so the empty column and the status line
    cannot drift into two spellings of the same thing.

    Kept short because of where it goes: the empty column draws it at the item
    size, and at 720 px the version that carried "-- Settings ▸ Music folder"
    along with it ran off the right edge mid-word. `empty_advice` is the one
    that says where to go, in the smaller type that has room for it.
    """
    name = folder.name if folder is not None else ""
    if error == library.NO_FOLDER or folder is None:
        return "No folder yet"
    if error == library.MISSING:
        return f"{name} is gone"
    if error == library.UNREADABLE:
        return f"Can't read {name}"
    return f"No playable MP3s in {name}"


def empty_advice(error: str | None, folder: Path | None) -> str:
    """The same reason, plus the one row that fixes any of them."""
    return f"{empty_reason(error, folder)}  --  {_SETTINGS_ROW}"


class XmbStage(QWidget):
    """The cross itself: the wave, the crossbar, the item column, the page.

    All four are transparent to the mouse so this one widget can decide what a
    click meant -- they overlap, and letting any of them eat events would make
    the others unclickable. The wave is constructed first, which is what puts
    it at the bottom of the stack: siblings paint in creation order.

    The column and the page are alternatives, never both: Music and Settings are
    lists, Now Playing is a page. `show_page` swaps them.
    """

    # The mouse's half of the navigation blip. Emitted only when a click or a
    # wheel step actually moved the cursor, so clicking the selected category or
    # scrolling against the end of a list is silent -- the same as the keyboard,
    # which gets this by comparing indices around the keypress. The stage says
    # *that* the cursor moved and nothing more; `ui/sounds.py` owns the rest.
    moved = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.wave = WaveBackground(self)
        self.bar = Crossbar(self)
        self.column = ItemColumn(self)
        self.page = NowPlayingPage(self)
        self._status = ""  # what is painted: the transient over the sticky
        self._transient = ""
        self._sticky = ""
        self._dragging = False
        self._showing_page: bool | None = None

        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.setInterval(STATUS_MS)
        self._status_timer.timeout.connect(lambda: self.set_status(""))

    def show_page(self, showing: bool) -> None:
        """Swap the column and the page. Visibility only -- `enter` does the fly-in.

        `_refresh_column` calls this on every controller signal, so anything
        animated from in here would restart whenever the position poll noticed
        a new duration.
        """
        if showing == self._showing_page:
            return
        self._showing_page = showing
        self.page.setVisible(showing)
        self.column.setVisible(not showing)
        # Whatever just went behind has no business still animating.
        (self.column if showing else self.page).settle()

    def enter(self) -> None:
        """Fly the visible half in. One call per crossbar step, and no other.

        Not folded into `show_page`: Music to Settings leaves the same widget
        on screen with different rows in it, and that is every bit as much an
        arrival as swapping the page for the column.
        """
        (self.page if self._showing_page else self.column).enter()

    def resizeEvent(self, event) -> None:
        # Not a layout: they're deliberately on top of each other.
        for child in (self.wave, self.bar, self.column, self.page):
            child.setGeometry(self.rect())
        super().resizeEvent(event)

    def set_status(self, text: str, *, sticky: bool = False) -> None:
        """Put `text` on the status line. "" clears it.

        Two layers, because there are two kinds of thing to say. An *event* --
        a track that wouldn't decode -- is transient and times out. A
        *condition* -- the output device is gone, no folder has been chosen --
        stays true until something changes it, and a line that expires while
        what it describes is still the case is worse than no line at all.

        A transient message covers a sticky one and then uncovers it, so an
        error during a device outage doesn't quietly end up as the last word.
        The reverse does not hold: a condition that has *just* become true is
        newer news than whatever transient is still on screen, and leaving the
        device-lost line queued behind a four-second-old "3 files skipped" is
        the one ordering that reads as the app not having noticed.
        """
        if sticky:
            self._sticky = text
            if text:
                self._status_timer.stop()
                self._transient = ""
        else:
            self._status_timer.stop()
            if text:
                self._status_timer.start()
            self._transient = text
        self._status = self._transient or self._sticky
        self.update()

    def paintEvent(self, event) -> None:
        if not self._status:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setFont(theme.font(13))
        painter.setPen(theme.WARN)
        # Right-aligned, and it has to stay that way. The gutter on the left is
        # the art placeholder's; the left of the column is the Now Playing key
        # hint and, further down a long Music list, the track titles. This is
        # the only edge of the stage that nothing else claims.
        painter.drawText(
            QRect(
                theme.ITEM_X,
                self.height() - theme.STATUS_MARGIN - 22,
                self.width() - theme.ITEM_X - theme.RIGHT_MARGIN,
                22,
            ),
            Qt.AlignRight | Qt.AlignVCenter,
            self._status,
        )

    # -- mouse -------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        pos = event.position().toPoint()

        if self.page.isVisible():
            track = self.page.track_rect()
            if track is not None and track.adjusted(-8, -12, 8, 12).contains(pos):
                self._dragging = True
                self.page.slider_moved.emit(self.page.fraction_at(pos.x()))
                return
            self._click_category(pos)
            return

        item = self.column.hit(pos)
        if item is not None:
            # Click to select, click again to open -- the same row twice is the
            # mouse equivalent of Down-then-Enter, and it makes a single click
            # on the already-selected track do the obvious thing.
            if item == self.column.index:
                self.column.activate()  # `activated` is what sounds the confirm
            else:
                self.column.set_index(item)
                self.moved.emit()
            return

        self._click_category(pos)

    def _click_category(self, pos: QPoint) -> None:
        category = self.bar.hit(pos)
        if category is None or category == self.bar.index:
            return  # missed, or clicked the one already selected
        self.bar.set_index(category)
        self.moved.emit()

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            # Live: hearing the pitch move while you drag is the entire point
            # (decisions log).
            self.page.slider_moved.emit(
                self.page.fraction_at(event.position().toPoint().x())
            )

    def mouseReleaseEvent(self, event) -> None:
        self._dragging = False

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() != Qt.LeftButton or self.page.isVisible():
            return
        if self.column.hit(event.position().toPoint()) is not None:
            self.column.activate()

    def wheelEvent(self, event) -> None:
        steps = event.angleDelta().y() // 120
        if not steps:
            return
        if self.page.isVisible():
            # No `moved` here: the slider ticks instead, and only when the value
            # it lands on is a different one. The window fires that, since it is
            # the half that knows whether the speed actually changed.
            self.page.slider_moved.emit(
                min(1.0, max(0.0, self.page.state.fraction + steps * 0.02))
            )
            return
        before = self.column.index
        self.column.step(-steps)
        if self.column.index != before:
            self.moved.emit()


class MainWindow(ChromeWindow):
    def __init__(self, controller: PlayerController) -> None:
        super().__init__("XMB PLAYER")
        self.controller = controller
        self.sounds = Sounds(controller)

        # Per-category cursors: stepping away from Music and back should land
        # where you left, not at the top of a 200-track list. Sized off
        # `CATEGORIES` rather than written out, because a literal here is a list
        # that has to agree with another list -- which is the bug class Batch 14
        # and Batch 21 were both about, and it would land as an IndexError on
        # whichever category somebody forgot to add.
        self._selection = [0] * len(CATEGORIES)
        self._category = CAT_NOW  # mirrors `stage.bar.index`, see `_on_category`
        self._library = ScanResult()
        self._folder: Path | None = None
        self._playing = False
        self._speed = settings_mod.DEFAULT_SPEED
        # Mirrored for the same reason `_speed` is: three things read them back
        # (the Settings row, the Now Playing tail, the transport buttons) and
        # none of them should have to ask the controller mid-paint.
        self._shuffle = settings_mod.DEFAULT_SHUFFLE
        self._repeat = settings_mod.DEFAULT_REPEAT
        self._duration = 0.0
        self._device_lost = False
        # Set while the Theme row is holding the arrow keys. One of the two
        # modal states in the app, which is why it is spelled out here rather
        # than inferred from the cursor being on that row.
        self._stepping = False
        # The other one: Music being filtered. `_searching` and `_query` are
        # separate because an open search with nothing typed is a real state --
        # the header is up and the keyboard has changed meaning, while the list
        # is still every track.
        self._searching = False
        self._query = ""
        # Column row -> index into `_library.tracks`. Everything above the
        # controller addresses a track by its real index -- `play_index`, the
        # marker, "Track 4 of 196", the shuffle bag -- and a filtered column is
        # the one place that identity stops holding. Rebuilt by `_music_items`,
        # which is the method that already walks the library to make the rows.
        self._matches: list[int] = []
        # -- Get Music --
        #
        # Deliberately *not* folded into `_searching` and `_query` above. Those
        # three read `_searching` (`_music_row`, `_end_search`, `_refresh_sticky`)
        # and every one of them means "Music is filtered" by it; widening that to
        # "typing is happening somewhere" is how all three quietly start
        # answering a question nobody asked them.
        #
        # There is no `_get_searching` to go with `_get_query`, because this
        # category has no mode to be in or out of: its column is always the
        # header and a list, so the category *is* the mode.
        #
        # A column row here is an index into `_results` and nothing else -- no
        # map, no second list to keep in step. That is the one thing Music
        # needed `_matches` for and the reason this one does not need anything.
        self._get_query = ""
        self._results: list[fetch.Result] = []
        self._searching_online = False
        self._downloading = ""  # the title in flight, "" when nothing is
        self._progress = 0.0
        # Looked up once at startup rather than per keystroke: `shutil.which`
        # walks PATH, and a category that stats the disk every time you type a
        # letter is the sort of thing Batch 22 went looking for. Re-checked when
        # the category is entered, so installing yt-dlp does not need a restart.
        self._tools = fetch.find_tools()
        # The first `library_changed` is the one that can decide this is a first
        # run. Every later one is the user changing folders, and landing them
        # back on Settings for that would be the app taking the wheel.
        self._first_library = True

        self._build()
        self._connect()
        self._refresh_column(reset=True)
        # The app arrives the same way a category does -- and now it announces
        # itself the same way too. The stream is already open by here (`app.py`
        # builds the engine first), so the swell starts under the folder scan
        # rather than after it.
        self.stage.enter()
        self.sounds.startup()

    # -- construction ------------------------------------------------------

    def _build(self) -> None:
        self.stage = XmbStage()
        self.transport = TransportBar()

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.stage, 1)
        layout.addWidget(self.transport)
        self.set_body(body)

        self.stage.bar.set_categories(CATEGORIES)
        # All three seeded from the defaults, not from what was saved -- the real
        # values arrive moments later on `controller.start()`, through `_on_theme`
        # and `_on_speed`, which is what actually colours a launch. This exists
        # because the palette and the accent are module state and a second window
        # in the same process (the harness, the render tools) would otherwise
        # inherit the last one's colour in a stylesheet built before anything set
        # it.
        theme.set_palette(settings_mod.DEFAULT_THEME)
        self.stage.wave.set_fraction(_speed_fraction(self._speed))
        theme.set_accent_fraction(_speed_fraction(self._speed))
        # Unconditional: the bucket may not have moved but the palette may have,
        # and this runs once per window rather than once per pixel of a drag.
        self.transport.refresh_accent()
        self.setFocusPolicy(Qt.StrongFocus)

        # Get Music. The fetcher owns the processes; this owns when to ask.
        self.fetcher = Fetcher(self)
        # Typing runs a search on a pause rather than on Enter, which is what
        # keeps Enter meaning exactly one thing on this category -- *get this
        # one*. Enter-to-search and Enter-to-download on the same key would be
        # decided by whether the query had changed since the last search, i.e.
        # by state the user cannot see.
        #
        # Long enough that typing a phrase is one request rather than a dozen,
        # short enough not to feel stuck. The 800 ms settings debounce is the
        # precedent; this is shorter because somebody is waiting for it.
        self._get_timer = QTimer(self)
        self._get_timer.setSingleShot(True)
        self._get_timer.setInterval(GET_DEBOUNCE_MS)
        self._get_timer.timeout.connect(self._run_search)

    def _connect(self) -> None:
        controller = self.controller

        controller.library_changed.connect(self._on_library)
        controller.folder_changed.connect(self._on_folder)
        controller.track_changed.connect(self._on_track)
        controller.art_changed.connect(self._on_art)
        controller.position_changed.connect(self._on_position)
        controller.playing_changed.connect(self._on_playing)
        controller.speed_changed.connect(self._on_speed)
        controller.theme_changed.connect(self._on_theme)
        controller.shuffle_changed.connect(self._on_shuffle)
        controller.repeat_changed.connect(self._on_repeat)
        controller.volume_changed.connect(self.transport.set_volume)
        controller.failed.connect(self.stage.set_status)

        self.fetcher.results.connect(self._on_results)
        self.fetcher.progress.connect(self._on_progress)
        self.fetcher.finished.connect(self._on_fetched)
        self.fetcher.failed.connect(self._on_fetch_failed)
        # Next to `controller.shutdown` in `app.py`, and for the same reason: a
        # yt-dlp that survives the window goes on writing into the music folder
        # after the app that asked for it is gone, and the next launch scans
        # that folder and finds a part-written file.
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.fetcher.cancel)
        # The one sound wired to a controller signal rather than to an input:
        # a failure is the app answering back, and it is worth hearing whether
        # or not you were looking at the status line when it appeared.
        controller.failed.connect(lambda _message: self.sounds.error())
        controller.device_changed.connect(self._on_device)

        self.stage.bar.index_changed.connect(self._on_category)
        self.stage.column.activated.connect(self._activate)
        # The one thing wired to `index_changed`, and not for sound: if the
        # cursor moved while a row was stepped into, it moved off that row --
        # a click, the wheel, Home, End. This is the mouse's exit as much as the
        # keyboard's, which is why it hangs off the movement rather than off any
        # of the four things that can cause it.
        self.stage.column.index_changed.connect(lambda _index: self._stop_stepping())
        self.stage.page.slider_moved.connect(self._on_slider_dragged)
        self.stage.moved.connect(self.sounds.move)

        self.transport.play_pressed.connect(self._toggle)
        self.transport.next_pressed.connect(lambda: self._skip(+1))
        self.transport.previous_pressed.connect(lambda: self._skip(-1))
        self.transport.shuffle_pressed.connect(self._shuffle_pressed)
        self.transport.repeat_pressed.connect(self._repeat_pressed)
        self.transport.seek_requested.connect(controller.seek)
        self.transport.volume_requested.connect(controller.set_volume)

    # -- controller -> shell ----------------------------------------------

    def _on_library(self, result: ScanResult) -> None:
        first, self._first_library = self._first_library, False
        self._library = result
        self._selection[CAT_MUSIC] = 0
        if result.skipped:
            # Mislabelled MP4/AAC, mostly. Say so rather than letting the user
            # wonder where those files went.
            self.stage.set_status(
                f"{len(result.skipped)} file(s) skipped -- not really MP3"
            )
        # A folder that has gone or turned unreadable is something *wrong*, and
        # worth a noise. An empty one, or one never chosen, is not -- blipping
        # an error at someone who has just opened the app for the first time
        # says they did something, and they didn't.
        if result.error in (library.MISSING, library.UNREADABLE):
            self.sounds.error()
        self._refresh_sticky()
        # A library refresh means the *Music* list changed, so Music's cursor
        # goes back to the top. Any other column is showing something else --
        # the Settings rows, or search results a finished download has no
        # business scrolling -- and `restore` is what leaves those where the
        # user put them. Before Get Music existed, `reset=True` was right for
        # every category because every category was the library or a fixed list.
        on_music = self._category == CAT_MUSIC
        self._refresh_column(reset=on_music, restore=not on_music)
        if first and result.error == library.NO_FOLDER:
            self._begin_first_run()

    def _on_folder(self, folder: Path | None) -> None:
        self._folder = folder
        self._refresh_sticky()
        self._refresh_column()

    def _on_device(self, working: bool) -> None:
        self._device_lost = not working
        if not working:
            # Wired to the signal rather than to an input for the same reason
            # `failed` is: nobody pressed anything, the app is answering back.
            # It very likely makes no sound -- there is no device -- but the
            # case where Windows moved us to a *different* one is exactly when
            # it would, and that is the case worth hearing.
            self.sounds.error()
        self._refresh_sticky()

    def _refresh_sticky(self) -> None:
        """Re-derive the status line's standing message.

        Two conditions can hold at once -- no folder and no device -- so they
        are ranked rather than raced. The device wins: a folder you can't play
        through is the smaller of the two problems.
        """
        if self._device_lost:
            self.stage.set_status(DEVICE_LOST_TEXT, sticky=True)
        elif self._downloading:
            # Above every other standing line and below the device, on the same
            # "how much can the user do about it" ranking the two below use. It
            # is deliberately not scoped to the Get Music category: a download
            # goes on running while you go back to listening, and a progress
            # readout that vanished when you stepped away would read as the
            # download having stopped.
            self.stage.set_status(
                f"Getting {_short(self._downloading)}   {round(self._progress * 100)}%",
                sticky=True,
            )
        elif self._category == CAT_GET:
            advice = self._get_advice()
            if advice:
                self.stage.set_status(advice, sticky=True)
            elif self._results:
                self.stage.set_status(f"{len(self._results)} result(s)", sticky=True)
            else:
                self.stage.set_status("", sticky=True)
        elif self._searching and self._library.tracks:
            # Sticky rather than transient: a search is a *condition*, and a
            # count that expired after six seconds while the query was still on
            # screen would be the status line contradicting the header. Below
            # the device and above the library error, which is the same ranking
            # by how much the user can do about it.
            self.stage.set_status(
                f"{len(self._matches)} of {len(self._library.tracks)} matching",
                sticky=True,
            )
        elif self._library.error is not None:
            self.stage.set_status(
                empty_advice(self._library.error, self._folder), sticky=True
            )
        else:
            self.stage.set_status("", sticky=True)

    def _begin_first_run(self) -> None:
        """Nothing has ever been chosen: open on Settings, on the folder row.

        Chosen with the user over throwing a native folder dialog at someone who
        has not seen the app yet. It stays inside the XMB and costs one press --
        and the row it lands on is the one every "no music" line names.

        Settled rather than slid: this is where the app *started*, not somewhere
        it navigated to, and the entrance animation is already playing over it.
        No blip either -- nobody pressed anything.
        """
        self.stage.bar.set_index(CAT_SETTINGS)
        self.stage.bar.settle()
        self.stage.set_status(FIRST_RUN_TEXT)

    def _on_track(self, index: int) -> None:
        track = self.controller.current
        self.transport.set_title(track.title if track else "nothing loaded")
        # The cursor follows the track, and under a filter the row it lives on
        # is not the track's index. A track the query hides gets no cursor move
        # at all rather than a clamped one -- there is no row to move to.
        row = self._music_row(index) if index >= 0 else None
        if row is not None:
            self._selection[CAT_MUSIC] = row
            if self._category == CAT_MUSIC:
                self.stage.column.set_index(row)
        self._refresh_column()

    def _on_art(self, data: object) -> None:
        """The playing track's cover, as bytes off the controller.

        The `ui` half of the seam: `core.tags` hands up whatever sat in the APIC
        frame and has no opinion about whether it is an image, and this is where
        it becomes pixels or doesn't. Reaching down for those bytes from here is
        what Batch 14 moved -- the read is the controller's now, and the window
        is told, like it is told about everything else.
        """
        self.stage.page.set_art(_cover_image(data if isinstance(data, bytes) else None))

    def _on_position(self, position: float, duration: float) -> None:
        self.transport.set_position(position, duration)
        # This fires 30 times a second; only the *duration* changes what the
        # page says, so the rebuild is gated on it rather than on the clock.
        if duration != self._duration:
            self._duration = duration
            self._refresh_column()

    def _on_playing(self, playing: bool) -> None:
        self._playing = playing
        self.transport.set_playing(playing)
        self._refresh_column()

    def _on_speed(self, speed: float) -> None:
        self._speed = speed
        fraction = _speed_fraction(speed)
        # The hue is the speed: deep blue at daycore, violet at nightcore. The
        # wave has always said so; now the accent says it too, so the selection
        # plate, the glow, both slider fills and every readout travel with the
        # ribbons instead of sitting icy blue on top of a magenta background.
        self.stage.wave.set_fraction(fraction)
        restyle = theme.set_accent_fraction(fraction)
        # Everything that paints itself picks the new accent up on its next
        # repaint; the transport bar's colours live in a stylesheet and have to
        # be told. `restyle` is what keeps that off the per-pixel drag path.
        if restyle:
            self.transport.refresh_accent()
        self._refresh_column()
        # `_refresh_column` only touches whichever of the page and the column is
        # showing, and the column's accent now depends on the speed rather than
        # only on its contents. Cheap insurance: an update on a hidden widget
        # costs nothing.
        self.stage.column.update()

    def _on_theme(self, name: str) -> None:
        """A different spectrum under the same slider. Everything else holds.

        The restyle is unconditional, unlike `_on_speed`'s. That gate asks
        whether the *fraction* moved a bucket, and it hasn't -- the slider is
        exactly where it was and only the ramp beneath it changed, so a swap
        sails straight through the comparison and the bottom bar keeps the old
        colour. The wave needs no telling at all: it reads `wave_color` six
        times a frame and caches nothing, so it is already repainting.
        """
        theme.set_palette(name)
        self.transport.refresh_accent()
        self._refresh_column()
        self.stage.column.update()

    def _on_shuffle(self, on: bool) -> None:
        self._shuffle = on
        self.transport.set_shuffle(on)
        self._refresh_column()

    def _on_repeat(self, mode: str) -> None:
        """Light the button, swap its glyph, and rebuild whatever is on screen.

        The bar is told two facts rather than the mode's name -- see
        `TransportBar.set_repeat` for why a widget in that package doesn't get
        to know what a mode is called.
        """
        self._repeat = mode
        self.transport.set_repeat(mode != REPEAT_OFF, one=mode == REPEAT_ONE)
        self._refresh_column()

    def _on_slider_dragged(self, fraction: float) -> None:
        span = settings_mod.MAX_SPEED - settings_mod.MIN_SPEED
        self._set_speed(settings_mod.MIN_SPEED + fraction * span)

    # -- things the user did ----------------------------------------------
    #
    # Four small wrappers, and they all exist for the same reason: the sound
    # belongs to the *press*, not to what the press changed. Wiring these
    # straight through to the controller is what used to make auto-advance blip
    # like a keypress and a slider pinned at nightcore keep on ticking.

    def _set_speed(self, value: float) -> None:
        """Speed, from the arrows, the wheel or a drag. Ticks only on a change.

        `_on_speed` has already run by the time `set_speed` returns -- the
        signal is direct -- so `self._speed` is the new value here. Comparing
        against it is what keeps a slider held at either end silent instead of
        ticking at the frame rate against a clamp.
        """
        before = self._speed
        self.controller.set_speed(value)
        if self._speed != before:
            self.sounds.tick()

    def _toggle(self) -> None:
        """Play/pause, from Space or the transport button."""
        was = self._playing
        self.controller.toggle()
        if self._playing == was:
            return  # nothing loaded and it wouldn't load: `failed` says so
        self.sounds.confirm() if self._playing else self.sounds.back()

    def _skip(self, delta: int) -> None:
        """Next/Previous. The end of a track goes through `controller.step`
        directly and so stays silent -- that is the whole reason this exists."""
        self.sounds.move()
        self.controller.step(delta)

    def _shuffle_pressed(self) -> None:
        """The transport button and the `S` key. The Settings row is not here.

        That row activates through `_activate`, which has already sounded its
        confirm by the time the action runs -- so its action is the controller's
        own `toggle_shuffle` and this exists for the two inputs that have no
        such blip of their own. Same shape as `_fullscreen` below, and the same
        reason `_skip` exists at all.
        """
        self.controller.toggle_shuffle()
        self.sounds.confirm() if self._shuffle else self.sounds.back()

    def _repeat_pressed(self) -> None:
        """`move`, not `confirm`: this is walking a value, like the theme row's
        arrows, rather than switching one thing on."""
        self.controller.cycle_repeat()
        self.sounds.move()

    def _fullscreen(self) -> None:
        """F11 and Escape. The Settings row goes through `_activate`, which has
        already sounded its confirm by the time it gets here."""
        self.toggle_fullscreen()
        self.sounds.confirm() if self.isFullScreen() else self.sounds.back()

    # -- categories and items ---------------------------------------------

    def _on_category(self, index: int) -> None:
        # Leaving Settings leaves the row and leaving Music leaves the search,
        # however you left. Before the refresh below, or the column rebuilds
        # still wearing the outline -- and before `self._category` moves on, so
        # the search's own restore banks against the category it belonged to.
        self._stop_stepping()
        self._end_search()
        # The crossbar has already moved by the time this fires, so the cursor
        # for the category we just left has to be banked against the mirrored
        # index rather than against `bar.index`.
        self._selection[self._category] = self.stage.column.index
        self._category = index
        if index == CAT_GET:
            # Arriving is the moment to look again: somebody who read the "not
            # installed" line, went and installed it, and came back should find
            # the category working rather than having to relaunch. One `which`
            # per category step is nothing.
            self._recheck_tools()
        self._refresh_column(restore=True)
        self._refresh_sticky()
        self.stage.enter()

    def _refresh_column(self, *, reset: bool = False, restore: bool = False) -> None:
        """Rebuild the visible column from current state.

        Called on every controller signal that changes what a row says. Cheap
        enough to do wholesale -- the lists are short and only the rows actually
        on screen get painted.
        """
        if not reset and not restore:
            self._selection[self._category] = self.stage.column.index

        category = self._category
        index = 0 if reset else self._selection[category]

        self.stage.show_page(category == CAT_NOW)
        # Said here rather than only in the branches below, so a query can't
        # outlive the list it was narrowing: leaving Music closes the search,
        # but the header should not depend on that having happened first.
        #
        # Get Music always has a header, including with nothing typed -- it is
        # not a mode you can be outside of on that category, and a list of
        # results with no query above them would leave the caret nowhere.
        if category == CAT_GET:
            self.stage.column.set_search(self._get_query, GET_LABEL)
        else:
            self.stage.column.set_search(self._query if self._searching else None)

        if category == CAT_NOW:
            self.stage.page.set_state(self._now_playing())
        elif category == CAT_MUSIC:
            self.stage.column.set_items(
                self._music_items(), index=index, empty_text=self._music_empty_text()
            )
        elif category == CAT_GET:
            self.stage.column.set_items(
                self._get_items(), index=index, empty_text=self._get_empty_text()
            )
        else:
            self.stage.column.set_items(self._settings_items(), index=index)

        self._selection[category] = self.stage.column.index

    def _now_playing(self) -> NowPlaying:
        """The Now Playing page's contents, formatted here rather than there.

        The page paints strings; this decides what they say -- same split as the
        item builders below. Speed applies whether or not a track is loaded, so
        the slider is live even on an empty library.
        """
        track = self.controller.current
        where = self._folder.name if self._folder else "no folder"

        if track is None:
            first = f"{len(self._library.tracks)} tracks  ·  {where}"
            second = (
                "Choose one in Music"
                if self._library.tracks
                else empty_reason(self._library.error, self._folder)
            )
        else:
            # Who it is, then how long, then where in the list -- the same order
            # you'd read them off a sleeve. The first line is blank on an
            # untagged file rather than absent, so the two below it don't move.
            first = _credit(track)
            # The warped length is the one number only this app can tell you,
            # and it moves as the slider does. `duration` is the file's real
            # length, so dividing by speed gives the wallclock it'll actually
            # take -- 2:00 at 1.30x really is 1:32.
            second = f"{clock(self._duration)}"
            if self._duration > 0 and abs(self._speed - 1.0) > 0.005:
                second += f"   ·   plays in {clock(self._duration / self._speed)}"
                second += f" at {self._speed:.2f}x"
            third = (
                f"Track {self.controller.index + 1} of {len(self._library.tracks)}"
                f"{self._modes_tail()}   ·   {where}"
            )

        return NowPlaying(
            title=track.title if track else "Nothing playing",
            lines=(first, second) if track is None else (first, second, third),
            fraction=_speed_fraction(self._speed),
            speed_text=f"{self._speed:.2f}x",
        )

    def _modes_tail(self) -> str:
        """What the third info line adds about shuffle and repeat, if anything.

        Appended to a line that already exists rather than given a slot of its
        own: the info block is three fixed lines and the third clears the
        slider's box by 1 px, so a fourth is a new metric and a fresh collision
        to check. It also belongs on that line by meaning -- "Track 4 of 31" is
        already the sentence about where you are in the list, and these say how
        it will move on from there.

        Inserted *before* the folder name rather than after it, which is the
        whole reason this is a method and not an f-string. `_paint_info` elides
        the line from the right, and the folder name is the one field on it that
        comes out of a file and so has no length -- put the modes last and a
        library called `Nightcore Collection Remastered` silently eats them.
        Whatever is unbounded goes at the end, where eliding it costs least.

        Silent when the modes are what the app has always done, for the same
        reason the length line drops its "plays in" at 1.00x: a readout that
        never changes stops being read. `Repeat: All` is Batch 3's wrapping
        auto-advance, so only `one` and `off` say anything.
        """
        parts = []
        if self._shuffle:
            parts.append("Shuffle")
        if self._repeat != REPEAT_ALL:
            parts.append(f"Repeat {self._repeat}")
        return "".join(f"   ·   {part}" for part in parts)

    def _music_items(self) -> list[Item]:
        """The Music rows, and the map back to real track indices.

        The two are built together on purpose: a row list and a row->track list
        that are assembled in two places is the Batch 14 parallel-array bug in a
        new costume, and this one would misfire as *playing the wrong song*.
        With no query `_matches` is the identity, so everything downstream of it
        behaves exactly as it did before there was a search at all.
        """
        playing = self.controller.index
        tracks = self._library.tracks
        self._matches = self._match_indices(self._query)
        return [
            Item(tracks[i].title, value=tracks[i].artist, marker=(i == playing))
            for i in self._matches
        ]

    def _match_indices(self, query: str) -> list[int]:
        """Which tracks `query` would leave on screen, in list order.

        Split out of `_music_items` so `_set_query` can ask what a keystroke
        would do *before* doing it -- which is the only way to tell a press that
        narrowed the list from one that merely made the query longer.
        """
        return [
            i
            for i, track in enumerate(self._library.tracks)
            if library.matches(track, query)
        ]

    def _music_row(self, index: int) -> int | None:
        """Which column row is showing track `index`, or None if it's filtered out.

        The identity shortcut is not an optimisation: with no query open, Music
        may never have been built -- the app opens on Now Playing -- so
        `_matches` can legitimately be empty while the library is not. A query
        can only be open on Music, which is the case where `_matches` is
        guaranteed fresh.
        """
        if not self._query:
            return index
        try:
            return self._matches.index(index)
        except ValueError:
            return None

    def _music_empty_text(self) -> str:
        # A query that matches nothing is not an empty folder, and saying "No
        # playable MP3s" there reads as the library having vanished. The query
        # itself is not repeated into this line: it is already on screen in the
        # header above, and it is the one string here with no length.
        if self._query and self._library.tracks:
            return "Nothing matches"
        return empty_reason(self._library.error, self._folder)

    def _folder_summary(self) -> str:
        """What the Music folder row says on its right.

        A folder that has gone says so here rather than showing its name as
        though it were fine. One word, not the name and then the word: at 720 px
        "no-such-folder  (missing)" pushed the row's own label into an ellipsis,
        and a row whose value elides its label has them the wrong way round.
        The status line underneath is where the name goes.
        """
        if self._folder is None:
            return "not set"
        if self._library.error == library.MISSING:
            return "missing"
        if self._library.error == library.UNREADABLE:
            return "unreadable"
        return self._folder.name

    # -- Get Music ---------------------------------------------------------

    def _get_items(self) -> list[Item]:
        """The search results, one row each. The row *is* the index.

        No map and no second list, which is the whole difference from
        `_music_items`: a result has no track index to translate into, so
        `_results[row]` is the entire lookup and there is nothing that can fall
        out of step with it.

        The value is the **duration and nothing else**, which is a decision that
        cost the uploader its place and was made from a render. `duration ·
        uploader` was the first version and reads fine at 980; at the 720
        minimum it claims the whole of `_paint_item`'s 45% cap and cuts the
        title to `1. Extended Ni...`, which identifies nothing. Eliding the
        value harder does not help -- a value only gives room back by being
        *short*, and a channel name has no length.

        So: the field that decides a pick, in four fixed-width characters. A
        ten-hour loop and the song you wanted are otherwise the same row, and
        the title is what tells them apart once they aren't.
        """
        return [
            Item(
                result.title,
                value=clock(result.duration_s) if result.duration_s else "",
            )
            for result in self._results
        ]

    def _get_empty_text(self) -> str:
        """Why the results list is empty. One place, like `empty_reason`.

        Ranked by what the user can do about it, most fixable last: a tool that
        is not installed beats a folder that is not set beats having typed
        nothing yet, because the first two make the third pointless.

        Short, because the empty column draws at the item size -- and now in
        280 px at the 720 minimum rather than 368. The line that says where to
        go is `_get_advice`, in the smaller type that has room for it.
        """
        missing = self._tools.missing
        if missing == fetch.NO_YTDLP:
            return "yt-dlp not installed"
        if missing == fetch.NO_FFMPEG:
            return "ffmpeg not installed"
        if self._folder is None:
            return "No folder yet"
        if self._searching_online:
            return "Searching…"
        if not self._get_query:
            return "Type to search"
        return "Nothing found"

    def _get_advice(self) -> str:
        """The same reason with the fix attached, for the status line.

        Same split as `empty_reason` / `empty_advice`, and short for the same
        reason that one is. The first version named `fetch.tools_dir()` in full,
        which is an absolute path and therefore unbounded: at 980 px it pushed
        the front of its own sentence off the left edge and the status line read
        `dlp not found`, having eaten the `yt-`. The status line is right-aligned
        and elides nothing, so a line too long for it does not shrink -- it
        loses its beginning, which is the half that says what is wrong.

        Where to put the file is in the README and in the log line beside it.
        A path is a thing to copy, and the status bar is not a place you can
        copy from.
        """
        missing = self._tools.missing
        if missing is not None:
            name = "yt-dlp" if missing == fetch.NO_YTDLP else "ffmpeg"
            return f"{name} not installed  --  put it on PATH"
        if self._folder is None:
            return f"Downloads need somewhere to go  --  {_SETTINGS_ROW}"
        return ""

    def _set_get_query(self, query: str) -> None:
        """Retype the query and arm the search. The results do not move yet.

        Unlike `_set_query` next door, this cannot compare the result set before
        and after -- the answer is a network round trip away. What it *can*
        compare is what is on screen, and the header is on screen: a keystroke
        changes the query, the query is drawn, so the keystroke did something
        and blips. That is the same rule as everywhere else in this file
        (`a press that changes nothing makes no sound`) reaching a case where
        the visible thing is the query itself rather than the list under it.
        """
        if query == self._get_query:
            return
        self._get_query = query
        self._refresh_column()
        if query.strip():
            self._get_timer.start()  # restarts, so a phrase is one request
        else:
            # Deleting back to nothing is a request to stop, not to search for
            # everything. The list empties with it, or a stale set of results
            # sits under an empty header claiming to be its answer.
            self._get_timer.stop()
            self._results = []
            self._searching_online = False
            self._refresh_column(reset=True)
        self._refresh_sticky()
        self.sounds.move()

    def _recheck_tools(self) -> None:
        """Look for yt-dlp and ffmpeg again, and say where they should go.

        The status line cannot carry the folder -- an absolute path is unbounded
        and that line elides nothing (see `_get_advice`) -- so the path is
        written *here*, where it can be read at leisure and copied. Throttled,
        because this runs on every category step and every search.
        """
        self._tools = fetch.find_tools()
        missing = self._tools.missing
        if missing is not None and log_mod.due("fetch-tools", 60.0):
            _log.info(
                "%s not found; looked on PATH and in %s", missing, fetch.tools_dir()
            )

    def _run_search(self) -> None:
        """The debounce fired. Ask, if there is anything to ask with."""
        query = self._get_query.strip()
        if not query:
            return
        # Re-checked here rather than trusted from startup, so installing yt-dlp
        # and coming back does not need the app restarted. It is a `which` on a
        # keystroke *pause*, not on a keystroke.
        self._recheck_tools()
        if self._tools.missing is not None:
            self._searching_online = False
            self._refresh_column()
            self._refresh_sticky()
            self.sounds.error()
            return
        self._searching_online = True
        self._refresh_column()
        self._refresh_sticky()
        self.fetcher.search(self._tools, query)

    def _on_results(self, results: object) -> None:
        self._searching_online = False
        self._results = list(results) if isinstance(results, list) else []
        self._selection[CAT_GET] = 0
        # Only rebuild the column if it is the one showing these. A search
        # started on Get Music and answered after the user stepped to Music must
        # not reset the Music cursor -- `_refresh_column` acts on whatever
        # category is current, not on the one that asked.
        if self._category == CAT_GET:
            self._refresh_column(reset=True)
        self._refresh_sticky()
        if not self._results:
            # Sound follows intent, and this still does: typing is the only
            # thing that starts a search, so a blip here is the answer to a
            # press. The network put a second between the two, which is not the
            # same as the app making a noise nobody asked for.
            self.sounds.error()

    def _start_download(self, index: int) -> bool:
        """Enter on a result. False if it did not start, and why is on the bar.

        Every refusal is a *condition the user can fix*, which is why each one
        gets a sentence rather than a shrug -- and why the caller only sounds
        `confirm` when this returns True.
        """
        if not 0 <= index < len(self._results):
            return False
        if self._folder is None or self._tools.missing is not None:
            self.stage.set_status(self._get_advice())
            self.sounds.error()
            return False
        if self.fetcher.downloading:
            self.stage.set_status(f"Already getting {_short(self._downloading)}")
            self.sounds.error()
            return False

        result = self._results[index]
        if not self.fetcher.download(self._tools, result, self._folder):
            self.stage.set_status("Could not start the download")
            self.sounds.error()
            return False

        self._downloading = result.title
        self._progress = 0.0
        self._refresh_sticky()
        return True

    def _on_progress(self, fraction: float) -> None:
        # Whole percents only. yt-dlp reports far more often than that, and each
        # one would rebuild a sentence and repaint the status line to say the
        # same thing -- which is the sort of per-frame work Batch 22 went
        # looking for rather than something to add.
        if round(fraction * 100) == round(self._progress * 100):
            return
        self._progress = fraction
        self._refresh_sticky()

    def _on_fetched(self, path: object) -> None:
        """A download finished. Put it in the library without stopping the music.

        `refresh_library` and not `rescan`: the latter goes through
        `open_folder`, which clears the engine -- so getting a song while
        listening to one would stop the one you are listening to.
        """
        title, self._downloading = self._downloading, ""
        self._progress = 0.0
        self.controller.refresh_library()
        # Sticky first, then the transient: a *new* sticky clears the transient
        # by design (`set_status`), so saying "Added ..." first and then
        # re-deriving the standing line could wipe it.
        self._refresh_sticky()
        name = Path(str(path)).stem if path else title
        self.stage.set_status(f"Added {_short(name)}")
        self.sounds.confirm()

    def _on_fetch_failed(self, message: str) -> None:
        self._downloading = ""
        self._progress = 0.0
        self._searching_online = False
        if self._category == CAT_GET:
            self._refresh_column()
        self._refresh_sticky()
        self.stage.set_status(message)
        self.sounds.error()

    def _get_key(self, key: int, modifiers, text: str) -> bool | None:
        """Get Music's keyboard. `None` means "not mine -- carry on".

        Falling through is most of the design, exactly as it is for the Music
        search: the arrows, Home, End and Enter all want to do what they do
        everywhere else, and Ctrl and Shift arrows stay transport because you
        may well be listening while you look for the next thing.

        There is no exit branch, because there is nothing to exit -- the header
        belongs to the category, so leaving it is stepping off the category, and
        that is Backspace and the crossbar doing what they always do.
        """
        if key == Qt.Key_Escape and self._get_query:
            self._set_get_query("")
            self.sounds.back()
            return True
        if key == Qt.Key_Backspace and self._get_query:
            # Only while there is something to delete. On an empty query this
            # falls through to the crossbar's "back", which steps to Settings --
            # the same thing Backspace does from every other category.
            self._set_get_query(self._get_query[:-1])
            return True
        # `text` and not `key`, which is what makes S, R and Space literal in
        # here while they stay bound to shuffle, repeat and play/pause outside.
        # `text` first, because "".isprintable() is True and an arrow key's text
        # is "" -- without it every arrow would count as typing nothing.
        if (
            text
            and text.isprintable()
            and not modifiers & (Qt.ControlModifier | Qt.AltModifier)
        ):
            self._set_get_query(self._get_query + text)
            return True
        return None

    def _settings_rows(self) -> list[SettingsRow]:
        """The Settings list, in order. The only place that order is stated.

        Rebuilt per call rather than held, because two of the three values move:
        the folder summary and the track counts are re-read on every
        `_refresh_column`, and the theme's chevrons come and go with the mode.
        Five tuples on a keypress is not a cost worth caching against a bug
        class this shape.
        """
        counts = f"{len(self._library.tracks)} tracks"
        if self._library.skipped:
            counts += f"  ·  {len(self._library.skipped)} skipped"
        # No speed presets here any more -- they're the two ends of the slider
        # on Now Playing, which is a better home for them than a settings list.
        # The theme row reads its value back out of `theme` rather than off the
        # controller, so an unknown name in the settings file shows as whatever
        # is actually on screen instead of what the file asked for. The chevrons
        # are the second half of saying the row is stepped into -- the outline
        # says the keys land here, and these say which keys.
        name = theme.palette().name
        return [
            SettingsRow("Music folder", self._folder_summary(), self._choose_folder),
            SettingsRow("Rescan folder", counts, self.controller.rescan),
            # Both actions are the controller's own bound methods, like `rescan`
            # above: `_activate` has already blipped by the time one of these
            # runs, so a wrapper here would only add a second noise.
            #
            # Repeat cycles on Enter rather than being stepped into like Theme.
            # A palette is a comparison you make by looking; these are three
            # states you already know the names of, and the button in the
            # transport bar can only mean "the next one" anyway. A row that
            # behaved differently from its own button is the inconsistency.
            SettingsRow(
                "Shuffle",
                "On" if self._shuffle else "Off",
                self.controller.toggle_shuffle,
            ),
            SettingsRow(
                "Repeat", self._repeat.capitalize(), self.controller.cycle_repeat
            ),
            SettingsRow(
                "Theme",
                f"‹ {name} ›" if self._stepping else name,
                self._start_stepping,
            ),
            SettingsRow("Full screen", "F11", self.toggle_fullscreen),
            SettingsRow("Quit", "", self.close),
        ]

    def _settings_items(self) -> list[Item]:
        return [Item(row.label, row.value) for row in self._settings_rows()]

    # -- activation --------------------------------------------------------

    def _activate(self, index: int) -> None:
        # Get Music is the one category whose activation can be *refused* -- no
        # folder, no yt-dlp, or a download already running -- so it sounds its
        # own confirm rather than taking the unconditional one below. A refusal
        # that blipped confirm and then error would be the app saying yes and
        # then no to one press.
        if self._category == CAT_GET:
            if self._start_download(index):
                self.sounds.confirm()
            return

        # One confirm for every activation, keyboard or mouse: `activated` is
        # only emitted when there is something to open, so an Enter on an empty
        # list is silent rather than a blip about nothing.
        self.sounds.confirm()
        # Now Playing has no items to activate -- it's a page, and its only
        # control answers to the arrow keys directly.
        if self._category == CAT_MUSIC:
            # Through the map, always. With no query it is the identity, so
            # this is the same call it has been since Batch 3.
            if 0 <= index < len(self._matches):
                self.controller.play_index(self._matches[index])
            # Enter is a decision: you found the track, so the filter has done
            # its job and the list goes back to being the library.
            self._end_search()
        elif self._category == CAT_SETTINGS:
            self._activate_settings(index)

    def _activate_settings(self, index: int) -> None:
        """Run the activated row's own action. No branches, so none to shift.

        The bounds check is not defensive padding: `activate` fires on whatever
        the cursor is on, and the column is rebuilt from a list this method also
        builds -- the two are momentarily out of step only if something between
        them changes the count, which is exactly the case worth not crashing on.
        """
        rows = self._settings_rows()
        if 0 <= index < len(rows):
            rows[index].action()

    # -- the theme row, which is stepped into ------------------------------
    #
    # The one modal row in the app. Enter steps in, Left and Right walk the
    # presets live, and Enter, Esc or Backspace steps back out -- as does
    # anything that moves the cursor off the row.
    #
    # Picking a theme is a *comparison*: you want to see each one on the screen
    # you are already looking at and stop on the one you like. Cycling blind
    # with a single key makes the one you liked two presses ago cost three more
    # to get back to, which is why this is a mode and not a toggle.

    def _start_stepping(self) -> None:
        self._stepping = True
        self.stage.column.set_stepping(True)
        self._refresh_column()

    def _stop_stepping(self) -> None:
        """Leave the mode. Safe to call when not in it -- most callers are."""
        if not self._stepping:
            return
        self._stepping = False
        self.stage.column.set_stepping(False)
        self._refresh_column()

    def _step_theme(self, delta: int) -> None:
        """Walk the presets, wrapping. Applied live, so you pick by looking."""
        names = theme.palette_names()
        here = names.index(theme.palette().name)
        self.controller.set_theme(names[(here + delta) % len(names)])

    # -- searching Music, which is the other mode --------------------------
    #
    # Built to the theme row's pattern above, because that design was argued out
    # once already: a branch at the top of `_handle_key`, three named exits, and
    # everything else leaving by moving the cursor off the thing. One place it
    # deliberately differs, and it is the whole difference between the two
    # modes: this one must *not* close on `index_changed`. Moving the cursor
    # through the results is the point of having filtered them.
    #
    # A filter rather than type-to-jump, chosen with the user. Jumping is the
    # smaller change -- the cursor hops and the list stays whole -- and it
    # answers "where is that song in the list", where the question here is
    # "which songs are these".

    def _begin_search(self) -> None:
        """Open the header. The list is still every track until something is typed."""
        if self._searching:
            return  # Ctrl+F twice is not a request to throw away the query
        self._searching = True
        self._query = ""
        self._refresh_column()
        self._refresh_sticky()
        self.sounds.confirm()

    def _set_query(self, query: str) -> None:
        """Retype the query and rebuild the list under it.

        The cursor goes to the top when the results change, which is what the
        banked Music index has to give up: row 4 under `tetris` is a different
        track from row 4 under `tetri`, so restoring it would be restoring a
        number rather than a place.

        When they *don't* change it stays exactly where it was, and that is the
        standing "a press that changes nothing" rule reaching a case it had not
        met before: the press did change the query, so the naive version reset
        the cursor and the index comparison in `keyPressEvent` blipped at it.
        Typing the back half of a word you have already narrowed to one track
        should neither tick nor move anything.
        """
        after = self._match_indices(query)
        changed = after != self._matches
        self._query = query
        if changed:
            self._selection[CAT_MUSIC] = 0
        self._refresh_column(reset=changed)
        self._refresh_sticky()
        if not changed:
            return
        self.sounds.error() if not self._matches else self.sounds.move()

    def _end_search(self) -> None:
        """Close it, keeping the cursor on the track it was on. No-op if closed.

        Translating the row back through the map before dropping it is the
        difference between landing where you were looking and landing on
        whichever track happens to be fourth in the library.
        """
        if not self._searching:
            return
        row = self.stage.column.index
        landing = self._matches[row] if 0 <= row < len(self._matches) else 0
        self._searching = False
        self._query = ""
        self._selection[CAT_MUSIC] = landing
        self._refresh_column(restore=True)
        self._refresh_sticky()

    def _search_key(self, key: int, modifiers, text: str) -> bool | None:
        """The search mode's keyboard. `None` means "not mine -- carry on".

        Falling through is most of the design. The arrows, PageUp/Down, Home,
        End and Enter all want to do exactly what they do outside the mode, on
        the shorter list; Ctrl and Shift arrows stay transport, verbatim from
        the theme row's reasoning -- you may well be listening while you look.
        """
        if key == Qt.Key_Escape:
            self._end_search()
            self.sounds.back()
            return True
        if key == Qt.Key_Backspace:
            # Deleting past the start leaves rather than falling through to the
            # crossbar's "back", which would be a category step out of nowhere.
            if self._query:
                self._set_query(self._query[:-1])
            else:
                self._end_search()
                self.sounds.back()
            return True
        # `text` and not `key`, which is what makes S, R and Space literal in
        # here while they stay bound to shuffle, repeat and play/pause outside.
        # Ctrl and Alt are excluded so a chord can't type its control character.
        # `text` first, because "".isprintable() is True and an arrow key's text
        # is "" -- without it every arrow would count as typing nothing.
        if (
            text
            and text.isprintable()
            and not modifiers & (Qt.ControlModifier | Qt.AltModifier)
        ):
            self._set_query(self._query + text)
            return True
        return None

    def _choose_folder(self) -> None:
        # Opening the picker *at* a folder that has been deleted is how you get
        # an empty dialog rooted nowhere. The reason someone is on this row is
        # often that the old folder is gone, so that is the likely case, not the
        # unlikely one.
        start = self.controller.folder
        if start is None or not start.is_dir():
            start = Path.home()
        chosen = QFileDialog.getExistingDirectory(self, "Music folder", str(start))
        if chosen:
            self.controller.open_folder(Path(chosen))

    # -- keyboard ----------------------------------------------------------
    #
    # The crossbar owns the arrow keys, so seeking moved onto Shift+Left/Right.
    # Every focusable child sets NoFocus, which is what keeps these firing no
    # matter what the user last clicked.

    def keyPressEvent(self, event) -> None:
        before = (self.stage.bar.index, self.stage.column.index)

        if not self._handle_key(event.key(), event.modifiers(), event.text()):
            super().keyPressEvent(event)
            return

        # The navigation blip is decided here rather than in ten branches: if
        # the cursor ended up somewhere other than it started, that was a move.
        # Which also buys the right silences for free -- Up against the top of a
        # list changes nothing, and a blip there would be the app claiming a
        # press did something when it didn't.
        #
        # Branches that speak for themselves (Enter, Space, the slider) leave
        # both indices alone. The exception is Ctrl+arrow, which asks for `move`
        # itself *and* shifts the Music cursor onto the new track; asking twice
        # inside the throttle window means once (`ui/sounds.py`).
        if (self.stage.bar.index, self.stage.column.index) != before:
            self.sounds.move()

        self._selection[self._category] = self.stage.column.index

    def _handle_key(self, key: int, modifiers, text: str = "") -> bool:
        """Do what `key` means. False if it means nothing here.

        `text` is the character the key produced, which only the search mode
        looks at -- and only it could, since every other branch here is about a
        key that has no character.
        """
        column = self.stage.column

        # A live search takes the keyboard before anything else, because the
        # keys it needs are ones this file has already spent: S and R are
        # shuffle and repeat, Space is play/pause, and all three are letters
        # somebody is entitled to type. Ahead of the stepped-into row too --
        # they are mutually exclusive, being on different categories, and the
        # order costs nothing to state.
        if self._searching:
            handled = self._search_key(key, modifiers, text)
            if handled is not None:
                return handled

        # Get Music takes the keyboard on the same terms and for the same
        # reasons, and needs no flag of its own: its column is always a header
        # over a list, so **the category is the mode**. The two are mutually
        # exclusive -- a Music search cannot be open on a different category --
        # so the order between them costs nothing to state.
        if self._category == CAT_GET:
            handled = self._get_key(key, modifiers, text)
            if handled is not None:
                return handled

        # A stepped-into row takes the horizontal arrows before the crossbar
        # sees them -- first, so the branch below can go on treating Left and
        # Right as category navigation without learning about the mode.
        #
        # Buying those two keys back is the entire reason this mode exists. The
        # standing rule is that Left/Right are category nav everywhere and can't
        # be spent on a value; stepping into a row is the one place that rule is
        # suspended, which is both what real XMB does with a slider item and
        # what the outline is announcing.
        if self._stepping:
            # Bare arrows only. Ctrl and Shift are transport -- you may well be
            # listening to something while you pick a theme, and the mode is
            # about this row's value, not about the whole keyboard.
            if key in (Qt.Key_Left, Qt.Key_Right) and not modifiers & (
                Qt.ControlModifier | Qt.ShiftModifier
            ):
                self._step_theme(+1 if key == Qt.Key_Right else -1)
                # Sounded here rather than left to the index comparison in
                # `keyPressEvent`: the cursor deliberately hasn't moved, and
                # this press did do something.
                self.sounds.move()
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape, Qt.Key_Backspace):
                self._stop_stepping()
                self.sounds.back()
                return True
            # Everything else falls through on purpose -- Up, Down, Home, End.
            # They move the cursor, which means the user has left this row, and
            # `index_changed` closes the mode for them. Same exit the wheel and
            # a click on another row already take, and it needs no branch here.

        # On Now Playing there is no list, so Up and Down have nothing to
        # navigate and drive the slider instead. That's what lets this page have
        # no "press Enter to adjust" step: the arrows can't mean anything else,
        # and the hint under the track says so up front.
        if self._category == CAT_NOW and key in (Qt.Key_Up, Qt.Key_Down):
            self._set_speed(self._speed + (SPEED_STEP if key == Qt.Key_Up else -SPEED_STEP))
            return True

        if key in (Qt.Key_Left, Qt.Key_Right):
            forward = key == Qt.Key_Right
            if modifiers & Qt.ControlModifier:
                self._skip(+1 if forward else -1)
            elif modifiers & Qt.ShiftModifier:
                self.controller.nudge(SEEK_STEP if forward else -SEEK_STEP)
            else:
                self.stage.bar.step(1 if forward else -1)
            return True

        if key == Qt.Key_Up:
            column.step(-1)
        elif key == Qt.Key_Down:
            column.step(+1)
        elif key == Qt.Key_PageUp:
            column.step(-PAGE)
        elif key == Qt.Key_PageDown:
            column.step(+PAGE)
        elif key == Qt.Key_Home:
            column.set_index(0)
        elif key == Qt.Key_End:
            column.set_index(column.count - 1)
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            column.activate()
        elif key == Qt.Key_Backspace:
            self.stage.bar.step(-1)  # XMB's "back" is a step left
        elif key == Qt.Key_Space:
            self._toggle()
        # The first letter keys the app has ever bound, and they were free --
        # `_handle_key` returned False for every one of them. No modifier check,
        # like Space above: there is nothing else `S` could be doing.
        elif key == Qt.Key_S:
            self._shuffle_pressed()
        elif key == Qt.Key_R:
            self._repeat_pressed()
        # Music only: there are seven Settings rows and one Now Playing page,
        # and neither is a list anybody needs to narrow. Returning False rather
        # than swallowing it keeps `/` free to mean something else one day.
        elif key == Qt.Key_Slash or (key == Qt.Key_F and modifiers & Qt.ControlModifier):
            if self._category != CAT_MUSIC:
                return False
            self._begin_search()
        elif key == Qt.Key_F11 or (key == Qt.Key_Escape and self.isFullScreen()):
            self._fullscreen()
        else:
            return False
        return True


def _short(text: str, limit: int = 42) -> str:
    """A title cut to something the status line can hold.

    A YouTube title is the least bounded string this app has ever drawn -- worse
    than a tag, worse than a folder name, because it is written to be a headline.
    The status line is the small font at the right edge and has no elision of its
    own, so this is the "a field whose text comes from a file has no length"
    convention applied one step further out.
    """
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _speed_fraction(speed: float) -> float:
    span = settings_mod.MAX_SPEED - settings_mod.MIN_SPEED
    if span <= 0:
        return 0.0
    return min(1.0, max(0.0, (speed - settings_mod.MIN_SPEED) / span))


def _credit(track) -> str:
    """`Artist · Album`, or whichever of them the file actually named.

    Empty when it named neither, which is most of this library -- and empty is
    a line the page draws nothing on rather than a line it leaves out.
    """
    return "   ·   ".join(part for part in (track.artist, track.album) if part)


def _cover_image(data: bytes | None) -> QImage | None:
    """Cover bytes as a `QImage`, or `None` if there isn't a usable one.

    `core.tags` hands up whatever bytes sat in the frame and stops there -- it
    has no image library and isn't allowed one. This is the other half of that
    seam, and the half that stayed put: only the *reading* moved behind the
    controller. A frame holding something Qt can't decode is the same as no
    frame -- the note glyph is a better answer than a black square.
    """
    if not data:
        return None
    image = QImage.fromData(data)
    return None if image.isNull() else image
