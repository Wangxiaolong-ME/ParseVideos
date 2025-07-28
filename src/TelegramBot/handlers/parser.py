from telegram import Update
from telegram.ext import ContextTypes
from TelegramBot.config import ADMIN_ID
from TelegramBot.recorder_parse import _parse_args, _load_stats, _collect_records
import logging

log = logging.getLogger(__name__)


async def showlog_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """管理员专用：/showlog [uid] [count]"""
    # ── 权限校验 ──
    if update.effective_user.id != ADMIN_ID:
        return

    # ── 解析参数 ──
    try:
        # 去掉命令本身，再按空格拆分参数
        args = update.effective_message.text.replace("/showlog", "", 1).strip().split()
        uid, count = _parse_args(args)
    except ValueError as ve:
        return await update.message.reply_text(f"❌ 参数错误：{ve}")

    # ── 加载日志并筛选 ──
    stats = _load_stats()
    if not stats:
        return await update.message.reply_text("📂 尚未记录任何解析日志。")

    records = _collect_records(stats, uid)
    if not records:
        who = f"UID {uid}" if uid is not None else "所有用户"
        return await update.message.reply_text(f"🔍 在 {who} 中未找到解析记录。")

    # ── 构造输出文本（最新 count 条） ──
    lines = []
    for rec in records[:count]:
        # -------- 批量取值，避免多次 dict.get --------
        ts_raw = rec.get("timestamp", "")
        uid = rec.get("uid")
        vid = rec.get("vid")
        hit = "缓存命中" if rec.get("is_cached_hit") else "新解析"
        title = (rec.get("title") or "").replace("\n", " ").strip()

        # -------- 时间裁剪并格式化 --------
        ts = ts_raw[:19].replace("T", " ")

        # -------- 主行（时间 / 命中状态 / UID / VID） --------
        lines.append(f"[{ts}] {hit}\nUID: {uid} | VID: {vid}")

        # -------- 副行：标题存在才输出 --------
        if title:
            lines.append(f"标题: {title[:15]}\n")  # 15 字截断，可按需调整

    # -------- 统计信息 --------
    lines.append(f"\n共展示 {min(count, len(records))} 条记录")

    await update.message.reply_text("\n".join(lines))
