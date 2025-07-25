# src/telegram_bot/handlers/status.py   （新建文件或直接改原文件）
import psutil
from telegram import Update
from telegram.ext import ContextTypes
from TelegramBot.config import ADMIN_ID
from TelegramBot.task_manager import TaskManager
from TelegramBot.monitor import get_queue_length
from TelegramBot.handlers import generic_handler       # 导入各下载模块，拿到它们的 executor
import  logging
log = logging.getLogger(__name__)
# 打包所有线程池，后续有新模块可随时 append
_EXECUTORS = [generic_handler.executor]
task_manager: TaskManager                    # 在 bot.py 里注入同一个实例

async def handle_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text('无权限，仅管理员可用',
                                               reply_to_message_id=update.message.message_id)

    # —— 系统资源 —— 
    cpu = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory().percent

    # —— 业务指标 ——
    queue_len = get_queue_length(_EXECUTORS)     # 等待 + 进行中
    running    = task_manager.active_count()     # 正在执行（以用户维度）

    msg = (
        "🖥️ **服务器状态**\n"
        f"CPU 使用率：`{cpu:.1f}%`\n"
        f"内存使用率：`{mem:.1f}%`\n"
        f"排队任务数：`{queue_len}`\n"
        f"执行中任务：`{running}`"
    )
    log.debug(f"输出服务器状态")
    await update.message.reply_markdown_v2(msg, reply_to_message_id=update.message.message_id)
