"""The log has to work when nothing else does, and never be the thing that broke.

Two properties matter more than the formatting: it does not raise when it cannot
open a file, and a fault that repeats at frame rate cannot rotate the
interesting part of the file out of existence.
"""

from __future__ import annotations

import logging

import pytest

from mp3player.core import log as log_mod
from mp3player.core import settings as s


@pytest.fixture
def logged(tmp_path):
    """A log pointed at a temp file, torn down again afterwards.

    The teardown is not politeness: the handler holds the file open, and on
    Windows an open handle is what stops pytest cleaning the temp directory up.
    """
    path = tmp_path / "logs" / "xmbplayer.log"
    original_clock = log_mod.clock
    assert log_mod.setup(path) == path
    try:
        yield path
    finally:
        log_mod.close()
        log_mod.clock = original_clock
        log_mod._seen.clear()


def test_the_log_sits_next_to_the_settings(tmp_path, monkeypatch) -> None:
    """One directory, already owned and already created by the app."""
    monkeypatch.setattr(s, "config_dir", lambda: tmp_path)
    assert log_mod.log_path() == tmp_path / log_mod.LOG_NAME
    assert log_mod.log_path().parent == s.config_path().parent


def test_setup_creates_the_directory_and_writes(logged) -> None:
    log_mod.get("test").info("hello")
    assert "hello" in logged.read_text(encoding="utf-8")
    assert log_mod.active_path() == logged


def test_setup_is_idempotent_for_the_same_file(logged) -> None:
    """Calling it twice must not double every line."""
    assert log_mod.setup(logged) == logged
    log_mod.get("test").info("once")
    assert logged.read_text(encoding="utf-8").count("once") == 1


def test_setup_survives_a_path_it_cannot_open(tmp_path) -> None:
    """No log, and no exception -- diagnosis does not get to be the fault."""
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("I am a file")
    assert log_mod.setup(blocker / "sub" / "xmbplayer.log") is None
    assert log_mod.active_path() is None
    log_mod.get("test").error("nowhere to go")  # must not raise


def test_the_file_is_size_capped(tmp_path) -> None:
    path = tmp_path / "xmbplayer.log"
    log_mod.setup(path)
    try:
        line = "x" * 512
        for _ in range(1200):  # ~600 KB of payload against a 256 KB cap
            log_mod.get("test").info(line)
        log_mod.close()
        assert path.stat().st_size <= log_mod.MAX_BYTES
        assert len(list(tmp_path.glob("xmbplayer.log*"))) <= log_mod.BACKUPS + 1
    finally:
        log_mod.close()


def test_due_is_true_once_per_gap(logged) -> None:
    now = [1000.0]
    log_mod.clock = lambda: now[0]

    assert log_mod.due("k", 10.0) is True
    assert log_mod.due("k", 10.0) is False
    now[0] += 9.9
    assert log_mod.due("k", 10.0) is False
    now[0] += 0.2
    assert log_mod.due("k", 10.0) is True
    # Keys are independent -- an xrun report must not silence a reconnect one.
    assert log_mod.due("other", 10.0) is True


def _raise(message: str) -> BaseException:
    try:
        raise ValueError(message)
    except ValueError as exc:
        return exc


def test_an_exception_is_written_once_and_then_throttled(logged) -> None:
    now = [1000.0]
    log_mod.clock = lambda: now[0]

    exc = _raise("boom")
    assert log_mod.record_exception(type(exc), exc, exc.__traceback__) is True

    # The same fault again, on the next frame: recognised, and not written.
    again = _raise("boom")
    assert log_mod.record_exception(type(again), again, again.__traceback__) is False

    log_mod.close()
    text = logged.read_text(encoding="utf-8")
    assert text.count("unhandled exception") == 1
    assert "ValueError: boom" in text
    assert "Traceback" in text


def test_a_different_fault_is_written_even_while_one_repeats(logged) -> None:
    log_mod.clock = lambda: 1000.0

    first = _raise("one")
    assert log_mod.record_exception(type(first), first, first.__traceback__) is True

    try:
        raise KeyError("two")  # a different type, a different line
    except KeyError as other:
        assert log_mod.record_exception(type(other), other, other.__traceback__) is True

    log_mod.close()
    assert logged.read_text(encoding="utf-8").count("unhandled exception") == 2


def test_nothing_is_logged_above_the_app_logger(logged) -> None:
    """The handler hangs off `mp3player`, so nothing else in the process is caught."""
    logging.getLogger("some.other.library").error("not ours")
    log_mod.get("test").info("ours")
    text = logged.read_text(encoding="utf-8")
    assert "not ours" not in text
    assert "ours" in text
