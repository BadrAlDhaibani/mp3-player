# Third-party notices

XMB Player itself is **GPL-2.0-or-later** (see `LICENSE`). It is built on the
components below, each under its own licence. Nothing here is vendored into the
repository — from source they are ordinary `pip` dependencies — but the
standalone Windows build in `dist/XMB Player/` **incorporates all of them**, so
a copy of this file ships inside that folder.

## Why the distributed build is GPL

`mutagen` is **GPL-2.0-or-later** and `mp3player/core/tags.py` imports it
directly. Running from source, that is a combined work; the PyInstaller build
goes further and packs mutagen's bytecode *inside `XMB Player.exe` itself*, in
the archive appended to the bootloader, alongside ours. Either way the result is
covered by the GPL, and so the whole of XMB Player is offered under
GPL-2.0-or-later rather than under a permissive licence with an inconvenient
asterisk. This was a deliberate choice, not an accident of dependency selection
— the alternative was hand-rolling an ID3 reader to avoid mutagen, which was
considered and rejected on the grounds that its failure mode is silently mangled
track titles.

## How PyInstaller changes the picture

The build is a **onedir** PyInstaller bundle. `XMB Player.exe` is a bootloader
with an archive of pure-Python bytecode appended to it, and everything with
native code — Qt, numpy, libsndfile, PortAudio — sits beside it in `_internal/`
as an ordinary `.pyd`/`.dll` loaded at runtime. It is *not* a static link and
not a single-file archive. This matters for the LGPL components:

- **Qt (PySide6, shiboken6)** is used under the **LGPLv3**, which asks that the
  end user be able to replace the Qt libraries with their own build. A onedir
  bundle satisfies that directly: `PySide6/*.pyd` and the `Qt6*.dll` files in
  `_internal/` can be swapped in place without rebuilding or relinking anything
  of ours. Qt is unmodified.
- **libsndfile**, shipped inside the `soundfile` wheel, is **LGPL-2.1** and is
  present as `_soundfile_data/libsndfile*.dll` — likewise replaceable in place,
  likewise unmodified.

Nothing in the build is statically linked, and no third-party source is
modified. The complete corresponding source for XMB Player is the repository
this file came from.

## The components

| Component | Version built against | Licence | Role |
|---|---|---|---|
| [mutagen](https://mutagen.readthedocs.io/) | 1.48.1 | GPL-2.0-or-later | ID3 tags and embedded cover art |
| [PySide6](https://doc.qt.io/qtforpython/) (+ `PySide6_Essentials`, `PySide6_Addons`) | 6.11.1 | LGPLv3 (also available under GPL-2.0 / GPL-3.0) | the entire UI |
| [shiboken6](https://doc.qt.io/qtforpython/shiboken6/) | 6.11.1 | LGPLv3 (as above) | PySide6's binding runtime |
| [numpy](https://numpy.org/) | 2.5.1 | BSD-3-Clause | every audio buffer, the resampler, the synthesized UI sounds |
| [sounddevice](https://python-sounddevice.readthedocs.io/) | 0.5.5 | MIT | the output stream; bundles **PortAudio** (MIT) |
| [soundfile](https://python-soundfile.readthedocs.io/) | 0.14.0 | BSD-3-Clause | MP3 decoding; bundles **libsndfile** (LGPL-2.1) |
| [pytest](https://pytest.org/) | 9.1.1 | MIT | tests only — not shipped |
| [PyInstaller](https://pyinstaller.org/) | 6.21.0 | GPL-2.0-or-later, with an exception permitting proprietary bundled apps | builds the exe — not shipped, and its exception is moot here since we are GPL anyway |

Versions are the ones the shipped build was produced against; `requirements.txt`
is the authority on what a source checkout installs.

## Where the licence texts are

**In a release zip, all of them travel with the binary.** Nothing here relies on
a link staying alive, because two of these licences specifically ask for a copy
rather than a reference — LGPLv3 §4(b) wants the combined work accompanied by a
copy of the LGPL and the GPL it builds on, and MIT wants its notice included in
all copies.

Most components carry their own text into the build inside their package
directory. In `dist/XMB Player/`:

```
LICENSE                                        this project, and mutagen: GPL-2.0
_internal/_soundfile_data/COPYING              libsndfile: LGPL-2.1
_internal/numpy-*.dist-info/licenses/          numpy: BSD-3 (plus its vendored parts)
```

Two do not ship a licence of their own, so verbatim copies are checked into this
project's `licenses/` folder and copied into the release beside the exe:

```
licenses/LGPL-3.0.txt      Qt, via PySide6 / PySide6_Essentials /
licenses/GPL-3.0.txt         PySide6_Addons / shiboken6
licenses/PortAudio.txt     PortAudio, inside the sounddevice wheel
```

- **PySide6, PySide6_Essentials, PySide6_Addons and shiboken6** carry only
  `LicenseRef-Qt-Commercial.txt` in their `dist-info/licenses/` — the *other*
  side of Qt's dual licensing, which is not the side used here. Qt's own summary
  of the arrangement is at <https://doc.qt.io/qt-6/licensing.html>.
- **PortAudio**, inside the `sounddevice` wheel at
  `_sounddevice_data/portaudio-binaries/`, ships a `README.md` and no licence
  file at all.

From a source checkout the authoritative copy of every other licence is the one
in the environment it was installed into — `venv/Lib/site-packages/`, under each
package's `dist-info/licenses/`.

`LICENSE` at the root of this project is the GPL-2.0 text verbatim, which is
also mutagen's and PyInstaller's licence.

## What is *not* third-party

The UI sounds are synthesized in numpy at startup (`core/audio/sfx.py`) rather
than shipped as audio files, and the XMB look is an original reimplementation in
Qt — no Sony asset, sound or image is included, copied or derived from. That was
the point of synthesizing them.
