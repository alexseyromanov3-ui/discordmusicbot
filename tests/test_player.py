"""Unit tests for the MusicPlayer state transitions and controls."""

from unittest.mock import MagicMock

import pytest

from models.track import Track
from music.player import MusicPlayer
from music.queue import LoopMode
from utils.errors import InvalidVolume


@pytest.fixture
def mock_bot() -> MagicMock:
    bot = MagicMock()
    bot.loop = MagicMock()

    def _create_task_mock(coro: object, *args: object, **kwargs: object) -> MagicMock:
        if hasattr(coro, "close"):
            coro.close()
        return MagicMock()

    bot.loop.create_task.side_effect = _create_task_mock
    return bot


@pytest.fixture
def mock_guild() -> MagicMock:
    guild = MagicMock()
    guild.id = 99999
    return guild


@pytest.fixture
def player(mock_guild: MagicMock, mock_bot: MagicMock) -> MusicPlayer:
    youtube_mock = MagicMock()
    return MusicPlayer(
        guild=mock_guild,
        bot=mock_bot,
        ffmpeg_path="ffmpeg",
        youtube_service=youtube_mock,
        idle_timeout=300,
        default_volume=0.5,
    )


def test_player_initial_state(player: MusicPlayer) -> None:
    """Verify default initial player state."""
    assert player.volume == 0.5
    assert player.loop_mode == LoopMode.OFF
    assert player.is_playing is False
    assert player.is_paused is False
    assert player.current_track is None
    assert player.queue.is_empty is True


def test_pause_and_resume(player: MusicPlayer) -> None:
    """Verify pause and resume methods trigger voice client correctly."""
    mock_vc = MagicMock()
    mock_vc.is_playing.return_value = True
    mock_vc.is_paused.return_value = False
    player.voice_client = mock_vc

    # Pause
    assert player.pause() is True
    mock_vc.pause.assert_called_once()

    # Resume when paused
    mock_vc.is_playing.return_value = False
    mock_vc.is_paused.return_value = True
    assert player.resume() is True
    mock_vc.resume.assert_called_once()


def test_skip(player: MusicPlayer) -> None:
    """Verify skip stops current voice client to trigger next track."""
    mock_vc = MagicMock()
    mock_vc.is_playing.return_value = True
    mock_vc.is_paused.return_value = False
    player.voice_client = mock_vc

    assert player.skip() is True
    mock_vc.stop.assert_called_once()


def test_stop(player: MusicPlayer) -> None:
    """Verify stop clears queue and stops playback."""
    dummy_track = Track(
        title="T",
        url="http://url",
        webpage_url="http://yt",
        duration=100,
        thumbnail=None,
        uploader=None,
        requested_by="U",
    )
    player.queue.add(dummy_track)
    player.current_track = dummy_track

    mock_vc = MagicMock()
    mock_vc.is_playing.return_value = True
    player.voice_client = mock_vc

    player.stop()

    assert player.queue.is_empty is True
    assert player.current_track is None
    mock_vc.stop.assert_called_once()


def test_volume_control(player: MusicPlayer) -> None:
    """Verify volume adjustment and limits."""
    # 50%
    assert player.set_volume(50) == 0.5
    assert player.volume == 0.5

    # 150%
    assert player.set_volume(150) == 1.5
    assert player.volume == 1.5

    # Invalid volume (< 0 or > 200)
    with pytest.raises(InvalidVolume):
        player.set_volume(-10)

    with pytest.raises(InvalidVolume):
        player.set_volume(205)


def test_loop_modes_and_toggle(player: MusicPlayer) -> None:
    """Verify loop mode switching and cycling."""
    assert player.loop_mode == LoopMode.OFF

    assert player.toggle_loop() == LoopMode.TRACK
    assert player.loop_mode == LoopMode.TRACK

    assert player.toggle_loop() == LoopMode.QUEUE
    assert player.loop_mode == LoopMode.QUEUE

    assert player.toggle_loop() == LoopMode.OFF
    assert player.loop_mode == LoopMode.OFF

    player.set_loop_mode(LoopMode.TRACK)
    assert player.loop_mode == LoopMode.TRACK


def test_set_initial_message(player: MusicPlayer) -> None:
    """Verify setting and clearing the initial message."""
    mock_msg = MagicMock()
    player.set_initial_message(mock_msg)
    assert player._initial_message is mock_msg
    player.set_initial_message(None)
    assert player._initial_message is None

