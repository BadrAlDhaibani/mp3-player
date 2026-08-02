"""Colors, fonts, metrics -- the single source of truth for how this looks.

Nothing here imports another `ui` module, so every widget can pull from it
without a cycle. If a number appears in two widgets, it belongs in this file.

The palette is PS3 XMB read from memory rather than sampled: a near-black navy
that lifts toward the horizon, white text at three brightnesses, and one icy
accent used sparingly enough that it still reads as an accent. Batch 5 paints
the wave *over* `background_brush`; the gradient is what shows through it.
"""

from __future__ import annotations

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QFont, QLinearGradient

# -- palette ---------------------------------------------------------------

BG_TOP = QColor(12, 30, 62)
BG_MID = QColor(6, 16, 38)
BG_BOTTOM = QColor(2, 6, 15)

TEXT = QColor(255, 255, 255)
TEXT_DIM = QColor(178, 196, 224)
TEXT_FAINT = QColor(120, 140, 172)

ACCENT = QColor(126, 200, 255)
ACCENT_SOFT = QColor(126, 200, 255, 70)

LINE = QColor(255, 255, 255, 28)  # the crossbar rule
PANEL = QColor(255, 255, 255, 18)  # art placeholder, chrome hover
PANEL_EDGE = QColor(255, 255, 255, 46)

WARN = QColor(255, 178, 120)


def background_brush(rect: QRect) -> QLinearGradient:
    """The window gradient. Top-lit, so the crossbar sits in the bright band."""
    gradient = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.bottom())
    gradient.setColorAt(0.00, BG_TOP)
    gradient.setColorAt(0.45, BG_MID)
    gradient.setColorAt(1.00, BG_BOTTOM)
    return gradient


def faded(color: QColor, alpha: float) -> QColor:
    """`color` at `alpha` (0..1) of its own opacity. Used for the item falloff."""
    out = QColor(color)
    out.setAlpha(max(0, min(255, int(color.alpha() * alpha))))
    return out


# -- fonts -----------------------------------------------------------------

UI_FAMILY = "Segoe UI"
GLYPH_FAMILY = "Segoe UI Symbol"  # the ▶ ⏮ ♪ ⚙ set, present on Windows 10+

_fonts: dict[tuple[str, int, int, bool], QFont] = {}


def font(
    pixels: int,
    *,
    family: str = UI_FAMILY,
    weight: int = QFont.Normal,
    letter_spacing: bool = False,
) -> QFont:
    """A cached font. Pixel-sized so metrics don't move with the DPI setting.

    Cached because `paintEvent` asks for the same handful of fonts on every
    frame and constructing a QFont per item is measurable once the wave lands.
    """
    key = (family, pixels, int(weight), letter_spacing)
    cached = _fonts.get(key)
    if cached is None:
        cached = QFont(family)
        cached.setPixelSize(pixels)
        cached.setWeight(weight)
        if letter_spacing:
            cached.setLetterSpacing(QFont.PercentageSpacing, 112)
        _fonts[key] = cached
    return cached


# -- metrics ---------------------------------------------------------------
#
# The XMB geometry, in one place. The rule that makes it feel right: the
# *selection* never moves. The active category sits at FOCUS_X forever and the
# other categories slide past it; the active item sits on the crossbar row
# forever and the list scrolls under it.

# Of the stage height, measured to the icon centres. Every pixel above the row
# is what the Now Playing header has to live in, so this is really a trade
# between header room and how many items fit below.
CROSSBAR_Y_RATIO = 0.44

FOCUS_X = 88  # where the active category icon centres
CATEGORY_SPACING = 88
CATEGORY_ICON = 44  # glyph pixel size, active
CATEGORY_ICON_SMALL = 30  # glyph pixel size, everything else
CATEGORY_LABEL_GAP = 32  # icon centre -> label baseline area

# The bar and the column must never share horizontal space: the column's active
# row sits *on* the crossbar row, so any overlap makes one of them unclickable.
# With three categories the furthest-right icon is FOCUS_X + 2 * SPACING = 264,
# which clears ITEM_X with room for the marker gutter. Adding a fourth category
# means moving ITEM_X right, not just appending to the list.
ITEM_X = 312  # left edge of the item column
ITEM_SPACING = 44
ITEM_TEXT = 17
ITEM_TEXT_ACTIVE = 20
ITEM_MARKER_GAP = 22  # room for the ▶ that marks the playing track
ITEM_FADE_SPAN = 9.0  # distance at which an item would fade out completely
ITEM_FADE_FLOOR = 0.38  # ...except it never gets dimmer than this, so a short
# action list doesn't read as half-disabled. Long track lists still fall away.

# The art placeholder shrinks to whatever room is left above the crossbar row,
# and is dropped entirely below the minimum -- a clipped square looks like a
# bug, and at 720x480 there is genuinely no room for one.
HEADER_ART = 132  # the "now playing" art placeholder, square, at full size
HEADER_ART_MIN = 64  # below this it isn't worth drawing
HEADER_GAP = 26  # art block -> first item

RIGHT_MARGIN = 40
STATUS_MARGIN = 18

CHROME_HEIGHT = 34
TRANSPORT_HEIGHT = 104
TRANSPORT_MARGIN = 28  # tighter than RIGHT_MARGIN: this row is the crowded one
RESIZE_MARGIN = 6  # window border the frameless resize grips live in

# The transport row must survive the minimum window width. Fixed widths would
# not: at 720 the row wanted 773 px, so Qt overlapped the readouts onto the
# sliders it could not shrink. Every control below is a *range*.
BUTTON_W, BUTTON_H = 34, 28
SPEED_SLIDER = (72, 140)  # min, max
VOLUME_SLIDER = (62, 96)
SPEED_VALUE_W = 46
VOLUME_VALUE_W = 36

WINDOW_DEFAULT = (980, 640)
WINDOW_MINIMUM = (720, 480)


# -- stylesheet ------------------------------------------------------------
#
# Only the transport bar is stock Qt widgets; everything else is painted. These
# rules deliberately set no widget *background* -- the window gradient is
# painted once by the window and shows through every child that doesn't fill.


def rgba(color: QColor) -> str:
    return f"rgba({color.red()},{color.green()},{color.blue()},{color.alpha()})"


def transport_qss() -> str:
    return f"""
    QLabel {{ color: {rgba(TEXT_DIM)}; background: transparent; }}

    /* `add-page` has to be styled explicitly. Left alone it keeps the native
       palette's light track, which over this background reads as *filled* --
       every slider looks pegged at maximum. */
    QSlider::groove:horizontal {{ height: 4px; background: transparent; }}
    QSlider::add-page:horizontal {{
        height: 4px;
        background: {rgba(QColor(255, 255, 255, 34))};
        border-radius: 2px;
    }}
    QSlider::sub-page:horizontal {{
        height: 4px;
        background: {rgba(ACCENT)};
        border-radius: 2px;
    }}
    /* The handle's height is the groove's plus its own margins: 4 + 2*4 = 12,
       which matches the width so the radius makes a circle rather than a slab. */
    QSlider::handle:horizontal {{
        width: 12px;
        margin: -4px 0;
        border-radius: 6px;
        background: {rgba(TEXT)};
    }}
    QSlider::handle:horizontal:hover {{ background: {rgba(ACCENT)}; }}
    /* Subcontrol first, pseudo-state second. Get that order wrong and Qt drops
       the malformed rule *and everything after it* -- silently. */
    QSlider::sub-page:horizontal:disabled {{
        background: {rgba(QColor(255, 255, 255, 34))};
    }}
    QSlider::handle:horizontal:disabled {{ background: {rgba(TEXT_FAINT)}; }}

    QPushButton {{
        color: {rgba(TEXT_DIM)};
        background: transparent;
        border: none;
        padding: 0;
    }}
    QPushButton:hover {{ color: {rgba(TEXT)}; }}
    QPushButton:pressed {{ color: {rgba(ACCENT)}; }}
    """
