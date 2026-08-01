"""Drive the audio engine from the keyboard, with no Qt in sight.

The end of Batch 2: everything the player will eventually do to the audio --
play, pause, seek, next/prev, live speed, volume, UI blips -- reachable with one
keypress each. If it feels right here, the Qt layer in Batch 3 has nothing left
to prove about the audio.

    venv/Scripts/python.exe tools/engine_harness.py                 # saved folder
    venv/Scripts/python.exe tools/engine_harness.py "D:/Music"
    venv/Scripts/python.exe tools/engine_harness.py "song.mp3"
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# This file lives outside the package, so running it by path puts `tools/` on
# sys.path rather than the repo root. Put the root back before importing.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mp3player.core import settings as settings_mod  # noqa: E402
from mp3player.core.audio import sfx  # noqa: E402
from mp3player.core.audio.decode import DecodeError  # noqa: E402
from mp3player.core.audio.engine import AudioDeviceError, AudioEngine  # noqa: E402
from mp3player.core.library import scan_folder  # noqa: E402
from mp3player.core.models import Track  # noqa: E402

SEEK_STEP = 5.0
SPEED_STEP = 0.05
VOLUME_STEP = 0.05
POLL_S = 0.03

HELP = """
  space  play / pause          <-  ->   seek -5s / +5s
  ,  .   prev / next track      up/down speed -/+ 0.05
  n      nightcore  1.30x      [  ]     volume -/+
  r      normal     1.00x      1-5      move/confirm/back/error/startup
  d      daycore    0.80x      ?        this help
  q      quit
"""


class Keyboard:
    """Non-blocking single keypresses.

    Windows-only in practice (`msvcrt`), which is what this project targets --
    but the import is guarded so the harness fails with a sentence rather than
    a traceback anywhere else.
    """

    ARROWS = {b"H": "up", b"P": "down", b"K": "left", b"M": "right"}

    def __init__(self) -> None:
        try:
            import msvcrt
        except ImportError as exc:  # pragma: no cover - Windows-targeted tool
            raise SystemExit(
                "the harness needs a Windows console for single keypresses"
            ) from exc
        self._msvcrt = msvcrt

    def poll(self) -> str | None:
        """The next key as a lowercase name, or None if nothing was pressed."""
        if not self._msvcrt.kbhit():
            return None
        key = self._msvcrt.getch()
        if key in (b"\x00", b"\xe0"):  # arrow and function keys arrive as pairs
            return self.ARROWS.get(self._msvcrt.getch())
        if key == b"\x03":
            return "q"
        return key.decode("latin-1").lower()


def clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


class Harness:
    def __init__(self, engine: AudioEngine, tracks: list[Track]) -> None:
        self.engine = engine
        self.tracks = tracks
        self.index = -1
        self.keys = Keyboard()
        self.running = True
        self._status_width = 0

    # -- output ----------------------------------------------------------

    def say(self, message: str = "") -> None:
        """Print above the status line without leaving fragments behind."""
        print("\r" + " " * self._status_width + "\r" + message, flush=True)
        self._status_width = 0

    def draw_status(self) -> None:
        engine = self.engine
        position, duration = engine.position, engine.duration
        filled = int(24 * position / duration) if duration else 0
        bar = "#" * filled + "-" * (24 - filled)
        state = "|>" if engine.is_playing else "||"
        line = (
            f"  {state} [{bar}] {clock(position)}/{clock(duration)} "
            f" {engine.speed:.2f}x  vol {engine.volume:.2f} "
        )
        print("\r" + line.ljust(self._status_width), end="", flush=True)
        self._status_width = max(self._status_width, len(line))

    # -- tracks ----------------------------------------------------------

    def select(self, index: int, *, autoplay: bool = True) -> None:
        if not self.tracks:
            return
        self.index = index % len(self.tracks)
        track = self.tracks[self.index]
        try:
            rate, duration = self.engine.load_path(track.path, autoplay=autoplay)
        except DecodeError as exc:
            # scan_folder already sniffs magic bytes, so this means a truncated
            # or genuinely broken file rather than the usual mislabelled MP4.
            self.say(f"  !! {exc}")
            self.engine.play_sfx(sfx.ERROR)
            return
        self.say(
            f"  >> {self.index + 1}/{len(self.tracks)}  {track.title}"
            f"   [{clock(duration)}, {rate} Hz]"
        )

    def step(self, delta: int) -> None:
        self.engine.play_sfx(sfx.MOVE)
        self.select(self.index + delta if self.index >= 0 else 0)

    # -- input -----------------------------------------------------------

    def handle(self, key: str) -> None:
        engine = self.engine

        if key == "q":
            self.running = False
        elif key == " ":
            engine.toggle()
            engine.play_sfx(sfx.CONFIRM if engine.is_playing else sfx.BACK)
        elif key == "left":
            engine.seek(max(0.0, engine.position - SEEK_STEP))
        elif key == "right":
            engine.seek(min(engine.duration, engine.position + SEEK_STEP))
        elif key == ",":
            self.step(-1)
        elif key == ".":
            self.step(+1)
        elif key in ("up", "down"):
            self.set_speed(engine.speed + (SPEED_STEP if key == "up" else -SPEED_STEP))
        elif key == "n":
            self.set_speed(settings_mod.NIGHTCORE_SPEED)
        elif key == "d":
            self.set_speed(settings_mod.DAYCORE_SPEED)
        elif key == "r":
            self.set_speed(1.0)
        elif key in ("[", "]"):
            engine.volume += VOLUME_STEP if key == "]" else -VOLUME_STEP
        elif key in "12345":
            engine.play_sfx(sfx.NAMES[int(key) - 1])
        elif key == "?":
            self.say(HELP)

    def set_speed(self, value: float) -> None:
        self.engine.speed = min(
            max(value, settings_mod.MIN_SPEED), settings_mod.MAX_SPEED
        )

    # -- loop ------------------------------------------------------------

    def run(self) -> None:
        self.engine.play_sfx(sfx.STARTUP)
        self.say(f"  device: {self.engine.device}")
        self.say(f"  output latency: {self.engine.latency_ms:.0f} ms")
        self.say(HELP)

        if self.tracks:
            self.select(0, autoplay=False)

        while self.running:
            key = self.keys.poll()
            if key is not None:
                self.handle(key)
            if self.engine.take_finished():
                # Polled, never pushed: nothing is ever called from the audio
                # thread. Batch 3's controller does exactly this at 30 Hz.
                self.step(+1)
            self.draw_status()
            time.sleep(POLL_S)

        self.say()
        if self.engine.xruns:
            self.say(f"  {self.engine.xruns} stream underruns")


def collect_tracks(target: Path | None) -> list[Track]:
    """Resolve the argument into a playlist: a file, a folder, or the saved one."""
    if target is not None and target.is_file():
        return [Track.from_path(target)]

    folder = target or settings_mod.load().music_folder or Path.home() / "Music"
    result = scan_folder(folder)
    print(f"  {folder}: {len(result.tracks)} playable, {len(result.skipped)} skipped")
    return list(result.tracks)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path, nargs="?", help="a folder or one .mp3")
    args = parser.parse_args()

    if args.target is not None and not args.target.exists():
        print(f"no such path: {args.target}", file=sys.stderr)
        return 1

    tracks = collect_tracks(args.target)
    if not tracks:
        print("  nothing playable here -- pass a folder or a file", file=sys.stderr)
        return 1

    saved = settings_mod.load()
    try:
        with AudioEngine(volume=saved.volume, speed=saved.speed) as engine:
            Harness(engine, tracks).run()
    except AudioDeviceError as exc:
        print(f"\naudio: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
