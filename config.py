"""Application configuration and environment settings."""

import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

from utils.helpers import find_ffmpeg

# Load .env file if present
load_dotenv()


@dataclass(frozen=True)
class Config:
    """Central configuration class."""

    discord_token: str
    idle_timeout: int
    default_volume: float
    log_level: str
    ffmpeg_path: str
    youtube_cookiefile: str | None = None
    youtube_cookies_browser: str | None = None

    @classmethod
    def load(cls) -> "Config":
        """Load and validate configuration from environment variables."""
        token = os.getenv("DISCORD_TOKEN", "").strip()

        # Idle timeout (seconds, 0 to disable)
        try:
            idle_timeout = int(os.getenv("IDLE_TIMEOUT", "300"))
            if idle_timeout < 0:
                idle_timeout = 0
        except ValueError:
            idle_timeout = 300

        # Default volume (0.0 to 2.0)
        try:
            default_volume = float(os.getenv("DEFAULT_VOLUME", "0.5"))
            if not 0.0 <= default_volume <= 2.0:
                default_volume = 0.5
        except ValueError:
            default_volume = 0.5

        # Log level
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        if log_level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            log_level = "INFO"

        # FFmpeg executable path
        custom_ffmpeg = os.getenv("FFMPEG_PATH", "").strip() or None
        ffmpeg_path = find_ffmpeg(custom_ffmpeg)

        # YouTube cookies support
        cookiefile = os.getenv("YOUTUBE_COOKIEFILE", "").strip() or None
        if not cookiefile and os.path.isfile("cookies.txt"):
            cookiefile = "cookies.txt"

        cookies_browser = os.getenv("YOUTUBE_COOKIES_BROWSER", "").strip() or None

        return cls(
            discord_token=token,
            idle_timeout=idle_timeout,
            default_volume=default_volume,
            log_level=log_level,
            ffmpeg_path=ffmpeg_path,
            youtube_cookiefile=cookiefile,
            youtube_cookies_browser=cookies_browser,
        )


def setup_logging(level_name: str = "INFO") -> None:
    """Configure standard library logging."""
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Silence internal discord.player process termination logs (INFO level)
    logging.getLogger("discord.player").setLevel(logging.WARNING)

    # Silence noisy discord gateway / aiohttp debug logs unless requested
    if level < logging.INFO:
        logging.getLogger("discord.gateway").setLevel(logging.INFO)
        logging.getLogger("discord.client").setLevel(logging.INFO)
