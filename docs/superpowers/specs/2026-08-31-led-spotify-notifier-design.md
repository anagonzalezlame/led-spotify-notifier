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

- `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` — from a Spotify Developer Dashboard app.
- `SPOTIFY_REDIRECT_URI` — e.g. `http://127.0.0.1:8888/callback`, must match the app's
  registered redirect URI.
- `LED_ADDRESS` — same BLE MAC address used by the sibling projects.

`.env.example` and a `README.md` follow the same format as the sibling projects.

### Authentication

Uses the `spotipy` library (`pip install spotipy`) instead of hand-rolled OAuth:
`spotipy.oauth2.SpotifyOAuth` with scope `user-read-currently-playing
user-read-playback-state`. On first run it opens the browser for the user to
authorize; spotipy caches the resulting refresh token to a local cache file
(`.cache-spotify`, gitignored) so subsequent runs don't prompt again.

### Poll loop

Every 5 seconds, call `sp.current_playback()`. Track identity is the tuple
`(track_id, is_playing)`. Only re-render and re-send to the panel when this tuple
changes from the last sent state — avoids redundant BLE writes on every poll.

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

Matches `gmail_notifier.py`'s style: each poll iteration wraps the Spotify API
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
