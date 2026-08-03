"""Data types shared across the core.

No Qt, no audio libraries -- see the `core/` rule in CLAUDE.md. That extends to
the tag reader: this is the module everything else imports, so `Tags` comes in
under `TYPE_CHECKING` only and `models` keeps importing nothing at runtime.
`from_tags` needs the shape, not the library.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # `Tags` is a type here and nothing more -- see the module
    from mp3player.core.tags import Tags  # docstring on why it stays that way


@dataclass(frozen=True, slots=True)
class Track:
    """A playable file in the library.

    `title` was a field rather than a property from v1 precisely so the tag
    reader could fill it in later without anything downstream changing. Batch 8
    cashed that in: `from_path` still names a track by its filename, and
    `from_tags` is what `scan_folder` uses when the file had something to say.

    `artist` and `album` default to empty rather than `None` so every consumer
    can treat "absent" and "blank" the same way -- which they are, on screen.
    Cover art is deliberately not here: it is half a megabyte per track and only
    the playing one needs it, so it is fetched on demand (`core.tags.read_art`)
    rather than carried around by the whole library.
    """

    path: Path
    title: str
    artist: str = ""
    album: str = ""

    @classmethod
    def from_path(cls, path: Path) -> Track:
        return cls(path=path, title=path.stem)

    @classmethod
    def from_tags(cls, path: Path, tags: Tags) -> Track:
        """Name the track from its tag, falling back to the filename.

        The fallback is the whole rule, and it lives here so it is spelled once:
        a tagged file is named by its tag, an untagged one by its stem -- which
        is exactly what the app did before tags existed.
        """
        return cls(
            path=path,
            title=tags.title or path.stem,
            artist=tags.artist,
            album=tags.album,
        )

    def __str__(self) -> str:
        return self.title
