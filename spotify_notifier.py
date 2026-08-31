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
