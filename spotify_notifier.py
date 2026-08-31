import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import pypixelcolor

SCRIPT_DIR = Path(__file__).parent
ENV_PATH = SCRIPT_DIR / ".env"
IMG_PATH = SCRIPT_DIR / "_spotify_frame.gif"
IDLE_IMG_PATH = SCRIPT_DIR / "_spotify_idle.png"

PANEL_WIDTH = 96
PANEL_HEIGHT = 16
POLL_INTERVAL_SECONDS = 5
FRAME_INTERVAL_SECONDS = 0.3

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

FRAME_DURATION_MS = 80
SCROLL_STEP_PX = 6


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

LASTFM_URL = "https://ws.audioscrobbler.com/2.0/"
LASTFM_API_KEY = os.environ.get("LASTFM_API_KEY") or _env.get("LASTFM_API_KEY")
LASTFM_USERNAME = os.environ.get("LASTFM_USERNAME") or _env.get("LASTFM_USERNAME")


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


def draw_spotify_logo(draw: ImageDraw.ImageDraw, x: int, y: int, size: int, circle_color: tuple, bar_color: tuple) -> None:
    draw.ellipse([x, y, x + size - 1, y + size - 1], fill=circle_color)
    cx = x + size // 2
    for i, dy in enumerate((6, 9, 12)):
        half_width = size // 2 - 4 + i
        draw.arc(
            [cx - half_width, y + dy - 3, cx + half_width, y + dy + 3],
            start=200, end=340, fill=bar_color, width=1,
        )


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


def connect_panel(led_address: str) -> pypixelcolor.Client:
    device = pypixelcolor.Client(led_address)
    device.connect()
    return device


def send_frame(device: pypixelcolor.Client, image: Image.Image) -> None:
    image.save(IMG_PATH, format="PNG")
    device.send_image(str(IMG_PATH))


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
