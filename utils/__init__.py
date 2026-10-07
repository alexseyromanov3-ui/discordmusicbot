"""Utilities module for Discord Music Bot."""

from utils.errors import (
    InvalidVolume,
    MusicBotError,
    PlaybackError,
    QueueEmpty,
    TrackNotFound,
    VoiceConnectionError,
    YouTubeError,
)

__all__ = [
    "InvalidVolume",
    "MusicBotError",
    "PlaybackError",
    "QueueEmpty",
    "TrackNotFound",
    "VoiceConnectionError",
    "YouTubeError",
]
