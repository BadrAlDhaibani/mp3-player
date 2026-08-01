"""Turn a folder on disk into a list of playable tracks.

Top level only -- subfolder recursion is post-v1 (CLAUDE.md, v1 scope).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mp3player.core.formats import is_mp3
from mp3player.core.models import Track

AUDIO_SUFFIX = ".mp3"


@dataclass(frozen=True, slots=True)
class ScanResult:
    """What a folder scan found.

    `skipped` holds files named `.mp3` whose contents say otherwise. We report
    them rather than dropping them silently so the UI can show "20 files
    skipped -- unsupported format" instead of leaving the user wondering where
    their music went.
    """

    tracks: tuple[Track, ...] = ()
    skipped: tuple[Path, ...] = ()

    def __len__(self) -> int:
        return len(self.tracks)

    def __bool__(self) -> bool:
        return bool(self.tracks)


def scan_folder(folder: Path | str | None) -> ScanResult:
    """List playable MP3s sitting directly inside `folder`.

    Never raises. A folder that is missing, empty, unreadable, or simply not a
    folder all yield an empty result -- the app should degrade to "no music"
    rather than fail to start.
    """
    if folder is None:
        return ScanResult()

    try:
        entries = sorted(Path(folder).iterdir(), key=lambda p: p.name.casefold())
    except OSError:
        # Missing, not a directory, or permission denied.
        return ScanResult()

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
            tracks.append(Track.from_path(entry))
        else:
            skipped.append(entry)

    return ScanResult(tracks=tuple(tracks), skipped=tuple(skipped))
