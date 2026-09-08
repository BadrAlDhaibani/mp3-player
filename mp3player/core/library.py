"""Turn a folder on disk into a list of playable tracks.

Top level only -- subfolder recursion is post-v1 (CLAUDE.md, v1 scope).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mp3player.core.formats import is_mp3
from mp3player.core.models import Track
from mp3player.core.tags import read_tags

AUDIO_SUFFIX = ".mp3"

# Why a scan came back empty. Reported as data rather than as a sentence: the
# folder being *gone* and the folder merely having no music in it want different
# copy and, in the first case, a different suggestion -- but which words to use
# is the UI's business, not this module's.
NO_FOLDER = "no_folder"  # nothing has ever been chosen
MISSING = "missing"  # chosen once, not there any more
UNREADABLE = "unreadable"  # there, but we cannot list it


@dataclass(frozen=True, slots=True)
class ScanResult:
    """What a folder scan found.

    `skipped` holds files named `.mp3` whose contents say otherwise. We report
    them rather than dropping them silently so the UI can show "20 files
    skipped -- unsupported format" instead of leaving the user wondering where
    their music went.

    `error` is why there are no tracks, when the reason is the folder itself.
    `None` -- the default, because it is what a result with tracks in it always
    means -- says the scan reached the folder and read it, including the
    perfectly ordinary case of a folder with no MP3s in it.
    """

    tracks: tuple[Track, ...] = ()
    skipped: tuple[Path, ...] = ()
    error: str | None = None

    def __len__(self) -> int:
        return len(self.tracks)

    def __bool__(self) -> bool:
        return bool(self.tracks)


def matches(track: Track, query: str) -> bool:
    """Does `track` answer to `query`? Case-insensitive substring, title or artist.

    Here rather than in the window because it is a pure function of a `Track`
    and a string, which is the only kind of thing `tests/` can reach -- the
    filtering *mode* is all Qt and lives upstairs. Title and artist and not the
    album, chosen with the user: an album name you remember is nearly always a
    name you would also find under the artist, and most of this library has
    neither.

    An empty query matches everything, and that is load-bearing rather than
    tidy. The window maps column rows onto track indices through this, so "no
    query" has to come back as the identity or every caller above would need a
    branch for the case that is true 99% of the time.

    Stripped, so a trailing space typed mid-word doesn't silently empty the
    list, and a query of nothing but spaces means no query at all.
    """
    needle = query.strip().casefold()
    if not needle:
        return True
    return needle in track.title.casefold() or needle in track.artist.casefold()


def scan_folder(folder: Path | str | None, *, tags: bool = True) -> ScanResult:
    """List playable MP3s sitting directly inside `folder`.

    Never raises. A folder that is missing, empty, unreadable, or simply not a
    folder all yield an empty result -- the app should degrade to "no music"
    rather than fail to start. Which of those it was comes back in `error`.

    `tags=False` names every track by its filename and reads nothing else. It is
    for callers that only want the paths -- the audio and sfx harnesses in
    `tools/` -- and is not a setting anybody can reach from the app; the
    reason it exists is that a tag read is the one part of a scan that touches
    the *contents* of every file, and something that only wants a playlist
    shouldn't pay for it. Cover art is never read here at any setting: see
    `core.tags` for why that one is fetched a track at a time.
    """
    if folder is None:
        return ScanResult(error=NO_FOLDER)

    path = Path(folder)
    try:
        entries = sorted(path.iterdir(), key=lambda p: p.name.casefold())
    except OSError:
        # A folder can go away while the app is open -- an unplugged drive, a
        # rename, a sync client -- and that wants different words from a folder
        # that is right there and refusing to be read. `is_dir` splits them the
        # way the user experiences them: there is no such folder, or there is
        # one and we're not allowed in. Anything that isn't a directory (a file
        # under that name, a broken link) is the first kind.
        try:
            readable_folder = path.is_dir()
        except OSError:
            readable_folder = False
        return ScanResult(error=UNREADABLE if readable_folder else MISSING)

    tracks: list[Track] = []
    skipped: list[Path] = []
    for entry in entries:
        if entry.suffix.casefold() != AUDIO_SUFFIX:
            continue
        try:
            if not entry.is_file():
                continue
        except OSError:
            continue  # a broken link or a path we can't stat
        if is_mp3(entry):
            tracks.append(
                Track.from_tags(entry, read_tags(entry)) if tags else Track.from_path(entry)
            )
        else:
            skipped.append(entry)

    return ScanResult(tracks=tuple(tracks), skipped=tuple(skipped), error=None)
