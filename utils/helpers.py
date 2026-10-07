"""Helper functions for formatting, embed generation, and environment utilities."""

import os
import shutil
from glob import glob
from typing import TYPE_CHECKING, Optional

import discord

if TYPE_CHECKING:
    from models.track import Track
    from music.queue import LoopMode


def find_ffmpeg(configured_path: str | None = None) -> str:
    """Find the FFmpeg executable from configuration, PATH, or standard installation directories.

    Args:
        configured_path: Optional explicit path provided in config / environment.

    Returns:
        Absolute path or executable name for FFmpeg.

    Raises:
        FileNotFoundError: If FFmpeg cannot be located anywhere.
    """
    if configured_path and os.path.exists(configured_path):
        return configured_path

    # Check system PATH
    found = shutil.which("ffmpeg")
    if found:
        return found

    # Check Windows Winget / Gyan FFmpeg standard locations
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        winget_pattern = os.path.join(
            local_app_data,
            "Microsoft",
            "WinGet",
            "Packages",
            "*FFmpeg*",
            "**",
            "ffmpeg.exe",
        )
        winget_matches = glob(winget_pattern, recursive=True)
        if winget_matches:
            return winget_matches[0]

    # Check common fallback locations on Windows
    common_paths = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
        os.path.expanduser(r"~\scoop\apps\ffmpeg\current\bin\ffmpeg.exe"),
    ]
    for path in common_paths:
        if os.path.isfile(path):
            return path

    raise FileNotFoundError(
        "FFmpeg executable not found. Please install FFmpeg and add it to PATH, "
        "or specify FFMPEG_PATH in your .env file."
    )


def format_duration(seconds: int | None) -> str:
    """Format duration in seconds to HH:MM:SS or MM:SS string."""
    if seconds is None or seconds <= 0:
        return "🔴 Прямой эфир"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def create_progress_bar(current: int, total: int, length: int = 12) -> str:
    """Create a graphical text progress bar."""
    if total <= 0:
        return "🔘" + "▬" * (length - 1)
    progress = min(max(current / total, 0.0), 1.0)
    filled_len = int(round(length * progress))
    bar = "▬" * filled_len + "🔘" + "▬" * (length - filled_len)
    return bar


def create_now_playing_embed(
    track: "Track",
    volume: float,
    loop_mode: "LoopMode",
    queue_len: int,
) -> discord.Embed:
    """Build a rich embed for the currently playing track."""
    embed = discord.Embed(
        title="🎶 Сейчас играет",
        description=f"[{track.title}]({track.webpage_url})",
        color=discord.Color.blurple(),
    )

    if track.thumbnail:
        embed.set_thumbnail(url=track.thumbnail)

    duration_str = format_duration(track.duration)
    embed.add_field(name="⏳ Длительность", value=duration_str, inline=True)
    embed.add_field(name="👤 Автор", value=track.uploader or "Неизвестен", inline=True)
    embed.add_field(name="🎧 Запросил", value=track.requested_by, inline=True)

    volume_percent = int(volume * 100)
    loop_str = loop_mode.value.upper()
    embed.add_field(name="🔊 Громкость", value=f"{volume_percent}%", inline=True)
    embed.add_field(name="🔁 Повтор", value=loop_str, inline=True)
    embed.add_field(name="📋 Треков в очереди", value=str(queue_len), inline=True)

    embed.set_footer(text="Discord Music Bot | Production Ready")
    return embed


def create_track_queued_embed(track: "Track", position: int) -> discord.Embed:
    """Build an embed when a track is added to the queue."""
    embed = discord.Embed(
        title="✅ Трек добавлен в очередь",
        description=f"[{track.title}]({track.webpage_url})",
        color=discord.Color.green(),
    )
    if track.thumbnail:
        embed.set_thumbnail(url=track.thumbnail)

    embed.add_field(name="Позиция в очереди", value=f"#{position}", inline=True)
    embed.add_field(
        name="Длительность", value=format_duration(track.duration), inline=True
    )
    embed.add_field(name="Запросил", value=track.requested_by, inline=True)
    return embed


def create_queue_embed(
    tracks: list["Track"],
    current_track: Optional["Track"],
    page: int = 1,
    per_page: int = 10,
) -> discord.Embed:
    """Build an embed displaying the tracks in the queue."""
    total_tracks = len(tracks)
    total_pages = max((total_tracks + per_page - 1) // per_page, 1)
    page = max(1, min(page, total_pages))

    embed = discord.Embed(
        title="📜 Очередь воспроизведения",
        color=discord.Color.blue(),
    )

    if current_track:
        embed.add_field(
            name="▶️ Сейчас играет",
            value=f"[{current_track.title}]({current_track.webpage_url}) | `{format_duration(current_track.duration)}` (запросил: {current_track.requested_by})",
            inline=False,
        )

    if not tracks:
        embed.description = "Очередь пуста. Добавьте треки с помощью `/play`!"
    else:
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        page_tracks = tracks[start_idx:end_idx]

        lines = []
        for i, t in enumerate(page_tracks, start=start_idx + 1):
            dur = format_duration(t.duration)
            lines.append(f"`{i}.` [{t.title}]({t.webpage_url}) | `{dur}` ({t.requested_by})")

        embed.description = "\n".join(lines)

    embed.set_footer(text=f"Страница {page} из {total_pages} • Всего треков: {total_tracks}")
    return embed


def create_error_embed(message: str) -> discord.Embed:
    """Build a uniform error embed."""
    return discord.Embed(
        title="Ошибка",
        description=message,
        color=discord.Color.red(),
    )


def create_success_embed(title: str, description: str) -> discord.Embed:
    """Build a uniform success embed."""
    return discord.Embed(
        title=title,
        description=description,
        color=discord.Color.green(),
    )
