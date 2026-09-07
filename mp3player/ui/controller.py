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
layer genuinely cannot tell a press from a consequence: only the window knows,
being the half that was pressed. `step` is still silent for that reason, and so
is `_advance` -- which is the same move for a different cause, and is the whole
reason the two are separate methods now that `repeat` exists.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from mp3player.core import log as log_mod
from mp3player.core import settings as settings_mod
from mp3player.core.audio.decode import DecodeError
from mp3player.core.audio.engine import NO_STATS, AudioDeviceError, AudioEngine
from mp3player.core.library import scan_folder
from mp3player.core.models import Track
from mp3player.core.settings import Settings
from mp3player.core.tags import read_art
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

# What the end of a track means. Stored as a bare name (`core/settings.py` keeps
# no list, for the same reason it keeps no list of palettes), so this is the
# list, and `_known_repeat` is the clamp -- exactly the theme's seam.
#
# The order is the cycle order, and it starts where the app has always been:
# `ALL` is Batch 3's wrapping auto-advance, unchanged and still the default.
REPEAT_ALL, REPEAT_ONE, REPEAT_OFF = "all", "one", "off"
REPEAT_MODES = (REPEAT_ALL, REPEAT_ONE, REPEAT_OFF)


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
    # The playing track's embedded cover, as the bytes that sat in the frame --
    # `None` when there is no track or it named no art. Raw bytes because the
    # `core` hands up bytes / `ui` makes pixels seam is the right one and is not
    # what moved: `core.tags` has no image library and is not allowed one, and
    # `ui` is where a frame Qt cannot decode becomes the note glyph.
    #
    # A signal rather than a property the window asks for, because *when* a track
    # changes is this object's to know. It used to be the widget that decided,
    # by calling `core.tags.read_art` itself -- file I/O and a full ID3 parse
    # performed above the one seam this project is built around.
    art_changed = Signal(object)  # bytes | None
    position_changed = Signal(float, float)  # position, duration (seconds)
    playing_changed = Signal(bool)
    speed_changed = Signal(float)
    volume_changed = Signal(float)
    theme_changed = Signal(str)  # the colour preset, by name
    shuffle_changed = Signal(bool)
    repeat_changed = Signal(str)  # one of REPEAT_MODES
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
        self._shuffle = bool(saved.shuffle)
        # Clamped here for the same reason and against the same kind of list.
        self._repeat = _known_repeat(saved.repeat)
        # The shuffled play order, as a permutation of *indices* into `tracks`.
        # Not a reordering of `tracks` itself: everything above this object
        # addresses a track by its index -- `track_changed(int)`, the Music
        # column's cursor, the "Track 4 of 31" line -- so shuffling the tuple
        # would desync all of it. The list on screen stays in scan order and
        # only the meaning of "next" moves.
        self._order: list[int] = []
        self._cursor = -1
        # Mirrored so the poll only emits `playing_changed` on an actual edge --
        # the engine's own flag flips by itself at end of track.
        self._was_playing = engine.is_playing
        self._device_lost = False
        self._resume_on_reconnect = False
        # Mirrors of two counters that are otherwise written and never read:
        # the callback's xrun tally, and whether the last settings write worked.
        self._xruns = engine.xruns
        self._save_failed = False
        # The audio-health report. `_pending` accumulates every poll and is
        # cleared when a line is actually written; `_since` is where the last
        # line's interval started, which is what makes the shortfall meaningful
        # (see `_log_xruns`). The `_worst_*` mirrors cover the whole launch, so
        # the shutdown line describes the session rather than the last window.
        self._pending = NO_STATS
        self._since = (engine.rendered_s, log_mod.clock())
        self._lost_s = 0.0
        self._worst_slack_ms = math.inf
        self._worst_peak = 0.0

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
        self.shuffle_changed.emit(self._shuffle)
        self.repeat_changed.emit(self._repeat)
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
            stats = self.engine.take_stats()
            _log.info(
                "shutting down after %d late audio block(s), least headroom %.1f ms, "
                "peak %.2f",
                self.engine.xruns,
                min(self._worst_slack_ms, stats.min_slack_ms),
                max(self._worst_peak, stats.peak),
            )
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
        # A permutation of the *old* library is nonsense against the new one,
        # and half of it would point past the end. Rebuilt from nothing here,
        # which is also what makes a rescan reshuffle.
        self._reshuffle()

        self.folder_changed.emit(self._folder)
        self.library_changed.emit(result)
        self.track_changed.emit(-1)
        self.art_changed.emit(None)
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
        # Whatever put us on this track -- a click in Music, Next, the end of
        # the previous one -- the shuffled order now walks on from *here*. Pick
        # track 12 by hand with shuffle on and press Next, and without this the
        # next track has nothing to do with the one you chose.
        self._cursor = self._order.index(index) if index in self._order else -1
        self.track_changed.emit(index)
        # The one place a cover is read, and the reason it is cheap is the line
        # above it: the decode has just cost 70-210 ms on this library and the
        # art costs 0.2-11 ms, so it disappears into a wait that already
        # existed. That is why it belongs on the track change rather than on
        # anything that merely repaints -- and why `Track` still does not carry
        # one (decisions log: art is fetched, never carried).
        self.art_changed.emit(read_art(track.path))
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
        """Move `delta` tracks and play. Always wraps, whatever `repeat` says.

        Silent, and it has to be: the window is the half that knows a press
        happened, so `_skip` blips and this does not.

        It used to be the auto-advance path as well. It is not any more --
        `_advance` is -- because the two want different things the moment
        `repeat` exists: running off the last track under `Repeat: Off` should
        stop, and running off it because you pressed Next should not. Pressing
        a button is an explicit request; reaching the end of a file is not.
        Repeat-one is the same argument from the other side: it must not trap
        the Next button on one track.
        """
        if not self.tracks:
            return
        index, _wrapped = self._next_index(delta)
        self.play_index(index)

    def next_track(self) -> None:
        self.step(+1)

    def previous_track(self) -> None:
        self.step(-1)

    def restart(self) -> None:
        """Play the current track again from the top, without re-decoding it.

        The order of these two lines is the whole method. At the end of a track
        the mixer has already set its own `_playing` false and jumped the music
        fader to zero, and `_apply_pending_seek` runs *ahead* of the fader's
        silent early return -- so a seek posted while the gain is zero is
        applied on the very next block and ramps back in cleanly. Calling
        `play()` first would let a callback render one more block from the end
        of the file, which re-arms `_finished` and advances twice.

        `play_index(self.index)` would also work and would cost the full 70-210
        ms decode again, on every loop, for a file that is already in memory.
        """
        if not self.engine.has_track:
            return
        self.engine.seek(0.0)
        self.engine.play()
        self._set_playing(self.engine.is_playing)

    # -- what "next" means -------------------------------------------------

    def _reshuffle(self, *, lead: int | None = None, avoid: int | None = None) -> None:
        """Deal a fresh permutation of the library into `_order`.

        `lead` pins an index to the front and `avoid` keeps one off it -- the
        two ends of the same question, asked by the two callers. Turning shuffle
        on mid-track leads with the track you are listening to, so nothing jumps
        and the bag then lasts a full library rather than however much of the
        permutation happened to fall after you. Running the bag empty avoids the
        track that just played, so a reshuffle cannot hand you the same song
        twice in a row -- the one coincidence that reads as the feature being
        broken rather than as chance.
        """
        self._order = list(range(len(self.tracks)))
        random.shuffle(self._order)
        if lead is not None and lead in self._order:
            here = self._order.index(lead)
            self._order[0], self._order[here] = self._order[here], self._order[0]
        elif avoid is not None and len(self._order) > 1 and self._order[0] == avoid:
            # One swap, not a re-deal: rejection sampling on a one-in-N event
            # is fine until N is 1, and this is exact at every N.
            self._order[0], self._order[-1] = self._order[-1], self._order[0]
        self._cursor = self._order.index(self.index) if self.index in self._order else -1

    def _next_index(self, delta: int) -> tuple[int, bool]:
        """The index `delta` steps from here, and whether getting there wrapped.

        The second half is the only thing `Repeat: Off` is asking about, and it
        cannot be recovered afterwards -- `play_index` folds any index back into
        range, which is exactly the behaviour that has to be *noticed* here
        before it happens.
        """
        # Nothing loaded yet: the top of the list, and that is not a wrap.
        if self.index < 0:
            return 0, False

        if self._shuffle and self._order:
            order, position = self._order, self._cursor + delta
            return order[position % len(order)], not 0 <= position < len(order)

        count, position = len(self.tracks), self.index + delta
        return position % count, not 0 <= position < count

    def _advance(self) -> None:
        """End of track. The only caller is `_poll`, and that is the point.

        Nobody pressed anything, so this is where `repeat` gets to have an
        opinion -- see `step` for why the two are not the same path.
        """
        if not self.tracks:
            return

        if self._repeat == REPEAT_ONE:
            self.restart()
            return

        index, wrapped = self._next_index(+1)
        if wrapped:
            if self._repeat == REPEAT_OFF:
                # Nothing to do, deliberately. The mixer paused itself when the
                # voice ran out, so the `_set_playing` edge at the bottom of the
                # poll reports the stop without this having to say anything.
                return
            if self._shuffle:
                self._reshuffle(avoid=self.index)
                index = self._order[0]
        self.play_index(index)

    @property
    def shuffle(self) -> bool:
        return self._shuffle

    @property
    def repeat(self) -> str:
        return self._repeat

    def set_shuffle(self, on: bool) -> None:
        """Whether "next" walks a shuffled order. Turning it on deals a new one.

        Dealing on the way *in* rather than at every advance is what makes the
        order stable enough to walk backwards through: Previous is the track you
        actually just heard, not another roll of the dice.
        """
        on = bool(on)
        if on:
            self._reshuffle(lead=self.index)
        self._shuffle = on
        self.shuffle_changed.emit(on)
        self._save_soon()

    def toggle_shuffle(self) -> None:
        self.set_shuffle(not self._shuffle)

    def set_repeat(self, mode: str) -> None:
        self._repeat = _known_repeat(mode)
        self.repeat_changed.emit(self._repeat)
        self._save_soon()

    def cycle_repeat(self) -> None:
        """The next mode round, wrapping. One press is one step.

        Not a stepped-into row like Theme, and the difference is what the two
        are for: a palette is a *comparison* you make by looking, where these
        are three states you already know the names of. It is also the only
        thing a single click of the transport button can mean, and a row that
        behaved differently from its own button would be the inconsistency.
        """
        here = REPEAT_MODES.index(self._repeat)
        self.set_repeat(REPEAT_MODES[(here + 1) % len(REPEAT_MODES)])

    # -- seeking -----------------------------------------------------------

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
            # check below, so no spurious pause flickers through the UI -- and
            # under `Repeat: Off` the same ordering is what lets `_advance` do
            # nothing at all and have the stop reported for it.
            self._advance()

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

        `xruns` alone turned out not to be enough. It counts what *PortAudio*
        noticed, and on WASAPI it frequently notices nothing while the stream is
        audibly popping -- every session logged `0 late audio block(s)` while the
        app crackled. `take_stats()` measures the thing that actually goes wrong:
        a Python callback that did not get the GIL in time. Both are reported,
        because a disagreement between them is itself the diagnosis.
        """
        xruns = self.engine.xruns
        if xruns != self._xruns and log_mod.due("xruns", XRUN_GAP_S):
            _log.warning(
                "%d late or dropped audio block(s), %d since launch (%s)",
                xruns - self._xruns,
                xruns,
                self.engine.status_flags or "no flag",
            )
            self._xruns = xruns

        # Drained on every poll, whatever gets logged. The engine's window is
        # only ever as long as one poll, so what accumulates here is what the
        # throttled line reports -- the same discipline as the mirror above, for
        # the same reason: a rate limit that also *discards* is a rate limit
        # that lies about the rate.
        self._pending = self._pending.plus(self.engine.take_stats())
        self._worst_slack_ms = min(self._worst_slack_ms, self._pending.min_slack_ms)
        self._worst_peak = max(self._worst_peak, self._pending.peak)

        lost_s, quiet = self._audio_shortfall()
        if not (quiet and self._pending.quiet) and log_mod.due("jitter", XRUN_GAP_S):
            _log.warning(
                "audio: %.0f ms lost, least headroom %.1f ms, worst render %.2f ms, "
                "peak %.2f",
                lost_s * 1000.0,
                self._pending.min_slack_ms,
                self._pending.max_render_ms,
                self._pending.peak,
            )
            self._pending = NO_STATS

    def _audio_shortfall(self) -> tuple[float, bool]:
        """Seconds of audio never rendered since the last report, and whether
        that is small enough to say nothing about.

        The measure the batch was rebuilt around, because it is the only one
        that survived a real machine. A starved callback is not called late, it
        is *not called at all*, so the block it would have filled is simply
        never made -- and wall time minus rendered time is exactly the audio the
        user lost. `xruns` misses it entirely (PortAudio never raised a flag in
        any session) and so does a gap counter (a 512-frame block against a
        480-frame host period makes long gaps structural, six a second, forever).

        Measured over the whole reporting interval rather than per poll on
        purpose: a poll spans about three blocks, so rounding to whole blocks is
        +/-10.7 ms of noise on a 33 ms window, and clamping that at zero every
        time would manufacture a shortfall out of it. Over ten seconds the same
        rounding is a tenth of a percent.
        """
        rendered, since = self._since
        now = log_mod.clock()
        elapsed = now - since
        if elapsed < XRUN_GAP_S:
            return self._lost_s, True

        lost = max(0.0, elapsed - (self.engine.rendered_s - rendered))
        self._since = (self.engine.rendered_s, now)
        self._lost_s = lost
        # A block and a half of slop over ten seconds is the quantisation and a
        # reopen, not a fault. Below that there is nothing to report.
        return lost, lost < 0.02

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
                shuffle=self._shuffle,
                repeat=self._repeat,
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


def _known_repeat(name: str) -> str:
    """A repeat mode this build knows what to do with, or the default."""
    return name if name in REPEAT_MODES else REPEAT_ALL
