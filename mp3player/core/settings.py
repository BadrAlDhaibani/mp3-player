"""Persisted user settings.

Tolerant by design: a missing, corrupt, or hand-edited file must never stop the
app from starting. Anything we can't make sense of falls back to a default, and
every value is clamped to a range the rest of the app can rely on.
"""

from __future__ import annotations

import contextlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "XMBPlayer"

DEFAULT_VOLUME = 0.8
DEFAULT_SPEED = 1.0

# The colour preset. A bare *name*, because `core` imports no Qt and has no
# business knowing what a palette is -- `ui/theme.py` owns the list and clamps
# an unknown name to this one at apply time. Same seam as `library.MISSING`:
# here it is a token, up there it means something.
DEFAULT_THEME = "XMB Blue"

MIN_VOLUME, MAX_VOLUME = 0.0, 1.0

DAYCORE_SPEED = 0.80
NIGHTCORE_SPEED = 1.30

# The presets *are* the ends of the speed slider, which is the only reason its
# two labels can be read literally: slam the handle right and you get nightcore.
# Anything outside is clamped on load, so an older settings file that saved
# 1.45x quietly comes back as 1.30x.
MIN_SPEED, MAX_SPEED = DAYCORE_SPEED, NIGHTCORE_SPEED


def config_dir() -> Path:
    """Where settings live. `%APPDATA%/XMBPlayer` on Windows."""
    appdata = os.environ.get("APPDATA")
    root = Path(appdata) if appdata else Path.home() / ".config"
    return root / APP_NAME


def config_path() -> Path:
    return config_dir() / "settings.json"


def _clamp(value: object, default: float, low: float, high: float) -> float:
    """Coerce `value` to a float inside [low, high], or fall back to `default`."""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if number != number:  # NaN
        return default
    return min(max(number, low), high)


def _as_folder(value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return Path(value)


def _as_name(value: object, default: str) -> str:
    """Any non-empty string, whether or not this build knows it.

    Deliberately not checked against a list of legal names: a file written by a
    later build with more presets in it would then come back as the default and
    be saved that way, quietly destroying a setting this build merely doesn't
    recognise. `ui` clamps it when it applies it, which is where the list lives.
    """
    if not isinstance(value, str) or not value.strip():
        return default
    return value.strip()


@dataclass(frozen=True, slots=True)
class Settings:
    music_folder: Path | None = None
    volume: float = DEFAULT_VOLUME
    speed: float = DEFAULT_SPEED
    theme: str = DEFAULT_THEME

    def to_dict(self) -> dict[str, object]:
        return {
            "music_folder": str(self.music_folder) if self.music_folder else None,
            "volume": self.volume,
            "speed": self.speed,
            "theme": self.theme,
        }

    @classmethod
    def from_dict(cls, raw: object) -> Settings:
        """Build settings from whatever was in the file.

        Each field is validated independently, so one bad value doesn't discard
        the rest.
        """
        if not isinstance(raw, dict):
            return cls()
        return cls(
            music_folder=_as_folder(raw.get("music_folder")),
            volume=_clamp(raw.get("volume"), DEFAULT_VOLUME, MIN_VOLUME, MAX_VOLUME),
            speed=_clamp(raw.get("speed"), DEFAULT_SPEED, MIN_SPEED, MAX_SPEED),
            theme=_as_name(raw.get("theme"), DEFAULT_THEME),
        )


def load(path: Path | None = None) -> Settings:
    """Read settings from disk. Never raises -- falls back to defaults.

    Read as `utf-8-sig`, not `utf-8`: a byte-order mark is what Notepad and
    PowerShell's `Out-File -Encoding utf8` put at the front of a UTF-8 file, and
    plain `utf-8` hands that BOM to `json.loads` as a stray character. The whole
    file is then "corrupt" and every setting silently goes back to its default
    -- which looks exactly like the app forgetting your music folder for no
    reason. `utf-8-sig` eats a BOM if there is one and is identical if not. We
    still write without one.
    """
    target = path or config_path()
    try:
        raw = json.loads(target.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return Settings()
    return Settings.from_dict(raw)


def save(settings: Settings, path: Path | None = None) -> bool:
    """Write settings to disk atomically.

    Writes a sibling temp file then renames over the target, so a crash or a
    full disk can't leave a half-written settings file behind. Returns False if
    the write failed -- losing settings is not worth crashing the app over.
    """
    target = path or config_path()
    temp = target.with_suffix(target.suffix + ".tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp.write_text(
            json.dumps(settings.to_dict(), indent=2) + "\n", encoding="utf-8"
        )
        os.replace(temp, target)
        return True
    except OSError:
        with contextlib.suppress(OSError):
            temp.unlink(missing_ok=True)
        return False
