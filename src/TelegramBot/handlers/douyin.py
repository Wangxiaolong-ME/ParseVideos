# TelegramBot/handlers/douyin.py
import logging
from telegram import Update
from telegram.ext import ContextTypes
from .generic_handler import generic_command_handler
from ..parsers.douyin_parser import DouyinParser  # 注意路径
from TelegramBot.config import DOUYIN_SAVE_DIR

__all__ = ["douyin_command"]
logger = logging.getLogger(__name__)


async def douyin_command(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        *,
        is_command: bool = True,
):
    """
    抖音视频/图集下载命令 /dy <url>
    此函数现在是一个简单的入口，所有逻辑都委托给通用处理器。
    """
    logger.info("douyin_command (refactored) start >>>")

    return await generic_command_handler(
        update=update,
        context=context,
        parser_class=DouyinParser,
        platform_name="douyin",
        save_dir=DOUYIN_SAVE_DIR,
        is_command=is_command,
    )