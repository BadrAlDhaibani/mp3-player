# XMB MP3 Player

A small desktop MP3 player with a **PlayStation 3 XMB** skin. Point it at a folder,
browse the `.mp3` files in it, play them — and warp the audio into **nightcore**
(sped up, pitched up) or **daycore** (slowed down, pitched down) live with a slider.

This file is the project's memory and **the single source of truth for status**.
If a box below isn't ticked, it isn't done.

> ## ▶ Resume here
>
> **Done:** Batch 0 (spike) · Batch 1 (core library & settings) ·
> Batch 2 (audio engine) · Batch 3 (ugly working player) ·
> Batch 4 (XMB shell structure) ·
> Batch 5 (motion & atmosphere) ·
> Batch 6 (sound & feel — **all but the ear pass**) ·
> Batch 7 (ship v1 — 202 tests, 154 harness checks, `.exe` built and run) ·
> Batch 8 (ID3 tags & album art — 231 tests, 178 harness checks)
>
> **v1 is shipped and Batch 8 landed on top of it.** Everything on the roadmap
> is ticked except one box that can't be ticked from this side of the screen:
> *"tune the synthesized sounds by ear"*. Shipping without it was decided with
> the user — the instrument exists and the numbers are unverified, not wrong.
> Run `tools/sfx_harness.py`, listen — especially `m` (a held arrow key) and
> `p` (blips over music) — and say what to change. It's `_PEAKS` in
> `core/audio/sfx.py` for the mix and `_MIN_GAP_MS` in `ui/sounds.py` for how
> often; neither needs a code change to try.
>
> **Next** is whatever comes off the post-v1 list in the v1 scope section — a
> visualizer, shuffle/repeat, export, subfolders, multiple folders. None of it
> is started. Confirm with the user before beginning any of it.
>
> Before writing any of it, read the note in the conventions about
> `tools/shell_harness.py` running offscreen with no fonts. Every layout bug in
> Batch 4 was found by rendering a PNG and looking at it; none by an assertion —
> in Batch 5 the glow took two goes to stop looking like a border, in Batch 6
> the easing durations were halved on the evidence of a filmstrip after feel had
> called them fine twice, and in Batch 7 the "folder is gone" line passed every
> assertion while running off the right edge mid-word at 720 px.
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
~~ID3 tags & album art~~ (landed in Batch 8) · spectrum visualizer ·
shuffle/repeat/queue · export to file · subfolder recursion ·
multiple library folders.

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
| ~~The ending ramp lives in the final block~~ → **it is a function of read position** | *Corrected in Batch 6.* A 10 ms ramp does not fit in whatever is left of the block where the track happens to end, so `fade_out_at` was silently giving you 480 frames of fade when a track ended near a block boundary and **one** when it ended just after one — a full-amplitude step, and about one track in sixteen. `fade_before_end` computes the gain from how far the read position still is from the end, so the ramp starts in whichever block is 10 ms out and crosses the boundary without knowing it is there. |
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
| **Sound policy lives in `ui/sounds.py`, not the controller** | The controller cannot tell the cases apart: `step(+1)` is a press of Next *and* the end of a track, and only one of those should blip. The window can, because it is the half that was pressed. So the controller announces (`failed`, `playing_changed`) and forwards `play_sfx`, and every decision about *what* makes a noise is made at the input that caused it. |
| **Sound follows intent, not state** | Nothing is wired to `index_changed`: auto-advance moves the cursor too, and a blip nobody asked for reads as an alert rather than as feedback. Keyboard navigation compares the indices around the keypress and blips if they differ, which also buys the right silence at the end of a list for free. |
| **Auto-advance is silent** | Chosen with the user. You didn't press anything. Pressing Next for the same move still blips. |
| **The speed slider ticks, quietly and rate-limited** | Also chosen with the user. `move` at 0.55 gain, no closer than 90 ms apart. It fires while you are already hearing the result, so it only has to say "that registered". Silent when the slider is pinned at either preset — a control that ticks against a clamp is claiming a press did something. |
| **The startup swell stays** | Also chosen with the user. It's the console-boot feel, it happens once a launch, and it is the one sound with room to be the loudest thing you hear. Sounded from `MainWindow.__init__` next to the entrance animation — the app arrives once, in both senses. |
| **UI sounds are throttled per sound, and dropped rather than queued** | A held key repeats about 30 times a second; unthrottled that is 30 overlapping 45 ms blips, which is a buzz and not a series of ticks. A blip that arrives after the keypress that earned it has stopped being feedback — 22 ms of output latency is already the budget — so a queue would spend the rest of it playing catch-up. Asking twice for the same blip inside its window therefore means once, which is what lets Ctrl+→ ask for `move` directly *and* trip the index comparison. |
| **The SFX pool takes a free voice before it steals one** | Round-robin alone cut a voice that was still sounding while seven slots sat idle — and the victim was always the *longest* sound, that being the one still playing when the pointer comes round. Half a second of held arrow key chopped the 1.1 s startup swell in half. Stealing is still what happens when the pool is genuinely full, so the newest keypress is always the one you hear. |
| **Animation durations are set from a filmstrip, not from feel** | Batch 5 set 190/220 ms by feel. A strip of one row step, rendered every 27 ms, was still travelling at 54 ms and pixel-identical from 81 ms to 190. 140/160 ms is the same curve with most of that drift removed — the character is unchanged, only the dead time. Note what this *doesn't* fix: the invisible fraction belongs to the curve, so roughly the last half of any ease-out is imperceptible at any duration. Flattening it is the other lever, and the arrival is where it would pay most; left alone as a preference rather than something the evidence settles. |
| **The curve must be an ease-*out*, whatever else it is** | `Tween.to()` restarts from wherever the value has got to, and an ease-in restarts it at zero velocity. Any `InOut*` curve therefore stutters once per key repeat while an arrow is held — the exact problem restarting-from-current exists to solve. This is a constraint on the choice, not a preference within it. |
| **Why a folder is empty is data; what to say about it is UI** | Three empties want three screens — nothing chosen yet, chosen and now gone, and a perfectly good folder with no music in it — and only the last of them means "no playable MP3s". `scan_folder` reports `NO_FOLDER`/`MISSING`/`UNREADABLE` as bare tokens and `ui/main_window.empty_reason` is the single place they become words, so the empty column and the status line can't drift into two spellings. `MISSING` vs `UNREADABLE` splits on `is_dir()`: there is no such folder, or there is one and we're not allowed in. |
| **The device going away is polled, like everything else** | The stream is always on, so it renders a block every ~10 ms whether or not anything is playing — which makes a block counter that stops moving *the* signal that the device was unplugged. PortAudio doesn't reliably mark such a stream inactive, and it couldn't tell us from the audio thread anyway. `StreamWatch` is the same shape as every other clock in this project: injectable, so no test sleeps through half a second to find out. |
| **Losing the device is a condition; a bad track is an event** | So the status line has two layers. A transient message times out and covers a standing one, then uncovers it. A *new* standing message clears the transient outright — leaving "audio device lost" queued behind a four-second-old "3 files skipped" is the one ordering that reads as the app not having noticed. |
| **The app reconnects rather than needing a restart** | Headphones come out and go back in, or Windows moves the default device — on a desktop that is routine, and going permanently silent until relaunch is not a v1 an app ships with. `AudioEngine.reopen()` re-enumerates PortAudio (it caches its device list at init and never revisits it) and puts the track back at the position it left, on a 2 s retry. The mixer survives untouched unless the new device runs at a different rate, which is when it has to be rebuilt — the SFX bank and every fade are synthesized against that number. |
| **Recovery is silent; loss blips once** | Loss is the app answering back, which is the same reason `failed` makes a noise. Recovery is not: you didn't press anything, and hearing the music return *is* the feedback. The blip fires once, not once per retry. |
| **First run opens on Settings, not on a file dialog** | Chosen with the user. Throwing a native folder picker at someone who has not yet seen the app puts a Windows dialog in front of the thing they launched, and cancelling it drops them exactly where doing nothing would have. Landing on Settings ▸ Music folder stays inside the XMB, costs one press, and lands on the row that every "no music" line already names. Settled rather than slid — this is where the app *started*, not somewhere it navigated to — and silent, because nobody pressed anything. |
| **Settings are read as `utf-8-sig`, written without a BOM** | Notepad and PowerShell's `Out-File -Encoding utf8` both prepend a byte-order mark. Read as plain `utf-8` that BOM reaches `json.loads` as a stray character, the whole file counts as corrupt, and every setting silently reverts — which the user experiences as the app forgetting their music folder for no reason. Found by hand-editing the file while testing the packaged exe, which is the only reason it was ever seen. |
| **The `.exe` is a folder, not one file** | `--onefile` unpacks ~120 MB of Qt to a temp directory on *every* launch: several seconds of nothing before the window exists. This app opens its audio stream and sounds a startup swell in the first frame — an app selling a console boot cannot spend four seconds arriving. Shipped as `dist/XMB Player/` plus a zip. |
| **`mutagen` reads the tags, and we accept its licence** | This library is YouTube rips: ID3v2.2 alongside 2.4, unsynchronisation, UTF-16 BOMs, every APIC variant. Hand-rolling that (the alternative considered, ~200 lines next to `formats.py`'s existing byte sniffing) means owning a long tail whose failure mode is mojibake titles and art missing from the odd file. mutagen is pure Python, no C extensions, ~1.5 MB into a 150 MB exe. **It is GPL-2.0, so the distributed zip inherits copyleft** — chosen with the user, a shrug for a personal novelty app, and written down here rather than discovered later. |
| **The tag names the track; the filename is the fallback** | Non-empty `TIT2` wins, otherwise the stem — which is exactly what the app did before tags existed, so an untagged library looks identical to how it always did. Whitespace-only frames normalise to empty in `core/tags`, or the fallback never fires and the row renders blank, which reads as a bug in the list rather than in the file. No setting and no "does this tag look like junk" heuristic: both were considered and neither survives contact with having to define junk. |
| **Text tags at scan time, cover art one track at a time** | Measured on the real library: **199 tracks cost 111 ms tagged against 34 ms bare — and 31 tracks cost 104 ms.** The scan is dominated by *reading embedded covers*, not by file count, because the folder with fewer files has more art in it. So `read_tags` and `read_art` are separate calls with separate call sites: every file pays for the text, only the playing one pays for the image. `read_art` costs 0.18–11 ms against a decode that was already going to take 70–210 ms, so it disappears into a wait that existed anyway. If this ever needs to get faster, the axis is **bytes of art**, not files. |
| **Art is fetched, never carried** | Covers in this library run to 2.2 MB and a `Track` is held for every file in the folder. `Track` therefore gains `artist` and `album` and stops there; the cover is read on track change and handed to the page. A library-wide art cache is a post-v1 idea for a post-v1 problem. |
| **`core` hands up image *bytes*; `ui` makes pixels** | Same seam as `MISSING`/`UNREADABLE` versus `empty_reason`. `core/tags.read_art` returns whatever sat in the APIC frame and has no opinion about whether it decodes — it has no image library and isn't allowed one. `ui/main_window._cover_image` is the other half, and a frame Qt can't decode becomes `None`, i.e. the note glyph, because that beats a black square. |
| **The artist is the Music row's right-aligned readout** | `Item` already had `label`/`value` for Settings rows, so this cost no widget change — and one consequence was worth taking rather than avoiding: a row with a value gets the full-width selection plate, so the Music list now wears the same plate Settings does. Rendered at 1600 before believing it; it reads as a proper XMB cursor, not the banner the code comment warns about. |
| **A readout gets at most 45% of its row, elided** | Settings values are short words and never came close. An artist tag has no length at all, and `_paint_item` measured the label against an *unelided* value: at 720 px "Boards of Canada featuring Somebody Else Entirely" claimed the whole row, left the title a 40 px stub, and then drew itself right-aligned straight over it. The value is elided first, then the label gets what's left. The label always keeps the majority. |
| **The Now Playing info block is three fixed slots, not a flowing list** | Artist · Album, then the length, then where you are. Most of this library is untagged, so a block that closed up when there was no credit would jump on nearly every track change — and things staying put is most of what makes an XMB feel like one. An empty first line is drawn as nothing and keeps its space. Three lines needed the offsets tightened from 54/78 to 46/68/90: a third at the old spacing lands 1 px off the slider's box, which is not clearance. |

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
    tags.py              # read_tags() -> Tags; read_art() -> bytes | None
    library.py           # scan_folder(path) -> ScanResult(tracks, skipped, error)
    settings.py          # JSON at %APPDATA%/XMBPlayer/settings.json
    audio/
      decode.py          # load_audio(path) -> (float32[n,2], sr)
      dsp.py             # resample(), Fader, fade_before_end() -- pure numpy
      engine.py          # Mixer (the callback, no device) + AudioEngine (the stream)
                         #   + StreamWatch: has the callback stopped being called?
      sfx.py             # synthesized UI sounds -> numpy arrays
  ui/                    # all Qt
    theme.py             # colors, fonts, metrics, motion -- single source of truth
    motion.py            # Tween: one easing helper, shared by the three animators
    sounds.py            # which event makes which noise, how loud, how often
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
tools/                   # dev harnesses + the build -- runnable, kept, not shipped
tests/                   # core only, no display needed
README.md                # for someone who has never seen the project
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
- **A sound belongs to the press, not to the state change it caused.** Wire
  blips at the input, not to a signal — every signal worth listening to also
  fires when the app did something by itself, and that is the difference
  between feedback and an alert.
- **A press that changes nothing makes no sound.** Up at the top of a list, a
  slider at its clamp, a click on the category you are already on. Compare
  before and after rather than trusting the branch you are in.
- **Normalise a sound *after* enveloping it, never before.** Anything
  percussive has its peak in the first samples, which is exactly where the
  attack ramp is still at zero — so normalising first sets a level the
  envelope then takes away, and the mix table quietly stops being the mix.
- **A ramp that has to be N frames long cannot be written against one block.**
  If the thing it lands on can fall anywhere in a block, compute the gain from
  the *position* and let the ramp start in whichever block it needs to. The
  block-local version silently gives you a shorter fade the closer the event
  lands to the start of a block, and the worst case is no fade at all.
- **Judge motion from a filmstrip, not from watching it.** Render the same
  tween every N ms with the clock driven by hand, tile the frames, and look:
  the frames that are identical to their neighbour are the part of the
  duration nobody can see. Twice now the number that felt right was about
  double the number that was doing anything.
- **Make the throttle's clock injectable.** `Sounds.clock` is swappable for
  the same reason the animations have `settle()` — a test that sleeps through
  a rate limit is a test that depends on the scheduler. `StreamWatch.clock` is
  the same idea a layer down.
- **Report *why*, not the sentence.** `core/` hands up a token
  (`MISSING`, `UNREADABLE`); `ui/` owns the words. The moment the same
  condition needs wording in two places — an empty column and a status line —
  a sentence built in `core/` becomes a sentence built twice.
- **Faking a verdict beats faking the world.** The device-loss harness swaps
  out `StreamWatch`, not the stream — so everything downstream is the real code
  path, *and* the reconnect that follows can be a genuine reopen of a genuine
  device rather than another stand-in. When it counts as stalled is tested
  offline, where it belongs.
- **The offscreen harness can't tell you a line is too long, and the item
  font is bigger than the status font.** The same sentence fits in one and runs
  off the edge in the other. Anything that appears in both gets a short form and
  a long form, and both get looked at in a render.
- **Elide a right-aligned value *before* measuring the label against it, and
  cap what it may claim.** Right-aligned text that doesn't fit doesn't clip —
  it runs left, over whatever is already there. A layout that subtracts the
  value's width from the label's budget is only correct while the value is
  short, which is true of every readout you wrote by hand and false of the
  first one that comes out of a file.
- **A field whose text comes from a file has no length.** Tags, filenames,
  folder names. Anything laid out against one needs a bound that holds at
  720 px, and the bound is a share of the row rather than a pixel count.
- **Vertical positions are fixed numbers, so the offscreen harness *can*
  check those.** It cannot judge width, but "this line's box clears that
  control's box" is arithmetic on `theme.py` constants and belongs in an
  assertion. Batch 8's third info line got both: an assertion for the collision
  and a render for whether it reads.
- **This venv is Microsoft Store Python, so `%APPDATA%` is redirected.**
  `settings.json` from `run.bat` lands in
  `AppData/Local/Packages/PythonSoftwareFoundation.Python.3.13_*/LocalCache/Roaming/XMBPlayer/`,
  while the packaged `.exe` writes the real `AppData/Roaming/XMBPlayer/`. They
  are two different files. The exe showing a first-run screen while the source
  build remembers your folder is this, not a bug.

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
- [x] `dsp.py` — `resample()`, `Fader`, `fade_out_at()` *(replaced in Batch 6 by
      `fade_before_end()`; see the decisions log for why)*
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

- [x] Hook `move` / `confirm` / `back` / `error` / `startup` to navigation
- [ ] **Tune the synthesized sounds by ear** — the instrument exists
      (`tools/sfx_harness.py`); the ear does not live on this side of the
      screen. Not tickable from here. **v1 shipped without it, deliberately and
      with the user's say-so** — the levels in `_PEAKS` and the rate limits in
      `_MIN_GAP_MS` are unverified rather than known wrong, and changing either
      needs no code.
- [x] Click-free fades on every transition
- [x] Easing curve tuning

`sfx.py` was *tested* from Batch 2 and *called* from Batch 3 — but only by the
controller, for transport. None of the shell Batches 4 and 5 built made a
sound: not a crossbar step, not a row, not Enter, not a click. That is what
landed here, along with `ui/sounds.py` to decide when.

**The interesting half was the silences.** Every hard case was a place where
two different events reach the same code: `step(+1)` is a press of Next and
also the end of a track; `column.set_index` is a keypress and also
auto-advance moving the cursor to the track that just started. Wiring sound to
those signals gives an app that blips at nothing, which sounds broken while
every sound in it is correct — so the policy moved up to `ui/sounds.py` and the
window fires it at the input. Keyboard navigation compares the crossbar and
column indices around the keypress and blips only if they differ, which is one
place instead of ten branches and makes clamping at either end of a list
silent for free.

**Two clicks found, neither by ear.** Writing "click-free on every transition"
as one continuous render — the whole session in a single array, rather than one
transition per test — turned up the end-of-track fade being as long as whatever
was left of the block the track ended in: 10 ms if it ended near a boundary,
**one sample** if it ended just after one, which is a full-amplitude step and
about one track in sixteen. And the SFX pool's round-robin stole a voice that
was still sounding with seven free, always the longest one, so half a second of
held arrow key cut the startup swell in half. Both are decisions-log rows now.

The sounds themselves got one fix that did not need ears: `_finish` normalised
*before* enveloping, so `move` — whose peak is its first sample — asked for
0.22 and came out at 0.18. Peak is not loudness either; the harness prints the
loudest 30 ms alongside it, which is the column to compare when the question is
whether one sound sits under another.

Easing was re-tuned by rendering filmstrips of a single row step, and they
settled it: still travelling at 54 ms, pixel-identical from 81 ms to 190. The
durations came down to 140/160 ms. The tool that showed it is
`tools/filmstrip.py` now, because a convention that says "look at the motion"
needs something to look with.

Verified: 186 tests green (12 new, all core-only as the convention requires),
`tools/shell_harness.py` 123/123 including 19 new checks that are mostly about
what *doesn't* make a noise, and a real mapped-window run through nav, play,
category switching and the speed slider — exit 0, zero underruns.

### Batch 7 — Ship v1 ✅

- [x] Error handling: empty folder, deleted folder, corrupt mp3, no audio device
- [x] First-run experience when no folder has been chosen yet
- [x] `README.md` with run instructions
- [x] PyInstaller build → standalone `.exe` (distribution only; dev still runs live source)
- [x] Final `CLAUDE.md` status pass
- [x] Tag v1

`PlayerController` grew a device-loss path and `core/` grew two small things;
otherwise the seam held for the fifth batch running.

**The four error cases were not four problems.** Corrupt mp3 was already done
(Batch 3) and no-audio-device-at-launch was already a message box (Batch 3).
What was actually missing was the *middle* of both: a folder that had gone said
"No playable MP3s in Music" about a folder that wasn't there, and a device that
went away *while running* said nothing at all — every control still worked and
none of them did anything, which is the worst version of a failure. Both are
decisions-log rows now. The device one reconnects rather than asking for a
restart, because headphones coming out and going back in is a normal Tuesday.

**Two bugs found by leaving the intended path.** Testing the packaged exe meant
hand-writing a `settings.json`, PowerShell wrote it with a BOM, and the app
quietly reverted every setting — `read_text(encoding="utf-8")` hands the BOM to
`json.loads` and the whole file counts as corrupt. It is `utf-8-sig` now, and
"survives a hand-edited file" means survives the way Notepad and PowerShell
actually write one. Separately, a *passing* harness check crashed the run: the
shell's own strings contain `▸` and a Windows console is cp1252, so printing the
text it had just approved raised `UnicodeEncodeError`. `app.py` reconfigures its
streams for the same reason — under `run.bat` a track name with a `·` in it
would take down the traceback that was trying to tell you something else.

**The status line needed two layers, not one.** A bad track is an event and
times out; a missing device is a condition and must not. A transient covers a
standing message and then uncovers it — but a *new* standing message clears the
transient outright, because "audio device lost" queued behind a four-second-old
"3 files skipped" reads as the app not having noticed.

**And the renders caught what 154 assertions couldn't**, again: `no-such-folder
is gone -- Settings ▸ Music folder` passed every check and ran off the right
edge mid-word at 720 px, because the empty column draws at the item size and the
status line doesn't. Same string, two fonts, one of them too big for it. It is a
short form and a long form now. The Settings row had the same shape of problem
from the other end — `no-such-folder  (missing)` pushed the row's own label into
an ellipsis, and a row whose value elides its label has them the wrong way round.

Verified: 202 tests green (16 new, core-only as the convention requires),
`tools/shell_harness.py` 154/154 including 31 new checks across the three
empties, the device outage and the first run — and the reconnect in there is a
*real* reopen of the real WASAPI stream, resuming mid-track. Rendered the new
screens with the real platform at 720x480 and looked at them. Ran from source
through nav, playback, the speed slider, and out via Settings ▸ Quit with
settings flushed. Built the exe (149 MB unpacked, 60 MB zipped, 59 s), ran it,
and played a track through it — which is the only thing that proves libsndfile
and PortAudio actually came along.

Also landed: `main.py` deleted. It was the Batch 0 `QWidget` stub, tracked and
dead since `app.py` existed.

### Batch 8 — ID3 tags & album art ✅

- [x] `core/tags.py` — `read_tags()` / `read_art()`, never raises
- [x] `Track` gains `artist`/`album`; `scan_folder(..., tags=True)` fills them
- [x] Music rows show the tag title with the artist right-aligned
- [x] Now Playing shows the real cover, and a third info line for artist · album
- [x] `requirements.txt` — `mutagen>=1.47`
- [x] Tests, harness checks, renders, exe rebuild

**The seams Batch 1 left open were the whole job.** `Track.title` was a field
rather than a property specifically so a tag reader could fill it later, and the
art placeholder was already sized and hit-tested with a comment saying the block
was the right shape for a cover. Neither needed moving. `PlayerController`,
`core/audio/` and `ui/sounds.py` were untouched — the sixth batch running where
the seam held.

**The scan is not shaped the way anyone would guess.** 199 tracks cost 111 ms
with tags against 34 ms without; 31 tracks cost 104 ms. Fewer files, more time —
because that folder has more embedded art in it, and reading a tag reads the
covers whether you wanted them or not. That measurement is the reason
`read_tags` and `read_art` are two calls instead of one convenience function,
and it's a decisions-log row so the next person optimises bytes rather than
files.

**One real bug, found the way they always are.** Every check passed and the
Music list at 720 px was drawing "Boards of Canada featuring Somebody Else
Entirely" right-aligned straight through its own song title, which had been
elided to `E…` — because `_paint_item` measured the label against the value's
*unelided* width, and a value long enough to fill the row leaves the label the
40 px floor. Invisible to the harness twice over: offscreen fonts measure 2.5x
too wide, and nothing about it is an assertion anyway. Settings never hit it
because every value there is a word you typed. Two conventions came out of it.

**The third info line's collision, by contrast, *was* checkable.** Vertical
offsets are constants, so "this box clears the slider's box" is arithmetic —
and at the old 24 px spacing a third line lands 1 px off. It got an assertion at
all three sizes *and* a render, which is the split worth remembering: the
harness can do position, only a render can do width.

The credit line is drawn as an empty slot rather than left out when a file names
nobody, which is most of this library — a block that closed up would jump on
nearly every track change. Verified by rendering a tagged track and an untagged
one and checking the length line hadn't moved between them.

Verified: 231 tests green (29 new, core-only as the convention requires),
`tools/shell_harness.py` 178/178 including 24 new checks. Renders at 720x480,
980x640 and 1600x900 of the Music list with a long title *and* a long artist,
Now Playing with a real cover, and Now Playing with nothing tagged. Ran against
the real library — `Don Toliver - Italy.mp3` reads as **"Like It Or Leave"**,
which is the batch justifying itself — 20 of 31 tracks tagged, cover on screen,
exit 0. Rebuilt the exe (150 MB unpacked, 60 MB zipped, 102 s) and launched it:
it scans and lists 31 tracks, which *is* mutagen running 31 times inside the
frozen app. `qjpeg.dll` ships in the bundled `imageformats` plugins, which is
what real covers need and the one packaging risk here — mutagen itself has no
native code to leave behind.

---

## Running it

```bash
# deps (already installed in venv/)
venv/Scripts/python.exe -m pip install -r requirements.txt

# the app
run.bat                          # console: tracebacks and prints land here
venv/Scripts/python.exe -m mp3player.app
powershell -ExecutionPolicy Bypass -File tools/make_shortcut.ps1   # desktop .lnk

# the standalone build -- distribution only, never the edit-run loop
venv/Scripts/python.exe tools/build_exe.py    # -> dist/XMB Player/ + a zip

# tests
venv/Scripts/python.exe -m pytest

# the Batch 4 harness -- drives the real widgets offscreen, no display
venv/Scripts/python.exe tools/shell_harness.py

# the Batch 6 harness -- audition the UI sounds; `m` is the one that matters
venv/Scripts/python.exe tools/sfx_harness.py
venv/Scripts/python.exe tools/sfx_harness.py "song.mp3"

# look at an animation instead of watching it -- real platform, driven clock
venv/Scripts/python.exe tools/filmstrip.py out.png                # a row step
venv/Scripts/python.exe tools/filmstrip.py out.png --what appear --ms 220

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
