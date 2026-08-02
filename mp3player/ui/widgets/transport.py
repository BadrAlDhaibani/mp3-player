"""The bottom bar: seek, transport buttons, speed and volume.

Speed lives here rather than behind the Settings category on purpose. The
decisions log calls the live speed slider "the entire app" -- dragging it and
hearing the pitch move is the thing this player exists to do, so it stays on
screen no matter which category you're in. The Settings column offers the three
presets; this is the continuous control.

Seek commits on release, speed and volume are live. That split is also from the
decisions log: a live seek would post a fade-jump-fade per pixel and sound like
a skipping CD, while a live speed change is the whole point.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from mp3player.core import settings as settings_mod
from mp3player.ui import theme

# Both continuous knobs go through integer sliders.
SPEED_SCALE = 100  # 0.50x .. 1.50x  ->  50 .. 150
SEEK_SCALE = 10  # tenths of a second: smooth enough at the 30 Hz poll

PREVIOUS_GLYPH = "⏮"
NEXT_GLYPH = "⏭"
PLAY_GLYPH = "▶"
PAUSE_GLYPH = "❚❚"


def clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


class TransportBar(QWidget):
    """Everything you can do to the current track without leaving the crossbar."""

    seek_requested = Signal(float)  # seconds, on release
    speed_requested = Signal(float)
    volume_requested = Signal(float)
    play_pressed = Signal()
    next_pressed = Signal()
    previous_pressed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(theme.TRANSPORT_HEIGHT)
        self.setStyleSheet(theme.transport_qss())

        self._build()
        self._connect()

    # -- construction ------------------------------------------------------

    def _build(self) -> None:
        self.elapsed = _label("0:00", 12, theme.TEXT_DIM)
        self.duration = _label("0:00", 12, theme.TEXT_FAINT)
        self.elapsed.setFixedWidth(46)
        self.duration.setFixedWidth(46)
        self.duration.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.seek = QSlider(Qt.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.setEnabled(False)
        self.seek.setFocusPolicy(Qt.NoFocus)

        self.previous_button = _glyph_button(PREVIOUS_GLYPH)
        self.play_button = _glyph_button(PLAY_GLYPH)
        self.next_button = _glyph_button(NEXT_GLYPH)

        # The only thing on the bottom row allowed to take the leftover space --
        # and the only thing allowed to shrink to nothing.
        self.title = _ElidingLabel("nothing loaded")

        self.speed = _slider(*theme.SPEED_SLIDER)
        self.speed.setRange(
            int(settings_mod.MIN_SPEED * SPEED_SCALE),
            int(settings_mod.MAX_SPEED * SPEED_SCALE),
        )
        self.speed_value = _label("1.00x", 12, theme.ACCENT)
        self.speed_value.setFixedWidth(theme.SPEED_VALUE_W)

        self.volume = _slider(*theme.VOLUME_SLIDER)
        self.volume.setRange(0, 100)
        self.volume_value = _label("80%", 12, theme.TEXT_FAINT)
        self.volume_value.setFixedWidth(theme.VOLUME_VALUE_W)

        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(self.elapsed)
        top.addWidget(self.seek, 1)
        top.addWidget(self.duration)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        bottom.addWidget(self.previous_button)
        bottom.addWidget(self.play_button)
        bottom.addWidget(self.next_button)
        bottom.addSpacing(10)
        bottom.addWidget(self.title, 1)
        bottom.addWidget(_label("SPEED", 10, theme.TEXT_FAINT, spaced=True))
        bottom.addWidget(self.speed)
        bottom.addWidget(self.speed_value)
        bottom.addSpacing(12)
        bottom.addWidget(_label("VOL", 10, theme.TEXT_FAINT, spaced=True))
        bottom.addWidget(self.volume)
        bottom.addWidget(self.volume_value)

        root = QVBoxLayout(self)
        root.setContentsMargins(
            theme.TRANSPORT_MARGIN, 14, theme.TRANSPORT_MARGIN, 16
        )
        root.setSpacing(12)
        root.addLayout(top)
        root.addLayout(bottom)

    def _connect(self) -> None:
        self.previous_button.clicked.connect(self.previous_pressed)
        self.play_button.clicked.connect(self.play_pressed)
        self.next_button.clicked.connect(self.next_pressed)

        self.seek.sliderMoved.connect(self._on_seek_preview)
        self.seek.sliderReleased.connect(self._on_seek_commit)

        self.speed.valueChanged.connect(
            lambda value: self.speed_requested.emit(value / SPEED_SCALE)
        )
        self.volume.valueChanged.connect(
            lambda value: self.volume_requested.emit(value / 100)
        )

    # -- state in ----------------------------------------------------------

    def set_title(self, title: str) -> None:
        self.title.setText(title)

    def set_playing(self, playing: bool) -> None:
        self.play_button.setText(PAUSE_GLYPH if playing else PLAY_GLYPH)

    def set_position(self, position: float, duration: float) -> None:
        self.duration.setText(clock(duration))
        if self.seek.isSliderDown():
            return  # the user owns the handle; don't fight the drag
        self.elapsed.setText(clock(position))
        self.seek.setEnabled(duration > 0)
        self.seek.setRange(0, int(duration * SEEK_SCALE))
        self.seek.setValue(int(position * SEEK_SCALE))

    def set_speed(self, speed: float) -> None:
        self.speed_value.setText(f"{speed:.2f}x")
        _silently(self.speed, int(round(speed * SPEED_SCALE)))

    def set_volume(self, volume: float) -> None:
        self.volume_value.setText(f"{volume * 100:.0f}%")
        _silently(self.volume, int(round(volume * 100)))

    # -- seek --------------------------------------------------------------

    def _on_seek_preview(self, value: int) -> None:
        self.elapsed.setText(clock(value / SEEK_SCALE))

    def _on_seek_commit(self) -> None:
        self.seek_requested.emit(self.seek.value() / SEEK_SCALE)


class _ElidingLabel(QLabel):
    """A label that shrinks to nothing and ellipsises, instead of clipping.

    A plain QLabel demands the width of its text and, when the row can't give
    it, gets truncated mid-word with no ellipsis to say so. `Ignored` lets the
    layout squeeze this to zero; `paintEvent` decides what still fits.
    """

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self._full = text
        self.setFont(theme.font(14))
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def setText(self, text: str) -> None:  # noqa: N802 -- Qt's name
        self._full = text
        super().setText(text)
        self.update()

    def text(self) -> str:
        return self._full

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setFont(self.font())
        painter.setPen(theme.TEXT)
        elided = QFontMetrics(self.font()).elidedText(
            self._full, Qt.ElideRight, self.width()
        )
        painter.drawText(self.rect(), Qt.AlignLeft | Qt.AlignVCenter, elided)


def _label(text: str, pixels: int, color, *, spaced: bool = False) -> QLabel:
    label = QLabel(text)
    label.setFont(theme.font(pixels, letter_spacing=spaced))
    label.setStyleSheet(f"color: {theme.rgba(color)}; background: transparent;")
    return label


def _slider(minimum_width: int, maximum_width: int) -> QSlider:
    """A slider that can give ground. Fixed widths are what broke the row."""
    slider = QSlider(Qt.Horizontal)
    slider.setMinimumWidth(minimum_width)
    slider.setMaximumWidth(maximum_width)
    slider.setFocusPolicy(Qt.NoFocus)
    return slider


def _glyph_button(glyph: str) -> QPushButton:
    button = QPushButton(glyph)
    button.setFixedSize(theme.BUTTON_W, theme.BUTTON_H)
    button.setCursor(Qt.PointingHandCursor)
    button.setFocusPolicy(Qt.NoFocus)  # keys belong to the crossbar, not here
    button.setFont(theme.font(15, family=theme.GLYPH_FAMILY))
    return button


def _silently(slider: QSlider, value: int) -> None:
    """Move a slider to match the controller without echoing back into it."""
    slider.blockSignals(True)
    slider.setValue(value)
    slider.blockSignals(False)
