"""Finding a song online and fetching it as an MP3 -- the half that isn't Qt.

This module builds argument lists and parses lines. It does not run anything, it
does not open a socket, and it imports neither Qt nor `subprocess`: the process
is `ui/fetcher.py`'s business, because a download has to be driven by the event
loop and the only thing here that would need is a reason to be untestable.

**Why a subprocess at all, rather than `import yt_dlp`.** The audio callback is
Python and has a 10.7 ms deadline (see `core/audio/engine.py` and Batch 16 in
CLAUDE.md), so it competes for the GIL with every other line of Python in the
app -- including a worker thread, which is the version of this that looks safe
and is not. A separate process is scheduled by the OS on its own core and costs
the callback nothing. That is also why the app still has no `threading` import.

Two external tools, neither of them bundled:

* **yt-dlp** does the searching and the downloading.
* **ffmpeg** does the conversion, and is not optional. libsndfile decodes MP3
  and nothing else, so the m4a/opus that actually comes down the wire is a file
  this app cannot play -- and `core.library` would skip it on the magic-byte
  sniff without saying why, which is the failure this module exists to make
  legible instead.

Absence is reported as a bare token (`NO_YTDLP`, `NO_FFMPEG`) exactly the way
`library.MISSING` and `library.UNREADABLE` are: **`core` reports why, `ui` owns
the words.** There is one wording of "you need to install this" and it lives in
`ui/main_window.py` beside the other five.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from mp3player.core.settings import config_dir

# Why the feature can't run. Tokens, not sentences -- see the module docstring.
NO_YTDLP = "no_ytdlp"
NO_FFMPEG = "no_ffmpeg"

# How many results one search asks for. The column shows a handful at a time and
# a search that returns thirty is a scrolling exercise, not an answer.
SEARCH_LIMIT = 10

# yt-dlp writes progress and the finished path onto stdout among its own
# chatter, so both are prefixed with something no title will ever contain and
# nothing else emits. Parsing its human-readable progress bar instead is the
# obvious alternative and a bad one: that output is carriage-return animated,
# localised in places, and is not a contract it has ever promised to keep.
PROGRESS_PREFIX = "XMBDL"
FILE_PREFIX = "XMBFILE"

PROGRESS_TEMPLATE = f"download:{PROGRESS_PREFIX} %(progress._percent_str)s"
FILE_TEMPLATE = f"after_move:{FILE_PREFIX} %(filepath)s"


@dataclass(frozen=True, slots=True)
class Tools:
    """Where the two executables are, if they are anywhere.

    `None` rather than a sentinel path, so a caller that forgets to check gets a
    `TypeError` building its argv rather than a process that fails to start
    twenty seconds later with something unreadable in stderr.
    """

    ytdlp: Path | None = None
    ffmpeg: Path | None = None

    @property
    def missing(self) -> str | None:
        """Which tool is absent, or `None` if both are here.

        yt-dlp first when both are gone: it is the one you need to install to get
        anywhere at all, and naming two things at once in a status line that has
        to fit at 720 px is how neither gets read.
        """
        if self.ytdlp is None:
            return NO_YTDLP
        if self.ffmpeg is None:
            return NO_FFMPEG
        return None

    def __bool__(self) -> bool:
        return self.missing is None


def tools_dir() -> Path:
    """Where the app looks for tools it did not find on PATH.

    A sibling of `settings.json` and the log, for the reason the log is one: the
    app already owns that directory, already creates it, and it is already the
    path somebody gets told when they are asked to send a file in. A second
    location is a second thing to explain.
    """
    return config_dir() / "tools"


def _find_one(name: str, folder: Path) -> Path | None:
    """PATH first, then `folder`. `None` if it is in neither."""
    found = shutil.which(name)
    if found:
        return Path(found)
    # `shutil.which` against an explicit directory rather than a bare `exists`:
    # it is what applies PATHEXT, so this finds `yt-dlp.exe` from `yt-dlp` on
    # Windows and does not need a hard-coded suffix to do it.
    found = shutil.which(name, path=str(folder))
    return Path(found) if found else None


def find_tools(folder: Path | None = None) -> Tools:
    """Locate yt-dlp and ffmpeg. Never raises; absence is the ordinary answer.

    `folder` overrides `tools_dir()` and exists for the tests, which must not
    depend on what happens to be installed on the machine running them.
    """
    where = tools_dir() if folder is None else folder
    return Tools(ytdlp=_find_one("yt-dlp", where), ffmpeg=_find_one("ffmpeg", where))


@dataclass(frozen=True, slots=True)
class Result:
    """One search hit. The same shape as `Track`, and deliberately not a `Track`.

    A `Track` is a file on disk with a path, and everything above the controller
    treats it as one. This has no path because it is not here yet, and conflating
    the two is how something ends up trying to play a search result.

    `uploader` and `duration_s` default to empty and zero rather than `None` for
    the reason `Track.artist` does: absent and blank look the same on screen, and
    a consumer that had to tell them apart would be inventing a distinction.
    """

    video_id: str
    title: str
    uploader: str = ""
    duration_s: float = 0.0


def parse_result(line: str) -> Result | None:
    """One `--dump-json` line into a `Result`, or `None` if it isn't one.

    Never raises. yt-dlp interleaves its own notices with the JSON, entries come
    back with fields missing, and a deleted or private video can arrive as an
    entry with no title at all -- none of which is exceptional enough to stop a
    search that got nine other good answers.

    A hit needs an id and a title, because those are the two the app cannot
    invent: the id is what gets downloaded and the title is the whole of what the
    row says. Everything else is decoration and defaults.
    """
    line = line.strip()
    if not line.startswith("{"):
        return None
    try:
        raw = json.loads(line)
    except ValueError:
        return None
    if not isinstance(raw, dict):
        return None

    video_id = raw.get("id")
    title = raw.get("title")
    if not isinstance(video_id, str) or not video_id.strip():
        return None
    if not isinstance(title, str) or not title.strip():
        return None

    # `--flat-playlist` fills `channel` on some extractors and `uploader` on
    # others, and search results have been known to carry neither.
    uploader = ""
    for key in ("uploader", "channel"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            uploader = value.strip()
            break

    duration = raw.get("duration")
    seconds = float(duration) if isinstance(duration, (int, float)) else 0.0
    if seconds != seconds or seconds < 0:  # NaN, or a live stream reporting junk
        seconds = 0.0

    return Result(
        video_id=video_id.strip(),
        title=title.strip(),
        uploader=uploader,
        duration_s=seconds,
    )


def parse_progress(line: str) -> float | None:
    """A progress line as a fraction in 0..1, or `None` if it isn't one.

    Clamped rather than trusted: `_percent_str` is a display field, and a
    fragmented download can briefly report over 100 as it re-estimates.
    """
    line = line.strip()
    if not line.startswith(PROGRESS_PREFIX):
        return None
    body = line[len(PROGRESS_PREFIX) :].strip().rstrip("%").strip()
    try:
        percent = float(body)
    except ValueError:
        return None  # "N/A" before the size is known
    if percent != percent:
        return None
    return min(1.0, max(0.0, percent / 100.0))


def parse_filepath(line: str) -> Path | None:
    """The finished file's path, or `None` if this line isn't announcing one.

    Asked for rather than guessed at. yt-dlp owns the filename -- it sanitises
    the title against Windows' rules, resolves collisions and changes the
    extension during conversion -- so reconstructing it here would be a second
    implementation of somebody else's algorithm, silently wrong the first time a
    title contains a colon. This is the "verify the artifact, not the build log"
    convention applied to a download: the tool says what it wrote.
    """
    line = line.strip()
    if not line.startswith(FILE_PREFIX):
        return None
    body = line[len(FILE_PREFIX) :].strip()
    return Path(body) if body else None


def search_argv(tools: Tools, query: str, limit: int = SEARCH_LIMIT) -> list[str]:
    """The command that searches. One JSON object per line on stdout.

    `--flat-playlist` is what makes this quick: without it yt-dlp resolves every
    hit in full, which is ten round trips for a list nobody has picked from yet.

    The query cannot be read as an option however it starts, because it is not
    passed as its own argument -- it is the tail of `ytsearchN:`, which is not a
    flag. There is no shell anywhere in this, so there is nothing to quote.
    """
    if tools.ytdlp is None:
        raise ValueError("no yt-dlp; check Tools.missing before building an argv")
    return [
        str(tools.ytdlp),
        # A user's own yt-dlp.conf can set an output template, a format or a
        # download archive, any of which would change what these commands mean
        # under us. This one is not negotiable for the same reason the build
        # pins its dependencies.
        "--ignore-config",
        "--no-warnings",
        "--flat-playlist",
        # No `--encoding` here, unlike `download_argv`, and the asymmetry is
        # measured rather than an oversight: `--dump-json` emits JSON with
        # `ensure_ascii` on, so a line of it is **pure ASCII on the wire** and
        # every non-ASCII title arrives as `\uXXXX` escapes that `json.loads`
        # turns back. Verified against a search returning Japanese titles.
        "--dump-json",
        f"ytsearch{max(1, int(limit))}:{query}",
    ]


def download_argv(tools: Tools, video_id: str, folder: Path) -> list[str]:
    """The command that fetches one video into `folder` as an MP3.

    The flag combination is fussier than it looks and each half needs the other:
    `--print` implies `--quiet --simulate`, so without `--no-simulate` this
    downloads nothing at all, and without `--progress` the quiet it also implies
    swallows every progress line. Both are here to buy back what `--print` took.
    """
    if tools.ytdlp is None or tools.ffmpeg is None:
        raise ValueError("tools missing; check Tools.missing before building an argv")
    return [
        str(tools.ytdlp),
        "--ignore-config",
        # **`--print` silently drops every character the console codepage cannot
        # hold, and this is the flag that stops it.** Found by downloading a
        # track whose title contains a colon: Windows forbids `:` in a filename
        # so yt-dlp sanitises it to a fullwidth `：`, and the path it then
        # printed came back with that character *missing entirely* -- not
        # replaced, removed -- so the file the app was told about did not exist.
        # `PYTHONIOENCODING=utf-8` in the child's environment does **not** fix
        # it; this does. Nothing here is affected by the console the app was
        # launched from, which is the point.
        "--encoding", "UTF-8",
        # A search hit can be a video that also belongs to a playlist, and
        # without this yt-dlp would happily fetch the other ninety.
        "--no-playlist",
        "--no-overwrites",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        # The app reads ID3 and cover art (Batch 8) and would otherwise show a
        # row named after a YouTube title with no artist and no picture.
        "--embed-metadata",
        "--embed-thumbnail",
        # Point it at the ffmpeg we found rather than trusting PATH to agree
        # with `find_tools` -- the whole point of looking in `tools_dir()` is
        # that PATH might not have one.
        "--ffmpeg-location", str(tools.ffmpeg),
        "--newline",
        "--progress", "--no-simulate",
        "--progress-template", PROGRESS_TEMPLATE,
        "--print", FILE_TEMPLATE,
        "--paths", str(folder),
        "--output", "%(title)s.%(ext)s",
        # Ends the options, so an id beginning with a dash is an id.
        "--",
        video_id,
    ]
