"""Colors, fonts, metrics -- the single source of truth for how this looks.

Nothing here imports another `ui` module, so every widget can pull from it
without a cycle. If a number appears in two widgets, it belongs in this file.

The palette is PS3 XMB read from memory rather than sampled: a near-black navy
that lifts toward the horizon, white text at three brightnesses, and one icy
accent used sparingly enough that it still reads as an accent. The wave is
painted *over* `background_brush`; the gradient is what shows through it.
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


def mix(first: QColor, second: QColor, amount: float) -> QColor:
    """`first` at 0, `second` at 1. Alpha is interpolated with the channels.

    What lets a category or an item *become* the selection rather than switch
    to it: everything about the active look is the far end of a mix, so the
    animation gets a cross-fade for free.
    """
    amount = max(0.0, min(1.0, amount))

    def channel(a: int, b: int) -> int:
        return int(round(a + (b - a) * amount))

    return QColor(
        channel(first.red(), second.red()),
        channel(first.green(), second.green()),
        channel(first.blue(), second.blue()),
        channel(first.alpha(), second.alpha()),
    )


def lerp(first: float, second: float, amount: float) -> float:
    return first + (second - first) * max(0.0, min(1.0, amount))


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

# The art placeholder lives in the empty gutter left of the item column, below
# the category label -- not above the items. Stacking it above the column meant
# competing with them for vertical room, which the 720x480 minimum simply does
# not have; out here its size is bounded by the gutter instead, so no window
# size can take it away.
ART_MAX = 180
ART_MIN = 56  # below this, don't bother
ART_TOP_GAP = 46  # category label baseline -> top of the art
ART_BOTTOM_PAD = 20

HEADER_GAP = 26  # title/subtitle block -> first item

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
VOLUME_SLIDER = (62, 96)
VOLUME_VALUE_W = 36

# Both sliders in the app work in hundredths, so 0.80x..1.30x is 80..130. Lives
# here rather than in `transport.py` because the speed slider is painted by
# `item_column.py` now and the two must agree.
SPEED_SCALE = 100

# The painted speed slider: DAYCORE | track | NIGHTCORE | readout.
SLIDER_END_LABEL = 10  # pixel size of the two end captions
SLIDER_LABEL_GAP = 14
SLIDER_TRACK_H = 4
SLIDER_HANDLE = 12
SLIDER_TRACK_MIN = 60  # narrower than this and it isn't worth painting
SLIDER_VALUE_W = 68  # room for the readout *and* a gap after NIGHTCORE

# The Now Playing page, as offsets from the crossbar row. It is a page, not a
# list -- the song title sits *on* the row and everything else hangs beneath it
# at a fixed distance, so nothing here scrolls.
NP_TITLE = 24  # font size of the song title
NP_INFO_FIRST = 54  # row -> first info line
NP_INFO_SECOND = 78
NP_INFO_TEXT = 13
NP_SLIDER = 128
NP_HINT = 154
NP_HINT_TEXT = 11

WINDOW_DEFAULT = (980, 640)
WINDOW_MINIMUM = (720, 480)


# -- motion ----------------------------------------------------------------
#
# Short enough that holding an arrow key still feels like scrubbing a list
# rather than waiting for it. The slide is the only thing that moves on a
# navigation, so it sets the whole app's tempo.

SLIDE_MS = 190  # crossbar and item column, sliding to the new selection
APPEAR_MS = 220  # a category's content arriving after a crossbar step
APPEAR_OFFSET = 26  # how far it flies in from, in pixels

# The selection glow: rounded rects *stroked* one step further out each time,
# each fainter than the last. Two things this got wrong on the way:
#
# Filled rings stack their alpha over the plate and put a hard step at every
# ring edge, which reads as a border rather than as light. Stroke them.
#
# And the falloff has to start *at* the plate and be gradual. Four rings 5 px
# apart drops from full to half in one step, and that first bright band sitting
# just off the edge is a rim -- the same border by another route. Small steps,
# an eased decay, and enough of them to get out to a believable distance.
GLOW_RINGS = 6
GLOW_STEP = 3
GLOW_ALPHA = 40
GLOW_FALLOFF = 1.6  # exponent; >1 keeps the light close to the plate

# The plate dims while the list is in flight, which is what hides its width
# changing under the new selection. It must not dim to *nothing*, though: a
# Home-to-End jump is several rows of travel, and without a floor the cursor
# would simply be missing for most of it.
GLOW_FLOOR = 0.35


# -- the wave --------------------------------------------------------------
#
# A band centred on the crossbar row, not a full-screen field: it lights the
# row the selection lives on instead of drifting behind the track list.
#
# The buffer is coarse across and full-height down, which is not a compromise
# but a fit to the shape: a ribbon is a long, slowly-varying horizontal band,
# so its edges run almost horizontally and it is the *vertical* sampling alone
# that decides whether they look crisp. Along x a feature spans hundreds of
# pixels and a quarter of them is indistinguishable. Rendering both axes coarse
# is what made the first version look soft.

# A cap, not a promise -- see the note on the timer in `wave.py`. Windows'
# 15.6 ms tick turns a 33 ms coarse timer into roughly 21 fps, which is
# deliberately left alone: the fastest ribbon moves 2 px a frame at 1600 px
# wide, and buying the other 9 fps costs about four times the CPU.
WAVE_FPS = 30
WAVE_SCALE_X = 4  # across: coarse, and invisible
WAVE_SCALE_Y = 1  # down: full, and the only thing crispness depends on
WAVE_AMPLITUDE = 0.085  # of the stage height
WAVE_BAND = 0.42  # falloff distance from the row, of the stage height
WAVE_THICKNESS = 26  # ribbon thickness in full-resolution pixels
WAVE_ALPHA = 52
WAVE_BLOOM_ALPHA = 42
WAVE_BREATH = 0.55  # radians/sec of the bloom's slow swell

# Both of these were set by measurement, not taste -- see the perf note in
# `wave.py`. Sampling a ribbon 60 times across the width is the point where
# faceting stops being visible through the upscale; the glow is a downsampled
# copy of the buffer added back over the top.
WAVE_STEP = 60
# In *screen* pixels, then divided back through each axis's scale. Stated this
# way because the buffer's two axes are scaled differently: a single divisor
# would give a halo four times wider than it is tall without ever saying so.
WAVE_GLOW_RADIUS = 9
WAVE_GLOW = 0.6  # how much of the blurred copy is added back

# Hue tracks the speed slider, so the atmosphere reads out the one thing this
# app is for: deep blue at daycore, the accent itself at 1.00x, violet at
# nightcore. The knots are (slider fraction, value) -- 1.00x is 0.4 of the way
# along a 0.80..1.30 range, which is why the middle knot sits there.
_WAVE_HUE = ((0.0, 0.625), (0.4, 0.571), (1.0, 0.819))
_WAVE_SATURATION = ((0.0, 0.70), (0.4, 0.51), (1.0, 0.74))


def _along(knots: tuple[tuple[float, float], ...], fraction: float) -> float:
    """Piecewise-linear lookup through `knots`, clamped at both ends."""
    fraction = max(0.0, min(1.0, fraction))
    for (x0, y0), (x1, y1) in zip(knots, knots[1:]):
        if fraction <= x1:
            span = x1 - x0
            return y0 if span <= 0 else lerp(y0, y1, (fraction - x0) / span)
    return knots[-1][1]


def wave_color(fraction: float, *, alpha: int = 255, hue_shift: float = 0.0) -> QColor:
    """The wave's colour at a point along the speed slider.

    At `fraction=0.4` this returns ACCENT to within a rounding step, which is
    the point: at 1.00x the wave is the same icy blue as every other accent in
    the app, and only the effect pulls it away.
    """
    hue = (_along(_WAVE_HUE, fraction) + hue_shift) % 1.0
    color = QColor.fromHsvF(hue, _along(_WAVE_SATURATION, fraction), 1.0)
    color.setAlpha(max(0, min(255, alpha)))
    return color


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
