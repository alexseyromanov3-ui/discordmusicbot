"""Music playback package."""

from music.player import MusicPlayer
from music.queue import LoopMode, MusicQueue
from music.source import create_audio_source
from music.youtube import YouTubeService

__all__ = [
    "LoopMode",
    "MusicPlayer",
    "MusicQueue",
    "YouTubeService",
    "create_audio_source",
]
