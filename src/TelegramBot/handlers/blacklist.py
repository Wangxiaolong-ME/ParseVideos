# -*- coding: utf-8 -*-
from telegram import Update
from telegram.ext import ContextTypes
from TelegramBot.config import ADMIN_ID
from TelegramBot.recorder_blacklist import load_blacklist, save_blacklist
from TelegramBot.recorder_parse import load_users

import logging

log = logging.getLogger(__name__)


# 公共工具：解析参数 → chat_id
def _token_to_cid(token: str, uname2cid: dict[str, int]) -> int | None:
    token = token.lstrip("@").strip()
    if token.isdigit():
        return int(token)
    return uname2cid.get(token)


async def handle_blacklist_add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """用法： /blacklist_add <chat_id|@username> [...]"""
    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:
        return await update.message.reply_text("用法：/blacklist_add <chat_id|@username> ...",
                                               reply_to_message_id=update.message.message_id)

    blacklist: list[int] = load_blacklist()
    users = load_users()
    uname2cid = {v.get("uname"): int(k) for k, v in users.items() if v.get("uname")}

    added, already, unknown = [], [], []

    for token in context.args:
        cid = _token_to_cid(token, uname2cid)
        if cid is None:
            unknown.append(token); continue
        if cid in blacklist:
            already.append(cid)
        else:
            blacklist.append(cid); added.append(cid); log.info(f"加入黑名单: {cid}")

    if added:
        save_blacklist(sorted(set(blacklist)))

    parts = []
    if added:   parts.append(f"✅ 已加入: {', '.join(map(str, added))}")
    if already: parts.append(f"⚠ 已在黑名单: {', '.join(map(str, already))}")
    if unknown: parts.append(f"❓ 未识别: {', '.join(unknown)}")
    await update.message.reply_text("\n".join(parts))


async def handle_blacklist_remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """用法： /blacklist_remove <chat_id|@username> [...]"""
    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:
        return await update.message.reply_text("用法：/blacklist_remove <chat_id|@username> ...",
                                               reply_to_message_id=update.message.message_id)

    blacklist: list[int] = load_blacklist()
    users = load_users()
    uname2cid = {v.get("uname"): int(k) for k, v in users.items() if v.get("uname")}

    removed, not_in, unknown = [], [], []

    for token in context.args:
        cid = _token_to_cid(token, uname2cid)
        if cid is None:
            unknown.append(token); continue
        if cid in blacklist:
            blacklist.remove(cid); removed.append(cid); log.info(f"移除黑名单: {cid}")
        else:
            not_in.append(cid)

    if removed:
        save_blacklist(sorted(set(blacklist)))

    parts = []
    if removed: parts.append(f"✅ 已移除: {', '.join(map(str, removed))}")
    if not_in:  parts.append(f"ℹ 不在黑名单: {', '.join(map(str, not_in))}")
    if unknown: parts.append(f"❓ 未识别: {', '.join(unknown)}")
    await update.message.reply_text("\n".join(parts))


async def handle_blacklist_show_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """用法： /blacklist_show   —— 列出当前黑名单"""
    if update.effective_user.id != ADMIN_ID:
        return

    blacklist: list[int] = load_blacklist()
    if not blacklist:
        return await update.message.reply_text("当前黑名单为空")

    users = load_users()
    uname2info = {int(k): (v.get("uname", ""), v.get("full_name", "")) for k, v in users.items()}

    lines = []
    for cid in blacklist:
        uname, full_name = uname2info.get(cid, ("", ""))
        tag = f"{full_name} (@{uname})" if uname or full_name else "未知用户"
        lines.append(f"{cid}  {tag}")

    await update.message.reply_text("📋 当前黑名单：\n" + "\n".join(lines))