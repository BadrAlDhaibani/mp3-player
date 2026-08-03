"""Tag reading must never raise -- a bad tag costs you a title, not the scan."""

from __future__ import annotations

from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1

from mp3player.core.tags import Tags, read_art, read_tags

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32  # enough to be distinguishable
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def tagged(path, **frames) -> object:
    """Write a real ID3v2.4 tag onto `path`, creating the file if need be."""
    tag = ID3()
    if "title" in frames:
        tag.add(TIT2(encoding=3, text=frames["title"]))
    if "artist" in frames:
        tag.add(TPE1(encoding=3, text=frames["artist"]))
    if "album" in frames:
        tag.add(TALB(encoding=3, text=frames["album"]))
    for picture in frames.get("pictures", ()):
        tag.add(picture)
    tag.save(str(path))
    return path


def cover(data: bytes = JPEG, kind: int = 3, mime: str = "image/jpeg") -> APIC:
    return APIC(encoding=3, mime=mime, type=kind, desc="", data=data)


# -- text ------------------------------------------------------------------


def test_reads_the_three_frames_we_show(tmp_path) -> None:
    path = tagged(
        tmp_path / "song.mp3",
        title="Xtal",
        artist="Aphex Twin",
        album="Selected Ambient Works 85-92",
    )
    assert read_tags(path) == Tags(
        title="Xtal", artist="Aphex Twin", album="Selected Ambient Works 85-92"
    )


def test_absent_frames_are_empty_not_missing(tmp_path) -> None:
    path = tagged(tmp_path / "song.mp3", title="Only a title")
    tags = read_tags(path)
    assert tags.title == "Only a title"
    assert tags.artist == ""
    assert tags.album == ""


def test_a_file_with_no_tag_at_all_reads_empty(tmp_path) -> None:
    bare = tmp_path / "untagged.mp3"
    bare.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 256)  # raw MPEG sync
    assert read_tags(bare) == Tags()


def test_whitespace_is_the_same_as_absent(tmp_path) -> None:
    """Otherwise it reads as truthy, the filename fallback never fires, and the
    row renders blank -- which looks like a bug in the list, not in the file."""
    path = tagged(tmp_path / "song.mp3", title="   ", artist="\t\n")
    assert read_tags(path) == Tags()


def test_surrounding_whitespace_is_trimmed(tmp_path) -> None:
    path = tagged(tmp_path / "song.mp3", title="  Windowlicker  ")
    assert read_tags(path).title == "Windowlicker"


def test_a_multi_value_frame_takes_the_first(tmp_path) -> None:
    path = tagged(tmp_path / "song.mp3", artist=["Boards of Canada", "BoC"])
    assert read_tags(path).artist == "Boards of Canada"


def test_garbage_is_empty_tags_not_an_exception(tmp_path) -> None:
    junk = tmp_path / "junk.mp3"
    junk.write_bytes(b"\xde\xad\xbe\xef" * 64)
    assert read_tags(junk) == Tags()


def test_a_truncated_tag_is_empty_tags(tmp_path) -> None:
    """An ID3 header promising far more bytes than the file actually holds."""
    lying = tmp_path / "truncated.mp3"
    lying.write_bytes(b"ID3\x04\x00\x00\x00\x00\x7f\x7f" + b"\x00" * 16)
    assert read_tags(lying) == Tags()


def test_a_missing_file_is_empty_tags(tmp_path) -> None:
    assert read_tags(tmp_path / "nope.mp3") == Tags()


def test_something_that_is_not_an_mp3_is_empty_tags(tmp_path) -> None:
    wav = tmp_path / "tone.wav"
    wav.write_bytes(b"RIFF" + b"\x00" * 64)
    assert read_tags(wav) == Tags()


def test_accepts_a_string_path(tmp_path) -> None:
    path = tagged(tmp_path / "song.mp3", title="Rhubarb")
    assert read_tags(str(path)).title == "Rhubarb"


def test_id3v22_frames_read_through_the_same_names(tmp_path) -> None:
    """The headline reason for a real tag library: a 2002-era file writes `TT2`
    where a modern one writes `TIT2`, and this library is full of both."""
    body = b"\x00" + b"Fingerbib"  # latin-1, per the v2.2 encoding byte
    frame = b"TT2" + len(body).to_bytes(3, "big") + body
    size = bytes((0, 0, (len(frame) >> 7) & 0x7F, len(frame) & 0x7F))  # syncsafe

    old = tmp_path / "ancient.mp3"
    old.write_bytes(b"ID3\x02\x00\x00" + size + frame + b"\xff\xfb\x90\x00")
    assert read_tags(old).title == "Fingerbib"


# -- truthiness ------------------------------------------------------------


def test_empty_tags_are_falsy() -> None:
    assert not Tags()


def test_any_field_makes_tags_truthy() -> None:
    assert Tags(album="Music Has the Right to Children")


# -- art -------------------------------------------------------------------


def test_reads_the_embedded_cover(tmp_path) -> None:
    path = tagged(tmp_path / "song.mp3", title="Xtal", pictures=[cover()])
    assert read_art(path) == JPEG


def test_no_picture_is_none_not_empty_bytes(tmp_path) -> None:
    path = tagged(tmp_path / "song.mp3", title="Xtal")
    assert read_art(path) is None


def test_the_front_cover_wins_over_the_other_images(tmp_path) -> None:
    path = tagged(
        tmp_path / "song.mp3",
        pictures=[cover(PNG, kind=4, mime="image/png"), cover(JPEG, kind=3)],
    )
    assert read_art(path) == JPEG


def test_an_untyped_picture_is_still_used(tmp_path) -> None:
    """One image and no picture-type byte worth trusting is the common case."""
    path = tagged(tmp_path / "song.mp3", pictures=[cover(PNG, kind=0, mime="image/png")])
    assert read_art(path) == PNG


def test_the_bytes_come_back_untouched(tmp_path) -> None:
    """No decoding here -- whatever the tagger wrote is what `ui/` gets."""
    path = tagged(tmp_path / "song.mp3", pictures=[cover(PNG, mime="image/png")])
    assert read_art(path) == PNG


def test_an_empty_picture_frame_is_none(tmp_path) -> None:
    path = tagged(tmp_path / "song.mp3", pictures=[cover(b"")])
    assert read_art(path) is None


def test_art_from_a_file_with_no_tag_is_none(tmp_path) -> None:
    bare = tmp_path / "untagged.mp3"
    bare.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 256)
    assert read_art(bare) is None


def test_art_from_a_missing_file_is_none(tmp_path) -> None:
    assert read_art(tmp_path / "nope.mp3") is None


def test_art_from_garbage_is_none(tmp_path) -> None:
    junk = tmp_path / "junk.mp3"
    junk.write_bytes(b"\xde\xad\xbe\xef" * 64)
    assert read_art(junk) is None
