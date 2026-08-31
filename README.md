# 🎵 LED Spotify Notifier

A tiny local background script: polls Last.fm (which you scrobble your Spotify
listening to) for what you're currently playing and shows a pixel-art Spotify
logo plus a scrolling "Song - Artist" marquee on a 96x16 BLE LED matrix panel.
Falls back to a dim idle screen when nothing is playing.

Runs standalone — it shares the panel with `led-gmail-notifier` but the two are
never run at the same time; stop one before starting the other.

## Setup

```bash
pip install pillow
```

1. Create an API key at [last.fm/api/account/create](https://www.last.fm/api/account/create)
   (make sure Spotify scrobbling is connected and active on your Last.fm account).
2. Copy `.env.example` to `.env` and fill in `LASTFM_API_KEY`,
   `LASTFM_USERNAME`, and `LED_ADDRESS` (same BLE MAC address used by the
   other panel scripts).
3. Run it:

```bash
python spotify_notifier.py
```

## Notes

- Polls Last.fm every 5 seconds to detect track changes; drives the marquee
  scroll itself by sending the panel a new PNG frame roughly every 300ms
  over a single Bluetooth connection kept open for the whole run (the
  panel's own GIF-looping doesn't animate partial-frame content like
  scrolling text, so this app-driven approach replaced it; 300ms/6px-per-step
  was calibrated live against the real panel — faster intervals left it
  stuck on a stale frame with no error raised).
- Depends on Last.fm's "now playing" scrobble status staying live — if
  scrobbling lags or disconnects, the panel falls back to idle.
- No automated tests — verified manually against real Spotify playback and
  the physical panel.
