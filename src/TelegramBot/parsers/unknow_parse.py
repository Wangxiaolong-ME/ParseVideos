# TelegramBot/parsers/unknow_parse.py
"""
未知请求
"""
import logging
from pathlib import Path

from .base import BaseParser, ParseResult

logger = logging.getLogger(__name__)


class UnknowParser(BaseParser):
    """解析网易云音乐 URL/ID，返回 `ParseResult`。"""

    def __init__(self, target: str, save_dir: Path | None = None):
        super().__init__(target, save_dir or None)
        self.target = target  # 兼容旧变量名

    def parse(self) -> ParseResult:
        self.target
