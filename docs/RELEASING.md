# Releasing XMB Player

The checklist for cutting a release. It lives here rather than in CI because
**most of these steps cannot run on a GitHub runner** — the shell harness opens
a real WASAPI stream, the renders need a real font database, and the smoke test
launches a window. A runner has none of the three. CI covers `core/`; this file
covers everything else, and the two do not overlap by accident.

Everything below runs from the repo root with the venv's interpreter.

---

## 1. Decide the version

`mp3player/__init__.py` owns `__version__` and **nothing else carries it**. The
zip name, the exe's Windows version resource and `QApplication.applicationVersion()`
all read from there, so bumping it in that one file is the whole job.

```python
__version__ = "1.2.0"
```

Rough rule, consistent with how `1.1.0` was arrived at: a batch that adds a
feature is a minor bump, a batch that only fixes things is a patch bump, and
nothing has yet justified a major. `tests/test_version.py` holds it to a shape
the Windows resource can actually take — a version the resource cannot parse
ships happily as `0.0.0.0` in the file properties, which is the failure this
guards.

## 2. The checks, in order

```bash
venv/Scripts/python.exe -m ruff check .
venv/Scripts/python.exe -m mypy
venv/Scripts/python.exe -m pytest
venv/Scripts/python.exe tools/shell_harness.py
```

The first three are what CI runs. **The fourth is the only coverage `ui/` has**
and CI will never run it, so skipping it here means shipping the whole front end
unchecked.

> **Known flake, not a regression.** `...resuming where it left off` fails
> roughly one run in five at `0.00s` instead of `~0.05s`. It is a real WASAPI
> reopen racing a position read and it passes on a re-run. One line failing with
> everything else green is the known state; anything else is yours.

## 3. Look at it

The harness cannot judge width, colour or motion — the offscreen platform has no
font database and `QFontMetrics` there returns fallback widths about 2.5x too
wide. Every layout bug this project has had was found by rendering a PNG and
looking at it, and none by an assertion.

```bash
venv/Scripts/python.exe tools/render.py out.png --theme all      # 5 palettes x 3 speeds
venv/Scripts/python.exe tools/render.py out.png --what now --size 720x480
venv/Scripts/python.exe tools/render.py out.png --what settings --select 2 --step
venv/Scripts/python.exe tools/make_icon.py icon.png --preview    # every icon size
```

720x480 is `WINDOW_MINIMUM` and is where things collide; the default window
hides most of it. If the release changed a colour or a metric, render both.

## 4. Build

```bash
venv/Scripts/python.exe tools/build_exe.py
```

Around 60–100 s. It generates the icon and the version resource into a scratch
directory, runs PyInstaller, copies the licence files to the top of the app
folder, **launches the exe and closes it**, and only then writes the zip. A
build that fails the smoke test is not zipped, because an archive sitting next
to an error message is an archive that eventually gets uploaded.

A window appears for a few seconds during the smoke test. That is the test:
under `QT_QPA_PLATFORM=offscreen` there is no window handle to close, so the exit
code and the shutdown path could not be checked. It runs against a redirected
`%APPDATA%`, so it cannot touch your real `settings.json`.

`--skip-smoke` exists for a machine with no audio output, where the app
correctly puts up a modal box and never opens a stream. **It is not for saving
ten seconds before a release.**

Output:

```
dist/XMB Player/XMB Player.exe
dist/XMB-Player-<version>-windows.zip
```

## 5. Check the artifact, not the build log

```powershell
# the version reached the binary
(Get-Item "dist/XMB Player/XMB Player.exe").VersionInfo | Format-List

# the licences are at the top of the folder, not only inside _internal/
Get-ChildItem "dist/XMB Player"
```

Expect `LICENSE`, `THIRD_PARTY_NOTICES.md` and `licenses/` beside the exe, and
file properties reading the new version, `XMB Player`, and the GPL copyright
line.

**Look at the icon in Explorer**, at both Large and Extra Large. It is drawn
fresh from `theme.py` on every build, so a palette change moves it, and the
16 px frame is the one that stops reading first.

> Batch 11 found two missing third-party licence texts by inspecting a built
> zip rather than trusting the dependency table. Unzipping the artifact
> somewhere clean and looking is worth the minute.

## 6. Tag and push

```bash
git tag -a v<version> -m "XMB Player <version>"
git push origin main
git push origin v<version>
```

Tag the commit that was built, not a later one.

## 7. Cut the GitHub release

Draft a release against the tag at
<https://github.com/BadrAlDhaibani/mp3-player/releases/new> and **attach
`dist/XMB-Player-<version>-windows.zip`**. The zip is the release; the source
tarball GitHub generates is not a thing anyone can run.

Distribution is GitHub Releases and the zip, deliberately — no installer, no
PyPI, no winget. The reasoning is in `CLAUDE.md`'s Batch 15 section.

The release notes should say, at minimum: what changed, that it is Windows only,
and that SmartScreen will warn (see `README.md` — link to that section rather
than restating it, so there is one copy).

## 8. Afterwards

Update the *Resume here* block at the top of `CLAUDE.md`: what shipped, what the
`.exe` is current as of, and where the tag now points. That block is the thing
the next session reads first, and a stale one costs more than it looks like it
should.

---

## Why there is no code signing

An unsigned executable downloaded from the internet gets Microsoft Defender
SmartScreen's "Windows protected your PC" dialog, and most people stop there.
The fix is an Authenticode certificate, which costs real money annually and,
for an OV certificate, still needs to build reputation before the warning goes
away. That is not a sensible trade for a novelty MP3 player, so the README
explains the warning instead. If this ever changes, the signing step goes
between 4 and 5 — sign the exe, *then* zip.
