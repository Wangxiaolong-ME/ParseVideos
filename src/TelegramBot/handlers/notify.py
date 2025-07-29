# src/telegram_bot/handlers/notify.py
import asyncio
import re

from telegram import Update
from telegram.ext import ContextTypes
from TelegramBot.config import ADMIN_ID
from TelegramBot.recorder_parse import load_users

import logging

log = logging.getLogger(__name__)


async def handle_notify_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 仅允许管理员使用
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text('无权限，仅管理员可用',
                                               reply_to_message_id=update.message.message_id)

    bot = context.bot
    raw_cmd = update.effective_message.text.lstrip()  # 原始文本

    # 去掉开头的 /notify 与多余空格
    payload = re.sub(r'^/notify\s*', '', raw_cmd, count=1).strip()

    # 解析“ID区段 + 消息正文”
    m = re.match(r'^([\d,]+)\s+(.*)$', payload)  # 若写了 UID
    if m:
        uid_part, msg_text = m.groups()
        target_uids = [int(u) for u in uid_part.split(',') if u]
        msg_text = msg_text or "🤖 Bot 服务已启动 ✅"
    else:
        # 群发：无 UID 或 UID 非纯数字
        target_uids = list(load_users().keys())
        msg_text = payload or "🤖 Bot 服务已启动 ✅"

    users = load_users()  # 只加载一次
    success = []

    async def _send(uid: int) -> None:
        try:
            await bot.send_message(chat_id=uid, text=msg_text)
            uinfo = users.get(uid, {})
            success.append(f"{uid} {uinfo.get('full_name', 'No Name')} "
                           f"({uinfo.get('uname', 'Unknown')})")
            log.debug(f"已通知用户 {uid}")
        except Exception as e:
            log.error(f"通知用户 {uid} 失败: {e}")

    await asyncio.gather(*[_send(uid) for uid in target_uids])

    report = '\n'.join(success) or '无'
    await bot.send_message(chat_id=ADMIN_ID, text=f"通知成功用户:\n{report}")
