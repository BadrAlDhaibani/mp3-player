"""`mp3player.__version__` is load-bearing, so it gets held to a shape.

`tools/build_exe.py` turns it into a Windows version resource -- four 16-bit
integers, which is the one thing a version string here is not free to stop
being -- and into the release zip's filename. Neither of those fails loudly:
a non-numeric version yields `(0, 0, 0, 0)` in the exe's properties and a zip
called `XMB-Player-dev-windows.zip`, both of which ship happily and are wrong.

These also stand in for importing the package at all. `mp3player/__init__.py`
is imported by every module in `core/`, and the reason it holds nothing but a
string is that anything else in there would cross the no-Qt seam from above.
"""

from __future__ import annotations

import re

import mp3player


def test_version_is_a_nonempty_string() -> None:
    assert isinstance(mp3player.__version__, str)
    assert mp3player.__version__


def test_version_is_dotted_numbers() -> None:
    # Two to four numeric components, optionally with a pre-release suffix on
    # the last one. `version_quad` truncates the suffix; it cannot invent
    # numbers that were never there.
    assert re.fullmatch(r"\d+(\.\d+){1,3}([a-z]+\d*)?", mp3player.__version__)


def test_version_components_fit_a_windows_resource() -> None:
    for chunk in mp3player.__version__.split("."):
        digits = re.match(r"\d+", chunk)
        assert digits is not None
        assert int(digits.group()) < 65536


def test_package_import_pulls_in_nothing_heavy() -> None:
    """The package root stays import-free, so `core/` can lean on it."""
    source = (
        __import__("pathlib").Path(mp3player.__file__).read_text(encoding="utf-8")
    )
    code = [
        line
        for line in source.splitlines()
        if line.startswith(("import ", "from "))
        # `__future__` is a compiler directive, not a dependency.
        and "__future__" not in line
    ]
    assert code == []
