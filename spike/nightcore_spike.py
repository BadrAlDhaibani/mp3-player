"""Batch 0 spike: prove the nightcore/daycore audio path before we build on it.

Validates the three assumptions the whole app rests on:

  1. `soundfile` decodes a real .mp3 into a numpy array on this machine.
  2. `sounddevice` plays that array through a callback-mode output stream.
  3. Resampling at a fractional read position gives us nightcore/daycore with
     pitch linked to speed -- and speed can change *mid-playback* without clicks.

Throwaway code. The `Voice` class below is the seed of core/audio/engine.py.

    python spike/nightcore_spike.py "path/to/song.mp3"
    python spike/nightcore_spike.py "path/to/song.mp3" --render out.wav
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

BLOCK = 512

NORMAL, NIGHTCORE, DAYCORE = 1.00, 1.30, 0.80

# Negotiated at runtime by pick_output(); the offline renderer assumes this too.
STREAM_SR = 48000


def pick_output() -> tuple[int | None, int]:
    """Choose the lowest-latency usable output device.

    On this machine MME (PortAudio's default) reports ~186 ms, which would make
    every UI blip land a fifth of a second after the keypress. WASAPI does 22 ms
    -- but only at the device's shared-mode mix rate, so we take its rate rather
    than insisting on 44100. That costs us nothing: the file's sample rate is
    folded into the resample ratio anyway.
    """
    for api in sd.query_hostapis():
        if "WASAPI" not in api["name"]:
            continue
        dev = api["default_output_device"]
        if dev < 0:
            continue
        rate = int(sd.query_devices(dev)["default_samplerate"])
        try:
            sd.check_output_settings(device=dev, samplerate=rate,
                                     channels=2, dtype="float32")
            return dev, rate
        except Exception:
            pass
    # Any other machine: take PortAudio's default and whatever rate it likes.
    dev_info = sd.query_devices(kind="output")
    return None, int(dev_info["default_samplerate"])


def sniff(path: Path) -> str:
    """Identify a file by magic bytes. ~8% of files named .mp3 aren't."""
    with open(path, "rb") as f:
        head = f.read(12)
    if head[:3] == b"ID3":
        return "mp3"
    if len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:
        return "mp3"
    if head[4:8] == b"ftyp":
        return "mp4/m4a"
    if head[:4] == b"OggS":
        return "ogg"
    if head[:4] == b"fLaC":
        return "flac"
    if head[:4] == b"RIFF":
        return "wav"
    return "unknown"


def load(path: Path) -> tuple[np.ndarray, int]:
    """Decode a whole file to float32 [n_frames, 2]. Mono is upmixed to stereo."""
    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    elif data.shape[1] > 2:
        data = data[:, :2]
    return np.ascontiguousarray(data), sr


class Voice:
    """A decoded track read at a variable rate.

    Speed and pitch are deliberately linked: we just walk the sample array
    faster or slower and interpolate. That *is* nightcore -- no time-stretch,
    no pitch preservation. Because `pos` is a float advanced continuously,
    `speed` can be reassigned at any moment and the audio follows seamlessly.
    """

    def __init__(self, samples: np.ndarray, sr: int) -> None:
        self.samples = samples
        self.sr = sr
        self.pos = 0.0
        self.speed = NORMAL
        self.volume = 0.8

    @property
    def ratio(self) -> float:
        # Folding sample-rate conversion in here makes it free.
        return self.speed * (self.sr / STREAM_SR)

    def read(self, frames: int) -> tuple[np.ndarray, bool]:
        ratio = self.ratio  # sample once; the UI thread may change it mid-call
        last = len(self.samples) - 2
        idx = self.pos + np.arange(frames, dtype=np.float64) * ratio
        finished = idx[-1] >= last

        np.clip(idx, 0, last, out=idx)
        i0 = idx.astype(np.int64)
        frac = (idx - i0).astype(np.float32)[:, None]

        block = self.samples[i0] * (1.0 - frac) + self.samples[i0 + 1] * frac
        self.pos += frames * ratio
        return block * self.volume, finished


# The demo timeline: (seconds, target_speed, label). A `None` target means hold.
TIMELINE = [
    (5.0, NORMAL, "normal      1.00x"),
    (3.0, NIGHTCORE, "gliding ->  1.30x   <- listen for clicks here"),
    (5.0, NIGHTCORE, "NIGHTCORE   1.30x"),
    (4.0, DAYCORE, "gliding ->  0.80x   <- and here"),
    (6.0, DAYCORE, "DAYCORE     0.80x"),
]


def run_realtime(voice: Voice) -> None:
    finished = False

    def callback(outdata, frames, _time, status):
        nonlocal finished
        if status:
            print(f"  [stream status: {status}]", file=sys.stderr)
        block, done = voice.read(frames)
        outdata[:] = block
        if done:
            finished = True
            raise sd.CallbackStop

    device, rate = pick_output()
    globals()["STREAM_SR"] = rate  # spike-only shortcut; engine.py will pass it in
    info = sd.query_devices(device if device is not None else sd.default.device[1])
    api = sd.query_hostapis(info["hostapi"])["name"]
    print(f"\nplaying on: {info['name']}  [{api} @ {rate} Hz]\n")

    with sd.OutputStream(
        device=device, samplerate=rate, channels=2, dtype="float32",
        blocksize=BLOCK, callback=callback,
    ) as stream:
        print(f"  output latency: {stream.latency*1000:.0f} ms\n")
        for seconds, target, label in TIMELINE:
            print(f"  {label}")
            start_speed, t0 = voice.speed, time.monotonic()
            while (elapsed := time.monotonic() - t0) < seconds:
                if finished:
                    print("\n  (track ended)")
                    return
                # Glide rather than jump, so any zipper noise would be audible.
                k = min(1.0, elapsed / seconds)
                voice.speed = start_speed + (target - start_speed) * k
                time.sleep(0.01)
            voice.speed = target
    print("\n  done.")


def run_render(voice: Voice, out: Path) -> None:
    """Same timeline, rendered offline -- lets us verify without a sound card."""
    blocks, elapsed = [], 0.0
    for seconds, target, label in TIMELINE:
        start_speed = voice.speed
        n = int(seconds * STREAM_SR)
        for off in range(0, n, BLOCK):
            k = min(1.0, off / max(n, 1))
            voice.speed = start_speed + (target - start_speed) * k
            block, done = voice.read(BLOCK)
            blocks.append(block)
            if done:
                break
        voice.speed = target
        elapsed += seconds
        print(f"  rendered {label}")

    audio = np.concatenate(blocks)
    sf.write(str(out), audio, STREAM_SR)
    print(f"\n  wrote {out}  ({len(audio)/STREAM_SR:.1f}s, {audio.shape})")
    print(f"  peak {np.abs(audio).max():.3f}   finite: {np.isfinite(audio).all()}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path)
    ap.add_argument("--render", type=Path, help="render to a wav instead of playing")
    args = ap.parse_args()

    if not args.path.is_file():
        print(f"no such file: {args.path}", file=sys.stderr)
        return 1

    kind = sniff(args.path)
    if kind != "mp3":
        print(f"'{args.path.name}' is actually {kind}, not mp3 -- libsndfile can't "
              f"decode it.", file=sys.stderr)
        return 1

    samples, sr = load(args.path)
    dur = len(samples) / sr
    print(f"decoded {args.path.name}")
    print(f"  {samples.shape[0]:,} frames  {sr} Hz  {dur:.1f}s  "
          f"{samples.nbytes/1e6:.0f} MB in memory")

    voice = Voice(samples, sr)
    if args.render:
        run_render(voice, args.render)
    else:
        run_realtime(voice)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
