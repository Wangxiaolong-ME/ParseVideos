# TelegramBot/parsers/music_parser.py
"""网易云音乐解析器

抽离旧版 `music.py` 中的下载/缓存逻辑，统一为 `BaseParser` 接口。
"""
import logging
from pathlib import Path

from MusicDownload.download import download_single
from MusicDownload.download_music import get_download_link
from TelegramBot.config import MUSIC_SAVE_DIR
from .base import BaseParser, ParseResult

logger = logging.getLogger(__name__)


class MusicParser(BaseParser):
    """解析网易云音乐 URL/ID，返回 `ParseResult`。"""

    def __init__(self, target: str, save_dir: Path | None = None):
        super().__init__(target, save_dir or MUSIC_SAVE_DIR)
        self.target = target  # 兼容旧变量名
        self.song_name = None
        self.song_id = None

    async def peek(self) -> tuple[str, str]:
        _, song_name, song_id = get_download_link(self.target, return_song_id=True)
        self.song_id = f"MUSIC{song_id}"
        self.song_name = self._sanitize_filename(song_name)
        return self.song_id, self.song_name

    async def parse(self) -> ParseResult:  # noqa: C901
        try:
            # ① 解析下载链接（同时返回歌曲名、ID）
            local_path = self.save_dir / f"{self.song_name}.mp3"

            # 基本信息
            self.result.title = self.song_name
            self.result.vid = self.song_id
            self.result.content_type = 'audio'

            # ② 命中磁盘缓存
            if local_path.exists():
                logger.debug("命中磁盘缓存 -> %s", local_path.name)
            else:
                # ③ 下载音频文件
                logger.info("开始下载 -> %s", self.target)
                url, download_url = download_single(self.target, output_dir=str(self.save_dir),
                                                    file_name=f"{self.song_name}.mp3")
                logger.info("下载完成 -> %s", local_path.name)
                self.result.url = url
                self.result.download_url = download_url

            # ③ 构建结果并返回
            self.result.add_media(local_path=local_path, file_type='audio')
            self.result.success = True
            return self.result

        except Exception as e:  # pragma: no cover
            logger.exception("音乐解析失败: %s", e)
            self.result.error_message = f"解析音乐链接时出错: {e}"
            self.result.success = False
            return self.result

    # ─────────────────────────────────────────────
    # utils
    # ─────────────────────────────────────────────
    @staticmethod
    def _sanitize_filename(name: str) -> str:
        return "".join(c for c in name if c not in r'\\/:*?"<>\.|').strip()
