"""The vertical half of the cross: the item list for the active category.

Same rule as the crossbar -- the selection is nailed to the crossbar row and the
*list* moves. That's why this can't be a `QListWidget`: a list view scrolls only
when the selection would leave the viewport, and XMB scrolls on every step.

Items fade out with distance from the selection instead of being clipped, which
is what stops a 200-track folder from looking like a spreadsheet.

Two rows are not plain text. A row with a `fraction` paints a slider -- that's
the Daycore/Nightcore control, and it's painted here rather than being a real
QSlider for the same reason the column isn't a QListWidget: it has to sit on the
crossbar row and scroll with everything else. `Now Playing` also carries a
`Header`, whose title and subtitle sit above item 0 and whose art placeholder
goes out in the gutter left of the column, where the window height can't
squeeze it.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

from mp3player.ui import theme

HEADER_TEXT_BLOCK = 52  # title + subtitle above the first item
VALUE_PAD = 12  # right-hand readout inset, so it clears the plate's corner
PLAYING_MARKER = "▶"

DAYCORE_LABEL = "DAYCORE"
NIGHTCORE_LABEL = "NIGHTCORE"
EDIT_HINT = "←  →   adjust      ·      Enter   done"


@dataclass(frozen=True, slots=True)
class Item:
    """One row. `value` is the right-aligned readout on settings-style rows."""

    label: str
    value: str = ""
    marker: bool = False  # this is the track that's loaded
    fraction: float | None = None  # 0..1 -> paint a slider instead of a label


@dataclass(frozen=True, slots=True)
class Header:
    title: str
    subtitle: str = ""


class ItemColumn(QWidget):
    """The item list. Paints and hit-tests; the stage owns the keyboard."""

    index_changed = Signal(int)
    activated = Signal(int)
    slider_moved = Signal(float)  # 0..1, live -- emitted by the stage's drag

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._items: tuple[Item, ...] = ()
        self._header: Header | None = None
        self._index = 0
        self._empty_text = ""
        self._editing = False

    # -- model -------------------------------------------------------------

    def set_items(
        self,
        items: list[Item] | tuple[Item, ...],
        *,
        header: Header | None = None,
        index: int | None = None,
        empty_text: str = "",
    ) -> None:
        """Replace the column's contents.

        `index=None` keeps the current selection where it still exists, so a
        refresh triggered by the 30 Hz poll doesn't yank the cursor back to the
        top while the user is reading the list.
        """
        self._items = tuple(items)
        self._header = header
        self._empty_text = empty_text
        limit = max(0, len(self._items) - 1)
        self._index = min(self._index if index is None else int(index), limit)
        self._index = max(0, self._index)
        # Whatever row was stepped into may not exist any more, or may not be a
        # slider. Never leave the column holding the arrow keys for a row that
        # has gone.
        self._editing = self._editing and self.is_slider(self._index)
        self.update()

    @property
    def index(self) -> int:
        return self._index

    @property
    def count(self) -> int:
        return len(self._items)

    def set_index(self, index: int) -> None:
        if not self._items:
            return
        index = max(0, min(int(index), len(self._items) - 1))
        if index == self._index:
            return
        self._index = index
        self.update()
        self.index_changed.emit(index)

    def step(self, delta: int) -> None:
        self.set_index(self._index + delta)

    def activate(self) -> None:
        if self._items:
            self.activated.emit(self._index)

    @property
    def editing(self) -> bool:
        """True while the selected slider row has been stepped into."""
        return self._editing

    def set_editing(self, editing: bool) -> None:
        editing = bool(editing) and self.is_slider(self._index)
        if editing != self._editing:
            self._editing = editing
            self.update()

    def is_slider(self, index: int) -> bool:
        return 0 <= index < len(self._items) and self._items[index].fraction is not None

    # -- geometry ----------------------------------------------------------

    def row_y(self) -> int:
        return int(self.height() * theme.CROSSBAR_Y_RATIO)

    def _item_y(self, index: int) -> int:
        return self.row_y() + (index - self._index) * theme.ITEM_SPACING

    def _text_width(self) -> int:
        return max(80, self.width() - theme.ITEM_X - theme.RIGHT_MARGIN)

    def track_rect(self, index: int) -> QRect | None:
        """The draggable part of a slider row, or None if it isn't one.

        The stage hit-tests against this before its ordinary item hit-test, so
        a press on the track starts a drag rather than re-opening the row.
        """
        if not self.is_slider(index):
            return None

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

        y = self._item_y(index)
        return QRect(left, y - theme.SLIDER_HANDLE // 2, right - left, theme.SLIDER_HANDLE)

    def fraction_at(self, index: int, x: int) -> float:
        """Where `x` falls along a slider row's track, clamped to 0..1.

        Spans `width - 1` because both ends are *pixels*, not boundaries: the
        rightmost pixel of the track has to mean 1.0, or clicking the visible
        end of the bar lands at 0.999 and nightcore is unreachable by mouse.
        `_paint_slider_row` places the handle on the same span.
        """
        track = self.track_rect(index)
        if track is None or track.width() <= 1:
            return 0.0
        return min(1.0, max(0.0, (x - track.left()) / (track.width() - 1)))

    def hit(self, pos: QPoint) -> int | None:
        if not self._items or pos.x() < theme.ITEM_X - theme.ITEM_MARKER_GAP:
            return None
        offset = round((pos.y() - self.row_y()) / theme.ITEM_SPACING)
        index = self._index + int(offset)
        if not 0 <= index < len(self._items):
            return None
        if abs(pos.y() - self._item_y(index)) > theme.ITEM_SPACING // 2:
            return None
        return index

    # -- painting ----------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        if not self._items:
            if self._empty_text:
                painter.setFont(theme.font(theme.ITEM_TEXT))
                painter.setPen(theme.TEXT_FAINT)
                painter.drawText(
                    QRect(theme.ITEM_X, self.row_y() - 16, self._text_width(), 32),
                    Qt.AlignLeft | Qt.AlignVCenter,
                    self._empty_text,
                )
            return

        if self._header is not None:
            self._paint_art(painter)
            self._paint_header(painter, self._header)

        for index, item in enumerate(self._items):
            y = self._item_y(index)
            if y < -theme.ITEM_SPACING or y > self.height() + theme.ITEM_SPACING:
                continue  # off-stage; a 200-track folder only paints what shows
            self._paint_item(painter, index, item, y)

    def _paint_item(self, painter: QPainter, index: int, item: Item, y: int) -> None:
        active = index == self._index

        if item.fraction is not None:
            self._paint_slider_row(painter, index, item, y, active)
            return

        distance = abs(index - self._index)
        alpha = max(theme.ITEM_FADE_FLOOR, 1.0 - distance / theme.ITEM_FADE_SPAN)

        size = theme.ITEM_TEXT_ACTIVE if active else theme.ITEM_TEXT
        painter.setFont(theme.font(size))
        metrics = QFontMetrics(painter.font())

        available = self._text_width()
        value_width = metrics.horizontalAdvance(item.value) + 24 if item.value else 0
        box = QRect(theme.ITEM_X, y - theme.ITEM_SPACING // 2, available, theme.ITEM_SPACING)

        if active:
            # A plate sized to its contents, not to the column: a full-width
            # slab behind "Play" reads as a banner rather than a cursor. Batch 5
            # turns this into a real glow; for now it's what says where you are.
            # Rows with a readout run the full width so the values stay in a
            # column; rows without one shrink to fit their label.
            plate = (
                available
                if item.value
                else min(available, max(220, metrics.horizontalAdvance(item.label) + 34))
            )
            painter.setPen(Qt.NoPen)
            painter.setBrush(theme.ACCENT_SOFT)
            painter.drawRoundedRect(
                QRect(box.left() - 14, box.top() + 3, plate + 14, box.height() - 6), 4, 4
            )
            painter.setBrush(Qt.NoBrush)

        painter.setPen(theme.TEXT if active else theme.faded(theme.TEXT_DIM, alpha))
        label = metrics.elidedText(
            item.label, Qt.ElideRight, max(40, available - value_width)
        )
        painter.drawText(box, Qt.AlignLeft | Qt.AlignVCenter, label)

        if item.value:
            painter.setPen(
                theme.ACCENT if active else theme.faded(theme.TEXT_FAINT, alpha)
            )
            # Inset so the readout doesn't sit flush against the selection
            # plate's rounded edge.
            painter.drawText(
                box.adjusted(0, 0, -VALUE_PAD, 0),
                Qt.AlignRight | Qt.AlignVCenter,
                item.value,
            )

    def _paint_slider_row(
        self, painter: QPainter, index: int, item: Item, y: int, active: bool
    ) -> None:
        """DAYCORE | track | NIGHTCORE | readout.

        The colours are lifted from the transport stylesheet on purpose -- there
        are two sliders in this app and they should look like one control.
        """
        available = self._text_width()
        box = QRect(
            theme.ITEM_X, y - theme.ITEM_SPACING // 2, available, theme.ITEM_SPACING
        )
        track = self.track_rect(index)

        if active:
            # Stepped into, the plate gets an outline: the row is no longer just
            # selected, it's taking the arrow keys, and that has to be visible.
            painter.setPen(theme.ACCENT if self._editing else Qt.NoPen)
            painter.setBrush(theme.ACCENT_SOFT)
            painter.drawRoundedRect(
                QRect(box.left() - 14, box.top() + 3, available + 14, box.height() - 6),
                4,
                4,
            )
            painter.setBrush(Qt.NoBrush)

        if track is None:
            # Too narrow for a track -- fall back to the readout alone rather
            # than painting a slider nobody could aim at.
            painter.setFont(theme.font(theme.ITEM_TEXT))
            painter.setPen(theme.TEXT if active else theme.TEXT_DIM)
            painter.drawText(box, Qt.AlignLeft | Qt.AlignVCenter, item.label)
            painter.setPen(theme.ACCENT)
            painter.drawText(
                box.adjusted(0, 0, -VALUE_PAD, 0),
                Qt.AlignRight | Qt.AlignVCenter,
                item.value,
            )
            return

        caption = theme.font(theme.SLIDER_END_LABEL, letter_spacing=True)
        painter.setFont(caption)
        painter.setPen(theme.TEXT_DIM if active else theme.TEXT_FAINT)
        painter.drawText(
            QRect(theme.ITEM_X, box.top(), track.left() - theme.ITEM_X, box.height()),
            Qt.AlignLeft | Qt.AlignVCenter,
            DAYCORE_LABEL,
        )
        # Stops short of the readout's column. Running to `box.right()` let the
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

        fraction = min(1.0, max(0.0, item.fraction or 0.0))
        handle_x = track.left() + int(round(fraction * (track.width() - 1)))
        groove = QRect(
            track.left(),
            y - theme.SLIDER_TRACK_H // 2,
            track.width(),
            theme.SLIDER_TRACK_H,
        )

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 34))
        painter.drawRoundedRect(groove, 2, 2)
        painter.setBrush(theme.ACCENT)
        painter.drawRoundedRect(
            QRect(groove.left(), groove.top(), handle_x - groove.left(), groove.height()),
            2,
            2,
        )

        painter.setBrush(theme.TEXT if active else theme.TEXT_DIM)
        radius = theme.SLIDER_HANDLE // 2
        painter.drawEllipse(QPoint(handle_x, y), radius, radius)
        painter.setBrush(Qt.NoBrush)

        painter.setFont(theme.font(theme.ITEM_TEXT))
        painter.setPen(theme.ACCENT if active else theme.TEXT_FAINT)
        painter.drawText(
            box.adjusted(0, 0, -VALUE_PAD, 0),
            Qt.AlignRight | Qt.AlignVCenter,
            item.value,
        )

        if active and self._editing:
            painter.setFont(theme.font(11, letter_spacing=True))
            painter.setPen(theme.faded(theme.TEXT_FAINT, 0.9))
            painter.drawText(
                QRect(theme.ITEM_X, box.bottom() + 2, available, 18),
                Qt.AlignLeft | Qt.AlignVCenter,
                EDIT_HINT,
            )

        if item.marker:
            painter.setFont(theme.font(11, family=theme.GLYPH_FAMILY))
            painter.setPen(theme.faded(theme.ACCENT, max(alpha, 0.55)))
            painter.drawText(
                QRect(
                    theme.ITEM_X - theme.ITEM_MARKER_GAP,
                    box.top(),
                    theme.ITEM_MARKER_GAP,
                    box.height(),
                ),
                Qt.AlignLeft | Qt.AlignVCenter,
                PLAYING_MARKER,
            )

    def _paint_art(self, painter: QPainter) -> None:
        """The art placeholder, in the gutter left of the column.

        Sized by the gutter rather than by whatever vertical room the items left
        over, which is what makes it survive the 720x480 minimum. It's a square,
        so the narrower of the two dimensions wins.
        """
        row = self.row_y()
        top = row + theme.CATEGORY_LABEL_GAP + theme.ART_TOP_GAP
        size = min(
            theme.ART_MAX,
            theme.ITEM_X - 2 * theme.RIGHT_MARGIN,
            self.height() - theme.ART_BOTTOM_PAD - top,
        )
        if size < theme.ART_MIN:
            return

        art = QRect(theme.ITEM_X // 2 - size // 2, top, size, size)
        painter.setPen(theme.PANEL_EDGE)
        painter.setBrush(theme.PANEL)
        painter.drawRoundedRect(art, 6, 6)
        painter.setBrush(Qt.NoBrush)

        # No ID3 art in v1 (see the scope list) -- a note glyph stands in, and
        # the block is the right shape for a cover when tags land.
        painter.setFont(theme.font(max(24, size * 2 // 5), family=theme.GLYPH_FAMILY))
        painter.setPen(theme.faded(theme.TEXT_FAINT, 0.7))
        painter.drawText(art, Qt.AlignCenter, "♪")

    def _paint_header(self, painter: QPainter, header: Header) -> None:
        """Title and subtitle, sitting above item 0 and scrolling with it."""
        bottom = self._item_y(0) - theme.ITEM_SPACING // 2 - theme.HEADER_GAP
        if bottom <= 0:
            return  # scrolled off the top entirely

        text_top = bottom - HEADER_TEXT_BLOCK
        available = self._text_width()
        painter.setFont(theme.font(21))
        painter.setPen(theme.TEXT)
        title = QFontMetrics(painter.font()).elidedText(
            header.title, Qt.ElideRight, available
        )
        painter.drawText(
            QRect(theme.ITEM_X, text_top + 4, available, 26),
            Qt.AlignLeft | Qt.AlignVCenter,
            title,
        )

        if header.subtitle:
            painter.setFont(theme.font(13))
            painter.setPen(theme.TEXT_FAINT)
            painter.drawText(
                QRect(theme.ITEM_X, text_top + 30, available, 18),
                Qt.AlignLeft | Qt.AlignVCenter,
                header.subtitle,
            )
