"""Scanning must never raise -- the app degrades to 'no music', never crashes."""

from __future__ import annotations

import pytest

from mp3player.core.library import ScanResult, scan_folder
from mp3player.core.models import Track

ID3V2 = b"ID3\x04\x00\x00\x00\x00"
MP4_DASH = b"\x00\x00\x00\x18ftypdash"


def make_mp3(folder, name: str) -> None:
    (folder / name).write_bytes(ID3V2 + b"\x00" * 64)


def make_fake_mp3(folder, name: str) -> None:
    """A file named .mp3 that is really an MP4 -- 8% of the target library."""
    (folder / name).write_bytes(MP4_DASH + b"\x00" * 64)


def test_finds_mp3s(tmp_path) -> None:
    make_mp3(tmp_path, "b.mp3")
    make_mp3(tmp_path, "a.mp3")
    result = scan_folder(tmp_path)
    assert [t.title for t in result.tracks] == ["a", "b"]
    assert result.skipped == ()


def test_sorts_case_insensitively(tmp_path) -> None:
    for name in ("Zebra.mp3", "apple.mp3", "Banana.mp3"):
        make_mp3(tmp_path, name)
    result = scan_folder(tmp_path)
    assert [t.title for t in result.tracks] == ["apple", "Banana", "Zebra"]


def test_skips_files_that_lie_about_their_format(tmp_path) -> None:
    make_mp3(tmp_path, "real.mp3")
    make_fake_mp3(tmp_path, "fake.mp3")
    result = scan_folder(tmp_path)
    assert [t.title for t in result.tracks] == ["real"]
    assert [p.name for p in result.skipped] == ["fake.mp3"]


def test_ignores_other_extensions(tmp_path) -> None:
    make_mp3(tmp_path, "keep.mp3")
    (tmp_path / "cover.jpg").write_bytes(b"\xff\xd8\xff")
    (tmp_path / "notes.txt").write_text("hello")
    result = scan_folder(tmp_path)
    assert [t.title for t in result.tracks] == ["keep"]
    assert result.skipped == ()


def test_extension_match_is_case_insensitive(tmp_path) -> None:
    make_mp3(tmp_path, "SHOUTY.MP3")
    assert [t.title for t in scan_folder(tmp_path).tracks] == ["SHOUTY"]


def test_does_not_recurse(tmp_path) -> None:
    """Top level only -- subfolder recursion is post-v1."""
    make_mp3(tmp_path, "top.mp3")
    nested = tmp_path / "Album"
    nested.mkdir()
    make_mp3(nested, "buried.mp3")
    assert [t.title for t in scan_folder(tmp_path).tracks] == ["top"]


def test_ignores_directories_named_like_tracks(tmp_path) -> None:
    (tmp_path / "weird.mp3").mkdir()
    assert scan_folder(tmp_path).tracks == ()


@pytest.mark.parametrize("bad", ["missing_folder", None])
def test_degrades_gracefully(tmp_path, bad) -> None:
    folder = None if bad is None else tmp_path / bad
    result = scan_folder(folder)
    assert result == ScanResult()
    assert not result


def test_a_file_where_a_folder_was_expected(tmp_path) -> None:
    target = tmp_path / "not-a-folder.txt"
    target.write_text("hi")
    assert scan_folder(target) == ScanResult()


def test_empty_folder(tmp_path) -> None:
    assert not scan_folder(tmp_path)
    assert len(scan_folder(tmp_path)) == 0


def test_result_supports_len_and_truthiness(tmp_path) -> None:
    make_mp3(tmp_path, "one.mp3")
    result = scan_folder(tmp_path)
    assert len(result) == 1
    assert result


def test_track_keeps_full_path(tmp_path) -> None:
    make_mp3(tmp_path, "song.mp3")
    track = scan_folder(tmp_path).tracks[0]
    assert track == Track(path=tmp_path / "song.mp3", title="song")
    assert str(track) == "song"
