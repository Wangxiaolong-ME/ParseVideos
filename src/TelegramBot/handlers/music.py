# TelegramBot/handlers/music.py
import logging
from telegram import Update
from telegram.ext import ContextTypes
from .generic_handler import generic_command_handler
from ..parsers.music_parser import  MusicParser # 注意路径
from TelegramBot.config import MUSIC_SAVE_DIR

__all__ = ["music_command"]
logger = logging.getLogger(__name__)


async def music_command(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        *,
        is_command: bool = True,
):
    """
    抖音视频/图集下载命令 /dy <url>
    此函数现在是一个简单的入口，所有逻辑都委托给通用处理器。
    """
    logger.info("music_command (refactored) start >>>")

    await generic_command_handler(
        update=update,
        context=context,
        parser_class=MusicParser,
        platform_name="music",
        save_dir=MUSIC_SAVE_DIR,
        is_command=is_command,
    )