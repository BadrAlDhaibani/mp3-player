"""`Mixer` is the audio callback with the sound card taken away, which is the
whole reason it exists as a separate class: transport, fades, seeking, the SFX
pool and end-of-track can all be driven block by block with no device, no
threads and no real time.

`AudioEngine` itself is hardware and is exercised by `tools/engine_harness.py`.
"""

from __future__ import annotations

import numpy as np
import pytest

from mp3player.core.audio import engine as engine_mod
from mp3player.core.audio import sfx
from mp3player.core.audio.engine import Mixer, StreamWatch

SR = 48000
BLOCK = 512


def level_track(seconds: float = 10.0, level: float = 0.5, rate: int = SR):
    """A constant-amplitude track, so output level is easy to reason about."""
    return np.full((int(seconds * rate), 2), level, dtype=np.float32), rate


def pump(mixer: Mixer, blocks: int = 1, frames: int = BLOCK) -> np.ndarray:
    """Run the callback `blocks` times and return everything it produced."""
    out = []
    for _ in range(blocks):
        buffer = np.zeros((frames, 2), dtype=np.float32)
        mixer.render(buffer)
        out.append(buffer.copy())
    return np.concatenate(out)


def peak(block: np.ndarray) -> float:
    return float(np.abs(block).max())


def settle(mixer: Mixer, blocks: int = 6) -> None:
    """Run long enough for any in-flight fade or seek to complete."""
    pump(mixer, blocks)


# -- idle ----------------------------------------------------------------


def test_outputs_silence_with_nothing_loaded() -> None:
    mixer = Mixer(SR)
    assert peak(pump(mixer, 4)) == 0.0
    assert not mixer.has_track
    assert mixer.duration == 0.0
    assert mixer.position == 0.0


def test_a_loaded_but_paused_track_is_silent() -> None:
    mixer = Mixer(SR, volume=1.0)
    mixer.set_track(*level_track(), autoplay=False)
    assert mixer.has_track
    assert not mixer.is_playing
    assert peak(pump(mixer, 4)) == 0.0


def test_render_fills_the_buffer_it_is_given() -> None:
    mixer = Mixer(SR, volume=1.0)
    mixer.set_track(*level_track(), autoplay=True)
    buffer = np.zeros((BLOCK, 2), dtype=np.float32)
    mixer.render(buffer)
    assert peak(buffer) > 0.0


# -- playback ------------------------------------------------------------


def test_playing_produces_the_track_at_the_set_volume() -> None:
    mixer = Mixer(SR, volume=0.5)
    mixer.set_track(*level_track(level=0.8), autoplay=True)
    settle(mixer)
    assert peak(pump(mixer)) == pytest.approx(0.8 * 0.5, abs=0.01)


def test_playback_fades_in_rather_than_starting_at_full_level() -> None:
    mixer = Mixer(SR, volume=1.0)
    mixer.set_track(*level_track(level=0.8), autoplay=True)
    first = pump(mixer)
    assert abs(float(first[0, 0])) < 0.01
    assert float(first[-1, 0]) == pytest.approx(0.8, abs=0.01)


def test_pause_fades_out_to_real_silence() -> None:
    mixer = Mixer(SR, volume=1.0)
    mixer.set_track(*level_track(), autoplay=True)
    settle(mixer)
    mixer.pause()
    assert not mixer.is_playing
    pump(mixer, 2)  # the fade itself
    assert peak(pump(mixer, 4)) == 0.0


def test_position_advances_while_playing_and_freezes_when_paused() -> None:
    mixer = Mixer(SR, volume=1.0)
    mixer.set_track(*level_track(), autoplay=True)
    pump(mixer, 8)
    playing_at = mixer.position
    assert playing_at == pytest.approx(8 * BLOCK / SR, abs=0.01)

    mixer.pause()
    settle(mixer)
    paused_at = mixer.position
    pump(mixer, 20)
    assert mixer.position == paused_at


def test_toggle_alternates() -> None:
    mixer = Mixer(SR)
    mixer.set_track(*level_track(), autoplay=False)
    mixer.toggle()
    assert mixer.is_playing
    mixer.toggle()
    assert not mixer.is_playing


def test_play_does_nothing_without_a_track() -> None:
    mixer = Mixer(SR)
    mixer.play()
    assert not mixer.is_playing
    assert peak(pump(mixer, 4)) == 0.0


def test_clear_track_silences_and_forgets() -> None:
    mixer = Mixer(SR, volume=1.0)
    mixer.set_track(*level_track(), autoplay=True)
    settle(mixer)
    mixer.clear_track()
    assert not mixer.has_track
    assert not mixer.is_playing
    assert peak(pump(mixer, 4)) == 0.0


def test_duration_comes_from_the_file_not_the_stream() -> None:
    mixer = Mixer(SR)
    mixer.set_track(*level_track(seconds=3.0, rate=44100), autoplay=False)
    assert mixer.duration == pytest.approx(3.0, abs=0.01)


# -- speed ---------------------------------------------------------------


def test_speed_scales_how_fast_the_track_is_consumed() -> None:
    """Nightcore: 30% faster means 30% further through the track per second."""
    mixer = Mixer(SR, volume=1.0, speed=1.30)
    mixer.set_track(*level_track(), autoplay=True)
    pump(mixer, 10)
    assert mixer.position == pytest.approx(10 * BLOCK * 1.30 / SR, abs=0.01)


def test_speed_can_be_changed_mid_playback() -> None:
    mixer = Mixer(SR, volume=1.0)
    mixer.set_track(*level_track(), autoplay=True)
    pump(mixer, 4)
    halfway = mixer.position
    mixer.speed = 0.80
    pump(mixer, 4)
    assert mixer.position - halfway == pytest.approx(4 * BLOCK * 0.80 / SR, abs=0.01)


def test_a_file_at_another_rate_plays_at_the_right_speed() -> None:
    """44.1 kHz through a 48 kHz stream still takes its own duration to play."""
    mixer = Mixer(SR, volume=1.0)
    mixer.set_track(*level_track(rate=44100), autoplay=True)
    pump(mixer, 10)
    assert mixer.position == pytest.approx(10 * BLOCK / SR, abs=0.01)


# -- seeking -------------------------------------------------------------


def test_seek_lands_where_it_was_asked_to() -> None:
    mixer = Mixer(SR, volume=1.0)
    mixer.set_track(*level_track(), autoplay=True)
    settle(mixer)
    mixer.seek(5.0)
    pump(mixer, 3)
    assert mixer.position == pytest.approx(5.0, abs=0.05)
    assert mixer.is_playing


def test_seek_silences_the_music_before_it_jumps() -> None:
    """Jumping mid-waveform is a step, and a step is a click."""
    mixer = Mixer(SR, volume=1.0)
    mixer.set_track(*level_track(), autoplay=True)
    settle(mixer)
    mixer.seek(5.0)
    pump(mixer)
    assert mixer.music_gain == 0.0  # faded out, jump happens next block
    assert mixer.position < 1.0


def test_seek_while_paused_takes_effect_without_resuming() -> None:
    mixer = Mixer(SR, volume=1.0)
    mixer.set_track(*level_track(), autoplay=False)
    mixer.seek(3.0)
    pump(mixer)
    assert mixer.position == pytest.approx(3.0, abs=0.01)
    assert not mixer.is_playing
    assert peak(pump(mixer, 4)) == 0.0


def test_the_last_seek_wins_when_several_are_posted() -> None:
    """A slider drag posts a stream of these; none may be lost or reordered."""
    mixer = Mixer(SR, volume=1.0)
    mixer.set_track(*level_track(), autoplay=True)
    settle(mixer)
    for target in (2.0, 4.0, 6.0):
        mixer.seek(target)
    pump(mixer, 3)
    assert mixer.position == pytest.approx(6.0, abs=0.05)


def test_a_seek_posted_during_the_fade_out_is_not_lost() -> None:
    mixer = Mixer(SR, volume=1.0)
    mixer.set_track(*level_track(), autoplay=True)
    settle(mixer)
    mixer.seek(2.0)
    pump(mixer)  # fading out towards the 2.0 jump
    mixer.seek(8.0)
    pump(mixer, 3)
    assert mixer.position == pytest.approx(8.0, abs=0.05)


def test_seek_is_clamped_to_the_track() -> None:
    mixer = Mixer(SR, volume=1.0)
    mixer.set_track(*level_track(seconds=2.0), autoplay=False)
    mixer.seek(99.0)
    pump(mixer)
    assert 0.0 <= mixer.position <= 2.0
    mixer.seek(-5.0)
    pump(mixer)
    assert mixer.position == 0.0


def test_stop_rewinds_and_pauses() -> None:
    mixer = Mixer(SR, volume=1.0)
    mixer.set_track(*level_track(), autoplay=True)
    settle(mixer)
    mixer.stop()
    pump(mixer, 3)
    assert not mixer.is_playing
    assert mixer.position == 0.0
    assert peak(pump(mixer, 4)) == 0.0


def test_loading_a_new_track_drops_a_seek_still_in_flight() -> None:
    mixer = Mixer(SR, volume=1.0)
    mixer.set_track(*level_track(), autoplay=True)
    settle(mixer)
    mixer.seek(5.0)
    mixer.set_track(*level_track(), autoplay=True)
    pump(mixer, 3)
    assert mixer.position < 1.0


# -- end of track --------------------------------------------------------


def test_end_of_track_stops_playback_and_raises_the_flag() -> None:
    mixer = Mixer(SR, volume=1.0)
    mixer.set_track(*level_track(seconds=0.02), autoplay=True)
    pump(mixer, 4)
    assert mixer.take_finished()
    assert not mixer.is_playing


def test_the_finished_flag_is_reported_once() -> None:
    mixer = Mixer(SR, volume=1.0)
    mixer.set_track(*level_track(seconds=0.02), autoplay=True)
    pump(mixer, 4)
    assert mixer.take_finished()
    assert not mixer.take_finished()


def test_a_track_that_ended_stays_silent() -> None:
    mixer = Mixer(SR, volume=1.0)
    mixer.set_track(*level_track(seconds=0.02), autoplay=True)
    pump(mixer, 4)
    assert peak(pump(mixer, 4)) == 0.0


def test_the_end_of_a_track_is_not_a_click() -> None:
    """`resample` leaves the tail silent, so the gain can be cut for free."""
    mixer = Mixer(SR, volume=1.0)
    mixer.set_track(*level_track(seconds=0.02), autoplay=True)
    block = pump(mixer, 4)
    assert float(np.abs(np.diff(block[:, 0])).max()) < 0.05


def test_a_fresh_track_clears_the_finished_flag() -> None:
    mixer = Mixer(SR, volume=1.0)
    mixer.set_track(*level_track(seconds=0.02), autoplay=True)
    pump(mixer, 4)
    mixer.set_track(*level_track(), autoplay=True)
    assert not mixer.take_finished()


# -- sfx -----------------------------------------------------------------


def test_a_blip_is_audible_with_no_music_playing() -> None:
    mixer = Mixer(SR, volume=1.0)
    mixer.play_sfx(sfx.MOVE)
    assert peak(pump(mixer, 4)) > 0.0


def test_a_blip_is_audible_while_paused() -> None:
    """Navigation sounds must work before anything has been played."""
    mixer = Mixer(SR, volume=1.0)
    mixer.set_track(*level_track(), autoplay=False)
    mixer.play_sfx(sfx.CONFIRM)
    assert peak(pump(mixer, 4)) > 0.0


def test_a_blip_stops_when_it_is_over() -> None:
    mixer = Mixer(SR, volume=1.0)
    mixer.play_sfx(sfx.MOVE)  # ~45 ms
    pump(mixer, 12)  # ~128 ms
    assert peak(pump(mixer, 4)) == 0.0


def test_a_blip_adds_to_the_music_rather_than_replacing_it() -> None:
    mixer = Mixer(SR, volume=1.0)
    mixer.set_track(*level_track(level=0.4), autoplay=True)
    settle(mixer)
    music_only = peak(pump(mixer))
    mixer.play_sfx(sfx.CONFIRM)
    assert peak(pump(mixer)) > music_only


def test_gain_scales_a_blip() -> None:
    loud = Mixer(SR, volume=1.0)
    loud.play_sfx(sfx.MOVE, gain=1.0)
    quiet = Mixer(SR, volume=1.0)
    quiet.play_sfx(sfx.MOVE, gain=0.25)
    assert peak(pump(quiet, 4)) == pytest.approx(peak(pump(loud, 4)) * 0.25, rel=0.05)


def test_blips_overlap_instead_of_cutting_each_other_off() -> None:
    mixer = Mixer(SR, volume=1.0)
    mixer.play_sfx(sfx.MOVE)
    mixer.play_sfx(sfx.MOVE)
    assert sum(v.active for v in mixer._sfx_voices) == 2


def test_the_pool_is_bounded_and_steals_the_oldest_slot() -> None:
    """Mashing a key must not grow anything the callback walks."""
    mixer = Mixer(SR, volume=1.0, max_sfx=2)
    for _ in range(5):
        mixer.play_sfx(sfx.MOVE)
    assert len(mixer._sfx_voices) == 2
    assert sum(v.active for v in mixer._sfx_voices) == 2


def test_an_unknown_blip_name_raises_on_the_ui_thread() -> None:
    with pytest.raises(KeyError):
        Mixer(SR).play_sfx("explode")


# -- volume and headroom -------------------------------------------------


def test_volume_scales_the_whole_mix() -> None:
    mixer = Mixer(SR, volume=0.0)
    mixer.set_track(*level_track(), autoplay=True)
    mixer.play_sfx(sfx.ERROR)
    assert peak(pump(mixer, 4)) == 0.0


def test_volume_changes_are_ramped_not_stepped() -> None:
    mixer = Mixer(SR, volume=1.0)
    mixer.set_track(*level_track(level=0.5), autoplay=True)
    settle(mixer)
    mixer.volume = 0.0
    block = pump(mixer)
    assert float(np.abs(np.diff(block[:, 0])).max()) < 0.01


def test_volume_is_clamped_to_a_sane_range() -> None:
    mixer = Mixer(SR)
    mixer.volume = 5.0
    assert mixer.volume == 1.0
    mixer.volume = -1.0
    assert mixer.volume == 0.0


def test_the_mix_never_leaves_full_scale() -> None:
    """Music plus blips can sum past 1.0; wrapping would sound like distortion."""
    mixer = Mixer(SR, volume=1.0)
    mixer.set_track(*level_track(level=1.0), autoplay=True)
    settle(mixer)
    for _ in range(4):
        mixer.play_sfx(sfx.ERROR, gain=1.0)
    assert peak(pump(mixer, 4)) <= 1.0


def test_output_is_always_finite_float32() -> None:
    mixer = Mixer(SR, volume=1.0)
    mixer.set_track(*level_track(level=1.0), autoplay=True)
    mixer.play_sfx(sfx.STARTUP)
    block = pump(mixer, 8)
    assert block.dtype == np.float32
    assert np.isfinite(block).all()


def test_an_odd_block_size_is_handled() -> None:
    """PortAudio may hand us a short final block; the scratch must cope."""
    mixer = Mixer(SR, volume=1.0)
    mixer.set_track(*level_track(), autoplay=True)
    assert peak(pump(mixer, 3, frames=333)) > 0.0
    assert peak(pump(mixer, 1, frames=4096)) > 0.0


# -- the device going away -----------------------------------------------
#
# `StreamWatch` is the other half of `AudioEngine` that can be tested without a
# sound card: the stream is always on, so a block counter that stops moving is
# what an unplugged device looks like from the UI thread. Its clock is
# injectable for the same reason `Sounds.clock` is -- a test that sleeps out a
# half-second stall is a test that depends on the scheduler.


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_a_stream_that_keeps_rendering_is_never_stalled() -> None:
    clock = FakeClock()
    watch = StreamWatch(stall_s=0.5, clock=clock)
    watch.reset(0)
    for blocks in range(1, 201):
        clock.advance(0.01)
        assert not watch.stalled(blocks)


def test_a_counter_that_stops_moving_stalls_after_the_timeout() -> None:
    clock = FakeClock()
    watch = StreamWatch(stall_s=0.5, clock=clock)
    watch.reset(7)

    clock.advance(0.49)
    assert not watch.stalled(7)
    clock.advance(0.02)
    assert watch.stalled(7)


def test_the_clock_decides_not_how_often_it_is_asked() -> None:
    """Polled at 30 Hz or once, the answer must be the same."""
    clock = FakeClock()
    watch = StreamWatch(stall_s=0.5, clock=clock)
    watch.reset(3)
    for _ in range(15):
        clock.advance(0.02)
        assert not watch.stalled(3)  # 0.30 s of polling, still fine
    clock.advance(0.3)
    assert watch.stalled(3)


def test_one_late_block_clears_the_stall() -> None:
    """A device that comes back on its own is not a device that went away."""
    clock = FakeClock()
    watch = StreamWatch(stall_s=0.5, clock=clock)
    watch.reset(0)
    clock.advance(0.6)
    assert watch.stalled(0)
    assert not watch.stalled(1)  # it rendered; the timer starts over
    clock.advance(0.4)
    assert not watch.stalled(1)


# -- re-enumerating the device list --------------------------------------
#
# `refresh_devices` is two calls into *private* sounddevice API, wrapped in a
# try. What it catches is the whole of the design: a PortAudio failure is the
# expected answer while the device is still unplugged and is genuinely
# best-effort, but a rename of `_terminate` or `_initialize` used to be caught
# by the same clause -- which stopped reconnection working forever while the
# retry timer went on firing and the "audio device lost" line stayed up. The
# real PortAudio is never touched here; both calls are replaced.


def test_a_portaudio_failure_is_swallowed(monkeypatch) -> None:
    """The expected one: no worse off than before, and the reopen that follows
    fails with a real message."""

    def boom() -> None:
        raise engine_mod.sd.PortAudioError("no device to terminate")

    monkeypatch.setattr(engine_mod.sd, "_terminate", boom)
    monkeypatch.setattr(engine_mod.sd, "_initialize", lambda: None)
    engine_mod.refresh_devices()  # does not raise


def test_a_renamed_private_call_is_not_swallowed(monkeypatch) -> None:
    """The one that used to be silent. Loose, it reaches `sys.excepthook`: one
    log line, one dialog, and the retry timer keeps going regardless."""

    def gone() -> None:
        raise AttributeError("module 'sounddevice' has no attribute '_terminate'")

    monkeypatch.setattr(engine_mod.sd, "_terminate", gone)
    monkeypatch.setattr(engine_mod.sd, "_initialize", lambda: None)
    with pytest.raises(AttributeError):
        engine_mod.refresh_devices()


def test_both_halves_run_when_neither_fails(monkeypatch) -> None:
    """Order matters: terminate then initialize, or PortAudio is left down."""
    calls: list[str] = []
    monkeypatch.setattr(engine_mod.sd, "_terminate", lambda: calls.append("terminate"))
    monkeypatch.setattr(engine_mod.sd, "_initialize", lambda: calls.append("initialize"))
    engine_mod.refresh_devices()
    assert calls == ["terminate", "initialize"]


def test_detach_track_hands_back_what_was_playing() -> None:
    """What `reopen` needs to rebuild onto a new stream, in the file's own
    timeline -- so a device running at another rate changes nothing about it."""
    mixer = Mixer(SR, volume=1.0)
    samples, rate = level_track(seconds=10.0, rate=44100)
    mixer.set_track(samples, rate, autoplay=True)
    settle(mixer)
    pump(mixer, 40)

    state = mixer.detach_track()
    assert state is not None
    out_samples, out_rate, position, playing = state
    assert out_samples is samples
    assert out_rate == 44100
    assert playing is True
    assert position > 0.0
    # Taken out, not copied out.
    assert not mixer.has_track
    assert peak(pump(mixer, 2)) == 0.0


def test_detach_track_reports_a_paused_track_as_paused() -> None:
    mixer = Mixer(SR, volume=1.0)
    mixer.set_track(*level_track(), autoplay=True)
    settle(mixer)
    mixer.pause()
    settle(mixer)
    state = mixer.detach_track()
    assert state is not None and state[3] is False


def test_detach_track_with_nothing_loaded_is_none() -> None:
    assert Mixer(SR).detach_track() is None


def test_a_detached_track_can_be_put_back_click_free() -> None:
    """The reconnect path, offline: take the track out, rebuild the mixer at
    another rate, put it back where it was. No step at the joint."""
    mixer = Mixer(44100, volume=1.0)
    mixer.set_track(*level_track(seconds=10.0, level=1.0, rate=44100), autoplay=True)
    settle(mixer)
    pump(mixer, 40)

    samples, rate, position, playing = mixer.detach_track()

    blocks = 12
    rebuilt = Mixer(48000, volume=1.0)
    rebuilt.set_track(samples, rate, autoplay=playing)
    rebuilt.seek(position)
    block = pump(rebuilt, blocks)

    assert peak(block) > 0.5  # it really did come back
    # Where it left off, plus only what it has played since -- not back at the
    # top of the song, which is what a naive reload would give you.
    played = blocks * BLOCK / 48000
    assert abs(rebuilt.position - (position + played)) < 0.02
    assert float(np.abs(np.diff(block, axis=0)).max()) < 0.2  # no edge
