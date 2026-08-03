"""Scanning must never raise -- the app degrades to 'no music', never crashes."""

from __future__ import annotations

import pytest
from mutagen.id3 import ID3, TALB, TIT2, TPE1

from mp3player.core import library
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
    assert result.tracks == () and result.skipped == ()
    assert not result


def test_a_file_where_a_folder_was_expected(tmp_path) -> None:
    target = tmp_path / "not-a-folder.txt"
    target.write_text("hi")
    result = scan_folder(target)
    assert result.tracks == ()
    # Not a folder at all, so from the user's side there is no such folder --
    # the same sentence a deleted one gets, rather than "can't read it".
    assert result.error == library.MISSING


def test_empty_folder(tmp_path) -> None:
    assert not scan_folder(tmp_path)
    assert len(scan_folder(tmp_path)) == 0


# -- why a scan came back empty ------------------------------------------
#
# The distinction the UI needs: nothing chosen yet, chosen and now gone, and a
# perfectly good folder with no music in it are three different screens.


def test_no_folder_chosen_is_its_own_reason() -> None:
    assert scan_folder(None).error == library.NO_FOLDER


def test_a_folder_that_is_not_there_reports_missing(tmp_path) -> None:
    assert scan_folder(tmp_path / "gone").error == library.MISSING


def test_an_empty_folder_is_not_an_error(tmp_path) -> None:
    # It was read, successfully, and there was nothing in it. Nothing is wrong.
    assert scan_folder(tmp_path).error is None


def test_a_folder_with_tracks_is_not_an_error(tmp_path) -> None:
    make_mp3(tmp_path, "one.mp3")
    assert scan_folder(tmp_path).error is None


def test_a_folder_of_only_skipped_files_is_not_an_error(tmp_path) -> None:
    # We reached it and read it; the files in it are the problem, and `skipped`
    # is already how that gets reported.
    (tmp_path / "fake.mp3").write_bytes(b"\x00\x00\x00\x18ftypmp42")
    result = scan_folder(tmp_path)
    assert result.error is None
    assert len(result.skipped) == 1


def test_result_defaults_to_no_error() -> None:
    # The default matters: a result with tracks in it is always error-free, and
    # anything constructing one by hand should get that without saying so.
    assert ScanResult().error is None


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


# -- tags ------------------------------------------------------------------
#
# The rule is one line: the tag names the track, and the filename is what
# happens when it can't. Everything here is a way of the tag not being there.


def make_tagged_mp3(folder, name: str, **frames) -> None:
    tag = ID3()
    if "title" in frames:
        tag.add(TIT2(encoding=3, text=frames["title"]))
    if "artist" in frames:
        tag.add(TPE1(encoding=3, text=frames["artist"]))
    if "album" in frames:
        tag.add(TALB(encoding=3, text=frames["album"]))
    tag.save(str(folder / name))


def test_a_tagged_track_is_named_by_its_tag(tmp_path) -> None:
    make_tagged_mp3(
        tmp_path, "01 - track.mp3", title="Roygbiv", artist="Boards of Canada"
    )
    track = scan_folder(tmp_path).tracks[0]
    assert track.title == "Roygbiv"
    assert track.artist == "Boards of Canada"


def test_an_untagged_track_falls_back_to_the_filename(tmp_path) -> None:
    make_mp3(tmp_path, "Some Artist - Some Song.mp3")
    track = scan_folder(tmp_path).tracks[0]
    assert track.title == "Some Artist - Some Song"
    assert track.artist == ""


def test_a_blank_title_frame_falls_back_too(tmp_path) -> None:
    """A YouTube rip with an empty TIT2 must not render as a blank row."""
    make_tagged_mp3(tmp_path, "real name.mp3", title="  ", artist="Somebody")
    track = scan_folder(tmp_path).tracks[0]
    assert track.title == "real name"
    assert track.artist == "Somebody"


def test_the_sort_is_still_by_filename_not_by_title(tmp_path) -> None:
    """Tags change what a row says, never what order the rows are in -- the
    on-disk order is the one thing about the list that has always been stable."""
    make_tagged_mp3(tmp_path, "a.mp3", title="Zebra")
    make_tagged_mp3(tmp_path, "z.mp3", title="Apple")
    assert [t.title for t in scan_folder(tmp_path).tracks] == ["Zebra", "Apple"]


def test_tags_off_names_everything_by_filename(tmp_path) -> None:
    make_tagged_mp3(tmp_path, "01 - track.mp3", title="Roygbiv", artist="BoC")
    track = scan_folder(tmp_path, tags=False).tracks[0]
    assert track == Track(path=tmp_path / "01 - track.mp3", title="01 - track")


def test_an_unreadable_tag_costs_a_title_not_the_scan(tmp_path) -> None:
    """The whole point of the never-raises contract, one layer up: a file with a
    broken tag still appears in the list, under its filename."""
    (tmp_path / "broken.mp3").write_bytes(b"ID3\x04\x00\x00\x00\x00\x7f\x7f" + b"\xff\xfb")
    result = scan_folder(tmp_path)
    assert [t.title for t in result.tracks] == ["broken"]
    assert result.error is None
