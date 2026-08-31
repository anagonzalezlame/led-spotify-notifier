# LED Spotify Notifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Python script that polls Spotify for the currently playing track and pushes a pixel-art Spotify logo + scrolling song/artist marquee to the 96x16 BLE LED panel, falling back to an idle screen when nothing is playing.

**Architecture:** Single-file script (`spotify_notifier.py`), mirroring the sibling `led-gmail-notifier` project: `.env`-based config, an infinite poll loop, Pillow-rendered frames, `pypixelcolor` for BLE delivery. Track-change detection avoids redundant BLE writes; looping GIFs are sent once per change and loop on-device.

**Tech Stack:** Python 3.12, `spotipy` (Spotify Web API + OAuth), `Pillow`, `pypixelcolor`.

**Spec:** `docs/superpowers/specs/2026-08-31-led-spotify-notifier-design.md`

## Global Constraints

- Panel resolution is fixed at 96x16 (`PANEL_WIDTH = 96`, `PANEL_HEIGHT = 16`) — from spec and both sibling projects.
- Poll interval is 5 seconds (`POLL_INTERVAL_SECONDS = 5`) — from spec.
- OAuth scope is exactly `user-read-currently-playing user-read-playback-state` — from spec.
- Auth uses the `spotipy` library (`SpotifyOAuth`), not hand-rolled OAuth — from spec.
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

### Task 2: Spotify Developer app + OAuth client

**Files:**
- Modify: `spotify_notifier.py` (add `get_spotify_client`)

**Interfaces:**
- Consumes: `_env: dict`, `SCOPE: str`, `CACHE_PATH: Path` (Task 1)
- Produces: `get_spotify_client() -> Spotify`

- [ ] **Step 1: Create the Spotify Developer app (manual, in browser)**

Guide the user through:
1. Go to https://developer.spotify.com/dashboard and log in.
2. Click "Create app". Name: anything (e.g. "LED Panel Notifier"). Redirect URI: `http://127.0.0.1:8888/callback` (must match exactly).
3. Check the box for the Web API.
4. Save, then open the app's Settings to copy the **Client ID** and **Client Secret**.

- [ ] **Step 2: Fill in `.env`**

Copy `.env.example` to `.env` and fill in `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback`, and `LED_ADDRESS` (reuse the value from the sibling projects' `.env`).

- [ ] **Step 3: Add `get_spotify_client` to `spotify_notifier.py`**

```python
def get_spotify_client() -> Spotify:
    client_id = os.environ.get("SPOTIFY_CLIENT_ID") or _env.get("SPOTIFY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET") or _env.get("SPOTIFY_CLIENT_SECRET")
    redirect_uri = os.environ.get("SPOTIFY_REDIRECT_URI") or _env.get("SPOTIFY_REDIRECT_URI")
    if not client_id or not client_secret or not redirect_uri:
        print("Falta configurar .env (copia .env.example a .env y completa los datos).")
        sys.exit(1)

    auth_manager = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=SCOPE,
        cache_path=str(CACHE_PATH),
    )
    return Spotify(auth_manager=auth_manager)
```

- [ ] **Step 4: Verify the OAuth flow manually**

Add this temporarily at the bottom of `spotify_notifier.py`, replacing the `skeleton ok` print:

```python
if __name__ == "__main__":
    sp = get_spotify_client()
    print(sp.current_user()["display_name"])
```

Run: `python spotify_notifier.py`
Expected: a browser window opens asking to authorize the app; after accepting, the script prints your Spotify display name. `.cache-spotify` now exists in the project folder. Run it a second time — expected: no browser popup this time (cached token), prints the name immediately.

- [ ] **Step 5: Commit**

```bash
git add spotify_notifier.py
git commit -m "Add Spotify OAuth client"
```

(Do not commit `.env` or `.cache-spotify` — both are gitignored.)

---

### Task 3: Now-playing polling wrapper

**Files:**
- Modify: `spotify_notifier.py` (add `get_now_playing`)

**Interfaces:**
- Consumes: `get_spotify_client() -> Spotify` (Task 2)
- Produces: `get_now_playing(sp: Spotify) -> dict | None` — returns `{"track_id": str, "title": str, "artist": str, "is_playing": bool}` or `None` if nothing is loaded.

- [ ] **Step 1: Add `get_now_playing`**

```python
def get_now_playing(sp: Spotify) -> dict | None:
    playback = sp.current_playback()
    if not playback or not playback.get("item"):
        return None
    item = playback["item"]
    artists = ", ".join(a["name"] for a in item.get("artists", []))
    return {
        "track_id": item["id"],
        "title": item["name"],
        "artist": artists,
        "is_playing": playback.get("is_playing", False),
    }
```

- [ ] **Step 2: Verify manually against real playback**

Replace the bottom of `spotify_notifier.py`:

```python
if __name__ == "__main__":
    sp = get_spotify_client()
    print(get_now_playing(sp))
```

Run: `python spotify_notifier.py` with nothing playing on any device.
Expected: prints `None`.
Start playing a song on Spotify (any device logged into your account), run again.
Expected: prints a dict with the correct `track_id`, `title`, `artist`, and `is_playing: True`. Pause the song, run again — expected `is_playing: False`.

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

### Task 7: Panel sender

**Files:**
- Modify: `spotify_notifier.py` (add `send_to_panel`)

**Interfaces:**
- Consumes: `LED_ADDRESS: str | None` (Task 1)
- Produces: `send_to_panel(frame_path: Path, led_address: str) -> None`

- [ ] **Step 1: Add `send_to_panel`**

```python
def send_to_panel(frame_path: Path, led_address: str) -> None:
    device = pypixelcolor.Client(led_address)
    try:
        device.connect()
        device.send_image(str(frame_path))
    finally:
        device.disconnect()
```

- [ ] **Step 2: Verify against the real panel**

Make sure the LED panel is powered on and within BLE range, and that no other script (`led-gmail-notifier`, `led-panel-prompt`) is currently connected to it. Replace the bottom of `spotify_notifier.py`:

```python
if __name__ == "__main__":
    if not LED_ADDRESS:
        print("Falta LED_ADDRESS en .env")
        sys.exit(1)
    path = render_idle_frame()
    send_to_panel(path, LED_ADDRESS)
    print("enviado al panel")
```

Run: `python spotify_notifier.py`
Expected: prints "enviado al panel" and the physical panel updates to show the dim idle logo + "Spotify" text.

- [ ] **Step 3: Commit**

```bash
git add spotify_notifier.py
git commit -m "Add panel sender"
```

---

### Task 8: Main poll loop

**Files:**
- Modify: `spotify_notifier.py` (add `main`, final `if __name__ == "__main__":` block)

**Interfaces:**
- Consumes: `get_spotify_client() -> Spotify` (Task 2), `get_now_playing(sp) -> dict | None` (Task 3), `build_marquee_frames(title, artist) -> list[Image.Image]` and `save_marquee_gif(frames) -> Path` (Task 5), `render_idle_frame() -> Path` (Task 6), `send_to_panel(frame_path, led_address) -> None` (Task 7), `LED_ADDRESS`, `POLL_INTERVAL_SECONDS` (Task 1)
- Produces: `main() -> None` (entry point; nothing downstream consumes this)

- [ ] **Step 1: Add `main` and the final entry point**

```python
def main() -> None:
    if not LED_ADDRESS:
        print("Falta configurar LED_ADDRESS en .env")
        sys.exit(1)

    sp = get_spotify_client()
    print(f"[{datetime.now()}] Spotify -> LED panel notifier iniciado. Consultando cada {POLL_INTERVAL_SECONDS}s.")

    last_state = None  # (track_id, is_playing) or (None, False)

    while True:
        try:
            now_playing = get_now_playing(sp)
        except Exception as e:
            print(f"[{datetime.now()}] Error consultando Spotify: {e}")
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

- [ ] **Step 2: Verify the full end-to-end flow manually**

Run: `python spotify_notifier.py`.
Expected sequence, checked against the real panel:
1. With nothing playing, panel shows the idle screen within ~5s.
2. Start playing a song — panel switches to the marquee (logo + scrolling title/artist) within ~5s, and it keeps looping on its own without flicker or re-sends (watch the console: no repeated "Cambio de estado" lines while the same track keeps playing).
3. Pause the song — panel switches back to idle within ~5s.
4. Skip to a different track while playing — panel updates to the new marquee text within ~5s.
5. Turn off the panel's Bluetooth (or move it out of range) — console prints an "Error enviando al panel" line and the loop keeps running (does not crash).

- [ ] **Step 3: Commit**

```bash
git add spotify_notifier.py
git commit -m "Wire up main poll loop with change detection and error handling"
```

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

A tiny local background script: polls what you're currently playing on Spotify
and shows a pixel-art Spotify logo plus a scrolling "Song - Artist" marquee on
a 96x16 BLE LED matrix panel. Falls back to a dim idle screen when nothing is
playing.

Runs standalone — it shares the panel with `led-gmail-notifier` but the two are
never run at the same time; stop one before starting the other.

## Setup

```bash
pip install spotipy pillow
```

1. Create an app at the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
   with redirect URI `http://127.0.0.1:8888/callback`.
2. Copy `.env.example` to `.env` and fill in `SPOTIFY_CLIENT_ID`,
   `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REDIRECT_URI`, and `LED_ADDRESS` (same BLE
   MAC address used by the other panel scripts).
3. Run it:

```bash
python spotify_notifier.py
```

The first run opens a browser to authorize your Spotify account; after that,
the auth token is cached in `.cache-spotify` and it won't ask again.

## Notes

- Polls every 5 seconds but only re-sends to the panel when the track or
  play/pause state actually changes.
- No automated tests — verified manually against real Spotify playback and
  the physical panel.
```

- [ ] **Step 2: Final commit**

```bash
git add README.md
git commit -m "Add README"
```
