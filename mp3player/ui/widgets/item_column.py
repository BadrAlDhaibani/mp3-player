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

There are exactly two modes in here, `set_stepping` and `set_search`, and both
are only a *look*: an outline that says the selected row is holding the arrow
keys, and a header that says what is being typed. What either means -- which
rows can be stepped into, what a query matches, which rows survive it -- stays
in the window. This widget has never known what any of its rows are for, and
the filtered list arrives here as a plain shorter list of items.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import Property, QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QFontMetrics, QPainter, QPen, QPixmap
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
SEARCH_LABEL = "FIND"


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
        self._stepping = False
        # None is "no search open". "" is a search open with nothing typed yet,
        # which is a real and visible state -- one value carries both facts, the
        # same way `set_stepping` carries one.
        self._search: str | None = None

        self._display = 0.0
        self._appear = 1.0
        self._slide = Tween(self, "display_index", theme.SLIDE_MS)
        self._arrival = Tween(self, "appear", theme.APPEAR_MS)

        # The painted rows, kept as pixels. See `_paint_key` for why this is
        # keyed rather than invalidated, and `paintEvent` for what it costs.
        self._cache = QPixmap()
        self._cache_key: tuple[object, ...] | None = None

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

    # -- stepped-into rows -------------------------------------------------

    @property
    def stepping(self) -> bool:
        return self._stepping

    def set_stepping(self, on: bool) -> None:
        """Whether the selected row is currently holding the arrow keys.

        Purely a *look*. Which rows can be stepped into and what stepping does
        to them are the window's business -- this column has never known what
        any of its rows mean and is not about to start. All it does is outline
        the plate, so the mode is something you can see rather than something
        you have to remember you are in.
        """
        on = bool(on)
        if on != self._stepping:
            self._stepping = on
            self.update()

    # -- the search header -------------------------------------------------

    @property
    def search(self) -> str | None:
        return self._search

    def set_search(self, query: str | None) -> None:
        """The query to show above the list, or `None` for no search at all.

        Same contract as `set_stepping`: a value in, a look out. This widget
        does no filtering -- the window hands it a shorter list of items and
        the string that produced it, and would be none the wiser if the two
        had nothing to do with each other.
        """
        if query != self._search:
            self._search = query
            self.update()

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
        """Blit the cached rows. See `_paint_key` for when they are redrawn.

        The column is a full-size sibling of the wave, which is not, and the
        wave dirties the whole stage about 21 times a second -- so this was
        redrawing an unchanged track list at that rate for as long as the app
        was open. Measured against the real 196-track library: **4.56 ms a
        frame at 980x640 and 5.82 ms at 1920x1080**, against 0.07 and 0.31 for
        the blit that replaced it.

        That is not only a CPU figure. The audio callback is Python and shares
        the GIL with everything in here, and it is the one with a 10.7 ms
        deadline (CLAUDE.md, conventions) -- so the milliseconds come back to
        the audio thread as headroom.
        """
        painter = QPainter(self)
        painter.drawPixmap(theme.COLUMN_INK_LEFT, 0, self._content())

    # -- the cache ---------------------------------------------------------

    def _paint_key(self) -> tuple[object, ...]:
        """Everything the picture below depends on.

        **Keyed on its inputs rather than invalidated by whoever moved one**,
        which is this project's standing rule for a derived value (decisions
        log: *a derived cache is keyed on its inputs*; conventions: *a cache
        that has to be refreshed is a cache keyed on the wrong thing*). It
        matters more here than usual because two of the inputs are `theme`
        module state that this widget is never told about: the palette and the
        accent both move without anything calling a setter on the column, and a
        stale colour is a colour rather than an error.

        The two animated values are both in here, so an arrival and a slide each
        miss on every frame and redraw. That is correct rather than a
        concession: the rows really are moving. It was worth checking, though --
        the arrival is `setOpacity` plus a translate, so applying it to the blit
        instead looked like a way to get it free. **It is not the same picture.**
        Per-element opacity composites each ring, plate and label at `_appear`
        against what is under it; fading the finished layer composites them at
        full and scales the result, and the selection glow is six translucent
        rings stacked on a plate. Measured, they differ over ~2.5% of the inked
        bytes. Both fades are defensible and this one is the one that shipped --
        and the cost of keeping it is a redraw for the 160 ms after a category
        step, which is not what this cache was built for.
        """
        return (
            self._items,  # same tuple object, so `==` is a pointer compare a row
            self._index,
            # 0.001 of a row is 0.04 px at ITEM_SPACING -- below what a frame
            # can show, and it keeps a tween's float noise from missing forever.
            round(self._display, 3),
            round(self._appear, 3),
            self._empty_text,
            self._stepping,
            self._search,
            self.width(),
            self.height(),
            self.devicePixelRatio(),
            theme.palette().name,
            theme.accent_fraction(),
        )

    def _content(self) -> QPixmap:
        """The rows as pixels, redrawn only when `_paint_key` has moved.

        Sized to the box the column can actually ink rather than to the widget:
        it draws nothing left of the selection glow and nothing right of
        `RIGHT_MARGIN`, and at 1920x1080 that is 0.31 ms of blit against 0.86.
        """
        key = self._paint_key()
        if key == self._cache_key and not self._cache.isNull():
            return self._cache

        ratio = self.devicePixelRatio()
        left = theme.COLUMN_INK_LEFT
        width = max(1, self.width() - left)
        height = max(1, self.height())

        cache = QPixmap(round(width * ratio), round(height * ratio))
        cache.setDevicePixelRatio(ratio)
        cache.fill(Qt.transparent)

        painter = QPainter(cache)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        # Everything below goes on drawing in the widget's own coordinates, so
        # no metric in `theme` had to learn that this is a smaller canvas.
        painter.translate(-left, 0)
        # Arriving from a crossbar step: the whole column drifts in from the
        # right as it fades up. Nothing below has to know this is happening, and
        # the geometry the mouse is tested against never sees it.
        if self._appear < 1.0:
            painter.setOpacity(self._appear)
            painter.translate((1.0 - self._appear) * theme.APPEAR_OFFSET, 0)
        self._paint_content(painter)
        painter.end()

        self._cache, self._cache_key = cache, key
        return cache

    def _visible_range(self) -> tuple[int, int]:
        """The half-open range of rows that can land on screen.

        The loop used to walk all 196 items to `continue` past the ~185 that are
        off-stage. Cheap (0.29 ms) and pointless: `_paint_y` is linear in the
        index, so the range it puts on screen is arithmetic rather than a search.
        """
        if not self._items:
            return 0, 0
        # A row sits at `row_y + (index - _display) * ITEM_SPACING`, and the old
        # test kept it while that is within one spacing of the widget. Solved
        # for `index`, that is a range rather than a scan.
        span = theme.ITEM_SPACING
        offset = self._display - self.row_y() / span
        first = max(0, math.floor(offset - 1.0))
        last = min(len(self._items), math.ceil(offset + self.height() / span + 1.0) + 1)
        return first, last

    def _paint_content(self, painter: QPainter) -> None:
        if self._search is not None:
            self._paint_search(painter)
            # The list is clipped below the header rather than the header being
            # given something opaque to sit on: no child in this app fills its
            # background, and a clip is the same non-overlap for no pixels. It
            # costs the topmost row, which is the one already half off the top.
            painter.setClipRect(
                QRectF(0, theme.SEARCH_BAND, self.width(), self.height())
            )

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

        base = painter.opacity()
        first, last = self._visible_range()
        for index in range(first, last):
            item = self._items[index]
            y = self._paint_y(index)
            if y < -theme.ITEM_SPACING or y > self.height() + theme.ITEM_SPACING:
                continue  # off-stage; a 200-track folder only paints what shows
            if self._search is not None:
                # Rows fade into the header rather than being chopped at it.
                # The clip alone left a sliver of descenders hanging under the
                # query line, which reads as a paint bug where the same cut at
                # the window's own edge reads as a list running off the top.
                painter.setOpacity(base * self._under_header(y))
            self._paint_item(painter, index, item, y)
        painter.setOpacity(base)

    def _under_header(self, y: float) -> float:
        """How much of a row centred at `y` survives the search header. 0..1.

        1 once the row's box clears `SEARCH_BAND` entirely, 0 once it is wholly
        above it, and linear in between -- so a row sliding up out of the list
        dims out instead of being sliced. Exported as its own function because
        the harness asserts on both ends of it, and an assertion that restated
        the arithmetic would go on passing after the band moved.
        """
        over = theme.SEARCH_BAND + theme.ITEM_SPACING / 2 - y
        if over <= 0:
            return 1.0
        return max(0.0, 1.0 - over / theme.ITEM_SPACING)

    def _paint_search(self, painter: QPainter) -> None:
        """`FIND  tetris▌`, above the list it is narrowing.

        The caption takes the crossbar label's letter-spaced 13px, so the header
        reads as part of the furniture rather than as a row that wandered up
        there; the query itself takes the item size and the accent, because it
        is the thing that changes.
        """
        height = theme.SEARCH_TEXT + 8
        painter.setFont(theme.font(13, letter_spacing=True))
        painter.setPen(theme.TEXT_FAINT)
        painter.drawText(
            QRectF(theme.ITEM_X, theme.SEARCH_TOP, theme.SEARCH_LABEL_W, height),
            Qt.AlignLeft | Qt.AlignVCenter,
            SEARCH_LABEL,
        )

        x = theme.ITEM_X + theme.SEARCH_LABEL_W
        room = max(
            40,
            self.width() - x - theme.RIGHT_MARGIN - theme.SEARCH_CARET_W - 6,
        )
        painter.setFont(theme.font(theme.SEARCH_TEXT))
        metrics = QFontMetrics(painter.font())
        # From the *left*, unlike every other elision in this file. A query is
        # unbounded text you are still typing, and what you just typed is the
        # end of it -- losing the front of a long one is what a text field does
        # and what makes the caret keep meaning something.
        shown = metrics.elidedText(self._search or "", Qt.ElideLeft, room)
        painter.setPen(theme.accent_text())
        painter.drawText(
            QRectF(x, theme.SEARCH_TOP, room, height),
            Qt.AlignLeft | Qt.AlignVCenter,
            shown,
        )
        # Painted, not a glyph. The offscreen harness has no font database, so a
        # block character there is a fallback of some other width -- a rectangle
        # is the same rectangle everywhere, and it is what says the header is
        # taking keys even before anything has been typed into it.
        painter.fillRect(
            QRectF(
                x + metrics.horizontalAdvance(shown) + 3,
                theme.SEARCH_TOP + 3,
                theme.SEARCH_CARET_W,
                height - 6,
            ),
            theme.accent_text(),
        )

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

        if self._stepping:
            # An outline rather than a brighter plate. The glow already says
            # "this row is selected"; what needs saying now is "and the arrow
            # keys land here instead of moving the cursor", which is a different
            # claim and wants a different mark. Inset by one so the stroke sits
            # on the plate rather than straddling its edge into the glow.
            painter.setPen(QPen(theme.faded(theme.accent_text(), settled), 2))
            painter.drawRoundedRect(plate.adjusted(1, 1, -1, -1), 4, 4)

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
