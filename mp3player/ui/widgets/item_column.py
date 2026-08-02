"""The vertical half of the cross: the item list for the active category.

Same rule as the crossbar -- the selection is nailed to the crossbar row and the
*list* moves. That's why this can't be a `QListWidget`: a list view scrolls only
when the selection would leave the viewport, and XMB scrolls on every step.

Items fade out with distance from the selection instead of being clipped, which
is what stops a 200-track folder from looking like a spreadsheet.

`Now Playing` adds a header block above item 0 -- art placeholder, title,
subtitle. It scrolls with the column like everything else, so there is no
special case anywhere but `_paint_header`.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

from mp3player.ui import theme

HEADER_TEXT_BLOCK = 52  # title + subtitle under the art placeholder
VALUE_PAD = 12  # right-hand readout inset, so it clears the plate's corner
PLAYING_MARKER = "▶"


@dataclass(frozen=True, slots=True)
class Item:
    """One row. `value` is the right-aligned readout on settings-style rows."""

    label: str
    value: str = ""
    marker: bool = False  # this is the track that's loaded


@dataclass(frozen=True, slots=True)
class Header:
    title: str
    subtitle: str = ""


class ItemColumn(QWidget):
    """The item list. Paints and hit-tests; the stage owns the keyboard."""

    index_changed = Signal(int)
    activated = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._items: tuple[Item, ...] = ()
        self._header: Header | None = None
        self._index = 0
        self._empty_text = ""

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

    # -- geometry ----------------------------------------------------------

    def row_y(self) -> int:
        return int(self.height() * theme.CROSSBAR_Y_RATIO)

    def _item_y(self, index: int) -> int:
        return self.row_y() + (index - self._index) * theme.ITEM_SPACING

    def _text_width(self) -> int:
        return max(80, self.width() - theme.ITEM_X - theme.RIGHT_MARGIN)

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
            self._paint_header(painter, self._header)

        for index, item in enumerate(self._items):
            y = self._item_y(index)
            if y < -theme.ITEM_SPACING or y > self.height() + theme.ITEM_SPACING:
                continue  # off-stage; a 200-track folder only paints what shows
            self._paint_item(painter, index, item, y)

    def _paint_item(self, painter: QPainter, index: int, item: Item, y: int) -> None:
        active = index == self._index
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

    def _paint_header(self, painter: QPainter, header: Header) -> None:
        bottom = self._item_y(0) - theme.ITEM_SPACING // 2 - theme.HEADER_GAP
        art_top = bottom - HEADER_TEXT_BLOCK - theme.HEADER_ART
        if art_top > self.height():
            return

        art = QRect(theme.ITEM_X, art_top, theme.HEADER_ART, theme.HEADER_ART)
        painter.setPen(theme.PANEL_EDGE)
        painter.setBrush(theme.PANEL)
        painter.drawRoundedRect(art, 6, 6)
        painter.setBrush(Qt.NoBrush)

        # No ID3 art in v1 (see the scope list) -- a note glyph stands in, and
        # the block is already the right shape for a cover when tags land.
        painter.setFont(theme.font(52, family=theme.GLYPH_FAMILY))
        painter.setPen(theme.faded(theme.TEXT_FAINT, 0.7))
        painter.drawText(art, Qt.AlignCenter, "♪")

        available = self._text_width()
        painter.setFont(theme.font(21))
        painter.setPen(theme.TEXT)
        title = QFontMetrics(painter.font()).elidedText(
            header.title, Qt.ElideRight, available
        )
        painter.drawText(
            QRect(theme.ITEM_X, art.bottom() + 8, available, 26),
            Qt.AlignLeft | Qt.AlignVCenter,
            title,
        )

        if header.subtitle:
            painter.setFont(theme.font(13))
            painter.setPen(theme.TEXT_FAINT)
            painter.drawText(
                QRect(theme.ITEM_X, art.bottom() + 34, available, 18),
                Qt.AlignLeft | Qt.AlignVCenter,
                header.subtitle,
            )
