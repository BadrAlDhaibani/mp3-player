"""The Now Playing page: art, the track, and the Daycore/Nightcore slider.

Deliberately *not* an `ItemColumn`. A column pins its selection to the crossbar
row and scrolls everything else past it; this page puts the song title on that
row and hangs a fixed block beneath it, which is the opposite arrangement. Two
widgets saying two different things beats one widget with a mode.

Because there is no list here, Up and Down have nothing to navigate -- so they
drive the slider directly. That is the whole reason this page needs no
"press Enter to adjust" step: there is no other thing the arrows could mean, and
a hint under the track says so without the user having to find it.

This widget paints and measures. It decides nothing and formats nothing: the
window hands it finished strings, the stage routes its mouse.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import Property, QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics, QImage, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QWidget

from mp3player.ui import theme
from mp3player.ui.motion import Tween

DAYCORE_LABEL = "DAYCORE"
NIGHTCORE_LABEL = "NIGHTCORE"
HINT = "↑ ↓   adjust"


@dataclass(frozen=True, slots=True)
class NowPlaying:
    """Everything the page shows, already formatted."""

    title: str = "Nothing playing"
    lines: tuple[str, ...] = field(default_factory=tuple)
    fraction: float = 0.0  # 0..1 along the slider
    speed_text: str = "1.00x"


class NowPlayingPage(QWidget):
    """Paints the page and measures its slider. No state beyond what it shows."""

    slider_moved = Signal(float)  # 0..1, live -- emitted by the stage's drag

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # The stage routes clicks; this widget overlaps the crossbar, and
        # letting either of them eat events would break the other.
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._state = NowPlaying()
        self._art: QImage | None = None
        self._scaled: QPixmap | None = None
        self._scaled_size = QSize()
        self._appear = 1.0
        self._arrival = Tween(self, "appear", theme.APPEAR_MS)

    def set_state(self, state: NowPlaying) -> None:
        if state != self._state:
            self._state = state
            self.update()

    @property
    def state(self) -> NowPlaying:
        return self._state

    def set_art(self, image: QImage | None) -> None:
        """The current track's cover, or `None` for the note glyph.

        Kept off `NowPlaying` on purpose. That dataclass is "everything the page
        shows, already formatted" -- strings, rebuilt on every speed tick and
        every duration change -- and a cover is neither formatted nor cheap to
        compare. It changes once per track, so it arrives by its own door.
        """
        if image is self._art:
            return
        self._art = image
        self._scaled = None  # a new cover invalidates whatever we had scaled
        self._scaled_size = QSize()
        self.update()

    @property
    def art(self) -> QImage | None:
        return self._art

    # -- arrival -----------------------------------------------------------
    #
    # The page flies in when a crossbar step lands on it, the same way the item
    # column does. Nothing else here animates: the slider follows the engine
    # live, and easing it would put the handle somewhere the audio isn't.

    def _get_appear(self) -> float:
        return self._appear

    def _set_appear(self, value: float) -> None:
        self._appear = float(value)
        self.update()

    appear = Property(float, _get_appear, _set_appear)

    def enter(self) -> None:
        self._appear = 0.0
        self._arrival.to(1.0)

    def settle(self) -> None:
        self._arrival.finish()

    # -- geometry ----------------------------------------------------------

    def row_y(self) -> int:
        return int(self.height() * theme.CROSSBAR_Y_RATIO)

    def _text_width(self) -> int:
        return max(80, self.width() - theme.ITEM_X - theme.RIGHT_MARGIN)

    def track_rect(self) -> QRect | None:
        """The draggable part of the slider, or None if the window is too narrow."""
        metrics = QFontMetrics(theme.font(theme.SLIDER_END_LABEL, letter_spacing=True))
        left = (
            theme.ITEM_X
            + metrics.horizontalAdvance(DAYCORE_LABEL)
            + theme.SLIDER_LABEL_GAP
        )
        right = (
            theme.ITEM_X
            + self._text_width()
            - theme.SLIDER_VALUE_W
            - metrics.horizontalAdvance(NIGHTCORE_LABEL)
            - theme.SLIDER_LABEL_GAP
        )
        if right - left < theme.SLIDER_TRACK_MIN:
            return None

        y = self.row_y() + theme.NP_SLIDER
        return QRect(left, y - theme.SLIDER_HANDLE // 2, right - left, theme.SLIDER_HANDLE)

    def fraction_at(self, x: int) -> float:
        """Where `x` falls along the track, clamped to 0..1.

        Spans `width - 1` because both ends are *pixels*, not boundaries: the
        rightmost pixel has to mean 1.0, or clicking the visible end of the bar
        lands at 0.999 and nightcore is unreachable by mouse.
        """
        track = self.track_rect()
        if track is None or track.width() <= 1:
            return 0.0
        return min(1.0, max(0.0, (x - track.left()) / (track.width() - 1)))

    def art_rect(self) -> QRect | None:
        """The art placeholder, sized by the gutter left of the item column.

        Bounded by the gutter rather than by leftover vertical room, which is
        what makes it survive the 720x480 minimum -- stacked above a column it
        had nowhere to go and had to be dropped.
        """
        top = self.row_y() + theme.CATEGORY_LABEL_GAP + theme.ART_TOP_GAP
        size = min(
            theme.ART_MAX,
            theme.ITEM_X - 2 * theme.RIGHT_MARGIN,
            self.height() - theme.ART_BOTTOM_PAD - top,
        )
        if size < theme.ART_MIN:
            return None
        return QRect(theme.ITEM_X // 2 - size // 2, top, size, size)

    # -- painting ----------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        # Same arrival as the item column. A transform, so `track_rect` and
        # `art_rect` -- which the stage hit-tests against -- never see it.
        if self._appear < 1.0:
            painter.setOpacity(self._appear)
            painter.translate((1.0 - self._appear) * theme.APPEAR_OFFSET, 0)

        self._paint_art(painter)
        self._paint_title(painter)
        self._paint_info(painter)
        self._paint_slider(painter)

    def _paint_art(self, painter: QPainter) -> None:
        art = self.art_rect()
        if art is None:
            return

        cover = self._cover(art.size())
        if cover is not None:
            # Clipped rather than drawn square, so the cover keeps the same
            # rounded corners the placeholder had and the gutter doesn't gain a
            # hard-edged rectangle the moment a track happens to be tagged.
            outline = QPainterPath()
            outline.addRoundedRect(QRectF(art), 6, 6)
            painter.save()
            painter.setClipPath(outline)
            painter.drawPixmap(art, cover)
            painter.restore()
            painter.setPen(theme.PANEL_EDGE)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(art, 6, 6)
            return

        painter.setPen(theme.PANEL_EDGE)
        painter.setBrush(theme.PANEL)
        painter.drawRoundedRect(art, 6, 6)
        painter.setBrush(Qt.NoBrush)

        # No cover in the file -- which is most of this library. The note glyph
        # that stood in for every track before Batch 8 is still what an untagged
        # one gets, so the gutter is never empty.
        painter.setFont(
            theme.font(max(24, art.width() * 2 // 5), family=theme.GLYPH_FAMILY)
        )
        painter.setPen(theme.faded(theme.TEXT_FAINT, 0.7))
        painter.drawText(art, Qt.AlignCenter, "♪")

    def _cover(self, size: QSize) -> QPixmap | None:
        """The cover scaled to exactly `size`, or `None` if there isn't one.

        Cached against the size rather than scaled per paint. Covers in this
        library run to 2.2 MB and well past a thousand pixels a side, and this
        widget shares a window with a background that repaints 21 times a
        second -- so a smooth transform on every frame is a cost worth paying
        once. `art_rect` moves with the window, which is why the cache is keyed
        on the size and not just on the image.
        """
        if self._art is None or size.isEmpty():
            return None
        if self._scaled is not None and self._scaled_size == size:
            return self._scaled

        # Expanding, then centre-cropped: a cover is usually square but nothing
        # guarantees it, and letterboxing one inside the plate would put bars
        # where the panel edge is supposed to be.
        scaled = self._art.scaled(
            size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
        )
        crop = QRect(
            (scaled.width() - size.width()) // 2,
            (scaled.height() - size.height()) // 2,
            size.width(),
            size.height(),
        )
        self._scaled = QPixmap.fromImage(scaled.copy(crop))
        self._scaled_size = size
        return self._scaled

    def _paint_title(self, painter: QPainter) -> None:
        available = self._text_width()
        painter.setFont(theme.font(theme.NP_TITLE))
        painter.setPen(theme.TEXT)
        title = QFontMetrics(painter.font()).elidedText(
            self._state.title, Qt.ElideRight, available
        )
        painter.drawText(
            QRect(theme.ITEM_X, self.row_y() - 20, available, 40),
            Qt.AlignLeft | Qt.AlignVCenter,
            title,
        )

    def _paint_info(self, painter: QPainter) -> None:
        available = self._text_width()
        painter.setFont(theme.font(theme.NP_INFO_TEXT))
        painter.setPen(theme.TEXT_DIM)
        metrics = QFontMetrics(painter.font())

        # Fixed slots, not a flowing list: an empty line keeps its space rather
        # than pulling the ones below it up. Most of this library is untagged,
        # so a block that closed up when there was no artist would jump on
        # nearly every track change -- and things staying put is most of what
        # makes an XMB feel like one.
        offsets = (theme.NP_INFO_FIRST, theme.NP_INFO_SECOND, theme.NP_INFO_THIRD)
        # strict=False on purpose: `lines` defaults to empty and is whatever the
        # window last handed over, so a short tuple must draw what it has rather
        # than raise -- inside a paintEvent, at startup.
        for line, offset in zip(self._state.lines, offsets, strict=False):
            if line:
                painter.drawText(
                    QRect(theme.ITEM_X, self.row_y() + offset, available, 18),
                    Qt.AlignLeft | Qt.AlignVCenter,
                    metrics.elidedText(line, Qt.ElideRight, available),
                )
            painter.setPen(theme.TEXT_FAINT)  # later lines sit back a shade

    def _paint_slider(self, painter: QPainter) -> None:
        track = self.track_rect()
        y = self.row_y() + theme.NP_SLIDER
        box = QRect(theme.ITEM_X, y - 16, self._text_width(), 32)

        if track is None:
            # Too narrow to aim at -- show the number alone rather than a
            # slider nobody could hit.
            painter.setFont(theme.font(theme.ITEM_TEXT))
            painter.setPen(theme.accent_text())
            painter.drawText(box, Qt.AlignLeft | Qt.AlignVCenter, self._state.speed_text)
            return

        caption = theme.font(theme.SLIDER_END_LABEL, letter_spacing=True)
        painter.setFont(caption)
        painter.setPen(theme.TEXT_DIM)
        painter.drawText(
            QRect(theme.ITEM_X, box.top(), track.left() - theme.ITEM_X, box.height()),
            Qt.AlignLeft | Qt.AlignVCenter,
            DAYCORE_LABEL,
        )
        # Stops short of the readout's column; running to `box.right()` let the
        # two share pixels and "NIGHTCORE" ran straight into "1.15x".
        night_left = track.right() + theme.SLIDER_LABEL_GAP
        painter.drawText(
            QRect(
                night_left,
                box.top(),
                max(0, box.right() - theme.SLIDER_VALUE_W - night_left),
                box.height(),
            ),
            Qt.AlignLeft | Qt.AlignVCenter,
            NIGHTCORE_LABEL,
        )

        fraction = min(1.0, max(0.0, self._state.fraction))
        handle_x = track.left() + round(fraction * (track.width() - 1))
        groove = QRect(
            track.left(), y - theme.SLIDER_TRACK_H // 2, track.width(), theme.SLIDER_TRACK_H
        )

        # The same colours the transport stylesheet uses, and now literally the
        # same constants: there are two sliders in this app and they should look
        # like one control, including while the accent is travelling.
        painter.setPen(Qt.NoPen)
        painter.setBrush(theme.GROOVE)
        painter.drawRoundedRect(groove, 2, 2)
        painter.setBrush(theme.accent())
        painter.drawRoundedRect(
            QRect(groove.left(), groove.top(), handle_x - groove.left(), groove.height()),
            2,
            2,
        )
        painter.setBrush(theme.TEXT)
        radius = theme.SLIDER_HANDLE // 2
        painter.drawEllipse(QPoint(handle_x, y), radius, radius)
        painter.setBrush(Qt.NoBrush)

        painter.setFont(theme.font(theme.ITEM_TEXT))
        painter.setPen(theme.accent_text())
        painter.drawText(
            box.adjusted(0, 0, -12, 0), Qt.AlignRight | Qt.AlignVCenter, self._state.speed_text
        )

        # Always visible, never a mode to discover.
        painter.setFont(theme.font(theme.NP_HINT_TEXT, letter_spacing=True))
        painter.setPen(theme.faded(theme.TEXT_FAINT, 0.85))
        painter.drawText(
            QRect(theme.ITEM_X, self.row_y() + theme.NP_HINT, self._text_width(), 18),
            Qt.AlignLeft | Qt.AlignVCenter,
            HINT,
        )
