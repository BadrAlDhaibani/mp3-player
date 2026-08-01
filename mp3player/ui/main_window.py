"""The ugly window.

Batch 3 exists to prove the wiring, not the look: stock widgets, default style,
no theme. Batch 4 replaces this file wholesale with the XMB shell and keeps
`PlayerController` underneath unchanged -- so nothing here may reach past the
controller into the engine.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from mp3player.core import settings as settings_mod
from mp3player.core.library import ScanResult
from mp3player.ui.controller import SEEK_STEP, PlayerController

# Sliders are integers, so both continuous knobs get a scale factor.
SPEED_SCALE = 100  # 0.50x .. 1.50x  ->  50 .. 150
SEEK_SCALE = 10  # tenths of a second, fine enough to look smooth at 30 Hz


def clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


class MainWindow(QMainWindow):
    def __init__(self, controller: PlayerController) -> None:
        super().__init__()
        self.controller = controller
        self.setWindowTitle("XMB Player")
        self.resize(560, 620)

        self._build()
        self._connect()
        self._shortcuts()

    # -- construction ------------------------------------------------------

    def _build(self) -> None:
        self.folder_button = QPushButton("Open folder...")
        self.folder_label = QLabel("no folder")
        self.folder_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.list = QListWidget()
        self.status_label = QLabel("")

        self.now_playing = QLabel("nothing loaded")
        self.time_label = QLabel("0:00 / 0:00")

        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setRange(0, 0)

        self.prev_button = QPushButton("|<")
        self.play_button = QPushButton("Play")
        self.next_button = QPushButton(">|")

        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(
            int(settings_mod.MIN_SPEED * SPEED_SCALE),
            int(settings_mod.MAX_SPEED * SPEED_SCALE),
        )
        self.speed_slider.setTickInterval(10)
        self.speed_slider.setTickPosition(QSlider.TicksBelow)
        self.speed_label = QLabel("1.00x")

        self.daycore_button = QPushButton("Daycore")
        self.normal_button = QPushButton("Normal")
        self.nightcore_button = QPushButton("Nightcore")

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_label = QLabel("80%")

        root = QVBoxLayout()
        root.addLayout(_row(self.folder_button, self.folder_label, stretch=1))
        root.addWidget(self.list, stretch=1)
        root.addWidget(self.status_label)
        root.addLayout(_row(self.now_playing, stretch=1, then=self.time_label))
        root.addWidget(self.seek_slider)
        root.addLayout(
            _row(self.prev_button, self.play_button, self.next_button, stretch=1)
        )
        root.addLayout(
            _row(
                QLabel("Speed"),
                self.speed_slider,
                stretch=1,
                then=self.speed_label,
            )
        )
        root.addLayout(
            _row(self.daycore_button, self.normal_button, self.nightcore_button)
        )
        root.addLayout(
            _row(QLabel("Volume"), self.volume_slider, stretch=1, then=self.volume_label)
        )

        central = QWidget()
        central.setLayout(root)
        self.setCentralWidget(central)

    def _connect(self) -> None:
        controller = self.controller

        controller.library_changed.connect(self._on_library)
        controller.folder_changed.connect(self._on_folder)
        controller.track_changed.connect(self._on_track)
        controller.position_changed.connect(self._on_position)
        controller.playing_changed.connect(self._on_playing)
        controller.speed_changed.connect(self._on_speed)
        controller.volume_changed.connect(self._on_volume)
        controller.failed.connect(self.status_label.setText)

        self.folder_button.clicked.connect(self._choose_folder)
        self.list.itemActivated.connect(self._on_item_activated)

        self.prev_button.clicked.connect(controller.previous_track)
        self.play_button.clicked.connect(controller.toggle)
        self.next_button.clicked.connect(controller.next_track)

        # Seeking commits on release; while the handle is down the poll leaves
        # the slider alone (see `_on_position`) so it doesn't fight the drag.
        self.seek_slider.sliderMoved.connect(self._on_seek_preview)
        self.seek_slider.sliderReleased.connect(self._on_seek_commit)

        # Speed is live by design -- watching the slider change the pitch as you
        # drag it is the entire point of the app.
        self.speed_slider.valueChanged.connect(self._on_speed_slider)
        self.volume_slider.valueChanged.connect(self._on_volume_slider)

        self.daycore_button.clicked.connect(
            lambda: self.controller.set_speed(settings_mod.DAYCORE_SPEED)
        )
        self.normal_button.clicked.connect(lambda: self.controller.set_speed(1.0))
        self.nightcore_button.clicked.connect(
            lambda: self.controller.set_speed(settings_mod.NIGHTCORE_SPEED)
        )

    def _shortcuts(self) -> None:
        for keys, slot in (
            ("Space", self.controller.toggle),
            ("Ctrl+Right", self.controller.next_track),
            ("Ctrl+Left", self.controller.previous_track),
            ("Right", lambda: self.controller.nudge(+SEEK_STEP)),
            ("Left", lambda: self.controller.nudge(-SEEK_STEP)),
        ):
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.activated.connect(slot)

    # -- controller -> widgets --------------------------------------------

    def _on_library(self, result: ScanResult) -> None:
        self.list.clear()
        for track in result.tracks:
            item = QListWidgetItem(track.title)
            item.setToolTip(str(track.path))
            self.list.addItem(item)

        parts = [f"{len(result.tracks)} playable"]
        if result.skipped:
            # Not real MP3s -- mislabelled MP4/AAC, mostly. Say so rather than
            # letting the user wonder where those files went.
            parts.append(f"{len(result.skipped)} skipped (not MP3)")
        self.status_label.setText(", ".join(parts))

    def _on_folder(self, folder: Path | None) -> None:
        self.folder_label.setText(str(folder) if folder else "no folder")

    def _on_track(self, index: int) -> None:
        self.list.setCurrentRow(index)
        track = self.controller.current
        self.now_playing.setText(track.title if track else "nothing loaded")

    def _on_position(self, position: float, duration: float) -> None:
        self.time_label.setText(f"{clock(position)} / {clock(duration)}")
        if self.seek_slider.isSliderDown():
            return  # the user owns the handle right now
        self.seek_slider.setRange(0, int(duration * SEEK_SCALE))
        self.seek_slider.setValue(int(position * SEEK_SCALE))

    def _on_playing(self, playing: bool) -> None:
        self.play_button.setText("Pause" if playing else "Play")

    def _on_speed(self, speed: float) -> None:
        self.speed_label.setText(f"{speed:.2f}x")
        _without_signals(self.speed_slider, int(round(speed * SPEED_SCALE)))

    def _on_volume(self, volume: float) -> None:
        self.volume_label.setText(f"{volume * 100:.0f}%")
        _without_signals(self.volume_slider, int(round(volume * 100)))

    # -- widgets -> controller --------------------------------------------

    def _choose_folder(self) -> None:
        start = self.controller.folder or Path.home()
        chosen = QFileDialog.getExistingDirectory(self, "Music folder", str(start))
        if chosen:
            self.controller.open_folder(Path(chosen))

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        self.controller.play_index(self.list.row(item))

    def _on_seek_preview(self, value: int) -> None:
        duration = self.seek_slider.maximum() / SEEK_SCALE
        self.time_label.setText(f"{clock(value / SEEK_SCALE)} / {clock(duration)}")

    def _on_seek_commit(self) -> None:
        self.controller.seek(self.seek_slider.value() / SEEK_SCALE)

    def _on_speed_slider(self, value: int) -> None:
        self.controller.set_speed(value / SPEED_SCALE)

    def _on_volume_slider(self, value: int) -> None:
        self.controller.set_volume(value / 100)


def _row(*widgets: QWidget, stretch: int = 0, then: QWidget | None = None) -> QHBoxLayout:
    """A horizontal strip. `stretch` applies to the last of `widgets`."""
    layout = QHBoxLayout()
    for index, widget in enumerate(widgets):
        last = index == len(widgets) - 1
        layout.addWidget(widget, stretch if last else 0)
    if then is not None:
        layout.addWidget(then)
    return layout


def _without_signals(slider: QSlider, value: int) -> None:
    """Move a slider to match the controller without echoing back into it."""
    slider.blockSignals(True)
    slider.setValue(value)
    slider.blockSignals(False)
