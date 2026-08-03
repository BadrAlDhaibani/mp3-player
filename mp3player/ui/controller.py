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

Nothing here decides what the app *sounds* like, and `play_sfx` is the only
mention of sound in the file. Batch 6 moved that to `ui/sounds.py`, because this
layer genuinely cannot tell the cases apart: `step(+1)` is a press of Next and
also the end of a track, and only one of those should blip. The window knows,
because it is the half that was pressed.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from mp3player.core import log as log_mod
from mp3player.core import settings as settings_mod
from mp3player.core.audio.decode import DecodeError
from mp3player.core.audio.engine import AudioDeviceError, AudioEngine
from mp3player.core.library import scan_folder
from mp3player.core.models import Track
from mp3player.core.settings import Settings
from mp3player.ui import theme

_log = log_mod.get("controller")

POLL_MS = 33  # ~30 Hz

# Long enough that a slider drag settles into one write, short enough that a
# hard kill right after a change rarely loses it.
SAVE_DELAY_MS = 800

SEEK_STEP = 5.0

# How often to try to get the output back after the device went away. Each
# attempt tears PortAudio down and back up to re-enumerate, which costs a
# fraction of a second on the UI thread -- fine occasionally while the app is
# already silent, not fine at 30 Hz.
RECONNECT_MS = 2000

# Late audio blocks and failed reconnects both happen on a timer, so both are
# rate-limited on the way to the log rather than written every time. The running
# total is kept regardless -- the line that does get written covers the whole gap.
XRUN_GAP_S = 10.0
RECONNECT_GAP_S = 30.0

# Short on purpose: the status line is drawn in the small font at the right edge,
# and the log is where the path and the reason go.
SAVE_FAILED_TEXT = "Could not save settings"


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
    theme_changed = Signal(str)  # the colour preset, by name
    failed = Signal(str)  # something the user should see, in one sentence
    # The output device coming and going. Separate from `failed` because it is a
    # *condition*, not an event: its message has to stay up until it stops being
    # true, and the error blip that `failed` earns must not repeat once every
    # reconnect attempt for as long as the headphones are out.
    device_changed = Signal(bool)  # True when audio is working again

    def __init__(
        self, engine: AudioEngine, saved: Settings, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self.engine = engine
        self.tracks: tuple[Track, ...] = ()
        self.index = -1

        self._folder: Path | None = saved.music_folder
        # Clamped here rather than in `core`, which has no list to clamp
        # against. Doing it on the way in means the name that gets written back
        # is always one this build can actually paint with.
        self._theme = _known_theme(saved.theme)
        # Mirrored so the poll only emits `playing_changed` on an actual edge --
        # the engine's own flag flips by itself at end of track.
        self._was_playing = engine.is_playing
        self._device_lost = False
        self._resume_on_reconnect = False
        # Mirrors of two counters that are otherwise written and never read:
        # the callback's xrun tally, and whether the last settings write worked.
        self._xruns = engine.xruns
        self._save_failed = False

        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self._poll)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(SAVE_DELAY_MS)
        self._save_timer.timeout.connect(self._save_now)

        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setInterval(RECONNECT_MS)
        self._reconnect_timer.timeout.connect(self._try_reconnect)

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        """Emit the initial state and begin polling. Call once, after wiring up.

        Deliberately after connection rather than in `__init__`: the window
        renders itself from these signals, so it must be listening first.
        """
        # Theme first: everything below computes a colour off the ramp, and the
        # ramp is what this chooses. Emitting it after `speed_changed` would
        # paint one frame in the previous palette.
        self.theme_changed.emit(self._theme)
        self.volume_changed.emit(self.engine.volume)
        self.speed_changed.emit(self.engine.speed)
        self.folder_changed.emit(self._folder)

        if self._folder is not None:
            self.open_folder(self._folder, remember=False)
        else:
            # `scan_folder` rather than a bare `ScanResult()`: the reason there
            # is no music is a thing the window renders, and "nothing has been
            # chosen yet" is the one reason that gets its own first-run screen.
            self.library_changed.emit(scan_folder(None))

        self._timer.start()

    def shutdown(self) -> None:
        """Stop polling, flush settings, close the stream. Idempotent."""
        if self._timer.isActive():
            _log.info("shutting down after %d late audio block(s)", self.engine.xruns)
        self._timer.stop()
        self._reconnect_timer.stop()
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
        # No message from here about an empty result. `library_changed` already
        # carries *why* it was empty, and the window is where that becomes a
        # sentence -- the same sentence the empty column has to print anyway.
        # Two spellings of "no music here" is how they drift apart.

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
            _log.warning("could not decode %s: %s", track.path, exc)
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
        self._set_playing(self.engine.is_playing)

    def step(self, delta: int) -> None:
        """Move `delta` tracks and play. Wraps -- the end of the list loops.

        Silent, and it has to be: this is also how auto-advance moves, and the
        end of a track is not something the user did.
        """
        if not self.tracks:
            return
        self.play_index(self.index + delta if self.index >= 0 else 0)

    def next_track(self) -> None:
        self.step(+1)

    def previous_track(self) -> None:
        self.step(-1)

    def seek(self, seconds: float) -> None:
        self.engine.seek(max(0.0, min(float(seconds), self.engine.duration)))

    def nudge(self, seconds: float) -> None:
        self.seek(self.engine.position + seconds)

    # -- sound -------------------------------------------------------------

    def play_sfx(self, name: str, gain: float = 1.0) -> None:
        """Fire a UI sound. The only route the widgets have to the engine.

        A plain forward, on purpose: *which* sound and *how often* are decided
        in `ui/sounds.py`. This exists so the rule that nothing above the seam
        touches `AudioEngine` survives the shell having a voice.
        """
        self.engine.play_sfx(name, gain)

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

    def set_theme(self, name: str) -> None:
        """The colour preset. Nothing below the seam has an opinion about it.

        The odd one out among the knobs: there is no engine attribute behind it,
        because a theme is entirely a matter of paint. It still debounces its
        save like the others.
        """
        self._theme = _known_theme(name)
        self.theme_changed.emit(self._theme)
        self._save_soon()

    @property
    def theme(self) -> str:
        return self._theme

    # -- the poll ----------------------------------------------------------

    def _poll(self) -> None:
        engine = self.engine

        if not self._device_lost and engine.stalled:
            self._on_device_lost()
            return

        self._log_xruns()

        if engine.take_finished():
            # Polled, never pushed -- see the threading rules in engine.py.
            # Advancing here means `is_playing` is true again before the edge
            # check below, so no spurious pause flickers through the UI.
            self.step(+1)

        self.position_changed.emit(engine.position, engine.duration)
        self._set_playing(engine.is_playing)

    def _log_xruns(self) -> None:
        """Notice the audio callback falling behind.

        `engine.xruns` is incremented by the audio thread and, until now, read by
        nobody -- so a stream that was glitching told you nothing except by
        sounding wrong. The mirror is only advanced when a line is actually
        written, so a rate-limited report still accounts for every block since
        the last one rather than for the ones that happened to land in a
        window.
        """
        xruns = self.engine.xruns
        if xruns != self._xruns and log_mod.due("xruns", XRUN_GAP_S):
            _log.warning(
                "%d late or dropped audio block(s), %d since launch",
                xruns - self._xruns,
                xruns,
            )
            self._xruns = xruns

    def _set_playing(self, playing: bool) -> None:
        if playing != self._was_playing:
            self._was_playing = playing
            self.playing_changed.emit(playing)

    # -- the device going away --------------------------------------------
    #
    # Headphones come out, a USB interface is unplugged, Windows switches the
    # default device. The stream stops being asked for blocks and the app goes
    # quiet with no error anywhere -- which is the worst version of this, because
    # every control still works and none of them do anything.

    @property
    def device_lost(self) -> bool:
        return self._device_lost

    def _on_device_lost(self) -> None:
        self._device_lost = True
        _log.warning(
            "audio device stopped producing blocks (%s); retrying every %.1f s",
            self.engine.device,
            RECONNECT_MS / 1000.0,
        )
        # It cannot play, so it is not playing. Banked and then actually paused,
        # rather than only reported: leaving the mixer's flag set would have the
        # next poll emit `playing_changed(True)` straight back and flicker the
        # transport button once every 33 ms.
        self._resume_on_reconnect = self.engine.is_playing
        self.engine.pause()
        self._set_playing(False)
        self.device_changed.emit(False)
        self._reconnect_timer.start()

    def _try_reconnect(self) -> None:
        """One attempt at getting the output back. Called on a slow timer.

        Failure is the expected answer while the device is still unplugged, so
        it stays quiet and waits for the next tick. Nothing here reports
        progress: an app that narrates its retries is noisier than one that
        simply starts working again.
        """
        try:
            self.engine.reopen()
        except AudioDeviceError as exc:
            # Rate-limited: this is the *expected* answer for as long as the
            # headphones are out, and at one attempt every 2 s an unattended
            # evening would otherwise be the only thing in the file.
            if log_mod.due("reconnect", RECONNECT_GAP_S):
                _log.info("still no audio device: %s", exc)
            return

        self._reconnect_timer.stop()
        self._device_lost = False
        _log.info("audio device back: %s", self.engine.device)
        if self._resume_on_reconnect:
            # Back where you left it, still going. `reopen` restored the
            # position; this restores the transport, and the fade in the mixer
            # means it arrives rather than cutting in.
            self.engine.play()
        self.device_changed.emit(True)
        self._set_playing(self.engine.is_playing)

    # -- persistence -------------------------------------------------------

    def _save_soon(self) -> None:
        self._save_timer.start()  # restarts the countdown; a drag writes once

    def _save_now(self) -> None:
        # Rebuilt from scratch every time, so anything not named here is written
        # back as its default. A new setting that isn't mirrored onto this
        # object is therefore lost 800 ms after the next volume nudge, which is
        # a bug that looks like the app forgetting rather than like a missing
        # line.
        self._save_timer.stop()
        ok = settings_mod.save(
            Settings(
                music_folder=self._folder,
                volume=self.engine.volume,
                speed=self.engine.speed,
                theme=self._theme,
            )
        )

        # `save` has always returned whether it worked and nothing has ever
        # looked. A write that fails is experienced as the app forgetting your
        # music folder for no reason -- which is the exact symptom the
        # `utf-8-sig` decision was written about, and it was only ever found by
        # hand-editing the file.
        if ok:
            if self._save_failed:
                self._save_failed = False
                _log.info("settings written again")
            return

        _log.error("could not write settings to %s", settings_mod.config_path())
        if not self._save_failed:
            # Edge-triggered. The same disk is going to fail the next write too,
            # and `failed` also blips -- a message that re-announces itself every
            # 800 ms of a volume drag is an alarm, not a notice.
            self._save_failed = True
            self.failed.emit(SAVE_FAILED_TEXT)


def _clamp(value: float, low: float, high: float) -> float:
    return min(max(float(value), low), high)


def _known_theme(name: str) -> str:
    """A palette name this build can paint with, or the default."""
    return name if name in theme.palette_names() else theme.palette_names()[0]
