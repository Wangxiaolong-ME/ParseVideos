import re
from telegram import Update
from telegram.ext import ContextTypes
from TelegramBot.handlers.bilibili import bili_command
from TelegramBot.handlers.douyin import douyin_command
from TelegramBot.handlers.music import music_command
from TelegramBot.config import ADMIN_ID

# 通用 url 处理器，根据 url 自动分发到对应平台
async def handle_general_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.effective_message.text.strip()
    platform = ""
    if re.search(r'(bilibili\.com|b23\.tv\/)', text):
        platform = 'bilibili video'
        await bili_command(update, context, is_command=False)
    elif re.search(r'v\.douyin\.com', text):
        platform = 'douyin video'
        await douyin_command(update, context, is_command=False)
    elif re.search(r'(music\.163\.com)|(163cn\.tv)', text):
        platform = "music.163"
        await music_command(update, context, is_command=False)

    # 解析简报发送给管理员
    if update.effective_user.id != ADMIN_ID:
        uname = f"@{update.effective_user.name}" or ""
        full_name = update.effective_user.full_name
        await update.get_bot().send_message(ADMIN_ID, f"{uname}[{full_name}] parsed {platform}")

    # else:
    #     await update.message.reply_text('已收到', reply_to_message_id=update.message.message_id)