"""Unit tests for the Track data model."""

from models.track import Track


def test_track_creation_and_attributes() -> None:
    """Verify track creation with all required and optional attributes."""
    track = Track(
        title="Rick Astley - Never Gonna Give You Up",
        url="https://audio-stream.googlevideo.com/videoplayback",
        webpage_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        duration=213,
        thumbnail="https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
        uploader="Rick Astley",
        requested_by="Alice",
    )

    assert track.title == "Rick Astley - Never Gonna Give You Up"
    assert track.url == "https://audio-stream.googlevideo.com/videoplayback"
    assert track.webpage_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert track.duration == 213
    assert track.thumbnail == "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"
    assert track.uploader == "Rick Astley"
    assert track.requested_by == "Alice"
    assert track.is_live is False


def test_track_formatted_duration_standard() -> None:
    """Verify formatted duration for standard songs."""
    track = Track(
        title="Test Song",
        url="http://stream",
        webpage_url="http://youtube.com/watch?v=123",
        duration=215,  # 3 minutes 35 seconds
        thumbnail=None,
        uploader=None,
        requested_by="Bob",
    )
    assert track.formatted_duration == "03:35"


def test_track_formatted_duration_over_one_hour() -> None:
    """Verify formatted duration for long tracks (> 1 hour)."""
    track = Track(
        title="Long Podcast",
        url="http://stream",
        webpage_url="http://youtube.com/watch?v=123",
        duration=3665,  # 1 hour 1 minute 5 seconds
        thumbnail=None,
        uploader=None,
        requested_by="Bob",
    )
    assert track.formatted_duration == "01:01:05"


def test_track_formatted_duration_live_stream() -> None:
    """Verify formatted duration for live streams or None duration."""
    track_live = Track(
        title="Lofi Radio",
        url="http://stream",
        webpage_url="http://youtube.com/watch?v=live",
        duration=None,
        thumbnail=None,
        uploader="Lofi Girl",
        requested_by="Charlie",
        is_live=True,
    )
    assert track_live.formatted_duration == "🔴 Прямой эфир"

    track_zero = Track(
        title="Zero Duration",
        url="http://stream",
        webpage_url="http://youtube.com/watch?v=live",
        duration=0,
        thumbnail=None,
        uploader="Channel",
        requested_by="Charlie",
    )
    assert track_zero.formatted_duration == "🔴 Прямой эфир"
