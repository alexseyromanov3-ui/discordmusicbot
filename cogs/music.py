"""Discord Cog implementing slash commands and interactive buttons for music playback."""

import contextlib
import logging
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from music.player import MusicPlayer
from music.queue import LoopMode
from music.youtube import YouTubeService
from utils.errors import (
    InvalidVolume,
    TrackNotFound,
    VoiceConnectionError,
    YouTubeError,
)
from utils.helpers import (
    create_error_embed,
    create_now_playing_embed,
    create_queue_embed,
    create_success_embed,
    create_track_queued_embed,
)

logger = logging.getLogger(__name__)


def check_same_voice_channel(interaction: discord.Interaction) -> bool:
    """Validate that the invoking user is in the same voice channel as the bot."""
    if not interaction.guild:
        return False
    user = interaction.user
    if not isinstance(user, discord.Member) or not user.voice or not user.voice.channel:
        return False

    bot_voice = interaction.guild.voice_client
    if bot_voice and bot_voice.channel:
        return user.voice.channel == bot_voice.channel
    return True


class PlayerControlsView(discord.ui.View):
    """Interactive Discord UI View with playback control buttons."""

    def __init__(self, player: MusicPlayer) -> None:
        super().__init__(timeout=None)
        self.player = player
        self._update_buttons()

    def _update_buttons(self) -> None:
        """Update button styles and labels based on player state."""
        if self.player.is_paused:
            self.play_pause_button.label = "Возобновить"
            self.play_pause_button.emoji = "▶️"
            self.play_pause_button.style = discord.ButtonStyle.success
        else:
            self.play_pause_button.label = "Пауза"
            self.play_pause_button.emoji = "⏸️"
            self.play_pause_button.style = discord.ButtonStyle.secondary

        self.loop_button.label = f"Повтор: {self.player.loop_mode.value.upper()}"
        if self.player.loop_mode != LoopMode.OFF:
            self.loop_button.style = discord.ButtonStyle.primary
        else:
            self.loop_button.style = discord.ButtonStyle.secondary

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure the user interacting with buttons is connected to the same voice channel."""
        if not check_same_voice_channel(interaction):
            await interaction.response.send_message(
                "❌ Вы должны находиться в том же голосовом канале, что и бот!",
                ephemeral=True,
            )
            return False
        return True

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item[Any]
    ) -> None:
        """Handle unexpected errors during UI interaction to avoid interaction timeouts."""
        logger.error("Error in button interaction for item %s: %s", item, error, exc_info=True)
        if not interaction.response.is_done():
            with contextlib.suppress(Exception):
                await interaction.response.send_message(
                    "❌ Не удалось обработать нажатие кнопки.", ephemeral=True
                )

    @discord.ui.button(label="Пауза", style=discord.ButtonStyle.secondary, emoji="⏸️")
    async def play_pause_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if self.player.is_paused:
            self.player.resume()
        elif self.player.is_playing:
            self.player.pause()
        self._update_buttons()
        try:
            await interaction.response.edit_message(view=self)
        except Exception:
            with contextlib.suppress(Exception):
                await interaction.response.defer()

    @discord.ui.button(label="Пропустить", style=discord.ButtonStyle.secondary, emoji="⏭️")
    async def skip_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if self.player.skip():
            await interaction.response.send_message("⏭️ Трек пропущен.", ephemeral=True)
        else:
            await interaction.response.send_message("Нет активного трека для пропуска.", ephemeral=True)

    @discord.ui.button(label="Стоп", style=discord.ButtonStyle.danger, emoji="⏹️")
    async def stop_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.player.stop()
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except Exception:
            with contextlib.suppress(Exception):
                await interaction.response.send_message(
                    "⏹️ Воспроизведение остановлено.", ephemeral=True
                )
        self.stop()

    @discord.ui.button(label="Повтор: OFF", style=discord.ButtonStyle.secondary, emoji="🔁")
    async def loop_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        new_mode = self.player.toggle_loop()
        self._update_buttons()
        try:
            await interaction.response.edit_message(view=self)
        except Exception:
            await interaction.response.send_message(
                f"🔁 Режим повтора изменен на: **{new_mode.value.upper()}**", ephemeral=True
            )

    @discord.ui.button(label="Очередь", style=discord.ButtonStyle.secondary, emoji="📜")
    async def queue_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        embed = create_queue_embed(
            tracks=self.player.queue.tracks,
            current_track=self.player.current_track,
            page=1,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class MusicCog(commands.Cog, name="Music"):
    """Slash commands and handlers for audio playback."""

    def __init__(self, bot: commands.Bot, ffmpeg_path: str, idle_timeout: int = 300) -> None:
        self.bot = bot
        self.ffmpeg_path = ffmpeg_path
        self.idle_timeout = idle_timeout
        config = getattr(bot, "config", None)
        cookiefile = config.youtube_cookiefile if config else None
        cookies_browser = config.youtube_cookies_browser if config else None
        self.youtube_service = YouTubeService(
            cookiefile=cookiefile, cookies_browser=cookies_browser
        )
        self._players: dict[int, MusicPlayer] = {}

    def get_player(self, guild: discord.Guild) -> MusicPlayer:
        """Get or create the guild-isolated MusicPlayer instance."""
        if guild.id not in self._players:
            self._players[guild.id] = MusicPlayer(
                guild=guild,
                bot=self.bot,
                ffmpeg_path=self.ffmpeg_path,
                youtube_service=self.youtube_service,
                idle_timeout=self.idle_timeout,
            )
        return self._players[guild.id]

    async def cog_unload(self) -> None:
        """Clean up all players when cog is unloaded."""
        for player in self._players.values():
            await player.cleanup()
        self._players.clear()

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Monitor voice channels and trigger idle timer when channel is empty."""
        guild = member.guild
        bot_voice = guild.voice_client
        if not bot_voice or not bot_voice.channel:
            return

        bot_channel = bot_voice.channel
        if not isinstance(bot_channel, (discord.VoiceChannel, discord.StageChannel)):
            return

        # Check if the bot is the only non-bot member in the channel
        channel_members = [m for m in bot_channel.members if not m.bot]
        if len(channel_members) == 0:
            player = self._players.get(guild.id)
            if player and (player.is_playing or player.is_paused):
                logger.info(
                    "All users left voice channel %s in guild %s. Pausing and setting idle watchdog.",
                    bot_channel.id,
                    guild.id,
                )
                player.pause()
                player._reset_idle_timer()

    # --- Slash Commands ---

    @app_commands.command(name="play", description="Воспроизвести трек по ссылке или поисковому запросу")
    @app_commands.describe(query="Ссылка на YouTube или название трека")
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        """Queue and play audio from YouTube."""
        if not interaction.guild:
            await interaction.response.send_message("Команда доступна только на сервере.", ephemeral=True)
            return

        user = interaction.user
        if not isinstance(user, discord.Member) or not user.voice or not user.voice.channel:
            await interaction.response.send_message(
                "❌ Вы должны подключиться к голосовому каналу, чтобы воспроизводить музыку!",
                ephemeral=True,
            )
            return

        target_channel = user.voice.channel
        permissions = target_channel.permissions_for(interaction.guild.me)
        if not permissions.connect or not permissions.speak:
            await interaction.response.send_message(
                "❌ У бота нет прав для подключения или разговора в вашем голосовом канале!",
                ephemeral=True,
            )
            return

        player = self.get_player(interaction.guild)

        # Defer interaction since extraction can take 1-3 seconds
        await interaction.response.defer()

        # Connect or move
        try:
            await player.connect_voice(target_channel)
        except VoiceConnectionError as e:
            await interaction.followup.send(embed=create_error_embed(e.user_message))
            return

        # Extract track
        try:
            track = await self.youtube_service.get_track(query, requested_by=user.display_name)
        except (TrackNotFound, YouTubeError) as e:
            await interaction.followup.send(embed=create_error_embed(e.user_message))
            return
        except Exception as e:
            logger.error("Error searching track: %s", e, exc_info=True)
            await interaction.followup.send(
                embed=create_error_embed("❌ Произошла ошибка при поиске трека.")
            )
            return

        # Add to player
        is_already_active = player.is_playing or player.is_paused or (player.current_track is not None)
        target_msg_channel = (
            interaction.channel if isinstance(interaction.channel, discord.abc.Messageable) else None
        )
        position = await player.enqueue(track, text_channel=target_msg_channel)

        if is_already_active:
            embed = create_track_queued_embed(track, position)
            await interaction.followup.send(embed=embed)
        else:
            msg = await interaction.followup.send(f"🔍 Загружаю трек **{track.title}**...", wait=True)
            player.set_initial_message(msg)

    @app_commands.command(name="pause", description="Поставить воспроизведение на паузу")
    async def pause(self, interaction: discord.Interaction) -> None:
        """Pause playback."""
        if not interaction.guild:
            return
        if not check_same_voice_channel(interaction):
            await interaction.response.send_message(
                "❌ Вы должны быть в одном голосовом канале с ботом.", ephemeral=True
            )
            return

        player = self.get_player(interaction.guild)
        if player.pause():
            await interaction.response.send_message(
                embed=create_success_embed("Пауза", "⏸️ Воспроизведение приостановлено.")
            )
        else:
            await interaction.response.send_message(
                embed=create_error_embed("Сейчас ничего не воспроизводится."), ephemeral=True
            )

    @app_commands.command(name="resume", description="Возобновить воспроизведение")
    async def resume(self, interaction: discord.Interaction) -> None:
        """Resume playback."""
        if not interaction.guild:
            return
        if not check_same_voice_channel(interaction):
            await interaction.response.send_message(
                "❌ Вы должны быть в одном голосовом канале с ботом.", ephemeral=True
            )
            return

        player = self.get_player(interaction.guild)
        if player.resume():
            await interaction.response.send_message(
                embed=create_success_embed("Возобновление", "▶️ Воспроизведение возобновлено.")
            )
        else:
            await interaction.response.send_message(
                embed=create_error_embed("Воспроизведение не стоит на паузе."), ephemeral=True
            )

    @app_commands.command(name="skip", description="Пропустить текущий трек")
    async def skip(self, interaction: discord.Interaction) -> None:
        """Skip track."""
        if not interaction.guild:
            return
        if not check_same_voice_channel(interaction):
            await interaction.response.send_message(
                "❌ Вы должны быть в одном голосовом канале с ботом.", ephemeral=True
            )
            return

        player = self.get_player(interaction.guild)
        current = player.current_track
        if player.skip():
            title = current.title if current else "Текущий трек"
            await interaction.response.send_message(
                embed=create_success_embed("Пропуск", f"⏭️ Пропущен трек: **{title}**")
            )
        else:
            await interaction.response.send_message(
                embed=create_error_embed("Сейчас ничего не воспроизводится для пропуска."),
                ephemeral=True,
            )

    @app_commands.command(name="stop", description="Остановить плеер и очистить очередь")
    async def stop(self, interaction: discord.Interaction) -> None:
        """Stop playback and clear queue."""
        if not interaction.guild:
            return
        if not check_same_voice_channel(interaction):
            await interaction.response.send_message(
                "❌ Вы должны быть в одном голосовом канале с ботом.", ephemeral=True
            )
            return

        player = self.get_player(interaction.guild)
        player.stop()
        await interaction.response.send_message(
            embed=create_success_embed("Стоп", "⏹️ Плеер остановлен, очередь полностью очищена.")
        )

    @app_commands.command(name="queue", description="Показать текущую очередь воспроизведения")
    @app_commands.describe(page="Номер страницы")
    async def queue(self, interaction: discord.Interaction, page: int = 1) -> None:
        """Display queue."""
        if not interaction.guild:
            return

        player = self.get_player(interaction.guild)
        embed = create_queue_embed(
            tracks=player.queue.tracks,
            current_track=player.current_track,
            page=page,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="nowplaying", description="Информация о текущем треке")
    async def nowplaying(self, interaction: discord.Interaction) -> None:
        """Show currently playing track."""
        if not interaction.guild:
            return

        player = self.get_player(interaction.guild)
        if not player.current_track:
            await interaction.response.send_message(
                embed=create_error_embed("Сейчас ничего не воспроизводится."), ephemeral=True
            )
            return

        embed = create_now_playing_embed(
            track=player.current_track,
            volume=player.volume,
            loop_mode=player.loop_mode,
            queue_len=len(player.queue),
        )
        view = PlayerControlsView(player)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="volume", description="Изменить громкость воспроизведения")
    @app_commands.describe(percent="Громкость в процентах (0 - 200%)")
    async def volume(
        self, interaction: discord.Interaction, percent: app_commands.Range[int, 0, 200]
    ) -> None:
        """Adjust volume."""
        if not interaction.guild:
            return
        if not check_same_voice_channel(interaction):
            await interaction.response.send_message(
                "❌ Вы должны быть в одном голосовом канале с ботом.", ephemeral=True
            )
            return

        player = self.get_player(interaction.guild)
        try:
            player.set_volume(percent)
            await interaction.response.send_message(
                embed=create_success_embed("Громкость", f"🔊 Громкость установлена на **{percent}%**.")
            )
        except InvalidVolume as e:
            await interaction.response.send_message(
                embed=create_error_embed(e.user_message), ephemeral=True
            )

    @app_commands.command(name="loop", description="Установить режим повтора")
    @app_commands.describe(mode="Режим зацикливания")
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Выключен (off)", value="off"),
            app_commands.Choice(name="Текущий трек (track)", value="track"),
            app_commands.Choice(name="Вся очередь (queue)", value="queue"),
        ]
    )
    async def loop(
        self, interaction: discord.Interaction, mode: app_commands.Choice[str]
    ) -> None:
        """Set loop mode."""
        if not interaction.guild:
            return
        if not check_same_voice_channel(interaction):
            await interaction.response.send_message(
                "❌ Вы должны быть в одном голосовом канале с ботом.", ephemeral=True
            )
            return

        player = self.get_player(interaction.guild)
        selected_mode = LoopMode(mode.value)
        player.set_loop_mode(selected_mode)

        mode_names = {
            LoopMode.OFF: "Выключен",
            LoopMode.TRACK: "Текущий трек",
            LoopMode.QUEUE: "Вся очередь",
        }
        await interaction.response.send_message(
            embed=create_success_embed(
                "Режим повтора", f"🔁 Режим повтора установлен на: **{mode_names[selected_mode]}**"
            )
        )


async def setup(bot: commands.Bot) -> None:
    """Extension entry point for loading the cog."""
    config = getattr(bot, "config", None)
    ffmpeg_path = config.ffmpeg_path if config else "ffmpeg"
    idle_timeout = config.idle_timeout if config else 300
    await bot.add_cog(MusicCog(bot, ffmpeg_path=ffmpeg_path, idle_timeout=idle_timeout))
