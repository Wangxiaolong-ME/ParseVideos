# TelegramBot/handlers/unknow_command.py
import logging
from telegram import Update
from telegram.ext import ContextTypes
from .generic_handler import generic_command_handler

__all__ = ["unknow_command"]
logger = logging.getLogger(__name__)


async def unknow_command(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        platform="unknow",
        *,
        is_command: bool = True,
):
    """
    抖音视频/图集下载命令 /dy <url>
    此函数现在是一个简单的入口，所有逻辑都委托给通用处理器。
    """
    logger.info("unknow_command (refactored) start >>>")


    await generic_command_handler(
        update=update,
        context=context,
        parser_class=None,
        platform_name=platform,
        save_dir=None,
        is_command=is_command,
    )