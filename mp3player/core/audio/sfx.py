"""The UI sounds, synthesized from scratch.

Sony's XMB sounds are their copyrighted assets, so we make our own out of sine
waves: free to ship, tunable by editing a number, and no binary files in git
(CLAUDE.md, decisions log).

Each builder returns mono or stereo float32 at the requested sample rate.
`_finish` then normalises it and ramps both ends to exactly zero, so every sound
is click-free by construction rather than by luck.
"""

from __future__ import annotations

import numpy as np

TWO_PI = 2.0 * np.pi

MOVE = "move"
CONFIRM = "confirm"
BACK = "back"
ERROR = "error"
STARTUP = "startup"

NAMES = (MOVE, CONFIRM, BACK, ERROR, STARTUP)

# Peak amplitude per sound. These are the "mix" -- blips sit well under the
# music, the startup swell is allowed to be the loudest thing you hear.
_PEAKS = {
    MOVE: 0.22,
    CONFIRM: 0.30,
    BACK: 0.26,
    ERROR: 0.34,
    STARTUP: 0.42,
}

_ATTACK_MS = 2.0
_RELEASE_MS = 4.0


def _time(duration: float, sample_rate: int) -> np.ndarray:
    """A time axis in seconds, one entry per frame."""
    return np.arange(int(duration * sample_rate), dtype=np.float32) / sample_rate


def _sine(t: np.ndarray, freq: float) -> np.ndarray:
    return np.sin(TWO_PI * freq * t, dtype=np.float32)


def _glide(t: np.ndarray, start: float, end: float, over: float, sample_rate: int):
    """Phase of a tone sliding `start` -> `end` Hz over the first `over` seconds.

    Returns phase, not a sine, so callers can build harmonics on top of it.
    Frequency is integrated into phase rather than plugged straight into
    `sin(2*pi*f*t)`; the naive version sweeps twice as far as intended.
    """
    freq = start + (end - start) * np.minimum(t / max(over, 1e-6), 1.0)
    phase = TWO_PI * np.cumsum(freq) / sample_rate
    return phase.astype(np.float32)


def _decay(t: np.ndarray, tau: float) -> np.ndarray:
    return np.exp(-t / tau, dtype=np.float32)


def _build_move(sample_rate: int) -> np.ndarray:
    """The one you hear most: a short, soft, high tick as the selection moves."""
    t = _time(0.045, sample_rate)
    wave = _sine(t, 1180.0) + 0.35 * _sine(t, 2360.0)
    return wave * _decay(t, 0.012)


def _build_confirm(sample_rate: int) -> np.ndarray:
    """Rising two-tone: something opened, something started."""
    t = _time(0.14, sample_rate)
    phase = _glide(t, 740.0, 1480.0, 0.055, sample_rate)
    wave = np.sin(phase) + 0.30 * np.sin(2.0 * phase)
    return wave * _decay(t, 0.048)


def _build_back(sample_rate: int) -> np.ndarray:
    """`confirm` inverted -- falling, slightly darker. Something closed."""
    t = _time(0.13, sample_rate)
    phase = _glide(t, 880.0, 520.0, 0.055, sample_rate)
    wave = np.sin(phase) + 0.22 * np.sin(2.0 * phase)
    return wave * _decay(t, 0.045)


def _build_error(sample_rate: int) -> np.ndarray:
    """Low, buzzy, unmistakably a refusal.

    Odd harmonics at 1/k give a hollow square-ish tone; the slow amplitude
    wobble keeps it from sounding like a musical note.
    """
    t = _time(0.22, sample_rate)
    wave = sum(_sine(t, 196.0 * k) / k for k in (1, 3, 5, 7))
    wobble = 1.0 + 0.25 * _sine(t, 22.0)
    return wave * wobble * _decay(t, 0.10)


def _build_startup(sample_rate: int) -> np.ndarray:
    """A slow swell on launch: root, fifth, octave, twelfth.

    The two channels are detuned by a fraction of a hertz, which spreads the
    sound across the stereo field as the partials drift in and out of phase.
    """
    t = _time(1.1, sample_rate)
    envelope = (1.0 - np.exp(-t / 0.09, dtype=np.float32)) * _decay(t, 0.42)

    partials = ((330.0, 1.00), (495.0, 0.55), (660.0, 0.40), (990.0, 0.18))
    channels = []
    for detune in (-0.35, 0.35):
        wave = sum(amp * _sine(t, freq + detune) for freq, amp in partials)
        channels.append(wave * envelope)
    return np.stack(channels, axis=1)


_BUILDERS = {
    MOVE: _build_move,
    CONFIRM: _build_confirm,
    BACK: _build_back,
    ERROR: _build_error,
    STARTUP: _build_startup,
}


def _finish(wave: np.ndarray, sample_rate: int, peak: float) -> np.ndarray:
    """Ramp both ends to zero, normalise to `peak`, return `float32[n, 2]`.

    That order matters, and it used to be the other way round. A blip whose
    loudest moment is its first sample -- `move`, and every percussive sound
    worth the name -- has that sample multiplied by the attack ramp's zero, so
    normalising first sets a level the envelope then takes away: `move` asked
    for 0.22 and came out at 0.18, and the mix in `_PEAKS` was quietly a
    different mix from the one written down. Enveloping first makes the table
    mean what it says.
    """
    wave = np.asarray(wave, dtype=np.float32)
    if wave.ndim == 1:
        wave = np.repeat(wave[:, None], 2, axis=1)
    wave = wave.copy()  # the builders' arrays are scaled in place below

    frames = len(wave)
    attack = min(frames // 2, max(1, int(sample_rate * _ATTACK_MS / 1000)))
    release = min(frames - attack, max(1, int(sample_rate * _RELEASE_MS / 1000)))
    if attack > 0:
        wave[:attack] *= np.linspace(0.0, 1.0, attack, dtype=np.float32)[:, None]
    if release > 0:
        wave[-release:] *= np.linspace(1.0, 0.0, release, dtype=np.float32)[:, None]

    loudest = float(np.abs(wave).max()) if wave.size else 0.0
    if loudest > 0.0:
        wave *= peak / loudest

    return np.ascontiguousarray(wave, dtype=np.float32)


def render(name: str, sample_rate: int) -> np.ndarray:
    """Synthesize one sound. Prefer `SfxBank`, which caches."""
    try:
        builder = _BUILDERS[name]
    except KeyError:
        raise KeyError(f"unknown sound {name!r}; known: {', '.join(NAMES)}") from None
    return _finish(builder(sample_rate), sample_rate, _PEAKS[name])


class SfxBank:
    """Every UI sound, rendered once at the stream's rate and kept.

    Built at the stream rate so playback is a plain array copy -- no resampling
    on the audio thread for something that never changes pitch.
    """

    def __init__(self, sample_rate: int) -> None:
        self.sample_rate = int(sample_rate)
        self._cache: dict[str, np.ndarray] = {}

    def get(self, name: str) -> np.ndarray:
        sound = self._cache.get(name)
        if sound is None:
            sound = render(name, self.sample_rate)
            self._cache[name] = sound
        return sound

    def prerender(self) -> None:
        """Build everything up front, so no keypress ever pays for synthesis."""
        for name in NAMES:
            self.get(name)
