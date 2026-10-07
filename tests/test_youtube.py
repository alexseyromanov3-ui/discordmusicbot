"""Unit tests for the YouTubeService using mocks to avoid network dependency."""

from unittest.mock import patch

import pytest
import yt_dlp

from music.youtube import YouTubeService, is_url
from utils.errors import TrackNotFound, YouTubeError


def test_is_url() -> None:
    """Test URL detection helper."""
    assert is_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is True
    assert is_url("http://youtu.be/dQw4w9WgXcQ") is True
    assert is_url("https://soundcloud.com/artist/track") is True
    assert is_url("Never Gonna Give You Up") is False
    assert is_url("artist - track title") is False
    assert is_url("") is False


@pytest.mark.asyncio
async def test_get_track_direct_url_success() -> None:
    """Test successful track extraction for direct URL."""
    fake_info = {
        "title": "Sample Song",
        "url": "https://stream.googlevideo.com/sample.opus",
        "webpage_url": "https://www.youtube.com/watch?v=sample",
        "duration": 200,
        "thumbnail": "https://img.youtube.com/sample.jpg",
        "uploader": "Sample Artist",
        "is_live": False,
    }

    service = YouTubeService()
    with patch.object(service._ytdl, "extract_info", return_value=fake_info) as mock_extract:
        track = await service.get_track("https://www.youtube.com/watch?v=sample", requested_by="User1")

        mock_extract.assert_called_once_with(
            "https://www.youtube.com/watch?v=sample", download=False
        )
        assert track.title == "Sample Song"
        assert track.url == "https://stream.googlevideo.com/sample.opus"
        assert track.duration == 200
        assert track.requested_by == "User1"


@pytest.mark.asyncio
async def test_get_track_search_query_success() -> None:
    """Test successful search query resolving first entry."""
    fake_entry = {
        "title": "Search Result Song",
        "url": "https://stream.googlevideo.com/search.opus",
        "webpage_url": "https://www.youtube.com/watch?v=search123",
        "duration": 150,
        "thumbnail": "https://img.youtube.com/search.jpg",
        "uploader": "Search Artist",
        "is_live": False,
    }
    fake_info = {
        "_type": "playlist",
        "entries": [fake_entry],
    }

    service = YouTubeService()
    with patch.object(service._ytdl, "extract_info", return_value=fake_info) as mock_extract:
        track = await service.get_track("search terms", requested_by="User2")

        mock_extract.assert_called_once_with("ytsearch1:search terms", download=False)
        assert track.title == "Search Result Song"
        assert track.duration == 150
        assert track.requested_by == "User2"


@pytest.mark.asyncio
async def test_get_track_empty_entries_raises_not_found() -> None:
    """Test that empty search results raise TrackNotFound."""
    fake_info = {
        "_type": "playlist",
        "entries": [],
    }

    service = YouTubeService()
    with patch.object(service._ytdl, "extract_info", return_value=fake_info), pytest.raises(TrackNotFound):
        await service.get_track("nonexistent music query", requested_by="User3")


@pytest.mark.asyncio
async def test_get_track_empty_query_raises_not_found() -> None:
    """Test that blank queries raise TrackNotFound immediately."""
    service = YouTubeService()
    with pytest.raises(TrackNotFound):
        await service.get_track("   ", requested_by="User3")


@pytest.mark.asyncio
async def test_get_track_download_error_raises_youtube_error() -> None:
    """Test that yt-dlp DownloadError is caught and converted to YouTubeError."""
    service = YouTubeService()
    with patch.object(
        service._ytdl,
        "extract_info",
        side_effect=yt_dlp.utils.DownloadError("Video unavailable"),
    ), pytest.raises(YouTubeError):
        await service.get_track("https://youtube.com/watch?v=bad", requested_by="User4")


@pytest.mark.asyncio
async def test_get_track_fallback_soundcloud_success() -> None:
    """Test that when YouTube raises an eligible fallback error, SoundCloud fallback resolves the track."""
    service = YouTubeService()
    sc_entry = {
        "title": "Fallback Track",
        "url": "https://playback.sndcdn.com/fallback.m3u8",
        "webpage_url": "https://soundcloud.com/artist/track",
        "duration": 180,
        "thumbnail": "https://img.sndcdn.com/thumb.jpg",
        "uploader": "SoundCloud Artist",
        "is_live": False,
    }
    with patch.object(
        service._ytdl,
        "extract_info",
        side_effect=yt_dlp.utils.DownloadError("Sign in to confirm your age. Use --cookies"),
    ), patch.object(service, "_fallback_soundcloud", return_value=sc_entry):
        track = await service.get_track("age restricted query", requested_by="User5")
        assert track.title == "Fallback Track"
        assert track.url == "https://playback.sndcdn.com/fallback.m3u8"
        assert track.requested_by == "User5"

