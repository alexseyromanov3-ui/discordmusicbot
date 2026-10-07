"""Audio source creation using FFmpeg and discord.py audio transformers."""

import logging

import discord

from utils.errors import PlaybackError

logger = logging.getLogger(__name__)

FFMPEG_BEFORE_OPTIONS = (
    "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -reconnect_at_eof 1"
)
FFMPEG_OPTIONS = "-vn"


def create_audio_source(
    stream_url: str,
    ffmpeg_executable: str,
    volume: float = 0.5,
) -> discord.PCMVolumeTransformer:
    """Create a discord-compatible PCMVolumeTransformer audio source with FFmpeg.

    Args:
        stream_url: Direct audio stream URL.
        ffmpeg_executable: Path or name of the FFmpeg binary.
        volume: Initial volume level (0.0 to 2.0).

    Returns:
        discord.PCMVolumeTransformer instance ready for VoiceClient.play.

    Raises:
        PlaybackError: If audio source instantiation fails.
    """
    try:
        raw_source = discord.FFmpegPCMAudio(
            stream_url,
            executable=ffmpeg_executable,
            before_options=FFMPEG_BEFORE_OPTIONS,
            options=FFMPEG_OPTIONS,
        )
        transformed_source = discord.PCMVolumeTransformer(raw_source, volume=volume)
        return transformed_source
    except Exception as e:
        logger.error("Failed to initialize FFmpeg audio source: %s", e, exc_info=True)
        raise PlaybackError(f"Ошибка инициализации FFmpeg: {e}") from e
