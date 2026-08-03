"""A corrupt or hand-edited settings file must never stop the app starting."""

from __future__ import annotations

import json

import pytest

from mp3player.core import settings as s
from mp3player.core.settings import Settings


@pytest.fixture
def path(tmp_path):
    return tmp_path / "settings.json"


def test_round_trip(path) -> None:
    original = Settings(music_folder=path.parent / "Music", volume=0.5, speed=1.3)
    assert s.save(original, path)
    assert s.load(path) == original


def test_defaults_when_file_missing(path) -> None:
    assert s.load(path) == Settings()


def test_defaults_when_file_is_corrupt(path) -> None:
    path.write_text("{not json at all")
    assert s.load(path) == Settings()


def test_a_byte_order_mark_does_not_wipe_the_settings(path) -> None:
    """Notepad and `Out-File -Encoding utf8` both write one.

    Read as plain `utf-8` the BOM reaches `json.loads` as a stray character, the
    file counts as corrupt, and every setting quietly reverts -- which the user
    experiences as the app forgetting their music folder for no reason. Found
    by hand-editing this file on the way to testing the packaged exe.
    """
    original = Settings(music_folder=path.parent / "Music", volume=0.5, speed=1.3)
    path.write_text(json.dumps(original.to_dict()), encoding="utf-8-sig")
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")  # it really is there
    assert s.load(path) == original


def test_we_still_write_without_a_bom(path) -> None:
    s.save(Settings(), path)
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf")


@pytest.mark.parametrize("payload", ["null", '"a string"', "[1, 2, 3]", "42"])
def test_defaults_when_json_is_not_an_object(path, payload) -> None:
    path.write_text(payload)
    assert s.load(path) == Settings()


def test_one_bad_field_does_not_discard_the_others(path) -> None:
    """Independent validation -- a junk volume shouldn't lose the folder."""
    folder = path.parent / "Music"
    path.write_text(json.dumps({"music_folder": str(folder), "volume": "loud"}))
    loaded = s.load(path)
    assert loaded.music_folder == folder
    assert loaded.volume == s.DEFAULT_VOLUME


def test_unknown_keys_are_ignored(path) -> None:
    path.write_text(json.dumps({"volume": 0.3, "shuffle": True, "future": [1]}))
    assert s.load(path).volume == 0.3


@pytest.mark.parametrize(
    ("stored", "expected"),
    [(5.0, s.MAX_VOLUME), (-2.0, s.MIN_VOLUME), (0.25, 0.25)],
)
def test_volume_is_clamped(path, stored, expected) -> None:
    path.write_text(json.dumps({"volume": stored}))
    assert s.load(path).volume == expected


@pytest.mark.parametrize(
    ("stored", "expected"),
    [(99.0, s.MAX_SPEED), (0.01, s.MIN_SPEED), (1.3, 1.3)],
)
def test_speed_is_clamped(path, stored, expected) -> None:
    """A hand-edited 99x would blow through the end of the sample array."""
    path.write_text(json.dumps({"speed": stored}))
    assert s.load(path).speed == expected


@pytest.mark.parametrize("junk", ["nan", "null", '""', "{}"])
def test_nonsense_numbers_fall_back(path, junk) -> None:
    path.write_text('{"speed": %s}' % junk)
    assert s.load(path).speed == s.DEFAULT_SPEED


@pytest.mark.parametrize("stored", ["", "   ", None, 42])
def test_blank_or_wrong_typed_folder_becomes_none(path, stored) -> None:
    path.write_text(json.dumps({"music_folder": stored}))
    assert s.load(path).music_folder is None


def test_theme_round_trips(path) -> None:
    s.save(Settings(theme="Ember"), path)
    assert s.load(path).theme == "Ember"


def test_a_file_without_a_theme_gets_the_default(path) -> None:
    """Every settings file written before Batch 10 is one of these."""
    path.write_text(json.dumps({"volume": 0.3}))
    assert s.load(path).theme == s.DEFAULT_THEME


@pytest.mark.parametrize("junk", ["", "   ", None, 42, [], {}])
def test_a_blank_or_wrong_typed_theme_falls_back(path, junk) -> None:
    path.write_text(json.dumps({"theme": junk}))
    assert s.load(path).theme == s.DEFAULT_THEME


def test_an_unrecognised_theme_name_survives(path) -> None:
    """`core` has no list to check against, and inventing one would be worse.

    A file written by a later build with more presets in it must not come back
    as the default and then get *saved* that way -- that turns "this build
    doesn't know that name" into "your setting is gone". `ui` clamps it when it
    applies it, which is where the list actually lives.
    """
    path.write_text(json.dumps({"theme": "Nebula"}))
    assert s.load(path).theme == "Nebula"


def test_save_creates_missing_directories(tmp_path) -> None:
    nested = tmp_path / "a" / "b" / "settings.json"
    assert s.save(Settings(volume=0.42), nested)
    assert s.load(nested).volume == 0.42


def test_save_leaves_no_temp_file_behind(path) -> None:
    s.save(Settings(), path)
    assert [p.name for p in path.parent.iterdir()] == ["settings.json"]


def test_save_failure_is_reported_not_raised(tmp_path) -> None:
    """Losing settings is not worth crashing over."""
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file, not a directory")
    assert s.save(Settings(), blocker / "settings.json") is False


def test_existing_settings_survive_a_failed_write(path, monkeypatch) -> None:
    """The atomic rename is the point: a failed write leaves the old file intact."""
    s.save(Settings(volume=0.9), path)

    def disk_full(src, dst):
        raise OSError("no space left on device")

    monkeypatch.setattr(s.os, "replace", disk_full)

    assert s.save(Settings(volume=0.1), path) is False
    assert s.load(path).volume == 0.9  # the old value, uncorrupted
    assert [p.name for p in path.parent.iterdir()] == ["settings.json"]


def test_config_path_lives_under_appdata(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert s.config_path() == tmp_path / s.APP_NAME / "settings.json"


def test_config_path_falls_back_without_appdata(monkeypatch) -> None:
    monkeypatch.delenv("APPDATA", raising=False)
    assert s.config_path().parts[-3:] == (".config", s.APP_NAME, "settings.json")
