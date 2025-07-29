# notify_handler.py
import asyncio
import json
import logging
import os
import re
import uuid
from typing import List

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MessageEntity,
)
from telegram.constants import ParseMode
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
)

from TelegramBot.config import ADMIN_ID
from TelegramBot.recorder_parse import load_users

log = logging.getLogger(__name__)

SIGNATURE = ""               # 已在 MsgSender 统一追加可留空
DEFAULT_TEXT = "🤖 Bot 服务已启动 ✅"


# ────────────── /notify 指令入口 ──────────────
async def notify_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user

    # 权限校验
    if user.id != ADMIN_ID:
        await msg.reply_text("无权限，仅管理员可用", reply_to_message_id=msg.id)
        return

    raw = msg.text or ""
    payload = _strip_command(raw, msg.entities, context.bot.username).strip()
    if not payload:
        return await msg.reply_text(
            "用法：\n/notify <uid>[,<uid>...] <正文>\n/notify --all <正文>",
            reply_to_message_id=msg.id,
        )

    first, _, body = payload.partition(" ")
    body = body.strip() or DEFAULT_TEXT

    if first == "--all":
        target_uids: List[int] = list(load_users().keys())
    elif re.fullmatch(r"\d+(?:,\d+)*", first):
        target_uids = [int(u) for u in first.split(",")]
    else:
        return await msg.reply_text(
            "UID 参数应为纯数字，或使用 --all", reply_to_message_id=msg.id
        )

    if not target_uids:
        return await msg.reply_text("未找到有效 UID。", reply_to_message_id=msg.id)

    # 将待发任务缓存到 chat_data
    token = str(uuid.uuid4())
    context.chat_data[f"notify:{token}"] = {
        "uids": target_uids,
        "text": body,
    }

    # 回复确认按钮
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ 发送", callback_data=f"notify:{token}:yes"),
                InlineKeyboardButton("❌ 取消", callback_data=f"notify:{token}:no"),
            ]
        ]
    )
    await msg.reply_text(
        f"将向 {len(target_uids)} 位用户群发。请确认。",
        reply_markup=kb,
        reply_to_message_id=msg.id,
    )


# ────────────── 回调处理 ──────────────
async def notify_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    # 仅管理员可操作
    if update.effective_user.id != ADMIN_ID:
        return await q.answer("无权限！", show_alert=True)

    try:
        _prefix, token, action = q.data.split(":")
    except ValueError:
        return  # 非本模块数据

    key = f"notify:{token}"
    task = context.chat_data.pop(key, None)
    if not task:
        return await q.edit_message_text("任务已过期或不存在。")

    if action == "no":
        return await q.edit_message_text("❌ 已取消群发。")

    # 真正群发
    uids: List[int] = task["uids"]
    text: str = task["text"]
    users_meta = load_users()

    success, fail = [], []

    async def _push(uid: int):
        try:
            await context.bot.send_message(
                uid, text + SIGNATURE, parse_mode=ParseMode.HTML
            )
            success.append(uid)
        except Exception as e:
            fail.append(f"{uid}: {e!r}")
            log.warning("通知 %s 失败：%s", uid, e, exc_info=True)

    await asyncio.gather(*[_push(u) for u in uids])

    report = (
        f"✅ 成功 {len(success)}/{len(uids)}"
        + (f"\n{', '.join(map(str, success))}" if success else "")
        + (f"\n⚠️ 失败 {len(fail)}\n" + "\n".join(fail) if fail else "")
    )
    await q.edit_message_text(report)


# ────────────── 工具函数 ──────────────
def _strip_command(text: str, entities: List[MessageEntity], bot_name: str) -> str:
    """去掉 /notify 或 /notify@BotName 前缀"""
    if entities and entities[0].type == MessageEntity.BOT_COMMAND:
        return text[entities[0].length :]

    return re.sub(
        rf"^/notify(?:@{re.escape(bot_name)})?\s*", "", text, count=1, flags=re.I
    )

