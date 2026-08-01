"""Identify audio files by their magic bytes.

Never trust the extension. Roughly 8% of the `.mp3` files in the target library
are actually MP4/AAC -- YouTube downloads saved with the wrong suffix -- and
libsndfile cannot decode those. See the decisions log in CLAUDE.md.

Pure byte inspection: no numpy, no soundfile, no decoding. Both `library.py`
(deciding what to list) and `decode.py` (deciding how to open) rely on it.
"""

from __future__ import annotations

from pathlib import Path

# Enough for every signature below; `ftyp` sits at offset 4.
_HEADER_BYTES = 12

MP3 = "mp3"
UNREADABLE = "unreadable"
UNKNOWN = "unknown"


def sniff(path: Path) -> str:
    """Return a short format name for `path`.

    Returns `UNREADABLE` if the file can't be opened and `UNKNOWN` if the
    header matches nothing we recognise. Never raises.
    """
    try:
        with open(path, "rb") as handle:
            head = handle.read(_HEADER_BYTES)
    except OSError:
        return UNREADABLE
    return identify(head)


def identify(head: bytes) -> str:
    """Classify a file from its leading bytes."""
    if head[:3] == b"ID3":
        return MP3
    if len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:
        return MP3  # raw MPEG frame sync -- an mp3 with no ID3v2 tag
    if head[4:8] == b"ftyp":
        return "mp4"
    if head[:4] == b"OggS":
        return "ogg"
    if head[:4] == b"fLaC":
        return "flac"
    if head[:4] == b"RIFF":
        return "wav"
    return UNKNOWN


def is_mp3(path: Path) -> bool:
    return sniff(path) == MP3
