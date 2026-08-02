"""The horizontal half of the cross: category icons on a fixed rule.

The selection does not move. `FOCUS_X` is where the active category lives, and
choosing a different one slides every icon past that point instead of moving a
highlight along a static row.

That geometry was written as an offset from the active index, which is what
made animating it one float: `_display` eases toward `_index`, and everything
painted reads `_display` instead. Nothing about the layout had to change.

There is no separate "active" style either. Each category is drawn once, at a
size and colour mixed by how close it is to the focus point -- so at rest the
selection looks selected, and mid-slide two icons genuinely trade places rather
than one turning off and the other on.

This widget paints and hit-tests. It does not decide anything -- the stage owns
the keyboard and calls `set_index`.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Property, QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

from mp3player.ui import theme
from mp3player.ui.motion import Tween


@dataclass(frozen=True, slots=True)
class Category:
    glyph: str
    label: str


class Crossbar(QWidget):
    """The category row, plus the rule it sits on."""

    index_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # The stage routes clicks; letting this widget eat them would break the
        # item column stacked on top of it.
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._categories: tuple[Category, ...] = ()
        self._index = 0
        self._display = 0.0
        self._slide = Tween(self, "display_index", theme.SLIDE_MS)

    # -- the animated offset -----------------------------------------------
    #
    # A float index. At rest it equals `_index`; between selections it is
    # somewhere in between, and every painted position is derived from it.

    def _get_display(self) -> float:
        return self._display

    def _set_display(self, value: float) -> None:
        self._display = float(value)
        self.update()

    display_index = Property(float, _get_display, _set_display)

    def settle(self) -> None:
        """End the slide now, wherever it had got to."""
        self._slide.finish()

    # -- model -------------------------------------------------------------

    def set_categories(self, categories: list[Category] | tuple[Category, ...]) -> None:
        self._categories = tuple(categories)
        self._index = min(self._index, max(0, len(self._categories) - 1))
        self._slide.stop()
        self._display = float(self._index)
        self.update()

    @property
    def index(self) -> int:
        return self._index

    def set_index(self, index: int) -> None:
        """Select a category, clamped. Emits only on an actual change."""
        if not self._categories:
            return
        index = max(0, min(int(index), len(self._categories) - 1))
        if index == self._index:
            return
        self._index = index
        self._slide.to(float(index))
        self.index_changed.emit(index)

    def step(self, delta: int) -> None:
        self.set_index(self._index + delta)

    # -- geometry ----------------------------------------------------------
    #
    # Two of these, deliberately. `_centre_x` is where a category comes to
    # rest; `_paint_x` is where it is at this instant. Hit-testing uses the
    # resting layout: a click mid-slide should mean the category you aimed at,
    # not whichever one happened to be passing under the pointer.

    def row_y(self) -> int:
        """The crossbar rule, in this widget's coordinates."""
        return int(self.height() * theme.CROSSBAR_Y_RATIO)

    def _centre_x(self, index: int) -> int:
        return theme.FOCUS_X + (index - self._index) * theme.CATEGORY_SPACING

    def _paint_x(self, index: int) -> float:
        return theme.FOCUS_X + (index - self._display) * theme.CATEGORY_SPACING

    def hit(self, pos: QPoint) -> int | None:
        """Which category is under `pos`, if any.

        Stops short of the item column so the two hit regions stay disjoint --
        the active item shares this widget's row, and an overlap would make
        whichever one is tested second unreachable.
        """
        if pos.x() >= theme.ITEM_X - theme.ITEM_MARKER_GAP:
            return None
        if abs(pos.y() - self.row_y()) > 34:
            return None
        for index in range(len(self._categories)):
            if abs(pos.x() - self._centre_x(index)) <= theme.CATEGORY_SPACING // 2:
                return index
        return None

    # -- painting ----------------------------------------------------------

    def paintEvent(self, event) -> None:
        if not self._categories:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        row = self.row_y()

        # The rule stops where the item column starts. Run it the full width and
        # it strikes through whatever sits on the row -- the Now Playing song
        # title most obviously -- and past the selection plate it was only ever
        # a stray segment anyway.
        painter.setPen(theme.LINE)
        painter.drawLine(0, row, theme.ITEM_X - theme.ITEM_MARKER_GAP, row)

        for index, category in enumerate(self._categories):
            self._paint_category(painter, index, category, row)

    def _paint_category(
        self, painter: QPainter, index: int, category: Category, row: int
    ) -> None:
        centre = self._paint_x(index)
        distance = abs(index - self._display)

        # How much of the *active* look this category is wearing right now: 1 on
        # the focus point, 0 a full step away. This is the whole animation --
        # size, colour and the label all ride on it.
        focus = max(0.0, 1.0 - distance)
        # Two categories out is still on screen at 980px wide; let it dim rather
        # than vanish so the bar reads as a bar and not as a lone icon.
        alpha = max(0.0, 1.0 - distance / 3.5)

        box = QRectF(centre - 60, row - 44, 120, 88)

        size = round(theme.lerp(theme.CATEGORY_ICON_SMALL, theme.CATEGORY_ICON, focus))
        painter.setFont(theme.font(size, family=theme.GLYPH_FAMILY))
        painter.setPen(theme.mix(theme.faded(theme.TEXT_FAINT, alpha), theme.TEXT, focus))
        painter.drawText(box, Qt.AlignCenter, category.glyph)

        if focus <= 0.0:
            return  # nothing left of the label to draw

        # The label belongs to the selection, so it fades out with the slide
        # rather than crossing over -- two half-visible captions under two
        # half-sized icons reads as a smear.
        painter.setFont(theme.font(13, letter_spacing=True))
        painter.setPen(theme.faded(theme.TEXT_DIM, focus))
        painter.drawText(
            QRectF(centre - 90, row + theme.CATEGORY_LABEL_GAP, 180, 22),
            Qt.AlignHCenter | Qt.AlignVCenter,
            category.label.upper(),
        )
