"""Somewhere for a failure to go.

Four things used to happen and leave no trace anywhere: a late audio block, a
settings write that failed, the device going away and coming back, and any
unhandled exception at all. Under `pythonw.exe` there is no console, so the
last of those is a traceback written to a stream that does not exist -- which
is the same as not having noticed.

The file sits next to `settings.json`, in the directory the app already owns and
already creates. One rotating handler, capped: a log that can grow without
bound is a log that eventually costs more than it tells you.

Two rules this module is written around:

  * **It never raises.** `setup()` returns `None` if it cannot open the file and
    the app carries on without one. Logging is diagnosis; it does not get to be
    the thing that goes wrong.
  * **Repeats are throttled, not written.** An exception raised from a
    `paintEvent` comes back on *every frame* -- verified, PySide6 6.11 reports it
    and keeps going -- and a hundred copies of one traceback would rotate the
    interesting part of the log out of existence in seconds. `due()` is the
    gate, and its clock is injectable for the same reason `Sounds.clock` and
    `StreamWatch.clock` are: a test that sleeps through a rate limit is a test
    that depends on the scheduler.

`core/` imports no Qt, and this is no exception -- a crash *dialog* is `ui`'s
business (`app.py` puts one up), and all this side does is write the file and
say where it is.
"""

from __future__ import annotations

import logging
import logging.handlers
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from types import TracebackType

from mp3player.core import settings as settings_mod

LOG_NAME = "xmbplayer.log"

# Two backups at a quarter megabyte each: enough that a session's worth of
# device drops and skipped files is still there tomorrow, small enough that
# nobody ever has to think about it.
MAX_BYTES = 256 * 1024
BACKUPS = 2

# Everything the app logs hangs off this one logger, so a single handler on it
# catches the lot and nothing has to be configured twice.
ROOT = "mp3player"

# How long the same exception has to stay quiet before it is written again.
REPEAT_GAP_S = 10.0

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s  %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

# Swappable, like every other clock in this project.
clock: Callable[[], float] = time.monotonic

_handler: logging.Handler | None = None
_path: Path | None = None
_seen: dict[str, float] = {}


def log_path() -> Path:
    """The log file. A sibling of `settings.json`, deliberately.

    That directory is already created, already documented as redirected under
    Microsoft Store Python, and already the one place the app owns. A second
    location would be a second thing to explain when someone is asked to send
    the file in.
    """
    return settings_mod.config_dir() / LOG_NAME


def active_path() -> Path | None:
    """Where we are actually writing, or None if we never opened a file."""
    return _path


def setup(path: Path | None = None, *, level: int = logging.INFO) -> Path | None:
    """Open the log. Returns where it went, or None if it could not be opened.

    Idempotent for the same target: calling it twice does not double every line.
    Pointing it somewhere else closes the old file first, which is what the
    tests do -- and is also the only reason `close()` is public.
    """
    global _handler, _path

    target = Path(path) if path is not None else log_path()
    if _handler is not None and _path == target:
        return _path

    close()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = logging.handlers.RotatingFileHandler(
            target,
            maxBytes=MAX_BYTES,
            backupCount=BACKUPS,
            encoding="utf-8",
        )
    except OSError:
        # No log, and that is the end of it. Deliberately not `delay=True`:
        # opening now means an unwritable directory is discovered here, where
        # we can answer honestly, rather than silently at the first record.
        return None

    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATEFMT))
    logger = logging.getLogger(ROOT)
    logger.setLevel(level)
    logger.addHandler(handler)
    _handler, _path = handler, target
    return target


def close() -> None:
    """Detach and close the log file. Safe to call with nothing open."""
    global _handler, _path
    handler, _handler, _path = _handler, None, None
    if handler is not None:
        logging.getLogger(ROOT).removeHandler(handler)
        handler.close()


def get(name: str) -> logging.Logger:
    """A named child of the app's logger -- `get("engine")`, `get("controller")`.

    A bare word rather than `__name__`: the point of the name in the file is to
    say which part of the app spoke, and `mp3player.core.audio.engine` spends
    thirty characters saying it.
    """
    return logging.getLogger(f"{ROOT}.{name}")


def due(key: str, gap_s: float = REPEAT_GAP_S) -> bool:
    """True at most once per `gap_s` for `key`. The first call is always True.

    For anything that can happen at frame rate. The caller keeps whatever it was
    going to say and simply does not say it again yet -- and should hold on to
    its running total rather than resetting it, so the line that does get written
    covers everything since the last one.
    """
    now = clock()
    previous = _seen.get(key)
    if previous is not None and now - previous < gap_s:
        return False
    _seen[key] = now
    return True


def record_exception(
    exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None
) -> bool:
    """Write an unhandled exception. True if this is one we have not seen before.

    Identity is the exception's type plus where it was raised, which is what
    makes the repeat of a broken `paintEvent` recognisable as the same fault
    rather than as a hundred faults. The return value is what lets a caller put
    a dialog up once and not once a frame.
    """
    key = _signature(exc_type, tb)
    first = key not in _seen
    if not due(key):
        return False

    text = "".join(traceback.format_exception(exc_type, exc, tb)).rstrip()
    logger = get("crash")
    if first:
        logger.error("unhandled exception\n%s", text)
    else:
        logger.error("unhandled exception (still happening)\n%s", text)
    return first


def _signature(exc_type: type[BaseException], tb: TracebackType | None) -> str:
    """`ValueError@theme.py:212` -- the type and the line that raised it."""
    frames = traceback.extract_tb(tb)
    if not frames:
        return exc_type.__name__
    last = frames[-1]
    return f"{exc_type.__name__}@{Path(last.filename).name}:{last.lineno}"
