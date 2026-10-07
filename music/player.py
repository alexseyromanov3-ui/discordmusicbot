"""Guild music player managing audio queue, playback loop, and voice state."""

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from models.track import Track
from music.queue import LoopMode, MusicQueue
from music.source import create_audio_source
from music.youtube import YouTubeService
from utils.errors import InvalidVolume, VoiceConnectionError

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class MusicPlayer:
    """Manages audio playback for a single Discord guild."""

    def __init__(
        self,
        guild: discord.Guild,
        bot: commands.Bot,
        ffmpeg_path: str,
        youtube_service: YouTubeService,
        idle_timeout: int = 300,
        default_volume: float = 0.5,
    ) -> None:
        self.guild = guild
        self.bot = bot
        self.ffmpeg_path = ffmpeg_path
        self.youtube_service = youtube_service
        self.idle_timeout = idle_timeout

        self.queue = MusicQueue()
        self.current_track: Track | None = None
        self.previous_track: Track | None = None
        self.volume: float = default_volume
        self.loop_mode: LoopMode = LoopMode.OFF

        self.voice_client: discord.VoiceClient | None = None
        self.text_channel: discord.abc.Messageable | None = None
        self._initial_message: discord.Message | None = None
        self.current_source: discord.PCMVolumeTransformer | None = None

        self._playback_finished = asyncio.Event()
        self._new_track_event = asyncio.Event()
        self._worker_task: asyncio.Task | None = None
        self._idle_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._skip_current_loop = False
        self._is_destroyed = False

    @property
    def is_playing(self) -> bool:
        """Check if audio is currently playing."""
        return bool(self.voice_client and self.voice_client.is_playing())

    @property
    def is_paused(self) -> bool:
        """Check if audio is currently paused."""
        return bool(self.voice_client and self.voice_client.is_paused())

    @property
    def is_connected(self) -> bool:
        """Check if voice client is connected to a voice channel."""
        return bool(self.voice_client and self.voice_client.is_connected())

    def start_worker(self) -> None:
        """Ensure the background playback worker task is running."""
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = self.bot.loop.create_task(
                self._playback_worker(), name=f"music-worker-{self.guild.id}"
            )

    async def connect_voice(self, channel: discord.VoiceChannel | discord.StageChannel) -> None:
        """Connect or move to the specified voice channel."""
        async with self._lock:
            current_vc = self.guild.voice_client
            if current_vc and isinstance(current_vc, discord.VoiceClient):
                if current_vc.is_connected():
                    if current_vc.channel != channel:
                        if not self.is_playing and not self.is_paused:
                            await current_vc.move_to(channel)
                            self.voice_client = current_vc
                            return
                        raise VoiceConnectionError(
                            f"Бот уже воспроизводит музыку в канале {current_vc.channel.name}."
                        )
                    # Already connected to the target channel
                    self.voice_client = current_vc
                    return

                # Stale or disconnected voice client - force clean disconnect to avoid ClientException
                logger.info("Cleaning up stale voice client in guild %s", self.guild.id)
                with contextlib.suppress(Exception):
                    await current_vc.disconnect(force=True)
                self.voice_client = None

            try:
                self.voice_client = await channel.connect(timeout=20.0, reconnect=True)
            except Exception as e:
                logger.error("Failed to connect to voice channel %s: %s", channel.id, e)
                raise VoiceConnectionError(f"Не удалось подключиться к каналу: {e}") from e

    def _reset_idle_timer(self) -> None:
        """Reset or start the idle disconnect watchdog timer."""
        if self.idle_timeout <= 0:
            return

        if self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()

        self._idle_task = self.bot.loop.create_task(
            self._idle_watchdog(), name=f"music-idle-{self.guild.id}"
        )

    def _cancel_idle_timer(self) -> None:
        """Cancel idle watchdog timer when playback starts."""
        if self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()
            self._idle_task = None

    async def _idle_watchdog(self) -> None:
        """Disconnect after idle_timeout seconds of inactivity."""
        try:
            await asyncio.sleep(self.idle_timeout)
            if not self.is_playing and not self.is_paused and self.queue.is_empty:
                logger.info(
                    "Guild %s idle timeout reached (%ss). Disconnecting.",
                    self.guild.id,
                    self.idle_timeout,
                )
                if self.text_channel:
                    try:

                        embed = discord.Embed(
                            title="⏱️ Отключение по тайм-ауту",
                            description=f"Бот отключился от голосового канала после {self.idle_timeout // 60} мин. бездействия.",
                            color=discord.Color.light_grey(),
                        )
                        await self.text_channel.send(embed=embed)
                    except Exception:
                        pass
                await self.cleanup()
        except asyncio.CancelledError:
            pass

    def _after_playback(self, error: Exception | None) -> None:
        """Thread-safe callback triggered by discord.py when audio finishes."""
        if error:
            logger.error("Playback error callback in guild %s: %s", self.guild.id, error)
        # Notify worker loop thread-safely
        self.bot.loop.call_soon_threadsafe(self._playback_finished.set)

    def set_initial_message(self, message: discord.Message | None) -> None:
        """Store the initial loading message so it can be updated when playback begins."""
        self._initial_message = message

    async def _playback_worker(self) -> None:
        """Main loop that streams tracks sequentially from the queue."""
        logger.info("Playback worker started for guild %s", self.guild.id)
        while not self._is_destroyed:
            try:
                # 1. Determine next track
                track_to_play: Track | None = None

                # Handle loop mode: track
                if (
                    self.loop_mode == LoopMode.TRACK
                    and self.current_track is not None
                    and not self._skip_current_loop
                ):
                    track_to_play = self.current_track

                self._skip_current_loop = False

                if track_to_play is None and self.queue.is_empty:
                    self.current_track = None
                    self.current_source = None
                    self._reset_idle_timer()
                    self._new_track_event.clear()
                    await self._new_track_event.wait()
                    continue

                # 2. We have a track to play. Cancel idle timer.
                self._cancel_idle_timer()

                # Sync voice client reference
                if self.guild.voice_client and isinstance(self.guild.voice_client, discord.VoiceClient):
                    self.voice_client = self.guild.voice_client

                # Wait for voice connection to complete handshake if currently connecting
                connected = False
                for _ in range(30):  # up to 15 seconds
                    if self.guild.voice_client and isinstance(self.guild.voice_client, discord.VoiceClient):
                        self.voice_client = self.guild.voice_client
                    if self.voice_client and self.voice_client.is_connected():
                        connected = True
                        break
                    await asyncio.sleep(0.5)

                if not connected or self.voice_client is None:
                    logger.warning("Voice client not connected in guild %s after waiting.", self.guild.id)
                    # We have NOT popped the track yet, so it is safely retained in the queue.
                    await asyncio.sleep(2)
                    continue

                vc = self.voice_client

                # Now that voice client is confirmed connected, pop track from queue if needed
                if track_to_play is None:
                    track_to_play = self.queue.pop_next()
                    if track_to_play is None:
                        continue

                self.current_track = track_to_play

                # Ensure any lingering audio is stopped before starting a new stream
                if vc.is_playing() or vc.is_paused():
                    vc.stop()

                # 3. Create audio source
                stream_url = track_to_play.url
                try:
                    source = create_audio_source(
                        stream_url=stream_url,
                        ffmpeg_executable=self.ffmpeg_path,
                        volume=self.volume,
                    )
                except Exception as e:
                    logger.warning("Failed to create audio source directly, attempting refresh: %s", e)
                    try:
                        refreshed = await self.youtube_service.get_track(
                            track_to_play.webpage_url, track_to_play.requested_by
                        )
                        track_to_play.url = refreshed.url
                        source = create_audio_source(
                            stream_url=track_to_play.url,
                            ffmpeg_executable=self.ffmpeg_path,
                            volume=self.volume,
                        )
                    except Exception as refresh_err:
                        logger.error("Failed to refresh track %s: %s", track_to_play.title, refresh_err)
                        if self.text_channel:
                            with contextlib.suppress(Exception):
                                await self.text_channel.send(
                                    f"❌ Не удалось воспроизвести `{track_to_play.title}`: ошибка источника."
                                )
                        self.current_track = None
                        continue

                self.current_source = source
                self._playback_finished.clear()

                # Start playback
                try:
                    vc.play(source, after=self._after_playback)
                except Exception as play_err:
                    logger.error("Error playing audio source in guild %s: %s", self.guild.id, play_err)
                    if self.text_channel:
                        with contextlib.suppress(Exception):
                            await self.text_channel.send(
                                f"❌ Ошибка воспроизведения трека `{track_to_play.title}`: {play_err}"
                            )
                    self.current_track = None
                    continue

                # 4. Send or edit Now Playing embed to text channel
                if self.text_channel and self.loop_mode != LoopMode.TRACK:
                    try:
                        from cogs.music import PlayerControlsView
                        from utils.helpers import create_now_playing_embed

                        embed = create_now_playing_embed(
                            track=track_to_play,
                            volume=self.volume,
                            loop_mode=self.loop_mode,
                            queue_len=len(self.queue),
                        )
                        view = PlayerControlsView(self)

                        # If an initial loading message exists, edit it instead of sending a new one
                        if self._initial_message is not None:
                            msg_to_edit = self._initial_message
                            self._initial_message = None
                            try:
                                await msg_to_edit.edit(content=None, embed=embed, view=view)
                            except Exception:
                                await self.text_channel.send(embed=embed, view=view)
                        else:
                            await self.text_channel.send(embed=embed, view=view)
                    except Exception as e:
                        logger.debug("Failed to send/edit Now Playing embed: %s", e)

                # 5. Wait for track playback to complete or be skipped/stopped
                await self._playback_finished.wait()

                # Handle loop mode: queue (re-add played track to the end of the queue)
                if self.loop_mode == LoopMode.QUEUE and not self._skip_current_loop:
                    self.queue.add(track_to_play)

                # Save to previous track
                self.previous_track = track_to_play

            except asyncio.CancelledError:
                logger.info("Playback worker cancelled for guild %s", self.guild.id)
                break
            except Exception as e:
                logger.error("Unexpected error in playback worker: %s", e, exc_info=True)
                await asyncio.sleep(1)

    async def enqueue(self, track: Track, text_channel: discord.abc.Messageable | None = None) -> int:
        """Add a track to the queue and trigger worker if needed."""
        if text_channel:
            self.text_channel = text_channel

        position = self.queue.add(track)
        self.start_worker()
        self._new_track_event.set()
        return position

    def pause(self) -> bool:
        """Pause current playback."""
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()
            return True
        return False

    def resume(self) -> bool:
        """Resume current playback."""
        if self.voice_client and self.voice_client.is_paused():
            self.voice_client.resume()
            return True
        return False

    def skip(self) -> bool:
        """Skip currently playing track."""
        if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
            # If in track loop mode, skip should force advance to next track
            if self.loop_mode == LoopMode.TRACK:
                self._skip_current_loop = True
            self.voice_client.stop()
            return True
        return False

    def stop(self) -> None:
        """Stop playback and clear the queue."""
        self.queue.clear()
        self.current_track = None
        self._skip_current_loop = True
        if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
            self.voice_client.stop()
        self._reset_idle_timer()

    def set_volume(self, volume_percent: int) -> float:
        """Set playback volume between 0% and 200%.

        Args:
            volume_percent: Integer percentage (0 to 200).

        Returns:
            Normalized float volume (0.0 to 2.0).

        Raises:
            InvalidVolume: If percentage is outside 0..200.
        """
        if not 0 <= volume_percent <= 200:
            raise InvalidVolume(volume_percent)

        self.volume = volume_percent / 100.0
        if self.current_source:
            self.current_source.volume = self.volume
        return self.volume

    def set_loop_mode(self, mode: LoopMode) -> LoopMode:
        """Update loop playback mode."""
        self.loop_mode = mode
        return self.loop_mode

    def toggle_loop(self) -> LoopMode:
        """Cycle through loop modes: OFF -> TRACK -> QUEUE -> OFF."""
        if self.loop_mode == LoopMode.OFF:
            self.loop_mode = LoopMode.TRACK
        elif self.loop_mode == LoopMode.TRACK:
            self.loop_mode = LoopMode.QUEUE
        else:
            self.loop_mode = LoopMode.OFF
        return self.loop_mode

    async def cleanup(self) -> None:
        """Gracefully release all resources, voice connections, and cancel worker tasks."""
        self._is_destroyed = True
        self.stop()

        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()

        if self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()

        target_vc = self.voice_client or (
            self.guild.voice_client
            if isinstance(self.guild.voice_client, discord.VoiceClient)
            else None
        )
        if target_vc is not None:
            try:
                await target_vc.disconnect(force=True)
            except Exception as e:
                logger.debug("Error while disconnecting voice client: %s", e)
        self.voice_client = None
