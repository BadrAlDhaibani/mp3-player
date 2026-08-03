"""Frameless window plumbing: the title strip, dragging, and resize grips.

A console skin has to go to the edges of the window, which means no native
title bar -- and once it's gone we owe the user back everything it did. This
file is that debt: move, resize from any edge, minimise, maximise, close, and
F11 for the full-screen version of the same look.

Moving and resizing go through `startSystemMove` / `startSystemResize` rather
than a mouse-delta loop. The compositor then owns the drag, so we get snapping,
Aero Snap edges, and no lag -- and we get it in about ten lines.

The window is a plain `QWidget`, not a `QMainWindow`: the only thing we wanted
from `QMainWindow` was a central widget, and its layout ignores the contents
margins that give the resize grips somewhere to live.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mp3player.ui import theme


def _cursor_for(edges: Qt.Edges) -> Qt.CursorShape:
    """The resize cursor for a set of edges. Corners get the right diagonal.

    Derived rather than table-driven: `Qt.Edges` is a flag combination, and
    flag objects are unreliable dictionary keys across PySide versions.
    """
    left = bool(edges & Qt.LeftEdge)
    top = bool(edges & Qt.TopEdge)
    horizontal = left or bool(edges & Qt.RightEdge)
    vertical = top or bool(edges & Qt.BottomEdge)

    if horizontal and vertical:
        # Left+Top and Right+Bottom share the ↖↘ diagonal; the others get ↗↙.
        return Qt.SizeFDiagCursor if left == top else Qt.SizeBDiagCursor
    if horizontal:
        return Qt.SizeHorCursor
    if vertical:
        return Qt.SizeVerCursor
    return Qt.ArrowCursor


class TitleBar(QWidget):
    """The strip along the top: app name on the left, three buttons right.

    Dragging anywhere that isn't a button moves the window; double-clicking
    toggles maximise, same as a native title bar.
    """

    def __init__(self, window: ChromeWindow, title: str) -> None:
        super().__init__(window)
        self._window = window
        self.setFixedHeight(theme.CHROME_HEIGHT)
        self.setCursor(Qt.ArrowCursor)  # never inherit the window's resize cursor

        label = QLabel(title, self)
        label.setFont(theme.font(12, letter_spacing=True))
        label.setStyleSheet(f"color: {theme.rgba(theme.TEXT_FAINT)};")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(label)
        layout.addStretch(1)

        self.minimise = _ChromeButton("─", self)
        self.maximise = _ChromeButton("□", self)
        self.close_button = _ChromeButton("✕", self, danger=True)
        for button in (self.minimise, self.maximise, self.close_button):
            layout.addWidget(button)

        self.minimise.clicked.connect(window.showMinimized)
        self.maximise.clicked.connect(window.toggle_maximised)
        self.close_button.clicked.connect(window.close)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and not self._window.isFullScreen():
            handle = self._window.windowHandle()
            if handle is not None:
                handle.startSystemMove()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._window.toggle_maximised()


class _ChromeButton(QPushButton):
    def __init__(self, glyph: str, parent: QWidget, *, danger: bool = False) -> None:
        super().__init__(glyph, parent)
        self.setFixedSize(46, theme.CHROME_HEIGHT)
        self.setCursor(Qt.ArrowCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFont(theme.font(12, family=theme.GLYPH_FAMILY))
        hover = "rgba(220,60,60,220)" if danger else theme.rgba(theme.PANEL)
        self.setStyleSheet(
            f"QPushButton {{ color: {theme.rgba(theme.TEXT_FAINT)};"
            f" background: transparent; border: none; }}"
            f"QPushButton:hover {{ color: {theme.rgba(theme.TEXT)};"
            f" background: {hover}; }}"
        )


class ChromeWindow(QWidget):
    """Frameless top-level window. Subclasses fill it via `set_body`.

    Paints the background gradient for the whole app -- every child widget
    leaves its own background unfilled, so this one `paintEvent` is what shows
    through all of them.
    """

    def __init__(self, title: str) -> None:
        super().__init__()
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.setWindowTitle(title)
        self.setMinimumSize(*theme.WINDOW_MINIMUM)
        self.resize(*theme.WINDOW_DEFAULT)
        self.setMouseTracking(True)

        self.title_bar = TitleBar(self, title)

        self._layout = QVBoxLayout(self)
        self._layout.setSpacing(0)
        self._layout.addWidget(self.title_bar)
        self._apply_margins()

        self._body: QWidget | None = None

    # -- composition -------------------------------------------------------

    def set_body(self, body: QWidget) -> None:
        """Install the widget that fills everything below the title strip."""
        if self._body is not None:
            self._layout.removeWidget(self._body)
            self._body.deleteLater()
        self._body = body
        body.setParent(self)
        # An explicit cursor, so the body never *inherits* the resize cursor
        # this window sets on itself. See `mouseMoveEvent`.
        body.setCursor(Qt.ArrowCursor)
        self._layout.addWidget(body, 1)

    # -- window state ------------------------------------------------------

    def toggle_maximised(self) -> None:
        if self.isFullScreen() or self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        self._apply_margins()

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
        self._apply_margins()

    def _apply_margins(self) -> None:
        """Resize grips only exist when there's something to resize."""
        margin = 0 if self._gripless() else theme.RESIZE_MARGIN
        self._layout.setContentsMargins(margin, margin, margin, margin)

    def _gripless(self) -> bool:
        return self.isFullScreen() or self.isMaximized()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == event.Type.WindowStateChange:
            self._apply_margins()

    # -- painting ----------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), theme.background_brush(self.rect()))

    # -- resize grips ------------------------------------------------------
    #
    # Only the margin strip around the body belongs to this widget, so these
    # handlers only ever fire out there. No hit-testing against children needed.
    #
    # Cursor discipline matters more than it looks. A cursor set here is
    # inherited by any child that hasn't set its own, and the window stops
    # receiving move events the moment the pointer crosses into the body -- so a
    # cursor set on the way *in* to the margin has no event to reset it on the
    # way out, and the arrow stays a resize arrow. Two things prevent that: the
    # body sets its own cursor (see `set_body`), and this widget unsets rather
    # than overwrites, including right after a drag the compositor took over.

    def mouseMoveEvent(self, event) -> None:
        self._show_cursor_for(self._edges_at(event.position().toPoint()))
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        edges = self._edges_at(event.position().toPoint())
        if event.button() == Qt.LeftButton and edges:
            handle = self.windowHandle()
            if handle is not None:
                handle.startSystemResize(edges)
                # The drag ends wherever the user let go -- usually over the
                # body, where no move event of ours will ever arrive.
                self.unsetCursor()
                return
        super().mousePressEvent(event)

    def leaveEvent(self, event) -> None:
        self.unsetCursor()
        super().leaveEvent(event)

    def _show_cursor_for(self, edges: Qt.Edges) -> None:
        if edges:
            self.setCursor(_cursor_for(edges))
        else:
            self.unsetCursor()

    def _edges_at(self, pos: QPoint) -> Qt.Edges:
        if self._gripless():
            return Qt.Edges()
        margin = theme.RESIZE_MARGIN
        edges = Qt.Edges()
        if pos.x() < margin:
            edges |= Qt.LeftEdge
        elif pos.x() >= self.width() - margin:
            edges |= Qt.RightEdge
        if pos.y() < margin:
            edges |= Qt.TopEdge
        elif pos.y() >= self.height() - margin:
            edges |= Qt.BottomEdge
        return edges
