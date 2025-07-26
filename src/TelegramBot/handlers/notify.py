# src/telegram_bot/handlers/notify.py
from telegram import Update
from telegram.ext import ContextTypes
from TelegramBot.config import ADMIN_ID
from TelegramBot.recorder_parse import load_users

import  logging
log = logging.getLogger(__name__)


async def handle_notify_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 仅允许管理员使用
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text('无权限，仅管理员可用',
                                               reply_to_message_id=update.message.message_id)
    bot = update.get_bot()
    # 加载用户列表
    users = load_users()
    text = "🤖 Bot 服务已启动 ✅"
    if update.effective_message.text:
        text = update.effective_message.text.replace('/notify', '')
    success = []

    for cid, user_info in users.items():
        try:
            user_name = user_info.get('uname', 'Unknown')
            full_name = user_info.get('full_name', 'No Name')
            await bot.send_message(chat_id=cid, text=text)
            success.append(f"{cid} {full_name} ({user_name})")  # 显示 full_name 和 uname
            log.debug(f"已通知用户 {cid} - {full_name} ({user_name})")
        except Exception as e:
            log.error(f"通知用户 {cid} 失败: {e}")

    success = '\n'.join(success)
    await bot.send_message(chat_id=ADMIN_ID, text=f"通知成功用户:\n{success}")