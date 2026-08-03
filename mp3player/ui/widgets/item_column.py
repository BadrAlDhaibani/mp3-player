"""The vertical half of the cross: the item list for the active category.

Same rule as the crossbar -- the selection is nailed to the crossbar row and the
*list* moves. That's why this can't be a `QListWidget`: a list view scrolls only
when the selection would leave the viewport, and XMB scrolls on every step.

Items fade out with distance from the selection instead of being clipped, which
is what stops a 200-track folder from looking like a spreadsheet.

The list slides rather than jumping: `_display` eases toward `_index` and the
paint reads that, so an item grows and brightens as it arrives on the row
instead of the highlight teleporting down a rank. The selection plate keeps its
own place on the row throughout -- it is the fixed point everything else moves
past, and dimming it slightly while the list is in flight covers the one instant
where its width has to change.

Music and Settings use this. Now Playing does not -- it's a page rather than a
list, so it has its own widget (`now_playing.py`) instead of a mode in here.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Property, QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QWidget

from mp3player.ui import theme
from mp3player.ui.motion import Tween

VALUE_PAD = 12  # right-hand readout inset, so it clears the plate's corner
# The most of a row a readout may claim. Settings values are short words and
# never came near this; an artist tag has no length at all, and at 720px
# "Boards of Canada featuring Somebody Else Entirely" took the whole row and
# printed straight over its own title. The label always keeps the majority.
VALUE_MAX_SHARE = 0.45
PLAYING_MARKER = "▶"


@dataclass(frozen=True, slots=True)
class Item:
    """One row. `value` is the right-aligned readout on settings-style rows."""

    label: str
    value: str = ""
    marker: bool = False  # this is the track that's loaded


class ItemColumn(QWidget):
    """The item list. Paints and hit-tests; the stage owns the keyboard."""

    index_changed = Signal(int)
    activated = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._items: tuple[Item, ...] = ()
        self._index = 0
        self._empty_text = ""

        self._display = 0.0
        self._appear = 1.0
        self._slide = Tween(self, "display_index", theme.SLIDE_MS)
        self._arrival = Tween(self, "appear", theme.APPEAR_MS)

    # -- the animated offsets ----------------------------------------------

    def _get_display(self) -> float:
        return self._display

    def _set_display(self, value: float) -> None:
        self._display = float(value)
        self.update()

    display_index = Property(float, _get_display, _set_display)

    def _get_appear(self) -> float:
        return self._appear

    def _set_appear(self, value: float) -> None:
        self._appear = float(value)
        self.update()

    appear = Property(float, _get_appear, _set_appear)

    def enter(self) -> None:
        """Fly in. Called when a crossbar step makes this the visible category."""
        self._appear = 0.0
        self._arrival.to(1.0)

    def settle(self) -> None:
        """End both animations now. Nothing hidden should still be moving."""
        self._slide.finish()
        self._arrival.finish()

    # -- model -------------------------------------------------------------

    def set_items(
        self,
        items: list[Item] | tuple[Item, ...],
        *,
        index: int | None = None,
        empty_text: str = "",
    ) -> None:
        """Replace the column's contents.

        `index=None` keeps the current selection where it still exists, so a
        refresh triggered by the 30 Hz poll doesn't yank the cursor back to the
        top while the user is reading the list.
        """
        replaced = tuple(items) != self._items
        self._items = tuple(items)
        self._empty_text = empty_text
        limit = max(0, len(self._items) - 1)
        self._index = min(self._index if index is None else int(index), limit)
        self._index = max(0, self._index)

        if replaced:
            # A different list, so there is nothing to slide *from*: the rows
            # either side of the old position aren't the same rows any more.
            self._slide.stop()
            self._display = float(self._index)
        elif self._display != self._index:
            # Same list, moved cursor -- the caller changed the selection out
            # from under us (the playing track advanced, say). Slide to it.
            self._slide.to(float(self._index))
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
        self._slide.to(float(index))
        self.index_changed.emit(index)

    def step(self, delta: int) -> None:
        self.set_index(self._index + delta)

    def activate(self) -> None:
        if self._items:
            self.activated.emit(self._index)

    # -- geometry ----------------------------------------------------------
    #
    # `_item_y` is where a row comes to rest, `_paint_y` where it is right now.
    # Hit-testing uses the resting layout on purpose: a click during a slide
    # should select the row you were aiming at, not the one passing the pointer.

    def row_y(self) -> int:
        return int(self.height() * theme.CROSSBAR_Y_RATIO)

    def _item_y(self, index: int) -> int:
        return self.row_y() + (index - self._index) * theme.ITEM_SPACING

    def _paint_y(self, index: int) -> float:
        return self.row_y() + (index - self._display) * theme.ITEM_SPACING

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

        # Arriving from a crossbar step: the whole column drifts in from the
        # right as it fades up. Transform rather than per-item offsets, so
        # nothing below has to know this is happening -- and the geometry the
        # mouse is tested against never sees it.
        if self._appear < 1.0:
            painter.setOpacity(self._appear)
            painter.translate((1.0 - self._appear) * theme.APPEAR_OFFSET, 0)

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

        self._paint_selection(painter)

        for index, item in enumerate(self._items):
            y = self._paint_y(index)
            if y < -theme.ITEM_SPACING or y > self.height() + theme.ITEM_SPACING:
                continue  # off-stage; a 200-track folder only paints what shows
            self._paint_item(painter, index, item, y)

    def _paint_selection(self, painter: QPainter) -> None:
        """The plate and its glow -- drawn once, under every item.

        Fixed to the crossbar row because that *is* the selection: the list
        moves past it. Sized to the row it belongs to rather than to the
        column, since a full-width slab behind "Rescan" reads as a banner
        rather than a cursor. Rows with a readout run the full width anyway, so
        their values stay in a column.
        """
        item = self._items[self._index]
        row = self.row_y()

        painter.setFont(theme.font(theme.ITEM_TEXT_ACTIVE))
        metrics = QFontMetrics(painter.font())
        available = self._text_width()
        width = (
            available
            if item.value
            else min(available, max(220, metrics.horizontalAdvance(item.label) + 34))
        )

        # Dimmer while the list is in flight. The plate's width has to change
        # the instant the selection does, and dipping the whole thing is what
        # makes that change land in shadow instead of as a visible snap.
        settled = max(theme.GLOW_FLOOR, 1.0 - 2.0 * abs(self._display - self._index))

        plate = QRectF(
            theme.ITEM_X - 14,
            row - theme.ITEM_SPACING / 2 + 3,
            width + 14,
            theme.ITEM_SPACING - 6,
        )

        # The glow: bands of light stepping outward, each fainter than the last.
        # Stroked, not filled -- a stack of filled rects accumulates alpha over
        # the plate and puts a hard step at every ring edge, which comes out
        # looking like a border. Cheaper than a blur, and it leaves the plate's
        # own edge crisp so the selection doesn't read as out of focus.
        painter.setBrush(Qt.NoBrush)
        for ring in range(theme.GLOW_RINGS - 1, -1, -1):
            spread = (ring + 1) * theme.GLOW_STEP
            fade = (1.0 - ring / theme.GLOW_RINGS) ** theme.GLOW_FALLOFF
            color = theme.faded(theme.accent(), theme.GLOW_ALPHA / 255 * fade * settled)
            # A hair wider than the step, so consecutive rings meet instead of
            # leaving a dark gap between them.
            painter.setPen(QPen(color, theme.GLOW_STEP + 1))
            painter.drawRoundedRect(
                plate.adjusted(-spread, -spread, spread, spread), 4 + spread, 4 + spread
            )

        painter.setPen(Qt.NoPen)
        painter.setBrush(theme.faded(theme.accent_soft(), 0.55 + 0.45 * settled))
        painter.drawRoundedRect(plate, 4, 4)
        painter.setBrush(Qt.NoBrush)

    def _paint_item(self, painter: QPainter, index: int, item: Item, y: float) -> None:
        distance = abs(index - self._display)
        alpha = max(theme.ITEM_FADE_FLOOR, 1.0 - distance / theme.ITEM_FADE_SPAN)
        # How much of the selected look this row is wearing: it grows and
        # brightens on the way to the crossbar row rather than switching on
        # once it gets there.
        focus = max(0.0, 1.0 - distance)

        size = round(theme.lerp(theme.ITEM_TEXT, theme.ITEM_TEXT_ACTIVE, focus))
        painter.setFont(theme.font(size))
        metrics = QFontMetrics(painter.font())

        available = self._text_width()
        # The readout is elided first and to a share of the row, then the label
        # gets what's left. Both halves matter: an unelided value is drawn
        # right-aligned and simply runs left over the label, and a value allowed
        # to claim the whole row leaves the label a 40px stub. Neither shows up
        # in Settings, where every value is one short word.
        value = (
            metrics.elidedText(item.value, Qt.ElideRight, int(available * VALUE_MAX_SHARE))
            if item.value
            else ""
        )
        value_width = metrics.horizontalAdvance(value) + 24 if value else 0
        box = QRectF(
            theme.ITEM_X, y - theme.ITEM_SPACING / 2, available, theme.ITEM_SPACING
        )

        painter.setPen(theme.mix(theme.faded(theme.TEXT_DIM, alpha), theme.TEXT, focus))
        label = metrics.elidedText(
            item.label, Qt.ElideRight, max(40, available - value_width)
        )
        painter.drawText(box, Qt.AlignLeft | Qt.AlignVCenter, label)

        if value:
            painter.setPen(
                theme.mix(theme.faded(theme.TEXT_FAINT, alpha), theme.accent_text(), focus)
            )
            # Inset so the readout doesn't sit flush against the selection
            # plate's rounded edge.
            painter.drawText(
                box.adjusted(0, 0, -VALUE_PAD, 0),
                Qt.AlignRight | Qt.AlignVCenter,
                value,
            )

        if item.marker:
            painter.setFont(theme.font(11, family=theme.GLYPH_FAMILY))
            painter.setPen(theme.faded(theme.accent_text(), max(alpha, 0.55)))
            painter.drawText(
                QRectF(
                    theme.ITEM_X - theme.ITEM_MARKER_GAP,
                    box.top(),
                    theme.ITEM_MARKER_GAP,
                    box.height(),
                ),
                Qt.AlignLeft | Qt.AlignVCenter,
                PLAYING_MARKER,
            )
