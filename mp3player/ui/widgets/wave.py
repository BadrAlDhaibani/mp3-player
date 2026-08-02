"""The wave: sine ribbons in a band across the crossbar row.

The atmosphere layer, and the only thing in the app that moves when nobody is
touching it. Four ribbons drift at different speeds and wavelengths, and where
they cross they *add* rather than cover -- that additive overlap is the whole
look. Underneath them a slow bloom swells around the crossbar row.

Three decisions worth keeping:

**A band, not a field.** The ribbons are masked to a falloff centred on the
crossbar row. Run full-height they pass behind the track list and the transport
bar and turn into noise; kept to the band they light the row the selection
actually lives on.

**Hue tracks the speed slider** (`theme.wave_color`). Deep blue at daycore, the
app's own accent at 1.00x, violet at nightcore -- so the background reads out
the effect, and moves while the slider is dragged.

**Rendered into a buffer that is coarse across and full-height down.** A ribbon
is a long, slowly-varying horizontal band: its edges run almost horizontally, so
only the *vertical* sampling decides whether they look crisp, while along x a
feature spans hundreds of pixels and three in four can go. Scaling both axes
down -- the obvious thing, and what this did first -- costs the same as scaling
only x by four, and looks soft. The buffers are reused between frames; a
`QImage` per frame is the one allocation worth avoiding.

The timer only ever calls `update()`. All the cost is inside `paintEvent`,
which Qt simply doesn't call when the window is minimised or covered -- so an
idle-in-the-tray player pays nothing without needing to be told.

**Where the frame budget went.** The first version stroked each ribbon with a
wide soft pen for its halo and sampled the curve 160 times: **25 ms a frame**,
against a 33 ms budget, for a background. Stroking was 18 ms of it -- a wide
pen on a 320-point path makes Qt compute a join per point -- and building the
paths in Python was another 4. Filling instead of stroking, sampling 60 times,
and getting the halo from a downsampled additive copy of the whole buffer
instead of per-ribbon strokes brings it to **~2 ms**. The lesson worth keeping:
in this widget the cost is path geometry, not pixels. Dropping the resolution
from 1/2 to 1/4 only moved 25 ms to 19; deleting one `setPen` moved it to 6.

Once the stroke was gone the balance flipped and *pixels* became the cost --
filling the four ribbons is now the largest item in the frame. That is what
makes the anisotropic buffer worth it: full resolution is 14 ms, both axes
quartered is 4, and quartering only x is 5.6 and looks like the 14.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from mp3player.ui import theme

# One ribbon each: wavelength (of the width), amplitude, drift in radians per
# second, thickness, alpha, and a hue nudge off the wave's base colour. Signs
# differ so the ribbons cross each other rather than travelling as a pack;
# nothing here divides evenly into anything else, which is what stops the whole
# band from visibly repeating.
RIBBONS = (
    # wavelength, amplitude, drift, thickness, alpha, hue shift
    (1.35, 1.00, 0.21, 1.00, 1.00, 0.000),
    (0.90, 0.62, -0.15, 0.72, 0.78, -0.030),
    (1.90, 1.35, 0.11, 1.25, 0.55, 0.035),
    (0.62, 0.40, -0.27, 0.55, 0.62, 0.018),
)

MAX_STEP_S = 0.10  # a frame gap longer than this is a stall, not elapsed time


class WaveBackground(QWidget):
    """Paints the wave. Knows the speed fraction and nothing else about the app."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Bottom of the stage's stack and invisible to the pointer: the stage
        # does all the hit-testing, and this is scenery.
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self._fraction = 0.4  # 1.00x, so the wave starts on the accent colour
        self._phase = 0.0
        self._buffer: QImage | None = None
        self._glow: QImage | None = None
        self._clock = QElapsedTimer()

        self._frames = 0
        self._render_ms = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(max(1, 1000 // theme.WAVE_FPS))
        self._timer.timeout.connect(self.update)
        # Coarse on purpose, and it is the reason the wave runs at ~21 fps
        # rather than 30: Windows' timer tick is 15.6 ms, so a 33 ms coarse
        # timer fires every 46.8. A precise timer does deliver 30 fps, but it
        # raises the system-wide timer resolution -- a battery cost the whole
        # machine pays, for an app that sits open for hours -- and measured
        # four times the CPU at 1600x900. Nothing here moves fast enough to
        # care: the quickest ribbon travels about 2 px between frames.
        self._timer.setTimerType(Qt.CoarseTimer)

    # -- state -------------------------------------------------------------

    def set_fraction(self, fraction: float) -> None:
        """Where the speed slider is, 0..1. Drives the hue; no repaint needed.

        The timer is already painting a frame every 33 ms, so asking for
        another one here would only mean painting the same frame twice while
        the slider is dragged.
        """
        self._fraction = max(0.0, min(1.0, float(fraction)))

    @property
    def average_render_ms(self) -> float:
        """Mean cost of a frame since the last `reset_stats()`. For the perf pass."""
        return self._render_ms / self._frames if self._frames else 0.0

    def reset_stats(self) -> None:
        self._frames = 0
        self._render_ms = 0.0

    # -- lifecycle ---------------------------------------------------------

    def showEvent(self, event) -> None:
        self._clock.restart()
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    # -- painting ----------------------------------------------------------

    def paintEvent(self, event) -> None:
        if self.width() <= 0 or self.height() <= 0:
            return
        self._advance()

        started = QElapsedTimer()
        started.start()
        image = self._render()
        self._render_ms += started.nsecsElapsed() / 1e6
        self._frames += 1

        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawImage(self.rect(), image)

    def _advance(self) -> None:
        """Move the phase on by real elapsed time, not by a frame count.

        A dropped frame should cost smoothness, never speed -- and coming back
        from minimised must not fast-forward the wave through however long the
        window was away, which is what the clamp is for.
        """
        if not self._clock.isValid():
            self._clock.start()
            return
        self._phase += min(MAX_STEP_S, self._clock.restart() / 1000.0)

    def _render(self) -> QImage:
        width = max(1, self.width() // theme.WAVE_SCALE_X)
        height = max(1, self.height() // theme.WAVE_SCALE_Y)
        self._resize_buffers(width, height)

        image = self._buffer
        image.fill(Qt.transparent)
        row = height * theme.CROSSBAR_Y_RATIO

        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        # Where two ribbons cross, the light adds. Covering instead would make
        # the crossings darker than the ribbons, which is exactly backwards.
        painter.setCompositionMode(QPainter.CompositionMode_Plus)
        for ribbon in RIBBONS:
            self._paint_ribbon(painter, width, height, row, *ribbon)
        painter.end()

        self._add_glow(width, height)

        painter = QPainter(image)
        painter.setPen(Qt.NoPen)
        # After the glow, not before: the bloom is already a smooth gradient, so
        # blurring it achieves nothing and adding it twice just doubles it.
        painter.setCompositionMode(QPainter.CompositionMode_Plus)
        self._paint_bloom(painter, width, height, row)

        # The band, applied once at the end rather than folded into every
        # ribbon's alpha: one gradient fill against the finished image, and the
        # falloff is then guaranteed identical for all of them.
        painter.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        painter.fillRect(QRectF(0, 0, width, height), self._band(height, row))
        painter.end()

        return image

    def _resize_buffers(self, width: int, height: int) -> None:
        if (
            self._buffer is None
            or self._buffer.width() != width
            or self._buffer.height() != height
        ):
            self._buffer = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
            # The halo is specified in screen pixels and divided back through
            # each axis's own scale, so it comes out round rather than as wide
            # as the horizontal scale happens to be.
            self._glow = QImage(
                max(1, int(width * theme.WAVE_SCALE_X / theme.WAVE_GLOW_RADIUS)),
                max(1, int(height * theme.WAVE_SCALE_Y / theme.WAVE_GLOW_RADIUS)),
                QImage.Format_ARGB32_Premultiplied,
            )

    def _add_glow(self, width: int, height: int) -> None:
        """The halo, as a blurred copy of the ribbons added back over them.

        Two bilinear blits: down to a third of the buffer, which *is* the blur,
        and back up. The obvious alternative -- a wide soft pen on each ribbon
        -- looks much the same and costs nine times the whole rest of the frame
        (see the module docstring).
        """
        painter = QPainter(self._glow)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawImage(
            QRectF(0, 0, self._glow.width(), self._glow.height()), self._buffer
        )
        painter.end()

        painter = QPainter(self._buffer)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setCompositionMode(QPainter.CompositionMode_Plus)
        painter.setOpacity(theme.WAVE_GLOW)
        painter.drawImage(QRectF(0, 0, width, height), self._glow)
        painter.end()

    def _band(self, height: int, row: float) -> QLinearGradient:
        """The vertical mask. Only the alpha of these stops is ever read."""
        span = max(1.0, height * theme.WAVE_BAND)
        gradient = QLinearGradient(0.0, row - span, 0.0, row + span)
        # Not a straight ramp: a linear falloff leaves a visible edge where it
        # reaches zero. The shoulders round it off.
        for stop, alpha in ((0.0, 0), (0.28, 110), (0.5, 255), (0.72, 110), (1.0, 0)):
            gradient.setColorAt(stop, QColor(0, 0, 0, alpha))
        return gradient

    def _paint_bloom(
        self, painter: QPainter, width: int, height: int, row: float
    ) -> None:
        """The slow swell behind the crossbar, centred on the active category."""
        breath = 0.5 + 0.5 * math.sin(self._phase * theme.WAVE_BREATH)
        alpha = int(theme.WAVE_BLOOM_ALPHA * (0.65 + 0.35 * breath))

        centre = QPointF(theme.FOCUS_X / theme.WAVE_SCALE_X, row)
        gradient = QRadialGradient(centre, max(width, height) * 0.9)
        gradient.setColorAt(0.0, theme.wave_color(self._fraction, alpha=alpha))
        gradient.setColorAt(0.45, theme.wave_color(self._fraction, alpha=alpha // 3))
        gradient.setColorAt(1.0, QColor(0, 0, 0, 0))

        painter.fillRect(QRectF(0, 0, width, height), gradient)

    def _paint_ribbon(
        self,
        painter: QPainter,
        width: int,
        height: int,
        row: float,
        wavelength: float,
        amplitude_scale: float,
        drift: float,
        thickness_scale: float,
        alpha_scale: float,
        hue_shift: float,
    ) -> None:
        amplitude = height * theme.WAVE_AMPLITUDE * amplitude_scale
        # Thickness is a vertical measure, so it converts through the vertical
        # scale only -- the one place the two axes must not be confused.
        thickness = max(1.0, theme.WAVE_THICKNESS / theme.WAVE_SCALE_Y * thickness_scale)
        phase = self._phase * drift

        # Filled, never stroked. The halo comes from `_add_glow` instead: a
        # wide pen here was 18 of the original 25 ms a frame.
        painter.setBrush(
            theme.wave_color(
                self._fraction,
                alpha=int(theme.WAVE_ALPHA * alpha_scale),
                hue_shift=hue_shift,
            )
        )
        painter.drawPath(
            self._ribbon_path(width, row, amplitude, thickness, wavelength, phase)
        )

    def _ribbon_path(
        self,
        width: int,
        row: float,
        amplitude: float,
        thickness: float,
        wavelength: float,
        phase: float,
    ) -> QPainterPath:
        """One ribbon, as a closed band between two sampled edges.

        Two sines rather than one so the crest never repeats on a comfortable
        interval, and a thickness that breathes along the length -- a constant
        width reads as a drawn stroke, a varying one as a ribbon turning.

        It starts a step off the left of the buffer and ends a step off the
        right, deliberately. A path that stopped at the edge would close with a
        vertical segment there, and antialiasing that segment leaves a
        half-covered column -- which the upscale then blows up into a visible
        seam a few pixels in from the window edge.
        """
        wave_k = 2 * math.pi / max(1.0, width * wavelength)
        detail_k = wave_k * 2.3
        step = max(1.0, width / theme.WAVE_STEP)

        top: list[QPointF] = []
        bottom: list[QPointF] = []

        x = -step
        while x <= width + step:
            y = (
                row
                + amplitude * math.sin(wave_k * x + phase)
                + amplitude * 0.35 * math.sin(detail_k * x - phase * 1.7)
            )
            half = thickness * (0.55 + 0.45 * math.sin(wave_k * x * 0.7 + phase * 0.9)) / 2
            top.append(QPointF(x, y - half))
            bottom.append(QPointF(x, y + half))
            x += step

        path = QPainterPath(top[0])
        for point in top[1:]:
            path.lineTo(point)
        for point in reversed(bottom):
            path.lineTo(point)
        path.closeSubpath()
        return path
