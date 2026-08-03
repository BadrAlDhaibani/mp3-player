# Third-party licence texts

Verbatim licences for components whose own packaging does **not** carry one.
This folder is not a complete list of what XMB Player depends on — that is
[`../THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md), which says what each
component is and what it is used for.

| File | Applies to | Why it is here |
|---|---|---|
| `LGPL-3.0.txt` | Qt, via PySide6 / PySide6_Essentials / PySide6_Addons / shiboken6 | The wheels ship only `LicenseRef-Qt-Commercial.txt`, which is the *other* side of Qt's dual licence. LGPLv3 §4(b) asks that a copy accompany the combined work. |
| `GPL-3.0.txt` | the same | LGPLv3 is written as a set of additional permissions on top of GPLv3 and incorporates it by reference, so §4(b) asks for both. |
| `PortAudio.txt` | PortAudio, bundled inside the `sounddevice` wheel | MIT, and MIT asks that the notice be included in all copies. The wheel ships a `README.md` and no licence file. |

Everything else already brings its own text along and is not duplicated here:
libsndfile's LGPL-2.1 arrives in the build as `_internal/_soundfile_data/COPYING`,
numpy's BSD-3 inside its `dist-info`, and mutagen's GPL-2.0 is the same text as
[`../LICENSE`](../LICENSE), which is XMB Player's own licence.

These are checked in rather than downloaded during a build, so cutting a release
does not depend on gnu.org being reachable.
