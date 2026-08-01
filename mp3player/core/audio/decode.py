"""Turn a file on disk into the canonical audio buffer.

One shape, everywhere: `float32[n_frames, 2]`. Mono is upmixed and surround is
folded down to the front pair *here*, so nothing downstream -- resampling,
mixing, the engine -- ever has to think about channel counts.

The whole file is decoded into memory. A 4-minute track is ~62 MB, which is fine
for one track at a time and buys us a lot: seeking becomes a pointer move and
resampling becomes a fractional index lookup. See CLAUDE.md.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from mp3player.core import formats

CHANNELS = 2

# Formats we can recognise but libsndfile cannot open. Worth naming explicitly:
# ~8% of this library's `.mp3` files are really MP4/AAC, and "actually an MP4"
# is a far more useful thing to show a user than libsndfile's generic error.
_UNSUPPORTED = {
    "mp4": "actually an MP4/AAC file, which libsndfile cannot decode",
}

# Interpolation reads `samples[i]` and `samples[i + 1]`, so one frame is useless.
_MIN_FRAMES = 2


class DecodeError(RuntimeError):
    """A file could not be turned into samples.

    Carries the path and a human-readable reason so the UI can say what went
    wrong with a specific track instead of failing anonymously.
    """

    def __init__(self, path: Path | str, reason: str) -> None:
        self.path = Path(path)
        self.reason = reason
        super().__init__(f"{self.path.name}: {reason}")


def load_audio(path: Path | str) -> tuple[np.ndarray, int]:
    """Decode `path` to `(float32[n, 2], sample_rate)`.

    Raises `DecodeError` -- and only `DecodeError` -- for anything unplayable.
    """
    path = Path(path)

    kind = formats.sniff(path)
    if kind == formats.UNREADABLE:
        raise DecodeError(path, "could not be opened")
    if kind in _UNSUPPORTED:
        raise DecodeError(path, _UNSUPPORTED[kind])

    try:
        data, sample_rate = sf.read(str(path), dtype="float32", always_2d=True)
    except Exception as exc:  # libsndfile raises several unrelated types
        raise DecodeError(path, str(exc) or "not a decodable audio file") from exc

    if data.shape[0] < _MIN_FRAMES:
        raise DecodeError(path, "contains no audio")

    return to_canonical(data), int(sample_rate)


def to_canonical(data: np.ndarray) -> np.ndarray:
    """Coerce a decoded array to contiguous `float32[n, 2]`.

    Split out from `load_audio` so tests -- and any future decoder -- can reach
    the one place that defines what "our buffer shape" means.
    """
    if data.ndim == 1:
        data = data[:, None]
    if data.dtype != np.float32:
        data = data.astype(np.float32)

    channels = data.shape[1]
    if channels == 1:
        data = np.repeat(data, CHANNELS, axis=1)
    elif channels > CHANNELS:
        # Front left/right. Proper downmixing is a post-v1 concern, if ever --
        # this library is stereo MP3s.
        data = data[:, :CHANNELS]

    return np.ascontiguousarray(data, dtype=np.float32)
