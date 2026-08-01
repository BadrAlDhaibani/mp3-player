"""The seam between `core/` and the widgets.

Everything about *playing* lives here: the window says what the user did, the
controller does it to the engine, and engine state comes back out as signals.
No widget ever touches `AudioEngine` -- which is the whole point, because Batch 4
throws the window away and keeps this file.

Two rules from CLAUDE.md land here in particular:

  * The UI polls the engine at 30 Hz. Nothing is ever pushed from the audio
    thread, so `_poll` is the only place engine state is read while audio runs.
  * Settings are written after a pause, not on every slider tick -- a volume
    drag emits a change per pixel and none of them deserve a disk write.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from mp3player.core import settings as settings_mod
from mp3player.core.audio import sfx
from mp3player.core.audio.decode import DecodeError
from mp3player.core.audio.engine import AudioEngine
from mp3player.core.library import ScanResult, scan_folder
from mp3player.core.models import Track
from mp3player.core.settings import Settings

POLL_MS = 33  # ~30 Hz

# Long enough that a slider drag settles into one write, short enough that a
# hard kill right after a change rarely loses it.
SAVE_DELAY_MS = 800

SEEK_STEP = 5.0


class PlayerController(QObject):
    """Owns the playlist and drives the engine.

    Construct with an already-started `AudioEngine` and the settings it was
    built from, connect the signals, then call `start()`.
    """

    # `object` rather than a registered type: these carry plain Python values
    # (ScanResult, Path) that Qt has no meta-type for.
    library_changed = Signal(object)  # ScanResult
    folder_changed = Signal(object)  # Path | None
    track_changed = Signal(int)  # index into `tracks`, -1 for none
    position_changed = Signal(float, float)  # position, duration (seconds)
    playing_changed = Signal(bool)
    speed_changed = Signal(float)
    volume_changed = Signal(float)
    failed = Signal(str)  # something the user should see, in one sentence

    def __init__(
        self, engine: AudioEngine, saved: Settings, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self.engine = engine
        self.tracks: tuple[Track, ...] = ()
        self.index = -1

        self._folder: Path | None = saved.music_folder
        # Mirrored so the poll only emits `playing_changed` on an actual edge --
        # the engine's own flag flips by itself at end of track.
        self._was_playing = engine.is_playing

        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self._poll)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(SAVE_DELAY_MS)
        self._save_timer.timeout.connect(self._save_now)

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        """Emit the initial state and begin polling. Call once, after wiring up.

        Deliberately after connection rather than in `__init__`: the window
        renders itself from these signals, so it must be listening first.
        """
        self.volume_changed.emit(self.engine.volume)
        self.speed_changed.emit(self.engine.speed)
        self.folder_changed.emit(self._folder)

        if self._folder is not None:
            self.open_folder(self._folder, remember=False)
        else:
            self.library_changed.emit(ScanResult())

        self._timer.start()
        self.engine.play_sfx(sfx.STARTUP)

    def shutdown(self) -> None:
        """Stop polling, flush settings, close the stream. Idempotent."""
        self._timer.stop()
        self._save_now()
        self.engine.close()

    # -- library -----------------------------------------------------------

    def open_folder(self, folder: Path | str, *, remember: bool = True) -> None:
        """Scan `folder` and make it the playlist. Nothing starts playing.

        `remember=False` is for the folder we just restored from disk -- it is
        already saved, and rewriting it on every launch is noise.
        """
        result = scan_folder(folder)

        self.engine.clear()
        self._folder = Path(folder)
        self.tracks = result.tracks
        self.index = -1

        self.folder_changed.emit(self._folder)
        self.library_changed.emit(result)
        self.track_changed.emit(-1)
        self.position_changed.emit(0.0, 0.0)
        self._set_playing(False)

        if remember:
            self._save_soon()
        if not result.tracks:
            self.engine.play_sfx(sfx.ERROR)
            self.failed.emit(f"No playable MP3s in {self._folder}")

    def rescan(self) -> None:
        """Re-read the current folder -- files may have come or gone."""
        if self._folder is not None:
            self.open_folder(self._folder, remember=False)

    @property
    def folder(self) -> Path | None:
        return self._folder

    @property
    def current(self) -> Track | None:
        if 0 <= self.index < len(self.tracks):
            return self.tracks[self.index]
        return None

    # -- transport ---------------------------------------------------------

    def play_index(self, index: int) -> None:
        """Load and play the track at `index`, wrapping out-of-range values.

        Decoding is synchronous -- about 0.2 s for a four-minute file, measured
        on this library -- so this blocks the UI thread for that long. Tolerable
        at Batch 3's fidelity; moving it to a worker is a self-contained change
        if it starts to grate.
        """
        if not self.tracks:
            return
        index %= len(self.tracks)
        track = self.tracks[index]

        try:
            self.engine.load_path(track.path)
        except DecodeError as exc:
            # `scan_folder` already sniffed the magic bytes, so reaching here
            # means truncated or genuinely broken -- not the usual mislabelled
            # MP4. Leave the selection alone and say so.
            self.engine.play_sfx(sfx.ERROR)
            self.failed.emit(f"Could not play {track.title}: {exc}")
            return

        self.index = index
        self.track_changed.emit(index)
        self.position_changed.emit(self.engine.position, self.engine.duration)
        self._set_playing(self.engine.is_playing)

    def toggle(self) -> None:
        """Play/pause. With nothing loaded, start at the top of the list."""
        if not self.engine.has_track:
            self.play_index(0)
            return
        self.engine.toggle()
        self.engine.play_sfx(sfx.CONFIRM if self.engine.is_playing else sfx.BACK)
        self._set_playing(self.engine.is_playing)

    def step(self, delta: int) -> None:
        """Move `delta` tracks and play. Wraps -- the end of the list loops."""
        if not self.tracks:
            return
        self.engine.play_sfx(sfx.MOVE)
        self.play_index(self.index + delta if self.index >= 0 else 0)

    def next_track(self) -> None:
        self.step(+1)

    def previous_track(self) -> None:
        self.step(-1)

    def seek(self, seconds: float) -> None:
        self.engine.seek(max(0.0, min(float(seconds), self.engine.duration)))

    def nudge(self, seconds: float) -> None:
        self.seek(self.engine.position + seconds)

    # -- knobs -------------------------------------------------------------

    def set_speed(self, value: float) -> None:
        value = _clamp(value, settings_mod.MIN_SPEED, settings_mod.MAX_SPEED)
        self.engine.speed = value
        self.speed_changed.emit(value)
        self._save_soon()

    def set_volume(self, value: float) -> None:
        value = _clamp(value, settings_mod.MIN_VOLUME, settings_mod.MAX_VOLUME)
        self.engine.volume = value
        self.volume_changed.emit(value)
        self._save_soon()

    # -- the poll ----------------------------------------------------------

    def _poll(self) -> None:
        engine = self.engine

        if engine.take_finished():
            # Polled, never pushed -- see the threading rules in engine.py.
            # Advancing here means `is_playing` is true again before the edge
            # check below, so no spurious pause flickers through the UI.
            self.step(+1)

        self.position_changed.emit(engine.position, engine.duration)
        self._set_playing(engine.is_playing)

    def _set_playing(self, playing: bool) -> None:
        if playing != self._was_playing:
            self._was_playing = playing
            self.playing_changed.emit(playing)

    # -- persistence -------------------------------------------------------

    def _save_soon(self) -> None:
        self._save_timer.start()  # restarts the countdown; a drag writes once

    def _save_now(self) -> None:
        self._save_timer.stop()
        settings_mod.save(
            Settings(
                music_folder=self._folder,
                volume=self.engine.volume,
                speed=self.engine.speed,
            )
        )


def _clamp(value: float, low: float, high: float) -> float:
    return min(max(float(value), low), high)
