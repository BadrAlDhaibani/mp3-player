"""Running yt-dlp, which is the half of the download feature that is Qt.

`core/fetch.py` builds the argv and parses the lines; this drives the process
and turns what comes back into signals. The split is the project's usual one --
everything that is a pure function of its input lives below the seam where
`tests/` can reach it, and everything that needs an event loop lives up here.

**Why `QProcess` and not `import yt_dlp` on a worker thread.** The audio
callback is Python and has a 10.7 ms deadline, so it competes for the GIL with
every other line of Python in this application; a thread does not help, because
a thread is the same GIL. A separate process is scheduled by the OS on its own
core and costs the callback nothing at all. `QProcess` is also event-loop
driven, so nothing here blocks, nothing here sleeps, and this module adds no
threading discipline to a project that has deliberately never had any.

One operation at a time, in both senses: one search (a newer one replaces the
one in flight, because you have stopped caring about the old query) and one
download (a second request is *refused*, because you have not stopped caring
about the old file).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QObject, QProcess, QTimer, Signal

from mp3player.core import fetch
from mp3player.core import log as log_mod
from mp3player.core.fetch import Result, Tools

_log = log_mod.get("fetch")

# A search that has not answered by here is not going to. yt-dlp fails fast when
# the machine is offline, so this is really about DNS or a socket that hangs --
# rare, and indistinguishable from "Searching..." forever without it.
SEARCH_TIMEOUT_MS = 25_000

# How long to wait for a killed process to actually die before giving up on it.
# Only ever reached on shutdown, where the alternative is hanging the quit.
KILL_WAIT_MS = 2_000


def _text(raw: QByteArray) -> str:
    """A Qt byte buffer as text, never raising on what a process actually emits.

    `bytes(raw.data())` rather than `bytes(raw)`, which is not a declared
    overload, and rather than `raw.data().decode(...)`, which the stubs type as
    possibly a `memoryview`. The outer `bytes` is a copy of something already in
    memory and is what makes the whole expression checkable -- `ui/` is strict
    apart from the two flattened-enum rules and this is not worth an exemption.

    `replace` because yt-dlp is reporting on titles from the open internet, and a
    lone surrogate in a channel name must not be the thing that takes down a
    download that otherwise worked.
    """
    return bytes(raw.data()).decode("utf-8", "replace")


def _reader(process: QProcess) -> str:
    """Whatever `process` has to say on stdout right now, as text."""
    return _text(process.readAllStandardOutput())


def _last_error(text: str) -> str:
    """One sentence out of yt-dlp's stderr, for a status line 13 px tall.

    Its own `ERROR:` line is the useful one and is nearly always last; the rest
    is warnings about signature extraction that mean nothing to anybody here.
    Truncated hard, because this lands in the small font at the right edge and
    the convention in CLAUDE.md is that a line which appears on screen gets a
    short form -- the log keeps the whole thing.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith("ERROR:"):
            line = line[len("ERROR:") :].strip()
            return line[:80].rstrip() + "…" if len(line) > 80 else line
    return "Download failed"


class Fetcher(QObject):
    """Searches and downloads, one of each at a time.

    Every signal carries a finished thought rather than a line of output: the
    window never sees a process, an exit code or a byte of stderr.
    """

    results = Signal(object)  # list[Result] -- empty is a real answer
    progress = Signal(float)  # 0..1 through the current download
    finished = Signal(object)  # Path | None: what landed, if yt-dlp said
    failed = Signal(str)  # one sentence, already short enough for the bar

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._search_proc: QProcess | None = None
        self._search_buf = ""
        self._dl_proc: QProcess | None = None
        self._dl_buf = ""
        self._dl_path: Path | None = None

        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.setInterval(SEARCH_TIMEOUT_MS)
        self._timeout.timeout.connect(self._on_search_timeout)

    # -- state the window asks about ---------------------------------------

    @property
    def searching(self) -> bool:
        return self._search_proc is not None

    @property
    def downloading(self) -> bool:
        return self._dl_proc is not None

    # -- searching ---------------------------------------------------------

    def search(self, tools: Tools, query: str) -> None:
        """Look `query` up. Replaces a search already running.

        Replacing rather than refusing is the whole difference from `download`
        below, and it is about what the user still wants: a query you have typed
        past is a question you have stopped asking, where a file half fetched is
        one you are still waiting for.
        """
        query = query.strip()
        if not query or tools.missing is not None:
            return
        self._stop_search()

        self._search_buf = ""
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.SeparateChannels)
        process.readyReadStandardOutput.connect(self._on_search_output)
        process.finished.connect(self._on_search_finished)
        # A tool that was there at startup and is gone now -- an antivirus
        # quarantine, a half-finished update. Without this the search would
        # simply never come back.
        process.errorOccurred.connect(self._on_search_error)
        self._search_proc = process

        argv = fetch.search_argv(tools, query)
        _log.info("search: %s", query)
        process.start(argv[0], argv[1:])
        self._timeout.start()

    def _on_search_output(self) -> None:
        if self._search_proc is None:
            return
        # yt-dlp emits one JSON object per line, and a chunk off a pipe ends
        # wherever it ends -- so the tail is held back until its newline
        # arrives. Parsing per-chunk instead would drop whichever result
        # happened to straddle a read.
        self._search_buf += _reader(self._search_proc)

    def _on_search_finished(self, code: int, _status) -> None:
        process = self._search_proc
        if process is None:
            return
        self._timeout.stop()
        # Both channels drained *before* the object is handed to `deleteLater`.
        # It would still be alive to read from -- deletion happens on the next
        # turn of the loop -- but reading out of something already scheduled for
        # deletion is the kind of ordering that survives review and then stops
        # surviving a Qt upgrade.
        self._search_buf += _reader(process)
        stderr = _text(process.readAllStandardError())
        self._search_proc = None
        process.deleteLater()

        found = [
            result
            for result in (fetch.parse_result(line) for line in self._search_buf.splitlines())
            if result is not None
        ]

        # A non-zero exit with hits in hand is not a failure worth a message:
        # one dead video among ten is exactly the case `parse_result` drops, and
        # yt-dlp reports it in its exit code.
        if code != 0 and not found:
            _log.warning("search failed (%d): %s", code, stderr.strip()[:400])
            self.failed.emit(_last_error(stderr) if stderr.strip() else "Search failed")
            return
        _log.info("search returned %d result(s)", len(found))
        self.results.emit(found)

    def _on_search_error(self, _error) -> None:
        if self._search_proc is None:
            return
        self._stop_search()
        self.failed.emit("Could not run yt-dlp")

    def _on_search_timeout(self) -> None:
        if self._search_proc is None:
            return
        self._stop_search()
        self.failed.emit("Search timed out")

    def _stop_search(self) -> None:
        process, self._search_proc = self._search_proc, None
        self._timeout.stop()
        if process is None:
            return
        # Disconnected before killing, or `finished` arrives for a process
        # whose answer is no longer wanted and overwrites the newer search's.
        process.disconnect(self)
        process.kill()
        process.waitForFinished(KILL_WAIT_MS)
        process.deleteLater()

    # -- downloading -------------------------------------------------------

    def download(self, tools: Tools, result: Result, folder: Path) -> bool:
        """Fetch `result` into `folder`. False if it could not be started.

        Refused rather than queued while one is running -- the batch this landed
        in is one song at a time, and a refusal the status line explains beats a
        queue nobody asked for.
        """
        if self._dl_proc is not None or tools.missing is not None:
            return False

        self._dl_buf = ""
        self._dl_path = None
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.SeparateChannels)
        process.readyReadStandardOutput.connect(self._on_dl_output)
        process.finished.connect(self._on_dl_finished)
        process.errorOccurred.connect(self._on_dl_error)
        self._dl_proc = process

        argv = fetch.download_argv(tools, result.video_id, folder)
        _log.info("download: %s (%s) -> %s", result.title, result.video_id, folder)
        process.start(argv[0], argv[1:])
        self.progress.emit(0.0)
        return True

    def _consume(self, line: str) -> None:
        """Offer one whole line to both parsers. Neither is the usual answer."""
        fraction = fetch.parse_progress(line)
        if fraction is not None:
            self.progress.emit(fraction)
            return
        path = fetch.parse_filepath(line)
        if path is not None:
            self._dl_path = path

    def _on_dl_output(self) -> None:
        if self._dl_proc is None:
            return
        self._dl_buf += _reader(self._dl_proc)
        # Progress and the finished path arrive interleaved with yt-dlp's own
        # chatter. Only whole lines are consumed -- a chunk off a pipe ends
        # wherever it ends, and half a path is worse than no path.
        *lines, self._dl_buf = self._dl_buf.split("\n")
        for line in lines:
            self._consume(line)

    def _on_dl_finished(self, code: int, _status) -> None:
        process = self._dl_proc
        if process is None:
            return
        self._on_dl_output()
        # ...and then the tail, which `_on_dl_output` deliberately leaves alone
        # because it cannot know a line is finished until its newline arrives.
        # Here it can: the process has exited, so whatever is left is whole.
        # `after_move:filepath` is printed last and is exactly the line that
        # turns up with no newline behind it.
        if self._dl_buf.strip():
            self._consume(self._dl_buf)
        self._dl_buf = ""
        stderr = _text(process.readAllStandardError())
        self._dl_proc = None
        process.deleteLater()

        if code != 0:
            _log.warning("download failed (%d): %s", code, stderr.strip()[:400])
            self.failed.emit(_last_error(stderr))
            return
        _log.info("download finished: %s", self._dl_path)
        self.finished.emit(self._dl_path)

    def _on_dl_error(self, _error) -> None:
        if self._dl_proc is None:
            return
        self.cancel()
        self.failed.emit("Could not run yt-dlp")

    # -- shutdown ----------------------------------------------------------

    def cancel(self) -> None:
        """Stop everything. Idempotent, like every other teardown in this app.

        Wired to `aboutToQuit` next to `controller.shutdown`. Without it a
        yt-dlp survives the window and goes on writing into the music folder
        after the app that asked for it is gone -- which is worse than it
        sounds, because the next launch scans that folder and finds a
        half-written file.
        """
        self._stop_search()
        process, self._dl_proc = self._dl_proc, None
        if process is None:
            return
        process.disconnect(self)
        process.kill()
        process.waitForFinished(KILL_WAIT_MS)
        process.deleteLater()
        _log.info("download cancelled")
