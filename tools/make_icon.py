"""Draw the application icon from `theme.py`, as a multi-size Windows `.ico`.

    venv/Scripts/python.exe tools/make_icon.py out.ico
    venv/Scripts/python.exe tools/make_icon.py out.png --preview

`build_exe.py` imports `write_ico` and generates the file into its scratch
directory, so nothing binary is checked in and the icon cannot drift from the
palette it came from. That is the same reason there are no `.wav` files for the
UI sounds: this project synthesizes its assets in code.

The mark is the crossbar itself -- a horizontal rule, a vertical column, and the
selection sitting where they cross, which is the one rule the whole app is built
on (`theme.CROSSBAR_Y_RATIO`, and the selection never moving off it). It is
drawn from `BG_TOP`/`BG_MID`/`BG_BOTTOM`, `TEXT_DIM`, `TEXT_FAINT`, `PANEL_EDGE`
and `ACCENT`, so changing the palette in `theme.py` changes the icon.

**Every size is drawn at its own size, never downscaled.** The detail here is
three hairlines, and a hairline is exactly what survives downscaling worst --
16 px rendered natively is one crisp pixel where 256 px halved four times is
four shades of grey. The conventions say to ask which axis the detail is in
before downscaling a buffer; here the answer is "both, and it is one pixel
wide", so the answer is don't.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QBuffer, QByteArray, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QApplication

from mp3player.ui import theme

# Windows asks for these and picks whichever fits the slot it is filling: 16 in
# the title bar and the tray, 32 on the desktop, 48 in Explorer's medium view,
# 256 for the extra-large view and the Vista+ preview. Missing sizes are scaled
# from the nearest, badly, which is the whole reason to ship the small ones.
SIZES = (16, 24, 32, 48, 64, 128, 256)

# Where the crossbar's own numbers land in a square. `CROSSBAR_Y_RATIO` is the
# real one, straight from `theme`; the column's x is a whole-icon restatement of
# the same idea rather than `ITEM_X / WINDOW_DEFAULT[0]`, because an icon is
# square and the window is not -- taking that ratio literally puts the crossing
# so far left the mark stops looking like a cross.
COLUMN_X_RATIO = 0.42

# The selection plate, its four neighbours, and how far the glow reaches past
# it. `NEIGHBOUR_AT` is measured in plates from the centre and has to keep the
# outermost dot inside the tile at every size -- the first version put it at
# three plates and drew half a circle hanging off the right edge.
PLATE_RATIO = 0.18
NEIGHBOUR_AT = 1.65
NEIGHBOUR_RATIO = 0.26  # of the plate
GLOW_REACH = 2.6  # of the plate


def _px(size: int, ratio: float) -> float:
    return size * ratio


def draw(size: int) -> QImage:
    """One frame of the icon, drawn at `size` x `size`."""
    image = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)

    # A little air around the tile, so the rounded corners are visible against a
    # dark taskbar rather than being clipped flush to the canvas edge.
    inset = max(1.0, _px(size, 0.045))
    tile = QRectF(inset, inset, size - 2 * inset, size - 2 * inset)
    radius = tile.width() * 0.20

    # `background_brush` wants the window's own gradient stops, so the icon is
    # lit from the top exactly as the app is -- the crossbar sits in the bright
    # band in both.
    painter.setPen(Qt.NoPen)
    painter.setBrush(theme.background_brush(QRect(0, 0, size, size)))
    painter.drawRoundedRect(tile, radius, radius)

    hairline = max(1.0, size / 96.0)

    # The glossy panel edge. Below 32 px it is a grey ring around a 30 px mark
    # and costs more than it says, so it is dropped rather than dimmed.
    if size >= 32:
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(theme.PANEL_EDGE, hairline))
        painter.drawRoundedRect(tile.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

    cross_y = tile.top() + tile.height() * theme.CROSSBAR_Y_RATIO
    cross_x = tile.left() + tile.width() * COLUMN_X_RATIO

    # The crossbar rule, and the item column crossing it. The rule is the
    # brighter of the two for the same reason it is on screen: it is the row the
    # selection lives on, and the column is what scrolls past it.
    painter.setPen(QPen(theme.faded(theme.TEXT_DIM, 0.62), hairline))
    painter.drawLine(
        QPointF(tile.left() + tile.width() * 0.08, cross_y),
        QPointF(tile.right() - tile.width() * 0.08, cross_y),
    )
    painter.setPen(QPen(theme.faded(theme.TEXT_FAINT, 0.55), hairline))
    painter.drawLine(
        QPointF(cross_x, tile.top() + tile.height() * 0.10),
        QPointF(cross_x, tile.bottom() - tile.height() * 0.08),
    )

    plate = _px(size, PLATE_RATIO)
    painter.setPen(Qt.NoPen)

    # The neighbours: one more category either side along the rule, one more
    # item above and below down the column. They are what makes it read as a
    # *bar* rather than as a plus sign -- and they are the first thing to go,
    # because at 32 px they are sub-pixel smudges sitting next to the one mark
    # that has to stay legible.
    if size >= 48:
        small = plate * NEIGHBOUR_RATIO
        offset = plate * NEIGHBOUR_AT
        painter.setBrush(theme.faded(theme.TEXT_FAINT, 0.62))
        for point in (
            QPointF(cross_x - offset, cross_y),
            QPointF(cross_x + offset, cross_y),
            QPointF(cross_x, cross_y - offset),
            QPointF(cross_x, cross_y + offset),
        ):
            painter.drawEllipse(point, small / 2, small / 2)

    # The selection, glowing. One radial gradient rather than a stack of
    # translucent rects: overlapping fills accumulate alpha and step at every
    # edge, which is the Batch 5 bug where a glow came out looking like a
    # border. Twice. It looked like one here too, until this was rendered.
    reach = plate * GLOW_REACH / 2
    halo = QRadialGradient(QPointF(cross_x, cross_y), reach)
    halo.setColorAt(0.00, theme.faded(theme.ACCENT, 0.42))
    halo.setColorAt(0.45, theme.faded(theme.ACCENT, 0.16))
    halo.setColorAt(1.00, theme.faded(theme.ACCENT, 0.0))
    painter.setBrush(halo)
    painter.drawEllipse(QPointF(cross_x, cross_y), reach, reach)

    painter.setBrush(theme.ACCENT)
    painter.drawRoundedRect(
        QRectF(cross_x - plate / 2, cross_y - plate / 2, plate, plate),
        plate * 0.28,
        plate * 0.28,
    )

    painter.end()
    return image


def _png_bytes(image: QImage) -> bytes:
    # `store` is a named local on purpose. `QBuffer(QByteArray())` takes a
    # reference to a Python temporary that is then collected while the C++ side
    # still points at it, and the result is a segfault inside `image.save` --
    # not an exception, and not on the line that looks wrong.
    store = QByteArray()
    buffer = QBuffer(store)
    buffer.open(QBuffer.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(store)


def write_ico(path: Path, sizes: tuple[int, ...] = SIZES) -> Path:
    """Write a multi-size `.ico`. Needs a live `QApplication`.

    The container is assembled by hand rather than by Qt: Qt's ICO writer takes
    one image per file, and the point of an `.ico` is that it holds all seven.
    It is a 6-byte header, a 16-byte directory entry each, then the payloads --
    which are PNGs, because an ICO entry may be either a PNG or a headerless
    BMP and Windows has taken PNG since Vista. This project declares Windows 11.
    """
    frames = [_png_bytes(draw(size)) for size in sizes]

    header = struct.pack("<HHH", 0, 1, len(frames))
    offset = len(header) + 16 * len(frames)

    directory = b""
    for size, payload in zip(sizes, frames, strict=True):
        # 256 is stored as 0: the field is one byte and 256 does not fit, which
        # is also why there is no 512.
        directory += struct.pack(
            "<BBBBHHII",
            size % 256,
            size % 256,
            0,  # palette size: 0 for anything truecolour
            0,  # reserved
            1,  # colour planes
            32,  # bits per pixel
            len(payload),
            offset,
        )
        offset += len(payload)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + directory + b"".join(frames))
    return path


def write_preview(path: Path, sizes: tuple[int, ...] = SIZES) -> Path:
    """Every size, side by side on one sheet, so you can look at it.

    Same reasoning as `render.py` and `filmstrip.py`: the question "does 16 px
    still read as a crossbar" is not an assertion, it is a picture.
    """
    gap = 12
    width = sum(sizes) + gap * (len(sizes) + 1)
    height = max(sizes) + gap * 2

    sheet = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
    sheet.fill(QColor(30, 30, 30))

    painter = QPainter(sheet)
    x = gap
    for size in sizes:
        painter.drawImage(x, gap + (max(sizes) - size) // 2, draw(size))
        x += size + gap
    painter.end()

    sheet.save(str(path))
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", nargs="?", default="XMB Player.ico")
    parser.add_argument(
        "--preview",
        action="store_true",
        help="write a PNG of every size on one sheet instead of an .ico",
    )
    args = parser.parse_args()

    # QImage and QPainter both need one; nothing here needs a window, so
    # offscreen is enough and it draws no text, which is the one thing the
    # offscreen platform cannot do.
    app = QApplication.instance() or QApplication(sys.argv)

    path = Path(args.out)
    if args.preview:
        write_preview(path)
        print(f"wrote {path}  ({', '.join(str(n) for n in SIZES)} px)")
    else:
        write_ico(path)
        print(f"wrote {path}  ({path.stat().st_size / 1024:.1f} KB, {len(SIZES)} sizes)")

    # Named rather than discarded: PySide6 tears a QApplication down when the
    # last Python reference goes, and letting that happen part-way through the
    # function is its own class of crash.
    assert app is not None
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
