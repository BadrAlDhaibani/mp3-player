"""XMB Player -- a desktop MP3 player with a live nightcore/daycore slider.

Copyright (C) 2026 Badr Al-Dhaibani. GPL-2.0-or-later; see LICENSE.

This module is imported by everything, including `core/`, so it stays empty of
imports -- no Qt, no numpy, nothing that could turn the seam into a suggestion.
`__version__` is the single source of truth for which build this is: `app.py`
hands it to `QApplication`, and `tools/build_exe.py` stamps it into the exe's
Windows version resource and into the zip's filename. Bump it here and nowhere
else: a release is this line changing, and every artifact follows from it.
"""

from __future__ import annotations

__version__ = "1.1.0"
