import logging, sys
from PublicMethods.logger import setup_log, get_logger

setup_log(logging.DEBUG, "TelegramService", one_file=True)
logger = get_logger(__name__)
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from TelegramBot.config import TELEGRAM_TOKEN_ENV, ADMIN_ID, MIN_MSG_INTERVAL
from TelegramBot.rate_limiter import RateLimiter
from TelegramBot.task_manager import TaskManager
from TelegramBot.handlers import bilibili, douyin, music, general, status, notify, xiaohongshu, blacklist, cache


def _inject_singletons(app):
    """向各 handler 模块注入同一个限频器、任务管理器实例。"""
    limiter = RateLimiter(MIN_MSG_INTERVAL)
    manager = TaskManager()
    for mod in (bilibili, douyin, music, status):
        mod.rate_limiter = limiter
        mod.task_manager = manager


# —— 通知函数 ——
async def _notify_startup(app):
    await app.bot.send_message(chat_id=ADMIN_ID, text="🤖 Bot 服务已启动 ✅")


def main() -> None:
    token = TELEGRAM_TOKEN_ENV
    if not token:
        logger.error("环境变量 TELEGRAM_TOKEN 未设置")
        sys.exit(1)

    application = (
        ApplicationBuilder()
        .token(token)
        .concurrent_updates(True)  # 允许并发处理更新
        .post_init(_notify_startup)
        .build()
    )

    _inject_singletons(application)

    # 注册命令
    application.add_handler(CommandHandler("start", _start))

    application.add_handler(CommandHandler("getcache", cache.getcache_cmd))
    application.add_handler(CommandHandler("delcache", cache.delcache_cmd))
    application.add_handler(CommandHandler("showcache", cache.showcache_cmd))
    application.add_handler(CommandHandler("blacklist_add", blacklist.handle_blacklist_add_command))
    application.add_handler(CommandHandler("blacklist_remove", blacklist.handle_blacklist_remove_command))
    application.add_handler(CommandHandler("blacklist_show", blacklist.handle_blacklist_show_command))

    application.add_handler(CommandHandler("notify", notify.handle_notify_command))
    application.add_handler(CommandHandler("status", status.handle_status_command))

    # 暂时以下这些命令未开放使用,先放着看后续是否有需求
    application.add_handler(CommandHandler("bilibili", bilibili.bilibili_command))
    application.add_handler(CommandHandler("douyin", douyin.douyin_command))
    application.add_handler(CommandHandler("music", music.music_command))
    application.add_handler(CommandHandler("xhs", xiaohongshu.xhs_command))

    application.add_handler(MessageHandler(filters.ALL, general.handle_general_url))

    # 运行
    application.run_polling(
        drop_pending_updates=True,  # 忽略启动前的所有消息
    )
    logger.info("Bot started ✓")
    # await application.bot.send_message(chat_id=ADMIN_ID, text="Bot 已启动")
    # await application.updater.start_polling()
    # await application.wait_closed()


# 默认 /start
async def _start(update, ctx):
    await update.message.reply_text("欢迎！直接发送视频链接开始下载。")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")
