"""The audio engine: one always-on output stream, mixing music and UI blips.

Two layers, deliberately:

  `Mixer`        everything the audio callback does, with no sound card
                 attached. Pure numpy, fully testable offline.
  `AudioEngine`  a thin shell that picks a device, owns the PortAudio stream,
                 and hands each block to the mixer.

The stream is opened at launch and stays open, outputting silence when nothing
is playing. One device, no contention, and a UI blip never waits for a stream to
start.

Threading rules (CLAUDE.md, conventions):

  * The callback never blocks, never locks, never touches Qt.
  * `speed` is a plain float attribute -- assignment is atomic under the GIL.
  * Seeks are posted as a serial-tagged request the callback consumes.
  * End of track sets a flag the UI polls at 30 Hz. Nothing is ever called
    *from* the audio thread.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import sounddevice as sd

from mp3player.core.audio import decode
from mp3player.core.audio.dsp import Fader, fade_frames, fade_out_at, resample
from mp3player.core.audio.sfx import SfxBank

# Measured in Batch 0: WASAPI at blocksize 512 is ~22 ms, against 186 ms for
# PortAudio's default MME. Above ~50 ms a UI blip stops feeling connected to
# the keypress that caused it.
BLOCKSIZE = 512

MAX_SFX_VOICES = 8

# Volume drags produce a continuous stream of small changes; a slightly longer
# ramp than the transition fade keeps them from sounding stepped.
VOLUME_FADE_MS = 25.0

# How long `AudioEngine.load()` will wait for the music to fade out before
# swapping the samples array under it. Bounded so a dead stream can't hang us.
_SWAP_TIMEOUT_S = 0.05


class AudioDeviceError(RuntimeError):
    """No usable output device, or the stream refused to open."""


@dataclass(frozen=True, slots=True)
class OutputDevice:
    """A device we have already checked will accept stereo float32."""

    index: int | None
    sample_rate: int
    name: str
    hostapi: str

    def __str__(self) -> str:
        return f"{self.name} [{self.hostapi} @ {self.sample_rate} Hz]"


def pick_output_device() -> OutputDevice:
    """Choose the lowest-latency usable output.

    WASAPI first, because on this machine it is 22 ms against MME's 186 ms. It
    only accepts the device's shared-mode mix rate, so we take that rate rather
    than insisting on 44100 -- which costs nothing, since the file's rate is
    folded into the resample ratio anyway.

    Falls back to whatever PortAudio considers the default output, so this is
    not a Windows-only code path.
    """
    for api in sd.query_hostapis():
        if "WASAPI" not in api["name"]:
            continue
        index = api["default_output_device"]
        if index < 0:
            continue
        candidate = _describe(index)
        if candidate is not None:
            return candidate

    try:
        info = sd.query_devices(kind="output")
    except Exception as exc:
        raise AudioDeviceError(f"no usable audio output device: {exc}") from exc

    # `None` means "PortAudio's default", which is also what we want to hand
    # the stream -- no index to go stale if devices are hotplugged.
    candidate = _describe(None, info)
    if candidate is None:
        raise AudioDeviceError(
            "no audio output device accepts stereo float32 playback"
        )
    return candidate


def _describe(index: int | None, info: dict | None = None) -> OutputDevice | None:
    """Build an `OutputDevice` for `index`, or None if it won't take our format."""
    try:
        if info is None:
            info = sd.query_devices(index)
        rate = int(info["default_samplerate"])
        sd.check_output_settings(
            device=index, samplerate=rate, channels=2, dtype="float32"
        )
    except Exception:
        return None
    return OutputDevice(
        index=index,
        sample_rate=rate,
        name=str(info["name"]),
        hostapi=str(sd.query_hostapis(info["hostapi"])["name"]),
    )


class _MusicVoice:
    """One decoded track, read at a variable rate.

    `pos` is a fractional index into `samples` -- the file's own timeline -- so
    position in seconds stays meaningful regardless of what speed is set to.
    """

    __slots__ = ("samples", "file_rate", "stream_rate", "pos", "_end_fade")

    def __init__(self, samples: np.ndarray, file_rate: int, stream_rate: int) -> None:
        self.samples = samples
        self.file_rate = int(file_rate)
        self.stream_rate = int(stream_rate)
        self.pos = 0.0
        self._end_fade = fade_frames(self.stream_rate)

    @property
    def duration(self) -> float:
        return len(self.samples) / self.file_rate

    @property
    def position(self) -> float:
        return min(self.pos / self.file_rate, self.duration)

    @position.setter
    def position(self, seconds: float) -> None:
        limit = max(0.0, len(self.samples) - 2.0)
        self.pos = min(max(0.0, float(seconds) * self.file_rate), limit)

    def render(
        self, frames: int, speed: float, out: np.ndarray | None = None
    ) -> tuple[np.ndarray, bool]:
        # Sample-rate conversion rides along in the ratio for free.
        ratio = speed * (self.file_rate / self.stream_rate)
        block, self.pos, valid = resample(
            self.samples, self.pos, frames, ratio, out=out
        )
        if valid >= frames:
            return block, False
        # The samples simply run out. Files do not reliably end on silence, so
        # ramp the last few milliseconds down rather than cutting mid-waveform.
        fade_out_at(block, valid, self._end_fade)
        return block, True


class _SfxVoice:
    """One slot in a fixed pool of one-shot players.

    A fixed pool rather than a growing list: the UI thread arms a slot and the
    audio thread drains it, so no shared container is ever resized underneath
    the callback. `active` is written last when arming and first when clearing,
    which is what makes that safe without a lock.
    """

    __slots__ = ("samples", "pos", "gain", "active")

    def __init__(self) -> None:
        self.samples: np.ndarray | None = None
        self.pos = 0
        self.gain = 1.0
        self.active = False

    def arm(self, samples: np.ndarray, gain: float) -> None:
        self.active = False
        self.samples = samples
        self.pos = 0
        self.gain = float(gain)
        self.active = True

    def mix_into(self, out: np.ndarray, frames: int) -> None:
        samples = self.samples
        if samples is None:
            self.active = False
            return
        end = min(self.pos + frames, len(samples))
        count = end - self.pos
        if count > 0:
            chunk = samples[self.pos : end]
            if self.gain == 1.0:
                out[:count] += chunk
            else:
                out[:count] += chunk * self.gain
        self.pos = end
        if end >= len(samples):
            self.active = False


class Mixer:
    """The audio callback's body, without the sound card.

    Owns the music voice, the SFX pool, and every fade. `render()` fills one
    block; everything else is called from the UI thread and is written so that
    the two never need to agree on anything more than a single attribute write.
    """

    def __init__(
        self,
        sample_rate: int,
        *,
        volume: float = 0.8,
        speed: float = 1.0,
        max_sfx: int = MAX_SFX_VOICES,
    ) -> None:
        self.sample_rate = int(sample_rate)
        self.speed = float(speed)  # plain attribute: the UI writes it live

        self._music: _MusicVoice | None = None
        self._music_fader = Fader(self.sample_rate, gain=0.0)
        self._volume_fader = Fader(
            self.sample_rate, ms=VOLUME_FADE_MS, gain=float(volume)
        )
        self._playing = False
        self._finished = False

        # Serial-tagged so the audio thread never writes to the request slot --
        # a plain "consume and clear" can drop a seek posted microseconds later.
        self._seek_request: tuple[int, float] | None = None
        self._seek_serial = 0
        self._seek_applied = 0

        self.sfx = SfxBank(self.sample_rate)
        self._sfx_voices = [_SfxVoice() for _ in range(max(1, max_sfx))]
        self._sfx_next = 0

        self._scratch = np.zeros((BLOCKSIZE, 2), dtype=np.float32)

    # -- state the UI polls ------------------------------------------------

    @property
    def duration(self) -> float:
        return self._music.duration if self._music is not None else 0.0

    @property
    def position(self) -> float:
        return self._music.position if self._music is not None else 0.0

    @property
    def is_playing(self) -> bool:
        return self._playing

    @property
    def has_track(self) -> bool:
        return self._music is not None

    @property
    def music_gain(self) -> float:
        """Where the transition fade currently sits. Mostly for tests."""
        return self._music_fader.gain

    @property
    def volume(self) -> float:
        return self._volume_fader.target

    @volume.setter
    def volume(self, value: float) -> None:
        self._volume_fader.ramp_to(min(max(float(value), 0.0), 1.0))

    def take_finished(self) -> bool:
        """True once per track that played to its end.

        Polled by the UI rather than pushed from the audio thread -- see the
        threading rules at the top of this module.
        """
        if self._finished:
            self._finished = False
            return True
        return False

    # -- transport ---------------------------------------------------------

    def set_track(self, samples: np.ndarray, file_rate: int, *, autoplay: bool = True):
        """Swap in a decoded track, immediately.

        Immediately means *without* a fade, so callers with a live stream should
        silence the music first -- `AudioEngine.load()` does. Kept blunt here so
        the mixer stays free of waiting.
        """
        self._playing = False
        self._music_fader.jump_to(0.0)
        self._music = _MusicVoice(samples, file_rate, self.sample_rate)
        self._finished = False
        # Nothing to seek to any more; drop any request still in flight.
        self._seek_applied = self._seek_serial
        if autoplay:
            self.play()

    def clear_track(self) -> None:
        self._playing = False
        self._music_fader.jump_to(0.0)
        self._music = None
        self._finished = False

    def play(self) -> None:
        if self._music is None:
            return
        self._playing = True
        self._music_fader.ramp_to(1.0)

    def pause(self) -> None:
        self._playing = False
        self._music_fader.ramp_to(0.0)

    def toggle(self) -> None:
        self.pause() if self._playing else self.play()

    def stop(self) -> None:
        self.pause()
        self.seek(0.0)

    def seek(self, seconds: float) -> None:
        """Ask for a jump to `seconds`. Applied by the callback, after a fade."""
        self._seek_serial += 1
        self._seek_request = (self._seek_serial, float(seconds))

    def play_sfx(self, name: str, gain: float = 1.0) -> None:
        """Fire a UI sound into the next pool slot.

        Round-robin rather than "first free": when every slot is busy the oldest
        is stolen, so the newest keypress is always the one you hear.
        """
        samples = self.sfx.get(name)
        slot = self._sfx_voices[self._sfx_next]
        self._sfx_next = (self._sfx_next + 1) % len(self._sfx_voices)
        slot.arm(samples, gain)

    # -- the audio thread --------------------------------------------------

    def render(self, out: np.ndarray) -> None:
        """Fill `out` (`float32[frames, 2]`) with the next block of audio."""
        frames = len(out)
        out[:] = 0.0
        self._mix_music(out, frames)
        self._mix_sfx(out, frames)
        self._volume_fader.apply(out)
        np.clip(out, -1.0, 1.0, out=out)

    def _mix_music(self, out: np.ndarray, frames: int) -> None:
        voice = self._music
        if voice is None:
            return

        self._apply_pending_seek(voice)

        fader = self._music_fader
        if fader.silent:
            return  # paused and already quiet: nothing to add

        block, finished = voice.render(frames, self.speed, out=self._scratch_for(frames))
        fader.apply(block)
        out += block

        if finished:
            # The voice already faded itself out and the tail is silent, so
            # cutting the gain here costs nothing.
            self._playing = False
            fader.jump_to(0.0)
            self._finished = True

    def _apply_pending_seek(self, voice: _MusicVoice) -> None:
        request = self._seek_request
        if request is None or request[0] == self._seek_applied:
            return

        fader = self._music_fader
        if fader.gain > 0.0:
            # Jumping mid-waveform clicks. Get quiet first, land next block.
            fader.ramp_to(0.0)
            return

        voice.position = request[1]
        self._seek_applied = request[0]
        self._finished = False
        if self._playing:
            fader.ramp_to(1.0)

    def _mix_sfx(self, out: np.ndarray, frames: int) -> None:
        for voice in self._sfx_voices:
            if voice.active:
                voice.mix_into(out, frames)

    def _scratch_for(self, frames: int) -> np.ndarray:
        if frames > len(self._scratch):
            self._scratch = np.zeros((frames, 2), dtype=np.float32)
        return self._scratch[:frames]


class AudioEngine:
    """An always-on output stream with a `Mixer` behind it.

    Transport calls are forwarded to the mixer; the only thing this layer really
    adds is the device, the stream, and the fade-before-swap in `load()`.
    """

    def __init__(
        self,
        *,
        device: OutputDevice | None = None,
        blocksize: int = BLOCKSIZE,
        volume: float = 0.8,
        speed: float = 1.0,
    ) -> None:
        self.device = device or pick_output_device()
        self.blocksize = int(blocksize)
        self.mixer = Mixer(self.device.sample_rate, volume=volume, speed=speed)
        self._stream: sd.OutputStream | None = None
        self.xruns = 0  # counted, never printed -- the callback stays silent

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        """Open the stream. Idempotent."""
        if self._stream is not None:
            return
        self.mixer.sfx.prerender()  # never synthesize on a keypress
        try:
            stream = sd.OutputStream(
                device=self.device.index,
                samplerate=self.device.sample_rate,
                channels=2,
                dtype="float32",
                blocksize=self.blocksize,
                callback=self._callback,
            )
            stream.start()
        except Exception as exc:
            raise AudioDeviceError(f"could not open {self.device}: {exc}") from exc
        self._stream = stream

    def close(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.stop()
            stream.close()

    def __enter__(self) -> AudioEngine:
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    @property
    def running(self) -> bool:
        return self._stream is not None

    @property
    def latency_ms(self) -> float:
        return self._stream.latency * 1000.0 if self._stream is not None else 0.0

    @property
    def sample_rate(self) -> int:
        return self.device.sample_rate

    def _callback(self, outdata, frames, _time_info, status) -> None:
        if status:
            self.xruns += 1
        self.mixer.render(outdata)

    # -- tracks ------------------------------------------------------------

    def load(self, samples: np.ndarray, file_rate: int, *, autoplay: bool = True):
        """Swap in an already-decoded track, click-free.

        Drops the music gain and waits -- briefly, and only while the stream is
        actually running -- for the callback to reach silence before replacing
        the samples array. Unlike a seek this can't be deferred into the
        callback, because the new array only exists on this side.
        """
        self.mixer.pause()
        self._wait_for_silence()
        self.mixer.set_track(samples, file_rate, autoplay=autoplay)

    def load_path(self, path: Path | str, *, autoplay: bool = True) -> tuple[int, float]:
        """Decode `path` and play it. Returns `(sample_rate, duration)`.

        Raises `decode.DecodeError`; decoding is synchronous and takes a moment,
        so from Batch 3 on this belongs off the UI thread.
        """
        samples, rate = decode.load_audio(path)
        self.load(samples, rate, autoplay=autoplay)
        return rate, len(samples) / rate

    def _wait_for_silence(self) -> None:
        if self._stream is None:
            return
        deadline = time.monotonic() + _SWAP_TIMEOUT_S
        while self.mixer.music_gain > 0.0 and time.monotonic() < deadline:
            time.sleep(0.001)

    # -- transport, forwarded ---------------------------------------------

    def play(self) -> None:
        self.mixer.play()

    def pause(self) -> None:
        self.mixer.pause()

    def clear(self) -> None:
        """Drop the loaded track. Fades out first, so this is click-free."""
        self.mixer.pause()
        self._wait_for_silence()
        self.mixer.clear_track()

    def toggle(self) -> None:
        self.mixer.toggle()

    def stop(self) -> None:
        self.mixer.stop()

    def seek(self, seconds: float) -> None:
        self.mixer.seek(seconds)

    def play_sfx(self, name: str, gain: float = 1.0) -> None:
        self.mixer.play_sfx(name, gain)

    def take_finished(self) -> bool:
        return self.mixer.take_finished()

    @property
    def position(self) -> float:
        return self.mixer.position

    @property
    def duration(self) -> float:
        return self.mixer.duration

    @property
    def is_playing(self) -> bool:
        return self.mixer.is_playing

    @property
    def has_track(self) -> bool:
        return self.mixer.has_track

    @property
    def speed(self) -> float:
        return self.mixer.speed

    @speed.setter
    def speed(self, value: float) -> None:
        self.mixer.speed = float(value)

    @property
    def volume(self) -> float:
        return self.mixer.volume

    @volume.setter
    def volume(self, value: float) -> None:
        self.mixer.volume = value
