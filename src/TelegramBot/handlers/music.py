"""网易云音乐下载命令 /music <id|url>

入口函数 music_command(update, context, is_command=True) 不变。
"""
from __future__ import annotations

import asyncio
import functools
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Final

from telegram import Update, Message
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from MusicDownload.download import download_single
from MusicDownload.download_music import get_download_link
from TelegramBot.cleaner import purge_old_files
from TelegramBot.config import MUSIC_SAVE_DIR, MAX_THREAD_WORKERS, EXCEPTION_MSG
from TelegramBot.task_manager import TaskManager
from TelegramBot.rate_limiter import RateLimiter
from TelegramBot.utils import MsgSender
from TelegramBot.file_cache import get as cache_get, put as cache_put
from TelegramBot.recorder_parse import UserParseResult, _record_user_parse

__all__ = ["music_command"]

logger = logging.getLogger(__name__)

rate_limiter: RateLimiter
task_manager: TaskManager
executor: Final = ThreadPoolExecutor(max_workers=MAX_THREAD_WORKERS)
record = UserParseResult(0)
record.platform = "music.163"


# ════════════════════════════════════════════════
# Helper functions
# ════════════════════════════════════════════════
def _safe_filename(name: str) -> str:
    """跨平台安全的文件名：去掉非法字符。"""
    return "".join(c for c in name if c not in r'\/:*?"<>|').strip()


def _download_or_hit(target: str) -> Path:
    """
    若本地已存在同名 MP3 则直接返回；否则下载。
    返回值：下载/命中的本地文件 Path
    """
    # ① 先清理超过时间的本地缓存
    purge_old_files(MUSIC_SAVE_DIR, keep_hours=2)
    _, song_name = get_download_link(target)
    local_path = MUSIC_SAVE_DIR / f"{_safe_filename(song_name)}.mp3"

    if local_path.exists():
        logger.debug("命中磁盘缓存 -> %s", local_path.name)
        return local_path

    logger.info("开始下载 -> %s", target)
    url, download_url = download_single(target, output_dir=str(MUSIC_SAVE_DIR))
    record.url = url
    record.parsed_url = download_url
    logger.info("下载完成 -> %s", local_path.name)
    return local_path


def _extract_file_id(msg: Message) -> str | None:
    """兼容 document / audio 两种返回类型。"""
    if msg.document:
        return msg.document.file_id
    if msg.audio:
        return msg.audio.file_id
    return None


async def _send_with_cache(
        sender: MsgSender,
        chat_id: int,
        local_path: Path,
) -> Message | None:
    """
    • 如果 file_id 缓存命中：直接秒发
    • 否则上传文件并写回缓存
    """
    key = local_path.name
    if fid := cache_get(key):
        record.fid[key] = fid
        record.to_fid = True
        try:
            logger.debug(f"用 file_id 秒回 ({key})")
            return await sender.send_document(fid)
        except BadRequest as e:
            # file_id 失效，清理后回退到重新上传
            if "file not found" in str(e) or "FILE_REFERENCE" in str(e):
                logger.warning(f"file_id 失效，清理缓存并重新上传 -> {key}")
                cache_put(key, None)
            else:
                raise

    # 首次或失效：上传并写缓存
    msg = await sender.send_document(local_path)
    if fid := _extract_file_id(msg):
        cache_put(key, fid)
        logger.debug(f"记录 file_id 缓存 -> {key}")
    return msg


# ════════════════════════════════════════════════
# Entry point (kept for external references)
# ════════════════════════════════════════════════
async def music_command(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        *,
        is_command: bool = True,
) -> Message | None:
    """/music 与纯文本两种触发方式共用一个入口。"""
    logger.info("music_command start >>>")
    record.start_time = time.perf_counter()

    uid = update.effective_user.id
    sender = MsgSender(update)
    record.uid = uid
    uname = update.effective_user.username or "(无用户名)"
    name = update.effective_user.last_name or ''  + update.effective_user.first_name or ''  # 显示名
    record.uname = uname
    record.full_name = name

    # ---- 速率限制 & 同用户单任务 ----
    if not rate_limiter.allow(uid):
        return await sender.send("操作过于频繁，请稍后再试")
    if not await task_manager.acquire(uid):
        return await sender.send("您已有任务正在进行，请稍候完成后再发起新任务")

    try:
        # ---- 参数解析 ----
        if is_command and not context.args:
            return await sender.send(
                "示例：/music https://music.163.com/song?id=123456",
                reply=False,
            )
        target = context.args[0] if is_command else update.effective_message.text

        await sender.react("👀")
        await sender.typing()  # 正在输入状态

        # ---- I/O 密集：放线程池 ----
        loop = asyncio.get_running_loop()
        local_path: Path = await loop.run_in_executor(
            executor, functools.partial(_download_or_hit, target)
        )
        # ---- 发送 & 缓存 file_id ----
        msg =  await _send_with_cache(sender, update.effective_chat.id, local_path)
        record.success = True
        return msg

    except Exception as e:
        logger.exception("music_command 失败：%s", e)
        await sender.send(EXCEPTION_MSG)
    finally:
        task_manager.release(uid)
        _record_user_parse(record)