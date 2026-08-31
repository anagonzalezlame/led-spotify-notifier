# LED Spotify Notifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Python script that polls Last.fm (which the user already scrobbles her Spotify listening to) for the currently playing track and pushes a pixel-art Spotify logo + scrolling song/artist marquee to the 96x16 BLE LED panel, falling back to an idle screen when nothing is playing.

**Architecture:** Single-file script (`spotify_notifier.py`), mirroring the sibling `led-gmail-notifier` project: `.env`-based config, an infinite poll loop, Pillow-rendered frames, `pypixelcolor` for BLE delivery over a single persistent connection held for the script's lifetime. Track-change detection (every 5s) avoids re-hitting Last.fm needlessly; the marquee scroll is driven by the app itself, sending a new frame roughly every 150ms over that one open connection (see Revision note 2).

**Tech Stack:** Python 3.12, `urllib.request`/`urllib.parse` + `json` (stdlib, for the Last.fm API — matches `gmail_notifier.py`'s weather-call pattern), `Pillow`, `pypixelcolor`.

**Spec:** `docs/superpowers/specs/2026-08-31-led-spotify-notifier-design.md`

**Revision note 1 (2026-08-31):** Task 1 was implemented and reviewed while this plan still targeted the Spotify Web API with OAuth (`spotipy`). After Task 1 shipped, the user chose to switch the data source to Last.fm instead (she already scrobbles Spotify there), which needs only an API key — no OAuth. The spec was updated accordingly. Global Constraints and Tasks 2-3 below reflect the Last.fm version; Task 2 also carries a one-time cleanup of the now-stale Spotify-OAuth remnants Task 1 left behind (unused `spotipy` imports, `SCOPE`, `CACHE_PATH`).

**Revision note 2 (2026-08-31):** Tasks 1-7 were implemented and individually reviewed under the original design: `build_marquee_frames` + `save_marquee_gif` assembled the scroll into one looping animated GIF, sent once per track change via `send_to_panel`'s per-call `connect()`/`send_image()`/`disconnect()`. Live end-to-end testing during Task 8's hardware verification found the panel does not animate GIFs whose frames differ only in a small region (exactly the marquee's case) — confirmed across frame counts, durations, and disposal modes; see the spec's revision notes for the full diagnostic trail. Since a solid-color GIF animates fine and a static PNG with text displays fine, and since `connect()` measured ~4.5-4.8s but `send_image()` over an already-open connection measured ~0.1-0.15s, the fix is architectural: drive the scroll from the app itself, sending one PNG per frame over a single persistent connection, instead of relying on the panel to loop a GIF. This reworks Task 5 (drop `save_marquee_gif`, `build_marquee_frames` unchanged), Task 7 (replace per-call connect/disconnect with connect-once/send-many), and Task 8 (the main loop now runs two independent cadences: a 5s Last.fm poll and a ~150ms frame-send tick) — see their rewritten sections below. Tasks 1-6 needed no other changes; their other reviewed code stands.

## Global Constraints

- Panel resolution is fixed at 96x16 (`PANEL_WIDTH = 96`, `PANEL_HEIGHT = 16`) — from spec and both sibling projects.
- Last.fm poll interval is 5 seconds (`POLL_INTERVAL_SECONDS = 5`) — from spec.
- Panel frame-send interval is ~150ms (`FRAME_INTERVAL_SECONDS = 0.15`) — from spec's revision note, empirically measured against the real device.
- Data source is the Last.fm API (`user.getrecenttracks`, public, API-key only) via stdlib `urllib.request` — no OAuth, no `spotipy`, no browser authorization step — from spec.
- Track "now playing" is determined by the `@attr.nowplaying == "true"` field on the most recent track — from spec.
- The panel connection is a SINGLE persistent `pypixelcolor.Client` held for the life of the running script — never reconnect per frame — from spec's revision note 2 (measured: reconnecting costs ~4.5-4.8s per call, unusable for animation; sending over an open connection costs ~0.1-0.15s).
- No automated test suite — matches both sibling projects, which have none. Every "test" step below is a manual run + visual/console check, not pytest.
- This script runs standalone; it must NOT merge with or auto-toggle `led-gmail-notifier` — explicitly out of scope per spec.
- Single-file script style (`spotify_notifier.py`), matching `gmail_notifier.py`'s shape — no premature splitting into modules.
- Config lives in `.env` (gitignored) with a checked-in `.env.example`, matching sibling projects' format.

---

### Task 1: Project scaffolding

**Files:**
- Create: `C:\Users\Anita\Documents\led-spotify-notifier\.gitignore`
- Create: `C:\Users\Anita\Documents\led-spotify-notifier\.env.example`
- Create: `C:\Users\Anita\Documents\led-spotify-notifier\spotify_notifier.py` (skeleton: imports, constants, env loading only)

**Interfaces:**
- Consumes: nothing (first task)
- Produces: `SCRIPT_DIR: Path`, `ENV_PATH: Path`, `CACHE_PATH: Path`, `IMG_PATH: Path`, `IDLE_IMG_PATH: Path`, `PANEL_WIDTH: int`, `PANEL_HEIGHT: int`, `POLL_INTERVAL_SECONDS: int`, `load_env(path: Path) -> dict`, `_env: dict`, `LED_ADDRESS: str | None`

- [ ] **Step 1: Create `.gitignore`**

```
.env
.cache-spotify
__pycache__/
*.pyc
_spotify_frame.gif
_spotify_idle.png
```

- [ ] **Step 2: Create `.env.example`**

```
SPOTIFY_CLIENT_ID=your_client_id_here
SPOTIFY_CLIENT_SECRET=your_client_secret_here
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback
LED_ADDRESS=AA:BB:CC:DD:EE:FF
```

- [ ] **Step 3: Create `spotify_notifier.py` with the config/skeleton**

```python
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth

import pypixelcolor

SCRIPT_DIR = Path(__file__).parent
ENV_PATH = SCRIPT_DIR / ".env"
CACHE_PATH = SCRIPT_DIR / ".cache-spotify"
IMG_PATH = SCRIPT_DIR / "_spotify_frame.gif"
IDLE_IMG_PATH = SCRIPT_DIR / "_spotify_idle.png"

PANEL_WIDTH = 96
PANEL_HEIGHT = 16
POLL_INTERVAL_SECONDS = 5

LOGO_SIZE = 14
LOGO_MARGIN = 1
TEXT_START_X = LOGO_MARGIN + LOGO_SIZE + 3
MARQUEE_WIDTH = PANEL_WIDTH - TEXT_START_X

SPOTIFY_GREEN = (30, 215, 96)
DIM_GREEN = (60, 90, 70)
BG_COLOR = (0, 0, 0)
IDLE_BG_COLOR = (20, 20, 20)
TEXT_COLOR = (255, 255, 255)
IDLE_TEXT_COLOR = (90, 90, 90)

SCOPE = "user-read-currently-playing user-read-playback-state"

FRAME_DURATION_MS = 80
SCROLL_STEP_PX = 2


def load_env(path: Path) -> dict:
    env = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


_env = load_env(ENV_PATH)
LED_ADDRESS = os.environ.get("LED_ADDRESS") or _env.get("LED_ADDRESS")


if __name__ == "__main__":
    print("skeleton ok")
```

- [ ] **Step 4: Install dependencies and verify the skeleton runs**

Run: `pip install spotipy pillow` (`pypixelcolor` should already be installed from the sibling projects)
Then run: `python spotify_notifier.py`
Expected: prints `skeleton ok` with no import errors.

- [ ] **Step 5: Commit**

```bash
git add .gitignore .env.example spotify_notifier.py
git commit -m "Scaffold led-spotify-notifier project"
```

---

### Task 2: Last.fm API config + cleanup of stale Spotify-OAuth remnants

**Files:**
- Modify: `spotify_notifier.py` (remove unused `spotipy` imports/`SCOPE`/`CACHE_PATH` left over from the pre-revision Task 1; add `LASTFM_URL` constant and `import json`, `import urllib.request`, `import urllib.parse`)
- Modify: `.env.example` (replace the Spotify keys with the Last.fm ones)

**Interfaces:**
- Consumes: `_env: dict`, `SCRIPT_DIR` (Task 1)
- Produces: `LASTFM_URL: str`, `LASTFM_API_KEY: str | None`, `LASTFM_USERNAME: str | None` (module-level constants read from env, available to Task 3)

- [ ] **Step 1: Create a Last.fm API account (manual, in browser)**

Guide the user through:
1. Go to https://www.last.fm/api/account/create and log in with her Last.fm account.
2. Fill in any contact email and an application name (e.g. "LED Panel Notifier"); no callback URL is required for this use case.
3. Submit — the page shows an **API key** (and a shared secret, which this project does not need since it only reads public data).
4. Confirm her Last.fm **username** (visible in her Last.fm profile URL, `last.fm/user/<username>`) has Spotify scrobbling connected and active — check that a track she's currently playing on Spotify shows up on her Last.fm profile page as "Scrobbling now" / "Now playing" within a few seconds.

- [ ] **Step 2: Fill in `.env.example` and `.env`**

Update `.env.example` to:

```
LASTFM_API_KEY=your_api_key_here
LASTFM_USERNAME=your_lastfm_username_here
LED_ADDRESS=AA:BB:CC:DD:EE:FF
```

Then update the real `.env` (not committed) with the actual API key, username, and the `LED_ADDRESS` reused from the sibling projects' `.env`.

- [ ] **Step 3: Clean up `spotify_notifier.py`'s imports and constants**

Remove these lines (left over from before the Last.fm revision):
```python
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth

import pypixelcolor
```
Replace with:
```python
import json
import urllib.parse
import urllib.request

import pypixelcolor
```
(`pypixelcolor` is still needed for Task 7; only the Spotify-specific imports are dropped.)

Remove the now-unused `CACHE_PATH` constant and the `SCOPE` constant entirely (no OAuth, no scopes, no token cache with Last.fm).

Add, near the other constants:
```python
LASTFM_URL = "https://ws.audioscrobbler.com/2.0/"
LASTFM_API_KEY = os.environ.get("LASTFM_API_KEY") or _env.get("LASTFM_API_KEY")
LASTFM_USERNAME = os.environ.get("LASTFM_USERNAME") or _env.get("LASTFM_USERNAME")
```
(placed after the `_env = load_env(ENV_PATH)` line, same as the existing `LED_ADDRESS` constant).

- [ ] **Step 4: Verify manually**

Temporarily replace the bottom of `spotify_notifier.py`:

```python
if __name__ == "__main__":
    if not LASTFM_API_KEY or not LASTFM_USERNAME:
        print("Falta configurar .env (copia .env.example a .env y completa los datos).")
        sys.exit(1)
    params = urllib.parse.urlencode({
        "method": "user.getrecenttracks",
        "user": LASTFM_USERNAME,
        "api_key": LASTFM_API_KEY,
        "format": "json",
        "limit": 1,
    })
    with urllib.request.urlopen(f"{LASTFM_URL}?{params}", timeout=10) as resp:
        print(json.loads(resp.read()))
```

Run: `python spotify_notifier.py`
Expected: prints a JSON dict containing a `recenttracks` key with a `track` list — no import errors, no HTTP errors. If a song is currently playing on Spotify, the first track in the list has an `"@attr": {"nowplaying": "true"}` field.

- [ ] **Step 5: Commit**

```bash
git add spotify_notifier.py .env.example
git commit -m "Switch to Last.fm API config, drop Spotify OAuth remnants"
```

(Do not commit `.env` — gitignored.)

---

### Task 3: Now-playing polling wrapper

**Files:**
- Modify: `spotify_notifier.py` (add `get_now_playing`)

**Interfaces:**
- Consumes: `LASTFM_URL`, `LASTFM_API_KEY`, `LASTFM_USERNAME` (Task 2)
- Produces: `get_now_playing() -> dict | None` — returns `{"track_id": str, "title": str, "artist": str, "is_playing": bool}` or `None` if nothing is currently playing. No arguments — unlike a client-object API, each call is a self-contained HTTP request.

- [ ] **Step 1: Add `get_now_playing`**

```python
def get_now_playing() -> dict | None:
    params = urllib.parse.urlencode({
        "method": "user.getrecenttracks",
        "user": LASTFM_USERNAME,
        "api_key": LASTFM_API_KEY,
        "format": "json",
        "limit": 1,
    })
    with urllib.request.urlopen(f"{LASTFM_URL}?{params}", timeout=10) as resp:
        data = json.loads(resp.read())

    tracks = data.get("recenttracks", {}).get("track", [])
    if not tracks:
        return None
    track = tracks[0]
    if track.get("@attr", {}).get("nowplaying") != "true":
        return None

    title = track["name"]
    artist = track["artist"]["#text"]
    return {
        "track_id": f"{artist}|||{title}",
        "title": title,
        "artist": artist,
        "is_playing": True,
    }
```

- [ ] **Step 2: Verify manually against real playback**

Replace the bottom of `spotify_notifier.py`:

```python
if __name__ == "__main__":
    print(get_now_playing())
```

Run: `python spotify_notifier.py` with nothing playing on Spotify.
Expected: prints `None`.
Start playing a song on Spotify, wait a few seconds (Last.fm "now playing" usually updates within 1-5 seconds of playback starting), run again.
Expected: prints a dict with the correct `track_id`, `title`, `artist`, and `is_playing: True`. Pause the song and wait a few seconds, run again — expected `None` again (Last.fm drops the `nowplaying` flag on pause).

- [ ] **Step 3: Commit**

```bash
git add spotify_notifier.py
git commit -m "Add Last.fm now-playing polling wrapper"
```

- [ ] **Step 3: Commit**

```bash
git add spotify_notifier.py
git commit -m "Add now-playing polling wrapper"
```

---

### Task 4: Spotify logo renderer

**Files:**
- Modify: `spotify_notifier.py` (add `draw_spotify_logo`)

**Interfaces:**
- Consumes: `LOGO_SIZE`, `SPOTIFY_GREEN`, `DIM_GREEN`, `BG_COLOR`, `IDLE_BG_COLOR` (Task 1)
- Produces: `draw_spotify_logo(draw: ImageDraw.ImageDraw, x: int, y: int, size: int, circle_color: tuple, bar_color: tuple) -> None`

- [ ] **Step 1: Add `draw_spotify_logo`**

```python
def draw_spotify_logo(draw: ImageDraw.ImageDraw, x: int, y: int, size: int, circle_color: tuple, bar_color: tuple) -> None:
    draw.ellipse([x, y, x + size - 1, y + size - 1], fill=circle_color)
    cx = x + size // 2
    for i, dy in enumerate((4, 7, 10)):
        half_width = size // 2 - 2 - i
        draw.arc(
            [cx - half_width, y + dy - 3, cx + half_width, y + dy + 3],
            start=200, end=340, fill=bar_color, width=1,
        )
```

- [ ] **Step 2: Render both variants to PNG and inspect visually**

Replace the bottom of `spotify_notifier.py`:

```python
if __name__ == "__main__":
    img = Image.new("RGB", (LOGO_SIZE * 2 + 10, LOGO_SIZE + 4), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw_spotify_logo(draw, 2, 2, LOGO_SIZE, SPOTIFY_GREEN, BG_COLOR)
    draw_spotify_logo(draw, LOGO_SIZE + 8, 2, LOGO_SIZE, DIM_GREEN, IDLE_BG_COLOR)
    img.resize((img.width * 10, img.height * 10), Image.NEAREST).save(SCRIPT_DIR / "_logo_preview.png")
    print("saved _logo_preview.png")
```

Run: `python spotify_notifier.py`, then open `_logo_preview.png`.
Expected: a green circle with 3 dark curved bars on the left (active logo), and a dimmer/grayer version on the right (idle logo) — both recognizable as a small Spotify-style mark at 10x zoom. If the arcs look wrong (e.g. off-center or invisible), adjust the `dy`/`half_width` values in `draw_spotify_logo` and re-run until it reads clearly.

- [ ] **Step 3: Delete the preview file and commit**

```bash
rm _logo_preview.png
git add spotify_notifier.py
git commit -m "Add Spotify logo pixel-art renderer"
```

---

### Task 5: Marquee frame builder + GIF assembly

**Revision note (2026-08-31, see plan header "Revision note 2"):** this task's
`save_marquee_gif` (Step 2) is superseded — the animated-GIF approach doesn't
work on the real panel for this content. `save_marquee_gif` is removed as
part of Task 7's rework below. `build_marquee_frames` (Step 1) is unchanged
and still the one true frame-list producer.

**Files:**
- Modify: `spotify_notifier.py` (add `build_marquee_frames`, `save_marquee_gif`)

**Interfaces:**
- Consumes: `draw_spotify_logo(...)` (Task 4), `MARQUEE_WIDTH`, `TEXT_START_X`, `PANEL_WIDTH`, `PANEL_HEIGHT`, `TEXT_COLOR`, `BG_COLOR`, `SCROLL_STEP_PX`, `FRAME_DURATION_MS`, `IMG_PATH` (Task 1)
- Produces: `build_marquee_frames(title: str, artist: str) -> list[Image.Image]`, `save_marquee_gif(frames: list[Image.Image]) -> Path`

- [ ] **Step 1: Add `build_marquee_frames`**

```python
def build_marquee_frames(title: str, artist: str) -> list[Image.Image]:
    font = ImageFont.load_default()
    text = f"{title}  -  {artist}"
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    bbox = probe.textbbox((0, 0), text, font=font)
    text_height = bbox[3] - bbox[1]
    text_y = (PANEL_HEIGHT - text_height) // 2 - bbox[1]

    strip_width = (bbox[2] - bbox[0]) + MARQUEE_WIDTH
    strip = Image.new("RGB", (strip_width, PANEL_HEIGHT), BG_COLOR)
    ImageDraw.Draw(strip).text((MARQUEE_WIDTH, text_y), text, fill=TEXT_COLOR, font=font)

    frames = []
    for offset in range(0, strip_width, SCROLL_STEP_PX):
        window = Image.new("RGB", (MARQUEE_WIDTH, PANEL_HEIGHT), BG_COLOR)
        first_part = strip.crop((offset, 0, min(offset + MARQUEE_WIDTH, strip_width), PANEL_HEIGHT))
        window.paste(first_part, (0, 0))
        remaining = MARQUEE_WIDTH - first_part.width
        if remaining > 0:
            window.paste(strip.crop((0, 0, remaining, PANEL_HEIGHT)), (first_part.width, 0))

        frame = Image.new("RGB", (PANEL_WIDTH, PANEL_HEIGHT), BG_COLOR)
        draw_spotify_logo(ImageDraw.Draw(frame), LOGO_MARGIN, (PANEL_HEIGHT - LOGO_SIZE) // 2, LOGO_SIZE, SPOTIFY_GREEN, BG_COLOR)
        frame.paste(window, (TEXT_START_X, 0))
        frames.append(frame)
    return frames
```

- [ ] **Step 2: Add `save_marquee_gif`**

```python
def save_marquee_gif(frames: list[Image.Image]) -> Path:
    frames[0].save(
        IMG_PATH,
        save_all=True,
        append_images=frames[1:],
        duration=FRAME_DURATION_MS,
        loop=0,
        disposal=2,
    )
    return IMG_PATH
```

- [ ] **Step 3: Render a sample marquee GIF and inspect visually**

Replace the bottom of `spotify_notifier.py`:

```python
if __name__ == "__main__":
    frames = build_marquee_frames("Bohemian Rhapsody", "Queen")
    path = save_marquee_gif(frames)
    preview_frames = [f.resize((PANEL_WIDTH * 8, PANEL_HEIGHT * 8), Image.NEAREST) for f in frames]
    preview_frames[0].save(
        SCRIPT_DIR / "_marquee_preview.gif",
        save_all=True, append_images=preview_frames[1:],
        duration=FRAME_DURATION_MS, loop=0, disposal=2,
    )
    print(f"saved {path} and _marquee_preview.gif, {len(frames)} frames")
```

Run: `python spotify_notifier.py`, then open `_marquee_preview.gif` in a browser or image viewer.
Expected: the green logo stays fixed on the left; "Bohemian Rhapsody  -  Queen" scrolls smoothly right-to-left next to it, then loops back to blank and repeats seamlessly with no jump-cut or clipped text.

- [ ] **Step 4: Delete the preview file and commit**

```bash
rm _marquee_preview.gif
git add spotify_notifier.py
git commit -m "Add scrolling marquee frame builder and GIF assembly"
```

---

### Task 6: Idle frame renderer

**Files:**
- Modify: `spotify_notifier.py` (add `render_idle_frame`)

**Interfaces:**
- Consumes: `draw_spotify_logo(...)` (Task 4), `IDLE_IMG_PATH`, `IDLE_BG_COLOR`, `IDLE_TEXT_COLOR`, `DIM_GREEN`, `TEXT_START_X` (Task 1)
- Produces: `render_idle_frame() -> Path`

- [ ] **Step 1: Add `render_idle_frame`**

```python
def render_idle_frame() -> Path:
    frame = Image.new("RGB", (PANEL_WIDTH, PANEL_HEIGHT), IDLE_BG_COLOR)
    draw = ImageDraw.Draw(frame)
    draw_spotify_logo(draw, LOGO_MARGIN, (PANEL_HEIGHT - LOGO_SIZE) // 2, LOGO_SIZE, DIM_GREEN, IDLE_BG_COLOR)
    font = ImageFont.load_default()
    text = "Spotify"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_h = bbox[3] - bbox[1]
    text_y = (PANEL_HEIGHT - text_h) // 2 - bbox[1]
    draw.text((TEXT_START_X, text_y), text, fill=IDLE_TEXT_COLOR, font=font)
    frame.save(IDLE_IMG_PATH)
    return IDLE_IMG_PATH
```

- [ ] **Step 2: Render and inspect visually**

Replace the bottom of `spotify_notifier.py`:

```python
if __name__ == "__main__":
    path = render_idle_frame()
    Image.open(path).resize((PANEL_WIDTH * 8, PANEL_HEIGHT * 8), Image.NEAREST).save(SCRIPT_DIR / "_idle_preview.png")
    print(f"saved {path} and _idle_preview.png")
```

Run: `python spotify_notifier.py`, then open `_idle_preview.png`.
Expected: dim gray logo on the left, "Spotify" in muted gray text next to it, dark background — readable but clearly "off/idle" looking, distinct from the bright active state.

- [ ] **Step 3: Delete the preview file and commit**

```bash
rm _idle_preview.png
git add spotify_notifier.py
git commit -m "Add idle frame renderer"
```

---

### Task 7 (REWORKED 2026-08-31): Persistent panel connection

**What changed and why:** the original Task 7 (`send_to_panel(frame_path, led_address)`,
connecting and disconnecting on every single call) is superseded. Measured
against the real device: `connect()` costs ~4.5-4.8s, `send_image()` over an
already-open connection costs ~0.1-0.15s. Reconnecting per frame made any
kind of animation impossibly slow; this rework switches to one persistent
connection, held for the script's whole run, with many fast sends over it.
The original Task 7 code already shipped and was reviewed — this replaces
it outright (`send_to_panel` is removed, not kept alongside the new
functions) — and also removes Task 5's now-dead `save_marquee_gif` (the
GIF-looping approach it supported doesn't work on this panel; see the
spec's revision notes).

**Files:**
- Modify: `spotify_notifier.py` (remove `send_to_panel` and `save_marquee_gif`; add `connect_panel`, `send_frame`)

**Interfaces:**
- Consumes: `LED_ADDRESS: str | None` (Task 1), `IMG_PATH: Path` (Task 1)
- Produces: `connect_panel(led_address: str) -> pypixelcolor.Client`, `send_frame(device: pypixelcolor.Client, image: Image.Image) -> None`

- [ ] **Step 1: Remove `send_to_panel` and `save_marquee_gif`**

Delete both functions entirely from `spotify_notifier.py`. Nothing else in the
file should reference either name afterward (Task 8's rework, next, is what
replaces their call sites).

- [ ] **Step 2: Add `connect_panel` and `send_frame`**

```python
def connect_panel(led_address: str) -> pypixelcolor.Client:
    device = pypixelcolor.Client(led_address)
    device.connect()
    return device


def send_frame(device: pypixelcolor.Client, image: Image.Image) -> None:
    image.save(IMG_PATH)
    device.send_image(str(IMG_PATH))
```

`send_frame` always writes to the same reused `IMG_PATH` file (a PNG,
despite the `.gif`-suggesting name inherited from Task 1's constant — the
file extension pypixelcolor sees no longer matters since we always send a
single static frame now, never a multi-frame animation) rather than a fresh
file per call, since we're sending many times per second and don't need to
keep history.

- [ ] **Step 3: Verify against the real panel**

Make sure the LED panel is powered on and within BLE range, and that no other script (`led-gmail-notifier`, `led-panel-prompt`) is currently connected to it. Replace the bottom of `spotify_notifier.py`:

```python
if __name__ == "__main__":
    if not LED_ADDRESS:
        print("Falta LED_ADDRESS en .env")
        sys.exit(1)
    device = connect_panel(LED_ADDRESS)
    try:
        send_frame(device, Image.open(render_idle_frame()))
        print("enviado al panel")
    finally:
        device.disconnect()
```

Run: `python spotify_notifier.py`
Expected: prints "enviado al panel" and the physical panel updates to show the dim idle logo + "Spotify" text — same visible result as the original Task 7, just via the new connect-once/send-once/disconnect path.

- [ ] **Step 4: Commit**

```bash
git add spotify_notifier.py
git commit -m "Rework panel sending to a single persistent connection"
```

---

### Task 8 (REWORKED 2026-08-31): Main loop — two independent cadences

**What changed and why:** the original Task 8 (below, for the historical
record, was already implemented/reviewed) sent one static image or one
looping GIF per track change, on a single 5s cadence. Since GIF looping
doesn't animate on this panel (see Task 7's rework and the spec's revision
notes), the scroll now has to be driven by the app itself: `main()` runs
two independent cadences on one `while True` loop — a 5s Last.fm poll
(unchanged interval) and a ~150ms panel frame-send tick (new) — sharing a
single persistent panel connection from Task 7's rework.

**Files:**
- Modify: `spotify_notifier.py` (add `FRAME_INTERVAL_SECONDS` constant, rewrite `main`, rewrite the final `if __name__ == "__main__":` block)

**Interfaces:**
- Consumes: `get_now_playing() -> dict | None` (Task 3), `build_marquee_frames(title, artist) -> list[Image.Image]` (Task 5), `render_idle_frame() -> Path` (Task 6), `connect_panel(led_address) -> pypixelcolor.Client` and `send_frame(device, image) -> None` (Task 7 rework), `LED_ADDRESS`, `LASTFM_API_KEY`, `LASTFM_USERNAME`, `POLL_INTERVAL_SECONDS` (Task 1/2)
- Produces: `main() -> None`, `FRAME_INTERVAL_SECONDS: float` (entry point and a new module constant; nothing downstream consumes either)

- [ ] **Step 1: Add the `FRAME_INTERVAL_SECONDS` constant**

Add near `POLL_INTERVAL_SECONDS` (Task 1's constants block):

```python
FRAME_INTERVAL_SECONDS = 0.15
```

- [ ] **Step 2: Replace `main` and the final entry point**

Remove the old `main()` entirely (shown further below, in the original
Task 8 section, for reference only — do not keep both versions) and
replace it and the `if __name__ == "__main__":` block with:

```python
def main() -> None:
    if not LED_ADDRESS:
        print("Falta configurar LED_ADDRESS en .env")
        sys.exit(1)
    if not LASTFM_API_KEY or not LASTFM_USERNAME:
        print("Falta configurar LASTFM_API_KEY / LASTFM_USERNAME en .env")
        sys.exit(1)

    try:
        device = connect_panel(LED_ADDRESS)
    except Exception as e:
        print(f"[{datetime.now()}] Error conectando al panel: {e}")
        sys.exit(1)

    print(
        f"[{datetime.now()}] Last.fm -> LED panel notifier iniciado. "
        f"Consultando cada {POLL_INTERVAL_SECONDS}s, panel cada {FRAME_INTERVAL_SECONDS}s."
    )

    last_state = None  # (track_id, is_playing) or (None, False)
    last_poll = 0.0
    frames = [Image.open(render_idle_frame())]
    frame_index = 0
    panel_error_active = False

    try:
        while True:
            now = time.monotonic()

            if now - last_poll >= POLL_INTERVAL_SECONDS:
                last_poll = now
                try:
                    now_playing = get_now_playing()
                except Exception as e:
                    print(f"[{datetime.now()}] Error consultando Last.fm: {e}")
                    now_playing = None

                if now_playing and now_playing["is_playing"]:
                    state = (now_playing["track_id"], True)
                else:
                    state = (None, False)

                if state != last_state:
                    print(f"[{datetime.now()}] Cambio de estado: {state}")
                    if state[1]:
                        frames = build_marquee_frames(now_playing["title"], now_playing["artist"])
                    else:
                        frames = [Image.open(render_idle_frame())]
                    frame_index = 0
                    last_state = state

            try:
                send_frame(device, frames[frame_index])
                if panel_error_active:
                    print(f"[{datetime.now()}] Panel: conexion recuperada.")
                    panel_error_active = False
            except Exception as e:
                if not panel_error_active:
                    print(f"[{datetime.now()}] Error enviando al panel: {e}")
                    panel_error_active = True

            frame_index = (frame_index + 1) % len(frames)
            time.sleep(FRAME_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nDetenido.")
    finally:
        device.disconnect()


if __name__ == "__main__":
    main()
```

Note the structural change from the original: `KeyboardInterrupt` handling
and `device.disconnect()` both moved INSIDE `main()` (a `try/except
KeyboardInterrupt` wrapping the loop, with `finally: device.disconnect()`
below it) instead of wrapping `main()` from the `if __name__` block — this
is required now so the persistent connection is always cleanly closed on
exit, not just on normal completion (which never happens for an infinite
loop anyway). `main()` itself now owns its full lifecycle.

Also note the panel-send error handling now throttles: it only prints on
the transition into a failing state and the transition back to success
(via the `panel_error_active` flag), rather than once per failed send —
at a ~150ms cadence, logging every single failure would spam the console
during any real outage.

- [ ] **Step 3: Verify the full end-to-end flow manually**

Run: `python spotify_notifier.py`.
Expected sequence, checked against the real panel:
1. With nothing playing, panel shows the idle screen within ~5s.
2. Start playing a song — panel switches to the marquee within ~5s, and this
   time the text should actually be seen **scrolling smoothly** right-to-left
   (the whole point of this rework) — watch for at least one full scroll
   cycle. Console should show exactly one "Cambio de estado" line for this
   transition, not one per frame-send.
3. Pause the song — panel switches back to idle within ~5s.
4. Skip to a different track while playing — panel updates to the new
   scrolling marquee text within ~5s.
5. Turn off the panel's Bluetooth (or move it out of range) — console prints
   exactly one "Error enviando al panel" line (not one every ~150ms), the
   loop keeps running (does not crash), and if the panel comes back in range
   the console prints "Panel: conexion recuperada." and frames resume.

- [ ] **Step 4: Commit**

```bash
git add spotify_notifier.py
git commit -m "Rework main loop to drive marquee scrolling with two independent cadences"
```

---

<details>
<summary>Original Task 8 (superseded 2026-08-31, kept for history only — do not implement)</summary>

**Files:**
- Modify: `spotify_notifier.py` (add `main`, final `if __name__ == "__main__":` block)

**Interfaces:**
- Consumes: `get_now_playing() -> dict | None` (Task 3), `build_marquee_frames(title, artist) -> list[Image.Image]` and `save_marquee_gif(frames) -> Path` (Task 5), `render_idle_frame() -> Path` (Task 6), `send_to_panel(frame_path, led_address) -> None` (Task 7), `LED_ADDRESS`, `POLL_INTERVAL_SECONDS` (Task 1)
- Produces: `main() -> None` (entry point; nothing downstream consumes this)

```python
def main() -> None:
    if not LED_ADDRESS:
        print("Falta configurar LED_ADDRESS en .env")
        sys.exit(1)
    if not LASTFM_API_KEY or not LASTFM_USERNAME:
        print("Falta configurar LASTFM_API_KEY / LASTFM_USERNAME en .env")
        sys.exit(1)

    print(f"[{datetime.now()}] Last.fm -> LED panel notifier iniciado. Consultando cada {POLL_INTERVAL_SECONDS}s.")

    last_state = None  # (track_id, is_playing) or (None, False)

    while True:
        try:
            now_playing = get_now_playing()
        except Exception as e:
            print(f"[{datetime.now()}] Error consultando Last.fm: {e}")
            now_playing = None

        if now_playing and now_playing["is_playing"]:
            state = (now_playing["track_id"], True)
        else:
            state = (None, False)

        if state != last_state:
            print(f"[{datetime.now()}] Cambio de estado: {state}")
            try:
                if state[1]:
                    frames = build_marquee_frames(now_playing["title"], now_playing["artist"])
                    frame_path = save_marquee_gif(frames)
                else:
                    frame_path = render_idle_frame()
                send_to_panel(frame_path, LED_ADDRESS)
            except Exception as e:
                print(f"[{datetime.now()}] Error enviando al panel: {e}")
            else:
                last_state = state

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nDetenido.")
```

</details>

---

### Task 9: README and final docs

**Files:**
- Create: `C:\Users\Anita\Documents\led-spotify-notifier\README.md`

**Interfaces:**
- Consumes: nothing (documentation only)
- Produces: nothing (documentation only)

- [ ] **Step 1: Write `README.md`**

```markdown
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
  scroll itself by sending the panel a new frame roughly every 150ms over a
  single Bluetooth connection kept open for the whole run (the panel's own
  GIF-looping doesn't animate partial-frame content like scrolling text, so
  this app-driven approach replaced it).
- Depends on Last.fm's "now playing" scrobble status staying live — if
  scrobbling lags or disconnects, the panel falls back to idle.
- No automated tests — verified manually against real Spotify playback and
  the physical panel.
```

- [ ] **Step 2: Final commit**

```bash
git add README.md
git commit -m "Add README"
```
