# TelegramBot/parsers/xhs_parse.py
"""
小红书解析
"""
import logging
import os.path
from pathlib import Path

from pywebio.input import SELECT

from .base import BaseParser, ParseResult
from XiaoHongShu.xhs_parser import XiaohongshuPost
from TelegramBot.config import XIAOHONGSHU_COOKIE

logger = logging.getLogger(__name__)


class XiaohongshuParser(BaseParser):
    """解析小红书 URL/ID，返回 `ParseResult`。"""

    def __init__(self, target: str, save_dir: Path | None = None):
        super().__init__(target, save_dir or None)
        self.post = None  # type: XiaohongshuPost
        self.data = None

    async def peek(self) -> tuple[str, str]:
        self.post = XiaohongshuPost()
        self.data = self.post.get_xhs(self.url, cookies=XIAOHONGSHU_COOKIE)
        vid = self.data['id']
        title = f"<b>{self.data['title']}</b>"
        if self.data['description']:
            desc = self.data['description']
            desc = desc.replace('\t', '\n\n')
            title += f"\n\n{desc}"
        self.result.vid = vid
        self.result.title = title
        return vid, title

    # ────────────────────────────────────────────────────────────────
    # public API
    # ────────────────────────────────────────────────────────────────
    async def parse(self):
        try:
            self.result.content_type = 'image_gallery'  # 按图集逻辑发送
            self.result.download_url_list.extend(self.data['images'])
            self.result.download_url_list.extend(self.data['videos'])

            self.post.parser_downloader(self.data)

            for video in self.post.videos:
                if not os.path.exists(video):
                    logger.warning(f"文件不存在 {video}")
                    continue
                self.result.add_media(local_path=video, file_type='video')
            for image in self.post.images:
                if not os.path.exists(image):
                    logger.warning(f"文件不存在 {image}")
                    continue
                self.result.add_media(local_path=image, file_type='photo')
            self.result.success = True
            return self.result
        except Exception as e:  # pragma: no cover
            logger.exception("Xiaohongshu 解析失败: %s", e)
            self.result.error_message = f"解析 Xiaohongshu 链接时出错: {e}"
            self.result.success = False
            return self.result
