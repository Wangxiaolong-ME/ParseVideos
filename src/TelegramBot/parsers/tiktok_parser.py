# TelegramBot/parsers/tiktok_parser.py
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Coroutine, List, Optional


from TikTokDownload.tiktok_post import TikTokPostManager
from TelegramBot.config import DOWNLOAD_TIMEOUT, PREVIEW_SIZE, TIKTOK_NEEDS_QUALITY_SELECTION_SWITCH
from .base import BaseParser, ParseResult, VideoQualityOption
from PublicMethods.functool_timeout import retry_on_timeout_async

logger = logging.getLogger(__name__)


class TikTokParser(BaseParser):
    """Parse TikTok share‑links and prepare downloadable media for Telegram."""

    def __init__(self, url: str, save_dir: Path):
        super().__init__(url, save_dir)
        self.manager: Optional[TikTokPostManager] = None
        self.content_type: Optional[str] = None  # 'video' | 'image'

    # ------------------------------------------------------------------
    # Quick‑look helpers
    # ------------------------------------------------------------------
    async def peek(self) -> tuple[str, str]:
        """Resolve *aweme_id* & title without doing full download."""
        # Create manager, resolve and cache data
        self.manager = TikTokPostManager(self.url, save_dir=str(self.save_dir))
        await self.manager.fetch_details()

        data = self.manager.tiktok_post_data
        if not data:
            raise RuntimeError("TikTokPostManager.fetch_details() failed to return metadata")

        self.content_type = "image" if data.is_image_album else "video"
        vid = data.aweme_id
        title = data.title or vid

        self._parse_audio(data)
        return vid, title

    # ------------------------------------------------------------------
    # Core entry point
    # ------------------------------------------------------------------
    async def parse(self) -> Coroutine[Any, Any, ParseResult] | ParseResult:  # noqa: D401
        """Main entry – heavy work. Returns a populated ``ParseResult``."""
        try:
            # Ensure we have fetched initial data
            if not self.manager:
                self.manager = TikTokPostManager(self.url, save_dir=str(self.save_dir))
                await self.manager.fetch_details()

            data = self.manager.tiktok_post_data
            if not data:
                raise RuntimeError("TikTok metadata unavailable after fetch_details()")

            self.content_type = "image" if data.is_image_album else "video"

            if self.content_type == "video":
                return await self._parse_video()
            elif self.content_type == "image":
                return await self._parse_image_gallery()
            else:
                self.result.error_message = "未能识别TikTok内容类型，或该内容不可用。"
                return self.result
        except Exception as exc:  # noqa: BLE001
            logger.exception("TikTok 解析失败: %s", exc)
            self.result.error_message = f"解析 TikTok 链接时出错: {exc}"
            self.result.success = False
            return self.result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _parse_audio(self, data):
        """Fill audio fields in ``self.result`` if background music exists."""
        music = getattr(data, "music", None)
        if music and music.url:
            self.result.audio_uri = music.url
            self.result.audio_title = music.title or "TikTok Music"

    # ------------------------------------------------------------------
    # Video flow
    # ------------------------------------------------------------------
    @retry_on_timeout_async(30, 2)
    async def _parse_video(self) -> ParseResult:  # noqa: C901 (complexity ok – similar to DouyinParser)
        post = self.manager  # type: ignore  # Already ensured non‑None

        # 1) Arrange available qualities
        post.deduplicate_video_options_by_resolution(keep="highest_bitrate")

        vid = post.tiktok_post_data.aweme_id
        title = post.tiktok_post_data.title or vid

        self.result.vid = vid
        self.result.title = title
        self.result.content_type = "video"
        self.result.original_url = self.url

        # 2) Build quality_options list for Telegram inline‑keyboard, etc.
        quality_options: List[VideoQualityOption] = []
        for opt in post.processed_video_options:
            quality_name = f"{opt.resolution}p"
            if opt.size_mb:
                quality_name += f" ({opt.size_mb:.1f}MB)"
            params = opt.__dict__.copy()  # Keep all original attributes for later use
            params.update(
                {
                    "resolution": opt.resolution,
                    "quality_name": quality_name,
                    "download_url": opt.url,
                    "size_mb": opt.size_mb or 0,
                    "is_default": False,
                    "bit_rate": opt.bit_rate,
                }
            )
            quality_options.append(VideoQualityOption(**params))

        # 3) Decide preview option (≤ PREVIEW_SIZE MB preferred)
        preview_option = None
        if option := self._pick_option_under_size(quality_options, max_mb=PREVIEW_SIZE):
            preview_option = option
            logger.info(f"匹配到小于 {PREVIEW_SIZE}M 的预览视频")
        if not preview_option:
            if option := self._pick_option_under_size(quality_options, max_mb=50):
                preview_option = option
                logger.info(f"匹配到小于 50M 的预览视频")

        if not preview_option and quality_options:
            # Fallback: pick highest resolution
            preview_option = max(quality_options, key=lambda x: x.resolution)

        # 4) Deduplicate final list & make preview default
        quality_options = self._deduplicate_by_resolution(quality_options)
        if preview_option:
            for q in quality_options:
                q.is_default = False
            preview_option.is_default = True
            # 将预览选项放置在索引 0 处以方便 UI
            quality_options = [preview_option] + [q for q in quality_options if q is not preview_option]

        if TIKTOK_NEEDS_QUALITY_SELECTION_SWITCH:
            # 将最后视频对象中的URL都重定向一遍替换为真实下载地址
            for option in quality_options:
                option.download_url = post._get_real_download_url(option.url)
            self.result.needs_quality_selection = len(quality_options) > 0

        self.result.quality_options = quality_options

        # 5) 下载/缓存预览视频（仅在视频足够小的情况下）
        if preview_option and preview_option.size_mb < 50:
            gear = getattr(preview_option, "gear_name", f"{preview_option.resolution}p")
            local_path = self.save_dir / f"{vid}_{gear}.mp4"

            if not local_path.exists():
                logger.info("下载预览视频 -> %s", preview_option.quality_name)
                await post.download_video(preview_option, timeout=DOWNLOAD_TIMEOUT)
                # Files are saved inside ``post.save_dir``; move to unified ``self.save_dir``
                original_path = Path(post.save_dir) / local_path.name
                if original_path.exists():
                    original_path.rename(local_path)
                else:
                    # In case downloader saved directly to target dir
                    logger.debug("Download saved directly to target directory or path missing: %s", original_path)
            else:
                logger.debug("预览视频已缓存 -> %s", local_path.name)

            # Attach media to result
            self.result.add_media(
                local_path=local_path,
                file_type="video",
                width=getattr(preview_option, "width", 0),
                height=getattr(preview_option, "height", 0),
                duration=int(getattr(preview_option, "duration", 0)),
            )

        if preview_option:
            self.result.size_mb = preview_option.size_mb
            self.result.download_url = preview_option.download_url
            self.result.preview_url = preview_option.download_url

        self.result.success = True
        return self.result

    # ------------------------------------------------------------------
    # Image‑album flow
    # ------------------------------------------------------------------
    @retry_on_timeout_async(60, 2)
    async def _parse_image_gallery(self) -> ParseResult:
        post = self.manager  # type: ignore
        data = post.tiktok_post_data

        self.result.vid = data.aweme_id
        self.result.title = data.title or data.aweme_id
        self.result.content_type = "image_gallery"

        # Download every image (concurrent inside TikTokPostManager)
        image_paths = await post.download_image_album(timeout=DOWNLOAD_TIMEOUT)
        if not image_paths:
            self.result.error_message = "无法下载图集中的任何图片。"
            return self.result

        for path in image_paths:
            p = Path(path)
            if p.exists():
                self.result.add_media(local_path=p, file_type="photo")

        self.result.success = bool(self.result.media_items)
        if not self.result.success:
            self.result.error_message = "图集下载完成，但未找到任何有效文件。"

        return self.result

    # ------------------------------------------------------------------
    # Utility helpers (local only)
    # ------------------------------------------------------------------
    @staticmethod
    def _pick_option_under_size(options: List[VideoQualityOption], max_mb: float) -> Optional[VideoQualityOption]:
        """Return the first option within *max_mb* size limit."""
        for opt in options:
            if opt.size_mb and opt.size_mb <= max_mb:
                return opt
        return None

    @staticmethod
    def _deduplicate_by_resolution(options: List[VideoQualityOption]) -> List[VideoQualityOption]:
        """Keep only one option per resolution (prefer smallest file size)."""
        best: dict[int, VideoQualityOption] = {}
        for opt in options:
            res = opt.resolution
            if res not in best or (opt.size_mb and opt.size_mb < best[res].size_mb):
                best[res] = opt
        return sorted(best.values(), key=lambda x: x.resolution, reverse=True)
