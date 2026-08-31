# LED Spotify Notifier — Design

## Purpose

A standalone Python script, sibling to `led-panel-prompt` and `led-gmail-notifier`,
that shows what's currently playing on Spotify on the 96x16 BLE LED matrix panel:
a small pixel-art Spotify logo plus a scrolling "Song — Artist" marquee.

It runs independently from `led-gmail-notifier` — the panel can only display one
thing at a time over BLE, and the user runs at most one of these scripts at a time
manually (no auto-switching/merging between them).

## Components

### Config (`.env`)

- `LASTFM_API_KEY` — from a Last.fm API account (read-only, no secret needed).
- `LASTFM_USERNAME` — the user's Last.fm username (must have Spotify scrobbling
  connected and already active).
- `LED_ADDRESS` — same BLE MAC address used by the sibling projects.

`.env.example` and a `README.md` follow the same format as the sibling projects.

### Data source

**Revision (2026-08-31):** switched from the Spotify Web API (OAuth) to the
Last.fm API, because the user already scrobbles her Spotify listening to
Last.fm. Last.fm's `user.getrecenttracks` method is a public read endpoint
that needs only an API key — no OAuth, no browser authorization step, no
refresh-token cache. This trades a dependency on Spotify's own developer
platform for a dependency on her Last.fm scrobbling staying connected and
live; if scrobbling ever lags or breaks, "now playing" data breaks with it,
which is an accepted tradeoff for the simpler setup.

A plain HTTP GET (via `urllib.request`, matching the pattern
`gmail_notifier.py` already uses for the Open-Meteo weather call — no new
HTTP library dependency) against
`https://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks&user=<LASTFM_USERNAME>&api_key=<LASTFM_API_KEY>&format=json&limit=1`
returns the most recent track. Its `@attr.nowplaying == "true"` marks it as
currently playing; absence of that attribute (or an empty track list) means
nothing is playing right now.

### Poll loop

Every 5 seconds, fetch the most recent track from Last.fm. Track identity is
the tuple `(track_id, is_playing)`, where `track_id` is derived from the
artist+title pair (Last.fm's public API doesn't expose Spotify's own track
ID). Only rebuild the marquee frames when this tuple changes from the last
seen state — avoids re-hitting Last.fm's rate limits and rebuilding frames
needlessly. This poll interval is independent of the panel frame-send
interval below.

**Revision (2026-08-31):** the device-side native GIF looping described in
the original "Rendering"/"Sending to the panel" design below was tested
against the real hardware and does not work for this content — see the
revision notes in those sections for what replaced it and why.

### Rendering

- **Spotify logo**: hand-drawn with Pillow primitives (green filled circle +
  3 white arcs via `ImageDraw.arc`), ~14x14px, anchored left. A dimmed/grayscale
  variant is used for the idle state.
- **Marquee text**: "Song — Artist" rendered at full width to an off-screen
  canvas, then sampled through a sliding window to produce a list of scroll
  frames (in-memory `PIL.Image` objects — no GIF file is assembled; see the
  revision note below).
- **Idle state** (nothing playing): single static frame, dimmed logo + literal
  text "Spotify".

**Revision (2026-08-31) — animated GIF looping does not work on this panel
for partial-frame content:** the original design assembled the marquee scroll
into a single looping animated GIF (`loop=0`) sent once per track change,
relying on the panel to loop it natively. Live testing on the real hardware
found this doesn't work: a 2-frame solid-color-block GIF (e.g. full red →
full blue) animates correctly, but any GIF where frames differ only in a
small region (the scrolling text against a mostly-unchanged background,
which is exactly the marquee's case) gets stuck showing a single static
frame — reproduced across frame counts (111, 23, 2), frame durations
(80ms, 500ms), and both GIF disposal modes (1 and 2), so the cause is
specific to partial-frame content, not those parameters. Static PNGs with
text (the idle screen) display correctly, so this is isolated to the
animated-GIF path specifically, not text rendering in general. No root
cause was pinned down in the device/library internals; rather than keep
guessing against live hardware, the design changed to sidestep the failure
mode entirely (see "Sending to the panel" below).

### Sending to the panel

**Revision (2026-08-31):** replaced per-call `connect()`/`send_image()`/
`disconnect()` (the original design, still used for the Task 7 hardware
smoke-test) with a **single persistent BLE connection held for the life of
the running script**, because measured on the real device: `connect()` costs
~4.5-4.8s, but `send_image()` over an already-open connection costs only
~0.1-0.15s. Reconnecting per frame is far too slow for any kind of
animation; sending repeatedly over one open connection is fast enough for
the app to drive the scroll itself.

The script connects once at startup (`pypixelcolor.Client(LED_ADDRESS).connect()`),
keeps that connection for as long as it runs, and disconnects only in a
`finally` block on shutdown (`KeyboardInterrupt`) or unrecoverable error.
Every `FRAME_INTERVAL_SECONDS`, while a track's marquee is active, the
script writes the next scroll frame to a PNG file (explicit `format="PNG"`
— see the format revision note below) and calls `device.send_image()` on
the already-open connection — this is how the "animation" actually happens:
the app drives it frame-by-frame, not the panel's own GIF looping. When
nothing is playing, the idle frame is (re)sent at the same cadence
(harmless — sending the same static image repeatedly has no visible effect
and keeps the logic uniform, avoiding a separate "don't resend if
unchanged" special case for the idle path).

**Revision (2026-08-31) — file must be saved as an explicit PNG, and the
device needs ~300ms per frame, not ~150ms:** two further hardware findings
after the persistent-connection rework first shipped, both found via live
testing with the user:

1. The reused frame file was `IMG_PATH` (`_spotify_frame.gif`, inherited
   from the original GIF-based design). `Image.save(path)` without an
   explicit `format=` infers the format from the path's extension — so
   despite containing ordinary single-frame content, it was being written
   and sent as actual GIF-format bytes, routing every send through the
   panel's GIF-slot protocol (already shown to not reliably display partial
   content). Saving explicitly as PNG (`image.save(IMG_PATH, format="PNG")`,
   or renaming the constant to a `.png` path) fixed this — text became
   visible immediately once frames were sent as real PNGs.
2. Even sending correct PNGs, `FRAME_INTERVAL_SECONDS = 0.15` was still too
   fast: the device could not keep up, and appeared to just freeze on
   whichever frame it last finished rendering while later sends piled up
   and got silently dropped/coalesced — no error was raised, so nothing in
   the code path caught this. Verified empirically: at ~1s per frame the
   panel visibly stepped through distinct scroll positions; at ~300ms per
   frame (with `SCROLL_STEP_PX` widened from 2 to 6, so a full scroll needs
   about a third as many frames) the user confirmed visible, continuous
   — if unhurried — scrolling motion. **`FRAME_INTERVAL_SECONDS = 0.3` and
   `SCROLL_STEP_PX = 6` are the calibrated values**, replacing the original
   guesses of `0.15`/`2`.

### Error handling

Two independent concerns, each handled separately:
- The Last.fm poll (every 5s) is wrapped in its own `try/except`, logs a
  timestamped message on failure, and falls back to treating the state as
  "nothing playing" rather than crashing — matches `gmail_notifier.py`'s
  style.
- Each panel `send_image()` call (every ~150ms) is wrapped in its own
  `try/except`; a failure is logged (not on every single failed frame if
  they repeat rapidly — see the plan for the exact throttling) and the loop
  continues, attempting to send again next cycle. A failure here does not
  affect Last.fm polling or the poll interval's timing.

### Testing

No automated test suite (matches both sibling projects — they have none; this
depends on live Spotify playback state and real BLE hardware). Verified
manually: render the logo and inspect visually before wiring into the live
poll loop; run against real playback and confirm the panel updates on track
change and returns to idle when paused; the app-driven frame-send approach
was chosen specifically because it was verified against the real panel after
the original GIF-looping approach was found not to work for this content
(see the revision notes above).

## Out of scope

- Auto-switching or merging with `led-gmail-notifier` — explicitly rejected by
  the user; they stay separate, manually toggled scripts.
- Album art rendering — logo-only, not the track's actual cover image.
- Any web UI — this is a headless background loop, not a Flask app.
