# XMB MP3 Player

A small desktop MP3 player with a **PlayStation 3 XMB** skin. Point it at a folder,
browse the `.mp3` files in it, play them — and warp the audio into **nightcore**
(sped up, pitched up) or **daycore** (slowed down, pitched down) live with a slider.

This file is the project's memory and **the single source of truth for status**.
If a box below isn't ticked, it isn't done.

> ## ▶ Resume here
>
> **Done:** Batch 0 (spike) · Batch 1 (core library & settings) ·
> Batch 2 (audio engine, 174 tests green) · Batch 3 (ugly working player) ·
> Batch 4 (XMB shell structure) ·
> Batch 5 (motion & atmosphere — it moves now, and there's a wave behind it)
> **Next:** **Batch 6 — sound & feel.** The synthesized blips from `sfx.py`
> exist and are tested but nothing calls them; hook `move` / `confirm` / `back`
> to the navigation that Batch 5 just gave a tempo, then tune by ear.
> `controller.py` and everything under `core/` have still not been touched
> since Batch 3.
>
> Before writing any of it, read the note in the conventions about
> `tools/shell_harness.py` running offscreen with no fonts. Every layout bug in
> Batch 4 was found by rendering a PNG and looking at it; none by an assertion —
> and in Batch 5 the glow took two goes to stop looking like a border, both
> caught the same way.
>
> Starting a fresh session? Read the decisions log and conventions below before
> writing anything — they're the accumulated agreements, not suggestions.
> Then confirm the batch with the user before starting it.

---

## v1 scope

**In:** pick a folder · browse its tracks · play/pause/next/prev/seek · a live
speed slider running Daycore → Nightcore · XMB look · synthesized UI sounds.

(There are no longer separate Nightcore/Normal/Daycore *preset buttons* — the
two presets became the ends of the slider itself. See the decisions log.)

**Deliberately out of v1** — good ideas, parked until v1 actually ships:
ID3 tags & album art · spectrum visualizer · shuffle/repeat/queue · export to file ·
subfolder recursion · multiple library folders.

---

## Decisions log

Each row is settled. Don't re-litigate — if a decision needs to change, change it
here and write down why.

| Decision | Why |
|---|---|
| **Live effect, not rendered files** | Dragging the speed slider must change what you hear *right now*. |
| **Pitch linked to speed** | That *is* nightcore. Plain resampling — no time-stretch, no pitch preservation. |
| **We own the audio path** (decode → numpy → PortAudio) | `QMediaPlayer.setPlaybackRate()` delegates to Windows Media Foundation, which *preserves* pitch — the exact opposite of what we want. |
| **PS3 XMB theme** | Crossbar + wave background + glossy panels. Its structure maps naturally onto a music player. |
| **UI sounds synthesized in code** | Sony's XMB sounds are their copyrighted assets. numpy-generated blips are free, tunable, and add no binary files to git. |
| **Frameless window, mouse + keyboard** | Console look to the edges, but still usable as a normal desktop app. |
| **One folder, top-level `.mp3` only** | Smallest thing that's genuinely useful. Recursion is a post-v1 add. |
| **Qt Widgets, 100% Python** | Novelty-scale project; one language beats the last 15% of polish. Reversible — see the `core/` rule below. |
| **`soundfile` as the decoder** | Verified in Batch 0: libsndfile 1.2.2 ships `MP3 = MPEG-1/2 Audio`. No ffmpeg needed. |
| **WASAPI output, device mix rate, blocksize 512** | Measured in Batch 0: MME 186 ms, DirectSound 240 ms, **WASAPI 22 ms**. Anything above ~50 ms makes UI blips feel disconnected from the keypress. |
| **Stream sample rate is negotiated, not fixed** | WASAPI shared mode only accepts the device's mix rate (48 kHz here, not 44.1). Costs nothing — the file's rate is folded into the resample ratio anyway. |
| **Dev launcher runs live source; `.exe` only at v1** | PyInstaller with PySide6 is 80–150 MB and 30–60 s per build — rebuilding after every edit would dominate development. A shortcut pointing at `pythonw.exe` gives the same double-click feel with zero rebuild cost. |
| **Two launchers: `run.bat` (console) + shortcut (no console)** | The console is worth having while debugging — tracebacks and prints go somewhere visible. The shortcut is for the real-app feel. Same live source behind both. |
| **`Mixer` is split out of `AudioEngine`** | The callback body is where every subtle bug will live (fades, seek timing, end-of-track), and it needed to be testable block-by-block with no device, no threads and no real time. `AudioEngine` is left as a thin shell over PortAudio. Batch 2: 41 offline tests against `Mixer`, none needing a sound card. |
| **End of track is polled, not pushed** | The roadmap said "end-of-track callback", but the conventions forbid calling anything from the audio thread. The callback sets a flag; `take_finished()` reports it once to the 30 Hz poll. No callable is exposed at all — a footgun nobody needs. |
| **Seeks are serial-tagged, not consume-and-clear** | A slider drag posts a stream of seeks. If the audio thread cleared the request slot, a seek posted microseconds later could be dropped. The audio thread only ever *reads* the slot and records which serial it applied, so the last seek always wins. |
| **Tracks fade out at their own end** | Files do not reliably end on silence. Running off the end and zero-filling is itself a step — the first thing Batch 2's tests caught. `resample` reports how many frames were real; the voice ramps the last 10 ms down to meet the silence. |
| **Non-MP3 files are skipped, not listed** | ~8% of this library's `.mp3` files are actually MP4/AAC (YouTube downloads with the wrong extension). libsndfile can't decode AAC, and adding PyAV (~35 MB) isn't worth it for a novelty app. `scan_folder()` sniffs magic bytes and drops anything that isn't real MP3. Revisit post-v1 if the missing 8% becomes annoying. |
| **Widgets never touch `AudioEngine`** | Everything goes through `PlayerController`. That's what lets Batch 4 delete `main_window.py` and keep the controller — the seam is only real if nothing crosses it. |
| **Decode stays on the UI thread in v1** | Measured 0.07–0.21 s for this library. A worker thread means a load token, a cancel path, and a race on every fast next/next/next. Real cost, speculative benefit — revisit in Batch 7 if it grates. |
| **Settings are written on an 800 ms debounce** | A volume drag emits a change per pixel; none of them deserve a disk write. Flushed unconditionally on `shutdown()`, so quitting always persists. |
| **Seek commits on release; speed is live** | Dragging the *speed* slider and hearing the pitch move is the entire app. A live seek would post a fade-jump-fade per pixel and sound like a skipping CD, so it waits for release. |
| **Auto-advance wraps the list** | Running off the last track loops to the first. Matches the Batch 2 harness, and "stop dead at the end" is a worse default than repeat-all. Not a shuffle/repeat *feature* — that's still post-v1. |
| **Categories: Now Playing · Music · Settings** | Chosen with the user in Batch 4. Column-per-context, closest to real XMB. |
| ~~Speed and volume live in the transport bar~~ → **volume only** | *Revised after Batch 4's first real run.* The original reasoning — the live speed slider is the whole app, so keep it on screen everywhere — was sound while Now Playing was a list of transport actions. Once Now Playing became the page for the effect, a second speed slider in the bottom bar was two controls for one value: exactly the redundancy that got `Play / Next / Previous / Restart` deleted from that column. Now Playing owns speed; the bar owns the track. |
| **Now Playing is the speed page** | Its old rows all duplicated the transport bar. What it lacked was the one thing the app is *for*. Art, the current track, and one slider. |
| **Now Playing is a *page*, not a list — its own widget** | The song title sits *on* the crossbar row and a fixed block hangs beneath it, which is the opposite arrangement to a column that pins its selection to the row and scrolls everything past it. `now_playing.py` rather than a mode inside `item_column.py`; `ItemColumn` went back to being a plain list. |
| **No "press Enter to adjust": Up/Down drive the slider** | Because the page has no list, the vertical arrows have nothing else they could mean — so the step-in mode was deleted rather than advertised. A hint under the track says `↑ ↓ adjust` up front. Left/Right stay category nav everywhere. |
| **The info block shows the warped length** | `2:00 · plays in 1:44 at 1.15x`. It's the one number only this app can tell you and it moves as the slider does. Suppressed at 1.00x, where it would just repeat itself. |
| **The crossbar rule stops at the item column** | Run full width it strikes through whatever sits on the row — the Now Playing song title most obviously — and past the selection plate it was only ever a stray segment. |
| **The status line is right-aligned** | It's the only edge of the stage nothing else claims: the left gutter is the art, and the left of the column is the key hint and, further down a long list, the track titles. |
| **The speed range is the two presets: 0.80x–1.30x** | So the slider's end labels can be read literally — slam the handle right and you get nightcore, no explanation needed. `MIN_SPEED`/`MAX_SPEED` are now *defined as* `DAYCORE_SPEED`/`NIGHTCORE_SPEED`. Costs the extremes; 1.50x is chipmunks and 0.50x is a dirge, so little was lost. `tools/engine_harness.py` keeps its own wider 0.5–1.5 bounds — it probes the engine, not the product. |
| **Slider rows are stepped into: Enter, then arrows, then Enter/Esc** | Left/Right are category navigation and can't be spent on a value. This is what real XMB does with slider items, and the row outlines itself while it holds the arrow keys so the mode is visible. |
| **The art placeholder lives in the gutter, not above the items** | Stacked above the column it competed with them for vertical room, and at 720x480 there wasn't any — it clipped, then had to be dropped. Out in the empty space left of the column its size is bounded by the *gutter*, so no supported window size can take it away. |
| **The window is a plain `QWidget`, not a `QMainWindow`** | The only thing wanted from `QMainWindow` was a central widget, and its layout ignores the contents margins that give the frameless resize grips somewhere to live. |
| **Move/resize via `startSystemMove` / `startSystemResize`** | The compositor owns the drag, so Aero Snap and edge snapping still work and there's no lag. Ten lines instead of a mouse-delta loop. |
| **The item column is painted, not a `QListWidget`** | XMB scrolls on *every* step because the selection is nailed to the crossbar row. A list view only scrolls when the selection would leave the viewport — the opposite behaviour. |
| **The bar and the column never share horizontal space** | The active item sits *on* the crossbar row, so any overlap makes one of them unclickable — the first thing Batch 4's harness caught. `ITEM_X` clears the furthest-right category icon by construction. **A fourth category means moving `ITEM_X`, not just appending to the list.** |
| **Both stage children are transparent to the mouse** | `Crossbar` and `ItemColumn` are full-size overlapping siblings. `ignore()` on a press propagates to parents, not siblings, so `XmbStage` does the hit-testing and the children only paint. |
| **Arrow keys belong to the crossbar; seek moved to Shift+←→** | Nav is what arrows mean in an XMB. Every focusable child sets `NoFocus` so the window keeps the keys whatever was last clicked. |
| **The wave is a band on the crossbar row, not a full-screen field** | Chosen with the user in Batch 5. Run full height the ribbons pass behind the track list and the transport bar and turn into noise; kept to a masked band they light the row the selection actually lives on. |
| **The wave's hue tracks the speed slider** | Also chosen with the user. Deep blue at daycore, the app's own `ACCENT` at 1.00x, violet at nightcore — so the background reads out the one thing the app is *for*, and moves while the slider is dragged. The hue knots are fitted so that 1.00x really is `ACCENT`; the harness checks that rather than trusting it. |
| **Resting geometry and painted geometry are separate functions** | `_centre_x` / `_item_y` are where things come to rest; `_paint_x` / `_paint_y` are where they are this instant. Hit-testing uses the resting pair on purpose — a click during a slide should mean the row you aimed at, not the one passing under the pointer — and it's also what keeps the harness's "the selection never moves" assertions meaningful once things move. |
| **Animations are `QPropertyAnimation` on a float property, via `ui/motion.py`** | Qt already owns the timer, the easing and the repaint. `Tween.to()` restarts from the value's *current* position, which is what stops a held arrow key from stuttering. `finish()` exists for animations nobody can see — a hidden column, and the offscreen harness, which drives clocks rather than sleeping. |
| **The wave's buffer is coarse across and full-height down** | A ribbon is a long, slowly-varying horizontal band, so its edges run almost horizontally and only the *vertical* sampling decides whether they look crisp; along x a feature spans hundreds of pixels and three in four can go. Quartering both axes — the obvious thing, and what shipped first — looks soft for the same money. Full res 14 ms, both axes quartered 4 ms, **only x quartered 5.6 ms and looks like the 14**. |
| **The wave runs on a coarse timer at ~21 fps, not a precise 30** | Windows' 15.6 ms tick makes a 33 ms coarse timer fire every 46.8. A precise timer does deliver 30 fps but raises the *system-wide* timer resolution — a battery cost the whole machine pays for an app that sits open for hours — and measured about four times the CPU. The quickest ribbon moves ~2 px between frames either way. |

### Open questions

*None currently.*

---

## Architecture

The one rule that keeps this honest: **`core/` never imports Qt.** It's plain
Python, testable without a display, and it's what makes the Widgets choice
reversible.

```
mp3player/
  core/                  # zero Qt imports -- enforceable seam
    models.py            # Track dataclass
    formats.py           # magic-byte sniffing; no numpy, no decoding
    library.py           # scan_folder(path) -> ScanResult(tracks, skipped)
    settings.py          # JSON at %APPDATA%/XMBPlayer/settings.json
    audio/
      decode.py          # load_audio(path) -> (float32[n,2], sr)
      dsp.py             # resample(), Fader, fade_out_at() -- pure numpy
      engine.py          # Mixer (the callback, no device) + AudioEngine (the stream)
      sfx.py             # synthesized UI sounds -> numpy arrays
  ui/                    # all Qt
    theme.py             # colors, fonts, metrics, motion -- single source of truth
    motion.py            # Tween: one easing helper, shared by the three animators
    controller.py        # PlayerController(QObject): binds core <-> ui
    chrome.py            # frameless drag/resize/min/close
    main_window.py       # composes the shell; XmbStage owns the mouse
    widgets/
      crossbar.py        # category row + the rule it sits on
      item_column.py     # the item list -- Music and Settings only
      now_playing.py     # the Now Playing *page*: art, track, speed slider
      transport.py       # bottom bar: seek, transport buttons, volume
      wave.py            # the wave: ribbons in a band on the crossbar row
  app.py                 # entrypoint
spike/                   # throwaway Batch 0 proofs, kept for reference
tools/                   # dev harnesses -- runnable, kept, not shipped
tests/                   # core only, no display needed
```

### How the audio works

**One always-on output stream**, opened at launch, outputting silence when nothing
plays. It mixes the **music voice** (the decoded track, read at a variable rate)
with **N one-shot SFX voices** (UI blips at native rate). One device, no contention.

**Whole file decoded into memory** as `float32[n, 2]`. A 4-minute track is ~62 MB —
fine for one track at a time, and it makes seeking a pointer move and resampling a
fractional index lookup. Streaming decode is a post-v1 option if memory ever matters.

**Resampling** is a fractional read position with linear interpolation:

```python
ratio = speed * (file_sr / stream_sr)   # sample-rate conversion, free
idx   = pos + np.arange(frames) * ratio
i0    = idx.astype(np.int64)
frac  = (idx - i0)[:, None]
out   = samples[i0] * (1 - frac) + samples[i0 + 1] * frac
pos  += frames * ratio
```

Because `pos` is a float advanced continuously, **`speed` can be reassigned at any
moment and the audio follows seamlessly.** That's the whole trick. Verified in
Batch 0: 440 Hz in → 572 Hz at 1.30x, 352 Hz at 0.80x, zero discontinuities.

Known and accepted: speeding up without an anti-alias filter aliases content above
~17 kHz. Every nightcore edit on the internet does exactly this. Not fixing it in v1.

**Every gain change goes through a `Fader`** — play, pause, seek, track change,
volume drag. A gain that jumps puts a vertical edge in the waveform, and that edge
is the click. A seek can't just move `pos`: the callback fades the music out
first, jumps on the block where the gain reaches zero, then fades back in — about
21 ms, inaudible as a delay, silent as a transition.

---

## Conventions

Patterns worth keeping. When something works, it goes here and gets reused — we
don't invent a second way to do a thing we've already solved.

- **`core/` imports no Qt.** Ever. This is the seam; guard it.
- **`float32[n_frames, 2]` is the canonical audio buffer** everywhere. Mono is
  upmixed at decode time so nothing downstream has to think about channel counts.
- **The audio callback must not block, allocate wildly, or touch Qt.** No locks.
  `speed`/`volume` are plain float attributes (assignment is atomic under the GIL);
  seeks are posted as a `pending_seek` attribute the callback consumes.
- **The UI polls the engine at 30 Hz via `QTimer`** — never emit a Qt signal from
  the audio thread.
- **Sniff file types by magic bytes, never trust the extension.** 8% of this
  library's `.mp3` files aren't MP3.
- **Fade ~10 ms on every transition** (play/pause/seek/track change) to stay
  click-free.
- **Speed and pitch are linked by design.** If you're ever tempted to add
  time-stretch, that's a decisions-log change, not an implementation detail.
- **Every number that positions something lives in `theme.py`.** If a metric
  appears in two widgets it belongs there, and `theme.py` imports no other `ui`
  module so anything can pull from it.
- **The window paints the background once; children leave theirs unfilled.**
  That's what keeps one gradient continuous across the chrome, the stage and
  the transport bar. Never set an opaque background on a child.
- **No fixed widths in a row that has to survive 720 px.** Give controls a
  min/max range. Qt can't shrink a `setFixedWidth`, so it overlaps them instead
  and the result looks like a paint bug rather than a layout one.
- **Anything sized in pixels must survive the minimum window.** `WINDOW_MINIMUM`
  is 720x480; check there, not at the default. Shrink or drop — never clip.
- **`setCursor` is inherited by children and outlives the pointer.** A widget
  that sets a cursor conditionally must `unsetCursor()` rather than set an
  arrow, and anything below it should set its own.
- **The offscreen platform has no font database, so `tools/shell_harness.py`
  cannot judge text layout.** `QFontMetrics` there returns fallback widths about
  2.5x too wide (a hint that measures 60px on screen measures 148px offscreen).
  Anything that depends on how wide text actually is — collisions, elision,
  whether two labels touch — has to be checked by rendering a PNG with the real
  platform and *looking at it*. That is where every layout bug so far has been
  found, and none of them were found by an assertion.
- **In Qt stylesheets, subcontrol comes before pseudo-state** —
  `QSlider::handle:horizontal:disabled`, never `QSlider:disabled::handle`. Qt
  discards a malformed rule *and everything after it* without a word.
- **Animate by easing one float property; never hand-roll a frame timer.**
  `ui/motion.py` wraps `QPropertyAnimation`; the property's setter is where
  `update()` goes. Anything that animates also needs `settle()`, so a hidden
  widget stops and the harness can reach the resting state without sleeping.
- **Drive animation clocks in tests, don't sleep.** `settle()` or
  `Tween.setCurrentTime(ms)`. Waiting out real milliseconds makes the result
  depend on when the event loop got a turn.
- **Measure CPU inside the real event loop.** A `processEvents()` poll loop
  costs more than what it's measuring — it reported 44% for a wave that
  actually costs 12.
- **A widget that repaints continuously must be cheap in *path* terms, not
  just pixel terms.** Wide-pen strokes on many-point paths are the trap;
  filling and faking the halo elsewhere is ten times faster.
- **Before downscaling a render buffer, ask which axis the detail is in.**
  Halving both axes is a reflex, and it costs crispness in the direction that
  had it to lose. The wave's edges are horizontal, so vertical resolution is
  the whole of how sharp it looks and horizontal resolution is nearly free to
  give away.

---

## Roadmap

Tracer-bullet order: validate the riskiest thing first, reach a working-but-ugly
end-to-end player early, then layer polish onto something that already functions.

**Working agreement:** one batch at a time. Each batch ends in something runnable.
At the end of a batch, tick these boxes, report what's done and what's left, and
**stop for sign-off before starting the next.** No building ahead.

### Batch 0 — Foundations & spike ✅

- [x] Rewrite `requirements.txt` as UTF-8 (was UTF-16); add numpy, sounddevice, soundfile
- [x] Verify `soundfile` decodes real `.mp3` → numpy (libsndfile 1.2.2, MP3 present)
- [x] Verify `sounddevice` playback through a callback stream
- [x] Verify nightcore/daycore resampling — pitch tracks speed exactly, no clicks
- [x] Lock the decoder choice (`soundfile`; MP3 *encoding* also available, so post-v1 export is free)
- [x] Pick the output backend (WASAPI @ device rate, blocksize 512, 22 ms)
- [x] Create `CLAUDE.md`
- [x] Create the package skeleton

### Batch 1 — Core: library & settings ✅

- [x] `models.py` — `Track` dataclass
- [x] `formats.py` — magic-byte sniffing, split out so `library` and `decode` share it
- [x] `library.py` — `scan_folder()`, top-level `.mp3`, sorted, magic-byte sniffing,
      tolerant of missing / empty / unreadable folders
- [x] `settings.py` — JSON round-trip at `%APPDATA%/XMBPlayer/`, sane defaults,
      atomic write, survives a corrupt or hand-edited file
- [x] Tests for both — 54 passing

Verified against the real library: `~/Music` 31 playable / 6 skipped,
`~/Downloads` 199 playable / 14 skipped — matching the Batch 0 survey exactly.

### Batch 2 — Core: audio engine ✅

- [x] `decode.py` — `load_audio()` → `float32[n,2]` + sample rate, mono upmixed,
      surround folded, every failure a `DecodeError`
- [x] `dsp.py` — `resample()`, `Fader`, `fade_out_at()`
- [x] `engine.py` — always-on stream, music voice, transport, live speed, volume,
      end-of-track (polled, not pushed), device negotiation
- [x] `sfx.py` — synthesized blips + `play_sfx()` into a fixed voice pool on the
      same stream
- [x] Tests for `decode`, `dsp`, `sfx` **and `Mixer`** — 120 new, 174 total
- [x] `tools/engine_harness.py` — keyboard-driven, no Qt

Verified on hardware: WASAPI @ 48 kHz, 22 ms, zero underruns. A 44.1 kHz file
plays at correct pitch and duration through the 48 kHz stream; speed reassigned
mid-playback tracked 1.27x against a requested 1.30x over a half-second window.

### Batch 3 — Ugly working player ✅

- [x] **First:** `run.bat` (console, for debugging) + `XMB Player` desktop shortcut
      via `pythonw.exe` (no console) — both run the live source, no build step.
      The shortcut is generated by `tools/make_shortcut.ps1`; re-run it if the
      repo moves.
- [x] `controller.py` — `PlayerController(QObject)`, signals, 30 Hz position poll
- [x] Plain window: folder picker, `QListWidget`, transport buttons, seek + speed sliders
- [x] Everything wired: play / pause / next / prev / seek / speed
- [x] Folder, volume **and speed** remembered across launches

Also landed: `app.py`, `AudioEngine.clear()`, nightcore/normal/daycore preset
buttons, end-of-track auto-advance off the 30 Hz poll, `Space` / `Ctrl+←→` /
`←→` shortcuts, and a "6 skipped (not MP3)" line so the missing 8% is visible
rather than mysterious.

Verified end to end offscreen (`QT_QPA_PLATFORM=offscreen`, real WASAPI stream):
scan → play → seek → presets → volume → next/prev → pause → auto-advance →
settings round-trip, 21/21, zero underruns. Live speed measured **1.28x
wallclock** against a requested 1.30x. Tests still 174 green — Batch 3 is all
Qt, and Qt isn't tested (CLAUDE.md: `tests/` is core only, no display needed).

### Batch 4 — XMB shell: structure ✅

- [x] `theme.py` — palette, fonts, metrics, the transport stylesheet
- [x] `chrome.py` — frameless window, `startSystemMove`/`startSystemResize`, F11
- [x] `crossbar.py` + `item_column.py` — three categories, keyboard *and* mouse nav
- [x] Transport strip restyled into the bottom bar (seek, transport, volume)
- [x] Swap the ugly window out; identical controller underneath
- [x] `tools/shell_harness.py` — offscreen, drives real key and mouse events

`PlayerController` and `core/` were not touched — the whole front end was
replaced and nothing below the seam noticed, which is the first real test of
the rule that Batch 2 and 3 were written around.

**The rule that makes it feel like an XMB: the selection never moves.** The
active category is pinned at `FOCUS_X` and the active item is pinned to the
crossbar row; choosing something else slides the *content* past those points.
Both are computed as an offset from the active index, so Batch 5 animates two
floats rather than restructuring anything.

Verified offscreen (`tools/shell_harness.py`, real WASAPI stream): 78/78 —
crossbar and item nav, per-category cursor memory, hit-testing, mouse
select-then-open, the speed slider (Up/Down with nothing pressed first,
clamping at both presets, arrows still being category and list nav elsewhere,
drag-to-end), transport,
empty library, fullscreen, resize grips, and a clean paint at 720x480 /
980x640 / 1600x900. Then run for real with a mapped window: launches,
navigates, exits 0, settings flushed.
Tests still 174 green (`tests/` is core-only by convention).

**Reworked after the first real run.** Now Playing's column was
`Play / Next / Previous / Restart / Find in Music` — every one of which the
transport bar already did — while the speed presets sat in Settings, which is
the wrong home for the point of the app. Now Playing is now the song title on the
crossbar row, an info block beneath it, one Daycore→Nightcore slider and the
art out in the gutter; the transport bar dropped its speed control; Settings
dropped its three presets. It stopped being a list at all, so it became its own
widget and `ItemColumn` went back to being a plain list. See the decisions log:
one row in it had to be revised rather than added to.

Then three more from running it for real at 721x479, near the minimum:
the transport row's fixed widths needed 773 px against 629 available, so Qt
drew the readouts on top of the sliders and truncated the title mid-word;
the Now Playing art was a constant 132 px square in whatever room happened to
be left, clipped at the minimum and clearing by -2 px even at the default;
and the resize cursor stuck, because a cursor set on the window is inherited by
children and the window stops getting move events once the pointer enters the
body. Controls in that row are ranges now, the art sizes itself to the room and
is dropped below 64 px, and the body sets its own cursor.

Two bugs the harness caught and one the screenshots did:
the item column overlapped the right-hand category icons, making them
unclickable (fixed in the metrics, not with a hit-test tiebreak); an unstyled
`QSlider::add-page` kept the native light track, so every slider looked pegged
at maximum; and `QSlider:disabled::sub-page` has the subcontrol and pseudo-state
the wrong way round, which makes Qt silently discard that rule *and every rule
after it*.

### Batch 5 — XMB shell: motion & atmosphere ✅

- [x] `wave.py` — sine ribbons, additive glow, anisotropic buffer upscaled, fps cap
- [x] Slide + fade animations on category and item change
- [x] Glow / scale on the selected item
- [x] Perf pass — idle CPU with the wave running

`PlayerController` and `core/` were untouched again — three batches running.

**The hook Batch 4 left worked.** Both offsets were already written as a
distance from the active index, so animating them was one float each: `_display`
eases toward `_index` and the paint reads that. Nothing about the layout moved.
The active *look* stopped being a branch at the same time — a category and an
item are each drawn once, at a size and colour mixed by how close they are to
the focus point, so mid-slide two of them genuinely trade places instead of one
switching off and the other on.

**The wave cost 25 ms a frame before it cost 2.** The first version stroked each
ribbon with a wide soft pen for its halo and sampled the curve 160 times — a
background, using three quarters of a 33 ms budget. Stroking was 18 ms of it (a
wide pen makes Qt compute a join per point) and building the paths in Python was
another 4. Filling instead of stroking, sampling 60 times, and taking the halo
from one downsampled additive copy of the whole buffer brought it to ~2 ms.
Worth remembering: **the cost here is path geometry, not pixels.** Dropping the
render resolution from 1/2 to 1/4 moved 25 ms to 19; deleting one `setPen`
moved it to 6.

**Then the balance flipped, and the first version shipped too soft.** With the
stroke gone, filling the ribbons became the largest item in the frame — so
pixels were suddenly worth attacking, and the buffer that had been quartered on
both axes was blurring the edges for no benefit along x. See the decisions log:
coarse across, full-height down, which is 5.6 ms against full resolution's 14
and looks like it. Found by running it and being told the ribbons looked soft,
not by any measurement — the frame budget was never the complaint.

Measured idle, real event loop, this machine (8 cores), final:

| | CPU, one core | fps |
|---|---|---|
| 980x640, wave running | 2–3% | 21 |
| 980x640, wave hidden | 2.5% | — |
| 1600x900, wave running | 12% | 21 |
| 1600x900, playing | 18% | 21 |

At the default window the wave is free to within the noise; at 1600x900 it costs
about a tenth of one core, and the anisotropic buffer bought its crispness for
nothing measurable. **Measure in the real event loop** — a first pass that
polled `processEvents()` in a sleep loop reported 44%, nearly all of it the
polling.

Two bugs the screenshots caught, both invisible to any assertion:
the ribbons ended with a vertical closing edge at the buffer boundary, and
antialiasing it left a half-covered column that the 3x upscale blew up into a
seam near both window edges (they now start and end a step off-buffer); and
the selection glow read as a *border* twice running — first as stacked filled
rings, whose alpha piles up over the plate and steps at every edge, then as four
stroked rings 5 px apart, whose bright innermost band sitting just off the plate
is a rim by another name. Six small steps with an eased falloff, starting at the
plate, is a glow.

### Batch 6 — Sound & feel

- [ ] Hook `move` / `confirm` / `back` / `error` / `startup` to navigation
- [ ] Tune the synthesized sounds by ear
- [ ] Click-free fades on every transition
- [ ] Easing curve tuning

### Batch 7 — Ship v1

- [ ] Error handling: empty folder, deleted folder, corrupt mp3, no audio device
- [ ] First-run experience when no folder has been chosen yet
- [ ] `README.md` with run instructions
- [ ] PyInstaller build → standalone `.exe` (distribution only; dev still runs live source)
- [ ] Final `CLAUDE.md` status pass
- [ ] Tag v1

---

## Running it

```bash
# deps (already installed in venv/)
venv/Scripts/python.exe -m pip install -r requirements.txt

# the app
run.bat                          # console: tracebacks and prints land here
venv/Scripts/python.exe -m mp3player.app
powershell -ExecutionPolicy Bypass -File tools/make_shortcut.ps1   # desktop .lnk

# tests
venv/Scripts/python.exe -m pytest

# the Batch 4 harness -- drives the real widgets offscreen, no display
venv/Scripts/python.exe tools/shell_harness.py

# the Batch 2 harness -- keyboard-driven audio engine, no Qt
venv/Scripts/python.exe tools/engine_harness.py            # the saved folder
venv/Scripts/python.exe tools/engine_harness.py "D:/Music"
venv/Scripts/python.exe tools/engine_harness.py "song.mp3"

# the Batch 0 spike -- 23s of normal -> nightcore -> daycore
venv/Scripts/python.exe spike/nightcore_spike.py "path/to/song.mp3"
venv/Scripts/python.exe spike/nightcore_spike.py "path/to/song.mp3" --render out.wav
```

## Reference numbers

Measured on this machine (Realtek headphones, Windows 11), Batch 0:

| Host API | Latency @ 48 kHz |
|---|---|
| MME (PortAudio default) | 186 ms |
| DirectSound | 240 ms |
| **WASAPI** | **22 ms** (blocksize ≤ 512) |
| WDM-KS | device unavailable |

WASAPI shared mode rejects any rate but the device mix rate (48000 here).
