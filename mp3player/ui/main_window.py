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

from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QFileDialog, QVBoxLayout, QWidget

from mp3player.core import settings as settings_mod
from mp3player.core.library import ScanResult
from mp3player.ui import theme
from mp3player.ui.chrome import ChromeWindow
from mp3player.ui.controller import SEEK_STEP, PlayerController
from mp3player.ui.sounds import Sounds
from mp3player.ui.widgets.crossbar import Category, Crossbar
from mp3player.ui.widgets.item_column import Item, ItemColumn
from mp3player.ui.widgets.now_playing import NowPlaying, NowPlayingPage
from mp3player.ui.widgets.transport import TransportBar, clock
from mp3player.ui.widgets.wave import WaveBackground

CAT_NOW, CAT_MUSIC, CAT_SETTINGS = 0, 1, 2


CATEGORIES = (
    Category("▶", "Now Playing"),
    Category("♪", "Music"),
    Category("⚙", "Settings"),
)

STATUS_MS = 6000  # how long a failure line stays up
PAGE = 5  # items per PageUp/PageDown
SPEED_STEP = 0.01  # one Up/Down press on the Now Playing page


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
        self._status = ""
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

    def set_status(self, text: str) -> None:
        self._status = text
        if text:
            self._status_timer.start()
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
        # where you left, not at the top of a 200-track list.
        self._selection = [0, 0, 0]
        self._category = CAT_NOW  # mirrors `stage.bar.index`, see `_on_category`
        self._library = ScanResult()
        self._folder: Path | None = None
        self._playing = False
        self._speed = settings_mod.DEFAULT_SPEED
        self._duration = 0.0

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
        self.stage.wave.set_fraction(_speed_fraction(self._speed))
        self.setFocusPolicy(Qt.StrongFocus)

    def _connect(self) -> None:
        controller = self.controller

        controller.library_changed.connect(self._on_library)
        controller.folder_changed.connect(self._on_folder)
        controller.track_changed.connect(self._on_track)
        controller.position_changed.connect(self._on_position)
        controller.playing_changed.connect(self._on_playing)
        controller.speed_changed.connect(self._on_speed)
        controller.volume_changed.connect(self.transport.set_volume)
        controller.failed.connect(self.stage.set_status)
        # The one sound wired to a controller signal rather than to an input:
        # a failure is the app answering back, and it is worth hearing whether
        # or not you were looking at the status line when it appeared.
        controller.failed.connect(lambda _message: self.sounds.error())

        self.stage.bar.index_changed.connect(self._on_category)
        self.stage.column.activated.connect(self._activate)
        self.stage.page.slider_moved.connect(self._on_slider_dragged)
        self.stage.moved.connect(self.sounds.move)

        self.transport.play_pressed.connect(self._toggle)
        self.transport.next_pressed.connect(lambda: self._skip(+1))
        self.transport.previous_pressed.connect(lambda: self._skip(-1))
        self.transport.seek_requested.connect(controller.seek)
        self.transport.volume_requested.connect(controller.set_volume)

    # -- controller -> shell ----------------------------------------------

    def _on_library(self, result: ScanResult) -> None:
        self._library = result
        self._selection[CAT_MUSIC] = 0
        if result.skipped:
            # Mislabelled MP4/AAC, mostly. Say so rather than letting the user
            # wonder where those files went.
            self.stage.set_status(
                f"{len(result.skipped)} file(s) skipped -- not really MP3"
            )
        self._refresh_column(reset=True)

    def _on_folder(self, folder: Path | None) -> None:
        self._folder = folder
        self._refresh_column()

    def _on_track(self, index: int) -> None:
        track = self.controller.current
        self.transport.set_title(track.title if track else "nothing loaded")
        if index >= 0:
            self._selection[CAT_MUSIC] = index
            if self._category == CAT_MUSIC:
                self.stage.column.set_index(index)
        self._refresh_column()

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
        # The wave's hue is the speed: deep blue at daycore, violet at
        # nightcore. It's the only part of the app that says what the effect is
        # doing while you're looking at some other category.
        self.stage.wave.set_fraction(_speed_fraction(speed))
        # Nothing to push at the transport bar any more -- the slider that shows
        # this lives in the Now Playing column, which `_refresh_column` repaints
        # along with the subtitle that names it.
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

    def _fullscreen(self) -> None:
        """F11 and Escape. The Settings row goes through `_activate`, which has
        already sounded its confirm by the time it gets here."""
        self.toggle_fullscreen()
        self.sounds.confirm() if self.isFullScreen() else self.sounds.back()

    # -- categories and items ---------------------------------------------

    def _on_category(self, index: int) -> None:
        # The crossbar has already moved by the time this fires, so the cursor
        # for the category we just left has to be banked against the mirrored
        # index rather than against `bar.index`.
        self._selection[self._category] = self.stage.column.index
        self._category = index
        self._refresh_column(restore=True)
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

        if category == CAT_NOW:
            self.stage.page.set_state(self._now_playing())
        elif category == CAT_MUSIC:
            self.stage.column.set_items(
                self._music_items(), index=index, empty_text=self._music_empty_text()
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
                else "No folder yet  --  Settings ▸ Music folder"
            )
        else:
            # The warped length is the one number only this app can tell you,
            # and it moves as the slider does. `duration` is the file's real
            # length, so dividing by speed gives the wallclock it'll actually
            # take -- 2:00 at 1.30x really is 1:32.
            first = f"{clock(self._duration)}"
            if self._duration > 0 and abs(self._speed - 1.0) > 0.005:
                first += f"   ·   plays in {clock(self._duration / self._speed)}"
                first += f" at {self._speed:.2f}x"
            second = (
                f"Track {self.controller.index + 1} of {len(self._library.tracks)}"
                f"   ·   {where}"
            )

        return NowPlaying(
            title=track.title if track else "Nothing playing",
            lines=(first, second),
            fraction=_speed_fraction(self._speed),
            speed_text=f"{self._speed:.2f}x",
        )

    def _music_items(self) -> list[Item]:
        playing = self.controller.index
        return [
            Item(track.title, marker=(i == playing))
            for i, track in enumerate(self._library.tracks)
        ]

    def _music_empty_text(self) -> str:
        if self._folder is None:
            return "No folder yet  --  Settings ▸ Music folder"
        return f"No playable MP3s in {self._folder.name}"

    def _settings_items(self) -> list[Item]:
        counts = f"{len(self._library.tracks)} tracks"
        if self._library.skipped:
            counts += f"  ·  {len(self._library.skipped)} skipped"
        # No speed presets here any more -- they're the two ends of the slider
        # on Now Playing, which is a better home for them than a settings list.
        return [
            Item("Music folder", self._folder.name if self._folder else "not set"),
            Item("Rescan folder", counts),
            Item("Full screen", "F11"),
            Item("Quit", ""),
        ]

    # -- activation --------------------------------------------------------

    def _activate(self, index: int) -> None:
        # One confirm for every activation, keyboard or mouse: `activated` is
        # only emitted when there is something to open, so an Enter on an empty
        # list is silent rather than a blip about nothing.
        self.sounds.confirm()
        # Now Playing has no items to activate -- it's a page, and its only
        # control answers to the arrow keys directly.
        if self._category == CAT_MUSIC:
            self.controller.play_index(index)
        elif self._category == CAT_SETTINGS:
            self._activate_settings(index)

    def _activate_settings(self, index: int) -> None:
        if index == 0:
            self._choose_folder()
        elif index == 1:
            self.controller.rescan()
        elif index == 2:
            self.toggle_fullscreen()
        elif index == 3:
            self.close()

    def _choose_folder(self) -> None:
        start = self.controller.folder or Path.home()
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

        if not self._handle_key(event.key(), event.modifiers()):
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

    def _handle_key(self, key: int, modifiers) -> bool:
        """Do what `key` means. False if it means nothing here."""
        column = self.stage.column

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
        elif key == Qt.Key_F11:
            self._fullscreen()
        elif key == Qt.Key_Escape and self.isFullScreen():
            self._fullscreen()
        else:
            return False
        return True


def _speed_fraction(speed: float) -> float:
    span = settings_mod.MAX_SPEED - settings_mod.MIN_SPEED
    if span <= 0:
        return 0.0
    return min(1.0, max(0.0, (speed - settings_mod.MIN_SPEED) / span))
