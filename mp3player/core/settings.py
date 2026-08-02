"""Persisted user settings.

Tolerant by design: a missing, corrupt, or hand-edited file must never stop the
app from starting. Anything we can't make sense of falls back to a default, and
every value is clamped to a range the rest of the app can rely on.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "XMBPlayer"

DEFAULT_VOLUME = 0.8
DEFAULT_SPEED = 1.0

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


@dataclass(frozen=True, slots=True)
class Settings:
    music_folder: Path | None = None
    volume: float = DEFAULT_VOLUME
    speed: float = DEFAULT_SPEED

    def to_dict(self) -> dict[str, object]:
        return {
            "music_folder": str(self.music_folder) if self.music_folder else None,
            "volume": self.volume,
            "speed": self.speed,
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
        )


def load(path: Path | None = None) -> Settings:
    """Read settings from disk. Never raises -- falls back to defaults."""
    target = path or config_path()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
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
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        return False
