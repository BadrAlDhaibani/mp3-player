"""Every transition, in one continuous stream.

`test_dsp` and `test_engine` already check the fades one at a time: a seek does
not click, a pause does not click, the end of a track does not click. This is
the other question, and it is the one Batch 6 asks -- does the whole *session*
stay click-free when the transitions run into each other, and while UI blips are
being mixed over the top of them?

A click is a step: one sample to the next moving further than the signal itself
ever could. So the music here is a low sine, whose largest honest step is
arithmetic rather than a guess -- `2*pi*f/rate` per sample, times the amplitude,
times the fastest speed we ever read it at -- and anything above that came from
the mixer rather than from the music.

No device, no threads, no real time: the whole session is rendered block by
block exactly as the callback would, and then looked at as one array.
"""

from __future__ import annotations

import numpy as np
import pytest

from mp3player.core.audio import sfx
from mp3player.core.audio.engine import BLOCKSIZE, Mixer

SR = 48000
TONE_HZ = 110.0
SECOND_HZ = 220.0  # the track swapped in mid-session, an octave up
AMPLITUDE = 0.9
FAST = 1.30  # the app's nightcore end, and the fastest we ever read a file


def tone(seconds: float, hz: float = TONE_HZ, rate: int = SR) -> np.ndarray:
    t = np.arange(int(seconds * rate), dtype=np.float32) / rate
    wave = (AMPLITUDE * np.sin(2 * np.pi * hz * t)).astype(np.float32)
    return np.ascontiguousarray(np.repeat(wave[:, None], 2, axis=1))


# The bound below is the tone's own derivative, and the signal that comes back
# out of the mixer is a *linear interpolation* of a sampled sine in float32 --
# which lands a fraction of a percent either side of the ideal curve. Enough
# slack for that and no more: the bug this file was written for overshot its
# bound six times over, so nothing near the edge of this is in question.
STEP_TOLERANCE = 1.02


def biggest_honest_step(hz: float = TONE_HZ, speed: float = FAST) -> float:
    """The largest sample-to-sample move the tone itself can make."""
    return AMPLITUDE * 2 * np.pi * hz * speed / SR * STEP_TOLERANCE


def render(mixer: Mixer, blocks: int, script: dict[int, callable] | None = None):
    """Render `blocks` blocks, running `script[i]` before block `i`.

    Actions are handed `(mixer, pump)`, where `pump` renders one more block
    *into the session*. That matters for the ones that have to wait for a fade:
    in the app those blocks go to the sound card like any other, so a test that
    rendered them off to one side would be splicing its own click into the
    stream and then blaming the mixer for it.
    """
    script = script or {}
    out = np.zeros((BLOCKSIZE, 2), dtype=np.float32)
    session = []

    def pump() -> None:
        mixer.render(out)
        session.append(out.copy())

    for index in range(blocks):
        action = script.get(index)
        if action is not None:
            action(mixer, pump)
        pump()
    return np.concatenate(session)


def biggest_step(session: np.ndarray) -> float:
    return float(np.abs(np.diff(session, axis=0)).max())


def silence_the_music(mixer: Mixer, pump) -> None:
    """What `AudioEngine.load` does before swapping the samples array.

    A track change is the one transition the mixer cannot do by itself -- the
    new array only exists on the caller's side -- so the protocol is: pause,
    render until the fade has reached zero, then swap.
    """
    mixer.pause()
    for _ in range(8):
        pump()
        if mixer.music_gain == 0.0:
            return
    raise AssertionError("the music never reached silence")


def test_a_whole_session_of_transitions_has_no_step_in_it() -> None:
    """Play, pause, seek, speed, volume, track change, end of track -- in a row.

    Deliberately one continuous render: the fades overlap each other here in a
    way they never do in a test that sets up, transitions once, and stops.
    """
    mixer = Mixer(SR, volume=1.0)
    mixer.set_track(tone(4.0), SR, autoplay=False)

    def change_track(m: Mixer, pump) -> None:
        silence_the_music(m, pump)
        m.set_track(tone(2.0, hz=SECOND_HZ), SR)

    session = render(
        mixer,
        blocks=260,
        script={
            2: lambda m, _: m.play(),
            20: lambda m, _: m.pause(),
            30: lambda m, _: m.play(),
            45: lambda m, _: m.seek(2.5),
            60: lambda m, _: setattr(m, "volume", 0.25),
            75: lambda m, _: setattr(m, "speed", FAST),
            90: lambda m, _: m.seek(0.5),
            95: lambda m, _: m.pause(),  # a pause landing mid-seek
            100: lambda m, _: m.play(),
            115: lambda m, _: setattr(m, "volume", 1.0),
            130: change_track,
            150: lambda m, _: setattr(m, "speed", 0.8),
            170: lambda m, _: m.seek(1.9),  # run it off the end
        },
    )

    # The bound is set by the fastest-moving thing in the session, which is the
    # second track: the first is an octave below it and can only step half as
    # far, so holding the whole stream to its number would be the weaker test.
    limit = biggest_honest_step(hz=SECOND_HZ)
    assert biggest_step(session) <= limit, (
        f"step of {biggest_step(session):.4f} against a tone that can only "
        f"move {limit:.4f} per sample"
    )
    # ...and it really did play, rather than staying silent and passing for it.
    assert float(np.abs(session).max()) > 0.5


def test_blips_over_music_add_no_step_of_their_own() -> None:
    """The mix, not the sounds: UI blips ride on top of a track that is moving."""
    mixer = Mixer(SR, volume=1.0)
    mixer.set_track(tone(3.0), SR)

    blips = {block: (lambda m, _: m.play_sfx(sfx.MOVE)) for block in range(10, 120, 6)}
    blips[12] = lambda m, _: m.play_sfx(sfx.CONFIRM)
    blips[40] = lambda m, _: m.seek(1.0)
    blips[41] = lambda m, _: m.play_sfx(sfx.BACK)  # a blip landing inside a seek
    session = render(mixer, blocks=140, script=blips)

    # Each sound is a sampled sine of known bandwidth, so its own largest step
    # is measurable rather than assumed -- and the bound is the music's plus
    # every sound that could be sounding at once.
    sound_steps = sum(
        float(np.abs(np.diff(sfx.render(name, SR), axis=0)).max())
        for name in (sfx.MOVE, sfx.CONFIRM, sfx.BACK)
    )
    assert biggest_step(session) <= biggest_honest_step() + sound_steps


def test_a_held_arrow_key_does_not_cut_the_startup_swell() -> None:
    """The pool prefers a free slot, so the longest sound is not the victim.

    Plain round-robin stole one every eight blips whatever else was free, and
    the startup swell -- 1.1 s against a 45 ms tick -- is the sound still
    playing when the pointer comes round. Cutting it is a gain that reaches
    zero in one sample.
    """
    mixer = Mixer(SR)
    mixer.play_sfx(sfx.STARTUP)
    swell = next(v for v in mixer._sfx_voices if v.active)
    startup = swell.samples

    # Held-key presses, spaced as `ui/sounds.py` lets them through, for as long
    # as the swell lasts. That is twice round an eight-slot pool, which is the
    # thing being tested: round-robin alone stole the swell on the ninth.
    every = 6 * BLOCKSIZE  # ~64 ms
    presses = len(startup) // every - 1

    out = np.zeros((BLOCKSIZE, 2), dtype=np.float32)
    reached = 0
    for press in range(presses):
        mixer.play_sfx(sfx.MOVE)
        for _ in range(6):
            mixer.render(out)
        assert swell.samples is startup, f"the swell's slot was stolen (press {press})"
        assert swell.pos > reached, "the swell stopped advancing"
        reached = swell.pos

    assert presses >= 2 * len(mixer._sfx_voices), "not enough presses to lap the pool"
    assert swell.active, "the swell should still be sounding"


@pytest.mark.parametrize("speed", (0.8, 1.0, 1.3))
def test_the_end_of_a_track_is_click_free_at_any_speed(speed: float) -> None:
    """Reading off the end is a step unless the voice ramps down to meet it.

    Parametrised because the fade is a fixed number of *stream* frames while
    the read rate is not: at nightcore the voice covers the file faster, so it
    arrives at the end sooner and with less warning.
    """
    mixer = Mixer(SR, volume=1.0, speed=speed)
    mixer.set_track(tone(0.5), SR)
    session = render(mixer, blocks=80)

    assert biggest_step(session) <= biggest_honest_step(speed=speed)
    assert mixer.take_finished()
    assert float(np.abs(session[-BLOCKSIZE:]).max()) == 0.0
