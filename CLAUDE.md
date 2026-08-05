# XMB MP3 Player

A small desktop MP3 player with a **PlayStation 3 XMB** skin. Point it at a folder,
browse the `.mp3` files in it, play them — and warp the audio into **nightcore**
(sped up, pitched up) or **daycore** (slowed down, pitched down) live with a slider.

This file is the project's memory and **the single source of truth for status**.
If a box below isn't ticked, it isn't done.

### If you have just arrived

**You probably want [`README.md`](README.md), not this.** That one is for people
who want to run the app; this one is a working notebook, and it is long because
it is cumulative rather than because the project is complicated.

It is written for whoever picks the work up next — including Claude, which is
what the filename means. Four things live here and nowhere else:

- **The decisions log** — every settled choice with the reason it was settled.
  Rows are not re-litigated; a row that needs to change is edited *in place*
  with the new reasoning, which is why a few of them read as strikethroughs.
- **The conventions** — patterns that have already earned their keep. Most were
  written the day a bug proved they were needed, and several name that bug.
- **The roadmap** — one batch at a time, each ending in something runnable, each
  stopping for sign-off. Ticked boxes are done and verified; unticked ones are
  not started, whatever the surrounding prose sounds like.
- **The measurements** — latency, frame costs, scan times, contrast ratios. If a
  number appears here it was measured on real hardware, and the machine it was
  measured on is named.

Licensing is in [`LICENSE`](LICENSE) (GPL-2.0-or-later) and
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md). Nothing in this file is
legal text, and where the two disagree the licence wins.

> ## ▶ Resume here
>
> **Done:** Batch 0 (spike) · Batch 1 (core library & settings) ·
> Batch 2 (audio engine) · Batch 3 (ugly working player) ·
> Batch 4 (XMB shell structure) ·
> Batch 5 (motion & atmosphere) ·
> Batch 6 (sound & feel — **all but the ear pass**) ·
> Batch 7 (ship v1 — 202 tests, 154 harness checks, `.exe` built and run) ·
> Batch 8 (ID3 tags & album art — 231 tests, 178 harness checks) ·
> Batch 9 (the accent tracks the speed — 231 tests, 193 harness checks) ·
> Batch 10 (preset themes — 240 tests, 251 harness checks) ·
> Batch 11 (licence, provenance and version — 244 tests, `.exe` rebuilt at 1.1.0) ·
> Batch 12 (metadata and enforcement — 244 tests, 251 harness checks, ruff and
> mypy clean) ·
> Batch 13 (diagnosability — 253 tests, 267 harness checks, and a log file) ·
> Batch 14 (the four design defects — 256 tests, 286 harness checks, nothing
> moved on screen) ·
> Batch 15 (the download story — 256 tests, 294 harness checks, an icon, a
> smoke test, and a `.exe` rebuilt at 1.1.0 — **all but the release upload**) ·
> Batch 16 (the crackle — 263 tests, 300 harness checks, and audio that stops
> dropping blocks)
>
> **v1 is shipped; Batches 8 through 16 landed on top of it, and `v1.1.0` is
> tagged and pushed.** Every box through Batch 16 is ticked except the release
> *upload* — the zip attached to a GitHub release, which needs a browser — and
> the ones listed under *Open, and waiting on a human* below.
>
> **The roadmap is finished.** Batch 16 was not on it: the user reported audible
> pops and asked for them to be investigated, which is where it came from. What
> is left is one outward-facing action, three human judgements, and the post-v1
> feature list — all set out below.
>
> **The audio was dropping blocks and nothing in the app could see it.** Fixed
> in Batch 16. Two things to carry forward, because both are counter-intuitive:
> **`xruns` has always read zero and always will** — PortAudio's flag is not set
> by WASAPI for this failure, so `AudioEngine.take_stats()` and the "audio: N ms
> lost" log line are the health metric now. And **the audio callback is Python**,
> so it shares the GIL with every paintEvent in `ui/` and it is the one with a
> 10.7 ms deadline. The buffer is 45.7 ms (`SUGGESTED_LATENCY_S`) and
> `main()` sets `sys.setswitchinterval(0.001)`. **Neither number is decorative;
> read the decisions log before changing either.**
>
> **The app now writes a log**, at `%APPDATA%/XMBPlayer/xmbplayer.log`, next to
> `settings.json`. `core/log.py` owns it; `log.get("engine")` is how anything
> gets a logger; `log.due(key, gap_s)` is how anything that can happen at frame
> rate stays out of it. **Nothing prints — that discipline is unchanged.**
>
> **The repo is now pinned by tools, not just by habit.** `pyproject.toml` is the
> single config for `[project]`, pytest, ruff and mypy; `ruff check .` and `mypy`
> are both clean over the whole tree and are expected to stay that way.
> **Every rule that is switched off has its reason written next to it in that
> file — read the comment before re-enabling anything.** `ruff format` is
> deliberately not part of this; see the decisions log. There is a CI workflow at
> `.github/workflows/ci.yml`.
>
> **The remote exists and always did — Batches 12 and 13 are wrong about that.**
> `origin` is `github.com/BadrAlDhaibani/mp3-player`, `main` is pushed, and the
> workflow has been running. What was actually broken was the README's CI badge,
> which named `badraldhaibani/xmb-player` — a repo that does not exist — so the
> badge 404'd on the project's front page. Batch 15 fixed it. Treat the "no
> remote until Batch 15" lines further down as the historical record they are.
>
> **The build now draws an icon and tests what it built.** `tools/make_icon.py`
> draws the crossbar from `theme.py` at seven sizes and assembles the `.ico`;
> `build_exe.py` generates it alongside the version resource, and afterwards
> **launches the exe, waits for it to open an audio device, and closes it** —
> exit 0, settings flushed, or the zip is not written. A window appears for a few
> seconds during a build; that is the test, and it is deliberately *not*
> offscreen. `docs/RELEASING.md` is the full checklist and is the file to follow
> when cutting a release.
>
> **The app now has a licence and a version number.** GPL-2.0-or-later
> (`LICENSE`), the dependency picture in `THIRD_PARTY_NOTICES.md`, three
> third-party texts in `licenses/`, and `__version__ = "1.1.0"` in
> `mp3player/__init__.py` — which names the zip, stamps the exe's Windows version
> resource and is what `QApplication` reports. **Bump it in that one file and
> nowhere else.** The number was picked in-session rather than settled in
> advance; it was raised with the user, who was indifferent to it. **It stands
> — don't re-open it.**
>
> **The four design defects are gone.** `theme`'s accent-text mix is keyed on
> its inputs rather than refreshed by its writers; the Settings rows are one
> table of `(label, value, action)`; the cover is read by the controller and
> handed up as `art_changed`; `refresh_devices` catches `PortAudioError` and lets
> a renamed private call reach the excepthook. **Nothing on screen moved**, which
> was the intended result and was checked with renders rather than assumed. Batch
> 14 is also the first batch since 4 whose writeup has no "and then the renders
> found this" section — see there for why that is a property of the work rather
> than luck.
>
> **Every batch on the list is now done.** They came out of an audit run in one
> sitting (recorded in *The ship-prep audit* below, so nobody re-derives it).
> Note that Batch 11 found one of the audit's own claims to be wrong (see its
> writeup) — **the audit is a record of one sitting, not a verified spec. Check a
> claim against the file before acting on it.** Batch 12 is a milder version of
> the same lesson, and **Batch 13 is the sharpest yet: the audit's central claim
> about the crash path — that PySide6 terminates the process on a slot exception
> — is not true of 6.11, and the truth is worse. Check a claim against the
> *runtime*, not only against the file.** Batch 14, for the record, found the
> audit's four defect descriptions accurate — the only place it departed from the
> brief is the accent cache, where "invalidate on write" would have relocated the
> requirement rather than removed it. **Batch 15 departed once more, and again
> the runtime settled it**: the plan said to smoke-test the exe offscreen, and
> offscreen has no window handle to close, so the exit code it asked for could
> not exist.
>
> ### Open, and waiting on a human
>
> None of these is a bug or a missing feature. The last three are judgements that
> can only be made by someone looking at or listening to the running app, so they
> cannot be closed from inside a session. **Raise them; don't silently sit on
> them, and don't treat them as blocking.**
>
> 0. **Attach the zip to a GitHub release** *(open since Batch 15; step 6 done)*.
>    **`v1.1.0` is tagged and pushed** — annotated, on `31a08af`, the commit the
>    artifact was built from. What is left is step 7 alone: draft a release
>    against the tag at
>    <https://github.com/BadrAlDhaibani/mp3-player/releases/new> and attach
>    `dist/XMB-Player-1.1.0-windows.zip`. **`gh` is not installed on this
>    machine, so this is a browser job and cannot be closed from inside a
>    session.** It is the only thing standing between the repo and a download a
>    stranger can use.
>
> 1. **Tune the synthesized sounds by ear** *(open since Batch 6)*. The only
>    unticked box in a batch that is otherwise finished, and now the only
>    unticked box anywhere except the release above. Shipping without it was
>    decided with the user — the
>    numbers are unverified, not known wrong. Run `tools/sfx_harness.py` and
>    listen, especially `m` (a held arrow key) and `p` (blips over music). The
>    levers are `_PEAKS` in `core/audio/sfx.py` for the mix and `_MIN_GAP_MS` in
>    `ui/sounds.py` for how often. Neither needs a code change to try.
> 2. **Does the accent's travel feel right while dragging?** *(open since Batch
>    9)*. The colour ramp was verified as stills via `tools/render.py` and
>    measured for contrast, but nobody has held ↑ on Now Playing and watched it
>    move. If it feels like it lags or jumps, the lever is `_QSS_STEPS` in
>    `ui/theme.py` (how finely the transport bar's stylesheet follows — 48 now,
>    higher is smoother and costs 2 ms a step). The painted half is already
>    continuous and has no step to tune. **Batch 10 makes this five times more
>    answerable** — there are now five ramps to drag, and any lag is a property
>    of the plumbing rather than of any one palette.
> 3. **Do the five palettes hold up in use?** *(open since Batch 10)*. Each was
>    rendered at three speeds and looked at, which is how Aurora's daycore got
>    moved off Vapor's teal — but stills at three points are not the same as
>    living with one. The levers are all in `PALETTES` in `ui/theme.py`: three
>    hue knots and three saturation knots per preset, no code change to try a
>    different number. **If a knot moves, its `anchor` moves with it** or the
>    harness says so.
>
> ### State of the build
>
> **The `.exe` is current as of Batch 15, stamped `1.1.0`, and carries the
> icon.** It was rebuilt because Batch 15 changed the build again, and it passed
> its own smoke test inside the build: exit 0, settings flushed, four clean lines
> in the log. `dist/XMB Player/` and `dist/XMB-Player-1.1.0-windows.zip` are
> **the release artifact** — verified against the binary rather than the build
> log (version resource read back, all seven icon sizes read back out of
> `RT_ICON`, the licences at the top of the folder and libsndfile's `COPYING`
> still inside the zip).
>
> Rebuilding is still not part of development, which runs live source, and
> **still isn't something to do to catch up**: rebuild when you have changed the
> build, or when you are cutting a release.
>
> **`v1.1.0` now exists and points at `31a08af`**, which is the commit this
> artifact was built from — checked rather than assumed: nothing under
> `mp3player/` is newer than the build, and the only files edited after it
> (`tools/shell_harness.py`, `docs/RELEASING.md`) do not enter the exe. The old
> `v1` tag is left where it is as the historical marker it always was; it
> describes Batch 7's code and nothing since.
>
> ### Known flake — don't debug it
>
> `tools/shell_harness.py` fails `...resuming where it left off` maybe one run in
> five, at `0.00s` instead of `~0.05s`. It is a real WASAPI reopen racing a
> position read, it predates Batch 9, and it passes on a re-run. **299/300 with
> that one line failing is the known state. Anything else failing is yours.**
>
> ### Next
>
> **The roadmap is empty. Nothing is queued, and nothing should be started
> without asking.**
>
> The one piece of Batch 15 left is **step 7 and only step 7**: attach
> `dist/XMB-Player-1.1.0-windows.zip` to a GitHub release drafted against
> `v1.1.0`. The tag was cut and pushed on **2026-08-05**, when the user asked for
> the release — steps 1 through 6 of `docs/RELEASING.md` were re-run first, not
> taken on trust: ruff and mypy clean, 256 tests, and the harness **294/294 with
> the flake passing**. The upload is a browser job because `gh` is not installed
> here. **Don't push a tag or publish a release without being asked to** — that
> was true before this and is still true for whatever the next version is.
>
> After that the queue goes back to the post-v1 list in the v1 scope section —
> shuffle/repeat, export, subfolders, multiple folders. **None of that is
> started.** A spectrum visualizer was offered and **declined** in Batch 9 (the
> accent ramp was wanted instead), so don't re-offer it as though it were
> untouched.
>
> ### Before writing any of it
>
> Read the note in the conventions about `tools/shell_harness.py` running
> offscreen with no font database. **The split that keeps being true: assertions
> catch *position*, renders catch *width, colour and motion*.** The harness
> genuinely found Batch 4's column overlapping the category icons and Batch 8's
> third info line colliding with the slider — both arithmetic on `theme.py`
> constants. It was blind to every one of these: Batch 5's glow reading as a
> border (twice), Batch 6's easing being double what anyone could see, Batch 7's
> "folder is gone" line running off the right edge mid-word at 720 px, Batch 8's
> long artist drawing straight through its own title, and Batch 9's daycore
> readout coming out fainter than the unselected rows around it — that last one
> with all 178 checks green, Batch 10's Aurora and Vapor opening on the same
> teal — two presets wearing one colour, with all 227 checks green — and Batch
> 15's icon glow coming out as concentric rings (Batch 5's bug, a third time)
> with a neighbour dot drawn hanging half off the tile.
>
> So: if the question is "does this box clear that box", write the assertion. If
> it is "does this read", **`tools/render.py` is how you look** — give it a flag
> rather than writing another one.
>
> Then read the decisions log and the conventions below before writing anything.
> They are the accumulated agreements, not suggestions.

---

## v1 scope

**In:** pick a folder · browse its tracks · play/pause/next/prev/seek · a live
speed slider running Daycore → Nightcore · XMB look · synthesized UI sounds.

(There are no longer separate Nightcore/Normal/Daycore *preset buttons* — the
two presets became the ends of the slider itself. See the decisions log.)

**Deliberately out of v1** — good ideas, parked until v1 actually ships:
~~ID3 tags & album art~~ (landed in Batch 8) ·
~~spectrum visualizer~~ (offered and declined in Batch 9) ·
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
| **The accent tracks the speed, exactly like the wave** | Chosen with the user in Batch 9. The ribbons had hue-shifted since Batch 5 and nothing else did, so at nightcore the background was magenta and the selection plate, both slider fills and every readout were still icy blue — the atmosphere read out the effect and the interface on top of it contradicted the atmosphere. Scope was settled as **accent only**: the navy gradient and the white/grey text hold still, so the frame stays put and the shift reads as deliberate rather than as the app changing skin. |
| **`ACCENT` stops being painted with and becomes the anchor** | The constant stays exactly as it was and nothing reads it any more; `accent()` is what widgets call. Keeping a fixed 1.00x reference is what makes the invariant *checkable* — the wave's hue knots were fitted so the ramp passes through `ACCENT` at 1.00x, and a constant that moved would turn the harness check guarding that into a tautology. Also why the calls are functions rather than a mutated `theme.ACCENT`: `theme.accent()` says out loud that the value is live, where a constant-looking name would quietly become a lie. |
| **Fills take the ramp straight; text is lightened to a contrast floor** | **HSV value is not lightness.** Every colour off the ramp has `V=1.0`, but a saturated blue at `V=1.0` is far darker to the eye than a cyan at `V=1.0` — so the daycore accent measured **4.9:1 against the background, below `TEXT_FAINT`'s 5.5:1**. Rendered, that inverted the row: the *selected* track's artist was fainter than the unselected ones around it, which is the opposite of what focus means. Fills were fine at every speed. So `accent_text()` mixes toward white — and only as far as it has to, targeting 7:1: daycore 4.9→7.1, nightcore 6.2→7.0, and **1.00x needs zero mix and is byte-identical to before**, which is the invariant the whole ramp hangs on. A flat mix would have lifted 1.00x too. |
| **Only the transport bar has to be *told* the accent moved** | Everything else paints itself and picks the new colour up on its next repaint, because no widget captures a colour at construction. The bottom bar is stock Qt widgets coloured by stylesheet, so `TransportBar.refresh_accent()` re-applies it — gated on a 48-bucket quantisation of the fraction, because a drag emits on every mouse-move and re-applying a stylesheet re-polishes the whole widget tree. **Measured: 2.0 ms per drag step, about 30% of the drag path's total cost** — the gate stays. A bucket is ~2° of hue, invisible in a 4 px fill. |
| **A theme is a swap of the ramp's knots, and nothing else** | Chosen with the user in Batch 10. The whole ask was "change the spectrum the slider moves through", and Batch 9 had already routed every accent in the app through one function of one fraction — so a preset is two knot tuples and a name. The navy gradient, the three text greys, every metric and every animation hold still, which is the same scope discipline Batch 9 kept and for the same reason: the frame staying put is what makes the colour read as deliberate rather than as the app changing skin. It also keeps the contrast floor meaningful, since every number in it is measured against `BG_MID`. |
| **Each palette carries a hand-written `anchor`** | The harness has checked "1.00x *is* `ACCENT`" since Batch 9, and that check was only ever worth anything because `ACCENT` held still while the knots were fitted to it. Once there are five sets of knots, comparing each against its own `wave_color(0.4)` proves nothing — it is the same arithmetic on both sides. So `Palette.anchor` is a literal someone typed after looking at the number, the harness compares the two, and `PALETTES[0].anchor is ACCENT` keeps the original invariant exactly as it was. |
| **Knots may run outside 0..1** | `wave_color` takes the hue modulo 1 *after* interpolating, so Ember ends at `-0.08` (hot pink) and Vapor at `1.02` (coral). Clamping them into range instead would make `_along` lerp the long way round — Ember's amber→pink would pass through green, cyan and blue on the way. This is a property of the existing `% 1.0`, not something added for it. |
| **The theme name is a bare string in `core`; `ui` owns the list** | Same seam as `library.MISSING` versus `empty_reason`: `core` imports no Qt and has no business knowing what a palette is, so `_as_name` validates the *shape* (a non-empty string) and stops. `PlayerController` clamps it against `theme.palette_names()` on the way in and on every set, which is what stops a bad name reaching the paint path. Deliberately *not* clamped in `core`: a file written by a later build with more presets would come back as the default and then get saved that way, turning "this build doesn't know that name" into "your setting is gone". |
| **A palette swap always re-applies the transport stylesheet** | The 48-bucket gate asks whether the *fraction* moved, and swapping a palette doesn't move it — the slider is exactly where it was and only the ramp beneath it changed. So the swap sails straight through the comparison and the one part of the app coloured by stylesheet keeps the old colour. `set_palette` returns `True` unconditionally, which is honest rather than lazy: a theme change is a keypress, not a pixel of a drag, so there is nothing to protect. |
| ~~Enter cycles the Theme row~~ → **it is stepped into: Enter, then ←→, then Enter/Esc** | *Revised twice within Batch 10, both at the user's ask, both after the previous version had been built and run.* Cycling made every palette one press from the row — but picking a theme is a **comparison**, and blind cycling means the one you liked two presses ago costs three more to get back to. So: a mode. This is the Batch 4 slider-row decision coming back word for word, and it is worth noting that the *only* objection to it in Batch 9 was that `ItemColumn` had no per-row mode. It still doesn't — `set_stepping` is one bool and an outline, and every decision about what the mode means stayed in the window. The machinery Now Playing was built to avoid was a value editor inside the column, not a rectangle. |
| **Stepping in is what buys Left/Right back** | The adjusters are ←→, not ↑↓ — which reads as a straight contradiction of "Left/Right stay category nav everywhere" and is in fact the exception that rule was written to have. A stepped-into row is the one place the crossbar gives them up, that is exactly what real XMB does with a slider item, and it is what the outline is announcing. It also makes the readout's own `‹ ›` chevrons say which keys, rather than being decoration. `↑↓` were tried first and moved here in the same batch: they are the keys that mean "next row", and spending them on a value left the row's own axis doing nothing. |
| **The mode has three explicit exits and three that are just leaving** | A mode you can enter and not leave is worse than no mode. Enter, Esc and Backspace step out by name. Everything else that gets you out does it by *moving the cursor off the row* — ↑↓, Home, End, the wheel, a click on another row — and that is **one** connection to `index_changed`, not five branches. `index_changed` is the signal this project had deliberately never wired anything to, because it also fires when the app moves the cursor itself; that is precisely why it works here, since whoever moved the cursor, the user is no longer on that row. Ctrl and Shift arrows stay transport throughout: you may well be listening while you pick, and the mode is about one row's value, not about the whole keyboard. |
| **The Settings rows have names now** | `ItemColumn` activates by index and has no notion of an id, so a list and an if-chain of bare integers were held together by counting. Batch 10 inserted a row in the *middle* of that list, which without names is a silent misfire rather than a rename — `Full screen` would have quit. `SET_FOLDER … SET_QUIT` in `main_window.py`, plus a harness check that the label at each index is the one its branch expects. |
| **The Now Playing info block is three fixed slots, not a flowing list** | Artist · Album, then the length, then where you are. Most of this library is untagged, so a block that closed up when there was no credit would jump on nearly every track change — and things staying put is most of what makes an XMB feel like one. An empty first line is drawn as nothing and keeps its space. Three lines needed the offsets tightened from 54/78 to 46/68/90: a third at the old spacing lands 1 px off the slider's box, which is not clearance. |
| **The project is GPL-2.0-or-later** | Chosen with the user before Batch 11. mutagen is GPL-2.0 and `core/tags.py` links it directly, so the distributed zip has been a combined work since Batch 8 — writing that down costs nothing and is the honest option. The alternatives (MIT source with a GPL binary; dropping mutagen for a hand-rolled ID3 reader) are argued out in the Batch 11 section. |
| **`__version__` lives in `mp3player/__init__.py`, and starts at `1.1.0`** | `v1` was a git tag and nothing else, so two builds were indistinguishable by filename, by file properties and from inside the app. `1.1.0` because Batches 8–10 are features and nothing was removed. The number was proposed in-session rather than settled in advance, put to the user, and left to stand — so it is settled, not merely unchallenged. One owner, three consumers: the zip name, the exe's Windows version resource, and `QApplication.setApplicationVersion`. |
| **Licence texts are checked in, never fetched at build time** | A release must not depend on gnu.org being reachable, and a licence file that is downloaded is a licence file that can silently change under you between two builds of the same version. `licenses/` holds only what does not already ship inside a dependency's own package — Qt's LGPLv3+GPLv3 and PortAudio's MIT — because duplicating libsndfile's `COPYING`, which PyInstaller already collects, creates two copies that can disagree. `licenses/README.md` exists to say which are deliberately absent. |
| **The project declares Windows and stops hedging** | Chosen with the user before Batch 12. The README used to say "nothing is Windows-specific by design", which had never been run anywhere to find out. Every number in this file is a Windows one — WASAPI at 22 ms, `%APPDATA%`, `run.bat`, `make_shortcut.ps1` — so the classifiers say `Microsoft :: Windows`, the README says it might work elsewhere and nobody has checked, and CI runs on `windows-latest` only. Untested portability is a claim, not a feature. |
| **CI runs ruff, mypy and pytest — and never `tools/shell_harness.py`** | Chosen with the user. The reason is physical rather than philosophical: the harness opens a real WASAPI stream and a GitHub runner has no audio device. Making it device-optional means auditing 1,300 lines for device assumptions and living with a permanently split pass count — a batch of its own, if it is ever wanted. So it stays the local pre-release step it already was, and **the README says out loud that the badge covers `core/` only**, because a green badge otherwise reads as "the UI is tested" and the UI is the half with no tests. |
| **The linter is pinned; the formatter is declined** | `ruff format`'s entire quarrel with this repo is line-joining — 290 changed lines across 17 files, every one a hand-wrapped signature or comment block it would rejoin because it fits inside the limit. The linter catches defects and the formatter would only relitigate layout, and a batch whose job is to pin the discipline that already exists should not spend its diff rewriting it into a different one. Run it locally if you like; CI does not, and `pyproject.toml` says why next to the setting. |
| **`line-length` is 96 because that is where the code already lives** | Written to about 88 throughout, with a handful running a few characters past. 96 made four lines violations; 88 would have meant rewrapping forty-six, and adopting the formatter at either width means several hundred lines of churn. It is a ceiling the linter enforces, not a width to write to. |
| **Qt event handlers keep their unannotated `event`** | `ANN001` off, globally, decided once rather than half-done — the parameter's type is fixed by the base class, PySide6's own stubs already state it, and annotating twenty-two overrides adds an import per widget to restate what Qt knows. The cost is real and worth knowing: with it off, ruff had nothing to say about `StreamWatch.__init__(..., clock=time.monotonic)` or `AudioEngine._callback`, **and mypy caught both**, because they are in `core/` where nothing is exempt. The two tools overlap exactly where the exemptions are. |
| **mypy is strict everywhere; `ui/` gives up `attr-defined` and `name-defined`** | PySide6 supports the flattened enum names it documents — `Qt.AlignLeft`, `QPainter.Antialiasing`, `Qt.Key_F11` — while its generated stubs declare only the scoped ones. That was **140 of the first run's 183 errors**, across 58 distinct symbols, every one of them code that runs. The alternative is rewriting every paint call site to `Qt.AlignmentFlag.AlignLeft` and rewrapping most of the lines that touches. Everything else stays on in `ui/`, and that is where the value was: `arg-type`, `union-attr` and `return-value` between them found the wave's buffers typed `QImage | None` in front of six unguarded paint calls. |
| **Dependency ranges get ceilings, and the four Qt pins stay `==`** | The DSP is `float32[n, 2]` by contract at every layer and the resampler indexes it with `int64`; a major version of numpy is entitled to change what either means, and the failure would be *audible* rather than loud. soundfile and sounddevice wrap the two C libraries that decode MP3 and open WASAPI, and the build pulls both in by name. The Qt four are exact because a shiboken6 that does not match its PySide6 is an ABI error at import. `requirements.txt` stays the file humans install from; `pyproject.toml` carries the same set as metadata. |
| **The log is a sibling of `settings.json`** | `config_dir()` is already created, already owned by the app, already documented as redirected under Microsoft Store Python — and already the path someone gets told when they are asked to send a file in. A second location is a second thing to explain. One rotating handler, 256 KB × 3: a log that can grow without bound eventually costs more than it tells you. |
| ~~An unhandled exception in a slot terminates the process~~ → **PySide6 6.11 reports it and carries on** | *Corrected in Batch 13, by running it.* The audit's reasoning was that `aboutToQuit` never fires and settings are lost, which would make the `try/finally` around `app.exec()` the fix. Measured: a slot exception and a `paintEvent` exception both go to `sys.excepthook` and the app keeps running — and that is the **worse** failure, because nothing stops, nothing is written, and under `pythonw.exe` the traceback goes to a stream that does not exist. So the excepthook is the batch, not the `finally`. The `finally` stays: it caught a real one the first time it ran, from a top-level exception outside any slot. |
| **The crash dialog is one-shot, and posted rather than shown** | A broken `paintEvent` raises on *every frame*, so "tell the user" has to mean once per launch or the dialog is the crash. And it is handed to `QTimer.singleShot(0, ...)` instead of opened inside the hook: putting a modal dialog up part-way through somebody else's paint is how a crash report becomes a second crash. |
| **The file is throttled; the console is not** | `log.due(key, gap_s)` gates anything that can repeat at frame rate — the same exception, a stream of xruns, a reconnect retry every 2 s all evening. Without it the rotation quietly deletes the interesting part of the file to make room for a hundred copies of one traceback. The hook still chains to the previous excepthook every time, because under `run.bat` the console is the fastest way to read one and nothing there rotates. |
| **A failed settings write is edge-triggered on screen and written down every time** | `save()` has always returned a bool and nothing has ever looked at it — a failed write is experienced as the app forgetting your music folder for no reason, which is the exact symptom the `utf-8-sig` row was written about. It reaches the status line, so it is visible; but only on the *edge*, because `failed` also blips and the next write during a volume drag will fail for the same reason 800 ms later. A notice that re-announces itself is an alarm. |
| **A derived cache is keyed on its inputs, not refreshed by whoever moved one** | `_accent_text_mix` was a bare global that `set_palette` and `set_accent_fraction` each had to remember to recompute. Both did, and the comment in the first of them named the risk in its own words — which is documenting a hole rather than closing it. `_text_mix()` now caches against `(palette name, fraction)` and recomputes when the key changes, so a third writer of either input, or a third input entirely, is noticed for free. **Cost measured so nobody re-derives it as the reason: 0.051 → 0.033 ms per drag step, against a step that costs 4.70 ms.** That is 0.4%, so it is not a perf change; correctness is the whole of it. |
| **A best-effort `except` names the failure it is being lenient about** | `refresh_devices` caught `Exception` around two *private* sounddevice calls. The lenient case is real — PortAudio refusing to come down or go back up is what an unplugged device does, on a 2 s timer, for as long as the headphones are out — and it is exactly `sd.PortAudioError`, because both calls route their return codes through `sd._check`. What the same clause also caught was a rename of `_terminate` or `_initialize`: an `AttributeError` that stopped reconnection working *forever* while the retry timer went on firing and the "audio device lost" line stayed up, indistinguishable from the device still being unplugged. Loose, it reaches `sys.excepthook` — one log entry, one dialog, and the retries continue exactly as they would have. Batch 13 is what made that a sane outcome rather than a crash. |
| **The cover is read by the controller and handed up as a signal** | `main_window` called `core.tags.read_art` directly: file I/O and a full ID3 parse performed by a widget, in the project whose one architectural rule is that widgets don't do that. A signal (`art_changed`, carrying `bytes \| None`) rather than a property the window asks for, because *when* a track changes is the controller's to know and a property leaves the widget deciding when to hit the disk. **The `core` hands up bytes / `ui` makes pixels seam did not move** — `_cover_image` still turns them into a `QImage` or into `None`, and `core.tags` still has no image library. Only the read moved, and it moved to the one place that was already paying 70–210 ms for a decode. |
| **The Settings rows are one table of `(label, value, action)`** | `_settings_items` and `_activate_settings` were two lists held in the same order by counting. Batch 10 already hit it — inserting `Theme` in the middle shifted `Full screen` and `Quit`, so activating one would have run the other — and the `SET_FOLDER … SET_QUIT` constants named the indices without removing the requirement that two lists agree. `_settings_rows()` removes it: the label and what activating it does are the same tuple. The constants stay, demoted to what outside callers (the harness) use to talk about a row without counting. |
| **The icon is drawn at build time from `theme.py`, never checked in** | Same reasoning as the version resource one row down, and the same reasoning as there being no `.wav` files for the UI sounds: a checked-in binary is a second copy of something the source already defines, and this one would drift from the palette silently — a theme change would leave the icon wearing the old accent with nothing to notice it. `tools/make_icon.py` draws the crossbar off `CROSSBAR_Y_RATIO`, the background gradient and `ACCENT`, and `build_exe.py` generates it into the same scratch directory as the version resource. It is the one place the build imports Qt; a third of a second against a 71 s build, and a subprocess to avoid it would buy only a second way to fail. |
| **Seven sizes, each drawn at its own size, PNG payloads throughout** | Windows picks per slot — 16 in the tray, 32 on the desktop, 48 in Explorer, 256 for the preview — and a missing size is scaled from the nearest, badly. **Never downscaled**, because the detail is three hairlines and a hairline is what downscaling destroys first: 16 px rendered natively is one crisp pixel where 256 halved four times is four shades of grey. That is the conventions' "ask which axis the detail is in" rule reaching its limit — here the answer is "both, and it is one pixel wide". The container is assembled by hand because Qt's ICO writer takes one image per file, and the payloads are PNGs because an ICO entry may be either and Windows has taken PNG since Vista. Known and accepted: `System.Drawing.Icon` mishandles the 256 entry. That is a GDI+ limitation, the shell reads it correctly, and this project declares Windows 11. |
| **The smoke test runs on the real platform, not offscreen** | *The plan for Batch 15 said offscreen; the runtime said otherwise.* Offscreen gives the app no window handle, so `WM_CLOSE` has nothing to arrive at — measured, a graceful `taskkill /T` is ignored outright and only `/F` ends it, which discards the exit code and the shutdown path in one go. On the real platform the same close lands in 0.3 s with **exit 0 and `settings.json` written**, i.e. `aboutToQuit` fired and `shutdown()` ran. A window appearing for a few seconds during a build is what that costs. `%APPDATA%` is redirected at a temp directory, because a build step that rewrites your saved music folder is worse than the bug it is looking for. |
| **A build that fails the smoke test is not zipped** | The zip is written *after* the check, so a broken build leaves an error message and no archive. An archive sitting next to a failure is an archive that eventually gets uploaded — and the failure this catches is specifically the silent one, where `--collect-binaries` stops finding libsndfile or PortAudio, PyInstaller reports success, and the exe dies on first import. `--skip-smoke` exists for a machine with no audio output, where the app correctly puts up a modal box and never opens a stream; the flag's own help text says it is not for saving ten seconds. |
| **A Qt object built from a Python temporary is a segfault, not an error** | `QBuffer(QByteArray())` takes a reference to something that is collected immediately, and the process dies inside a later `image.save()` — no exception, no traceback, and not on the line that looks wrong. The fix is to name the `QByteArray` in a local so it outlives the buffer. Written down because the shape is general: any PySide6 constructor taking a reference to another Qt object needs that object held on the Python side for as long as the wrapper lives, and the failure mode is the least debuggable one available. |
| **The licence files ship twice: bundled *and* beside the exe** | `--add-data` puts them in `_internal/`, which under PyInstaller 6 is a folder with four hundred DLLs in it — the letter of "the licence travels with the binary" and none of the point. `copy_licences` also drops them at the top of `dist/XMB Player/`, where someone unzipping a release will actually see them. 36 KB against 150 MB is not a trade worth thinking about. |

| **The output buffer is 45.7 ms, not PortAudio's 22** | **The audio callback is Python.** It must take the GIL every 10.7 ms, render a block and return, and `latency='high'` — sounddevice's default, which reads back as a comfortable-sounding 22 ms — left it entering with **2.0 ms** of headroom at the 1st percentile. Any other thread holding the GIL past that means the block is not rendered late, it is *never made*. Measured on a bare stream doing nothing but zero-filling, with one busy Python thread beside it: **83.9 callbacks a second against a nominal 93.75, i.e. 10% of the audio simply absent**, and PortAudio raised no flag for a single one of them. `SUGGESTED_LATENCY_S = 0.035` reads back as 45.7 ms (PortAudio adds the block) and takes the 1st-percentile headroom to ~17 ms. The ceiling was agreed with the user at ~45 ms, against the decisions-log figure of ~50 ms for where a blip stops feeling connected to the keypress. |
| **`sys.setswitchinterval(0.001)`, in `main()`** | The other half of the same problem, and free. The default is 5 ms — that is how long a thread may keep the GIL *after another one has asked for it*, and the audio thread's entire budget is 10.7 ms. Same bare-stream measurement: 5 ms default gives 83.9 callbacks/s, 1 ms gives 94.0, which is every block. Either lever alone fixes the loss; both together is what takes the *worst* gap down as well as the average. Not a latency trade and not visible anywhere — the cost is more context switches on a thread that spends its life inside Qt, and it did not show up in the frame cost. |
| ~~Late audio blocks are what `xruns` counts~~ → **`xruns` counts what PortAudio noticed, which here is nothing** | Every session this app has ever logged ends `0 late audio block(s)`, including the ones that popped continuously. PortAudio's `status` flag is set by its host layer and WASAPI's does not set it for this failure. The counter stays — a flag that does fire is worth having, and it now records *which* flag — but it is not the health metric. |
| **Audio health is measured as seconds of audio never rendered, against a wall clock** | The one measure that survived a real machine. A starved callback is not called late, it is **not called**, so `blocks × blocksize / rate` against elapsed time is exactly the audio that was lost — and it is what the user heard. Measured over the *reporting* interval rather than per poll: a 33 ms poll spans about three blocks, so rounding to whole blocks is ±10.7 ms of noise, and clamping that at zero every time manufactures a shortfall out of quantisation. Over ten seconds the same rounding is a tenth of a percent. `min_slack_ms` (PortAudio's own `outputBufferDacTime - currentTime`) rides alongside as the leading indicator: it shrinks *before* anything is lost, and it is the number the buffer size buys. |
| **A gap between callbacks is not a fault, and counting them measured nothing** | The first instrument written, and it was worthless: at blocksize 512 against WASAPI's 480-frame host period, PortAudio must buffer a remainder, so one callback in sixteen is preceded by a double-length gap **by construction** — 6 a second, on a completely idle machine, forever. It reported 297 late callbacks in 45 s with the wave running and 267 with the wave stopped, which reads as "the wave is irrelevant" and is really "this metric is noise". The slack/shortfall pair reported 100 ms lost per 10 s and then zero, on the same runs. |
| **The window gradient and the wave's band are cached, because both are functions of size** | `ChromeWindow.paintEvent` was evaluating a three-stop vertical ramp over the whole dirty rect, and `wave._render` a five-stop one over the whole buffer, ~21 times a second, to arrive at the same pixels every time. The wave dirties the entire stage (all four children are full-size and transparent), and fullscreen is 3.3x the area of the default window — which is most of why the app was worse there. Both are now built once per size and blitted. **Verified as byte-identical rather than as looking fine**: 0 differing pixels at 720x480, 980x640 and 1920x1080, for both, and that comparison is a harness check rather than a note. `theme.background_brush` and `wave._band` remain the single source of each. |

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
                         #   folder, volume, speed, theme (a bare name)
    log.py               # the rotating log next to it; get(), due(),
                         #   record_exception() -- never raises, never prints
    audio/
      decode.py          # load_audio(path) -> (float32[n,2], sr)
      dsp.py             # resample(), Fader, fade_before_end() -- pure numpy
      engine.py          # Mixer (the callback, no device) + AudioEngine (the stream)
                         #   + StreamWatch: has the callback stopped being called?
                         #   + CallbackStats: is it making its deadline? (xruns can't say)
      sfx.py             # synthesized UI sounds -> numpy arrays
  ui/                    # all Qt
    theme.py             # colors, fonts, metrics, motion -- single source of truth
                         #   + PALETTES: the five speed-driven colour ramps
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
  make_icon.py           # the .ico, drawn from theme.py; imported by build_exe
tests/                   # core only, no display needed
docs/RELEASING.md        # the release checklist -- the steps CI cannot run
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
- **HSV value is not lightness, and a pen has a floor a fill doesn't.**
  A saturated blue at `V=1.0` is far darker to the eye than a cyan at the same
  value, so any colour picked by rotating a hue will be readable at some angles
  and not others. Fills don't care; text does. Anything drawn with a pen off a
  hue ramp needs a contrast floor against the background, and the floor should
  be applied *only as far as needed* — a flat correction changes the colours
  that were already fine, which is how an invariant elsewhere gets broken.
- **Contrast is arithmetic, so it belongs in an assertion — whether it
  *reads* still needs a render.** Same split as the vertical offsets below.
  The harness can prove the daycore readout is no fainter than `TEXT_FAINT`;
  only a PNG showed that it had been, and only a PNG says whether the result
  looks like the app or like a different app. **`tools/render.py` is the thing
  to render with** — don't write another one, and if it can't show what you need,
  give it a flag.
- **A gate keyed on one input is a hole the moment a second input can change
  the same output.** `set_accent_fraction`'s 48-bucket check is a correct
  answer to "did the accent move enough to matter?" only while the *fraction*
  is the only thing the accent depends on. Batch 10 added a second thing, and
  the gate went on answering the old question — silently, because a stale
  stylesheet is a colour and not an error. The fix is not a smarter gate: it is
  that the new input re-applies unconditionally, because it fires on a keypress
  rather than per pixel of a drag.
- **A harness that reads the user's saved settings must pin anything it
  asserts a constant about.** `shell_harness.py` builds a real controller from
  the real `settings.json`, so once the theme was persisted, every
  `ACCENT` comparison in it passed or failed depending on which palette the
  machine happened to be left on. It sets the default up front and puts the
  saved one back before shutdown flushes, next to the speed and the volume.
- **Vertical positions are fixed numbers, so the offscreen harness *can*
  check those.** It cannot judge width, but "this line's box clears that
  control's box" is arithmetic on `theme.py` constants and belongs in an
  assertion. Batch 8's third info line got both: an assertion for the collision
  and a render for whether it reads.
- **A rule you switch off gets its reason written where the switch is.**
  Every `ignore` in `pyproject.toml` carries the argument for it in a comment
  above it, because a bare rule code in a config file is indistinguishable from
  someone silencing a finding they did not want to read. It is the same habit as
  the decisions log, one directory down: the next person needs to be able to
  disagree with the reasoning rather than guess at it.
- **The linter and the type checker are not redundant, and they overlap
  exactly where the exemptions are.** Ruff's `ANN001` is off for Qt event
  handlers, which is right — and it means ruff is also silent about every *other*
  unannotated parameter, including two in `core/`. mypy caught both. Before
  turning a rule off in one tool, check what the other one still sees.
- **Anything that can happen at frame rate is throttled *before* it reaches the
  log, and its running total is kept outside the throttle.** `log.due()` is the
  gate; the caller keeps counting either way. `_log_xruns` only advances its
  mirror when a line is actually written, so the report covers every late block
  since the last one rather than the few that happened to land in a window — a
  rate limit that also discards is a rate limit that lies about the rate.
- **A log is not a print, and this project still has no `print()` in shipped
  code.** The hole Batch 13 filled was that nothing was *recorded*, not that
  nothing was displayed. `tools/` prints because printing is the point there.
- **A cache that has to be refreshed is a cache keyed on the wrong thing.**
  If the answer is a function of two module-level values, key it on those two
  values and recompute on a miss. Refreshing it from the setters means every
  present *and future* writer has to know, and the way you find out one didn't
  is by looking at the screen. This is the previous convention — a gate keyed
  on one input is a hole the moment a second input can change the same output —
  one step further: the gate at least fails loudly the day someone reads it,
  where a stale derived colour just looks slightly wrong.
- **An `except` that is being lenient should name what it is lenient about.**
  "Best-effort" is a claim about one expected failure, not about every exception
  the block can raise. `except Exception` around a call you do not control also
  swallows the day that call is renamed, and the symptom is not an error — it is
  a feature that quietly stopped working while everything around it kept
  retrying. Narrow to the expected type and let the rest reach the excepthook;
  that is what Batch 13 built it for.
- **Check the runtime, not just the file.** The conventions already say the
  audit is one sitting's findings rather than a spec. Batch 13 extends that:
  its central claim was about how PySide6 behaves, it was wrong, and thirty
  seconds of a throwaway script in `scratchpad/` settled it. A claim about a
  dependency's behaviour is a claim to run, not a claim to read. Batch 15 is
  the same lesson about the *plan* rather than a dependency: it specified an
  offscreen smoke test, offscreen turned out to have no window handle to close,
  and one probe settled it. Both times the throwaway script was cheaper than
  the argument.
- **Verify the artifact, not the build log.** `Copying icon to EXE` proves
  PyInstaller read a file and says nothing about whether Windows can. Reading
  the `RT_ICON` resources back out of the finished binary does. This is Batch
  11's missing-licence finding generalised — it inspected a built *zip* rather
  than the dependency table and found two licences nobody had listed — and the
  cost is a few minutes at the end of a release. A build step reports what it
  attempted; only the output reports what happened.
- **A second parser is worth more than a second look.** `System.Drawing.Icon`
  returned 128x128 when asked for 256 from a file that Qt, PyInstaller and the
  Windows shell all read correctly. That is a documented GDI+ limitation rather
  than a defect, and knowing *which* it is took one more reader — where staring
  at the first result would have produced either a shrug or a day rewriting a
  file that was already right. Anything hand-assembled to a binary format
  (this project: the ICO container, the Windows version resource) should be
  read back by something that did not write it.
- **A fallback you have not broken on purpose is a fallback you have not
  tested.** The shortcut script's icon step is best-effort and degrades to the
  interpreter's icon; the way that was checked was by renaming `make_icon.py`
  and running it. Batch 14 spent a batch removing exactly this class of bug —
  a lenient path that silently stopped working — and a `try` whose `catch` has
  never executed is the same thing waiting to happen.
- **The audio callback is Python, so it competes with the paint path for the
  GIL — and it is the one with a deadline.** Everything in `ui/` that costs
  milliseconds costs them out of the audio thread's 10.7 ms budget, whatever
  the CPU headroom says. This is not a threading bug to be found and fixed; it
  is a standing property of the design, and the two things that hold it back
  are buffer depth and `sys.setswitchinterval`. Before optimising a paint,
  check whether the audio actually needs it — Batch 16's UI work bought 15% of
  a wave frame and the audio was already clean without it.
- **A metric whose baseline is structural measures nothing, and it will look
  like a real number the whole time.** Counting over-long gaps between audio
  callbacks produced ~6 a second on a completely idle machine, because 512
  frames do not divide WASAPI's 480-frame period. It was not a *noisy* signal,
  it was a signal whose floor swamped the effect — which is worse, because the
  numbers moved plausibly and pointed at the wrong culprit. Before trusting a
  new counter, run it against the case where the answer must be zero.
- **"Invisible" is a claim about bytes, so compare bytes.** Both of Batch 16's
  paint caches are asserted at three sizes as `0 differing pixels`, not looked
  at and pronounced fine. This does not replace the render — the conventions
  above are still right that only a picture says whether something *reads* —
  but where the claim is "identical", a render is the weaker instrument and an
  assertion is available.
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
the real library — a file whose *name* is one song and whose `TIT2` is a
different one now lists under the tag, which is the batch justifying itself —
20 of 31 tracks tagged, cover on screen,
exit 0. Rebuilt the exe (150 MB unpacked, 60 MB zipped, 102 s) and launched it:
it scans and lists 31 tracks, which *is* mutagen running 31 times inside the
frozen app. `qjpeg.dll` ships in the bundled `imageformats` plugins, which is
what real covers need and the one packaging risk here — mutagen itself has no
native code to leave behind.

### Batch 9 — The accent tracks the speed ✅

- [x] `theme.accent()` / `accent_soft()` / `accent_text()` off the wave's own ramp
- [x] Selection plate, glow, ▶ marker, row readout, speed slider, transport sliders
- [x] `TransportBar.refresh_accent()` — the one thing coloured by stylesheet
- [x] Harness checks, renders at three speeds, a perf pass on the gate
- [x] `tools/render.py` — the render step, promoted out of a scratch file

The ribbons had hue-shifted with the speed since Batch 5 and nothing else did.
At nightcore that meant a magenta background under an icy-blue interface, which
is the atmosphere reading out the effect and the interface disagreeing with it.

**Two earlier decisions made this a two-hour job instead of a rewrite.** No
widget captures a colour at construction — every `paintEvent` reads `theme.X`
fresh — so one module-level value reaches everything that paints. And the ramp
already existed as `theme.wave_color(fraction)`, with knots deliberately fitted
so 1.00x *is* `ACCENT`. The accent became the same function; seven paint sites
changed a word each. `PlayerController` and `core/` were untouched — the
**seventh** batch running.

**The renders found the bug, again, and it was the opposite of the predicted
one.** The risk everyone expected was magenta text at nightcore. What actually
broke was daycore: a saturated blue at `V=1.0` measures 4.9:1 against the
background, *below* `TEXT_FAINT`, so the selected row's artist came out fainter
than the unselected rows above and below it — focus making a thing harder to
read. Invisible to all 178 existing checks, obvious in one PNG. The fix
distinguishes fills from pens and lifts only what needs lifting, so 1.00x is
byte-identical to Batch 8 and the two ends are 7:1. Both a decisions-log row and
two conventions.

**The gate was measured rather than assumed.** The plan said to delete it if it
turned out to be free; a 300-step drag costs 4.70 ms/step gated and 6.70
ungated, so it stays and the number is written down.

Verified: **231 tests green** (unchanged — `tests/` is core-only by convention
and this batch is entirely `ui/`, which is a deliberate omission rather than a
gap), `tools/shell_harness.py` **193/193** including 15 new checks — the accent
equals the wave's colour at all three speeds, the plate derives from it, the
transport stylesheet follows, the bucket gate fires and doesn't, and the text
floor holds at every speed. Rendered Music (selected row with a long artist) and
Now Playing at 0.80x / 1.00x / 1.30x, at 720x480 and 980x640, and looked at
them. Startup verified at all three saved speeds against an independently
computed colour — the seed in `__init__` runs at `DEFAULT_SPEED` and it is
`controller.start()` firing `speed_changed` that actually colours a launch,
which is worth knowing before trusting that line.

**The render step became a tool.** Four batches have now said "the assertions
passed and the picture didn't", and each one rendered its PNGs from a throwaway
script that was then deleted. `tools/render.py` is that script kept:
`--what now|music|settings`, `--size`, repeatable `--speed`, stacked and
captioned. It writes no settings and plays no sound, and it is where the next
"but does it read?" question gets answered.

Not done: the `.exe` was not rebuilt (see the resume block), and nobody has sat
and dragged the slider by hand yet — the renders are stills of three points on a
continuous move.

### Batch 10 — Preset themes ✅

- [x] `theme.Palette` + `PALETTES` — five ramps: XMB Blue, Ember, Aurora, Vapor, Mono
- [x] `palette()` / `palette_names()` / `set_palette()`; `wave_color` reads the active one
- [x] `settings.theme` — a bare validated name, `core` side
- [x] `PlayerController.set_theme` / `theme_changed`, clamped and persisted
- [x] A `Theme` row in Settings, stepped into with Enter and walked with ←→
- [x] `ItemColumn.set_stepping` — the outline, and nothing else
- [x] `tools/render.py --theme` / `--step`, harness checks, tests, `CLAUDE.md`

The ask was "change the spectrum the slider moves through", and Batch 9 had
already made that a one-function question: every accent in the app comes from
`wave_color(fraction)`, and the ramp was two hard-coded knot tuples. So a theme
is those two tuples with a name on them, and `PlayerController`, `core/audio/`,
`wave.py`, `item_column.py`, `now_playing.py` and `transport.py` were all
untouched — the **eighth** batch running where the seam held. Every paint site
reads `theme.X` fresh, so five palettes cost the widgets nothing.

**Two things had to be told, and both were the same shape of bug.**
`_accent_text_mix` is cached module state recomputed only inside
`set_accent_fraction`, and the transport bar's colours live in a stylesheet
gated on a 48-bucket quantisation of the *fraction*. A palette swap moves
neither the fraction nor the bucket, so both would have gone on answering the
question they were built for while the answer had changed underneath them.
That is a convention now — a gate keyed on one input is a hole the moment a
second input can change the same output.

**The renders found the bug, for the fifth batch running, and it was not a
contrast one this time.** All 227 checks were green while Aurora and Vapor
opened on the same teal — 169° and 180°, two presets wearing one colour at the
daycore end. Nothing measurable was wrong: both cleared 14:1, both travelled
three distinct hues, both hit their anchors. Aurora's daycore moved to 0.43,
which puts its whole ramp inside the greens and is what the name promised
anyway. Mono was caught before it shipped by the same reasoning at the other
end: at saturation 0.06 its anchor measured (240,248,255), which is white — an
accent the same colour as the text is not an accent. It sits at 0.16.

**The contrast floor carried over for free and earned its keep.** Ember's 1.00x
lands at 6.99:1 against a 7.0 floor and takes exactly one 0.05 mix step; every
other palette needs none, and XMB Blue at 1.00x is still byte-identical to
Batch 8. That is the floor doing what it was written for, on colours nobody had
when it was written.

**Then the row stopped cycling and started being stepped into**, at the user's
ask, after cycling had been built, rendered and run — and then the adjusters
moved from ↑↓ to ←→, same batch, same reason. Both are decisions-log rows; the
thing worth carrying forward is how little the mode cost. It is one bool on the
window, one bool on the column, and an outline — because the Batch 4 objection
to per-row modes ("`ItemColumn` would have to learn what a row means") is
avoidable by simply not telling it. `set_stepping` draws a rectangle. Every
branch about what the arrows do while it is on lives in `_handle_key`, in one
block, ahead of everything that assumes them.

Landing on ←→ is what makes the mode pay for itself rather than merely exist.
The standing rule is that Left and Right are category navigation *everywhere*,
and a stepped-into row is the one place that is suspended — which is what real
XMB does with a slider item, what the outline is announcing, and what the
readout's `‹ ›` chevrons have been pointing at all along. With ↑↓ as the
adjusters the mode was buying back keys that were never scarce.

The interesting half was the **exits**, exactly as it was in Batch 6 with the
silences. Only three are branches: Enter, Esc, Backspace. The rest — ↑↓, Home,
End, the wheel, a click on another row, a category change — all leave because
the cursor moved off the row, which is one connection to `index_changed` rather
than six. And `index_changed` is a signal this project had deliberately never
wired anything to, on the grounds that it also fires when the app moves the
cursor itself. That is precisely why it works here: if something moved the
cursor while a row was stepped into, the user is no longer on that row, whoever
did the moving.

Also landed: the Settings rows have names (`SET_FOLDER … SET_QUIT`). Inserting
`Theme` in the middle shifted `Full screen` and `Quit`, and an if-chain of bare
integers turns that into `Full screen` quitting the app rather than into a
rename. And the harness now pins the palette to the default before it asserts
on a colour — it reads the real `settings.json`, so once the theme persisted,
every `ACCENT` comparison in it depended on which theme the machine was left on.

Verified: **240 tests green** (9 new, core-only as the convention requires --
the settings field, including that an unrecognised name survives the round trip
rather than being helpfully destroyed). `tools/shell_harness.py` **251/251**,
58 new: every palette's anchor against its hand-written literal, every palette's
ramp travelling, the 7:1 floor and the never-fainter-than-`TEXT_FAINT` check at
three speeds × five palettes, the bucket-gate hole, ←→ walking all five presets
in both directions and wrapping *without the crossbar moving*, Ctrl+arrow still
being transport inside the mode, every way out of it, and the unknown-name
clamp. Rendered all five palettes at three speeds
on Music at 980x640, plus Now Playing, the Settings row and the stepped-into row
(`--step`), and looked at them. Ran it for real: 31 tracks playing throughout,
stepped into the row, walked every theme in both directions with the transport
bar following each time and the crossbar staying put, stepped out, confirmed Left went back to the crossbar. Theme persistence checked with a redirected `%APPDATA%` — pick, quit,
relaunch, same palette on screen.

Not done: the `.exe`, for the same reason as Batch 9 — UI-only, no new
dependency, no new bundled asset.

---

## The ship-prep audit

Run in one sitting before Batches 11–15 were written, in two sweeps: one over
the repo's distribution surface, one over the source's design health. **Recorded
here so it is not re-derived** — the findings are what the five batches are made
of, and a batch that re-audits before starting is spending its budget twice.

Line numbers are as of `d663345` and will drift. The claims are what matter.

### What holds up — don't go looking for these again

- **`core/` imports no Qt.** Zero hits, and *proven* rather than asserted:
  `core/models.py` keeps its `Tags` import under `TYPE_CHECKING`, and
  `core/tags.py` returns raw cover bytes precisely so it never needs an image
  library. The full import set for `core/` is stdlib plus numpy, soundfile,
  sounddevice and mutagen.
- **No bare `except:` anywhere.** All seven `except Exception` sites either
  re-raise as a typed error (`DecodeError`, `AudioDeviceError`) or are
  documented best-effort with a reason. Every "never raises" docstring claim —
  `settings.load`, `tags.read_tags`, `tags.read_art`, `library.scan_folder` —
  was checked and holds.
- **The threading discipline stated in `engine.py`'s header is honoured
  clause-for-clause.** The callback allocates nothing on the steady path, takes
  no locks and touches no Qt; `speed`/`volume` are single-attribute assignments;
  the seek request is a single tuple publish; end-of-track is a flag the UI
  polls. There is one thread in the whole app and this code did not create it.
- **Type hints are near-complete and modern.** `from __future__ import
  annotations` everywhere, `str | None`, `frozen=True, slots=True` dataclasses.
- **No file is oversized.** ~10k lines over 43 files, median ~180. The largest
  shipped file is `ui/main_window.py`. The largest file in the repo is
  `tools/shell_harness.py`, which is not shipped.
- **`.gitignore` is correct** and nothing personal is tracked: no music, no
  `settings.json`, no build output, no absolute paths beyond two `"D:/Music"`
  docstring examples (Batch 11 scrubs those).
- **Settings writes are atomic** (temp file + `os.replace`) and `engine.close()`
  is idempotent.

### What doesn't — this is the batch list

Each of these is claimed by a batch below; the batch is where the reasoning
lives.

| Finding | Batch |
|---|---|
| No `LICENSE`, and mutagen is GPL-2.0, linked directly and bundled into the exe — the zip already carries copyleft with nothing in the repo saying so | 11 |
| No `__version__` anywhere, so every zip is named identically and two releases are indistinguishable by filename | 11 |
| ~~No `pyproject.toml`, no pytest config, no lint/type/format config of any kind — the discipline is there, nothing pins it~~ *(done, Batch 12 — format config deliberately declined)* | 12 |
| ~~Dependency ranges float with no upper bound, over dtype-sensitive DSP~~ *(done, Batch 12)* | 12 |
| ~~No CI~~ *(written, Batch 12 — but never run; no remote until Batch 15)* | 12 |
| ~~No logging and no top-level exception handler: under `pythonw.exe` a slot exception is a silent process death and a failed settings write is invisible~~ *(done, Batch 13 — and it is not a process death; see there)* | 13 |
| ~~`theme._accent_text_mix` — a derived global cache with two writers and no invalidation guard~~ *(done, Batch 14 — keyed on its inputs rather than invalidated)* | 14 |
| ~~The Settings rows are a hand-maintained parallel array~~ *(done, Batch 14)* | 14 |
| ~~`read_art` called straight from the widget layer — the one real leak past the controller seam~~ *(done, Batch 14 — a signal, not a method; see there)* | 14 |
| ~~`refresh_devices` swallows every exception around *private* sounddevice API~~ *(done, Batch 14)* | 14 |
| ~~No icon; no automated smoke test of the built exe; nothing in the README for someone who just wants to download it~~ *(done, Batch 15 — the smoke test is not offscreen; see there)* | 15 |

### One finding deliberately not in a batch

**`ui/` has no automated tests** — 3,805 lines whose only coverage is a
1,308-line print-and-assert script that CI cannot run. That is a real gap and it
is *known and declined*: the scope chosen for this set was hygiene plus targeted
fixes, not a UI test suite. Several pure functions in `main_window.py` and the
whole `theme.py` contrast pipeline are testable today with no widget at all, so
this is cheap whenever it is wanted. **Don't treat it as an oversight and don't
quietly start it inside another batch.**

---

## Roadmap — ship prep

Batches 11–15. Same working agreement as everything above: **one batch at a
time, each ending in something runnable, tick the boxes, report, and stop for
sign-off before starting the next.**

Ordered so each is independently shippable and each one's output is available to
the next: **legal first** (it blocks release), then **enforcement** (so
everything after it is checked as it lands), then **diagnosability** (so the
defect work has somewhere to report), then **the defects**, then **cut the
release**.

### Batch 11 — Licence, provenance and version ✅

The legal blocker, plus a single source of truth for "which build is this".

- [x] `LICENSE` — GPL-2.0-or-later, full text
- [x] `THIRD_PARTY_NOTICES.md` — the six dependencies and their licences
- [x] `mp3player/__init__.py` gains `__version__` (it is an empty file today)
- [x] `tools/build_exe.py` reads it: version-stamped zip name, `--version-file`
- [x] `--add-data` the two licence files into the bundle
- [x] Scrub the two `"D:/Music"` examples and the personal track name; add a
      header framing `CLAUDE.md` for outside readers
- [x] `README.md` points at `LICENSE` instead of explaining the licence inline
- [x] **Beyond the original list:** `licenses/` — the three third-party texts
      that do not ship themselves, bundled too (see below)

**The licence choice is settled: GPL-2.0-or-later throughout.** Chosen with the
user. mutagen is GPL-2.0 and is linked directly by `core/tags.py`, and the
PyInstaller bundle statically incorporates it — so the zip *is already* a
combined work under GPL-2.0 and has been since Batch 8. The alternatives were
MIT-source-with-a-GPL-binary (defensible, muddier, needs a NOTICE explaining the
split) and dropping mutagen for a hand-rolled ID3 reader (~200 lines, rejected
once already in Batch 8 — this library is YouTube rips and the failure mode is
mojibake titles). Writing down what is true costs nothing and is the honest one.

The dependency list for `THIRD_PARTY_NOTICES.md`: mutagen (GPL-2.0),
PySide6/PySide6_Addons/PySide6_Essentials/shiboken6 (LGPLv3 — and LGPL normally
wants either dynamic linking or relinkable objects, which a onedir PyInstaller
bundle generally satisfies, but say so rather than leave it to chance), numpy
(BSD-3), sounddevice (MIT), soundfile (BSD-3, bundling libsndfile under
LGPL-2.1), pytest (MIT, dev only). **State the PyInstaller interaction in the
file**, not in a code comment — `requirements.txt` currently defers to "the
decisions log in CLAUDE.md", which is not where anyone unzipping a release will
look.

Note that the two licence files are the build's **first bundled data**. ~~The
comment above `COLLECT_BINARIES` in `build_exe.py` says there are no data files
because the UI sounds are synthesized; that stops being true here, and the
comment needs to stop saying it.~~ *There is no such comment* — the audit
misremembered `COLLECT_BINARIES`'s comment, which is about `soundfile` and
`sounddevice` shipping DLLs that nothing in the bytecode points at. Nothing to
correct. **The audit is a record of one sitting's findings, not a verified
spec; check a claim against the file before acting on it.**

**The version is `1.1.0`, and that is the first number this project has ever
had.** `v1` was a git tag and nothing else, so the exe built in Batch 8 and the
exe built today would have had identical filenames and identical (empty) file
properties. 1.1.0 rather than 1.0.1 because Batches 8, 9 and 10 are features —
tags and art, the accent ramp, five themes — and rather than 2.0 because
nothing about the app got taken away. It is deliberately set *now*, at the start
of the ship-prep set, so 12–15 land inside a version rather than bumping it
again; the release Batch 15 cuts is 1.1.0.

**Three places carry it and one owns it.** `mp3player/__init__.py` is the owner
and is otherwise still empty of imports, which is not laziness — `core/` imports
that module transitively, so anything with a dependency in it would put a crack
in the no-Qt seam from *above*, where nobody is looking for one. `app.py` hands
it to `QApplication.setApplicationVersion`, and `build_exe.py` imports it for
both the zip name and a generated Windows version resource.

**The version resource is generated, not checked in.** PyInstaller's
`--version-file` takes a file containing a `VSVersionInfo(...)` literal, which
is four 16-bit integers plus a string table; a checked-in one is a second copy
of the version number waiting to disagree with the first. `write_version_resource`
writes it into a **temp directory** rather than `build/`, because `--clean`
empties the work path and this file has to survive until PyInstaller reads it.
`version_quad` truncates a pre-release suffix (`1.2.0rc1` → `(1, 2, 0, 0)`)
because the binary field cannot hold one, while the string fields keep the real
value — which is the half anyone actually reads.

**The licence files are added twice, on purpose.** `--add-data` puts them in the
bundle, which under PyInstaller 6 means `_internal/` — a folder with four
hundred DLLs in it, where nobody will ever see them. So `copy_licences` also
drops both at the top of `dist/XMB Player/`, next to the exe. The GPL asks that
the licence travel with the binary; one copy satisfies the letter and the other
satisfies the point, and 36 KB in a 150 MB folder is not a trade worth thinking
about.

Also landed: `main()` deletes stale `XMB-Player-*windows.zip` files before
building, since `1.0.0` sitting beside `1.1.0` in `dist/` is precisely the
confusion the version stamp exists to end; and four core tests
(`tests/test_version.py`) hold `__version__` to a shape the Windows resource can
actually take, plus one that reads `__init__.py` back and asserts it still
imports nothing. Neither failure mode is loud on its own — a non-numeric version
yields `(0, 0, 0, 0)` in the file properties and ships happily.

**What the notices file says that a code comment could not.** The audit's
instruction was to state the PyInstaller interaction *in the file*, and the
substance is that a onedir bundle is not a static link: every Qt DLL and
libsndfile sit beside the exe as replaceable files, which is what LGPLv3 and
LGPL-2.1 are asking for. Written out, with the licence-text locations verified
rather than assumed — and verifying them is what turned up the one thing this
batch found that nobody had listed.

**The zip was missing two licences, and neither was ours.** Checking what a
built zip *actually contains* rather than what the dependency table says it
should: libsndfile's LGPL-2.1 is in there (`_internal/_soundfile_data/COPYING`)
and so is numpy's BSD, because those packages carry their licence inside their
own directory and PyInstaller collects it along with everything else. **Qt's and
PortAudio's are not.** The PySide6 wheels ship only
`LicenseRef-Qt-Commercial.txt` — the side of Qt's dual licence that is *not* in
use here — and the PortAudio binaries inside `sounddevice` ship a `README.md`
and nothing else. Both are licences that ask for a **copy**, not a citation:
LGPLv3 §4(b) wants the combined work accompanied by the LGPL and the GPL it
incorporates, and MIT wants its notice in all copies. So the first draft, which
linked to gnu.org and portaudio.com, was not sufficient. `licenses/` holds the
three texts verbatim, the build copies the folder in beside the exe, and
`licenses/README.md` says which is which and why the rest are absent — because a
folder of licences with no index invites the next person to add the ones that
were deliberately left out.

This is the batch's one piece of scope beyond its own checklist, and it is here
rather than deferred because the batch is the release blocker: a Batch 15 zip
built from the original checklist would have shipped incomplete.

Verified: **244 tests green** (4 new, core-only as the convention requires),
`tools/shell_harness.py` **251/251** — unchanged, and unchanged is the right
answer, because nothing in this batch touches a widget. The one code change
outside the build script is `app.py` gaining
`setApplicationVersion`. **The `.exe` was rebuilt twice and run**, which is where
the real verification is: the first build proved the version resource and
`--add-data` work, and inspecting *its zip* is what turned up the two missing
licences; the second carries `licenses/` and was checked at both destinations.
Windows file properties read `1.1.0` / `XMB Player` / the GPL copyright line.
Launched the built exe with a real window, confirmed the title, closed it
through `CloseMainWindow` and **got exit 0** — which means the bootloader found
libsndfile and PortAudio, `aboutToQuit` fired, and settings flushed.

Not done, deliberately: the exe is *not* the release artifact. Batches 12–15
change the build again, and Batch 15 owns the tag, the icon, the automated smoke
test and the zip anyone downloads.

### Batch 12 — Project metadata and enforcement ✅

The sharpest structural gap in the repo. The annotation and formatting
discipline is already good enough to pass these tools — it just isn't pinned, so
it decays the moment a second person contributes.

- [x] `pyproject.toml` — `[project]`, `[tool.pytest.ini_options]`,
      `[tool.ruff]`, `[tool.mypy]`
- [x] Cap the floating dependency ranges
- [x] Fix what the tools flag
- [x] `.github/workflows/ci.yml` — Windows: ruff + mypy + pytest
- [x] `README.md` — the badge, and what CI does *not* cover

**Windows-only, declared.** Chosen with the user. The README currently hedges —
"nothing is Windows-specific by design" — and that claim has never been run.
Every measurement in this project is Windows (WASAPI at 22 ms, the `%APPDATA%`
path, `run.bat`, `make_shortcut.ps1`). The classifiers and the README say
Windows and stop apologising for it. Claiming portability nobody has tested is
worse than not claiming it.

`pytest` today works only because `tests/__init__.py` plus rootdir insertion
happen to resolve `mp3player`. That is luck, it is fragile for an outside
contributor, and it is a blocker for CI as-is — which is most of why
`pyproject.toml` is here rather than being a nice-to-have.

The floaters need caps because the DSP is dtype-sensitive throughout (`float32`
assumed at every layer), and `numpy>=2.0` with no ceiling is an open door to a
3.x. The four Qt pins are `==` already and must stay that way — shiboken6 and
PySide6 mismatched is an import-time ABI error.

Expect the tool fixes to be small: three missing return annotations, two
over-length lines, and ~22 Qt event-handler overrides taking an unannotated
`event`. **Decide the `event` question once and write the decision down** —
annotate them all or exclude the pattern in config. Doing half is how a linter
starts getting ignored.

**CI runs ruff, mypy and pytest, and not `tools/shell_harness.py`.** Chosen with
the user, and the reason is physical rather than philosophical: the harness
opens a real WASAPI stream and GitHub's runners have no audio device. Making it
device-optional means auditing 1,308 lines for device assumptions and living
with a permanently split pass count, which is a batch of its own if it is ever
wanted. So the harness stays a local pre-release step, which is what it already
effectively is — and **the README must say the badge covers `core/` only**, or a
green badge reads as "the UI is tested" when the UI is the part with no tests.

**The prediction was right about the shape and wrong about the size.** The audit
guessed "three missing return annotations, two over-length lines and ~22
unannotated `event` parameters". It was exactly three return annotations
(`Mixer.set_track`, `AudioEngine.load`, `sfx._glide`) and four over-length lines,
all four in the harness. The rest of the 67 findings were things nobody had
listed: 31 dead `# noqa` directives, a percent-format in a test, a mutable class
attribute, four `int(round(...))` where `round` already returns an int, and one
`zip(knots, knots[1:])` that is spelled `itertools.pairwise`. None of it was a
bug. That is the point — **the tools were adopted because the discipline is
already there, and the job was pinning it, not repairing it.**

**The `event` question was decided rather than half-done**, as the batch asked.
`ANN001` is off, globally, with the reason written next to it in
`pyproject.toml`: a Qt override's parameter type is fixed by the base class,
PySide6 already states it in its own stubs, and annotating twenty-two of them
adds an import per widget to restate what Qt knows. What that costs is visible
one layer down, and worth knowing: with `ANN001` off, ruff had nothing to say
about `StreamWatch.__init__(self, stall_s, clock=time.monotonic)` or
`AudioEngine._callback(self, outdata, frames, _time_info, status)` — **both of
which mypy caught, because they are in `core/` where nothing is exempt.** The two
tools are not redundant, and the overlap is exactly where the exemptions are.

**mypy came back with 183 errors and 140 of them were one thing.** PySide6
supports the flattened enum names it has always documented — `Qt.AlignLeft`,
`QPainter.Antialiasing`, `Qt.Key_F11` — and its *generated stubs* declare only
the scoped spellings. 58 distinct symbols across every painting file, all of them
code that runs correctly. The alternative to switching `attr-defined` off in
`ui/` is rewriting every paint call site to `Qt.AlignmentFlag.AlignLeft`, which
would also rewrap most of the lines it touched. It is a decisions-log row, and
`ui/` keeps every other check — which is not a token concession, because **the
half that stayed on is the half that found something**: `wave.py`'s two buffers
were typed `QImage | None` and dereferenced without a guard in six places. Not a
live bug — `_resize_buffers` runs first and always assigns — but an `Optional`
nobody could ever hit, standing in front of six real paint calls. They are null
`QImage`s now, which the existing size comparison rebuilds on the first frame
exactly as the `None` check did.

**`ruff format` is configured out, not in.** It is the one tool here that was
declined, and the reason is that its entire quarrel with this repo is
line-joining: 290 changed lines across 17 files, every one of them a
hand-wrapped signature or a comment block that the formatter would rejoin
because it fits. A batch whose job is to pin the discipline that already exists
should not spend its diff rewriting that discipline into a different one. The
linter is pinned; layout stays a judgement. `line-length` is 96 for the same
reason — it is where this code already lives, so it is a ceiling rather than a
target, and only four lines had ever crossed it.

Also landed: `pythonpath = ["."]` in the pytest config, which is the whole
reason `[tool.pytest.ini_options]` was on the list — `pytest` had been resolving
`mp3player` by rootdir insertion, which is luck, and luck a CI runner does not
have. `.gitignore` picked up `.ruff_cache/`, `.mypy_cache/` and `*.egg-info/`.

Verified: **244 tests green** (unchanged, and unchanged is right — this batch
adds no behaviour), `tools/shell_harness.py` **251/251** with the known flake
passing on the first run, and `ruff check .` and `mypy` both clean over the whole
tree. `pip install -e . --no-deps` resolves the dynamic version to `1.1.0` out of
`mp3player/__init__.py`, which is the check that matters for `[project]`: the
version keeps one owner and the metadata reads it rather than copying it.
Rendered Now Playing at three speeds and looked at it, because the fixes touched
four paint sites (`theme.mix`, the wave's buffers, the info block's `zip`, the
volume readout). Launched the app for real under both `python.exe` and
`pythonw.exe`: it starts, paints, holds a live WASAPI stream and writes nothing
to stderr.

Two things not done, both deliberate:

**The CI workflow has never run.** There is no GitHub remote yet — Batch 15 is
what pushes one. It targets `windows-latest` and Python 3.13 and its three
commands are the three that pass locally, but **a workflow that has not gone
green has not been checked.** Expect to fix it on the first push; the likeliest
failure is `import sounddevice` on a runner with no audio device, which
`tests/test_engine.py` performs at import time.

**The app was not closed by hand at the end of the real run.** `CloseMainWindow`,
`taskkill` and a posted `WM_CLOSE` all fail to reach this window: it is
frameless and sets no title, so Windows reports no main window handle for the
process and the graceful paths have nothing to address. That is a property of
driving it from PowerShell, not a defect — the exe *was* closed this way in Batch
11, and the harness exercises the real `shutdown()` — but it means the exit path
was not re-verified here. Nothing in this batch touches it.

### Batch 13 — Diagnosability: logging and the crash path ✅

Four things happen today and leave no trace anywhere. For a `pythonw.exe` build
with no console, that means a user who hits any of them has nothing to send you.

- [x] A rotating, size-capped log next to `settings.json`
- [x] `sys.excepthook` + `try/finally` around `app.exec()`
- [x] A crash dialog naming the log file
- [x] Log the four invisible events
- [x] A failed settings write reaches the status line
- [x] Tests for the log path

The log goes next to `settings.json` via the existing `config_dir()` — one
place the app already owns, already created, already documented as redirected
under Microsoft Store Python. Don't invent a second location.

**The `try/finally` is the highest-value line in the batch.** `app.py` ends in a
bare `return app.exec()`. Under PySide6 an unhandled exception in a slot
terminates the process, `aboutToQuit` never fires, and `controller.shutdown()`
— which is what flushes settings and closes the stream — never runs. So the
current failure mode for any unanticipated bug is: the window vanishes, nothing
is written anywhere, and the user's last 800 ms of settings changes are gone.
`shutdown()` is already idempotent, so the `finally` costs nothing and cannot
double-fire.

The four events, all of which are currently silent:
`engine.xruns` is incremented by the audio callback and read by nothing;
`settings.save()` returns `False` on failure and `controller._save_now`
discards it; `refresh_devices` swallows its exception whole; and every device
loss and reconnect cycle passes without record. The settings one is the worst
of the four from the user's side — a failed write is experienced as the app
forgetting your music folder for no reason, which is exactly the symptom the
`utf-8-sig` decision was written about.

**This is a logging batch, not a print batch.** There is currently no `print()`
in shipped code at all — only in `tools/`, where printing is the point. That
discipline is right and stays; the hole is that nothing is *recorded*, not that
nothing is displayed.

---

**The batch's own premise was wrong, and finding that out took thirty seconds.**
The audit said an unhandled exception in a slot terminates the process, which is
what made the `try/finally` "the highest-value line in the batch". Three
throwaway scripts in the scratchpad say otherwise for PySide6 6.11: a timer slot
that raises, and a `paintEvent` that raises, both go to `sys.excepthook` and the
app **carries straight on** — the paint one raising again on every single frame
after that.

That is worse, and it moves the batch's centre of gravity. If the process died
you would at least know. Instead: nothing stops, nothing is written, the traceback
goes to a `sys.stderr` that is `None` under `pythonw.exe`, and the app keeps
running in whatever state the half-finished slot left it. So the excepthook *is*
the batch, and two things follow from "carries on" that would not have been
written otherwise — the dialog is **one-shot per launch**, and `record_exception`
throttles the file by `(type, file, line)`, because a hundred copies of one
traceback would rotate everything else out of a 256 KB file in about a second.
Both are decisions-log rows.

**The `try/finally` stayed, and justified itself immediately.** Not for the
reason it was written: the first real run of the app after this batch went in
crashed in the *scratchpad runner driving it*, outside any slot — and the log
shows `shutting down`, then `exiting`, then the traceback. Settings flushed, the
stream closed, and a report written, from a bug in a file that is not even part
of the project. That is the whole batch working, by accident, before anyone
tried to test it.

**Four events, four different reasons they were invisible.** `engine.xruns` was
incremented by the audio thread and read by nobody. `settings.save()` has
returned a bool since Batch 1 and no caller has ever looked at it. Device loss
and reconnect were deliberately quiet on screen — correctly, "an app that
narrates its retries is noisier than one that simply starts working again" — and
being quiet on screen had silently meant being quiet everywhere. And
`refresh_devices` swallowed its exception whole; it still catches `Exception`,
because narrowing it is Batch 14's line, but it no longer swallows it silently.

**The failed settings write is the one the user sees**, and it is the one worth
getting right: it reaches the status line as a short sentence (`Could not save
settings` — rendered at 720 px and 980 px and looked at, because the status line
is drawn in the small font at the right edge), and only on the *edge*. The next
write 800 ms into a volume drag will fail for the same reason, and `failed` also
blips; a notice that re-announces itself once a second is an alarm. The log gets
every attempt, with the path.

Also landed: `tools/render.py --status`, because looking at the new sentence
needed exactly the flag the conventions say to add rather than another script;
`log.due(key, gap_s)`, whose clock is injectable for the same reason
`Sounds.clock` and `StreamWatch.clock` are; and three lines of context the log
needs to be readable at all — the version at startup, the device and its latency
when the stream opens, and the xrun total on the way out. A real launch writes
exactly four lines and then stops.

Verified: **253 tests green** (9 new, core-only as the convention requires — the
log path, idempotent setup, a target it cannot open, the size cap, the throttle
against a driven clock, and an exception written once and then recognised as the
same one). `tools/shell_harness.py` **267/267**, 16 new: the failed write
reaching the status line and blipping exactly once and not twice, the recovery
being silent, an exception producing one log entry and one dialog however many
times it repeats, the dialog naming the file, and the device-loss section from
earlier in the same run turning up in the log where it should be. Rendered the
status line at both sizes and the crash dialog itself with its real text, and
looked at all three. Ran the app for real with a mapped window, exit 0, four
clean lines in `%APPDATA%/XMBPlayer/xmbplayer.log` and `22.0 ms` of WASAPI in
the second one.

One thing the harness cannot do and does not pretend to: PySide6 lets an
exception raised inside `processEvents()` propagate back out to whoever called
*it*, so a `QTimer` probe takes the harness down instead of reaching the hook.
Qt's half — that `exec()` routes to `sys.excepthook` — was checked directly in
the scratchpad. What the harness checks is ours: what the hook does when it is
handed one.

### Batch 14 — The four design defects ✅

Targeted fixes, no restructuring. Each one deletes a *class* of bug rather than
an instance — which is the bar for being in this batch at all.

- [x] `theme._accent_text_mix` becomes lazy: compute on read, invalidate on write
- [x] The Settings rows become one table of `(label, value_fn, action)`
- [x] `read_art` moves behind the controller
- [x] `refresh_devices`'s `except` is narrowed and logged
- [x] Harness checks and core tests for whatever is testable without a display

**1. The accent-text cache.** Two writers, `set_palette` and
`set_accent_fraction`, both of which must recompute it, neither of which is
forced to. Both do the right thing today and the comment in `set_palette` names
the risk in its own words: *"forgetting this is exactly the Batch 9 bug with a
new way in."* A third writer of `_palette` or `_accent_fraction` — or any future
input the accent depends on — silently desyncs it, and the symptom is unreadable
text, which is a colour and not an error. Computing on read removes the
possibility instead of documenting it. This is the conventions' own *"a gate
keyed on one input is a hole the moment a second input can change the same
output"* rule applied to the value living next door to the gate it was written
about.

**2. The Settings rows.** `_settings_items` and `_activate_settings` are a
parallel array held together by counting. Batch 10 already hit this: inserting
`Theme` in the middle shifted `Full screen` and `Quit`, and without names that
is `Full screen` quitting the app. The `SET_FOLDER … SET_QUIT` constants were
the mitigation, and they name the indices without removing the requirement that
two lists stay in the same order. One list of tuples removes it.

**3. `read_art`.** `main_window` calls `core.tags.read_art` directly — file I/O
and full ID3 parsing performed by a widget, in the one project whose entire
architecture rule is that widgets do not do that. The controller owns "when a
track changes" and never sees this happen. **The `core` hands up bytes / `ui`
makes pixels split stays exactly as it is** — that seam is right and is not what
is being fixed. Only the call site moves. Note the timing comment while you are
there: it justifies *when* the read happens (it disappears into a decode that
was going to block anyway) and that reasoning survives the move unchanged.

**4. `refresh_devices`.** `except Exception: pass` around `sd._terminate()` and
`sd._initialize()` — both **private** sounddevice API. A rename in a future
sounddevice release turns that into an `AttributeError`, silently caught, and
device reconnection stops working forever while the reconnect timer keeps firing
every 2 s and the "audio device lost" banner stays up. The failure is
indistinguishable from the device genuinely being unplugged, which is the worst
kind of silence and precisely the shape of bug Batch 7 wrote the reconnect path
to avoid. Narrow it and log it — Batch 13 is what gives it somewhere to go,
which is why it is sequenced first. **The logging half is already done**: the
`except` writes a warning with its traceback today, and still catches
`Exception`. What is left here is the narrowing, which is one line and one
argument about which exceptions are actually expected.

---

**The batch found nothing, and that is the first time.** Every batch since 4 has
had a section here about what the renders caught or what the audit got wrong.
This one has no such section: four fixes were specified, four fixes landed, and
the renders at the end were checked against the expectation that *nothing moved*
— which is what they showed. Worth saying out loud rather than leaving as an
absence, because the pattern of the previous ten batches would have the next
person looking for the twist.

There is a reason it went that way, and it is not luck. All four are the same
shape of change: **each one removes something somebody has to remember**, and
none of them changes a pixel, a sound, a curve or a number. The audit's own bar
for this batch — "deletes a *class* of bug rather than an instance" — is also
the property that makes them safe, because a fix that only removes a requirement
cannot introduce a behaviour.

**The accent-text cache is the one worth reading the diff of.** The brief said
"compute on read, invalidate on write", and invalidate-on-write is still two
writers who have to remember — the same requirement one level down. Keying the
cache on `(palette name, fraction)` and recomputing on a miss removes the
requirement instead of relocating it: any future writer of either value, or any
third input, is noticed without being told. The harness check is the bug itself,
written down — set XMB Blue at 1.00x (which needs no lift), assign
`theme._palette = Ember` **directly, straight past the setter**, and demand the
result still clears 7:1. Ember at 1.00x measures 6.99:1 raw and takes exactly one
0.05 step, so a stale mix of zero lands it just *under* the floor. One
comparison, and it is the whole defect.

**The performance argument for that change is real and does not matter**, which
is worth recording because it is the kind of number this file collects and
somebody will otherwise re-derive it as a justification. The contrast loop used
to run on every `set_accent_fraction`, i.e. once per mouse-move of a drag; behind
the key it runs when the answer can have changed. Measured over a 300-step drag:
**0.051 ms/step down to 0.033**, against a drag step that costs 4.70 ms in total.
0.4%. The reason for the change is that the old one could be silently wrong.

**`refresh_devices` was the one with an actual decision in it.** Narrowing
`except Exception` means saying which exceptions are expected, and the answer
turned out to be exactly one: both `sd._terminate` and `sd._initialize` route
their return codes through `sd._check`, so `PortAudioError` is the whole of the
lenient case — and it is genuinely lenient, being what an unplugged device does
every 2 s for as long as the headphones are out. The interesting half is what
happens to the *other* one. An `AttributeError` from a renamed private call now
propagates, out of `reopen`, out of the reconnect slot, into `sys.excepthook`:
one log entry, one dialog, and the retry timer carries on exactly as before. That
is only a sane outcome because Batch 13 exists, which is why the audit sequenced
it first — and it is the sequencing paying off rather than merely being tidy.
Three core tests pin it, and none of them touch the real PortAudio: both calls
are replaced, because the live stream is still open and the function is
documented as needing it closed.

**`read_art` moved as a signal rather than as a method**, and the distinction is
the point of the finding. A `controller.current_art()` the window calls would
satisfy the letter — nothing above the seam imports `core.tags` any more — while
leaving the widget deciding when to hit the disk, which is the actual complaint.
`art_changed(bytes | None)` puts *when* on the side that already owns it: it is
emitted next to `track_changed`, in the two places that exist, one of which is
immediately after the 70–210 ms decode the timing comment was always about. The
`core` hands up bytes / `ui` makes pixels seam is untouched and was never the
problem; `_cover_image` just takes bytes now instead of a path.

**The Settings table is the smallest change and closes the oldest hole.** Batch
10 hit this defect for real and mitigated it with names; the names were right and
were never sufficient, because two lists in one order is a requirement whatever
the indices are called. `_settings_rows()` is now the only place the order is
stated, `_settings_items()` is derived from it, and `_activate_settings` is a
lookup. The `SET_*` constants stay, demoted: nothing inside the file counts with
them any more, and the harness uses them to name a row. The check that earns its
keep pins each *action* to its index, not just each label — which is the half
that was never checkable before, because the actions were branch bodies.

Verified: **256 tests green** (3 new, core-only as the convention requires — the
`refresh_devices` split, both directions, plus the ordering of the two calls).
`tools/shell_harness.py` **286/286** on one run and 285/286 on another with the
known WASAPI flake, 19 new: the accent floor holding when either input is written
behind the setter's back and across all five presets at three speeds, 1.00x still
taking no lift at all, the five rows and each row's action, the painted items
being derived from that same table, an out-of-range activation being a no-op, the
controller handing a cover up on a track change as bytes and never as a `QImage`,
`_cover_image` on nothing and on bytes that aren't an image, and the two
`refresh_devices` outcomes. `ruff check .` and `mypy` clean. Rendered Settings at
720x480, the stepped-into row, Now Playing with a real cover and Music, all at
three speeds, and looked at them: nothing moved, which is the result this batch
wanted. Ran the app for real with a mapped window — played a track (the cover
reached the page through the new signal), stepped into the Theme row and walked
it in both directions, stepped out, and quit **through the Quit row**, which is
the table's own action running: exit 0, four clean lines in the log, zero late
audio blocks.

`core/audio/engine.py` is the only file below the seam this batch touched, and
what it touched is one `except` clause. `wave.py`, `item_column.py`,
`now_playing.py`, `transport.py`, `crossbar.py`, `chrome.py`, `sounds.py`,
`motion.py` and every module in `core/` besides that one are untouched.

Not done: the `.exe`, for the same reason as Batches 9, 10, 12 and 13 — nothing
here changes what PyInstaller reads. **Batch 15 owns the release rebuild**, and
it is the batch that changes the build again.

### Batch 15 — The download story ✅ *(all but the release upload)*

Everything between "the code is fine" and "a stranger can download this and run
it".

- [x] An icon, generated at build time from `theme.py`
- [x] `build_exe.py` smoke-tests the exe it just built
- [x] `README.md` — a Download section, and the SmartScreen warning explained
- [x] `docs/RELEASING.md` — the checklist
- [x] Rebuild the exe (current as of Batch 11, but 12–15 change the build again)
- [x] Tag and push — `v1.1.0` on `31a08af`, cut 2026-08-05 when it was asked for
- [ ] Attach the zip and publish the GitHub release *(browser job; no `gh` here)*
- [x] **Beyond the original list:** the desktop shortcut gets the icon too, and
      the README's CI badge pointed at a repo that does not exist

**Generate the `.ico` rather than checking one in.** The app has no icon
anywhere — not in the build, not in the shortcut, which admits as much in a
comment. Drawing it at build time from `theme.py`'s own colours keeps the
project's standing streak of synthesizing assets in code rather than shipping
binaries (which is why there are no `.wav` files for the UI sounds), and it
means the icon cannot drift from the palette it came from.

**The smoke test is the one failure this build can actually have.**
`build_exe.py` currently ends by printing *"Run it once before shipping it — a
missing DLL only shows up then"* and automating nothing. libsndfile and PortAudio
are pulled in by `--collect-binaries` because nothing in the bytecode points at
them; if that ever stops working the build still succeeds and the exe dies on
first import. Launch it offscreen, confirm it starts and exits 0.

**The README's Download section is not optional politeness.** An unsigned exe
downloaded from the internet gets "Windows protected your PC" from SmartScreen,
and the most likely outcome of a stranger downloading this zip today is that
they don't run it. Say what the warning is, why it appears (no code-signing
certificate — they cost money and this is a novelty app), and what to click.
Distribution was settled with the user as **GitHub Release + the zip**: no
installer, no PyPI, no winget. Those were considered — an Inno Setup installer
gets a Start-menu entry and an uninstaller but still trips SmartScreen, PyPI
serves developers and not the person who wants an app, and winget's community
repo effectively expects a signed installer.

`docs/RELEASING.md` is where the local-only steps live, and it exists because CI
deliberately doesn't run them: bump `__version__`, pytest, **the shell harness
locally** (the only `ui/` coverage there is), render the screens, build,
smoke-test, tag, push the tag, attach the zip.

---

**The remote already existed, which the plan above did not know.** Batches 12
and 13 both say "there is no GitHub remote until Batch 15" and CI "has never
run". `origin` is `github.com/BadrAlDhaibani/mp3-player`, `main` is pushed and up
to date, and the workflow has therefore been running for some time. What had
*not* been checked is the README's badge, which pointed at
`badraldhaibani/xmb-player` — a different repo name, so the badge on the front
page of the project was a 404 rendering as a broken image. Fixed. **This is the
fifth time a claim in this file has been wrong about something outside the
source, and it was again settled by looking rather than by reading.**

**The smoke test does not run offscreen, and the brief above says it should.**
This is the batch's one substantive departure and the runtime is what settled
it, exactly as in Batch 13. Under `QT_QPA_PLATFORM=offscreen` the app has no
window handle, so there is nothing to send `WM_CLOSE` to: measured, a `taskkill
/T` is ignored entirely and the only way to end the process is `/F`, which
throws away the exit code and the shutdown path together — i.e. precisely the
half worth checking. On the real platform the same close lands in **0.3 s with
exit 0 and a `settings.json` written**, which proves `aboutToQuit` fired and
`controller.shutdown()` ran. So a window appears for a few seconds during a
build, and that is the price of the check being worth anything. `%APPDATA%` is
redirected at a temp directory throughout, because a build step that quietly
rewrites your saved music folder is a worse bug than the one it is hunting.

Note what the smoke test actually waits for: the `stream open:` line in the log,
which only exists because of Batch 13. Before that batch there was nothing to
watch for and the check would have had to be a sleep. **A build that fails it is
not zipped**, because an archive sitting next to an error message is an archive
that eventually gets uploaded anyway.

**The icon is drawn rather than checked in**, which keeps the standing streak —
there are no `.wav` files for the UI sounds either — and means it cannot drift
from the palette. `tools/make_icon.py` draws the crossbar itself: the rule, the
column, the selection where they cross, four neighbours, and the window's own
top-lit gradient behind it, all off `theme.py` constants including
`CROSSBAR_Y_RATIO`. Seven sizes, each **drawn at its own size and never
downscaled** — the detail here is three hairlines, which is the thing that
survives downscaling worst.

**The renders found two bugs, for the sixth batch running, and one of them was
Batch 5's bug again.** The first draft built the glow the way Batch 5's first
draft did — a stack of translucent rounded rects — and it came out as visible
concentric rings, because overlapping fills accumulate alpha and step at every
edge. That is the third time this project has drawn a border and called it a
glow. One `QRadialGradient` fixes it and is less code. The second was
arithmetic nobody would have caught by reading: the neighbour dots were placed
three plates from a centre that sits at 0.42 of the width, so the right-hand one
was drawn hanging half off the tile. Both were obvious in one PNG and invisible
to everything else.

**Then `write_ico` segfaulted, and the crash was two lines from the cause.**
`QBuffer(QByteArray())` hands the C++ side a pointer to a Python temporary that
is then collected, and the process dies inside `image.save()` — not an
exception, no traceback, and not on the line that looks wrong. Naming the
`QByteArray` in a local is the whole fix. It is a decisions-log row because the
same shape will recur anywhere a Qt object is constructed from an expression.

**And the icon was verified against the artifact rather than the build log.**
PyInstaller prints `Copying icon to EXE`, which proves it read the file and
nothing about whether Windows can. Reading the `RT_ICON` resources back out of
the finished exe does: seven entries, byte-identical payloads, all seven
decoding. That is Batch 11's missing-licence lesson generalised — the build log
is a claim, the artifact is the evidence — and it earned its keep on the way
past, because `System.Drawing.Icon` had already been observed returning 128x128
when asked for 256. That is a documented GDI+ limitation and not a defect in the
file, which is exactly the sort of thing a second parser tells you and a first
one cannot.

Also landed: the desktop shortcut gets the icon, which the audit's own wording
asked for ("no icon anywhere — not in the build, **not in the shortcut**, which
admits as much in a comment"). It is written to `%LOCALAPPDATA%/XMBPlayer/`
rather than into the repo, because `build_exe.py` empties both `build/` and
`dist/` and a shortcut pointing at a file the next build deletes is worse than
no icon. The generation is best-effort and **the fallback was tested by breaking
it** — an untested fallback is the exact class of bug Batch 14 spent a batch
removing.

Verified: **256 tests green** (unchanged, and unchanged is right — `tests/` is
core-only and every line of this batch is a tool, a doc or a build step).
`tools/shell_harness.py` **294/294** on the first run, with the known WASAPI
flake passing; 8 new, and they are in the harness rather than in `tests/` because
the icon is Qt and that suite needs no display. They cover every size drawing,
the crossing being the anchor accent, the corner being transparent, and the ICO
container's own arithmetic — the header, every entry's offset landing inside the
file, the entries being contiguous, and 256 being stored as 0 because the field
is one byte. `ruff check .` and `mypy` clean. Built the exe (150 MB unpacked,
60 MB zipped, 71 s): the smoke test passed inside the build, the file properties
read `1.1.0` / `XMB Player` / the GPL line, `LICENSE`, `THIRD_PARTY_NOTICES.md`
and `licenses/` are at the top of the app folder, libsndfile's `COPYING` is still
in the zip, and all seven icon sizes came back out of the binary.

**The release was held back one session and then cut.** At the end of the batch
itself it was decided with the user rather than skipped — pushing a tag is an
outward-facing act that was not authorised then. **In the following session it
was, and step 6 ran: `v1.1.0` is an annotated tag on `31a08af`, pushed to
`origin`.**

Which commit to tag was the only question worth asking, and it was answered by
looking rather than by the log. `31a08af` is dated two days after the build, so
"tag the commit that was built" needed checking: nothing under `mp3player/` is
newer than the exe's mtime, and the only files touched afterwards are
`tools/shell_harness.py` and `docs/RELEASING.md`, neither of which PyInstaller
reads. So `HEAD` *is* the built tree. **The build date being later than the
commit date is not evidence of anything on its own** — a batch whose whole diff
is docs and tools will always look like that.

Steps 1–5 were re-run rather than taken on trust, which is the point of a
checklist that lives in a file: ruff and mypy clean, **256 tests**,
`tools/shell_harness.py` **294/294 with the flake passing**.

**Still not done: step 7.** `gh` is not installed on this machine, so attaching a
60 MB zip is a browser job — draft against the tag and attach
`dist/XMB-Player-1.1.0-windows.zip`. The old `v1` tag stays where it is, marking
Batch 7's code.

---

### Batch 16 — The crackle ✅

Not on any roadmap. The user reported occasional pops, worse at fullscreen and
present even with the app idle, and asked for it to be dug into.

- [x] Instrument the callback: headroom, render time, pre-clip peak, audio lost
- [x] `sys.setswitchinterval(0.001)` and an explicit output latency
- [x] Cache the window gradient and the wave's band mask
- [x] Core tests, harness checks, renders, a real run

**`xruns` had been lying by omission since Batch 2.** Every session in the log
ends `0 late audio block(s)`, including every session that crackled. PortAudio's
status flag is set by the host layer and WASAPI's does not set it for this
failure, so the app's only audio-health number was structurally incapable of
seeing the fault. That is the first thing to know about this batch: **the
instrument was the bug's best hiding place.**

**The first replacement instrument was also wrong, and the control run is what
said so.** Counting over-long gaps between callbacks gave 297 late in 45 s
fullscreen — and 267 with the wave timer *stopped*, which reads as "the wave has
nothing to do with it". Both numbers are noise: 512 frames against WASAPI's
480-frame period forces a double-length gap six times a second by construction,
on an idle machine, forever. A metric with a structural floor does not fail
loudly; it produces plausible numbers that point somewhere else. It is a
convention now, and the wave was cleared of a charge it was not guilty of.

**What the fault actually is: the audio callback is Python.** It takes the GIL
every 10.7 ms, and at sounddevice's default `latency='high'` — which reads back
as a comfortable-sounding 22 ms — it was entering with **2.0 ms** of headroom at
the 1st percentile. Past that the block is not rendered late, it is never
rendered. Settled on a bare stream with no Qt anywhere, doing nothing but
zero-filling, with one busy Python thread beside it: **83.9 callbacks a second
against a nominal 93.75**, i.e. a tenth of the audio absent, and not one
PortAudio flag. Thirty lines in the scratchpad, and it is the same lesson as
Batches 13 and 15 — check the runtime, not the file.

Two levers, and either alone restores every block: `sys.setswitchinterval(0.001)`
(the default 5 ms is how long a paint may keep the GIL after the audio thread has
asked for it) and `SUGGESTED_LATENCY_S = 0.035`, which reads back as 45.7 ms.
Both, because the switch interval fixes the average and the buffer fixes the
worst case. The latency ceiling was agreed with the user beforehand at ~45 ms.

Measured on this machine, fullscreen at 1920x1080, a track playing, `Mono`:

| | audio lost / 10 s | least headroom | `xruns` |
|---|---|---|---|
| before, idle | **57–164 ms** | 2.0 ms | 0 |
| before, hammering arrow keys | **175–1638 ms** | 2.0 ms | 0 |
| after, idle | **0** | 10.7 ms | 0 |
| after, hammering arrow keys | 0, after the first window | 10.7 ms | 0 |

The one residual is the first ten-second window under load — 49 ms in one run,
285 ms in another, nothing in the fifty seconds after it. That is
`play_index`'s **synchronous decode**, which is a decisions-log row of its own
("decode stays on the UI thread in v1"), lands during a track change when the
music is faded out anyway, and is left where it is rather than quietly turned
into a threading batch.

**The UI half was worth doing and was not what fixed it**, which is worth
recording in that order. The window gradient was being re-evaluated over ~1.8 M
pixels 21 times a second to produce the same pixels, and the wave's band mask
likewise over its buffer; both are functions of size alone and are now built once
and blitted. That took the wave's frame from 5.1–5.8 ms to 4.61 ms at fullscreen.
The audio was already clean before it. **The two changes that were allowed to
cost something visible — dropping the wave's frame rate, capping the buffer's
height — were therefore not made at all**, which is the right answer to "only if
I can't tell": there was nothing left to buy.

Both caches are asserted **byte-identical** rather than looked at: 0 differing
pixels at 720x480, 980x640 and 1920x1080, in the harness. That is a new
convention, and it does not displace the render — it is that where the claim is
"nothing changed", an assertion is the stronger instrument and one was available.

Verified: **263 tests green** (7 new, core-only as the convention requires — the
allocation-free peak against the obvious spelling and against an empty block, a
quiet mix never reporting over 1.0, the peak being read before the clip and being
a running maximum, the log gate, and the stats fold — which has to take the *min*
of one field and the max of the others, and must be a no-op against `NO_STATS` or
a caller draining every poll reports infinite headroom). `tools/shell_harness.py`
**300/300** on the first run with the known WASAPI flake passing; 6 new, and they
are the byte-identical claims. `ruff check .` and `mypy` clean. Rendered Music at
1920x1080, Now Playing at 720x480 and Settings at 980x640, all at three speeds,
and looked at them: nothing moved. Ran the real entrypoint with a mapped window —
exit 0, settings written, `45.7 ms` in the log, four clean lines and no warnings.

Not done: the `.exe`, for the same reason as Batches 9, 10, 12, 13 and 14 —
nothing here changes what PyInstaller reads. **The release upload is still open**
and is still the only thing standing between the repo and a download.

---

## Running it

```bash
# deps (already installed in venv/)
venv/Scripts/python.exe -m pip install -r requirements.txt

# the app
run.bat                          # console: tracebacks and prints land here
venv/Scripts/python.exe -m mp3player.app
powershell -ExecutionPolicy Bypass -File tools/make_shortcut.ps1   # desktop .lnk

# the standalone build -- distribution only, never the edit-run loop.
# Generates the icon and the version resource, builds, then LAUNCHES the exe and
# closes it (a window appears for a few seconds; that is the test). A build that
# fails that is not zipped. See docs/RELEASING.md for the whole checklist.
venv/Scripts/python.exe tools/build_exe.py         # -> dist/XMB Player/ + a zip
venv/Scripts/python.exe tools/build_exe.py --skip-smoke   # no audio device only

# the icon, drawn from theme.py. `--preview` is the one to look at.
venv/Scripts/python.exe tools/make_icon.py out.ico
venv/Scripts/python.exe tools/make_icon.py out.png --preview   # all 7 sizes

# the three checks CI runs, in the order it runs them. All configured in
# pyproject.toml, which also says why each disabled rule is disabled.
venv/Scripts/python.exe -m ruff check .
venv/Scripts/python.exe -m ruff check . --fix     # the mechanical half
venv/Scripts/python.exe -m mypy
venv/Scripts/python.exe -m pytest

# `ruff format` is NOT part of this -- see the decisions log. It is not wrong,
# it just wants to rejoin ~290 hand-wrapped lines to say the same things.

# the Batch 4 harness -- drives the real widgets offscreen, no display
venv/Scripts/python.exe tools/shell_harness.py

# Known flake, not a regression: `...resuming where it left off` fails maybe one
# run in five at 0.00s. It is a real WASAPI reopen racing the position read, it
# predates Batch 9, and it passes on a re-run. 293/294 with *that* line failing
# is the known one; anything else failing is yours.
#
# It writes its log to a temp file, not to yours -- and its crash-probe section
# prints a real traceback to stderr on purpose. Both are meant to be there.

# look at a screen instead of asserting on it -- real platform, real fonts
venv/Scripts/python.exe tools/render.py out.png                     # Music, 3 speeds
venv/Scripts/python.exe tools/render.py out.png --what now --size 720x480
venv/Scripts/python.exe tools/render.py out.png --what settings --speed 1.30
venv/Scripts/python.exe tools/render.py out.png --theme all         # 5 palettes x 3 speeds
venv/Scripts/python.exe tools/render.py out.png --theme Ember --theme Mono
venv/Scripts/python.exe tools/render.py out.png --what settings --select 2 --step
venv/Scripts/python.exe tools/render.py out.png --status "Could not save settings"

# the four that exist for shots that end up on a page rather than in front of
# you -- the README's screenshots are these. `--track` because most of a real
# library is untagged and draws the note glyph, `--volume` because `VOL 0%` with
# the slider pinned left reads as a broken build.
venv/Scripts/python.exe tools/render.py out.png --no-caption --across
venv/Scripts/python.exe tools/render.py out.png --what now --track 1 --volume 0.7

# the Batch 6 harness -- audition the UI sounds; `m` is the one that matters
venv/Scripts/python.exe tools/sfx_harness.py
venv/Scripts/python.exe tools/sfx_harness.py "song.mp3"

# look at an animation instead of watching it -- real platform, driven clock
venv/Scripts/python.exe tools/filmstrip.py out.png                # a row step
venv/Scripts/python.exe tools/filmstrip.py out.png --what appear --ms 220

# the Batch 2 harness -- keyboard-driven audio engine, no Qt
venv/Scripts/python.exe tools/engine_harness.py            # the saved folder
venv/Scripts/python.exe tools/engine_harness.py "path/to/folder"
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

**These are host-API latencies, not what the app asks for.** Batch 16 stopped
taking PortAudio's `latency='high'` default: it reads back as the 22 ms above and
leaves a *Python* callback with 2.0 ms of headroom at the 1st percentile, which
is not enough to survive the paint path holding the GIL. `SUGGESTED_LATENCY_S`
is 0.035 and reads back as **45.7 ms**. The 22 ms row stands as the measurement
it always was — WASAPI against MME's 186 — and is no longer the number the app
runs at.

Callback headroom on this machine, blocksize 512, 48 kHz, measured over 8 s with
one busy Python thread alongside (`outputBufferDacTime - currentTime`):

| suggested | reported | p1 headroom | callbacks/s (nominal 93.75) |
|---|---|---|---|
| `'high'` (the old default) | 22.0 ms | 2.0 ms | **83.9** |
| `'high'` + 1 ms switch interval | 22.0 ms | 2.0 ms | 94.0 |
| 0.035 | **45.7 ms** | 17.7 ms | 94.0 |
| 0.035 + 1 ms switch interval | 45.7 ms | 16.7 ms | 94.0 |

A buffer *fills* over a stream's first few callbacks — 0, then one block, then
two — so anything measuring minimum headroom has to wait for it. `AudioEngine`
latches on half the requested latency; the first version of that check reported
`0.0 ms` for every session, forever, and was reporting the prefill.
