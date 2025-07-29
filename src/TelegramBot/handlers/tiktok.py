# TelegramBot/handlers/tiktok.py
import logging
from telegram import Update
from telegram.ext import ContextTypes
from TelegramBot.handlers.generic_handler import generic_command_handler
from TelegramBot.parsers.tiktok_parser import TikTokParser  # 注意路径
from TelegramBot.config import TIKTOK_SAVE_DIR

__all__ = ["tiktok_command"]
logger = logging.getLogger(__name__)


async def tiktok_command(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        *,
        is_command: bool = True,
):
    """
    此函数现在是一个简单的入口，所有逻辑都委托给通用处理器。
    """
    logger.info("tiktok_command (refactored) start >>>")

    return await generic_command_handler(
        update=update,
        context=context,
        parser_class=TikTokParser,
        platform_name="tiktok",
        save_dir=TIKTOK_SAVE_DIR,
        is_command=is_command,
    )