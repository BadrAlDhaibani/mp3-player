"""Decoding must produce exactly one buffer shape, and must fail in exactly one
way -- `DecodeError`, never a raw libsndfile exception leaking to the UI.

Fixtures are written with `soundfile` rather than checked in, so the tests
exercise the real decoder without adding binaries to git.
"""

from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf

from mp3player.core.audio.decode import CHANNELS, DecodeError, load_audio, to_canonical

SR = 44100

MP4_HEADER = b"\x00\x00\x00\x18ftypdash"


def write_wav(path, channels: int = 2, seconds: float = 0.1, sample_rate: int = SR):
    frames = int(seconds * sample_rate)
    t = np.arange(frames, dtype=np.float32) / sample_rate
    mono = np.sin(2 * np.pi * 440 * t, dtype=np.float32)
    data = np.repeat(mono[:, None], channels, axis=1) * np.linspace(
        0.3, 1.0, channels, dtype=np.float32
    )
    sf.write(str(path), data, sample_rate)
    return path


# -- load_audio ----------------------------------------------------------


def test_decodes_to_the_canonical_buffer(tmp_path) -> None:
    samples, rate = load_audio(write_wav(tmp_path / "tone.wav"))
    assert samples.dtype == np.float32
    assert samples.ndim == 2 and samples.shape[1] == CHANNELS
    assert samples.flags["C_CONTIGUOUS"]
    assert rate == SR


def test_reports_the_files_own_sample_rate(tmp_path) -> None:
    _, rate = load_audio(write_wav(tmp_path / "tone.wav", sample_rate=22050))
    assert rate == 22050


def test_length_matches_the_source(tmp_path) -> None:
    samples, rate = load_audio(write_wav(tmp_path / "tone.wav", seconds=0.25))
    assert len(samples) / rate == pytest.approx(0.25, abs=0.01)


def test_mono_is_upmixed_so_nothing_downstream_counts_channels(tmp_path) -> None:
    samples, _ = load_audio(write_wav(tmp_path / "mono.wav", channels=1))
    assert samples.shape[1] == CHANNELS
    assert np.array_equal(samples[:, 0], samples[:, 1])


def test_surround_is_folded_to_the_front_pair(tmp_path) -> None:
    samples, _ = load_audio(write_wav(tmp_path / "surround.wav", channels=6))
    assert samples.shape[1] == CHANNELS


def test_accepts_a_string_path(tmp_path) -> None:
    samples, _ = load_audio(str(write_wav(tmp_path / "tone.wav")))
    assert len(samples) > 0


# -- failure modes -------------------------------------------------------


def test_missing_file_is_a_decode_error(tmp_path) -> None:
    with pytest.raises(DecodeError, match="could not be opened"):
        load_audio(tmp_path / "nope.mp3")


def test_mp4_wearing_an_mp3_extension_says_so(tmp_path) -> None:
    """The 8% case. libsndfile's own error would not explain anything."""
    fake = tmp_path / "youtube-rip.mp3"
    fake.write_bytes(MP4_HEADER + b"\x00" * 512)
    with pytest.raises(DecodeError, match="MP4/AAC"):
        load_audio(fake)


def test_garbage_is_a_decode_error_not_a_libsndfile_error(tmp_path) -> None:
    junk = tmp_path / "junk.mp3"
    junk.write_bytes(b"\xde\xad\xbe\xef" * 64)
    with pytest.raises(DecodeError):
        load_audio(junk)


def test_empty_file_is_a_decode_error(tmp_path) -> None:
    empty = tmp_path / "empty.mp3"
    empty.write_bytes(b"")
    with pytest.raises(DecodeError):
        load_audio(empty)


def test_valid_container_with_no_audio_is_a_decode_error(tmp_path) -> None:
    silent = tmp_path / "silent.wav"
    sf.write(str(silent), np.zeros((0, 2), dtype=np.float32), SR)
    with pytest.raises(DecodeError, match="no audio"):
        load_audio(silent)


def test_error_carries_the_path_and_reason(tmp_path) -> None:
    target = tmp_path / "gone.mp3"
    with pytest.raises(DecodeError) as caught:
        load_audio(target)
    assert caught.value.path == target
    assert caught.value.reason
    assert "gone.mp3" in str(caught.value)


# -- to_canonical --------------------------------------------------------


def test_canonical_promotes_a_flat_mono_array() -> None:
    out = to_canonical(np.zeros(100, dtype=np.float32))
    assert out.shape == (100, CHANNELS)


def test_canonical_converts_dtype() -> None:
    out = to_canonical(np.zeros((10, 2), dtype=np.float64))
    assert out.dtype == np.float32


def test_canonical_leaves_stereo_alone() -> None:
    data = np.arange(20, dtype=np.float32).reshape(10, 2)
    assert np.array_equal(to_canonical(data), data)
