# TelegramBot/parsers/bilibili_parser.py
"""Bilibili 解析器

将旧版 `bilibili.py` 的下载/解析逻辑抽离到专用解析器，
供 `handlers/generic_handler.py` 调用。

- 保留所有日志打点和中文备注原文；
- 对于 >50 MB 的视频仅返回直链 Markdown 链接；
- 避免在解析层执行网络上传工作，上传由上层 handler 处理。
"""
from __future__ import annotations

import logging
from pathlib import Path
from telegram.helpers import escape_markdown

from BilibiliDownload.bilibili_post import BilibiliPost
from PublicMethods.tools import check_file_size
from TelegramBot.config import BILI_SAVE_DIR, BILI_COOKIE
from .base import BaseParser, ParseResult
from PublicMethods.functool_timeout import timeout

logger = logging.getLogger(__name__)

INVALID = r'\\/:*?"<>|'


def _safe_filename(name: str, max_len: int = 80) -> str:
    safe = "".join("_" if c in INVALID else c for c in name).strip()
    return safe[:max_len]


class BilibiliParser(BaseParser):
    """解析 bilibili 视频 URL，返回标准 `ParseResult`."""

    def __init__(self, url: str, save_dir: Path | None = None):
        super().__init__(url, save_dir or BILI_SAVE_DIR)
        self.post = None

    def peek(self) -> tuple[str, str]:
        self.post = BilibiliPost(self.url, threads=8, cookie=BILI_COOKIE).fetch()
        vid = self.post.bvid
        title = self.post.title or self.post.bvid
        return vid, title
    # ────────────────────────────────────────────────────────────────
    # public API
    # ────────────────────────────────────────────────────────────────
    def parse(self) -> ParseResult:  # noqa: C901  (保持复杂度便于保留原始日志)
        try:
            post = self.post
            post.save_dir = self.save_dir
            post.merge_dir = self.save_dir

            # ① 预览视频 (无需音频合并)
            if post.preview_video:
                self.result.bili_preview_video = True
                return self._parse_preview(post)

            # ② 正常番剧/视频
            return self._parse_video(post)

        except Exception as e:  # pragma: no cover
            logger.exception("Bilibili 解析失败: %s", e)
            self.result.error_message = f"解析 Bilibili 链接时出错: {e}"
            self.result.success = False
            return self.result

    # ────────────────────────────────────────────────────────────────
    # internal helpers
    # ────────────────────────────────────────────────────────────────
    def _parse_preview(self, post: BilibiliPost) -> ParseResult:
        """处理卡点 / 预览视频("preview_video")场景。"""
        pre_name = post.preview_video_download()
        local_path = self.save_dir / f"{pre_name}.mp4"

        self.result.title = _safe_filename(post.title or post.bvid)
        self.result.vid = post.bvid
        self.result.download_url = post.preview_video
        self.result.size_mb = check_file_size(local_path)
        self.result.content_type = 'video'
        logger.debug("命中 preview 视频 -> %s", local_path.name)

        self.result.add_media(local_path=local_path, file_type='video')
        self.result.success = True
        return self.result

    @timeout(40)
    def _parse_video(self, post: BilibiliPost) -> ParseResult:
        """常规 bilibili 视频解析+合并。"""
        # ---- 预处理 ----
        post.filter_by_size(max_mb=50)
        url = post.selected_video['url']
        gear_name = post.gear_name  # e.g. 1080P
        local_path = self.save_dir / f"{post.bvid}_{gear_name}_merged.mp4"

        self.result.title = _safe_filename(post.title or post.bvid)
        self.result.vid = post.bvid
        self.result.download_url = url  # 最终直链 (用于大文件 fallback)
        self.result.content_type = 'video'
        self.result.size_mb = post.size_mb
        self.result.width = post.width
        self.result.height = post.height
        self.result.duration = post.duration
        logger.debug("初始化size: %sMB", post.size_mb)  # 保留原日志

        # ---- >50 MB 文件：直接返回 Markdown 链接 ----
        if post.size_mb > 50:
            md_link = (
                f"[{escape_markdown(self.result.title, version=2)}]"
                f"({escape_markdown(url, version=2)})"
            )
            self.result.text_message = (
                f"✅ 上传完成！由于视频超过 50 MB，请点击下方链接下载：\n{md_link}"
            )
            self.result.content_type = 'link'
            self.result.success = True
            logger.debug("文件大于50MB，返回直链Markdown.")
            return self.result

        # ---- 50 MB 以内：查看本地 / 下载 / 合并 ----
        if not local_path.exists():
            logger.info("开始下载 -> %s", url)
            vpath, apath = post.download()  # 多线程下载
            v_size = check_file_size(vpath)
            a_size = check_file_size(apath)
            logger.debug("视频大小:%sMB", v_size)
            logger.debug("音频大小:%sMB", a_size)
            merged_size = v_size + a_size
            logger.debug("预估大小合计:%sMB", merged_size)
            out = post.merge(vpath, apath)
            logger.info("下载完成 -> %s", out)
            # 由于 post.merge 直接输出到 save_dir，我们使用返回值 out
            local_path = Path(out)
            self.result.size_mb = check_file_size(local_path, ndigits=2)
            logger.debug("合并完成，大小合计:%sMB", self.result.size_mb)
        else:
            logger.debug("命中磁盘缓存 -> %s", local_path.name)
            self.result.size_mb = check_file_size(local_path)

        # ---- 填充 ParseResult ----
        self.result.add_media(
            local_path=local_path,
            file_type='video',
            width=self.result.width,
            height=self.result.height,
            duration=int(self.result.duration),
        )
        self.result.success = True
        return self.result
