"""What the shell sounds like.

The blips themselves are `core/audio/sfx.py` -- synthesized, tested, and with no
opinion about when they play. This file is the opinion: which event makes which
noise, how loud, and how often it is allowed to.

It lives in `ui/` rather than in the controller because the controller cannot
tell the two apart. `step(+1)` is the end of a track *and* a press of Next, and
those want different things -- one is feedback, the other is an interruption.
The window knows which happened, because it is the half that was pressed. So the
controller announces (`failed`, `playing_changed`) and routes audio, and every
decision about sound is made here or at the keypress that caused it.

Sound follows *intent*, not state. Nothing here hangs off `index_changed`: that
signal also fires when auto-advance moves the cursor to the track that just
started playing, and a blip nobody asked for reads as an alert rather than as
feedback.

Everything goes through `PlayerController.play_sfx`, so the rule that widgets
never touch `AudioEngine` survives.
"""

from __future__ import annotations

from time import monotonic
from typing import TYPE_CHECKING

from mp3player.core.audio import sfx

if TYPE_CHECKING:  # pragma: no cover - import cycle otherwise, typing only
    from mp3player.ui.controller import PlayerController

# The tick is the move blip, backed off. It fires while you are already hearing
# the result -- the pitch of the music itself -- so it only has to say "that
# registered", not "listen to me".
TICK_GAIN = 0.55

# The floor on how often a sound may repeat, per sound.
#
# Windows repeats a held key about 30 times a second. Unthrottled that is 30
# overlapping 45 ms blips, which is not a series of ticks but a buzz -- and it
# would lap the eight-slot voice pool three times a second, cutting each sound
# off mid-flight to start the next. At 60 ms the pool is never even close to
# full and consecutive move blips do not overlap at all.
#
# The slider is slower still: a mouse drag emits a move event per pixel, and
# unlike a keypress there is no repeat rate limiting it in the first place.
_MIN_GAP_MS = {
    sfx.MOVE: 60.0,
    sfx.CONFIRM: 90.0,
    sfx.BACK: 90.0,
    sfx.ERROR: 250.0,  # a failure that repeats is one failure
    sfx.STARTUP: 0.0,  # once a launch; nothing to rate-limit
}
_DEFAULT_GAP_MS = 60.0

_TICK = "tick"  # not a sound of its own -- `move`, quieter and rarer


def _now_ms() -> float:
    return monotonic() * 1000.0


class Sounds:
    """Fires UI sounds, throttled. One per window.

    Deliberately not a `QObject`: it owns no signals and no timers, and making
    it one would only invite something to connect to it. The window calls these
    methods directly at the point the user did the thing.
    """

    def __init__(self, controller: PlayerController) -> None:
        self._controller = controller
        self._last: dict[str, float] = {}
        # Swappable so the harness can drive the throttle instead of sleeping
        # through it (CLAUDE.md, conventions). Milliseconds, monotonic.
        self.clock = _now_ms

    # -- the map -----------------------------------------------------------

    def move(self) -> None:
        """The cursor moved: a crossbar step, a row, a wheel, a click."""
        self._play(sfx.MOVE)

    def tick(self) -> None:
        """The speed slider moved. Same blip, quieter and further apart."""
        self._play(sfx.MOVE, gain=TICK_GAIN, key=_TICK, gap_ms=90.0)

    def confirm(self) -> None:
        """Something opened or started: Enter, a click on the selection, play."""
        self._play(sfx.CONFIRM)

    def back(self) -> None:
        """Something closed or stopped: pause, leaving full screen."""
        self._play(sfx.BACK)

    def error(self) -> None:
        """The app could not do it. Wired to the controller's `failed`."""
        self._play(sfx.ERROR)

    def startup(self) -> None:
        self._play(sfx.STARTUP)

    # -- the throttle ------------------------------------------------------

    def _play(
        self,
        name: str,
        *,
        gain: float = 1.0,
        key: str | None = None,
        gap_ms: float | None = None,
    ) -> None:
        """Play `name` unless it played too recently.

        Dropped rather than queued. A blip that arrives after the keypress that
        earned it has stopped being feedback -- 22 ms of output latency is
        already the budget (CLAUDE.md, reference numbers), and a queue would
        spend the rest of it playing catch-up with a held arrow key.
        """
        key = key or name
        gap = _MIN_GAP_MS.get(name, _DEFAULT_GAP_MS) if gap_ms is None else gap_ms
        now = self.clock()

        previous = self._last.get(key)
        if previous is not None and now - previous < gap:
            return

        self._last[key] = now
        self._controller.play_sfx(name, gain)
