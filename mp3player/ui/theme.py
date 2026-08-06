"""Colors, fonts, metrics -- the single source of truth for how this looks.

Nothing here imports another `ui` module, so every widget can pull from it
without a cycle. If a number appears in two widgets, it belongs in this file.

The palette is PS3 XMB read from memory rather than sampled: a near-black navy
that lifts toward the horizon, white text at three brightnesses, and one icy
accent used sparingly enough that it still reads as an accent. The wave is
painted *over* `background_brush`; the gradient is what shows through it.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QFont, QLinearGradient

# -- palette ---------------------------------------------------------------

BG_TOP = QColor(12, 30, 62)
BG_MID = QColor(6, 16, 38)
BG_BOTTOM = QColor(2, 6, 15)

TEXT = QColor(255, 255, 255)
TEXT_DIM = QColor(178, 196, 224)
TEXT_FAINT = QColor(120, 140, 172)

# The accent at 1.00x. Nothing paints with these any more -- `accent()` and
# `accent_soft()` further down are what the widgets call, because the accent
# now travels with the speed slider. These stay as the *anchor*: the wave's hue
# knots were fitted so the ramp passes exactly through them at 1.00x, and that
# invariant is only checkable against a value that holds still.
#
# Since Batch 10 there are five ramps and this is specifically *XMB Blue's*
# anchor -- the default, and the only one that predates the others. Every palette
# carries its own; see `PALETTES`.
ACCENT = QColor(126, 200, 255)
ACCENT_SOFT = QColor(126, 200, 255, 70)

LINE = QColor(255, 255, 255, 28)  # the crossbar rule
PANEL = QColor(255, 255, 255, 18)  # art placeholder, chrome hover
PANEL_EDGE = QColor(255, 255, 255, 46)
GROOVE = QColor(255, 255, 255, 34)  # the unfilled part of any slider track

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
        return round(a + (b - a) * amount)

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
    weight: QFont.Weight = QFont.Normal,
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
# Three info lines, tightened from the two-line 54/78 to make room without
# moving the slider. A third at the old spacing would have landed at 102, whose
# 18px box runs to 111 against a slider box that starts at 112 -- one pixel is
# not clearance. 46/68/90 keeps the 22px rhythm and leaves 22px below the last.
NP_INFO_FIRST = 46  # row -> first info line
NP_INFO_SECOND = 68
NP_INFO_THIRD = 90
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
#
# Both numbers came down in Batch 6, and by looking rather than by feel
# (`tools/filmstrip.py`): a strip of one row step rendered every 27 ms was
# still visibly travelling at 54 ms and *identical* from 81 ms to 190. An
# ease-out spends its last third covering the last few percent of the distance,
# so the old durations were the length of the motion plus a drift nobody can
# see.
#
# Shortening does not remove that drift -- the invisible fraction belongs to
# the curve, not to the duration, and roughly the last half of any ease-out is
# imperceptible. It makes the total honest instead: the drift is now ~60 ms
# rather than ~110. Flattening the curve is the other lever, and the arrival is
# where it would pay most, a fade being even more front-loaded to the eye than
# a slide. Left alone deliberately: one motion character across the shell, and
# that one is a preference rather than something a filmstrip settles.
#
# The curve stays an ease-*out* for a reason that outranks taste: `Tween.to()`
# restarts from wherever the value has got to, and an ease-in restarts it at
# zero velocity. Held arrow keys would then stutter once per repeat, which is
# the exact problem the restart-from-current behaviour exists to avoid.

SLIDE_MS = 140  # crossbar and item column, sliding to the new selection
APPEAR_MS = 160  # a category's content arriving after a crossbar step
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

# -- the ramps -------------------------------------------------------------
#
# Hue tracks the speed slider, so the atmosphere reads out the one thing this
# app is for: deep blue at daycore, the accent itself at 1.00x, violet at
# nightcore. The knots are (slider fraction, value) -- 1.00x is 0.4 of the way
# along a 0.80..1.30 range, which is why the middle knot sits there.
#
# A *theme* is a swap of these two tuples and nothing else. The navy gradient and
# the white/grey text hold still whichever palette is on, for the same reason
# Batch 9 kept its scope to the accent: the frame staying put is what makes the
# colour shift read as deliberate rather than as the app changing skin.

Knots = tuple[tuple[float, float], ...]


@dataclass(frozen=True, slots=True)
class Palette:
    """One preset spectrum: where the colour travels as the slider moves.

    `anchor` is what this palette's 1.00x comes out as, **written by hand rather
    than derived**. That is the only thing keeping the harness's "1.00x is the
    accent" check from becoming a tautology now that the knots can move -- a
    fitted value compared against itself proves nothing.
    """

    name: str
    hue: Knots
    saturation: Knots
    anchor: QColor


# The default is first, and its knots are the ones the app shipped with. Every
# other palette keeps the same shape -- three knots, the middle one at 0.4 --
# because that is where 1.00x lands and the resting colour belongs on a knot.
#
# Knots may run outside 0..1: `wave_color` takes the hue modulo 1 *after*
# interpolating, so Ember's -0.08 is hot pink and Vapor's 1.02 is coral. That is
# how a ramp crosses the red wrap without `_along` lerping the long way round
# through green. Do not "fix" one of these back into range.
PALETTES: tuple[Palette, ...] = (
    Palette(
        "XMB Blue",
        hue=((0.0, 0.625), (0.4, 0.571), (1.0, 0.819)),
        saturation=((0.0, 0.70), (0.4, 0.51), (1.0, 0.74)),
        anchor=ACCENT,
    ),
    Palette(
        "Ember",
        hue=((0.0, 0.085), (0.4, 0.035), (1.0, -0.08)),
        saturation=((0.0, 0.85), (0.4, 0.70), (1.0, 0.62)),
        anchor=QColor(255, 114, 76),
    ),
    # Daycore was 0.47 and rendered as the same teal Vapor opens on -- two
    # presets whose slowest end is indistinguishable is one preset with a longer
    # menu. 0.43 keeps the whole ramp inside the greens, which is also what the
    # name promises.
    Palette(
        "Aurora",
        hue=((0.0, 0.43), (0.4, 0.36), (1.0, 0.22)),
        saturation=((0.0, 0.75), (0.4, 0.60), (1.0, 0.72)),
        anchor=QColor(102, 255, 126),
    ),
    Palette(
        "Vapor",
        hue=((0.0, 0.50), (0.4, 0.88), (1.0, 1.02)),
        saturation=((0.0, 0.65), (0.4, 0.55), (1.0, 0.60)),
        anchor=QColor(255, 114, 216),
    ),
    # Saturation stays low throughout -- but not *too* low. At 0.06 the anchor
    # measured (240,248,255), which is white to within a rounding error: the
    # selected row's readout would have been the same colour as its title, and
    # an accent that matches the text is not an accent. 0.16 is still "no
    # colour" at a glance and still tells the two apart.
    Palette(
        "Mono",
        hue=((0.0, 0.55), (0.4, 0.58), (1.0, 0.78)),
        saturation=((0.0, 0.34), (0.4, 0.16), (1.0, 0.28)),
        anchor=QColor(214, 235, 255),
    ),
)

_palette = PALETTES[0]


def palette() -> Palette:
    """The palette in force. Read fresh -- widgets never cache a colour."""
    return _palette


def palette_names() -> tuple[str, ...]:
    """Every preset, in cycle order. The Settings row steps through this."""
    return tuple(item.name for item in PALETTES)


def set_palette(name: str) -> bool:
    """Swap the ramp. Always True: the caller must re-apply the stylesheet.

    Unlike `set_accent_fraction` there is no gate to earn here. That one is
    keyed on the slider fraction, which does not move when only the palette
    does -- so a swap sails straight through the bucket comparison and the
    transport bar would keep the old colour. Returning True unconditionally is
    the honest answer, and a palette change happens on a keypress rather than
    once per pixel of a drag, so there is nothing to protect.

    Nothing derived is recomputed here. `_text_mix` is keyed on this value, so
    it notices by itself -- see the note above it for why that is not merely
    tidier.
    """
    global _palette

    for item in PALETTES:
        if item.name == name:
            _palette = item
            break
    else:
        _palette = PALETTES[0]
    return True


def _along(knots: Knots, fraction: float) -> float:
    """Piecewise-linear lookup through `knots`, clamped at both ends."""
    fraction = max(0.0, min(1.0, fraction))
    for (x0, y0), (x1, y1) in pairwise(knots):
        if fraction <= x1:
            span = x1 - x0
            return y0 if span <= 0 else lerp(y0, y1, (fraction - x0) / span)
    return knots[-1][1]


def ramp_color(
    pal: Palette, fraction: float, *, alpha: int = 255, hue_shift: float = 0.0
) -> QColor:
    """A *named* palette's colour at a point along the speed slider.

    Split out of `wave_color` so something can ask for one particular ramp
    regardless of which palette is in force. The only caller that wants that is
    `ui/icon.py`, whose mark is fixed to Mono however the app is themed -- see
    the decisions log. Everything that paints the app itself wants the active
    palette and should keep calling `wave_color`.
    """
    hue = (_along(pal.hue, fraction) + hue_shift) % 1.0
    color = QColor.fromHsvF(hue, _along(pal.saturation, fraction), 1.0)
    color.setAlpha(max(0, min(255, alpha)))
    return color


def wave_color(fraction: float, *, alpha: int = 255, hue_shift: float = 0.0) -> QColor:
    """The wave's colour at a point along the speed slider.

    At `fraction=0.4` this returns the active palette's anchor to within a
    rounding step, which is the point: at 1.00x the wave is the same colour as
    every other accent in the app, and only the effect pulls it away. On the
    default palette that anchor is ACCENT, so 1.00x is the icy blue it always
    was.
    """
    return ramp_color(_palette, fraction, alpha=alpha, hue_shift=hue_shift)


def palette_by_name(name: str) -> Palette:
    """Look one up. Raises rather than falling back -- see `ui/icon.py`.

    `PlayerController` clamps an unknown *setting* to the default on purpose (a
    file written by a later build should not lose the user's theme). This is the
    other case: a name written in source, which if it stops matching is a typo or
    a rename, and a silent fallback there would leave the icon quietly wearing
    the wrong palette with nothing to notice it.
    """
    for pal in PALETTES:
        if pal.name == name:
            return pal
    raise LookupError(f"no palette named {name!r}; have {palette_names()}")


# -- the live accent -------------------------------------------------------
#
# The accent rides the same ramp as the wave, so the selection plate, the glow,
# both slider fills and every readout turn violet along with the ribbons behind
# them. At 1.00x this is ACCENT and the app looks exactly as it always did;
# only the effect pulls it away.
#
# This is module state, which is worth being deliberate about: it works because
# no widget captures a colour at construction -- every paintEvent reads from
# this module afresh, so one assignment reaches everything that paints. The one
# exception is the transport bar, whose colours come from a stylesheet applied
# once (see `transport_qss` below), and that is what `set_accent_fraction`
# returns a bool for.

_accent_fraction = 0.4  # 1.00x, where ACCENT lives
_QSS_STEPS = 48  # buckets across the range; ~2 degrees of hue each
_accent_bucket = int(_accent_fraction * _QSS_STEPS)


def set_accent_fraction(fraction: float) -> bool:
    """Move the accent along the speed ramp. True if the stylesheet needs redoing.

    Painted widgets get the exact colour and repaint anyway. The stylesheet is
    the expensive one -- a drag emits on every mouse-move and re-applying a
    stylesheet re-polishes the whole widget tree -- so it is told only when the
    colour has moved a bucket, which is a step too small to see in a 4px fill.
    """
    global _accent_fraction, _accent_bucket

    _accent_fraction = max(0.0, min(1.0, float(fraction)))
    bucket = int(_accent_fraction * _QSS_STEPS)
    if bucket == _accent_bucket:
        return False
    _accent_bucket = bucket
    return True


def accent_fraction() -> float:
    """Where the accent currently sits. For the harness, and for symmetry."""
    return _accent_fraction


def accent(alpha: int = 255) -> QColor:
    """The accent right now. At 1.00x this is ACCENT to within a rounding step."""
    return wave_color(_accent_fraction, alpha=alpha)


def accent_soft() -> QColor:
    """The selection plate's fill: the accent at ACCENT_SOFT's opacity.

    Derived rather than a second literal -- the two used to be independent
    QColors carrying the same RGB, which is a desync waiting for a palette edit.
    """
    return accent(ACCENT_SOFT.alpha())


# -- the accent, as text ---------------------------------------------------
#
# HSV value is not lightness. Every colour off the ramp has V=1.0, but a
# saturated blue at V=1.0 is far darker to the eye than a cyan at V=1.0 -- so
# the daycore end came out at 4.9:1 against the background, *below* TEXT_FAINT's
# 5.5:1. Rendered, that inverted the row: the selected track's artist was
# fainter than the unselected ones above and below it, which is the opposite of
# what focus is supposed to do. Fills were fine at every speed; it is only text.
#
# So text mixes toward white -- but only as far as it has to. A flat mix would
# lift 1.00x too, and "at 1.00x the app looks exactly as it always did" is the
# invariant the whole ramp is hung on. At 1.00x the accent already clears the
# floor, the mix comes out zero, and nothing moves.

_TEXT_CONTRAST_FLOOR = 7.0  # comfortably above TEXT_FAINT, below ACCENT's 10.4


def _luminance(color: QColor) -> float:
    def channel(value: int) -> float:
        v = value / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * channel(color.red())
        + 0.7152 * channel(color.green())
        + 0.0722 * channel(color.blue())
    )


def _contrast(first: QColor, second: QColor) -> float:
    high, low = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


# Cached, and keyed on the two things it is a function of rather than
# recomputed by whoever moved one of them. It used to be a bare global that
# `set_palette` and `set_accent_fraction` each had to remember to refresh, and
# the comment in the first of them named the risk in its own words: forgetting
# it is the Batch 9 bug with a new way in. That is the conventions' "a gate
# keyed on one input is a hole the moment a second input can change the same
# output" applied to the value living next door to the gate it was written
# about -- and a third writer of either input, or a third input entirely, could
# desync this silently, because the symptom is a colour and not an error.
#
# Keyed on the inputs there is nothing left to remember: a stale key cannot
# survive a read.
#
# It is also slightly cheaper, and the number is here so nobody re-derives it as
# a justification: the loop below runs up to twenty contrast computations and
# used to run on *every* `set_accent_fraction`, i.e. once per mouse-move of a
# drag. Moving it behind a key takes a 300-step drag from 0.051 to 0.033 ms per
# step -- against a drag step that costs 4.70 ms in total, so it is 0.4% and not
# a reason to do anything. The correctness is the reason.
_text_mix_key: tuple[str, float] | None = None
_text_mix_value = 0.0


def _text_mix() -> float:
    """How far toward white this hue has to go to stay readable. 0 at 1.00x."""
    global _text_mix_key, _text_mix_value

    key = (_palette.name, _accent_fraction)
    if key == _text_mix_key:
        return _text_mix_value

    base = accent()
    amount = 0.0
    while amount < 1.0 and _contrast(mix(base, TEXT, amount), BG_MID) < _TEXT_CONTRAST_FLOOR:
        amount += 0.05
    _text_mix_key, _text_mix_value = key, amount
    return amount


def accent_text() -> QColor:
    """The accent for anything drawn with a pen: readouts, the marker, glyphs."""
    amount = _text_mix()
    return mix(accent(), TEXT, amount) if amount else accent()


# -- stylesheet ------------------------------------------------------------
#
# Only the transport bar is stock Qt widgets; everything else is painted. These
# rules deliberately set no widget *background* -- the window gradient is
# painted once by the window and shows through every child that doesn't fill.


def rgba(color: QColor) -> str:
    return f"rgba({color.red()},{color.green()},{color.blue()},{color.alpha()})"


def transport_qss() -> str:
    """The bottom bar's colours. Rebuilt whenever the accent moves a bucket.

    Everything else in the app paints itself and so picks the accent up on its
    next repaint for free. These are stock Qt widgets, so their colour is baked
    into a stylesheet at `setStyleSheet` time and someone has to re-apply it --
    `TransportBar.refresh_accent`.
    """
    return f"""
    QLabel {{ color: {rgba(TEXT_DIM)}; background: transparent; }}

    /* `add-page` has to be styled explicitly. Left alone it keeps the native
       palette's light track, which over this background reads as *filled* --
       every slider looks pegged at maximum. */
    QSlider::groove:horizontal {{ height: 4px; background: transparent; }}
    QSlider::add-page:horizontal {{
        height: 4px;
        background: {rgba(GROOVE)};
        border-radius: 2px;
    }}
    QSlider::sub-page:horizontal {{
        height: 4px;
        background: {rgba(accent())};
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
    QSlider::handle:horizontal:hover {{ background: {rgba(accent())}; }}
    /* Subcontrol first, pseudo-state second. Get that order wrong and Qt drops
       the malformed rule *and everything after it* -- silently. */
    QSlider::sub-page:horizontal:disabled {{
        background: {rgba(GROOVE)};
    }}
    QSlider::handle:horizontal:disabled {{ background: {rgba(TEXT_FAINT)}; }}

    QPushButton {{
        color: {rgba(TEXT_DIM)};
        background: transparent;
        border: none;
        padding: 0;
    }}
    QPushButton:hover {{ color: {rgba(TEXT)}; }}
    QPushButton:pressed {{ color: {rgba(accent_text())}; }}
    """
