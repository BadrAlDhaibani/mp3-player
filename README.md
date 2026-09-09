# XMB Player

A desktop MP3 player with a PlayStation 3 XMB skin. Point it at a folder, browse
your music, and drag one slider to turn any track into nightcore (faster, higher)
or daycore (slower, lower) while it's playing.

https://github.com/user-attachments/assets/2c7f0e35-23ff-4956-8acb-5d21d80266a2

[![CI](https://github.com/BadrAlDhaibani/mp3-player/actions/workflows/ci.yml/badge.svg)](https://github.com/BadrAlDhaibani/mp3-player/actions/workflows/ci.yml)

Windows · Python 3.13 · PySide6 · numpy · sounddevice · soundfile

---

## Why I built this

The PS3 dashboard is still the best-looking menu I've ever used, and I'd wanted
to rebuild it for a while. [Replace this with what actually got you started —
the XMB itself? nightcore edits on YouTube? wanting to see if you could?]

I also wanted an audio project where I owned the whole path instead of calling
someone else's `play()` and hoping. [What you wanted to prove to yourself here.]

The part I didn't see coming was [the thing that turned out to be hardest —
worth naming one, it's the most interesting sentence on this page].

---

## What it does

- **Nightcore and daycore, live.** Drag the slider and the pitch moves with the
  speed, in the track you're already hearing. `0.70x` is daycore, `1.30x` is
  nightcore. Nothing is pre-rendered and nothing is pitch-corrected — speeding
  up is *supposed* to make it squeakier.
- **The interface reads out the speed.** Deep blue at daycore, violet at
  nightcore. The background wave, the selection, every slider and every number
  shift together as you drag, so you can see the effect from any screen.
- **It tells you the real runtime.** `3:36 · plays in 2:46 at 1.30x`, updating
  as you move the slider.
- **Five colour themes.** Settings ▸ Theme, then `←` `→` to flip through them
  live. Remembered next launch, along with your folder, volume and speed.
- **Reads your tags.** Title, artist, album and embedded cover art. Untagged
  files just show their filename.
- **Shuffle and repeat.** `S` and `R`, or the two buttons in the bottom bar, or
  the rows in Settings. Repeat goes all → one → off; shuffle deals a fresh order
  and plays every track once before dealing another. Both remembered.
- **Search the folder.** `/` on the Music list, then type: it narrows to the
  tracks whose title or artist contains what you typed. `Enter` plays one and
  closes, `Esc` goes back to the whole library.
- **Get music.** A fourth category: type a song name, pick from the results, and
  it downloads into your music folder as an MP3 and appears in the list without
  interrupting whatever is playing. This one **needs two programs you install
  yourself** — see below.

### Screens

![Now Playing](docs/images/now-playing.png)

![The same screen at 0.80x, 1.00x and 1.30x](docs/images/speeds.png)

*The same screen at daycore, normal and nightcore. Everything follows the slider.*

![The music list](docs/images/music.png)

![Five colour themes](docs/images/themes.png)

*XMB Blue, Ember, Aurora, Vapor, Mono.*

---

## Download

Grab the latest `XMB-Player-<version>-windows.zip` from
[**Releases**](https://github.com/BadrAlDhaibani/mp3-player/releases), unzip it
anywhere, and run `XMB Player.exe`. No installer. Keep the folder together — the
exe needs the files next to it.

It writes one folder, `%APPDATA%/XMBPlayer`, holding your settings and a small
log. Delete that and the unzipped folder and it's gone.

**You'll get a SmartScreen warning the first time.** Click *More info*, then
*Run anyway*. It shows up for any exe without a code-signing certificate, and
those cost a few hundred a year, which I'm not spending on this. If you'd rather
not, [run it from source](#running-from-source) instead — it's the same app.

---

## Controls

| | |
|---|---|
| `←` `→` | move between Now Playing · Music · Settings · Get Music |
| `↑` `↓` | move down a list — or drive the speed slider on Now Playing |
| `Enter` | play the selected track, or open the selected setting |
| `Enter` on **Theme** | step into the row, then `←` `→` to browse, `Enter` or `Esc` to leave |
| `/` or `Ctrl` + `F` | on **Music**, search: type to narrow, `Esc` to clear |
| typing | on **Get Music**, search online: it looks after you stop, `Enter` downloads |
| `Backspace` | back a category — or one character, while searching |
| `Space` | play / pause |
| `S` | shuffle on / off |
| `R` | repeat: all → one → off |
| `Ctrl` + `←` `→` | previous / next track |
| `Shift` + `←` `→` | seek 5 seconds |
| `Home` `End` `PgUp` `PgDn` | jump around a list |
| `F11` | fullscreen |

The mouse works too: click a row to select it, click again to play, click a
category to switch, drag or scroll the speed slider.

First launch opens on **Settings ▸ Music folder**, since there's nothing to play
yet. It reads the `.mp3` files sitting directly in that folder, top level only.

---

## Running from source

```bash
python -m venv venv
venv/Scripts/python.exe -m pip install -r requirements.txt

# shortcuts on the Desktop and next to run.bat -- no console window, real icon
powershell -ExecutionPolicy Bypass -File tools/make_shortcut.ps1 -Here
```

Then double-click **XMB Player**. There's no build step: the shortcut points at
`pythonw.exe` and runs the live source, so edits show up on the next launch.

For debugging there's `run.bat`, which keeps a console so tracebacks and prints
land somewhere visible — a `.bat` always gets a console window, which is why the
quiet launcher is a shortcut instead. Either way the app also writes
`%APPDATA%\XMBPlayer\xmbplayer.log`.

```bash
run.bat                                    # console, for debugging
venv/Scripts/python.exe -m mp3player.app   # same thing, directly
```

To build the standalone exe: `venv/Scripts/python.exe tools/build_exe.py`. It
draws the icon, stamps the version, builds, then launches what it built and
closes it again to check nothing's missing.
[`docs/RELEASING.md`](docs/RELEASING.md) has the full checklist.

### Checks

```bash
venv/Scripts/python.exe -m ruff check .           # lint
venv/Scripts/python.exe -m mypy                   # types
venv/Scripts/python.exe -m pytest                 # core logic, no display needed
venv/Scripts/python.exe tools/shell_harness.py    # the real widgets, offscreen
```

The first three are what CI runs. The harness is a local step because it opens a
real audio stream and CI runners don't have a sound card, so the badge covers the
core rather than the interface.

[`CLAUDE.md`](CLAUDE.md) is my working notebook for this project: every decision
with the reason behind it, the patterns worth reusing, and the measurements they
came from. It's long, but it's where the actual thinking is.

---

## How it works

The pitch shift is the same trick as playing a record faster. There's one
always-on output stream, and the music is read out of memory at a fractional
position:

```python
ratio = speed * (file_sr / stream_sr)
idx   = pos + np.arange(frames) * ratio
i0    = idx.astype(np.int64)
frac  = (idx - i0)[:, None]
out   = samples[i0] * (1 - frac) + samples[i0 + 1] * frac
pos  += frames * ratio
```

`pos` is a float that advances continuously, so `speed` can be reassigned at any
moment and the audio follows without a gap. That's the whole feature.

The rest is keeping it quiet. Every gain change — play, pause, seek, track
change, volume — ramps over about 10 ms instead of jumping, because a gain that
jumps puts a vertical edge in the waveform, and that edge is an audible click.

---

## Get Music needs two programs, and doesn't ship them

The fourth category shells out to **[yt-dlp](https://github.com/yt-dlp/yt-dlp)**
to search and download, and to **[ffmpeg](https://ffmpeg.org/)** to turn what
comes down into an MP3. Neither is bundled: between them they're about 100 MB,
and a bundled yt-dlp goes stale — it needs updating whenever YouTube changes,
which is often.

Put both on your `PATH`, or drop the two `.exe` files in:

```
%APPDATA%\XMBPlayer\tools\
```

That's the same folder as `settings.json`. The app looks in both places every
time you open the category, so you don't have to restart after installing them.
Until it finds them, Get Music says which one is missing and does nothing else.

ffmpeg is genuinely required rather than a nice-to-have: the audio YouTube
serves is m4a or opus, and the decoder this player uses reads MP3 and nothing
else, so an unconverted download would be a file it can't play.

**A note on what this does.** Downloading from YouTube is against its Terms of
Service, and whether any particular download is lawful depends on what you're
downloading and where you are. This is a personal project and that's your call
to make — the feature is a wrapper around a tool you install yourself, and it
does nothing you couldn't do by typing the same command.

---

## Known limits

- **Some `.mp3` files aren't.** Around 8% of my library is actually MP4/AAC with
  the wrong extension, usually YouTube downloads. Those get sniffed by their
  magic bytes and skipped, and the app tells you how many rather than letting
  them silently disappear.
- **Speeding up aliases.** There's no anti-alias filter, so content above about
  17 kHz folds back at nightcore speeds. Every nightcore edit online does this.
- **Windows only.** It might work elsewhere, but I've never run it anywhere else
  and every measurement in the project is a Windows one.

---

## Licence

**GPL-2.0-or-later** — full text in [`LICENSE`](LICENSE). It's GPL because
[mutagen](https://mutagen.readthedocs.io/), which reads the ID3 tags, is.
Everything else it depends on is listed in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

No Sony assets are used. The XMB look is rebuilt from scratch in Qt, and the UI
sounds are generated with numpy at startup rather than shipped as files.
