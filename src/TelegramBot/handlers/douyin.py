"""抖音视频下载命令 /dy <url>"""
from __future__ import annotations

import asyncio, functools, logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Any

from telegram import Update, Message
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown
from TelegramBot import config
from DouyinDownload.douyin_post import DouyinPost  # 你现有的脚本
from TelegramBot.cleaner import purge_old_files
from TelegramBot.config import DOUYIN_SAVE_DIR, MAX_THREAD_WORKERS, EXCEPTION_MSG, DOWNLOAD_TIMEOUT
from TelegramBot.task_manager import TaskManager
from TelegramBot.rate_limiter import RateLimiter
from TelegramBot.utils import MsgSender
from TelegramBot.file_cache import get as cache_get, put as cache_put
from TelegramBot.recorder_parse import UserParseResult, _record_user_parse

__all__ = ["douyin_command"]

logger = logging.getLogger(__name__)

rate_limiter: RateLimiter
task_manager: TaskManager
executor: Final = ThreadPoolExecutor(max_workers=MAX_THREAD_WORKERS)
record = UserParseResult(1)
record.platform = "douyin"
# ── helpers ──────────────────────────────────────────────
def _safe_filename(name: str) -> str:
    return "".join(c for c in name if c not in r'\/:*?"<>|').strip()


@dataclass
class DY:
    path: str | None = None
    fid: str = None
    vid: str = None
    url: str = None
    download_url :str or None = None
    title: str = None
    md_title: str = None
    gear_name: str = None
    size: float = None
    height: int = None
    width: int = None
    duration: int | float = None


def _download_or_hit(url: str):
    """下载或命中本地缓存，返回 mp4 Path。"""
    dy = DY
    post = DouyinPost(url).fetch_details()
    url = post.short_url
    post.filter_by_size(max_mb=50)
    post.deduplicate_by_resolution()
    option = post.get_option(720)
    video_id = post.video_id
    gear_name = option.gear_name
    title = post.video_title
    local_path = DOUYIN_SAVE_DIR / f"{video_id}_{gear_name}.mp4"

    dy.vid = video_id
    dy.title = title
    dy.gear_name = gear_name
    dy.url = url
    dy.path = local_path
    dy.height = option.height
    dy.width = option.width
    dy.duration = option.duration
    dy.download_url = option.url
    dy.size = option.size_mb

    # 若所有清晰度都 > 50 MB，则取体积最小的
    smallest = min(post.processed_video_options, key=lambda o: o.size_mb)
    if smallest.size_mb > 50:
        dy.size = smallest.size_mb
        download_link = post.processed_video_options[0].url
        dy.download_url = download_link
        display = f"{dy.title}"
        md_link = (
            f"[{escape_markdown(display, version=2)}]"
            f"({escape_markdown(download_link, version=2)})"
        )
        logger.debug(f"markdown:{md_link}")
        dy.md_title = md_link
        dy.path = None
        return dy

    # 依据json fid读缓存
    if fid := cache_get(video_id):
        dy.fid = fid
        logger.debug("命中fid缓存 -> %s", local_path.name)
        return dy

    # 依据本地文件读缓存
    if local_path.exists():
        logger.debug("命中磁盘缓存 -> %s", local_path.name)
        return dy

    logger.info("开始下载 -> %s", url)
    v_path = post.download_option(option, timeout=DOWNLOAD_TIMEOUT)  # 返回 mp4
    Path(v_path).rename(local_path)  # 统一命名
    logger.info("下载完成 -> %s", local_path.name)
    dy.path = local_path
    return dy


def _extract_file_id(msg: Message) -> str | None:
    return msg.video.file_id if msg.video else msg.document.file_id if msg.document else None


async def _send_with_cache(sender: MsgSender, dy: DY, progress_msg: Message) -> Message:
    key = dy.vid
    if fid := cache_get(key):
        try:
            record.fid[key] = fid
            record.to_fid = True
            logger.debug("用 file_id 秒回 (%s)", key)
            return await sender.send_video(fid, caption=dy.title, progress_msg=progress_msg)
        except BadRequest as e:
            if "file not found" in str(e) or "FILE_REFERENCE" in str(e):
                cache_put(key, None)
            else:
                raise

    msg = await sender.send_video(dy.path,
                                  caption=dy.title,
                                  width=dy.width,
                                  height=dy.height,
                                  duration=dy.duration,
                                  progress_msg=progress_msg,
                                  )
    record.success = True
    if fid := _extract_file_id(msg):
        cache_put(key, fid)
    return msg


# ── entry ────────────────────────────────────────────────
async def douyin_command(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        *,
        is_command: bool = True,
) -> Message | None:
    logger.info("douyin_command start >>>")

    uid = update.effective_user.id
    sender = MsgSender(update)
    record.uid = uid

    # ① 先清理本地缓存
    clear = purge_old_files(DOUYIN_SAVE_DIR, keep_hours=2)
    if clear:
        clear = '\n'.join(clear)
        await context.bot.send_message(text=f"已清除缓存文件：{clear}", chat_id=config.ADMIN_ID)

    if not rate_limiter.allow(uid):
        return await sender.send("操作过于频繁，请稍后再试")
    if not await task_manager.acquire(uid):
        return await sender.send("您已有任务正在进行，请稍候完成后再发起新任务")

    await sender.react("👀")
    progress_msg = await sender.send("视频下载中.....")

    try:
        if is_command and not context.args:
            return await sender.send("示例：/dy https://v.douyin.com/xxxxx", reply=False)

        url = context.args[0] if is_command else update.effective_message.text

        loop = asyncio.get_running_loop()
        dy = await loop.run_in_executor(
            executor, functools.partial(_download_or_hit, url)
        )
        # await progress_msg.delete()  # 视频下载消息删除

        record.url = dy.url
        record.parsed_url = dy.download_url
        record.vid = dy.vid
        record.title = dy.title
        record.size = dy.size

        # 文件过大：local_path 为 None，直接发 Markdown
        if dy.path is None:
            msg = await sender.send(
                f" 视频超过 50 MB，点击下方链接下载：\n{dy.md_title}",
                reply=False,
                parse_mode=ParseMode.MARKDOWN_V2,
                preview=False,
            )
            record.success = True
            return msg

        msg = await _send_with_cache(sender, dy, progress_msg)
        record.success = True
        return msg

    except Exception as e:
        logger.exception("douyin_command 失败：%s", e)
        record.exception = e
        await progress_msg.edit_text(EXCEPTION_MSG)
    finally:
        task_manager.release(uid)
        logger.info("douyin_command finished.")
        _record_user_parse(record)
