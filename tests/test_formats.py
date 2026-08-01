"""Format sniffing must be right: it decides what shows up in the library."""

from __future__ import annotations

import pytest

from mp3player.core import formats

# Real leading bytes, taken from actual files during the Batch 0 survey.
ID3V2 = b"ID3\x04\x00\x00\x00\x00"
RAW_FRAME = b"\xff\xfb\x90\x64\x00\x00\x00\x00"
MP4_DASH = b"\x00\x00\x00\x18ftypdash"
OGG = b"OggS\x00\x02\x00\x00"
FLAC = b"fLaC\x00\x00\x00\x22"
WAV = b"RIFF\x24\x08\x00\x00WAVE"


@pytest.mark.parametrize(
    ("head", "expected"),
    [
        (ID3V2, "mp3"),
        (RAW_FRAME, "mp3"),
        (MP4_DASH, "mp4"),
        (OGG, "ogg"),
        (FLAC, "flac"),
        (WAV, "wav"),
        (b"", formats.UNKNOWN),
        (b"nonsense----", formats.UNKNOWN),
    ],
)
def test_identify(head: bytes, expected: str) -> None:
    assert formats.identify(head) == expected


def test_identify_handles_short_input() -> None:
    """A one-byte file must not raise on the frame-sync index check."""
    assert formats.identify(b"\xff") == formats.UNKNOWN


def test_sniff_reads_from_disk(tmp_path) -> None:
    good = tmp_path / "song.mp3"
    good.write_bytes(ID3V2 + b"\x00" * 64)
    assert formats.sniff(good) == "mp3"
    assert formats.is_mp3(good)


def test_sniff_sees_through_a_lying_extension(tmp_path) -> None:
    """The whole point: an MP4 named .mp3 is still an MP4."""
    liar = tmp_path / "youtube-download.mp3"
    liar.write_bytes(MP4_DASH + b"\x00" * 64)
    assert formats.sniff(liar) == "mp4"
    assert not formats.is_mp3(liar)


def test_sniff_missing_file_is_unreadable(tmp_path) -> None:
    assert formats.sniff(tmp_path / "nope.mp3") == formats.UNREADABLE
    assert not formats.is_mp3(tmp_path / "nope.mp3")
