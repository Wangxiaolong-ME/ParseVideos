# TelegramBot/parsers/douyin_parser.py
import logging
from pathlib import Path
from telegram.helpers import escape_markdown

from DouyinDownload.douyin_post import DouyinPost
from DouyinDownload.douyin_image_post import DouyinImagePost
from TelegramBot.config import DOWNLOAD_TIMEOUT,DOUYIN_FETCH_IMAGE_TIMEOUT, DOUYIN_FETCH_VIDEO_TIMEOUT
from .base import BaseParser, ParseResult
from PublicMethods.functool_timeout import timeout

logger = logging.getLogger(__name__)


class DouyinParser(BaseParser):
    def __init__(self, url: str, save_dir: Path):
        # 直接将接收到的参数传给父类
        super().__init__(url, save_dir)
        self.post = None

    def peek(self) -> tuple[str, str]:
        self.post = DouyinPost(self.url)
        self.post.fetch_details()  # 只拿 video_id / title
        vid = self.post.video_id
        title = self.post.video_title or self.post.video_id
        return vid, title

    def parse(self) -> ParseResult:
        """
        实现抖音视频/图集的解析和下载逻辑。
        """
        try:
            post = self.post
            content_type_str = post.get_content_type(post.short_url)

            if content_type_str == 'video':
                return self._parse_video(post)
            elif content_type_str == 'image':
                return self._parse_image_gallery(post.short_url)
            else:
                self.result.error_message = "未能识别抖音内容类型，或该内容不可用。"
                logger.warning(f"未能识别抖音短链接内容类型: {self.url}")
                return self.result

        except Exception as e:
            logger.exception("抖音解析失败: %s", e)
            self.result.error_message = f"解析抖音链接时出错: {e}"
            self.result.success = False
            return self.result

    @timeout(DOUYIN_FETCH_VIDEO_TIMEOUT)
    def _parse_video(self, post: DouyinPost) -> ParseResult:
        # post.fetch_details()
        post.filter_by_size(max_mb=50)
        post.deduplicate_by_resolution()
        option = post.get_option(720)

        # 填充基本信息到标准结果中
        self.result.vid = post.video_id
        self.result.title = post.video_title
        self.result.download_url = option.url
        self.result.size_mb = option.size_mb
        self.result.content_type = 'video'

        # 文件过大处理逻辑
        smallest = min(post.processed_video_options, key=lambda o: o.size_mb)
        if smallest.size_mb > 50:
            md_link = f"[{escape_markdown(self.result.title, version=2)}]({escape_markdown(smallest.url, version=2)})"
            self.result.text_message = f"视频超过 50 MB，点击下方链接下载：\n{md_link}"
            self.result.content_type = 'link'
            self.result.success = True
            return self.result

        # 本地路径
        local_path = self.save_dir / f"{post.video_id}_{option.gear_name}.mp4"

        # 命中磁盘缓存（注意：file_id 缓存逻辑移到通用处理器中）
        if local_path.exists():
            logger.debug("命中磁盘缓存 -> %s", local_path.name)
        else:
            logger.info("开始下载抖音视频 -> %s", self.url)
            v_path = post.download_option(option, timeout=DOWNLOAD_TIMEOUT)
            Path(v_path).rename(local_path)
            logger.info("下载完成 -> %s", local_path.name)

        # 将媒体文件添加到结果
        self.result.add_media(
            local_path=local_path,
            file_type='video',
            width=option.width,
            height=option.height,
            duration=int(option.duration / 1000)
        )
        self.result.success = True
        return self.result

    @timeout(DOUYIN_FETCH_IMAGE_TIMEOUT)
    def _parse_image_gallery(self, url: str) -> ParseResult:
        image_post = DouyinImagePost(url)
        image_post.fetch_details()

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