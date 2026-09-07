"""The bottom bar: seek, transport buttons, volume.

Speed is deliberately *not* here. It used to be, on the grounds that the live
speed slider is the whole point of the app and should be on screen in every
category -- but once Now Playing became the page for the effect, keeping a
second slider down here meant two controls for one value, which is the same
redundancy that got the transport actions removed from that column. Now Playing
owns speed; this bar owns everything about the track.

Seek commits on release, volume is live. That split is from the decisions log:
a live seek would post a fade-jump-fade per pixel and sound like a skipping CD.
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

from mp3player.ui import theme

SEEK_SCALE = 10  # tenths of a second: smooth enough at the 30 Hz poll

PREVIOUS_GLYPH = "⏮"
NEXT_GLYPH = "⏭"
PLAY_GLYPH = "▶"
PAUSE_GLYPH = "❚❚"
# The repeat button swaps its glyph the way the play button does, so "all" and
# "one" are told apart by the mark and not only by whether it is lit.
#
# NOT the emoji trio (U+1F500 shuffle, U+1F501/2 repeat), which is what these
# obviously want to be and what shipped for about an hour. Segoe UI Symbol hands
# those three to Segoe UI Emoji, which is a *colour* font: they came out as blue
# rounded tiles that look nothing like the transport glyphs beside them and --
# the part that actually matters -- ignore `color:` in the stylesheet entirely,
# so the lit/dim state the buttons exist to show could not be drawn at all.
# These are monochrome, in the same font as the rest of the bar, and take the
# accent like everything else.
# `⇄` and not one of the *crossing* arrows (U+2928, U+292D, U+292E), which are
# what shuffle actually means and were tried first: at 15 px the diagonals and
# their heads collapse into a four-pixel scribble, while two horizontal arrows
# keep both heads. The same trade as the app icon dropping its taper below
# 24 px -- the mark that survives the size beats the mark that is right.
SHUFFLE_GLYPH = "⇄"  # U+21C4, two arrows passing
REPEAT_ALL_GLYPH = "⭮"  # U+2B6E, a clockwise loop
REPEAT_ONE_GLYPH = "⭮¹"  # the same loop, and the one thing it will play


def clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


class TransportBar(QWidget):
    """Everything you can do to the current track without leaving the crossbar."""

    seek_requested = Signal(float)  # seconds, on release
    volume_requested = Signal(float)
    play_pressed = Signal()
    next_pressed = Signal()
    previous_pressed = Signal()
    # Presses, not values: these two say the button was clicked and let the
    # controller decide what the next state is. The tri-state one has to work
    # that way round, and having both do it keeps one path.
    shuffle_pressed = Signal()
    repeat_pressed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(theme.TRANSPORT_HEIGHT)
        self.setStyleSheet(theme.transport_qss())

        self._build()
        self._connect()

    def refresh_accent(self) -> None:
        """Re-apply the stylesheet so the seek fill follows the speed slider.

        This bar is the only part of the app coloured by stylesheet rather than
        by a paintEvent, so it is the only part that doesn't pick a new accent
        up on its own. Called from `MainWindow._on_speed`, and only when
        `theme.set_accent_fraction` says the colour actually moved -- re-applying
        a stylesheet re-polishes the whole widget tree, and a drag would
        otherwise do that on every mouse-move.
        """
        self.setStyleSheet(theme.transport_qss())

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
        # Checkable purely for the look: `QPushButton:checked` in the transport
        # stylesheet is what lights them, which costs no dynamic property and no
        # `unpolish`/`polish` dance, and means the lit colour follows the speed
        # ramp through `refresh_accent` like every other accent in the bar.
        self.shuffle_button = _glyph_button(SHUFFLE_GLYPH, checkable=True)
        self.repeat_button = _glyph_button(REPEAT_ALL_GLYPH, checkable=True)

        # The only thing on the bottom row allowed to take the leftover space --
        # and the only thing allowed to shrink to nothing.
        self.title = _ElidingLabel("nothing loaded")

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
        # The mode pair sits after the transport trio and before the gap: they
        # are about the track *after* this one, which is where the eye is
        # already going. The title is the only thing that gives ground for them,
        # and it is the one built to (`_ElidingLabel`, `QSizePolicy.Ignored`) --
        # 68 px out of the ~356 it has at the 720 px minimum.
        bottom.addWidget(self.shuffle_button)
        bottom.addWidget(self.repeat_button)
        bottom.addSpacing(10)
        bottom.addWidget(self.title, 1)
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
        # `clicked`, not `toggled`: a checkable button emits `toggled` when
        # `setChecked` moves it too, so the state coming back from the
        # controller would look like a second press and loop. `clicked` is
        # user-only. The button toggles itself on the way out and `set_shuffle`
        # / `set_repeat` put it where the controller actually landed -- which is
        # the same value, synchronously, unless something refused.
        self.shuffle_button.clicked.connect(self.shuffle_pressed)
        self.repeat_button.clicked.connect(self.repeat_pressed)

        self.seek.sliderMoved.connect(self._on_seek_preview)
        self.seek.sliderReleased.connect(self._on_seek_commit)

        self.volume.valueChanged.connect(
            lambda value: self.volume_requested.emit(value / 100)
        )

    # -- state in ----------------------------------------------------------

    def set_title(self, title: str) -> None:
        self.title.setText(title)

    def set_playing(self, playing: bool) -> None:
        self.play_button.setText(PAUSE_GLYPH if playing else PLAY_GLYPH)

    def set_shuffle(self, on: bool) -> None:
        self.shuffle_button.setChecked(on)

    def set_repeat(self, on: bool, *, one: bool = False) -> None:
        """`on` lights the button; `one` swaps its glyph.

        Two facts rather than the mode's name, because every widget in this
        package imports `theme` and `motion` and nothing else. Turning a
        controller value into a look is the window's job, and this is the same
        split as `set_playing` taking a bool rather than asking the engine.
        """
        self.repeat_button.setChecked(on)
        self.repeat_button.setText(REPEAT_ONE_GLYPH if one else REPEAT_ALL_GLYPH)

    def set_position(self, position: float, duration: float) -> None:
        self.duration.setText(clock(duration))
        if self.seek.isSliderDown():
            return  # the user owns the handle; don't fight the drag
        self.elapsed.setText(clock(position))
        self.seek.setEnabled(duration > 0)
        self.seek.setRange(0, int(duration * SEEK_SCALE))
        self.seek.setValue(int(position * SEEK_SCALE))

    def set_volume(self, volume: float) -> None:
        self.volume_value.setText(f"{volume * 100:.0f}%")
        _silently(self.volume, round(volume * 100))

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

    def setText(self, text: str) -> None:
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


def _glyph_button(glyph: str, *, checkable: bool = False) -> QPushButton:
    button = QPushButton(glyph)
    button.setFixedSize(theme.BUTTON_W, theme.BUTTON_H)
    button.setCursor(Qt.PointingHandCursor)
    button.setFocusPolicy(Qt.NoFocus)  # keys belong to the crossbar, not here
    button.setFont(theme.font(15, family=theme.GLYPH_FAMILY))
    button.setCheckable(checkable)
    return button


def _silently(slider: QSlider, value: int) -> None:
    """Move a slider to match the controller without echoing back into it."""
    slider.blockSignals(True)
    slider.setValue(value)
    slider.blockSignals(False)
