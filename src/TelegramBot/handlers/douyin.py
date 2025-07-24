"""抖音视频下载命令 /dy <url>"""
from __future__ import annotations

import asyncio, functools, logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Any, List

from telegram import Update, Message, InputMediaPhoto
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown

from DouyinDownload.douyin_image_post import DouyinImagePost
from DouyinDownload.models import Image
from TelegramBot import config
from DouyinDownload.douyin_post import DouyinPost
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
    download_url: str or None = None
    title: str = None
    md_title: str = None
    gear_name: str = None
    size: float = None
    height: int = None
    width: int = None
    duration: int | float = None
    content_type: str = "video"
    images: List[Image] = None


def _download_or_hit(url: str):
    """下载或命中本地缓存，返回 mp4 Path。"""
    dy = DY
    post = DouyinPost(url)
    # 尝试判断内容类型
    content_type = post.get_content_type(post.short_url)
    dy.content_type = content_type
    # 视频处理
    if content_type == 'video':
        post.fetch_details()
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
        dy.duration = option.duration / 1000  # 毫秒转秒
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
    elif content_type == 'images':
        image_post = DouyinImagePost(url)
        image_post.fetch_details()

        # 图片大小目前没有过滤机制，直接尝试下载所有图片
        images: List[Image] = image_post.download_images(timeout=DOWNLOAD_TIMEOUT)

        # 记录图片信息到 record 中
        record.vid = image_post.aweme_id
        record.title = image_post.title

        # 对于图片集，暂时不走文件ID缓存，每次都下载并发送
        # 如果图片很多，Telegram 的 media group 限制是 10 张，需要分批发送
        dy.title = image_post.title
        dy.vid = image_post.aweme_id
        dy.images = images
        return dy

    else:
        logger.warning(f"未能识别抖音短链接内容类型: {url}")
        return "unknown", "未能识别抖音短链接内容类型，或该内容不可用。请检查链接是否正确。"


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


async def _send_images_with_cache(sender: MsgSender, images: List[Image], title: str, progress_msg: Message,
                                  rep_msg_id) -> List[Message]:
    """专门用于发送图片集"""
    # Telegram media group 最多支持 10 张图片
    MAX_MEDIA_GROUP_SIZE = 10

    sent_messages: List[Message] = []

    # 准备 InputMediaPhoto 列表
    media_group_items: List[InputMediaPhoto] = []
    try:
        for i, img in enumerate(images):
            if not img.local_path or not Path(img.local_path).exists():
                logger.warning(f"图片文件 {img.local_path} 不存在，跳过发送。")
                continue

            caption_text = f"{title}" if i == 0 else ""  # 只有第一张带标题

            media_group_items.append(
                InputMediaPhoto(open(img.local_path, 'rb'), caption=caption_text,
                                parse_mode=ParseMode.HTML if i == 0 else None)
            )

            # 达到最大数量或所有图片都已添加，发送媒体组
            if len(media_group_items) == MAX_MEDIA_GROUP_SIZE or (i == len(images) - 1 and media_group_items):
                try:
                    # Telegram send_media_group 默认没有 progress_msg，此处可以考虑自定义实现或去掉
                    sent_msgs = await sender.send_media_group(media=media_group_items, reply_to_message_id=rep_msg_id)
                    sent_messages.extend(sent_msgs)
                    media_group_items = []  # 清空列表，准备下一批
                    record.success = True

                    # 如果图片很多，分批发送后，进度消息可能需要更新
                    if len(images) > MAX_MEDIA_GROUP_SIZE and i < len(images) - 1:
                        await progress_msg.edit_text(f"图片下载和发送中... 已发送 {len(sent_messages)}/{len(images)} 张")

                except BadRequest as e:
                    logger.error(f"发送图片组失败: {e}")
                    if "too much media in album" in str(e):  # 理论上不会发生，因为我们已经分批
                        logger.error("Too much media in album, this should not happen with batching.")
                    elif "MEDIA_EMPTY" in str(e):
                        logger.warning("Media group is empty, skipping send.")
                    else:
                        raise
                except Exception as e:
                    logger.error(f"发送图片组时发生未知错误: {e}")
                    raise
    except Exception as e:
        logger.error(f"发送图片组时发生未知错误: {e}")
    finally:
        await progress_msg.delete()
    if not sent_messages:
        raise Exception("未能成功发送任何图片。")

    return sent_messages


# ── entry ────────────────────────────────────────────────
async def douyin_command(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        *,
        is_command: bool = True,
) -> Message | None:
    logger.info("douyin_command start >>>")
    record.start_time = time.perf_counter()

    uid = update.effective_user.id
    msg_id = update.effective_message.id
    sender = MsgSender(update)
    record.uid = uid

    uname = update.effective_user.username or "(无用户名)"
    name = update.effective_user.last_name or '' + update.effective_user.first_name or ''  # 显示名
    record.uname = uname
    record.full_name = name

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
    progress_msg = await sender.send("正在下载.....")

    try:
        if is_command and not context.args:
            return await sender.send("示例：/dy https://v.douyin.com/xxxxx", reply=False)

        url = context.args[0] if is_command else update.effective_message.text

        loop = asyncio.get_running_loop()
        dy = await loop.run_in_executor(
            executor, functools.partial(_download_or_hit, url)
        )

        record.title = dy.title
        record.vid = dy.vid

        if dy.content_type == 'video':
            record.url = dy.url
            record.parsed_url = dy.download_url
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
        elif dy.content_type == 'images':
            await _send_images_with_cache(sender, dy.images, dy.title, progress_msg, rep_msg_id=msg_id)
            record.success = True
            return
        else:
            logger.error(f"内容类型未知，跳过此次操作")

    except Exception as e:
        logger.exception("douyin_command 失败：%s", e)
        record.exception = e
        await progress_msg.edit_text(EXCEPTION_MSG)
    finally:
        task_manager.release(uid)
        logger.info("douyin_command finished.")
        _record_user_parse(record)
