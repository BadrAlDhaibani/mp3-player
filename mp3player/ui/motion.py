"""One easing helper, shared by every widget that animates.

Three widgets slide or fade, and they all want the same three lines: stop
whatever is running, start again from wherever the value happens to be right
now, ease to the new one. Restarting from the *current* value rather than the
old target is what stops a held arrow key from stuttering -- each press picks
up the motion in flight instead of snapping back and replaying it.

`QPropertyAnimation` already owns the timer, the easing and the repaint, so
this is a thin wrapper rather than a tweening engine. The animated attribute
has to be a Qt `Property` on the target; its setter is where `update()` goes.

The default curve is an ease-*out*, and that is a constraint rather than a
preference: restarting from the current value is only smooth if the curve has
speed at t=0. Give this an ease-in and a held arrow key stutters once per key
repeat, because every press stops the motion dead and accelerates it again from
nothing. Anything passed as `curve` should clear the same bar.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QObject, QPropertyAnimation


class Tween(QPropertyAnimation):
    """Eases one float property of `target`. Parented to it, so it dies with it."""

    def __init__(
        self,
        target: QObject,
        name: str,
        duration_ms: int,
        curve: QEasingCurve.Type = QEasingCurve.OutCubic,
    ) -> None:
        super().__init__(target, name.encode(), target)
        self._name = name
        self.setDuration(duration_ms)
        self.setEasingCurve(curve)

    def to(self, value: float) -> None:
        """Ease to `value` from wherever the property is at this instant."""
        self.stop()
        self.setStartValue(float(self.targetObject().property(self._name)))
        self.setEndValue(float(value))
        self.start()

    def finish(self) -> None:
        """Jump straight to the end.

        For animations nobody can see: a column that's been hidden behind the
        Now Playing page has no business still sliding, and the offscreen
        harness needs the resting layout without waiting out real milliseconds.
        """
        if self.state() != QPropertyAnimation.Running:
            return
        end = float(self.endValue())
        self.stop()
        self.targetObject().setProperty(self._name, end)
