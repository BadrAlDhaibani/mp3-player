"""Assemble the application icon into a multi-size Windows `.ico`.

    venv/Scripts/python.exe tools/make_icon.py out.ico
    venv/Scripts/python.exe tools/make_icon.py out.png --preview

**The drawing is not here.** It is `mp3player/ui/icon.py`, because the running
app wears the same mark -- see the note at the top of that file. What lives here
is the part only a build needs: the ICO container, the preview sheet, and a CLI.

There is no `--theme`: the mark is fixed to one palette by design (a decisions-log
row), so there is nothing for a flag to move. The preview draws every size over
**four backgrounds instead**, which is the question this icon actually raises --
it has no tile, so it has to survive a dark taskbar and Explorer's white list
view with only its shadow to separate it.

`build_exe.py` imports `write_ico` and generates the file into its scratch
directory, so nothing binary is checked in and the icon cannot drift from the
palette it came from.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QBuffer, QByteArray
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from mp3player.ui.icon import SIZES, draw


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


# What the icon has to survive, because it has no tile of its own: a dark
# taskbar, Explorer's white list view, the mid grey of a selected row, and one
# saturated colour so a wallpaper-coloured Start menu is represented too.
PREVIEW_BACKS = (
    ("dark", QColor(32, 32, 32)),
    ("light", QColor(255, 255, 255)),
    ("grey", QColor(140, 140, 140)),
    ("colour", QColor(60, 90, 150)),
)


def write_preview(path: Path, sizes: tuple[int, ...] = SIZES) -> Path:
    """Every size over every background, on one sheet, so you can look at it.

    Same reasoning as `render.py` and `filmstrip.py`: "does 16 px still read as a
    ring" is not an assertion, it is a picture. The four rows are the reason this
    is not just a strip -- a tile-less mark is legible or not *per background*,
    and the pale end of Mono against white is the case that decides whether the
    shadow is doing its job.
    """
    gap = 12
    width = sum(sizes) + gap * (len(sizes) + 1)
    row = max(sizes) + gap * 2

    sheet = QImage(width, row * len(PREVIEW_BACKS), QImage.Format_ARGB32_Premultiplied)
    painter = QPainter(sheet)

    frames = {size: draw(size) for size in sizes}
    for index, (_name, back) in enumerate(PREVIEW_BACKS):
        top = index * row
        painter.fillRect(0, top, width, row, back)
        x = gap
        for size in sizes:
            painter.drawImage(x, top + gap + (max(sizes) - size) // 2, frames[size])
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
        backs = ", ".join(name for name, _ in PREVIEW_BACKS)
        print(f"wrote {path}  ({', '.join(str(n) for n in SIZES)} px over {backs})")
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
