"""Read ID3 tags off a file: what it's called, who by, and the cover.

Two entry points on purpose, because they cost different amounts. The text
frames are a few hundred bytes at the head of the file and every track in the
library needs them to draw a list; the cover is an embedded JPEG that can run to
half a megabyte and only the *playing* track needs one. Reading 200 covers to
paint a list that shows none of them is a scan that visibly hangs, so
`read_tags` and `read_art` are separate calls with separate call sites --
`scan_folder` takes the first, the window takes the second on track change.

Neither raises. A file with no tag, a corrupt tag, a permission error and a file
that is not an MP3 at all are all "no tags" -- same contract as
`library.scan_folder`, and for the same reason: the app degrades to filenames
rather than failing to list a folder.

No Qt here, and no image decoding: `read_art` hands up the raw bytes exactly as
they sat in the frame and `ui/` is what turns them into pixels. Same split as
the `MISSING`/`UNREADABLE` tokens -- core reports, ui renders.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mutagen import MutagenError
from mutagen.id3 import ID3

# The front cover, per the APIC spec's picture-type byte. A file can carry
# several images -- back cover, a band photo, a media shot -- and picking the
# first one in the tag gets you whichever the tagger happened to write first.
_FRONT_COVER = 3


@dataclass(frozen=True, slots=True)
class Tags:
    """The text frames we show. `""` means absent.

    Empty string rather than `None` so callers can say `tags.title or stem`
    without a branch -- which is the fallback rule, spelled once.
    """

    title: str = ""
    artist: str = ""
    album: str = ""

    def __bool__(self) -> bool:
        return bool(self.title or self.artist or self.album)


def read_tags(path: Path | str) -> Tags:
    """Read the text frames from `path`. Never raises; `Tags()` if there's none."""
    tag = _load(path)
    if tag is None:
        return Tags()
    return Tags(
        title=_text(tag, "TIT2"),
        artist=_text(tag, "TPE1"),
        album=_text(tag, "TALB"),
    )


def read_art(path: Path | str) -> bytes | None:
    """The embedded cover from `path` as raw image bytes, or `None`.

    Whatever the tagger put in the frame -- JPEG, PNG, anything -- handed up
    untouched. Deciding whether it decodes is the caller's problem, because
    deciding that means having an image library and this module doesn't.
    """
    tag = _load(path)
    if tag is None:
        return None

    pictures = tag.getall("APIC")
    if not pictures:
        return None

    # Front cover if the file says which is which, otherwise the first one --
    # a tag with one untyped image is far more common than a correctly typed
    # set, so "first" has to stay the fallback rather than the error case.
    for picture in pictures:
        if getattr(picture, "type", None) == _FRONT_COVER and picture.data:
            return bytes(picture.data)

    data = pictures[0].data
    return bytes(data) if data else None


def _load(path: Path | str) -> ID3 | None:
    """Parse the ID3 tag, or `None` if there isn't a readable one.

    `translate` and `load_v1` are mutagen's defaults and we want both: the first
    upgrades ID3v2.2's three-letter frames (`TT2`, `PIC`) to the v2.4 names used
    above, so a 2002-era file reads through the same code as a modern one, and
    the second falls back to the 128 bytes at the end of the file when there is
    no v2 tag at all. This library is YouTube rips -- it has both.
    """
    try:
        return ID3(str(path))
    except (MutagenError, OSError, ValueError):
        # MutagenError covers no-header and malformed; OSError covers the file
        # going away or being unreadable. ValueError is the belt-and-braces
        # case -- a truncated frame can surface as one from deep inside the
        # parser, and a tag reader that raises would take out the whole scan.
        return None


def _text(tag: ID3, frame_id: str) -> str:
    """The first value of a text frame, stripped. `""` when there's nothing.

    Whitespace normalises to empty on purpose: a frame holding `"   "` is a
    frame the tagger wrote and meant nothing by, and if it survived as truthy
    the filename fallback would never fire and the row would render blank.
    """
    frame = tag.get(frame_id)
    if frame is None:
        return ""
    try:
        values = list(frame.text)
    except (AttributeError, TypeError):
        return ""
    return str(values[0]).strip() if values else ""
