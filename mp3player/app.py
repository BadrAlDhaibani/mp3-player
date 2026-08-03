"""Entry point.

    venv/Scripts/python.exe -m mp3player.app

Assembles the three pieces and gets out of the way: the engine (core, no Qt),
the controller (the seam), and the window (all Qt). Order matters -- the window
draws itself from the controller's signals, so it must be connected before
`start()` emits them.
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path
from types import TracebackType

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from mp3player import __version__
from mp3player.core import log as log_mod
from mp3player.core import settings as settings_mod
from mp3player.core.audio.engine import AudioDeviceError, AudioEngine
from mp3player.ui.controller import PlayerController
from mp3player.ui.main_window import MainWindow

_log = log_mod.get("app")


def _make_console_utf8_safe() -> None:
    """Stop a track title from taking the app down.

    `run.bat` gives us a real console, and a Windows one is cp1252 by default --
    so a traceback or a print carrying a "·" or any non-Latin-1 character in a
    filename raises `UnicodeEncodeError` *while reporting the original problem*,
    replacing something diagnosable with something baffling. Under `pythonw.exe`
    there is no console at all and these are None, which is why it is guarded.
    """
    for stream in (sys.stdout, sys.stderr):
        if stream is not None:
            with contextlib.suppress(AttributeError, OSError):
                # Duck-typed on purpose, which is what the AttributeError above
                # is for: typeshed calls these `TextIO`, and only the concrete
                # `TextIOWrapper` declares `reconfigure`. Narrowing to that type
                # instead would skip anything else that supports it -- pytest's
                # capture, PyInstaller's console shim -- to please the stub.
                stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]


def _install_crash_handler(log_file: Path | None) -> None:
    """Send every unhandled exception to the log, and say so once, on screen.

    This is the whole reason there is a log file. PySide6 6.11 reports an
    exception raised inside a slot or a paint handler to `sys.excepthook` and
    then *carries on* -- checked, rather than assumed, because the audit that
    scoped this batch said the process terminates and it does not. Carrying on
    is the worse half of the problem: nothing stops, nothing is written, and
    under `pythonw.exe` the traceback goes to a stream that isn't there.

    Two things follow from "carries on". A broken `paintEvent` raises on every
    frame, so the dialog is shown **once** per launch and `record_exception`
    throttles the file. And the dialog is *posted* rather than shown from inside
    the hook: opening a modal dialog part-way through someone else's paint is
    how a crash report becomes a second crash.
    """
    previous = sys.excepthook
    shown = False

    def hook(
        exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None
    ) -> None:
        nonlocal shown
        if issubclass(exc_type, KeyboardInterrupt):
            previous(exc_type, exc, tb)
            return

        first = log_mod.record_exception(exc_type, exc, tb)
        if sys.stderr is not None:
            # Under `run.bat` the console is still the fastest way to read one.
            with contextlib.suppress(Exception):
                previous(exc_type, exc, tb)

        if first and not shown and QApplication.instance() is not None:
            shown = True
            QTimer.singleShot(0, lambda: _show_crash_dialog(log_file))

    sys.excepthook = hook


def _show_crash_dialog(log_file: Path | None) -> None:
    """Tell the user something broke and where it was written down.

    Guarded end to end: this runs *because* something already went wrong, and a
    failure in here would go straight back through the hook that called it.
    """
    where = (
        f"The details were written to:\n{log_file}"
        if log_file is not None
        else "No log file could be opened, so there is nothing to send on."
    )
    with contextlib.suppress(Exception):
        QMessageBox.warning(
            None,
            "XMB Player",
            "Something went wrong inside XMB Player.\n\n"
            f"{where}\n\n"
            "It is still running, but may not behave correctly from here -- "
            "restarting it is the safe move.",
        )


def main() -> int:
    _make_console_utf8_safe()
    log_file = log_mod.setup()
    _install_crash_handler(log_file)
    _log.info("XMB Player %s starting", __version__)

    app = QApplication(sys.argv)
    app.setApplicationName("XMB Player")
    app.setApplicationVersion(__version__)
    app.setOrganizationName(settings_mod.APP_NAME)

    saved = settings_mod.load()

    try:
        engine = AudioEngine(volume=saved.volume, speed=saved.speed)
        engine.start()
    except AudioDeviceError as exc:
        # Nothing to fall back to: the app is a music player, and unlike the
        # device going away *while* it runs there is no stream to nurse back --
        # we never got one. Say it in a box rather than a traceback nobody sees
        # under pythonw.exe.
        _log.error("no usable audio output at launch: %s", exc)
        QMessageBox.critical(
            None,
            "XMB Player",
            "No usable audio output was found.\n\n"
            f"{exc}\n\n"
            "Plug in or enable an output device and start XMB Player again.",
        )
        return 1

    controller = PlayerController(engine, saved)
    window = MainWindow(controller)

    # Settings are flushed and the stream closed on the way out, however we get
    # there -- window close, Alt+F4, or the session ending.
    app.aboutToQuit.connect(controller.shutdown)

    window.show()
    controller.start()

    # `aboutToQuit` covers every ordinary exit and this covers the rest.
    # `shutdown()` is idempotent -- it is what flushes the last 800 ms of
    # settings changes and closes the stream -- so paying for it twice on the
    # normal path costs nothing and buys the abnormal one.
    try:
        return app.exec()
    finally:
        controller.shutdown()
        _log.info("XMB Player exiting")


if __name__ == "__main__":
    raise SystemExit(main())
