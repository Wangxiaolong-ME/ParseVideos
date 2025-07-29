# TelegramBot/handlers/generic_handler.py
import asyncio
import functools
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Union

from prompt_toolkit.input.win32 import attach_win32_input
from telegram import Update, Message, InputMediaPhoto, InputMediaVideo, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown

from TelegramBot.cleaner import purge_old_files
from TelegramBot.config import EXCEPTION_MSG, MAX_THREAD_WORKERS, BILI_PREVIEW_VIDEO_TITLE, ADMIN_ID, USAGE_TEXT, \
    DOUYIN_OVER_SIZE, IMAGES_CACHE_SWITCH, LESS_FLAG
from TelegramBot.task_manager import TaskManager
from TelegramBot.rate_limiter import RateLimiter
from TelegramBot.utils import MsgSender
from TelegramBot.file_cache import put as cache_put, delete as cache_del, get_full as cache_get_full
from TelegramBot.recorder_parse import UserParseResult, _record_user_parse
from TelegramBot.parsers.base import BaseParser, ParseResult
from TelegramBot.uploader import upload

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
        elif platform_name == 'xhs':
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
        # await sender.send("操作过于频繁，请稍后再试")
        return
    if not await task_manager.acquire(uid):
        await sender.send("您已有任务正在进行，请稍候完成后再发起新任务")
        return

    target_url = context.args[0] if is_command else update.effective_message.text
    record.input_content = target_url

    await sender.react("👀")

    # ---- 2. 解析输入和准备 ----
    e = ''
    try:
        if is_command and not context.args:
            await sender.send(f"使用方法: /{platform_name} <链接>")
            return
        if not parser_class:
            await sender.send(USAGE_TEXT)
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
            entry = cache_get_full(vid)
            if entry:  # 旧缓存是 str，新缓存是 dict
                logger.debug(f"命中缓存vid -----> {vid}")
                if isinstance(entry, dict):
                    title = entry["title"]
                    file_id = entry["value"]
                    rm_data = entry.get("reply")
                    parse_mode = entry.get("parse_mode") or ParseMode.HTML
                    special = entry.get("special")
                else:  # 兼容旧格式
                    file_id = entry
                    rm_data = None
                    parse_mode = ParseMode.HTML
                    special = ''

                if IMAGES_CACHE_SWITCH and isinstance(file_id, list):  # 图集是否走缓存开关
                    pass
                else:
                    rm_obj = InlineKeyboardMarkup(rm_data) if rm_data else None
                    await _send_by_file_id(
                        sender,
                        file_id,
                        title,
                        reply_markup=rm_obj,
                        parse_mode=parse_mode,
                        special=special,
                    )
                    record.success = True
                    return record.success

        # ---- 3. 执行核心解析 (I/O密集，放入线程池) ----
        # loop = asyncio.get_running_loop()
        # parser_instance = parser_class(target_url, save_dir)

        logger.info(f"functools run parse task 开始解析")
        # functools.partial is used to pass arguments to the function running in the executor
        # parse_task = functools.partial(parser_instance.parse)
        parse_result: ParseResult = await parser_instance.parse()

        # 将解析结果同步到日志记录器
        _sync_record_with_result(record, parse_result)

        # ---- 4. 根据解析结果发送消息 ----
        logger.info(f"解析结果检查: success={parse_result.success}, content_type={parse_result.content_type}")
        logger.info(
            f"needs_quality_selection={parse_result.needs_quality_selection}, quality_options={len(parse_result.quality_options) if parse_result.quality_options else 0}")
        logger.info(f"media_items={len(parse_result.media_items) if parse_result.media_items else 0}")

        if not parse_result.success:
            logger.info(f"解析失败，发送异常消息, 异常详情:{parse_result.error_message}")
            error_msg = parse_result.error_message or EXCEPTION_MSG
            await progress_msg.edit_text(EXCEPTION_MSG)
            record.exception = error_msg
            return

        # 优先处理直接发送文本的情况 (如超大文件链接)
        if parse_result.content_type == 'link' and parse_result.text_message:
            logger.info(f"直接发送文本")
            await sender.send(
                parse_result.text_message,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply=False,
            )
            record.success = True
            return True

        # 先声明，确保两个分支都有 rm
        rm: InlineKeyboardMarkup | None = None

        # 处理需要质量选择的情况 (抖音多分辨率)
        # 增加额外检查：只要有quality_options就显示按钮
        if (parse_result.needs_quality_selection and parse_result.quality_options) or \
                (parse_result.quality_options and len(parse_result.quality_options) > 0):
            logger.info(f"处理抖音多分辨率选择")
            logger.info(f"预览链接: {parse_result.preview_url}")
            logger.info(f"质量选项数量: {len(parse_result.quality_options)}")

            # 直接显示分辨率选择按钮（标题包含预览链接）
            msg, rm = await _send_quality_selection(sender, parse_result, progress_msg, record)
        else:
            # ---- 5. 上传文件并缓存 file_id ----
            logger.info(f"_upload_and_send 上传文件并缓存 file_id")
            msg = await _upload_and_send(sender, parse_result, progress_msg, record)

        # 缓存新的 file_id
        if msg and parse_result.vid:
            await _save_cache_fid(msg, parse_result, reply_markup=rm)

        return record.success

    except Exception as e:
        logger.exception(f"{platform_name}_command 失败: {e}")
        await sender.send(EXCEPTION_MSG)
        record.exception = str(e)
    finally:
        # ---- 6. 清理和收尾 ----
        try:
            if record.success:
                await progress_msg.delete()
        except Exception:
            logger.warning(f"占位消息已删除，无需再次删除")
        task_manager.release(uid)
        _record_user_parse(record)  # 记录日志
        logger.info(f"{platform_name}_command finished.")


async def _save_cache_fid(msg: Message, parse_result: ParseResult, *, reply_markup: InlineKeyboardMarkup | None = None):
    logging.debug(f"缓存fid...")
    # 先把 InlineKeyboardMarkup 转成纯字典，兼容 v2 / v3
    if reply_markup:
        # PTB 统一用 to_dict()
        rm_dict = reply_markup.to_dict()
        reply_data = rm_dict["inline_keyboard"]  # 纯列表，能 JSON 序列化
    else:
        reply_data = None
    # 单视频/音频的file_id
    if parse_result.content_type in ['video', 'audio']:
        if file_id := _extract_file_id(msg):
            cache_put(
                parse_result.vid,
                file_id,
                title=parse_result.html_title or parse_result.title,
                reply=reply_data,
                parse_mode=ParseMode.HTML,
            )
            logger.debug(f"记录新的 file_id 缓存 -> {parse_result.vid}")
    # 图集消息：Telegram 返回的是消息列表
    elif parse_result.content_type == 'image_gallery':
        logging.debug(f"写入图集fid...")
        if isinstance(msg, list):
            album_file_ids = _build_image_gallery_cache_fid(msg)
            # 使用图集的唯一 ID 缓存整个 file_id 列表，方便后续取用
            if album_file_ids:
                cache_put(
                    parse_result.vid,
                    album_file_ids,
                    title=parse_result.html_title or parse_result.title,
                    reply=reply_data,
                    parse_mode=ParseMode.HTML,
                )
                logger.debug(f"记录新的图集 file_id 列表 -> {parse_result.vid}: {album_file_ids}")


# 生成图集的缓存ID列表,视频前缀VIDEO,图片前缀IMAGE
def _build_image_gallery_cache_fid(msg):
    album_file_ids = []
    # 遍历图集中的每条消息
    for index, m in enumerate(msg):
        fid = _extract_file_id(m)  # 提取每条消息的 file_id
        if fid:
            # 根据 file_type 判断是视频还是图片，添加相应的前缀
            if m.video:  # 如果是视频类型
                album_file_ids.append(f"VIDEO{fid}")
            else:  # 如果是图片类型
                album_file_ids.append(f"IMAGE{fid}")
    return album_file_ids


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
    if msg.photo: return msg.photo[-1].file_id  # tuple中多张尺寸图片,依次由小到大升序,取最大的
    logger.warning(f"未能从消息中提取 file_id")
    return None


async def _send_by_file_id(sender: MsgSender, file_id: str or list, caption: str, *,
                           reply_markup: InlineKeyboardMarkup | None = None,
                           parse_mode: str | None = ParseMode.HTML, special: str):
    """使用缓存的file_id发送 (此处可以扩展支持不同类型)"""

    # 如果value是链接,直接复制文本框内容发送,这种是上传三方平台用于预览下载视频的
    if special =="catbox" or 'catbox' in file_id:
        return await sender.send(
            text=caption,
            parse_mode=parse_mode,
            reply=False,
        )

    # 如果是单个 file_id，直接发送文档
    elif isinstance(file_id, str):
        return await sender.send_document(
            file_id,
            caption=caption,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )

    # 如果是图集，遍历每个 file_id 发送
    elif isinstance(file_id, list):
        media_group_items = []
        for file in file_id:
            # 去掉前缀并添加到 media_group_items 中
            if file.startswith('VIDEO'):
                file = file[len('VIDEO'):]  # 去掉 'VIDEO_' 前缀
                media_group_items.append(InputMediaVideo(media=file, caption=caption, parse_mode=ParseMode.HTML))
            elif file.startswith('IMAGE'):
                file = file[len('IMAGE'):]  # 去掉 'IMAGE_' 前缀
                media_group_items.append(InputMediaPhoto(media=file, caption=caption, parse_mode=ParseMode.HTML))

        # 如果媒体组的数量超过10个，分批发送
        media_group_batches = [media_group_items[i:i + 10] for i in range(0, len(media_group_items), 10)]

        all_sent_messages = []
        for idx, batch in enumerate(media_group_batches):
            sent_messages = await sender.send_media_group(media=batch)
            all_sent_messages.extend(sent_messages)

        return all_sent_messages  # 返回所有批次的消息
    else:
        raise ValueError("Invalid file_id type")


# 特殊处理片段
def _handle_special_field(result: ParseResult):
    # bilibili
    if result.bili_preview_video:
        logger.debug(f"{BILI_PREVIEW_VIDEO_TITLE}, {result.original_url}")
        result.title = f"{result.title}\n{BILI_PREVIEW_VIDEO_TITLE}"


async def _upload_and_send(sender: MsgSender, result: ParseResult, progress_msg: Message, record):
    """根据内容类型上传并发送文件"""
    content_type = result.content_type

    # video 和 audio 的处理逻辑保持不变
    if content_type in ["video", "audio"] and result.media_items:
        item = result.media_items[0]
        if content_type == "video":
            if result.size_mb > 50:
                if progress_msg:
                    await progress_msg.delete()
                progress_msg = await sender.send("视频较大，改用上传至三方平台预览…", reply=False)
                # 这里主要是B站合并后的大文件上传至三方在线平台,可以通过直链点进去观看下载
                await sender.upload()
                try:
                    _handle_special_field(result)
                    url = await upload(item.local_path, sender, progress_msg)
                    record.parsed_url = url
                    result.html_title = f"<a href=\"{url}\"><b>标题：{result.title}</b></a>"
                    text = f"✅ 上传完成！\n 由于视频超过 50 MB，请点击下方链接下载：\n{result.html_title}"
                    text += f"\n\n{LESS_FLAG}"
                    # 上传成功后，存入缓存
                    cache_put(result.vid, url, title=text, parse_mode="HTML", special="catbox")
                    return await progress_msg.edit_text(
                        text,
                        parse_mode=ParseMode.HTML,
                    )
                except Exception as e:
                    raise Exception(f"发送大视频文档失败: {e}")
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
                base_caption = result.title if i == 0 else None
                # 如果是首个视频且有背景音乐链接，就在标题下方加上“背景乐下载”超链接
                if i == 0 and getattr(result, 'audio_uri', None):
                    # 使用 HTML 格式：<a href="链接">文本</a>
                    music_link = f'<b>🎧<a href="{result.audio_uri}">下载背景乐 {result.audio_title}</a></b>'
                    # 如果已经有标题，就换行追加；否则直接使用链接
                    caption_text = f"{base_caption}\n\n{music_link}" if base_caption else music_link
                else:
                    caption_text = base_caption

                result.html_title = caption_text
                # 【核心逻辑】根据 media_items 中的 file_type 判断是创建视频还是图片对象
                if item.file_type == 'video':
                    # 如果是视频，创建 InputMediaVideo
                    media_group_items.append(
                        InputMediaVideo(
                            media=f,
                            caption=caption_text,
                            parse_mode=ParseMode.HTML,
                            width=item.width,
                            height=item.height,
                            duration=item.duration,
                            supports_streaming=True,
                        )
                    )
                    logger.debug(f"向媒体集添加视频: {item.local_path}")
                else:
                    # 否则，默认作为图片处理，创建 InputMediaPhoto
                    media_group_items.append(
                        InputMediaPhoto(
                            media=f,
                            caption=caption_text,
                            parse_mode=ParseMode.HTML,
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
                    parse_mode=ParseMode.HTML,
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


async def _send_quality_selection(sender: MsgSender, result: ParseResult, progress_msg: Message,
                                  record: UserParseResult):
    """发送分辨率选择按钮"""
    if not result.quality_options:
        await sender.send("没有可用的分辨率选项")
        return

    logger.debug(f"Sending quality selection for video: {result.vid}")
    logger.debug(f"Title: {repr(result.title)}")
    logger.debug(f"Quality options count: {len(result.quality_options)}")

    # 按分辨率降序排列，50M以内的放在前面
    default_options = [opt for opt in result.quality_options if opt.is_default]
    other_options = [opt for opt in result.quality_options if not opt.is_default]

    # 合并选项：默认选项在前，其他按分辨率降序
    sorted_options = default_options + sorted(other_options, key=lambda x: x.resolution, reverse=True)

    # 构建内联键盘按钮，每行2个
    keyboard = []
    logger.debug(f"开始构建URL按钮，排序后选项: {len(sorted_options)}")

    for i in range(0, len(sorted_options), 2):
        row = []
        for j in range(2):
            if i + j < len(sorted_options):
                option = sorted_options[i + j]
                # 按钮文本格式：分辨率 + 文件大小
                button_text = f"{option.resolution}p"
                if option.size_mb:
                    button_text += f" ({option.size_mb:.1f}MB)"
                if option.is_default:
                    button_text = f"⭐当前预览 {button_text}"  # 默认选项加星标

                # 使用URL按钮直接跳转到下载链接
                logger.debug(f"创建URL按钮: {button_text} -> {option.download_url}")
                row.append(InlineKeyboardButton(text=button_text, url=option.download_url))
        keyboard.append(row)

    # 构造音频下载按钮
    if result.audio_uri:
        text = f"🎵 MUSIC ({result.audio_title})"
        audio_btn = InlineKeyboardButton(text=text, url=result.audio_uri)

        # 如果最后一行不足 2 个，就直接 append 到最后一行
        if keyboard and len(keyboard[-1]) < 2:
            keyboard[-1].append(audio_btn)
        else:
            # 否则新起一行，只放音频按钮
            keyboard.append([audio_btn])
    logger.debug(f"共创建 {len(keyboard)} 行按钮")

    # URL按钮不需要取消按钮

    reply_markup = InlineKeyboardMarkup(keyboard)

    # 发送选择消息 - 使用HTML格式并进行HTML转义
    import html
    try:
        title = result.title or '抖音视频'
        safe_title = html.escape(title)
        logger.debug(f"Original title: {repr(title)}")
        logger.debug(f"Escaped title: {repr(safe_title)}")

        # 构建标题，如果有预览链接则在🎬处添加链接
        if result.preview_url:
            # 有预览链接，标题变成可点击链接
            message_text = f"<b>{safe_title}</b>"
            # message_text += "👆 点击🎬预览视频\n\n"
            logger.debug(f"添加预览链接到标题: {result.preview_url}")
        else:
            # 没有预览链接，普通标题
            message_text = f"🎬 <b>{safe_title}</b>"

        logger.debug(f"Final message length: {len(message_text)}")

    except Exception as e:
        logger.error(f"Error formatting quality selection message: {e}")
        # Fallback to simple message without HTML formatting
        message_text = f"视频标题: {result.title or 'Unknown'}"
        message_text += f"\n共找到 {len(result.quality_options)} 个分辨率选项"

    # 不再需要存储质量选项，因为使用URL按钮直接跳转
    try:
        if result.size_mb > 50:
            raise Exception("视频体积超50M")
        item = result.media_items[0] if result.media_items else None
        msg = await sender.send_video(
            video=item.local_path,
            caption=message_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
            duration=item.duration,
            width=item.width,
            height=item.height,
            progress_msg=progress_msg
        )
        logger.debug("Quality selection message sent successfully")
        result.success = True
        result.html_title = message_text
        return msg, reply_markup
    except Exception as e:
        logger.error(f"{e}")
        # Fallback: try without parse_mode
        try:
            text = "请选择分辨率下载"
            # 走到这条分支一般都是 视频超过体积了,如果超体积,告知用户原因
            if result.size_mb > 50:
                text = DOUYIN_OVER_SIZE
            simple_message = f"视频: {result.title or 'Unknown'}\n\n{text}"
            msg = await sender.send(
                simple_message,
                reply_markup=reply_markup,
                reply=False
            )
            logger.warning("Sent fallback quality selection message")
            result.html_title = message_text
            return msg, reply_markup
        except Exception as e:
            logger.error(f"兜底发送, 保留失败标识,避免原消息被删除{e}")
