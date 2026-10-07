"""Main entry point for the Discord Music Bot."""

import asyncio
import logging
import signal
import sys

import discord
from discord.ext import commands

from config import Config, setup_logging

logger = logging.getLogger("discord_music_bot")


class MusicBot(commands.Bot):
    """Custom Bot class handling extension loading, slash command sync, and graceful shutdown."""

    def __init__(self, config: Config) -> None:
        self.config = config
        intents = discord.Intents.default()
        intents.guilds = True
        intents.voice_states = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
        )

    async def setup_hook(self) -> None:
        """Executed during bot startup before connecting to Discord Gateway."""
        logger.info("Loading music extension...")
        await self.load_extension("cogs.music")

        logger.info("Synchronizing slash application commands...")
        try:
            synced = await self.tree.sync()
            logger.info("Successfully synced %d slash commands.", len(synced))
        except Exception as e:
            logger.error("Failed to sync slash commands: %s", e, exc_info=True)

    async def on_ready(self) -> None:
        """Triggered when bot is authenticated and ready."""
        logger.info("Bot logged in as: %s (ID: %s)", self.user, self.user.id if self.user else "N/A")
        logger.info("Connected to %d guild(s).", len(self.guilds))
        activity = discord.Activity(
            type=discord.ActivityType.listening,
            name="/play | YouTube Music",
        )
        await self.change_presence(activity=activity)

    async def close(self) -> None:
        """Gracefully release all resources, voice connections, and cogs."""
        logger.info("Initiating graceful bot shutdown...")

        # Unload music cog to disconnect all voice clients and terminate player tasks
        music_cog = self.get_cog("Music")
        if music_cog:
            try:
                await music_cog.cog_unload()
            except Exception as e:
                logger.error("Error unloading Music cog: %s", e)

        # Disconnect any remaining voice clients
        for voice_client in list(self.voice_clients):
            try:
                if isinstance(voice_client, discord.VoiceClient) and voice_client.is_connected():
                    await voice_client.disconnect(force=True)
            except Exception as e:
                logger.debug("Error disconnecting voice client: %s", e)

        await super().close()
        logger.info("Bot shutdown complete.")


def handle_signals(bot: MusicBot, loop: asyncio.AbstractEventLoop) -> None:
    """Register system signal handlers for graceful shutdown."""
    def _signal_handler() -> None:
        logger.info("Received termination signal, stopping bot...")
        asyncio.create_task(bot.close())

    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _signal_handler)


def main() -> None:
    """Initialize configuration and launch the bot."""
    config = Config.load()
    setup_logging(config.log_level)

    if not config.discord_token:
        logger.critical(
            "DISCORD_TOKEN is missing! Please create a .env file and set DISCORD_TOKEN. "
            "See .env.example for details."
        )
        sys.exit(1)

    logger.info("Using FFmpeg executable: %s", config.ffmpeg_path)
    logger.info("Idle timeout set to %d seconds.", config.idle_timeout)

    bot = MusicBot(config=config)

    # Signal handlers
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    handle_signals(bot, loop)

    try:
        loop.run_until_complete(bot.start(config.discord_token))
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received.")
        loop.run_until_complete(bot.close())
    except Exception as e:
        logger.critical("Fatal error running bot: %s", e, exc_info=True)
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


if __name__ == "__main__":
    main()
