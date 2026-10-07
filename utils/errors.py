"""Custom exception hierarchy for the Discord Music Bot."""



class MusicBotError(Exception):
    """Base exception for all music bot errors."""

    def __init__(self, message: str, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message = user_message or message


class TrackNotFound(MusicBotError):
    """Raised when a track cannot be found via search or direct URL."""

    def __init__(self, query: str) -> None:
        super().__init__(
            message=f"Track not found for query: {query}",
            user_message=f"❌ Не удалось найти аудио по запросу: `{query}`",
        )


class YouTubeError(MusicBotError):
    """Raised when yt-dlp fails to extract info or encounters an error."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            message=f"YouTube extraction error: {detail}",
            user_message=f"❌ Ошибка извлечения YouTube: {detail}",
        )


class VoiceConnectionError(MusicBotError):
    """Raised when there is an issue with connecting, moving, or staying in a voice channel."""

    def __init__(self, message: str, user_message: str | None = None) -> None:
        super().__init__(
            message=message,
            user_message=user_message or f"❌ Ошибка голосового подключения: {message}",
        )


class PlaybackError(MusicBotError):
    """Raised when an error occurs during audio playback."""

    def __init__(self, message: str, user_message: str | None = None) -> None:
        super().__init__(
            message=message,
            user_message=user_message or f"❌ Ошибка воспроизведения: {message}",
        )


class InvalidVolume(MusicBotError):
    """Raised when an invalid volume level is supplied."""

    def __init__(self, volume: int) -> None:
        super().__init__(
            message=f"Invalid volume level: {volume}",
            user_message="❌ Громкость должна быть целым числом в диапазоне от 0 до 200%.",
        )


class QueueEmpty(MusicBotError):
    """Raised when an action requires tracks in the queue, but it is empty."""

    def __init__(self) -> None:
        super().__init__(
            message="Queue is empty",
            user_message="❌ Очередь воспроизведения пуста.",
        )
