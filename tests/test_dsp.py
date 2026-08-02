"""The resampler is where nightcore actually happens, so test it as a pitch
shifter -- not just as array arithmetic. Fades are tested for the property that
matters: no step big enough to click.
"""

from __future__ import annotations

import numpy as np
import pytest

from mp3player.core.audio.dsp import (
    FADE_MS,
    Fader,
    fade_before_end,
    fade_frames,
    resample,
)

SR = 48000


def tone(freq: float, seconds: float, sample_rate: int = SR) -> np.ndarray:
    t = np.arange(int(seconds * sample_rate), dtype=np.float32) / sample_rate
    mono = np.sin(2 * np.pi * freq * t, dtype=np.float32)
    return np.repeat(mono[:, None], 2, axis=1)


def dominant_hz(block: np.ndarray, sample_rate: int = SR) -> float:
    """Loudest frequency in the left channel."""
    spectrum = np.abs(np.fft.rfft(block[:, 0]))
    return float(np.fft.rfftfreq(len(block), 1 / sample_rate)[spectrum.argmax()])


# -- resample ------------------------------------------------------------


def test_ratio_one_reproduces_the_input() -> None:
    samples = tone(440, 0.1)
    block, pos, valid = resample(samples, 0.0, 1024, 1.0)
    assert np.allclose(block, samples[:1024], atol=1e-6)
    assert pos == 1024.0
    assert valid == 1024


def test_output_is_canonical_shape_and_dtype() -> None:
    block, _, _ = resample(tone(440, 0.1), 0.0, 512, 1.3)
    assert block.shape == (512, 2)
    assert block.dtype == np.float32


def test_speeding_up_raises_pitch() -> None:
    """1.30x on a 440 Hz tone is 572 Hz -- the Batch 0 number."""
    samples = tone(440, 2.0)
    block, _, _ = resample(samples, 0.0, SR, 1.30)
    assert dominant_hz(block) == pytest.approx(572, abs=2)


def test_slowing_down_lowers_pitch() -> None:
    samples = tone(440, 2.0)
    block, _, _ = resample(samples, 0.0, SR, 0.80)
    assert dominant_hz(block) == pytest.approx(352, abs=2)


def test_ratio_folds_in_sample_rate_conversion() -> None:
    """A 44.1 kHz file played at 1.0x through a 48 kHz stream keeps its pitch."""
    samples = tone(440, 2.0, sample_rate=44100)
    block, _, _ = resample(samples, 0.0, SR, 1.0 * (44100 / 48000))
    assert dominant_hz(block, SR) == pytest.approx(440, abs=2)


def test_position_advances_by_frames_times_ratio() -> None:
    samples = tone(440, 1.0)
    _, pos, _ = resample(samples, 100.0, 512, 1.3)
    assert pos == pytest.approx(100.0 + 512 * 1.3)


def test_changing_ratio_between_blocks_is_continuous() -> None:
    """Speed can be reassigned at any moment; the seam must not be a step."""
    samples = tone(440, 1.0)
    first, pos, _ = resample(samples, 0.0, 512, 1.0)
    second, _, _ = resample(samples, pos, 512, 1.3)
    seam = abs(float(second[0, 0]) - float(first[-1, 0]))
    within_block = float(np.abs(np.diff(first[:, 0])).max())
    assert seam <= within_block * 2


def test_reports_how_much_of_the_block_is_real_audio() -> None:
    samples = tone(440, 0.01)  # 480 frames
    _, _, valid = resample(samples, 0.0, 512, 1.0)
    assert valid == 479  # the last frame has nothing to interpolate towards


def test_tail_past_the_end_is_silence_not_a_held_sample() -> None:
    """A held final sample is a DC step, and a DC step is a click."""
    samples = tone(440, 0.01)
    block, _, valid = resample(samples, 0.0, 1024, 1.0)
    assert valid < 1024
    assert np.all(block[valid:] == 0.0)


def test_starting_past_the_end_yields_silence() -> None:
    samples = tone(440, 0.01)
    block, _, valid = resample(samples, 10_000.0, 512, 1.0)
    assert valid == 0
    assert np.all(block == 0.0)


def test_zero_frames_is_harmless() -> None:
    block, pos, valid = resample(tone(440, 0.1), 7.0, 0, 1.3)
    assert len(block) == 0
    assert pos == 7.0
    assert valid == 0


def test_too_short_to_interpolate_is_silence() -> None:
    block, _, valid = resample(np.zeros((1, 2), np.float32), 0.0, 64, 1.0)
    assert valid == 0
    assert np.all(block == 0.0)


def test_negative_ratio_does_not_run_backwards() -> None:
    samples = tone(440, 0.5)
    block, pos, _ = resample(samples, 1000.0, 256, -1.0)
    assert pos == 1000.0
    assert np.all(block == block[0])  # frozen, not reversed


def test_writes_into_a_supplied_buffer() -> None:
    samples = tone(440, 0.5)
    out = np.full((256, 2), 9.0, dtype=np.float32)
    block, _, _ = resample(samples, 0.0, 256, 1.0, out=out)
    assert block is out
    assert not np.any(out == 9.0)


def test_supplied_buffer_is_cleared_past_the_end() -> None:
    """Reused scratch must not leak the previous block into the tail."""
    samples = tone(440, 0.01)  # 480 frames
    out = np.full((1024, 2), 9.0, dtype=np.float32)
    _, _, valid = resample(samples, 0.0, 1024, 1.0, out=out)
    assert np.all(out[valid:] == 0.0)


# -- fade_before_end -----------------------------------------------------

SIZE = 512  # the mixer's block, so the boundaries here are the real ones


def ending_gain(last: int, *, length: int = 480, ratio: float = 1.0, blocks: int = 6):
    """The gain the ending fade applies, over `blocks` consecutive blocks.

    Rendered block by block exactly as the callback would, and then joined --
    because the whole question about this fade is what it does *across* a block
    boundary, and one block at a time cannot answer it.
    """
    rendered = []
    for index in range(blocks):
        block = np.ones((SIZE, 2), np.float32)
        fade_before_end(block, index * SIZE * ratio, ratio, last, length)
        rendered.append(block)
    return np.concatenate(rendered)[:, 0]


def test_the_ending_fade_reaches_zero_exactly_as_the_samples_run_out() -> None:
    gain = ending_gain(last=3 * SIZE)
    assert gain[3 * SIZE] == pytest.approx(0.0, abs=1e-6)
    assert np.all(gain[3 * SIZE :] == 0.0)
    assert gain[0] == 1.0  # untouched a long way out


@pytest.mark.parametrize("offset", (0, 1, 37, 200, 400, 511))
def test_the_ending_fade_is_its_full_length_wherever_the_end_lands(offset: int) -> None:
    """The Batch 6 bug, in one assertion.

    A ramp that can only live inside the final block is as long as whatever is
    left of that block: ten milliseconds when the track happens to end on a
    boundary and *one sample* when it ends just after one. Written against the
    read position instead, the ramp is the length it asks for and simply starts
    in an earlier block when it needs to.
    """
    length = 480
    gain = ending_gain(last=3 * SIZE + offset, length=length)
    ramping = np.count_nonzero((gain > 0.0) & (gain < 1.0))
    assert ramping == pytest.approx(length, abs=2), f"ramp was {ramping} frames"


def test_the_ending_fade_has_no_step_of_its_own() -> None:
    gain = ending_gain(last=3 * SIZE + 1)  # the alignment that used to click
    assert np.abs(np.diff(gain)).max() <= 1.0 / 480 * 1.01


def test_blocks_nowhere_near_the_end_are_left_alone() -> None:
    """The early-out. This runs in the audio callback on every block."""
    block = np.ones((SIZE, 2), np.float32)
    fade_before_end(block, 0.0, 1.0, 48000, 480)
    assert np.all(block == 1.0)


def test_a_stopped_read_does_not_divide_by_its_own_rate() -> None:
    block = np.ones((SIZE, 2), np.float32)
    fade_before_end(block, 0.0, 0.0, 100, 480)
    assert np.all(block == 1.0)


# -- Fader ---------------------------------------------------------------


def test_fade_length_matches_the_configured_milliseconds() -> None:
    assert fade_frames(48000, 10.0) == 480
    assert fade_frames(44100, FADE_MS) == 441
    assert fade_frames(48000, 0.0) == 1  # never zero, so the rate stays finite


def test_starts_at_the_gain_it_was_given() -> None:
    fader = Fader(SR, gain=0.5)
    block = np.ones((10, 2), np.float32)
    fader.apply(block)
    assert np.allclose(block, 0.5)
    assert fader.idle


def test_ramp_reaches_the_target_within_the_fade_time() -> None:
    fader = Fader(SR, ms=10.0, gain=0.0)
    fader.ramp_to(1.0)
    fader.apply(np.ones((fade_frames(SR, 10.0), 2), np.float32))
    assert fader.gain == pytest.approx(1.0)
    assert fader.idle


def test_ramp_does_not_arrive_early() -> None:
    fader = Fader(SR, ms=10.0, gain=0.0)
    fader.ramp_to(1.0)
    fader.apply(np.ones((240, 2), np.float32))  # half the fade
    assert fader.gain == pytest.approx(0.5, abs=0.01)
    assert not fader.idle


def test_ramp_never_overshoots() -> None:
    fader = Fader(SR, ms=10.0, gain=0.0)
    fader.ramp_to(1.0)
    block = np.ones((4096, 2), np.float32)  # far longer than the fade
    fader.apply(block)
    assert block.max() <= 1.0
    assert fader.gain == pytest.approx(1.0)


def test_fade_out_ends_in_silence() -> None:
    fader = Fader(SR, ms=10.0, gain=1.0)
    fader.ramp_to(0.0)
    block = np.ones((1024, 2), np.float32)
    fader.apply(block)
    assert fader.gain == 0.0
    assert block[-1].max() == 0.0


def test_fade_introduces_no_step_large_enough_to_click() -> None:
    """The point of the whole class: consecutive gains stay close together."""
    fader = Fader(SR, ms=10.0, gain=0.0)
    fader.ramp_to(1.0)
    block = np.ones((2048, 2), np.float32)
    fader.apply(block)
    assert np.abs(np.diff(block[:, 0])).max() < 0.01


def test_ramp_is_continuous_across_blocks() -> None:
    fader = Fader(SR, ms=10.0, gain=0.0)
    fader.ramp_to(1.0)
    first = np.ones((100, 2), np.float32)
    second = np.ones((100, 2), np.float32)
    fader.apply(first)
    fader.apply(second)
    assert float(second[0, 0]) > float(first[-1, 0])
    assert float(second[0, 0]) - float(first[-1, 0]) < 0.01


def test_retargeting_mid_ramp_turns_around_from_where_it_is() -> None:
    fader = Fader(SR, ms=10.0, gain=0.0)
    fader.ramp_to(1.0)
    fader.apply(np.ones((240, 2), np.float32))
    midpoint = fader.gain
    fader.ramp_to(0.0)
    fader.apply(np.ones((10, 2), np.float32))
    assert 0.0 < fader.gain < midpoint


def test_jump_to_moves_gain_and_target_together() -> None:
    fader = Fader(SR, gain=1.0)
    fader.ramp_to(0.0)
    fader.jump_to(0.0)
    assert fader.idle and fader.silent


def test_silent_means_at_zero_and_going_nowhere() -> None:
    fader = Fader(SR, gain=0.0)
    assert fader.silent
    fader.ramp_to(1.0)
    assert not fader.silent


def test_apply_returns_the_same_array_it_scaled() -> None:
    fader = Fader(SR, gain=0.5)
    block = np.ones((32, 2), np.float32)
    assert fader.apply(block) is block


def test_empty_block_is_harmless() -> None:
    fader = Fader(SR, gain=0.0)
    fader.ramp_to(1.0)
    fader.apply(np.zeros((0, 2), np.float32))
    assert fader.gain == 0.0
