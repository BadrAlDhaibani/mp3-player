# XMB Player

A small desktop MP3 player wearing a **PlayStation 3 XMB** skin. Point it at a
folder, browse the tracks, play them — and warp the audio into **nightcore**
(sped up, pitched up) or **daycore** (slowed down, pitched down) live, with a
slider, while it plays.

[![CI](https://github.com/BadrAlDhaibani/mp3-player/actions/workflows/ci.yml/badge.svg)](https://github.com/BadrAlDhaibani/mp3-player/actions/workflows/ci.yml)

Windows · Python 3.13 · PySide6 · numpy · sounddevice · soundfile

---

## What it does

- **Live speed, live pitch.** Drag the slider on Now Playing and the pitch moves
  with it, in the audio you are already hearing. `0.80x` is daycore, `1.30x` is
  nightcore, and everything in between is a fractional read position with linear
  interpolation. No time-stretch, no pitch preservation — that *is* nightcore.
- **The XMB.** A crossbar you navigate with the arrow keys, a wave that lights
  the row your selection sits on, and UI blips synthesized in numpy rather than
  shipped as files.
- **The whole app reads out the speed.** Deep blue at daycore, the app's own blue
  at 1.00x, violet at nightcore — the wave, the selection, every slider fill and
  every readout travel together, so the colour tells you what the effect is doing
  while you are looking at some other category.
- **Five colour presets.** Settings ▸ Theme, Enter, then `←` `→` to walk them —
  the app recolours as you go, so you pick by looking. **XMB Blue**, **Ember**
  (amber → coral → hot pink), **Aurora** (teal → green → chartreuse), **Vapor**
  (cyan → hot pink → coral) and **Mono** (near-white throughout). A theme
  changes only where the colour travels as the slider moves; the navy background
  and the text stay put. Remembered across launches.
- **It tells you how long the track will actually take.** `4:07 · plays in
  3:10 at 1.30x`. It moves as you drag.
- **It reads your tags.** Title, artist, album and the embedded cover. A tagged
  file is listed under its tag with the artist alongside it; an untagged one
  keeps its filename and gets the note glyph, exactly as before.

## What it doesn't

Parked, deliberately: a spectrum visualizer, shuffle/repeat/queue, exporting the
warped audio to a file, subfolders, and more than one library folder at a time.

It does not *write* tags either — nothing here edits your files.

---

## Download

Grab the latest `XMB-Player-<version>-windows.zip` from
[**Releases**](https://github.com/BadrAlDhaibani/mp3-player/releases), unzip it
anywhere, and run `XMB Player.exe` inside.

There is no installer and nothing to set up. It writes one folder,
`%APPDATA%/XMBPlayer`, holding your settings and a small log; deleting the
unzipped folder and that one removes it completely.

Keep the whole folder together — the exe needs the files beside it. Making a
shortcut to the exe is the tidy way to get it onto your desktop or Start menu.

### "Windows protected your PC"

You will get this the first time, and it is expected:

> **Windows protected your PC**
>
> Microsoft Defender SmartScreen prevented an unrecognised app from starting.

Click **More info**, then **Run anyway**.

The warning is not about anything found in the file. SmartScreen shows it for
any executable that has no code-signing certificate and no download history, and
a certificate costs a few hundred pounds a year — which is not a sensible thing
to buy for a novelty MP3 player. So the honest options were to explain the
warning or to pretend it doesn't happen, and this is the first one.

If you would rather not click through a warning from a stranger — entirely
reasonable — [run it from source](#from-source) instead. It is the same
application; the exe is only these files with a Python interpreter stapled to
the front.

---

## Running it

### From source

```bash
python -m venv venv
venv/Scripts/python.exe -m pip install -r requirements.txt

run.bat                                    # console: tracebacks land here
venv/Scripts/python.exe -m mp3player.app   # the same thing, directly
```

`run.bat` keeps a console open, which is what you want while changing anything.
For the real-app feel there is a desktop shortcut through `pythonw.exe` with no
console window:

```bash
powershell -ExecutionPolicy Bypass -File tools/make_shortcut.ps1
```

Re-run that if the repo moves — the shortcut points at an absolute path. Both
launchers run the live source; there is no build step.

### As a standalone `.exe`

```bash
venv/Scripts/python.exe tools/build_exe.py
```

Produces `dist/XMB Player/XMB Player.exe` and a zip beside it. It is a folder
rather than a single file on purpose: one-file PyInstaller unpacks ~120 MB of Qt
to a temp directory on *every* launch, which is several seconds of nothing
before the window appears.

The icon and the Windows version stamp are drawn and written at build time from
`theme.py` and `__version__`, so neither is checked in and neither can drift.
When it finishes, the build launches the exe, waits until it has opened an audio
device, and closes it again — a window will appear for a few seconds. That is
the only check that catches a missing libsndfile or PortAudio, because nothing
in the bytecode points at either and a broken build still reports success.
`docs/RELEASING.md` is the full checklist.

---

## Keys

| | |
|---|---|
| `←` `→` | move between Now Playing · Music · Settings |
| `↑` `↓` | move down a list — or, on Now Playing, drive the speed slider |
| `Enter` | play the selected track, or open the selected setting |
| `Enter` on **Theme** | step into the row; `←` `→` then walk the presets, `Enter` or `Esc` leaves |
| `Backspace` | back a category |
| `Space` | play / pause |
| `Ctrl` + `←` `→` | previous / next track |
| `Shift` + `←` `→` | seek 5 s |
| `Home` `End` `PgUp` `PgDn` | jump around a list |
| `F11` | fullscreen (`Esc` leaves it) |

The mouse works too: click a row to select it, click it again to play it, click
a category to switch, and drag or scroll the speed slider.

---

## First run

There is no folder yet, so it opens on **Settings ▸ Music folder** with one
press between you and a folder picker. It reads the `.mp3` files sitting
directly in that folder — top level only — and remembers it, along with your
volume, speed and theme, in `%APPDATA%/XMBPlayer/settings.json`.

## When something goes wrong

There is a log next to that file, at `%APPDATA%/XMBPlayer/xmbplayer.log`. It
records which output device was opened, anything that went wrong with it, and
any unexpected error — capped at a few hundred kilobytes, so it looks after
itself. If the app puts up a box saying something went wrong, that file is what
it is pointing at, and it is the thing to send on.

---

## Known limits

- **Some `.mp3` files aren't.** About 8% of the library this was built against
  are really MP4/AAC saved with the wrong extension, usually YouTube downloads.
  libsndfile can't decode those, so they are sniffed by magic bytes and skipped,
  and the app tells you how many rather than letting them vanish. Settings ▸
  Rescan folder shows the count.
- **Speeding up aliases.** There is no anti-alias filter, so content above about
  17 kHz folds back at nightcore speeds. Every nightcore edit on the internet
  does exactly this.
- **The whole file is decoded into memory** — around 62 MB for a four-minute
  track. Fine for one at a time, and it makes seeking a pointer move.
- **Decoding blocks the UI** for 0.07–0.21 s per track on the test library. You
  can feel it on a fast next/next/next.
- **Opening a folder reads every tag**, which is about 110 ms for the folders
  this was measured on. Almost all of that is the embedded cover art going past,
  so a small folder of well-tagged albums costs more than a big one of bare
  rips. Covers themselves are only read for the track you play.
- **Tags are trusted over filenames.** If a rip is tagged `Track 01`, that is
  what the list will say. There is no toggle; renaming or retagging the file is
  the fix.
- **Windows only.** Not "portable in principle": every measurement here is a
  Windows one — WASAPI at 22 ms, `%APPDATA%`, `run.bat`, the shortcut script —
  and it has never been run anywhere else. The device picker does fall back to
  whatever PortAudio offers, so it might work elsewhere; nobody has checked, and
  claiming portability nobody has tested is worse than not claiming it.

---

## Developing

```bash
venv/Scripts/python.exe -m ruff check .           # lint
venv/Scripts/python.exe -m mypy                   # types
venv/Scripts/python.exe -m pytest                 # core only: no display, no Qt
venv/Scripts/python.exe tools/shell_harness.py    # the real widgets, offscreen
```

The first three are what CI runs, on Windows, on every push. `pyproject.toml`
configures all of them and says why each rule is off where it is off.

**The badge does not mean the UI is tested.** `tests/` covers `core/` and never
needs a display; the shell is checked by `tools/shell_harness.py`, which drives
the actual widgets through synthesized key and mouse events **with a real audio
stream open** — and a CI runner has no audio device, so that is a local step and
always will be. Run it before you ship anything.

Neither can judge how wide text is — the offscreen platform has no font
database, and `QFontMetrics` there returns fallback widths about 2.5x too large.
Anything about collisions, elision or two labels touching has to be checked by
rendering with the real platform and looking at it. That is where every layout
bug so far has been found.

Three more tools, each for a thing that can only be judged by a sense:

```bash
venv/Scripts/python.exe tools/sfx_harness.py            # hear the UI sounds
venv/Scripts/python.exe tools/filmstrip.py out.png      # see an animation
venv/Scripts/python.exe tools/engine_harness.py         # the audio engine, no Qt
venv/Scripts/python.exe tools/make_icon.py i.png --preview   # the icon, all sizes
```

[`docs/RELEASING.md`](docs/RELEASING.md) is the checklist for cutting a release,
and it is a separate file for the same reason the harness is a local step: most
of what it lists cannot run on a machine with no display and no sound card.

`CLAUDE.md` is the project's memory: the decisions log says what was settled and
why, and the conventions are the patterns worth reusing. Read those before
changing anything structural — they are accumulated agreements, not suggestions.

---

## How the trick works

One always-on output stream, opened at launch, outputting silence when nothing
plays. It mixes the music voice against a pool of one-shot SFX voices. The music
voice is read at a fractional position:

```python
ratio = speed * (file_sr / stream_sr)   # sample-rate conversion, free
idx   = pos + np.arange(frames) * ratio
i0    = idx.astype(np.int64)
frac  = (idx - i0)[:, None]
out   = samples[i0] * (1 - frac) + samples[i0 + 1] * frac
pos  += frames * ratio
```

Because `pos` is a float advanced continuously, `speed` can be reassigned at any
moment and the audio follows seamlessly. That's the whole thing.

Everything that changes a gain — play, pause, seek, track change, volume —
ramps over about 10 ms instead of jumping, because a gain that jumps puts a
vertical edge in the waveform and that edge is the click.

---

## Dependencies

PySide6, numpy, sounddevice (PortAudio), soundfile (libsndfile), and
[mutagen](https://mutagen.readthedocs.io/) for ID3 tags. `requirements.txt` is
the authority on versions.

## Licence

**GPL-2.0-or-later** — the full text is in [`LICENSE`](LICENSE).

It is GPL because mutagen is, and `core/tags.py` links it directly. Every
third-party component, what it is used for and how the packaged `.exe` affects
each one is set out in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md), which ships inside the zip
along with [`licenses/`](licenses/) — the texts for the two components that do
not carry one themselves.

No Sony asset is included or derived from. The XMB look is an original
reimplementation in Qt, and the UI sounds are synthesized in numpy at startup
rather than shipped as files.
