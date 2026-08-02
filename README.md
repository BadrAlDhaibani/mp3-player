# XMB Player

A small desktop MP3 player wearing a **PlayStation 3 XMB** skin. Point it at a
folder, browse the tracks, play them — and warp the audio into **nightcore**
(sped up, pitched up) or **daycore** (slowed down, pitched down) live, with a
slider, while it plays.

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
- **The wave reads out the speed.** Deep blue at daycore, the app's own blue at
  1.00x, violet at nightcore — so the background tells you what the effect is
  doing while you are looking at some other category.
- **It tells you how long the track will actually take.** `4:07 · plays in
  3:10 at 1.30x`. It moves as you drag.

## What it doesn't

Parked until after v1, deliberately: ID3 tags and album art, a spectrum
visualizer, shuffle/repeat/queue, exporting the warped audio to a file,
subfolders, and more than one library folder at a time.

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

---

## Keys

| | |
|---|---|
| `←` `→` | move between Now Playing · Music · Settings |
| `↑` `↓` | move down a list — or, on Now Playing, drive the speed slider |
| `Enter` | play the selected track, or open the selected setting |
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
volume and speed, in `%APPDATA%/XMBPlayer/settings.json`.

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
- **Windows only in practice.** Nothing is Windows-specific by design — the
  device picker falls back to whatever PortAudio offers — but it has only been
  run and measured there.

---

## Developing

```bash
venv/Scripts/python.exe -m pytest                 # core only: no display, no Qt
venv/Scripts/python.exe tools/shell_harness.py    # the real widgets, offscreen
```

`tests/` covers `core/` and never needs a display. The shell is checked by
`tools/shell_harness.py`, which drives the actual widgets through synthesized
key and mouse events with a real audio stream open.

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
```

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
