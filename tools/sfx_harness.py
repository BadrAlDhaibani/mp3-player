"""Audition the UI sounds. The instrument for the one part of Batch 6 that is
not a measurement.

    venv/Scripts/python.exe tools/sfx_harness.py                 # saved folder
    venv/Scripts/python.exe tools/sfx_harness.py "song.mp3"

`tools/shell_harness.py` can prove a blip fires on the right press and no other;
it cannot tell you the blip is too bright, or that the tick disappears under the
music, or that holding Down for two seconds sounds like a wasp. This plays them:
alone, over music, and -- the case that actually decides the numbers -- as the
stream a held arrow key produces, through the same throttle the window uses.

It is the real `ui.sounds.Sounds`, driven by hand. `Sounds` only needs something
with a `play_sfx` method, and its import of the controller is typing-only, so
none of Qt comes along for the ride.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from mp3player.core import settings as settings_mod  # noqa: E402
from mp3player.core.audio import sfx  # noqa: E402
from mp3player.core.audio.decode import DecodeError  # noqa: E402
from mp3player.core.audio.engine import AudioDeviceError, AudioEngine  # noqa: E402
from mp3player.core.library import scan_folder  # noqa: E402
from mp3player.core.models import Track  # noqa: E402
from mp3player.ui.sounds import Sounds  # noqa: E402

from engine_harness import Keyboard  # noqa: E402  -- same tools/ directory

# Windows repeats a held key about this often. The burst is the case the
# throttle exists for, so it is simulated at the rate that produces it.
KEY_REPEAT_HZ = 30.0
BURST_KEYS = 20

HELP = """
  1 2 3 4 5   move / confirm / back / error / startup
  m           hold an arrow key: 20 presses at 30/s, through the throttle
  t           sweep the speed slider: 20 ticks, same
  u           the same 20 presses with the throttle switched off
  p           play / pause music underneath, to hear the mix
  [ ]         volume down / up
  l           the loudness table
  ?           this help        q  quit
"""


class Tap:
    """Stands in for `PlayerController`: the one method `Sounds` calls.

    It also prints, which is the point of the burst tests -- you can see twenty
    presses collapse into five blips at the same time as you hear it.
    """

    def __init__(self, engine: AudioEngine) -> None:
        self.engine = engine
        self.echo = False
        self.played = 0

    def play_sfx(self, name: str, gain: float = 1.0) -> None:
        self.played += 1
        self.engine.play_sfx(name, gain)
        if self.echo:
            print(f"    {name} @ {gain:.2f}", flush=True)


def loudness_table(sample_rate: int) -> str:
    """Peak, and the loudest 30 ms, for every sound.

    Peak is what the mix table in `sfx.py` sets; it is not what you hear. A
    45 ms tick and a 220 ms buzz at the same peak are nowhere near the same
    loudness, so the short-window RMS is the column to compare when the
    question is "does this one sit under that one".
    """
    window = int(0.03 * sample_rate)
    kernel = np.ones(window) / window

    lines = [f"  {'sound':10}{'ms':>6}{'peak':>8}{'loudest 30ms':>15}"]
    for name in sfx.NAMES:
        sound = sfx.render(name, sample_rate)
        mono = sound.mean(axis=1)
        if len(mono) >= window:
            short = float(np.sqrt(np.convolve(mono**2, kernel, "valid")).max())
        else:
            short = float(np.sqrt((mono**2).mean()))
        lines.append(
            f"  {name:10}{1000 * len(sound) / sample_rate:6.0f}"
            f"{float(np.abs(sound).max()):8.3f}"
            f"{20 * np.log10(short + 1e-12):12.1f} dB"
        )
    return "\n".join(lines)


class Harness:
    def __init__(self, engine: AudioEngine, tracks: list[Track]) -> None:
        self.engine = engine
        self.tracks = tracks
        self.tap = Tap(engine)
        self.sounds = Sounds(self.tap)
        self._clock = self.sounds.clock  # kept, so `u` can put it back
        self.keys = Keyboard()
        self.running = True

    # -- bursts ------------------------------------------------------------

    def burst(self, fire, label: str, *, throttled: bool = True) -> None:
        """`BURST_KEYS` presses at the key repeat rate. The tuning case."""
        print(f"  {label}: {BURST_KEYS} presses at {KEY_REPEAT_HZ:.0f}/s")
        if not throttled:
            # Not a mode the app has -- it is here so you can hear what the
            # throttle is *for*, once, and then never want it removed.
            self.sounds.clock = lambda: 0.0
        self.tap.echo = True
        self.tap.played = 0
        for _ in range(BURST_KEYS):
            fire()
            time.sleep(1.0 / KEY_REPEAT_HZ)
        self.tap.echo = False
        self.sounds.clock = self._clock
        print(f"    -> {self.tap.played} sounds from {BURST_KEYS} presses")

    # -- music -------------------------------------------------------------

    def toggle_music(self) -> None:
        if not self.engine.has_track:
            if not self.tracks:
                print("  no tracks -- pass a file or set a folder first")
                return
            try:
                self.engine.load_path(self.tracks[0].path)
            except DecodeError as exc:
                print(f"  !! {exc}")
                return
            print(f"  playing {self.tracks[0].title}")
            return
        self.engine.toggle()

    # -- input -------------------------------------------------------------

    def handle(self, key: str) -> None:
        if key in "12345":
            name = sfx.NAMES[int(key) - 1]
            print(f"  {name}")
            self.engine.play_sfx(name)
        elif key == "m":
            self.burst(self.sounds.move, "held arrow")
        elif key == "t":
            self.burst(self.sounds.tick, "slider sweep")
        elif key == "u":
            self.burst(self.sounds.move, "held arrow, unthrottled", throttled=False)
        elif key == "p":
            self.toggle_music()
        elif key == "[":
            self.engine.volume = max(0.0, self.engine.volume - 0.05)
            print(f"  volume {self.engine.volume:.2f}")
        elif key == "]":
            self.engine.volume = min(1.0, self.engine.volume + 0.05)
            print(f"  volume {self.engine.volume:.2f}")
        elif key == "l":
            print(loudness_table(self.engine.sample_rate))
        elif key == "?":
            print(HELP)
        elif key == "q":
            self.running = False

    def run(self) -> None:
        print(HELP)
        while self.running:
            key = self.keys.poll()
            if key is not None:
                self.handle(key)
            time.sleep(0.01)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", help="a folder or a single .mp3")
    args = parser.parse_args()

    target = Path(args.target) if args.target else settings_mod.load().music_folder
    tracks: list[Track] = []
    if target is not None and Path(target).is_file():
        tracks = [Track.from_path(Path(target))]
    elif target is not None:
        tracks = list(scan_folder(target).tracks)

    try:
        engine = AudioEngine()
        engine.start()
    except AudioDeviceError as exc:
        print(f"no usable audio output: {exc}")
        return 1

    print(f"stream: {engine.device}  ({engine.latency_ms:.0f} ms)")
    print(loudness_table(engine.sample_rate))

    try:
        Harness(engine, tracks).run()
    finally:
        engine.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
