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


if __name__ == "__main__":
    img = Image.new("RGB", (LOGO_SIZE * 2 + 10, LOGO_SIZE + 4), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw_spotify_logo(draw, 2, 2, LOGO_SIZE, SPOTIFY_GREEN, BG_COLOR)
    draw_spotify_logo(draw, LOGO_SIZE + 8, 2, LOGO_SIZE, DIM_GREEN, IDLE_BG_COLOR)
    img.resize((img.width * 10, img.height * 10), Image.NEAREST).save(SCRIPT_DIR / "_logo_preview.png")
    print("saved _logo_preview.png")
