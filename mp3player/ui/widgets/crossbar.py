"""The horizontal half of the cross: category icons on a fixed rule.

The selection does not move. `FOCUS_X` is where the active category lives, and
choosing a different one slides every icon past that point instead of moving a
highlight along a static row. Batch 5 animates the slide; here it snaps, but the
geometry is already expressed as an offset from the active index so animating it
later is one interpolated float.

This widget paints and hit-tests. It does not decide anything -- the stage owns
the keyboard and calls `set_index`.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

from mp3player.ui import theme


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

    # -- model -------------------------------------------------------------

    def set_categories(self, categories: list[Category] | tuple[Category, ...]) -> None:
        self._categories = tuple(categories)
        self._index = min(self._index, max(0, len(self._categories) - 1))
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
        self.update()
        self.index_changed.emit(index)

    def step(self, delta: int) -> None:
        self.set_index(self._index + delta)

    # -- geometry ----------------------------------------------------------

    def row_y(self) -> int:
        """The crossbar rule, in this widget's coordinates."""
        return int(self.height() * theme.CROSSBAR_Y_RATIO)

    def _centre_x(self, index: int) -> int:
        return theme.FOCUS_X + (index - self._index) * theme.CATEGORY_SPACING

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

        painter.setPen(theme.LINE)
        painter.drawLine(0, row, self.width(), row)

        for index, category in enumerate(self._categories):
            self._paint_category(painter, index, category, row)

    def _paint_category(
        self, painter: QPainter, index: int, category: Category, row: int
    ) -> None:
        centre = self._centre_x(index)
        active = index == self._index
        distance = abs(index - self._index)
        # Two categories out is still on screen at 980px wide; let it dim rather
        # than vanish so the bar reads as a bar and not as a lone icon.
        alpha = max(0.0, 1.0 - distance / 3.5)

        box = QRect(centre - 60, row - 44, 120, 88)

        if active:
            painter.setFont(theme.font(theme.CATEGORY_ICON, family=theme.GLYPH_FAMILY))
            painter.setPen(theme.TEXT)
            painter.drawText(box, Qt.AlignCenter, category.glyph)

            painter.setFont(theme.font(13, letter_spacing=True))
            painter.setPen(theme.TEXT_DIM)
            painter.drawText(
                QRect(centre - 90, row + theme.CATEGORY_LABEL_GAP, 180, 22),
                Qt.AlignHCenter | Qt.AlignVCenter,
                category.label.upper(),
            )
        else:
            painter.setFont(
                theme.font(theme.CATEGORY_ICON_SMALL, family=theme.GLYPH_FAMILY)
            )
            painter.setPen(theme.faded(theme.TEXT_FAINT, alpha))
            painter.drawText(box, Qt.AlignCenter, category.glyph)
