"""Music queue data structure with loop mode support and queue operations."""

import random
from collections import deque
from collections.abc import Iterator
from enum import StrEnum

from models.track import Track


class LoopMode(StrEnum):
    """Loop playback mode."""

    OFF = "off"
    TRACK = "track"
    QUEUE = "queue"


class MusicQueue:
    """Thread-safe and async-safe FIFO queue for audio tracks."""

    def __init__(self) -> None:
        self._items: deque[Track] = deque()

    def add(self, track: Track) -> int:
        """Add a track to the end of the queue.

        Returns:
            Position of the track in the queue (1-based index).
        """
        self._items.append(track)
        return len(self._items)

    def add_left(self, track: Track) -> None:
        """Insert a track to the front of the queue."""
        self._items.appendleft(track)

    def pop_next(self) -> Track | None:
        """Retrieve and remove the next track from the front of the queue.

        Returns:
            Track if queue is not empty, otherwise None.
        """
        if self._items:
            return self._items.popleft()
        return None

    def peek(self) -> Track | None:
        """View the next track without removing it.

        Returns:
            Track if queue is not empty, otherwise None.
        """
        if self._items:
            return self._items[0]
        return None

    def remove(self, index: int) -> Track | None:
        """Remove and return track at 1-based index.

        Args:
            index: 1-based position in queue.

        Returns:
            Removed Track or None if index is out of bounds.
        """
        if 1 <= index <= len(self._items):
            track = self._items[index - 1]
            del self._items[index - 1]
            return track
        return None

    def clear(self) -> None:
        """Remove all tracks from the queue."""
        self._items.clear()

    def shuffle(self) -> None:
        """Shuffle tracks currently in the queue."""
        items_list = list(self._items)
        random.shuffle(items_list)
        self._items = deque(items_list)

    @property
    def is_empty(self) -> bool:
        """Check if the queue is empty."""
        return len(self._items) == 0

    @property
    def tracks(self) -> list[Track]:
        """Return a copy of the list of tracks currently in the queue."""
        return list(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[Track]:
        return iter(self._items)
