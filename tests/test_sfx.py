"""UI sounds are generated, so the things worth asserting are the invariants a
mixer depends on: canonical shape, bounded level, and silence at both ends.
Whether they sound *good* is an ear question, not a test question.
"""

from __future__ import annotations

import numpy as np
import pytest

from mp3player.core.audio import sfx

SR = 48000


def dominant_hz(sound: np.ndarray, sample_rate: int = SR) -> float:
    spectrum = np.abs(np.fft.rfft(sound[:, 0]))
    return float(np.fft.rfftfreq(len(sound), 1 / sample_rate)[spectrum.argmax()])


@pytest.mark.parametrize("name", sfx.NAMES)
def test_every_sound_is_a_canonical_stereo_buffer(name: str) -> None:
    sound = sfx.render(name, SR)
    assert sound.ndim == 2 and sound.shape[1] == 2
    assert sound.dtype == np.float32
    assert sound.flags["C_CONTIGUOUS"]


@pytest.mark.parametrize("name", sfx.NAMES)
def test_every_sound_is_finite_and_below_full_scale(name: str) -> None:
    sound = sfx.render(name, SR)
    assert np.isfinite(sound).all()
    peak = float(np.abs(sound).max())
    assert 0.0 < peak <= 0.5  # audible, but leaves headroom over the music


@pytest.mark.parametrize("name", sfx.NAMES)
def test_every_sound_starts_and_ends_at_silence(name: str) -> None:
    """Click-free by construction: no step into or out of the sound."""
    sound = sfx.render(name, SR)
    assert abs(float(sound[0].max())) < 1e-6
    assert abs(float(sound[-1].max())) < 1e-6


@pytest.mark.parametrize("name", sfx.NAMES)
def test_every_sound_is_short_enough_to_feel_immediate(name: str) -> None:
    seconds = len(sfx.render(name, SR)) / SR
    limit = 1.5 if name == sfx.STARTUP else 0.30
    assert 0.01 < seconds <= limit


def test_move_is_the_quietest_since_you_hear_it_constantly() -> None:
    peaks = {n: float(np.abs(sfx.render(n, SR)).max()) for n in sfx.NAMES}
    assert peaks[sfx.MOVE] == min(peaks.values())


def test_move_sits_where_it_was_designed_to() -> None:
    assert dominant_hz(sfx.render(sfx.MOVE, SR)) == pytest.approx(1180, rel=0.15)


def test_confirm_rises_and_back_falls() -> None:
    """The pair should read as opposites -- opening versus closing."""
    for name, ascending in ((sfx.CONFIRM, True), (sfx.BACK, False)):
        sound = sfx.render(name, SR)
        third = len(sound) // 3
        start = dominant_hz(sound[:third])
        end = dominant_hz(sound[third : 2 * third])
        assert (end > start) is ascending


def test_startup_is_wider_than_mono() -> None:
    sound = sfx.render(sfx.STARTUP, SR)
    assert not np.allclose(sound[:, 0], sound[:, 1])


def test_blips_are_mono_across_the_channels() -> None:
    for name in (sfx.MOVE, sfx.CONFIRM, sfx.BACK, sfx.ERROR):
        sound = sfx.render(name, SR)
        assert np.allclose(sound[:, 0], sound[:, 1])


def test_sample_rate_sets_the_length_not_the_pitch() -> None:
    at_44k = sfx.render(sfx.MOVE, 44100)
    at_48k = sfx.render(sfx.MOVE, 48000)
    assert len(at_44k) / 44100 == pytest.approx(len(at_48k) / 48000, rel=0.01)
    assert dominant_hz(at_44k, 44100) == pytest.approx(
        dominant_hz(at_48k, 48000), rel=0.05
    )


def test_a_very_low_rate_still_produces_something_playable() -> None:
    sound = sfx.render(sfx.MOVE, 8000)
    assert len(sound) > 0
    assert np.isfinite(sound).all()


def test_unknown_name_says_what_the_options_are() -> None:
    with pytest.raises(KeyError, match="move"):
        sfx.render("explode", SR)


# -- SfxBank -------------------------------------------------------------


def test_bank_caches_so_a_keypress_never_pays_for_synthesis() -> None:
    bank = sfx.SfxBank(SR)
    assert bank.get(sfx.MOVE) is bank.get(sfx.MOVE)


def test_bank_renders_at_its_own_rate() -> None:
    bank = sfx.SfxBank(22050)
    assert len(bank.get(sfx.MOVE)) == len(sfx.render(sfx.MOVE, 22050))


def test_prerender_fills_every_sound() -> None:
    bank = sfx.SfxBank(SR)
    bank.prerender()
    assert set(bank._cache) == set(sfx.NAMES)


def test_bank_rejects_unknown_names() -> None:
    with pytest.raises(KeyError):
        sfx.SfxBank(SR).get("explode")
