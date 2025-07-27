from telegram import Update
from telegram.ext import ContextTypes

from TelegramBot.config import ADMIN_ID
from TelegramBot.file_cache import delete, keys

async def delcache_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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


async def showcache_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /showcache [N]
    不带参数：列出全部 key
    N > 0     ：列出前 N 条
    N < 0     ：列出后 |N| 条
    """
    if update.effective_user.id != ADMIN_ID:
        return

    # 取得全部 key，按插入顺序（dict 在 3.7+ 保序）展示
    all_keys = keys()

    # —— 处理可选参数 ——
    n = None
    if context.args:
        try:
            n = int(context.args[0])
        except ValueError:
            await update.message.reply_text("参数必须是整数，例如：/showcache 10 或 /showcache -10")
            return

    # 根据 n 取子集
    if n is None or n == 0 or abs(n) >= len(all_keys):
        subset = all_keys
    elif n > 0:
        subset = all_keys[:n]
    else:
        subset = all_keys[n:]   # n 为负数，取最后 |n| 条

    if not subset:
        await update.message.reply_text("当前缓存为空。")
        return

    text = "📄 缓存键列表：\n" + "\n".join(subset)
    await update.message.reply_text(text)