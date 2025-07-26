# TelegramBot/handlers/generic_handler.py
import asyncio
import functools
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Union

from telegram import Update, Message, InputMediaPhoto, InputMediaVideo
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from TelegramBot.cleaner import purge_old_files
from TelegramBot.config import EXCEPTION_MSG, MAX_THREAD_WORKERS, BILI_PREVIEW_VIDEO_TITLE, ADMIN_ID
from TelegramBot.task_manager import TaskManager
from TelegramBot.rate_limiter import RateLimiter
from TelegramBot.utils import MsgSender
from TelegramBot.file_cache import get as cache_get, put as cache_put
from TelegramBot.recorder_parse import UserParseResult, _record_user_parse
from TelegramBot.parsers.base import BaseParser, ParseResult

executor = ThreadPoolExecutor(max_workers=MAX_THREAD_WORKERS)
rate_limiter = RateLimiter(min_interval=3.0)  # 示例值
task_manager = TaskManager()

logger = logging.getLogger(__name__)


async def generic_command_handler(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        parser_class: type[BaseParser] | None,
        platform_name: str,
        save_dir: Path | None,
        is_command: bool = True,
):
    """
    通用命令处理器，处理所有平台的解析请求。

    :param update: Telegram Update 对象.
    :param context: Telegram Context 对象.
    :param parser_class: 要使用的具体解析器类 (e.g., DouyinParser).
    :param platform_name: 平台名称 (e.g., "douyin"), 用于日志记录.
    :param save_dir: 保存路径
    :param is_command: 触发方式是命令还是纯文本.
    """
    # ---- 1. 初始化和前置检查 ----
    sender = MsgSender(update)
    uid = update.effective_user.id
    record = UserParseResult(uid=uid, platform=platform_name, start_time=time.perf_counter())

    # 填充用户信息 (这部分代码是通用的)
    record.uname = update.effective_user.username or "(无用户名)"
    record.full_name = (update.effective_user.last_name or '') + (update.effective_user.first_name or '')

    if save_dir:
        # 清本地缓存并汇报
        clear = [300, 0]
        if platform_name == 'douyin':
            clear = [200, 50]
        elif platform_name == 'bilibili':
            clear = [200, 50]
        elif platform_name == 'music':
            clear = [100, 20]

        deleted_size = purge_old_files(save_dir, *clear)
        if deleted_size:
            await context.bot.send_message(
                ADMIN_ID,
                text=f"已清除目录下 {save_dir}\n缓存文件：{deleted_size:.2f} MB",
                disable_web_page_preview=True,
        )

    # 速率和任务限制 (通用)
    if not rate_limiter.allow(uid):
        await sender.send("操作过于频繁，请稍后再试")
        return
    if not await task_manager.acquire(uid):
        await sender.send("您已有任务正在进行，请稍候完成后再发起新任务")
        return

    target_url = context.args[0] if is_command else update.effective_message.text
    record.input_content = target_url

    await sender.react("👀")

    # ---- 2. 解析输入和准备 ----
    try:
        if is_command and not context.args:
            await sender.send(f"使用方法: /{platform_name} <链接>")
            return
        if not parser_class:
            await sender.send(f"使用方法: 发送视频链接开始使用\n例：https://v.douyin.com/7kSRzFPFob4/")
            return

        progress_msg = await sender.send("正在处理中...")  # 发送一个占位消息
        await sender.typing()

        parser_instance = parser_class(target_url, save_dir)

        # —— 3a. 轻量 peek，看下有没有缓存 ——
        # vid, title = await parser_instance.peek()
        try:
            vid, title = await parser_instance.peek()
        except Exception:
            # 如果 peek 本身也出问题，继续走 parse 分支
            vid, title = None, None

        # 检查 file_id 缓存
        if vid:
            if file_id := cache_get(vid):
                logger.info(f"命中 file_id 缓存 ({vid})")
                try:
                    await _send_by_file_id(sender, file_id, title)
                    record.fid[vid] = file_id
                    record.to_fid = True
                    record.success = True
                    return
                except BadRequest as e:
                    logger.warning(f"file_id失效，清理并回退到上传: {e}")
                    cache_put(vid, None)
                    # 重新显示占位消息
                    progress_msg = await sender.send("缓存已失效，正在重新上传...")

        # ---- 3. 执行核心解析 (I/O密集，放入线程池) ----
        loop = asyncio.get_running_loop()
        # parser_instance = parser_class(target_url, save_dir)

        logger.info(f"functools run parse task 开始解析")
        # functools.partial is used to pass arguments to the function running in the executor
        # parse_task = functools.partial(parser_instance.parse)
        parse_result: ParseResult = await parser_instance.parse()

        # 将解析结果同步到日志记录器
        _sync_record_with_result(record, parse_result)

        # ---- 4. 根据解析结果发送消息 ----
        if not parse_result.success:
            logger.info(f"解析失败，发送异常消息, 异常详情:{parse_result.error_message}")
            error_msg = parse_result.error_message or EXCEPTION_MSG
            await sender.send(EXCEPTION_MSG)
            record.exception = error_msg
            return

        # 优先处理直接发送文本的情况 (如超大文件链接)
        if parse_result.content_type == 'link' and parse_result.text_message:
            logger.info(f"直接发送文本")
            await sender.send(
                parse_result.text_message,
                parse_mode=ParseMode.MARKDOWN_V2,
                disable_web_page_preview=True
            )
            record.success = True
            return

        # ---- 5. 上传文件并缓存 file_id ----
        logger.info(f"_upload_and_send 上传文件并缓存 file_id")
        msg = await _upload_and_send(sender, parse_result, progress_msg, update.effective_message.id)

        # 缓存新的 file_id
        if msg and parse_result.vid:
            # 对于图集，Telegram返回一个消息列表
            # 目前只缓存单视频/音频的file_id
            if parse_result.content_type in ['video', 'audio']:
                if file_id := _extract_file_id(msg):
                    cache_put(parse_result.vid, file_id)
                    logger.debug(f"记录新的 file_id 缓存 -> {parse_result.vid}")

        record.success = True

    except Exception as e:
        logger.exception(f"{platform_name}_command 失败: {e}")
        await sender.send(EXCEPTION_MSG)
        record.exception = str(e)
    finally:
        # ---- 6. 清理和收尾 ----
        try:
            await progress_msg.delete()
        except Exception:
            logger.warning(f"占位消息已删除，无需再次删除")
        task_manager.release(uid)
        _record_user_parse(record)  # 记录日志
        logger.info(f"{platform_name}_command finished.")


def _sync_record_with_result(record: UserParseResult, result: ParseResult):
    """用ParseResult的数据更新UserParseResult"""
    record.success = result.success
    record.title = result.title
    record.vid = result.vid
    record.url = result.original_url
    record.parsed_url = result.download_url
    record.size = result.size_mb
    if not result.success:
        record.exception = result.error_message


def _extract_file_id(msg: Message) -> str | None:
    """从消息中提取 file_id (兼容多种类型)"""
    if msg.video: return msg.video.file_id
    if msg.audio: return msg.audio.file_id
    if msg.document: return msg.document.file_id
    return None


async def _send_by_file_id(sender: MsgSender, file_id: str, caption: str):
    """使用缓存的file_id发送 (此处可以扩展支持不同类型)"""
    # 简单的实现，假设所有缓存都是 document 类型，你可以根据需要扩展
    return await sender.send_document(file_id, caption=caption)


# 特殊处理片段
def _handle_special_field(result: ParseResult):
    # bilibili
    if result.bili_preview_video:
        logger.debug(f"{BILI_PREVIEW_VIDEO_TITLE}, {result.original_url}")
        result.title = f"{result.title}\n{BILI_PREVIEW_VIDEO_TITLE}"

async def _upload_and_send(sender: MsgSender, result: ParseResult, progress_msg: Message, reply_to_id: int):
    """根据内容类型上传并发送文件"""
    content_type = result.content_type

    # video 和 audio 的处理逻辑保持不变
    if content_type in ["video", "audio"] and result.media_items:
        item = result.media_items[0]
        if content_type == "video":
            await progress_msg.edit_text("视频下载完成，正在上传...")
            try:
                _handle_special_field(result)
                return await sender.send_video(
                    video=item.local_path,
                    caption=result.title,
                    duration=item.duration,
                    width=item.width,
                    height=item.height,
                    progress_msg=progress_msg,  # 传递progress_msg让send_video处理
                )
            except Exception as e:
                raise Exception(f"发送视频时发生未知错误: {e}")
        else:  # audio
            await progress_msg.edit_text("音频下载完成，正在上传...")
            try:
                return await sender.send_document(document=item.local_path, caption=result.title)
            except Exception as e:
                raise Exception(f"发送音频时发生未知错误: {e}")

    # 图集
    elif content_type == "image_gallery" and result.media_items:
        await progress_msg.edit_text(f"图集下载完成，正在准备上传 {len(result.media_items)} 个媒体...")

        # 用于构建发送给 Telegram API 的媒体列表
        media_group_items: List[Union[InputMediaPhoto, InputMediaVideo]] = []
        # 用于妥善管理文件句柄，防止资源泄漏
        file_handles = []

        try:
            # 迭代每一个媒体项，而不是使用列表推导式
            for i, item in enumerate(result.media_items):
                # 为每个文件打开一个句柄，并记录下来以便后续关闭
                f = Path(item.local_path).open('rb')
                file_handles.append(f)

                # 只有媒体集中的第一个项目才附带标题
                caption_text = result.title if i == 0 else None

                # 【核心逻辑】根据 media_items 中的 file_type 判断是创建视频还是图片对象
                if item.file_type == 'video':
                    # 如果是视频，创建 InputMediaVideo
                    media_group_items.append(
                        InputMediaVideo(
                            media=f,
                            caption=caption_text,
                            width=item.width,
                            height=item.height,
                            duration=item.duration
                        )
                    )
                    logger.debug(f"向媒体集添加视频: {item.local_path}")
                else:
                    # 否则，默认作为图片处理，创建 InputMediaPhoto
                    media_group_items.append(
                        InputMediaPhoto(
                            media=f,
                            caption=caption_text
                        )
                    )
                    logger.debug(f"向媒体集添加图片: {item.local_path}")

            # 调用 sender 的 send_media_group 方法发送构建好的混合媒体列表
            # progress_msg 会在 sender.send_media_group 内部被处理
            # 将 media_group_items 列表每次分批（最多 10 个）发送，
            await progress_msg.edit_text(f"图片上传中... (共 {len(media_group_items)} 张)")
            all_results = []
            # 按步长 10 切片
            for i in range(0, len(media_group_items), 10):
                chunk = media_group_items[i: i + 10]
                logger.debug(f"分片发送开始：第 {i // 10 + 1} 组，共 {len(chunk)} 个媒体（索引 {i}–{i + len(chunk) - 1}）")
                result = await sender.send_media_group(
                    media=chunk,
                    progress_msg=progress_msg,
                    reply_to_message_id=reply_to_id
                )
                all_results.extend(result)
            logger.debug("所有分片发送完毕，共发送媒体组 %d 组。", (len(media_group_items) + 9) // 10)
            return all_results
        except Exception as e:
            raise Exception(f"发送媒体组时发生未知错误: {e}")
        finally:
            # 使用 finally 确保无论发送成功与否，所有打开的文件句柄都被关闭
            for f in file_handles:
                f.close()
            logger.debug(f"已关闭 {len(file_handles)} 个媒体文件句柄。")

    else:
        await progress_msg.edit_text("无法处理的媒体类型或没有媒体文件。")
        return None
