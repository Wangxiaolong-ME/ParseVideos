# -*- coding: utf-8 -*-
from telegram import Update
from telegram.ext import ContextTypes
from TelegramBot.config import ADMIN_ID
from TelegramBot.recorder_blacklist import load_blacklist, save_blacklist
from TelegramBot.recorder_parse import load_users

import logging

log = logging.getLogger(__name__)


async def handle_blacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """手动将指定用户加入黑名单。用法：
       /blacklist <chat_id|@username> [<chat_id|@username> ...]
    """
    if update.effective_user.id != ADMIN_ID:
        return
        # return await update.message.reply_text(
        #     "无权限，仅管理员可用",
        #     reply_to_message_id=update.message.message_id,
        # )

    if not context.args:
        return await update.message.reply_text(
            "用法：/blacklist <chat_id|@username> ...",
            reply_to_message_id=update.message.message_id,
        )

    # 当前黑名单
    blacklist: list[int] = load_blacklist()

    # 把用户名映射到 chat_id 方便处理
    users = load_users()
    uname2cid = {v.get("uname"): int(k) for k, v in users.items() if "uname" in v}

    added: list[int] = []
    already: list[int] = []
    unknown: list[str] = []
    removed: list[int] = []  # 新增：记录成功移除的
    not_in: list[int] = []  # 新增：记录本就不在黑名单的

    for token in context.args:
        is_remove = token.startswith("-")  # 前缀 - 代表移除
        token = token.lstrip("-@").strip()  # 去掉 - 和 @
        cid: int | None = None

        if token.isdigit():
            cid = int(token)
        else:
            cid = uname2cid.get(token)

        if cid is None:
            unknown.append(token)
            continue

        # 移出黑名单
        if is_remove:
            if cid in blacklist:
                blacklist.remove(cid)
                removed.append(cid)
                log.info(f"已移除黑名单: {cid}")
            else:
                not_in.append(cid)
            continue

        # 加入黑名单
        if cid in blacklist:
            already.append(cid)
        else:
            blacklist.append(cid)
            added.append(cid)
            log.info(f"已手动加入黑名单: {cid}")

    # 保存
    if added or removed:
        blacklist = sorted(set(blacklist))
        save_blacklist(blacklist)

    # 结果汇报
    parts: list[str] = []
    if added:
        parts.append(f"✅ 新增黑名单: {', '.join(map(str, added))}")
    if already:
        parts.append(f"⚠ 已在黑名单: {', '.join(map(str, already))}")
    if unknown:
        parts.append(f"❓ 未识别: {', '.join(unknown)}")
    if removed:
        parts.append(f"✅ 已从黑名单移除: {', '.join(map(str, removed))}")
    if not_in:
        parts.append(f"不在黑名单: {', '.join(map(str, not_in))}")

    await update.message.reply_text("\n".join(parts))
