"""Bilibili 视频下载命令 /bili <url>"""
from __future__ import annotations

import asyncio, functools, logging, re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Final, Any

from telegram import Update, Message
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.helpers import escape_markdown
from telegram.ext import ContextTypes

from BilibiliDownload.bilibili_post import BilibiliPost  # 你的脚本
from TelegramBot.cleaner import purge_old_files
from TelegramBot.config import BILI_SAVE_DIR, MAX_THREAD_WORKERS, ADMIN_ID, EXCEPTION_MSG, BILI_COOKIE
from TelegramBot.task_manager import TaskManager
from TelegramBot.rate_limiter import RateLimiter
from TelegramBot.uploader import upload
from TelegramBot.utils import MsgSender
from TelegramBot.file_cache import get as cache_get, put as cache_put
from PublicMethods.tools import check_file_size
from TelegramBot.recorder_parse import UserParseResult, _record_user_parse

__all__ = ["bili_command"]

logger = logging.getLogger(__name__)
rate_limiter: RateLimiter
task_manager: TaskManager
executor: Final = ThreadPoolExecutor(max_workers=MAX_THREAD_WORKERS)

record = UserParseResult(2)

record.platform = "bilibili"
# ─ helpers ────────────────────────────────────────────
INVALID = r'\/:*?"<>|'


def _safe_filename(name: str, max_len: int = 80) -> str:
    safe = "".join("_" if c in INVALID else c for c in name).strip()
    return safe[:max_len]


@dataclass
class Bili:
    path: str | None
    fid: str | None
    vid: str | None
    url: str | None
    title: str | None
    md_title: str = None
    gear_name: str = None
    size: float = None
    height: int = None
    width: int = None
    duration: int | float = None
    select_max_size: int = 200  # 选择下载视频大小，初始200，因为合并音频的缘故，会导致视频超过200，就需要逐步减少


# -----------------------------------------------------


def _download_or_hit(url: str):
    """解析→决定：返回 (Path | str | None, bvid, title/md_link)"""
    result = Bili

    post = BilibiliPost(url, threads=8, cookie=BILI_COOKIE).fetch()  # 解析
    post.save_dir = BILI_SAVE_DIR
    post.merge_dir = BILI_SAVE_DIR
    video_id = post.bvid
    title = _safe_filename(post.title or video_id)
    # 预览视频
    if post.preview_video:
        result.url = post.preview_video
        pre_name = post.preview_video_download()
        vpath = BILI_SAVE_DIR / f"{pre_name}.mp4"
        result.title = title
        result.vid = video_id
        result.path = vpath
        return result

    post.filter_by_size(max_mb=50)
    url = post.selected_video['url']
    gear_name = post.gear_name  # 1080P
    local_path = BILI_SAVE_DIR / f"{video_id}_{gear_name}_merged.mp4"

    result.title = title
    result.vid = video_id
    result.url = url
    result.path = local_path
    result.gear_name = gear_name
    result.size = post.size_mb
    result.width = post.width
    result.height = post.height
    result.duration = post.duration
    record.url = post.raw_url

    logger.debug(f"初始化size: {post.size_mb}MB")

    def _download():
        # ③ 真正下载
        logger.info("开始下载 -> %s", url)
        vpath, apath = post.download()  # 默认多线程
        v_size = check_file_size(vpath)
        a_size = check_file_size(apath)
        logger.debug(f"视频大小:{v_size}MB")
        logger.debug(f"音频大小:{a_size}MB")
        merged_size = v_size + a_size
        logger.debug(f"预估大小合计:{merged_size}MB")
        out = post.merge(vpath, apath)
        # 更新值
        result.gear_name = post.gear_name
        result.size = check_file_size(out, ndigits=2)
        logger.debug(f"合并完成，大小合计:{result.size}MB")
        logger.info("下载完成 -> %s", out)

    def _judge_size(max_mb=200):
        logger.debug(f"result.size:{result.size}")
        if 50 < result.size < 200:
            logger.debug(f"文件大于50M，开始走上传直链流程，正在筛选下载小于200M的视频")
            # 既然大于50，那就下载200M内质量最高的
            post.filter_by_size(max_mb=max_mb)
            _download()
            # 再次判断是否小于200M,如果还是超出，那就重新选择下载150M的视频
            if result.size > 200:
                result.select_max_size -= 20  # 每次减20，直到小于200以内
                _judge_size(150)

            display = f"*标题：{title}*"
            title_or_md = f"[{escape_markdown(display, version=2)}]"
            result.md_title = title_or_md
            return result

    # ① 先查 file_id 缓存
    if fid := cache_get(video_id):
        logger.debug("命中fid缓存 -> %s", local_path.name)
        result.fid = fid
        return result

    # ② 再看本地磁盘
    if local_path.exists():
        result.size = check_file_size(local_path)
        _judge_size()
        logger.debug("命中磁盘缓存 -> %s", local_path.name)
        return result

    _download()

    _judge_size()

    return result


def _extract_file_id(msg: Message) -> str | None:
    return msg.video.file_id if msg.video else (
        msg.document.file_id if msg.document else None
    )


async def _send_with_cache(sender: MsgSender, bili: Bili, progress_msg: Message) -> Message:
    if fid := cache_get(bili.vid):
        try:
            record.fid[bili.vid] = fid
            record.to_fid = True
            if isinstance(fid, str) and 'http' in fid:
                display = f"*标题：{bili.title}*"
                title_or_md = f"[{escape_markdown(display, version=2)}]({escape_markdown(fid, version=2)})"
                return await sender.send(
                    f"✅ 请点击下方链接下载：\n{title_or_md}",
                    reply=True,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    preview=False,
                    progress_msg=progress_msg,
                )
            return await sender.send_video(fid, caption=bili.title, progress_msg=progress_msg)
        except BadRequest as e:
            if "file not found" in str(e) or "FILE_REFERENCE" in str(e):
                cache_put(bili.vid, None)
            else:
                raise

    msg = await sender.send_video(bili.path,
                                  caption=bili.title,
                                  height=bili.height,
                                  width=bili.width,
                                  duration=bili.duration,
                                  progress_msg=progress_msg
                                  )
    if fid := _extract_file_id(msg):
        cache_put(bili.vid, fid)
    return msg


# ─ entry ─────────────────────────────────────────────
async def bili_command(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        *,
        is_command: bool = True,
) -> Message | None:
    logger.info("bili_command start >>>")
    record.start_time = time.perf_counter()
    uid = update.effective_user.id
    sender = MsgSender(update)

    record.uid = uid
    uname = update.effective_user.username or "(无用户名)"
    name = update.effective_user.full_name  # 显示名
    record.uname = uname
    record.full_name = name

    # 清本地缓存并汇报
    deleted = purge_old_files(BILI_SAVE_DIR, keep_hours=2)

    if deleted:
        await context.bot.send_message(
            ADMIN_ID,
            text="已清除缓存文件：\n" + "\n".join(deleted),
            disable_web_page_preview=True,
        )

    if not rate_limiter.allow(uid):
        return await sender.send("操作过于频繁，请稍后再试")
    if not await task_manager.acquire(uid):
        return await sender.send("您已有任务正在进行，请稍候完成后再发起新任务")

    await sender.react("👀")
    progress_msg = await sender.send("视频下载中.....")

    try:
        if is_command and not context.args:
            return await sender.send("示例：/bili https://www.bilibili.com/video/BV1xx411c7mD", reply=False)

        url = context.args[0] if is_command else update.effective_message.text

        loop = asyncio.get_running_loop()
        bili = await loop.run_in_executor(
            executor, functools.partial(_download_or_hit, url)
        )
        # await progress_msg.delete()  # 视频下载消息删除

        record.parsed_url = bili.url
        record.vid = bili.vid
        record.size = bili.size
        record.title = bili.title

        # 预览视频，直接发送
        if not bili.gear_name:
            return await _send_with_cache(sender, bili, progress_msg=progress_msg)

        logger.info(f"开始上传视频,视频标题:{bili.title}, 文件大小：{bili.size}MB")
        # >50 MB：返回 Markdown 链接
        if bili.size > 50:
            url = await upload(bili.path, sender)  # ← 调 uploader.upload
            record.parsed_url = url
            # 上传成功后，存入缓存
            cache_put(bili.vid, url)  # 这里将 bili.vid 作为 key，url 作为 value 存入缓存
            bili.md_title += f"({escape_markdown(url, version=2)})"
            msg = await progress_msg.edit_text(
                f"✅ 上传完成！\n 由于视频超过 50 MB，请点击下方链接下载：\n{bili.md_title}",
                reply=True,
                parse_mode=ParseMode.MARKDOWN_V2,
                preview=False,
            )
            record.success = True
            return msg

        msg = await _send_with_cache(sender, bili, progress_msg)
        record.success = True
        return msg

    except Exception as e:
        logger.exception("bili_command 失败：%s", e)
        record.exception = e
        await progress_msg.edit_text(EXCEPTION_MSG)
    finally:
        task_manager.release(uid)
        logger.info("bili_command finished.")
        _record_user_parse(record)
