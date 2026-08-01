"""Entry point.

    venv/Scripts/python.exe -m mp3player.app

Assembles the three pieces and gets out of the way: the engine (core, no Qt),
the controller (the seam), and the window (all Qt). Order matters -- the window
draws itself from the controller's signals, so it must be connected before
`start()` emits them.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from mp3player.core import settings as settings_mod
from mp3player.core.audio.engine import AudioDeviceError, AudioEngine
from mp3player.ui.controller import PlayerController
from mp3player.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("XMB Player")
    app.setOrganizationName(settings_mod.APP_NAME)

    saved = settings_mod.load()

    try:
        engine = AudioEngine(volume=saved.volume, speed=saved.speed)
        engine.start()
    except AudioDeviceError as exc:
        # Nothing to fall back to: the app is a music player. Say it in a box
        # rather than a traceback nobody sees under pythonw.exe.
        QMessageBox.critical(None, "XMB Player", f"No usable audio output.\n\n{exc}")
        return 1

    controller = PlayerController(engine, saved)
    window = MainWindow(controller)

    # Settings are flushed and the stream closed on the way out, however we get
    # there -- window close, Alt+F4, or the session ending.
    app.aboutToQuit.connect(controller.shutdown)

    window.show()
    controller.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
