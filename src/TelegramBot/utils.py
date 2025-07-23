# src/TelegramBot/utils.py
import time
from pathlib import Path
from typing import Union, IO
from telegram import InputFile, Message, Update, ReactionTypeEmoji, ReactionTypeCustomEmoji, InputMediaVideo
from telegram.constants import ChatAction

import logging

log = logging.getLogger(__name__)


def format_duration(duration_value: int | float) -> str:
    """
    把时长转换为“X分Y秒”或“Y秒”。
    函数会尝试判断传入值是秒还是毫秒，并进行转换。

    Args:
        duration_value (int | float): 时长，单位可能是秒或毫秒。

    Returns:
        str: 格式化后的字符串。
    """
    if duration_value is None or duration_value == 0:
        return '0秒'  # 0秒比None更准确

    # 尝试判断是否是毫秒：如果数值非常大（例如超过1小时的毫秒数），
    # 且没有小数部分（或小数部分很小），则很可能是毫秒。
    # 这是一个启发式判断，可能不完美，但能覆盖大部分情况。
    # 1小时 = 3600秒 = 3,600,000毫秒
    # 设定一个阈值，例如超过 2 小时的毫秒数，就认为是毫秒
    # 更安全的判断是检查是否是整数且非常大。

    # 优先假设是秒，然后判断极端情况
    seconds = duration_value

    # 假设如果传入的数值是一个非常大的整数（例如，大于1000000），则很可能是毫秒
    # 并且如果转换成秒后，它的小数部分接近于0（即原始值是1000的倍数）
    if isinstance(duration_value, int) and duration_value > 60000 and (duration_value % 1000 == 0):
        # 尝试转换为秒
        seconds = duration_value / 1000.0
    elif isinstance(duration_value, float) and duration_value > 60000:  # 如果是浮点数且数值很大，也可能是毫秒
        # 检查小数点后3位是否全是0，即是千的倍数
        if abs(duration_value * 1000 - round(duration_value * 1000)) < 0.001:
            seconds = duration_value / 1000.0

    # 对秒数进行四舍五入并转成整数
    seconds = int(round(seconds))

    if seconds <= 0:  # 如果转换后小于等于0，统一返回0秒
        return '0秒'

    # 核心逻辑：转换为分秒
    minutes, sec = divmod(seconds, 60)

    if minutes > 0:
        if sec > 0:
            return f"{minutes}分{sec}秒"
        else:  # 恰好是分钟的整数倍
            return f"{minutes}分"
    else:  # 小于1分钟
        return f"{seconds}秒"


class MsgSender:
    def __init__(self, update: Update):
        # 捕获当前这条消息，后续所有 send 都默认“回复”它
        self.msg: Message = update.effective_message
        self._bot = update.get_bot()  # ⚡ 取 bot 句柄
        self._chat_id = update.effective_chat.id

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

    async def send_document(
            self,
            document: Union[str, Path, IO, InputFile],
            *,
            caption: str | None = None,
            reply: bool = True,
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
                caption=caption,
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

    async def send_video(
            self,
            video: Union[str, Path, IO, InputFile],
            progress_msg: Message | None = None,
            *,
            caption: str | None = None,
            duration: int | None = None,
            width: int | None = None,
            height: int | None = None,
            reply: bool = True,
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
        await progress_msg.edit_text("视频上传中....")
        await self.upload()  # 上传状态
        try:
            msg: Message = await self.msg.reply_video(
                video=video,
                caption=caption,
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
            await progress_msg.delete()
            if opened_file:
                opened_file.close()
        log.debug("上传完成，reply_video 耗时 %.2f s", time.perf_counter() - start)
        return msg
