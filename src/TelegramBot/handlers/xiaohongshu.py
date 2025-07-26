# TelegramBot/handlers/xiaohongshu.py
import logging
from telegram import Update
from telegram.ext import ContextTypes
from TelegramBot.handlers.generic_handler import generic_command_handler
from TelegramBot.parsers.xhs_parser import XiaohongshuParser  # 注意路径
from TelegramBot.config import XIAOHONGSHU_SAVE_DIR

__all__ = ["xhs_command"]
logger = logging.getLogger(__name__)


async def xhs_command(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        *,
        is_command: bool = True,
):
    """
    此函数现在是一个简单的入口，所有逻辑都委托给通用处理器。
    """
    logger.info("xhs_command (refactored) start >>>")

    await generic_command_handler(
        update=update,
        context=context,
        parser_class=XiaohongshuParser,
        platform_name="xhs",
        save_dir=XIAOHONGSHU_SAVE_DIR,
        is_command=is_command,
    )