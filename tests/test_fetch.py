"""The half of the download feature that is a pure function of its input.

Nothing here starts a process or opens a socket. What is being pinned is the
part that would otherwise only be exercised by a real download against a real
network: the argv the app hands yt-dlp, and its ability to make sense of lines
that come back malformed, which for a search over the open internet is normal
rather than exceptional.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mp3player.core import fetch
from mp3player.core.fetch import (
    NO_FFMPEG,
    NO_YTDLP,
    Result,
    Tools,
    download_argv,
    find_tools,
    parse_filepath,
    parse_progress,
    parse_result,
    search_argv,
)

YTDLP = Path("C:/tools/yt-dlp.exe")
FFMPEG = Path("C:/tools/ffmpeg.exe")
BOTH = Tools(ytdlp=YTDLP, ffmpeg=FFMPEG)


def dump_json(**fields) -> str:
    """One line of what `--dump-json --flat-playlist` actually emits."""
    return json.dumps(fields)


# -- Tools -----------------------------------------------------------------


def test_both_present_is_truthy() -> None:
    assert BOTH
    assert BOTH.missing is None


def test_missing_names_ytdlp_first() -> None:
    """When both are gone, say the one you have to install to get anywhere.

    Naming two tools in a status line that has to fit at 720 px is how neither
    gets read.
    """
    assert Tools().missing == NO_YTDLP
    assert Tools(ffmpeg=FFMPEG).missing == NO_YTDLP
    assert Tools(ytdlp=YTDLP).missing == NO_FFMPEG
    assert not Tools(ytdlp=YTDLP)


# -- find_tools ------------------------------------------------------------
#
# PATH is emptied for both of these. Without that they would pass or fail
# depending on whether the machine running them happens to have yt-dlp
# installed, which is the same class of bug as the harness reading the user's
# saved theme -- a test whose answer depends on the room it is in.


def test_finds_tools_in_the_folder(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "nothing-here"))
    (tmp_path / "yt-dlp.exe").write_bytes(b"")
    (tmp_path / "ffmpeg.exe").write_bytes(b"")

    found = find_tools(tmp_path)

    assert found.ytdlp == tmp_path / "yt-dlp.exe"
    assert found.ffmpeg == tmp_path / "ffmpeg.exe"
    assert found


def test_absent_tools_are_reported_not_raised(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "nothing-here"))
    found = find_tools(tmp_path)
    assert found.ytdlp is None
    assert found.missing == NO_YTDLP


def test_one_tool_without_the_other(tmp_path, monkeypatch) -> None:
    """ffmpeg is the one people forget, and it is not optional."""
    monkeypatch.setenv("PATH", str(tmp_path / "nothing-here"))
    (tmp_path / "yt-dlp.exe").write_bytes(b"")
    assert find_tools(tmp_path).missing == NO_FFMPEG


def test_tools_dir_is_a_sibling_of_settings(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert fetch.tools_dir().parent == fetch.config_dir()


# -- parse_result ----------------------------------------------------------


def test_parses_a_search_hit() -> None:
    line = dump_json(id="abc123", title="Sandstorm", uploader="Darude", duration=225)
    assert parse_result(line) == Result("abc123", "Sandstorm", "Darude", 225.0)


def test_channel_stands_in_for_uploader() -> None:
    """Extractors fill one or the other, and search results carry either."""
    line = dump_json(id="a", title="t", channel="Some Channel")
    assert parse_result(line).uploader == "Some Channel"


def test_no_credit_at_all_is_blank_not_absent() -> None:
    result = parse_result(dump_json(id="a", title="t"))
    assert result.uploader == ""
    assert result.duration_s == 0.0


@pytest.mark.parametrize(
    "line",
    [
        "",
        "   ",
        "[youtube:search] Extracting URL",  # yt-dlp's own chatter on stdout
        "{not json at all",
        json.dumps([1, 2, 3]),  # valid JSON, wrong shape
        dump_json(title="no id"),
        dump_json(id="no title"),
        dump_json(id="", title="empty id"),
        dump_json(id="a", title="   "),  # a deleted video comes back like this
        dump_json(id=42, title="id is not a string"),
    ],
)
def test_junk_lines_are_none_never_exceptions(line: str) -> None:
    """A search that got nine good answers must not die on the tenth."""
    assert parse_result(line) is None


@pytest.mark.parametrize("duration", [None, "225", float("nan"), -5])
def test_unusable_durations_become_zero(duration) -> None:
    result = parse_result(dump_json(id="a", title="t", duration=duration))
    assert result is not None
    assert result.duration_s == 0.0


# -- parse_progress --------------------------------------------------------


def test_parses_progress() -> None:
    assert parse_progress(f"{fetch.PROGRESS_PREFIX}  42.3%") == pytest.approx(0.423)


def test_progress_is_clamped() -> None:
    """`_percent_str` is a display field and a re-estimating download overshoots."""
    assert parse_progress(f"{fetch.PROGRESS_PREFIX} 103.0%") == 1.0
    assert parse_progress(f"{fetch.PROGRESS_PREFIX} -2.0%") == 0.0


@pytest.mark.parametrize(
    "line",
    [
        "[download] 42.3% of 4MiB",  # the human bar, which we deliberately ignore
        f"{fetch.PROGRESS_PREFIX} N/A%",  # before the size is known
        f"{fetch.PROGRESS_PREFIX} ",
        "",
    ],
)
def test_non_progress_lines_are_none(line: str) -> None:
    assert parse_progress(line) is None


# -- parse_filepath --------------------------------------------------------


def test_parses_the_finished_path() -> None:
    line = f"{fetch.FILE_PREFIX} D:/Music/Sandstorm.mp3"
    assert parse_filepath(line) == Path("D:/Music/Sandstorm.mp3")


def test_a_title_with_spaces_survives() -> None:
    """The path is the rest of the line, not its first token."""
    line = f"{fetch.FILE_PREFIX} D:/Music/Some Long Song Name.mp3"
    assert parse_filepath(line) == Path("D:/Music/Some Long Song Name.mp3")


@pytest.mark.parametrize("line", ["", "Deleting original file", f"{fetch.FILE_PREFIX}  "])
def test_non_path_lines_are_none(line: str) -> None:
    assert parse_filepath(line) is None


# -- the argv --------------------------------------------------------------


def test_search_argv_carries_the_query_and_the_count() -> None:
    argv = search_argv(BOTH, "sandstorm", limit=7)
    assert argv[0] == str(YTDLP)
    assert "ytsearch7:sandstorm" in argv
    assert "--dump-json" in argv and "--flat-playlist" in argv


def test_a_query_that_looks_like_a_flag_is_not_one() -> None:
    """It is the tail of `ytsearchN:`, so there is no argument starting with `-`."""
    argv = search_argv(BOTH, "--version")
    assert argv[-1] == f"ytsearch{fetch.SEARCH_LIMIT}:--version"
    assert not argv[-1].startswith("-")


def test_search_limit_has_a_floor() -> None:
    assert "ytsearch1:x" in search_argv(BOTH, "x", limit=0)


def test_download_argv_targets_the_folder_and_the_id() -> None:
    folder = Path("D:/Music")
    argv = download_argv(BOTH, "abc123", folder)
    assert argv[-1] == "abc123"
    assert argv[-2] == "--"  # so an id starting with a dash stays an id
    # `str(folder)`, not the literal it was written as: a `Path` renders with
    # backslashes on Windows, and yt-dlp is handed the native spelling.
    assert argv[argv.index("--paths") + 1] == str(folder)
    assert argv[argv.index("--ffmpeg-location") + 1] == str(FFMPEG)


def test_download_converts_to_mp3() -> None:
    """Not decoration: libsndfile reads MP3 and nothing else that YouTube serves."""
    argv = download_argv(BOTH, "a", Path("D:/Music"))
    assert "--extract-audio" in argv
    assert argv[argv.index("--audio-format") + 1] == "mp3"


def test_print_is_paired_with_the_flags_that_undo_it() -> None:
    """`--print` implies `--quiet --simulate`, which would download nothing.

    The pairing is the whole reason these three flags are worth a test: drop
    `--no-simulate` and the feature silently stops downloading, drop
    `--progress` and it downloads with no progress. Both look like tidying.
    """
    argv = download_argv(BOTH, "a", Path("D:/Music"))
    assert "--print" in argv
    assert "--no-simulate" in argv
    assert "--progress" in argv


def test_download_forces_utf8_output() -> None:
    """Without this, `--print` drops characters and reports a path that isn't there.

    Found on a real download: a title containing a colon becomes a fullwidth
    `：` in the filename, and plain `--print` emitted the path with that
    character *removed*. The file existed; the one the app was told about did
    not. Pinned because a lone encoding flag reads like superstition.
    """
    assert "UTF-8" in download_argv(BOTH, "a", Path("D:/Music"))


def test_search_does_not_need_the_encoding_flag() -> None:
    """`--dump-json` is ASCII on the wire, so the asymmetry above is deliberate.

    Stated as a test rather than only as a comment so that "make the two argv
    builders consistent" is a change somebody has to argue with.
    """
    argv = search_argv(BOTH, "x")
    assert "--dump-json" in argv
    assert "--encoding" not in argv


def test_argv_refuses_to_be_built_without_the_tools() -> None:
    """Fail where the mistake is, not twenty seconds later inside a process."""
    with pytest.raises(ValueError):
        search_argv(Tools(), "x")
    with pytest.raises(ValueError):
        download_argv(Tools(ytdlp=YTDLP), "a", Path("D:/Music"))
