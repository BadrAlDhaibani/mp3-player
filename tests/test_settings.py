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
    # `shuffle` used to be one of the junk keys here, which was fine right up
    # until Batch 18 made it a real one. A key this build knows is not a test of
    # ignoring keys it doesn't.
    path.write_text(json.dumps({"volume": 0.3, "crossfade": True, "future": [1]}))
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
    [(99.0, s.MAX_SPEED), (0.01, s.MIN_SPEED), (1.3, 1.3), (0.75, 0.75)],
)
def test_speed_is_clamped(path, stored, expected) -> None:
    """A hand-edited 99x would blow through the end of the sample array.

    `0.75` is the Batch 19 case: it used to be below the floor and came back as
    0.80, and now it is inside the range and survives. Worth a row of its own
    rather than trusting the two ends -- a clamp is exactly the thing that goes
    on passing its boundary tests while the boundary is in the wrong place.
    """
    path.write_text(json.dumps({"speed": stored}))
    assert s.load(path).speed == expected


def test_daycore_reaches_070() -> None:
    """The slow end of the slider, named once outside `settings.py` itself.

    Not a tautology: `ui/theme.py` derives where every palette's resting colour
    is knotted from this constant, so moving it moves five ramps. That is fine
    and deliberate -- it is what stops them desyncing -- but it should not
    happen by accident, and the failure would otherwise be a colour.
    """
    assert s.DAYCORE_SPEED == 0.70
    assert (s.MIN_SPEED, s.MAX_SPEED) == (s.DAYCORE_SPEED, s.NIGHTCORE_SPEED)


@pytest.mark.parametrize("junk", ["nan", "null", '""', "{}"])
def test_nonsense_numbers_fall_back(path, junk) -> None:
    path.write_text(f'{{"speed": {junk}}}')
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


def test_shuffle_and_repeat_round_trip(path) -> None:
    s.save(Settings(shuffle=True, repeat="one"), path)
    loaded = s.load(path)
    assert loaded.shuffle is True
    assert loaded.repeat == "one"


def test_a_file_without_the_modes_gets_the_defaults(path) -> None:
    """Every settings file written before Batch 18 is one of these.

    The default repeat is `all` rather than `off` because that is what the app
    has always done -- running off the last track loops to the first -- so an
    upgrade must not quietly change how somebody's player behaves.
    """
    path.write_text(json.dumps({"volume": 0.3}))
    loaded = s.load(path)
    assert loaded.shuffle == s.DEFAULT_SHUFFLE
    assert loaded.repeat == s.DEFAULT_REPEAT == "all"


@pytest.mark.parametrize("junk", [1, 0, "true", "", None, [], {}])
def test_a_wrong_typed_shuffle_falls_back(path, junk) -> None:
    """`1` and `"true"` are what a hand-edited file contains, and guessing at
    them is how a setting comes back as something nobody typed."""
    path.write_text(json.dumps({"shuffle": junk}))
    assert s.load(path).shuffle is s.DEFAULT_SHUFFLE


@pytest.mark.parametrize("junk", ["", "   ", None, 42, [], {}])
def test_a_blank_or_wrong_typed_repeat_falls_back(path, junk) -> None:
    path.write_text(json.dumps({"repeat": junk}))
    assert s.load(path).repeat == s.DEFAULT_REPEAT


def test_an_unrecognised_repeat_mode_survives(path) -> None:
    """Same seam as the theme: no list here, so nothing to fail against.

    A mode a later build knows must come back out of this build unchanged
    rather than being written back as the default. `ui/controller.py` owns the
    list and clamps it at the point of use.
    """
    path.write_text(json.dumps({"repeat": "shuffle-album"}))
    assert s.load(path).repeat == "shuffle-album"


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
