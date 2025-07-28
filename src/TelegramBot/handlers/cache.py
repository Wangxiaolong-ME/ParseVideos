from telegram import Update
from telegram.ext import ContextTypes

from TelegramBot.config import ADMIN_ID
from TelegramBot.file_cache import delete, key_title_pairs,peek, get_title
from TelegramBot.handlers.generic_handler import _send_by_file_id
from TelegramBot.utils import MsgSender


async def delcache_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /delcache <key>
    删除指定 key 的文件 ID 缓存。
    """
    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:
        await update.message.reply_text("用法：/delcache <key>\n示例：/delcache 7479426668306730278")
        return

    key = context.args[0]
    if delete(key):
        await update.message.reply_text(f"✅ 已删除缓存：{key}")
    else:
        await update.message.reply_text(f"⚠️ 未找到缓存：{key}")


async def showcache_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /showcache [N]
    不带参数：列出全部 key
    N > 0     ：列出前 N 条
    N < 0     ：列出后 |N| 条
    """
    if update.effective_user.id != ADMIN_ID:
        return

    # 取得全部 (key, title)，字典在 3.7+ 默认保序
    all_pairs = key_title_pairs()

    # —— 解析可选参数 ——
    n: int | None = None
    if context.args:
        try:
            n = int(context.args[0])
        except ValueError:
            await update.message.reply_text("参数必须是整数，例如：/showcache 10 或 /showcache -10")
            return

    # —— 截取子集 ——
    if n is None or n == 0 or abs(n) >= len(all_pairs):
        subset = all_pairs
    elif n > 0:
        subset = all_pairs[:n]
    else:
        subset = all_pairs[n:]  # n 为负数 → 取最后 |n| 条

    if not subset:
        await update.message.reply_text("当前缓存为空。")
        return

    # —— 构造输出文本 ——
    lines = [f"{k}  {t.replace('\n',' ')[:15]}" if t else k for k, t in subset]
    text = "📄 缓存条目：\n" + "\n".join(lines)
    await update.message.reply_text(text)


async def getcache_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /getcache <key>
    直接把缓存里的文件发出来，附带 title。
    """
    # —— 权限控制 ——
    if update.effective_user.id != ADMIN_ID:
        return

    # —— 参数校验 ——
    if not context.args:
        await update.message.reply_text(
            "用法：/getcache <key>\n示例：/getcache 7479426668306730278"
        )
        return

    key = context.args[0]
    file_id = peek(key)
    if file_id is None:
        await update.message.reply_text(f"⚠️ 未找到缓存：{key}")
        return

    title = get_title(key) or ""   # 空标题则不加 caption

    # —— 发文件：file_id 可能是 str 或 list[str] ——
    # 如果是列表，只取第一项；如需全发可改成循环。
    fid_to_send = file_id[0] if isinstance(file_id, list) else file_id

    try:
        # sender 对象需具备 .send_*(...)，你的 _send_by_file_id 已封装好
        sender = MsgSender(update)    # 大多数封装里 chat 本身即可
        await _send_by_file_id(sender, fid_to_send, title)
    except Exception as e:
        await update.message.reply_text(f"file_id 无效或已过期：{e}")
        # 如需清理缓存，可在此调用 delete(key)
        if delete(key):
            await update.message.reply_text(f"✅ 已删除无效ID：{title} {file_id}")
        else:
            await update.message.reply_text(f"⚠️ 未找到缓存：{key}")