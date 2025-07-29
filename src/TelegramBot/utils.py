# src/TelegramBot/utils.py
import asyncio
import time
from pathlib import Path
from typing import Union, IO, List, Optional, Any, Coroutine
from telegram import InputFile, Message, Update, ReactionTypeEmoji, ReactionTypeCustomEmoji, InputMediaPhoto
from telegram.constants import ChatAction, ParseMode

import logging

from PublicMethods.functool_timeout import retry_on_timeout_async
from TelegramBot.config import SEND_TEXT_TIMEOUT,SEND_VIDEO_TIMEOUT,SEND_MEDIA_GROUP_TIMEOUT,LESS_FLAG

log = logging.getLogger(__name__)


def format_duration(seconds: int | float, ms=False) -> str:
    """
    把时长（秒）转换为“X分Y秒”或“Y秒”。
    Args:
    seconds (int | float): 时长，单位秒。
    Returns:
    str: 格式化后的字符串。
    """
    if not seconds:
        return 'None'

    seconds = int(round(seconds))  # 四舍五入并转成整数

    if seconds < 60:
        return f"{seconds}秒"

    minutes, sec = divmod(seconds, 60)
    return f"{minutes}分{sec}秒" if sec else f"{minutes}分"


class MsgSender:
    def __init__(self, update: Update):
        # 捕获当前这条消息，后续所有 send 都默认“回复”它
        self.msg: Message = update.effective_message
        self._bot = update.get_bot()  # ⚡ 取 bot 句柄
        self._chat_id = update.effective_chat.id

    # --- 统一追加签名 ---
    @staticmethod
    def _add_sig(text: str | None) -> str | None:
        if text is None:
            return LESS_FLAG.lstrip()
        if LESS_FLAG.strip() in text:
            return text                     # 防止重复
        # 避免多余空行，先去掉末尾换行再拼接
        return f"{text.rstrip()}\n\n{LESS_FLAG}"

    async def react(
            self,
            emoji: str | None = None,
            *,
            custom_emoji_id: str | None = None,
            is_big: bool = False,
            message: Message | None = None,
    ) -> None:
        """
        给指定消息添加 / 替换 / 清除表情回应。

        Parameters
        ----------
        emoji : str | None
            普通 Unicode Emoji，例如 "👍" "🔥"；传 None 表示清除已有反应
        custom_emoji_id : str | None
            自定义表情的 ID（二选一，优先于 emoji）
        is_big : bool
            True → 发送“大表情”效果；仅支持部分表情
        message : telegram.Message | None
            目标消息；默认用 sender 捕获的那条消息
        """
        target = message or self.msg
        if custom_emoji_id:
            reaction = [ReactionTypeCustomEmoji(custom_emoji_id)]
        elif emoji:
            reaction = [ReactionTypeEmoji(emoji)]
        else:
            reaction = None  # 清除表情
        await target.set_reaction(reaction=reaction, is_big=is_big)

    # 发送 chat action（正在输入 / 上传等）
    async def action(self, action: ChatAction = ChatAction.TYPING) -> None:
        """向当前聊天发送 chat action（默认 Typing）。"""
        await self._bot.send_chat_action(chat_id=self._chat_id, action=action)

    # 「正在输入」动作
    async def typing(self) -> None:
        await self.action(ChatAction.TYPING)

    # 「正在上传文件」动作
    async def upload(self) -> None:
        await self.action(ChatAction.UPLOAD_DOCUMENT)

    # 「正在查找」动作
    async def find(self) -> None:
        await self.action(ChatAction.FIND_LOCATION)

    @retry_on_timeout_async(*SEND_TEXT_TIMEOUT)
    async def send(
            self,
            text: str,
            *,
            reply: bool = True,
            preview: bool = False,
            **kwargs,
    ):
        """发送纯文本"""
        msg = await self.msg.reply_text(
            text,
            quote=reply,
            disable_web_page_preview=not preview,
            **kwargs,
        )
        return msg

    @retry_on_timeout_async(*SEND_MEDIA_GROUP_TIMEOUT)
    async def send_document(
            self,
            document: Union[str, Path, IO, InputFile],
            *,
            caption: str | None = None,
            reply: bool = False,
            **kwargs,
    ) -> Message:
        """
        发送文件（本地文件/IO 对象/InputFile）或已缓存的 **file_id**。

        Parameters
        ----------
        document : str | Path | IO | InputFile
            - 本地文件路径或 Path               → 自动包装成 InputFile
            - open(...) 返回的文件对象/BytesIO   → 直接用
            - telegram.InputFile                → 直接用
            - Telegram file_id (str)            → 直接转发，0 上传流量
        """
        opened_file = None  # ← 记录自己开的文件句柄

        # ① 本地文件路径 / Path
        if isinstance(document, (str, Path)):
            # 判断“这是不是磁盘上存在的文件” —— 是则打开，不是则当作 file_id
            p = Path(document)
            if p.exists():
                opened_file = p.open("rb")  # 记住句柄
                document = InputFile(p.open("rb"))
            # else: 保持 str，不做处理 → 当作 file_id or URL
        await self.upload()
        start = time.perf_counter()
        try:
            msg: Message = await self.msg.reply_document(
                document=document,
                caption=self._add_sig(caption),
                quote=reply,  # True → 回复原消息
                write_timeout=20,
                read_timeout=20,
                **kwargs,
            )
        finally:
            if opened_file:  # 主开关自己的文件
                opened_file.close()

        log.debug("reply_document 耗时 %.2f s", time.perf_counter() - start)
        return msg

    @retry_on_timeout_async(*SEND_MEDIA_GROUP_TIMEOUT)
    async def send_media_group(
            self,
            media: List[InputMediaPhoto],  # 接收 InputMediaPhoto 对象的列表
            progress_msg: Optional[Message] = None,
            reply_to_message_id: Optional[int] = None,  # 明确添加回复消息ID参数
            **kwargs
    ) -> tuple[Message, ...] | list[Any]:
        """
        发送媒体组（例如图片集）。
        Args:
            media: InputMediaPhoto 对象的列表。
            progress_msg: 用于显示进度的消息对象，发送前会被更新。
            reply_to_message_id: 可选的回复消息ID。
        Returns:
            发送成功的 Message 对象列表。
        """
        if not media:
            log.warning("media_group media 列表为空，不执行发送。")
            return []

        try:
            # 直接使用 self.bot 和 self.chat_id
            # reply_to_message_id 应是具体的消息ID
            send_kwargs = {
                "chat_id": self._chat_id,
                "media": media,
                "parse_mode":ParseMode.HTML
            }
            if reply_to_message_id:
                send_kwargs["reply_to_message_id"] = reply_to_message_id
            send_kwargs.update(kwargs)  # 将 kwargs 合并到发送参数中

            sent_messages = await self._bot.send_media_group(**send_kwargs, read_timeout=60)

            if progress_msg:
                try:
                    await progress_msg.delete()  # 发送成功后删除进度消息
                except Exception as e:
                    log.warning(f"无法删除进度消息: {e}")
            return sent_messages
        except Exception as e:
            log.error(f"发送媒体组失败: {e}", exc_info=True)
            if progress_msg:
                try:
                    await progress_msg.edit_text("发送图片集失败。")
                except Exception as edit_e:
                    log.warning(f"无法编辑失败消息: {edit_e}")
            raise  # 重新抛出异常，让上层处理

    @retry_on_timeout_async(*SEND_VIDEO_TIMEOUT)
    async def send_video(
            self,
            video: Union[str, Path, IO, InputFile],
            progress_msg: Message | None = None,
            *,
            caption: str | None = None,
            duration: int | None = None,
            width: int | None = None,
            height: int | None = None,
            reply: bool = False,
            supports_streaming: bool = True,
            **kwargs,
    ) -> Message:
        """
        发送视频（支持 Telegram 内联流媒体播放）。
        video:
            - 本地文件路径 / Path   → 自动 InputFile
            - 已打开文件对象 / BytesIO
            - telegram.InputFile
            - file_id (str)        → 秒回，不再上传
        """
        opened_file = None

        if isinstance(video, (str, Path)):
            p = Path(video)
            if p.exists():
                opened_file = p.open(("rb"))
                video = InputFile(opened_file, filename=p.name)
        # else: 认为是 file_id，保持原样

        start = time.perf_counter()
        log.debug(f"视频上传参数 >>> duration:{format_duration(duration)}, width:{width}, height:{height}")
        log.debug("开始上传，reply_video 视频开始上传中......")
        # progress_msg = await self.send("视频上传中，请稍等")
        if progress_msg:
            await progress_msg.edit_text("视频上传中....")
        await self.upload()  # 上传状态
        try:
            msg: Message = await self.msg.reply_video(
                video=video,
                caption=self._add_sig(caption),
                duration=duration,
                width=width,
                height=height,
                quote=reply,
                supports_streaming=supports_streaming,
                write_timeout=100,
                read_timeout=60,
                **kwargs,
            )
        finally:
            try:
                await progress_msg.delete()
            except Exception:
                log.warning("占位消息已删除,无需删除")
            if opened_file:
                opened_file.close()
        log.debug("上传完成，reply_video 耗时 %.2f s", time.perf_counter() - start)
        return msg
