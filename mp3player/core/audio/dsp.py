"""The signal processing the player actually needs: variable-rate reads and
click-free gain changes.

Pure numpy, no state beyond what `Fader` holds. Everything here is called from
the audio callback, so nothing may block and allocation is kept to a single
optional scratch buffer supplied by the caller.
"""

from __future__ import annotations

import numpy as np

# Long enough to hide a waveform discontinuity, short enough that a keypress
# still feels instant. Every transition in the app uses it.
FADE_MS = 10.0


def fade_frames(sample_rate: int, ms: float = FADE_MS) -> int:
    """How many frames a full 0 -> 1 fade spans at `sample_rate`."""
    return max(1, int(round(sample_rate * ms / 1000.0)))


def resample(
    samples: np.ndarray,
    pos: float,
    frames: int,
    ratio: float,
    out: np.ndarray | None = None,
) -> tuple[np.ndarray, float, int]:
    """Read `frames` frames starting at fractional index `pos`, stepping by `ratio`.

    This is the whole nightcore trick. Walking the sample array faster than it
    was recorded raises pitch along with tempo, which is exactly the effect we
    want -- no time-stretch, no pitch preservation (CLAUDE.md, decisions log).
    Sample-rate conversion rides along in `ratio` for free.

    Returns `(block, new_pos, valid)`. `block` is `float32[frames, 2]` and
    `valid` counts how many of those frames actually came from `samples`; the
    rest are silence rather than a held final sample, because a held sample is
    a DC step. `valid < frames` means the read ran off the end -- and the caller
    still owes the signal a fade down to that point, since a track that stops
    while it is loud is a step too. See `fade_out_at`.

    `pos` is a float advanced continuously, which is why `ratio` may change
    between calls -- or between blocks -- with no discontinuity.
    """
    if out is None:
        out = np.zeros((max(frames, 0), 2), dtype=np.float32)
    if frames <= 0:
        return out, pos, 0

    ratio = max(0.0, float(ratio))  # reverse playback is not a thing we support
    new_pos = pos + frames * ratio

    # The highest index we can interpolate *from*: reading it needs `last + 1`.
    last = len(samples) - 1
    if last < 1:
        out[:] = 0.0
        return out, new_pos, 0

    idx = pos + np.arange(frames, dtype=np.float64) * ratio
    # `idx` is non-decreasing, so one search finds where we leave the array.
    valid = int(np.searchsorted(idx, last))

    if valid > 0:
        head = idx[:valid]
        np.clip(head, 0.0, None, out=head)
        i0 = head.astype(np.int64)
        frac = (head - i0).astype(np.float32)[:, None]
        out[:valid] = samples[i0] * (1.0 - frac) + samples[i0 + 1] * frac
    out[valid:] = 0.0

    return out, new_pos, valid


def fade_out_at(block: np.ndarray, index: int, length: int) -> None:
    """Ramp `block` down in place so it reaches exactly zero at `index`.

    Used where the signal stops for a reason other than a transport change --
    the end of a track. The ramp starts at unity, so it joins the untouched
    samples before it without a seam of its own.
    """
    start = max(0, index - length)
    count = index - start
    if count <= 0:
        return
    ramp = np.linspace(1.0, 0.0, count, dtype=np.float32)
    block[start:index] *= ramp[:, None]


class Fader:
    """A gain that travels to its target instead of jumping to it.

    Play, pause, seek, track change and volume drags all move a gain, and a gain
    that moves in one step puts a vertical edge in the waveform -- an audible
    click. Ramping over ~10 ms removes it and costs nothing perceptible.

    The ramp runs at a constant rate, so a full 0 -> 1 takes `FADE_MS` and
    smaller moves take proportionally less.
    """

    __slots__ = ("gain", "target", "_rate")

    def __init__(
        self, sample_rate: int, *, ms: float = FADE_MS, gain: float = 0.0
    ) -> None:
        self._rate = 1.0 / fade_frames(sample_rate, ms)  # gain units per frame
        self.gain = float(gain)
        self.target = float(gain)

    def ramp_to(self, target: float) -> None:
        """Head for `target`, starting from wherever the gain currently is."""
        self.target = float(target)

    def jump_to(self, gain: float) -> None:
        """Set the gain outright. Only safe when the signal is already silent."""
        self.gain = self.target = float(gain)

    @property
    def idle(self) -> bool:
        return self.gain == self.target

    @property
    def silent(self) -> bool:
        """True when this fader neither is, nor is heading anywhere but, zero."""
        return self.gain == 0.0 and self.target == 0.0

    def apply(self, block: np.ndarray) -> np.ndarray:
        """Scale `block` in place, advancing the ramp by `len(block)` frames."""
        frames = len(block)
        if frames == 0:
            return block

        if self.gain == self.target:
            if self.gain != 1.0:
                block *= self.gain
            return block

        delta = self.target - self.gain
        step = self._rate if delta > 0.0 else -self._rate
        env = self.gain + step * np.arange(1, frames + 1, dtype=np.float32)
        low, high = sorted((self.gain, self.target))
        np.clip(env, low, high, out=env)

        if frames * self._rate >= abs(delta):
            # Arrived. Snap rather than trust the accumulated float32 value:
            # `idle` and `silent` are exact comparisons, and landing a hair
            # short of zero would leave a paused track quietly bleeding.
            self.gain = self.target
            env[-1] = np.float32(self.target)
        else:
            self.gain = float(env[-1])

        block *= env[:, None]
        return block
