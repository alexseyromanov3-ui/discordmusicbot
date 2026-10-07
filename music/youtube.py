"""YouTube extraction and search service using yt-dlp."""

import asyncio
import json
import logging
import os
import re
import shutil
import urllib.request
from typing import Any
from urllib.parse import urlparse

import yt_dlp

from models.track import Track
from utils.errors import TrackNotFound, YouTubeError

logger = logging.getLogger(__name__)

YTDL_OPTIONS: dict[str, Any] = {
    "format": "bestaudio[protocol^=http]/bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",  # bind to IPv4 since IPv6 can cause issues
    "extract_flat": False,
    "skip_download": True,
    "live_from_start": False,
}


def is_url(query: str) -> bool:
    """Check if the provided query is a valid HTTP/HTTPS URL."""
    try:
        result = urlparse(query)
        return bool(result.scheme in ("http", "https") and result.netloc)
    except Exception:
        return False


class YouTubeService:
    """Service for extracting audio metadata and stream URLs from YouTube."""

    def __init__(
        self,
        ytdl_options: dict[str, Any] | None = None,
        cookiefile: str | None = None,
        cookies_browser: str | None = None,
    ) -> None:
        opts = YTDL_OPTIONS.copy()

        # Enable Node.js for solving n-sig and JS challenges if available
        if shutil.which("node"):
            opts["js_runtimes"] = {"node": {}}
            opts["remote_components"] = ["ejs:github"]

        # Cookie authentication for age-restricted videos
        if cookiefile and os.path.isfile(cookiefile):
            logger.info("Using YouTube cookiefile: %s", cookiefile)
            opts["cookiefile"] = cookiefile
        elif os.path.isfile("cookies.txt"):
            logger.info("Using detected cookies.txt for YouTube authentication.")
            opts["cookiefile"] = "cookies.txt"

        if cookies_browser:
            logger.info("Using YouTube cookies from browser: %s", cookies_browser)
            opts["cookiesfrombrowser"] = (cookies_browser,)

        if ytdl_options:
            opts.update(ytdl_options)

        self._ytdl = yt_dlp.YoutubeDL(opts)

    def _fetch_oembed(self, webpage_url: str) -> dict[str, Any] | None:
        """Fetch basic public metadata for a YouTube video via oEmbed API or proxy."""
        clean_url = webpage_url
        yt_id_match = re.search(
            r"(?:v=|\/|youtu\.be\/|^)([a-zA-Z0-9_-]{11})(?:[&?]|$)", webpage_url
        )
        if yt_id_match and (
            not is_url(webpage_url) or "youtube.com" in webpage_url or "youtu.be" in webpage_url
        ):
            clean_url = f"https://www.youtube.com/watch?v={yt_id_match.group(1)}"

        # 1. Try official YouTube oEmbed API
        try:
            oembed_url = f"https://www.youtube.com/oembed?url={clean_url}&format=json"
            req = urllib.request.Request(
                oembed_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = dict(json.loads(resp.read().decode("utf-8")))
                if data.get("title"):
                    return data
        except Exception as e:
            logger.debug("YouTube oEmbed fetch failed for %s: %s", clean_url, e)

        # 2. Proxy oEmbed fallback (noembed.com) when youtube.com is blocked by DNS or firewall
        try:
            noembed_url = f"https://noembed.com/embed?url={clean_url}"
            req = urllib.request.Request(
                noembed_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = dict(json.loads(resp.read().decode("utf-8")))
                if data.get("title"):
                    logger.info("Resolved YouTube metadata via proxy oEmbed: '%s'", data.get("title"))
                    return data
        except Exception as e:
            logger.debug("noembed proxy fetch failed for %s: %s", clean_url, e)

        return None

    def _fallback_soundcloud(self, search_target: str) -> dict[str, Any] | None:
        """Attempt to resolve track stream through SoundCloud search as fallback."""
        try:
            logger.info("Attempting SoundCloud fallback for: %s", search_target)
            flat_opts: dict[str, Any] = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": "in_playlist",
                "ignoreerrors": True,
            }
            with yt_dlp.YoutubeDL(flat_opts) as sc_searcher:
                search_results = sc_searcher.extract_info(
                    f"scsearch5:{search_target}", download=False
                )

            entries = search_results.get("entries", []) if isinstance(search_results, dict) else []
            for entry in entries:
                if not isinstance(entry, dict) or not entry.get("url"):
                    continue
                try:
                    full_info = self._ytdl.extract_info(entry["url"], download=False)
                    if isinstance(full_info, dict) and full_info.get("url"):
                        logger.info("SoundCloud fallback succeeded: '%s'", full_info.get("title"))
                        return dict(full_info)
                except Exception as entry_err:
                    logger.debug("Skipping SoundCloud entry due to error: %s", entry_err)
                    continue
        except Exception as e:
            logger.warning("SoundCloud fallback search failed for %s: %s", search_target, e)
        return None

    def _sync_extract(self, search_target: str) -> dict[str, Any]:
        """Synchronous extraction method run in a separate thread."""
        logger.debug("Extracting info with yt-dlp: %s", search_target)
        try:
            info = self._ytdl.extract_info(search_target, download=False)
            if not isinstance(info, dict):
                raise TrackNotFound(search_target)
            return dict(info)
        except yt_dlp.utils.DownloadError as e:
            err_msg = str(e)
            logger.warning("yt-dlp DownloadError: %s", err_msg)

            # Check if this error is eligible for fallback (age gate, bot challenge, network/DNS error)
            should_fallback = any(
                phrase.lower() in err_msg.lower()
                for phrase in (
                    "sign in to confirm your age",
                    "age-restricted",
                    "sign in to confirm you’re not a bot",
                    "sign in to confirm you're not a bot",
                    "channel's members",
                    "getaddrinfo failed",
                    "failed to resolve",
                    "timed out",
                    "connection refused",
                    "transporterror",
                    "http error 429",
                    "http error 403",
                    "unable to download api page",
                    "incompleteread",
                )
            )

            if should_fallback:
                logger.info(
                    "Encountered YouTube limitation or network block (%s). Attempting automatic fallback chain...",
                    err_msg[:80],
                )
                title_for_search: str | None = None

                # If target is a YouTube URL or video ID, extract title via public oEmbed API / proxy
                yt_id_match = re.search(
                    r"(?:v=|\/|youtu\.be\/|^)([a-zA-Z0-9_-]{11})(?:[&?]|$)", search_target
                )
                if is_url(search_target) or yt_id_match:
                    oembed = self._fetch_oembed(search_target)
                    if oembed and oembed.get("title"):
                        title_for_search = str(oembed.get("title"))

                # If query itself was search terms, use query directly
                if not title_for_search and not is_url(search_target):
                    title_for_search = (
                        search_target.removeprefix("ytsearch1:").removeprefix("ytsearch:")
                    )

                # Try SoundCloud fallback search
                if title_for_search:
                    sc_result = self._fallback_soundcloud(title_for_search)
                    if sc_result:
                        logger.info(
                            "Recovered track via SoundCloud fallback: '%s'",
                            title_for_search,
                        )
                        if is_url(search_target):
                            sc_result["original_url"] = search_target
                        return sc_result

                if "age" in err_msg.lower():
                    raise YouTubeError(
                        "🔞 Это видео имеет возрастное ограничение (18+), и альтернативные источники не найдены. "
                        "Для его воспроизведения требуется файл `cookies.txt` или выберите другой трек."
                    ) from e
                raise YouTubeError(
                    f"❌ Не удалось загрузить аудио с YouTube ({err_msg[:70]}), и резервные источники не найдены."
                ) from e

            if "Private video" in err_msg:
                raise YouTubeError("🔒 Это видео приватное и недоступно для воспроизведения.") from e
            if "Video unavailable" in err_msg:
                raise YouTubeError("❌ Это видео недоступно на YouTube.") from e
            raise YouTubeError(f"Не удалось загрузить аудио: {err_msg[:120]}") from e
        except yt_dlp.utils.ExtractorError as e:
            logger.warning("yt-dlp ExtractorError: %s", e)
            raise YouTubeError(f"Ошибка парсера: {str(e)[:100]}") from e
        except Exception as e:
            logger.error("Unexpected yt-dlp extraction error: %s", e, exc_info=True)
            if "yandex" in search_target.lower():
                raise YouTubeError(
                    "❌ Прямые ссылки на Яндекс Музыку не поддерживаются (сервис блокирует сторонние плееры). "
                    "Пожалуйста, введите название трека текстом (например: `/play Название трека`) или укажите ссылку на YouTube/SoundCloud."
                ) from e
            raise YouTubeError(f"Непредвиденная ошибка при поиске: {str(e)[:100]}") from e

    async def get_track(self, query: str, requested_by: str) -> Track:
        """Resolve a URL or search query into a playable Track object.

        Args:
            query: YouTube URL or search keywords.
            requested_by: User name or mention who initiated the request.

        Returns:
            Track instance with stream URL and metadata.

        Raises:
            TrackNotFound: If query returned no results.
            YouTubeError: If extraction failed.
        """
        clean_query = query.strip()
        if not clean_query:
            raise TrackNotFound("Пустой запрос")

        search_target = clean_query if is_url(clean_query) else f"ytsearch1:{clean_query}"

        # Run extraction in worker thread so event loop remains responsive
        info = await asyncio.to_thread(self._sync_extract, search_target)

        # Handle search result list
        if "entries" in info:
            entries = info.get("entries")
            if not entries:
                raise TrackNotFound(clean_query)
            info = entries[0]
            if not info:
                raise TrackNotFound(clean_query)

        # Extract direct stream URL
        stream_url = info.get("url")
        if not stream_url:
            # Fallback to formats if direct url is not top-level
            formats = info.get("formats", [])
            audio_formats = [f for f in formats if f.get("acodec") != "none"]
            if audio_formats:
                stream_url = audio_formats[-1].get("url")

        if not stream_url:
            raise YouTubeError("Не найден подходящий аудиопоток для воспроизведения.")

        title = info.get("title") or "Неизвестный трек"
        webpage_url = info.get("webpage_url") or info.get("original_url") or clean_query
        raw_duration = info.get("duration")
        duration = int(raw_duration) if raw_duration is not None else None
        thumbnail = info.get("thumbnail")
        uploader = info.get("uploader") or info.get("channel") or info.get("artist")
        is_live = bool(info.get("is_live", False))

        return Track(
            title=title,
            url=stream_url,
            webpage_url=webpage_url,
            duration=duration,
            thumbnail=thumbnail,
            uploader=uploader,
            requested_by=requested_by,
            is_live=is_live,
        )
