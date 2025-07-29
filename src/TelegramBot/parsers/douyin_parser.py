# TelegramBot/parsers/douyin_parser.py
import logging
from pathlib import Path
from typing import Any, Coroutine

from telegram.helpers import escape_markdown

from DouyinDownload.douyin_post import DouyinPost
from DouyinDownload.douyin_image_post import DouyinImagePost
from TelegramBot.config import DOWNLOAD_TIMEOUT, PREVIEW_SIZE, DOUYIN_FETCH_IMAGE_TIMEOUT, DOUYIN_FETCH_VIDEO_TIMEOUT, \
    EXCLUDE_RESOLUTION
from .base import BaseParser, ParseResult, VideoQualityOption
from PublicMethods.functool_timeout import retry_on_timeout_async

logger = logging.getLogger(__name__)


class DouyinParser(BaseParser):
    def __init__(self, url: str, save_dir: Path):
        # 直接将接收到的参数传给父类
        super().__init__(url, save_dir)
        self.post = None
        self.image_post = None
        self.content_type = None

    async def peek(self) -> tuple[str, str]:
        vid, title = None, None
        self.post = DouyinPost(self.url)
        self.content_type = self.post.get_content_type(self.post.short_url)
        if self.content_type == 'image':
            self.image_post = DouyinImagePost(self.post.short_url)
            await self.image_post.fetch_details()
            vid = self.image_post.aweme_id
            title = self.image_post.title
            await self._parse_audio(self.image_post)
        else:
            await self.post.fetch_details()  # 只拿 video_id / title
            vid = self.post.video_id
            title = self.post.video_title or self.post.video_id
            await self._parse_audio(self.post)
        return vid, title

    @retry_on_timeout_async(60, 2)
    async def parse(self) -> Coroutine[Any, Any, ParseResult] | Any:
        """
        实现抖音视频/图集的解析和下载逻辑。
        """
        try:
            content_type_str = self.content_type
            if content_type_str == 'video':
                return await self._parse_video(self.post)
            elif content_type_str == 'image':
                return await self._parse_image_gallery(self.image_post)
            else:
                self.result.error_message = "未能识别抖音内容类型，或该内容不可用。"
                logger.warning(f"未能识别抖音短链接内容类型: {self.url}")
                return self.result

        except Exception as e:
            logger.exception("抖音解析失败: %s", e)
            self.result.error_message = f"解析抖音链接时出错: {e}"
            self.result.success = False
            return self.result

    async def _parse_audio(self, post):
        if post.audio:
            self.result.audio_uri = post.audio.url
            self.result.audio_title = post.audio.title

    async def _parse_video(self, post: DouyinPost) -> ParseResult:
        """解析视频并提供多分辨率选项"""
        # 获取所有可用的视频选项
        post.sort_options(by='resolution', descending=True, exclude_resolution=EXCLUDE_RESOLUTION)  # 按分辨率降序排列
        # post.deduplicate_by_resolution(keep='highest_bitrate')  # 每个分辨率保留最高码率

        # 填充基本信息
        self.result.vid = post.video_id
        self.result.title = post.video_title
        self.result.content_type = 'video'
        self.result.original_url = self.url

        # 3. 构建 quality_options 列表
        quality_options = []
        for opt in post.processed_video_options:
            name = f"{opt.resolution}p"
            if opt.size_mb:
                name += f" ({opt.size_mb:.1f}MB)"
            # 1. 拷贝所有属性
            params = opt.__dict__.copy()

            # 2. 覆盖/新增关键字段
            params.update({
                'resolution': opt.resolution,
                'quality_name': name,
                'download_url': opt.url,
                'size_mb': opt.size_mb or 0,
                'is_default': False,
            })

            # 3. 一次性传参
            quality_options.append(VideoQualityOption(**params))

        preview_option = None
        if option := post.pick_option_under_size(quality_options, max_mb=PREVIEW_SIZE):
            preview_option = option
            logger.info(f"匹配到小于 {PREVIEW_SIZE}M 的预览视频")
        if not preview_option:
            if option := post.pick_option_under_size(quality_options, max_mb=50):
                preview_option = option
                logger.info(f"匹配到小于 50M 的预览视频")

        # 兜底：选取整个列表里码率最高
        if not preview_option:
            quality_options = post.deduplicate_with_limit(quality_options)
            preview_option = quality_options[0]
        else:
            quality_options = post.deduplicate_with_limit(quality_options)
            quality_options.insert(0, preview_option)  # 作为首个展示用
            preview_option.is_default = True

        self.result.quality_options = quality_options
        self.result.needs_quality_selection = len(quality_options) > 0

        # 默认预览按钮
        # preview_option.is_default = True

        # 5. 下载并缓存这条预览视频
        gear = f"{preview_option.resolution}p"
        local_path = self.save_dir / f"{post.video_id}_{gear}.mp4"
        if preview_option.size_mb < 50:
            if not local_path.exists():
                logger.info(f"下载预览视频 -> {preview_option.quality_name}")
                download_path = post.download_option(preview_option, timeout=DOWNLOAD_TIMEOUT)
                Path(download_path).rename(local_path)
                logger.info(f"下载完成 -> {local_path.name}")
            else:
                logger.debug("预览视频已缓存 -> %s", local_path.name)

            # 添加媒体文件到结果，以便发送时使用 local_path
            self.result.add_media(
                local_path=local_path,
                file_type='video',
                width=preview_option.width,
                height=preview_option.height,
                duration=int(getattr(preview_option, 'duration', 0))
            )

        self.result.size_mb = preview_option.size_mb
        self.result.download_url = preview_option.download_url

        # 6. 设置 preview_url（兼容不下载时的在线预览）
        self.result.preview_url = preview_option.download_url

        # 强制调试：打印所有选项
        for i, opt in enumerate(self.result.quality_options):
            logger.info(
                f"选项{i}: {opt.resolution}p ({opt.size_mb}MB) default={opt.is_default} url={opt.download_url[:50]}...")

        self.result.success = True
        return self.result

    async def _parse_image_gallery(self, image_post: DouyinImagePost) -> ParseResult:
        self.result.vid = image_post.aweme_id
        self.result.title = image_post.title
        self.result.content_type = 'image_gallery'

        images = image_post.download_images(timeout=DOWNLOAD_TIMEOUT)
        if not images:
            self.result.error_message = "无法下载图集中的任何图片。"
            return self.result

        for img in images:
            if img.local_path and Path(img.local_path).exists():
                if img.file_type == 'photo':
                    self.result.add_media(local_path=img.local_path, file_type='photo')
                elif img.file_type == 'video':
                    self.result.add_media(local_path=img.local_path, file_type='video')
                else:
                    self.result.add_media(local_path=img.local_path, file_type='unknown')

        if self.result.media_items:
            self.result.success = True
        else:
            self.result.error_message = "图集下载完成，但未找到任何有效文件。"

        return self.result
