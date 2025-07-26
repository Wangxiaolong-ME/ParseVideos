import re
from telegram import Update
from telegram.ext import ContextTypes
from TelegramBot.handlers import bilibili, douyin, music, xiaohongshu, unknow
from TelegramBot.config import ADMIN_ID, EXCEPTION_MSG
import logging

logger = logging.getLogger(__name__)


# 通用 url 处理器，根据 url 自动分发到对应平台
async def handle_general_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.effective_message.text.strip()
    platform = ""
    if re.search(r'(bilibili\.com|b23\.tv\/)', text):
        try:
            platform = 'bilibili video'
            await bilibili.bilibili_command(update, context, is_command=False)
        except Exception as e:
            logger.error(f"bilibili_command 失败: {e}")
            await update.effective_message.reply_text(EXCEPTION_MSG, quote=True)

    elif re.search(r'v\.douyin\.com', text):
        try:
            platform = 'douyin video'
            await douyin.douyin_command(update, context, is_command=False)
        except Exception as e:
            logger.error(f"douyin_command 失败: {e}")
            await update.effective_message.reply_text(EXCEPTION_MSG, quote=True)

    elif re.search(r'(music\.163\.com)|(163cn\.tv)', text):
        try:
            platform = "music.163"
            await music.music_command(update, context, is_command=False)
        except Exception as e:
            logger.error(f"music_command 失败: {e}")
            await update.effective_message.reply_text(EXCEPTION_MSG, quote=True)

    elif re.search(r'xiaohongshu\.com/[\w\S]+', text):
        try:
            platform = "xhs"
            await xiaohongshu.xhs_command(update, context, is_command=False)
        except Exception as e:
            logger.error(f"xhs_command 失败: {e}")
            await update.effective_message.reply_text(EXCEPTION_MSG, quote=True)

    else:
        try:
            platform = "unknow"
            await unknow.unknow_command(update, context, is_command=False)
        except Exception as e:
            logger.error(f"unknow_command 失败: {e}")
            await update.effective_message.reply_text(EXCEPTION_MSG, quote=True)

    # 解析简报发送给管理员
    if update.effective_user.id != ADMIN_ID:
        uname = update.effective_user.name or ""
        full_name = update.effective_user.full_name
        await update.get_bot().send_message(ADMIN_ID, f"{uname}[{full_name}] parsed {platform}")

    # else:
    #     await update.message.reply_text('已收到', reply_to_message_id=update.message.message_id)
