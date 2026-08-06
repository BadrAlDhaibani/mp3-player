"""The application icon, drawn from `theme.py`.

The mark is a **crescent sweep**: one ribbon travelling most of a turn around a
centred label, holding full width through the top and then tapering clockwise to
a point. Motion in one stroke, and the reason it beat the alternatives at 16 px is
that its silhouette is a *ring* -- a ring survives being twelve pixels across
where a note's beam does not.

Three things about it are deliberate and are decisions-log rows, so change them
there rather than here:

* **It is Mono's colours, always.** Not the active palette. The sweep is a
  conical gradient through `Mono`'s own ramp -- cyan-ish where it is thick, pale
  through the middle, faintly violet at the tip -- which is variation in
  *brightness and temperature within one hue family*, not five different icons.
* **There is no tile.** No rounded square, no rim, no background. All four
  corners are transparent and the mark is the whole icon.
* **Which is why it carries a thin dark edge.** With no tile it has to survive a
  dark taskbar *and* Explorer's white list view, and Mono's middle is a
  near-white. One low-alpha pen does that. A soft radial shadow was tried first
  and is a grey blob on anything pale, which is a tile by another name.

**This lives in `ui/` rather than in `tools/` because the running app wears it
too.** `app.py` calls `app_icon()` for `QApplication.setWindowIcon`. That is
necessary and not sufficient on Windows -- see `app._claim_taskbar_identity`,
which is the other half and the reason the taskbar showed a Python logo for a
whole batch. `tools/make_icon.py` is the other consumer: it assembles these
frames into the `.ico` the build stamps into the exe. Nothing binary is checked
in, the same reason there are no `.wav` files for the UI sounds.

**Every size is drawn at its own size, never downscaled.** The sweep is a
hairline at its tip, and a hairline is what downscaling destroys first. The
conventions say to ask which axis the detail is in before downscaling a buffer;
here it is radial and one pixel wide, so the answer is don't. Anything that would
land sub-pixel is clamped to a whole pixel, which is why the small sizes look
blunter than a strict scaling of the 256 -- they have to be.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QConicalGradient,
    QIcon,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

from mp3player.ui import theme

# Windows asks for these and picks whichever fits the slot it is filling: 16 in
# the title bar and the tray, 32 on the desktop and the taskbar, 48 in Explorer's
# medium view, 256 for the extra-large view and the Vista+ preview. Missing sizes
# are scaled from the nearest, badly, which is the whole reason to ship the small
# ones.
SIZES = (16, 24, 32, 48, 64, 128, 256)

# The palette the mark is fixed to, whatever the app is themed as. Looked up by
# name through `theme.palette_by_name`, which **raises** if it is gone -- a
# rename should break the build, not silently repaint the icon.
PALETTE_NAME = "Mono"

# The sweep, in units of the canvas. `RING_R` is the ribbon's *centre* line, so
# the mark's true outer edge is `RING_R + WIDTH / 2` and that is what has to stay
# inside the canvas -- there is no tile to clip it any more.
MARGIN = 0.06  # of the canvas, kept clear on every side
WIDTH = 0.15  # ribbon thickness at its thickest, of the canvas
RING_R = 0.5 - MARGIN - WIDTH / 2

# Where it starts and how far it goes. Degrees, counterclockwise-positive with 0
# at three o'clock -- so 130 is the upper left, and a negative sweep travels
# clockwise from there. The 40-degree gap is what keeps the tip clear of the
# thick end; at 20 they overlapped and the crescent read as a closed ring with a
# lump on it.
START_DEG = 130.0
SWEEP_DEG = -320.0

# How the thickness runs out, and **it holds first**. A taper that starts
# immediately spends the whole sweep as a hairline and leaves the round cap
# standing alone as a blob -- which, with a dot in the middle, read unmistakably
# as an eye. Holding full width for the first half means the mark's silhouette is
# a *ring* and the taper is the last thing you notice rather than the first.
TAPER_HOLD = 0.5  # fraction of the sweep at full width
TAPER_POWER = 0.85
TIP_ALPHA = 125  # the tip dissolves rather than stopping
STEPS = 96  # samples along the sweep

# The label, centred. Off-centre was tried first and is what turned the dot into
# a pupil; a record's label is centred and this is large enough to read as one
# rather than as a spindle hole.
CORE_R = 0.125  # radius, of the canvas

# With no tile the mark has to survive Explorer's white list view, and Mono's
# middle is a near-white. A thin dark edge does that; a radial shadow was tried
# first and is a grey blob on anything pale -- the opposite of "no tile". Dropped
# below 32 px, where one dark pixel around a twelve-pixel ring costs more than it
# buys. `BG_BOTTOM` rather than black, so it is the app's own darkest navy.
EDGE_ALPHA = 0.30
EDGE_ABOVE = 32

# Below this the sweep is drawn at constant thickness and a shorter arc: a taper
# that reaches a point needs several pixels to do it in, and at a 14 px canvas
# the last third of the sweep is sub-pixel and antialiases into a grey smear that
# makes the ring look broken. A plain arc is still a ring. Same reasoning as the
# shadow being dropped there -- at 16 px a soft halo is just haze.
SIMPLE_BELOW = 24
SMALL_SWEEP_DEG = -300.0
SMALL_WIDTH_FLOOR = 2.0  # pixels
SMALL_CORE_FLOOR = 3.0  # pixels


def _palette() -> theme.Palette:
    return theme.palette_by_name(PALETTE_NAME)


def centre(size: int) -> QPointF:
    """The centre of the canvas, which the ring and the label share."""
    return QPointF(size / 2, size / 2)


def ribbon_width(size: int, t: float) -> float:
    """Thickness of the sweep at `t` (0 at the thick start, 1 at the tip).

    Exported because "it tapers" is arithmetic and therefore an assertion, where
    "it reads as motion" is a picture. Monotonically decreasing by construction,
    and the harness holds it to that.
    """
    full = size * WIDTH
    if size < SIMPLE_BELOW:
        return max(SMALL_WIDTH_FLOOR, full)
    if t <= TAPER_HOLD:
        return full
    run = (1.0 - t) / (1.0 - TAPER_HOLD)
    return max(0.6, full * run**TAPER_POWER)


def _sweep_deg(size: int) -> float:
    return SMALL_SWEEP_DEG if size < SIMPLE_BELOW else SWEEP_DEG


def _point(mid: QPointF, radius: float, degrees: float) -> QPointF:
    radians = math.radians(degrees)
    # Minus on y because Qt's y grows downward and these angles are read the way
    # a protractor reads them.
    return QPointF(
        mid.x() + radius * math.cos(radians),
        mid.y() - radius * math.sin(radians),
    )


def sweep_point(size: int, t: float) -> QPointF:
    """The point on the ribbon's *centre* line at `t` along the sweep.

    Exported so the harness can sample the ribbon without restating the geometry
    -- `t=0` is the middle of the thick end, which is exactly where the odd-even
    fill bug takes its bite out of the mark.
    """
    return _point(centre(size), size * RING_R, START_DEG + _sweep_deg(size) * t)


def crescent_path(size: int) -> QPainterPath:
    """The sweep as one filled path, tapering, with a rounded thick end.

    Built from its two edges rather than stroked: a stroke has one width, and the
    whole point of this mark is that the width runs out. So the outer edge is
    walked forwards, the inner edge back, and the ring closes.

    **The fill rule is set before `simplified()`, not after.** A `QPainterPath`
    fills odd-even by default, so the round cap added at the thick end would
    punch a hole exactly where it overlaps the sweep -- see the convention in
    CLAUDE.md, which this project has now paid for twice.
    """
    mid = centre(size)
    radius = size * RING_R
    sweep = _sweep_deg(size)

    outer: list[QPointF] = []
    inner: list[QPointF] = []
    for step in range(STEPS + 1):
        t = step / STEPS
        half = ribbon_width(size, t) / 2
        angle = START_DEG + sweep * t
        outer.append(_point(mid, radius + half, angle))
        inner.append(_point(mid, radius - half, angle))

    path = QPainterPath(outer[0])
    for point in outer[1:]:
        path.lineTo(point)
    for point in reversed(inner):
        path.lineTo(point)
    path.closeSubpath()

    # A blunt radial cut at the thick end looks sawn off. A circle of the same
    # diameter, centred on the ribbon's own centre line, rounds it.
    cap = ribbon_width(size, 0.0)
    cap_at = _point(mid, radius, START_DEG)
    path.addEllipse(QRectF(cap_at.x() - cap / 2, cap_at.y() - cap / 2, cap, cap))

    # `simplified()` is not decoration here, and forgetting it is visible: the
    # returned path is *stroked* as well as filled, so without the union the pen
    # traces the cap circle's hidden half straight across the ribbon and the mark
    # comes out with a lens-shaped seam bitten out of its thick end. The fill rule
    # has to be set first -- see the convention in CLAUDE.md.
    path.setFillRule(Qt.WindingFill)
    return path.simplified()


def core_rect(size: int) -> QRectF:
    """The label disc, centred."""
    at = centre(size)
    radius = max(SMALL_CORE_FLOOR / 2, size * CORE_R)
    return QRectF(at.x() - radius, at.y() - radius, radius * 2, radius * 2)


def mark_bounds(size: int) -> QRectF:
    """Everything that is actually the mark -- the sweep and the core, no shadow.

    What "it stays inside the canvas" is asserted against. Batch 15's icon drew a
    dot hanging half off its tile, and with no tile there is nothing to clip a
    repeat of that: it would just be cropped by the image edge.
    """
    return crescent_path(size).boundingRect().united(core_rect(size))


def _stop_at(t: float, sweep: float) -> float:
    """Gradient position for the point `t` along the sweep.

    **A `QConicalGradient` measures its stops counterclockwise, and this sweep
    runs clockwise.** Laying the stops out at `t` directly therefore applies the
    ramp *backwards*: the first render put the tip's faint violet immediately
    next to the thick cyan end, with a hard seam between them where the gradient
    wrapped, and it looked like a z-order mistake rather than a direction one.
    The angle at `t` is `START_DEG + sweep * t`, so its position is that offset
    over a full turn -- which for a negative sweep counts down from 1.0, exactly
    as it should.
    """
    return (sweep * t / 360.0) % 1.0


def _ink(size: int) -> QConicalGradient:
    """Mono's ramp, laid *around* the sweep rather than across the canvas.

    A conical gradient is the one Qt gradient whose parameter is an angle, which
    is exactly the sweep's own parameter -- so the colour travels with the ribbon
    instead of with the picture.
    """
    pal = _palette()
    sweep = _sweep_deg(size)
    gradient = QConicalGradient(centre(size), START_DEG)
    for t, fraction, alpha in ((0.0, 0.0, 255), (0.5, 0.4, 255), (1.0, 1.0, TIP_ALPHA)):
        gradient.setColorAt(_stop_at(t, sweep), theme.ramp_color(pal, fraction, alpha=alpha))
    return gradient


def draw(size: int) -> QImage:
    """One frame of the icon, drawn at `size` x `size`."""
    image = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)

    # The dark edge is what stands in for a tile, and it is a *pen* rather than a
    # halo -- see `EDGE_ALPHA`. Applied as one pen for both shapes so the mark
    # reads as a single object with an outline, not two outlined objects.
    if size >= EDGE_ABOVE:
        painter.setPen(QPen(theme.faded(theme.BG_BOTTOM, EDGE_ALPHA), max(1.0, size / 96.0)))
    else:
        painter.setPen(Qt.NoPen)

    painter.setBrush(_ink(size))
    painter.drawPath(crescent_path(size))

    # The core is solid rather than gradient-filled: it is the one shape that has
    # to still be a shape at 16 px, and it is what the harness samples for "is
    # this still Mono's anchor".
    painter.setBrush(_palette().anchor)
    painter.drawEllipse(core_rect(size))

    painter.end()
    return image


def app_icon(sizes: tuple[int, ...] = SIZES) -> QIcon:
    """The icon as Qt wants it, for `QApplication.setWindowIcon`.

    Every size added separately rather than handing Qt one big pixmap to scale:
    the small ones have their own pixel floors and their own shorter arc, and
    letting Qt smooth-scale the 256 down to 16 throws exactly that away.

    **All seven, drawn at startup.** Measured on this machine: 6.7 ms for the
    full set against 2.8 ms for the four a window strictly needs -- so the subset
    bought 3.9 ms and cost a second list of sizes that could disagree with
    `SIZES`. Against a launch that already spends 70-210 ms decoding the first
    track, neither number is worth a knob.
    """
    icon = QIcon()
    for size in sizes:
        icon.addPixmap(QPixmap.fromImage(draw(size)))
    return icon
