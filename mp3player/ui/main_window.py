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

from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QFileDialog, QVBoxLayout, QWidget

from mp3player.core import settings as settings_mod
from mp3player.core.library import ScanResult
from mp3player.ui import theme
from mp3player.ui.chrome import ChromeWindow
from mp3player.ui.controller import SEEK_STEP, PlayerController
from mp3player.ui.widgets.crossbar import Category, Crossbar
from mp3player.ui.widgets.item_column import Header, Item, ItemColumn
from mp3player.ui.widgets.transport import TransportBar

CAT_NOW, CAT_MUSIC, CAT_SETTINGS = 0, 1, 2

CATEGORIES = (
    Category("▶", "Now Playing"),
    Category("♪", "Music"),
    Category("⚙", "Settings"),
)

STATUS_MS = 6000  # how long a failure line stays up
PAGE = 5  # items per PageUp/PageDown


class XmbStage(QWidget):
    """The cross itself: crossbar and item column, stacked and full-bleed.

    Both children are transparent to the mouse so this one widget can decide
    what a click meant -- they overlap, and letting either of them eat events
    would make the other unclickable.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.bar = Crossbar(self)
        self.column = ItemColumn(self)
        self._status = ""

        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.setInterval(STATUS_MS)
        self._status_timer.timeout.connect(lambda: self.set_status(""))

    def resizeEvent(self, event) -> None:
        # Not a layout: they're deliberately on top of each other.
        for child in (self.bar, self.column):
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
        painter.drawText(
            QRect(
                theme.RIGHT_MARGIN,
                self.height() - theme.STATUS_MARGIN - 22,
                self.width() - 2 * theme.RIGHT_MARGIN,
                22,
            ),
            Qt.AlignLeft | Qt.AlignVCenter,
            self._status,
        )

    # -- mouse -------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        pos = event.position().toPoint()

        item = self.column.hit(pos)
        if item is not None:
            # Click to select, click again to open -- the same row twice is the
            # mouse equivalent of Down-then-Enter, and it makes a single click
            # on the already-selected track do the obvious thing.
            if item == self.column.index:
                self.column.activate()
            else:
                self.column.set_index(item)
            return

        category = self.bar.hit(pos)
        if category is not None:
            self.bar.set_index(category)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        if self.column.hit(event.position().toPoint()) is not None:
            self.column.activate()

    def wheelEvent(self, event) -> None:
        steps = event.angleDelta().y() // 120
        if steps:
            self.column.step(-steps)


class MainWindow(ChromeWindow):
    def __init__(self, controller: PlayerController) -> None:
        super().__init__("XMB PLAYER")
        self.controller = controller

        # Per-category cursors: stepping away from Music and back should land
        # where you left, not at the top of a 200-track list.
        self._selection = [0, 0, 0]
        self._category = CAT_NOW  # mirrors `stage.bar.index`, see `_on_category`
        self._library = ScanResult()
        self._folder: Path | None = None
        self._playing = False
        self._speed = settings_mod.DEFAULT_SPEED

        self._build()
        self._connect()
        self._refresh_column(reset=True)

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
        self.setFocusPolicy(Qt.StrongFocus)

    def _connect(self) -> None:
        controller = self.controller

        controller.library_changed.connect(self._on_library)
        controller.folder_changed.connect(self._on_folder)
        controller.track_changed.connect(self._on_track)
        controller.position_changed.connect(self.transport.set_position)
        controller.playing_changed.connect(self._on_playing)
        controller.speed_changed.connect(self._on_speed)
        controller.volume_changed.connect(self.transport.set_volume)
        controller.failed.connect(self.stage.set_status)

        self.stage.bar.index_changed.connect(self._on_category)
        self.stage.column.activated.connect(self._activate)

        self.transport.play_pressed.connect(controller.toggle)
        self.transport.next_pressed.connect(controller.next_track)
        self.transport.previous_pressed.connect(controller.previous_track)
        self.transport.seek_requested.connect(controller.seek)
        self.transport.speed_requested.connect(controller.set_speed)
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

    def _on_playing(self, playing: bool) -> None:
        self._playing = playing
        self.transport.set_playing(playing)
        self._refresh_column()

    def _on_speed(self, speed: float) -> None:
        self._speed = speed
        self.transport.set_speed(speed)
        self._refresh_column()

    # -- categories and items ---------------------------------------------

    def _on_category(self, index: int) -> None:
        # The crossbar has already moved by the time this fires, so the cursor
        # for the category we just left has to be banked against the mirrored
        # index rather than against `bar.index`.
        self._selection[self._category] = self.stage.column.index
        self._category = index
        self._refresh_column(restore=True)

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

        if category == CAT_NOW:
            self.stage.column.set_items(
                self._now_playing_items(),
                header=self._now_playing_header(),
                index=index,
            )
        elif category == CAT_MUSIC:
            self.stage.column.set_items(
                self._music_items(), index=index, empty_text=self._music_empty_text()
            )
        else:
            self.stage.column.set_items(self._settings_items(), index=index)

        self._selection[category] = self.stage.column.index

    def _now_playing_header(self) -> Header:
        track = self.controller.current
        where = self._folder.name if self._folder else "no folder"
        return Header(
            title=track.title if track else "Nothing playing",
            subtitle=f"{_speed_name(self._speed)} {self._speed:.2f}x  ·  {where}",
        )

    def _now_playing_items(self) -> list[Item]:
        return [
            Item("Pause" if self._playing else "Play"),
            Item("Next track"),
            Item("Previous track"),
            Item("Restart track"),
            Item("Find in Music"),
        ]

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
        return [
            Item("Music folder", self._folder.name if self._folder else "not set"),
            Item("Rescan folder", counts),
            Item("Nightcore", f"{settings_mod.NIGHTCORE_SPEED:.2f}x"),
            Item("Normal", f"{settings_mod.DEFAULT_SPEED:.2f}x"),
            Item("Daycore", f"{settings_mod.DAYCORE_SPEED:.2f}x"),
            Item("Full screen", "F11"),
            Item("Quit", ""),
        ]

    # -- activation --------------------------------------------------------

    def _activate(self, index: int) -> None:
        category = self._category
        if category == CAT_NOW:
            self._activate_now(index)
        elif category == CAT_MUSIC:
            self.controller.play_index(index)
        else:
            self._activate_settings(index)

    def _activate_now(self, index: int) -> None:
        if index == 0:
            self.controller.toggle()
        elif index == 1:
            self.controller.next_track()
        elif index == 2:
            self.controller.previous_track()
        elif index == 3:
            self.controller.seek(0.0)
        elif index == 4:
            self.stage.bar.set_index(CAT_MUSIC)

    def _activate_settings(self, index: int) -> None:
        if index == 0:
            self._choose_folder()
        elif index == 1:
            self.controller.rescan()
        elif index == 2:
            self.controller.set_speed(settings_mod.NIGHTCORE_SPEED)
        elif index == 3:
            self.controller.set_speed(settings_mod.DEFAULT_SPEED)
        elif index == 4:
            self.controller.set_speed(settings_mod.DAYCORE_SPEED)
        elif index == 5:
            self.toggle_fullscreen()
        elif index == 6:
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
        key = event.key()
        modifiers = event.modifiers()

        if key in (Qt.Key_Left, Qt.Key_Right):
            forward = key == Qt.Key_Right
            if modifiers & Qt.ControlModifier:
                self.controller.next_track() if forward else self.controller.previous_track()
            elif modifiers & Qt.ShiftModifier:
                self.controller.nudge(SEEK_STEP if forward else -SEEK_STEP)
            else:
                self.stage.bar.step(1 if forward else -1)
            return

        if key == Qt.Key_Up:
            self.stage.column.step(-1)
        elif key == Qt.Key_Down:
            self.stage.column.step(+1)
        elif key == Qt.Key_PageUp:
            self.stage.column.step(-PAGE)
        elif key == Qt.Key_PageDown:
            self.stage.column.step(+PAGE)
        elif key == Qt.Key_Home:
            self.stage.column.set_index(0)
        elif key == Qt.Key_End:
            self.stage.column.set_index(self.stage.column.count - 1)
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            self.stage.column.activate()
        elif key == Qt.Key_Backspace:
            self.stage.bar.step(-1)  # XMB's "back" is a step left
        elif key == Qt.Key_Space:
            self.controller.toggle()
        elif key == Qt.Key_F11:
            self.toggle_fullscreen()
        elif key == Qt.Key_Escape and self.isFullScreen():
            self.toggle_fullscreen()
        else:
            super().keyPressEvent(event)
            return

        self._selection[self._category] = self.stage.column.index


def _speed_name(speed: float) -> str:
    if speed > 1.02:
        return "Nightcore"
    if speed < 0.98:
        return "Daycore"
    return "Normal"
