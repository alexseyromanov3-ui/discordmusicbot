"""Unit tests for the MusicQueue data structure."""

from models.track import Track
from music.queue import LoopMode, MusicQueue


def create_dummy_track(title: str) -> Track:
    """Helper to generate dummy track fixtures."""
    return Track(
        title=title,
        url=f"https://stream.example.com/{title}",
        webpage_url=f"https://youtube.com/watch?v={title}",
        duration=180,
        thumbnail=None,
        uploader="Artist",
        requested_by="User",
    )


def test_empty_queue() -> None:
    """Verify state and operations on an empty queue."""
    q = MusicQueue()
    assert q.is_empty is True
    assert len(q) == 0
    assert q.pop_next() is None
    assert q.peek() is None
    assert list(q) == []
    assert q.tracks == []


def test_queue_add_and_ordering() -> None:
    """Verify FIFO ordering when adding multiple tracks."""
    q = MusicQueue()
    t1 = create_dummy_track("Song 1")
    t2 = create_dummy_track("Song 2")
    t3 = create_dummy_track("Song 3")

    pos1 = q.add(t1)
    pos2 = q.add(t2)
    pos3 = q.add(t3)

    assert pos1 == 1
    assert pos2 == 2
    assert pos3 == 3
    assert len(q) == 3
    assert q.is_empty is False

    assert q.peek() == t1

    # Pop sequentially
    assert q.pop_next() == t1
    assert len(q) == 2
    assert q.peek() == t2

    assert q.pop_next() == t2
    assert q.pop_next() == t3
    assert q.pop_next() is None
    assert q.is_empty is True


def test_queue_clear() -> None:
    """Verify clear operation completely empties the queue."""
    q = MusicQueue()
    q.add(create_dummy_track("Song 1"))
    q.add(create_dummy_track("Song 2"))
    assert len(q) == 2

    q.clear()
    assert len(q) == 0
    assert q.is_empty is True
    assert q.pop_next() is None


def test_queue_remove() -> None:
    """Verify removing tracks by 1-based index."""
    q = MusicQueue()
    t1 = create_dummy_track("Song 1")
    t2 = create_dummy_track("Song 2")
    t3 = create_dummy_track("Song 3")

    q.add(t1)
    q.add(t2)
    q.add(t3)

    # Remove out-of-bounds
    assert q.remove(0) is None
    assert q.remove(4) is None
    assert len(q) == 3

    # Remove second track
    removed = q.remove(2)
    assert removed == t2
    assert len(q) == 2
    assert q.tracks == [t1, t3]


def test_queue_add_left() -> None:
    """Verify adding track to the front of the queue."""
    q = MusicQueue()
    t1 = create_dummy_track("Song 1")
    t2 = create_dummy_track("Song 2")
    t_urgent = create_dummy_track("Urgent Song")

    q.add(t1)
    q.add(t2)
    q.add_left(t_urgent)

    assert len(q) == 3
    assert q.pop_next() == t_urgent
    assert q.pop_next() == t1
    assert q.pop_next() == t2


def test_loop_mode_values() -> None:
    """Verify LoopMode enum values."""
    assert LoopMode.OFF.value == "off"
    assert LoopMode.TRACK.value == "track"
    assert LoopMode.QUEUE.value == "queue"
