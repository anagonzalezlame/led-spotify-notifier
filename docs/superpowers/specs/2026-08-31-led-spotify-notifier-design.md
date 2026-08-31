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
ID). Only re-render and re-send to the panel when this tuple changes from
the last sent state — avoids redundant BLE writes on every poll.

### Rendering

- **Spotify logo**: hand-drawn with Pillow primitives (green filled circle +
  3 white arcs via `ImageDraw.arc`), ~14x14px, anchored left. A dimmed/grayscale
  variant is used for the idle state.
- **Marquee text**: "Song — Artist" rendered at full width to an off-screen
  canvas, then sampled through a sliding window to produce scroll frames,
  matching the frame-stitching approach `led-panel-prompt` already uses for
  animations. Assembled into a looping animated GIF (`loop=0`) and sent to the
  panel once per track change — the panel loops it natively, no repeated sends
  needed while the same track keeps playing.
- **Idle state** (nothing playing): single static frame, dimmed logo + literal
  text "Spotify".

### Sending to the panel

Identical pattern to the sibling scripts: `pypixelcolor.Client(LED_ADDRESS)`,
`connect()` / `send_image()` / `disconnect()` in a `try/finally`.

### Error handling

Matches `gmail_notifier.py`'s style: each poll iteration wraps the Last.fm API
call and the panel send in their own `try/except`, logs a timestamped message on
failure, and continues the loop rather than crashing.

### Testing

No automated test suite (matches both sibling projects — they have none; this
depends on live Spotify playback state and real BLE hardware). Verified manually:
render the logo and a sample marquee frame to a PNG/GIF and inspect visually
before wiring into the live poll loop; then run against real playback and confirm
the panel updates on track change and returns to idle when paused.

## Out of scope

- Auto-switching or merging with `led-gmail-notifier` — explicitly rejected by
  the user; they stay separate, manually toggled scripts.
- Album art rendering — logo-only, not the track's actual cover image.
- Any web UI — this is a headless background loop, not a Flask app.
