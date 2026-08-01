"""Data types shared across the core.

No Qt, no audio libraries -- see the `core/` rule in CLAUDE.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Track:
    """A playable file in the library.

    v1 identifies tracks by filename alone; reading ID3 tags is post-v1. `title`
    is a field rather than a property so the tag reader can populate it later
    without anything downstream having to change.
    """

    path: Path
    title: str

    @classmethod
    def from_path(cls, path: Path) -> Track:
        return cls(path=path, title=path.stem)

    def __str__(self) -> str:
        return self.title
