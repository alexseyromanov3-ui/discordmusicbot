"""Track data model representing an audio item."""

from dataclasses import dataclass


@dataclass
class Track:
    """Represents a playable audio track with metadata."""

    title: str
    url: str  # Direct stream audio URL extracted by yt-dlp
    webpage_url: str  # YouTube video or source webpage URL
    duration: int | None  # Duration in seconds, None if live stream
    thumbnail: str | None
    uploader: str | None
    requested_by: str
    is_live: bool = False

    @property
    def formatted_duration(self) -> str:
        """Return formatted duration string (MM:SS or HH:MM:SS)."""
        if self.duration is None or self.is_live or self.duration <= 0:
            return "🔴 Прямой эфир"
        hours = self.duration // 3600
        minutes = (self.duration % 3600) // 60
        seconds = self.duration % 60
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def __str__(self) -> str:
        return f"{self.title} ({self.formatted_duration})"
