"""The three category marks, painted rather than set in a font.

`▶ ♪ ⚙` were text in `theme.GLYPH_FAMILY` from Batch 4 until here. The user did
not like the gear, and the reason all three moved rather than just that one is
weight: a painted mark beside two font glyphs reads as mismatched, because a
typeface has its own ideas about stroke weight and optical size and they are not
this project's. `ui/icon.py` is the precedent -- the app icon is drawn from
`theme.py` for the same reason there are no `.wav` files for the UI sounds.

**Each function paints into a box it is handed and reads its ink off the
painter's pen.** That is the whole contract. The caller
(`widgets/crossbar.py._paint_category`) already computed the centre, the size and
the focus-mixed colour before any of this existed, so nothing about geometry,
animation, sizing or hit-testing had to move -- only `drawText` changed.

Two traps this project has already paid for, both in Batch 17, both within an
hour of each other:

* **A `QPainterPath` fills odd-even by default.** Every place a mark overlaps
  itself -- the note's stem inside its head, most obviously -- counts as
  *outside* and is punched transparent. It looks like an alpha or z-order bug,
  not a winding one, which is what makes it expensive.
  `setFillRule(Qt.WindingFill)` **then** `simplified()`, in that order.
* **The small size is a different problem, not the same drawing scaled.** These
  render at 30 px unfocused, which is where a fine counter -- a gear's tooth
  gaps, a wrench's jaw -- antialiases shut and leaves a grey blob. Both of the
  marks that had that problem were candidates that lost; the three here are
  made of lines, lumps and one filled triangle, none of which has a counter to
  lose. What they need instead is **pixel floors**, so a stroke that would land
  at 1.1 px is drawn at 1.5 and stays a line.

Everything else is in units of the box's side, so a mark scales continuously
with the focus animation where a font was snapping to hinted pixel sizes.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPen, QTransform


def _unit(box: QRectF) -> tuple[float, float, float]:
    """Centre and side of the square the mark is drawn in.

    `min` rather than either dimension: the caller hands a square today, and a
    mark that silently stretched if that ever stopped being true is a bug nobody
    would look for.
    """
    return box.center().x(), box.center().y(), min(box.width(), box.height())


# -- Now Playing -----------------------------------------------------------


def draw_play(painter: QPainter, box: QRectF) -> None:
    """A right-pointing triangle, rounded at its corners.

    Rounded by being *stroked as well as filled* with a round join rather than
    by three arcs: one pen setting against a dozen lines of tangent arithmetic,
    and the corner radius then scales with the mark for free.
    """
    cx, cy, s = _unit(box)
    ink = painter.pen().color()
    painter.save()

    # A triangle's mass sits left of its bounding centre, so a geometrically
    # centred one reads as pushed right. This is the standard nudge back.
    cx -= 0.025 * s

    path = QPainterPath(QPointF(cx + 0.265 * s, cy))
    path.lineTo(QPointF(cx - 0.205 * s, cy - 0.250 * s))
    path.lineTo(QPointF(cx - 0.205 * s, cy + 0.250 * s))
    path.closeSubpath()

    pen = QPen(ink, max(1.0, 0.085 * s))
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(ink)
    painter.drawPath(path)

    painter.restore()


# -- Music -----------------------------------------------------------------


def note_stem(box: QRectF) -> QRectF:
    """The note's stem, which runs *into* the head rather than up to it.

    Exported for the same reason `icon.sweep_point` is: the odd-even fill bug
    takes its bite exactly where two subpaths overlap, so a check for it has to
    sample the overlap -- and a harness that restated this rectangle by hand
    would go on passing after the geometry moved.
    """
    cx, cy, s = _unit(box)
    return QRectF(cx + 0.018 * s, cy - 0.340 * s, 0.058 * s, 0.580 * s)


def draw_note(painter: QPainter, box: QRectF) -> None:
    """An eighth note: tilted head, stem, one flag.

    Three subpaths that overlap on purpose -- the stem runs *into* the head, and
    the flag starts inside the stem -- which is exactly the odd-even case in this
    module's header. Union them under `WindingFill` or the overlaps come out as
    holes.
    """
    cx, cy, s = _unit(box)
    ink = painter.pen().color()
    painter.save()

    def at(x: float, y: float) -> QPointF:
        return QPointF(cx + x * s, cy + y * s)

    # The head is an ellipse tilted up to the right, which is what makes it a
    # note head rather than a dot. Qt cannot add a rotated ellipse to a path, so
    # it is built at the origin and mapped.
    rx, ry = 0.168 * s, 0.124 * s
    head = QPainterPath()
    head.addEllipse(QRectF(-rx, -ry, 2 * rx, 2 * ry))
    head = QTransform().translate(cx - 0.108 * s, cy + 0.215 * s).rotate(-20).map(head)

    stem = QPainterPath()
    stem.addRect(note_stem(box))

    # Out from the stem's top, down and back -- traversed clockwise like the
    # other two, because `WindingFill` unions subpaths that agree and would
    # subtract one that did not.
    flag = QPainterPath(at(0.076, -0.340))
    flag.cubicTo(at(0.300, -0.268), at(0.298, -0.078), at(0.152, 0.048))
    flag.cubicTo(at(0.232, -0.098), at(0.194, -0.198), at(0.076, -0.232))
    flag.closeSubpath()

    mark = QPainterPath()
    mark.addPath(head)
    mark.addPath(stem)
    mark.addPath(flag)
    mark.setFillRule(Qt.WindingFill)

    painter.setPen(Qt.NoPen)
    painter.setBrush(ink)
    painter.drawPath(mark.simplified())

    painter.restore()


# -- Settings --------------------------------------------------------------


def draw_settings(painter: QPainter, box: QRectF) -> None:
    """Three faders at three settings.

    Chosen from a sheet of four (`tools/render.py --marks`), against a gear, a
    dial and a wrench. Two reasons it won, and only the first is about this
    picture: it is the most legible of the four at 30 px, being made of lines
    and lumps where the other three all had a counter that closes up; and it
    rhymes with *this* app rather than with the desktop in general, the player
    being two sliders and a list. The dial lost partly on a third: the app icon
    is already a ring, and two rings in one window is one idea said twice.
    """
    cx, cy, s = _unit(box)
    ink = painter.pen().color()
    painter.save()

    # The knob reads as a knob because it is four times the track's weight, so
    # the two floors are not the same number. Below about 30 px the track would
    # otherwise land under a pixel and antialias into a grey smear, which is the
    # small-size failure this mark has instead of a lost counter.
    track_w = max(1.5, 0.052 * s)
    knob_r = max(2.4, 0.105 * s)
    rows = ((-0.245, 0.115), (0.0, -0.175), (0.245, 0.245))  # y, knob x

    pen = QPen(ink, track_w)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    for y, _ in rows:
        painter.drawLine(
            QPointF(cx - 0.355 * s, cy + y * s), QPointF(cx + 0.355 * s, cy + y * s)
        )

    painter.setPen(Qt.NoPen)
    painter.setBrush(ink)
    for y, x in rows:
        painter.drawEllipse(QPointF(cx + x * s, cy + y * s), knob_r, knob_r)

    painter.restore()
