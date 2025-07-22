import asyncio
from pathlib import Path

from telegram import Bot, InputFile
from telegram.constants import ParseMode
from TelegramBot.config import TELEGRAM_TOKEN_ENV, ADMIN_ID


async def send_emoji_message():
    # 替换成你的 Bot Token
    bot_token = TELEGRAM_TOKEN_ENV
    chat_id = ADMIN_ID  # 目标 chat_id

    bot = Bot(token=bot_token)

    # 直接发送 Unicode emoji
    text = "📥"

    # 发送消息，parse_mode 使用 MarkdownV2
    await bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)


# async def get_latest_message():
#     bot_token = TELEGRAM_TOKEN_ENV
#     bot = Bot(token=bot_token)
#
#     # 获取最新的消息
#     updates = await bot.get_updates(limit=1)
#
#     if updates:
#         latest_message = updates[0].message
#         text = latest_message.text
#         print(f"Message Text: {text}")
#         print(f"{latest_message.entities}")
#         # 如果消息中包含表情，通常是通过Unicode显示
#         # 或者可以通过 tg-emoji 的 ID 进行进一步的解析
#         return text


async def send_custom_emoji():
    bot_token = TELEGRAM_TOKEN_ENV
    chat_id = ADMIN_ID  # 目标 chat_id

    bot = Bot(token=bot_token)

    # 使用 custom_emoji_id 来发送
    text = '📥'  # 客户端可以看到的效果，直接用 emoji

    # 使用 <tg-emoji> 标签发送 emoji
    message = await bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)

    print(message.text)


async def get_latest_message():
    bot_token = TELEGRAM_TOKEN_ENV
    bot = Bot(token=bot_token)

    # 获取最新的消息
    updates = await bot.get_updates(limit=1)

    if updates:
        latest_message = updates[0].message
        text = latest_message.text
        print(f"Message Text: {text}")

        # 如果消息中包含表情，通常是通过 Unicode 或 custom_emoji_id 显示
        for entity in latest_message.entities:
            if entity.type == "custom_emoji":
                print(f"Custom Emoji ID: {entity.custom_emoji_id}")

        return text


async def send_video(
        video:str,
        *,
        caption: str | None = None,
        duration: int | None = None,
        width: int | None = None,
        height: int | None = None,
        supports_streaming: bool = True,
        **kwargs,
):
    """
    发送视频（支持 Telegram 内联流媒体播放）。
    video:
        - 本地文件路径 / Path   → 自动 InputFile
        - 已打开文件对象 / BytesIO
        - telegram.InputFile
        - file_id (str)        → 秒回，不再上传
    """
    bot_token = TELEGRAM_TOKEN_ENV
    chat_id = ADMIN_ID  # 目标 chat_id
    p = Path(video)
    if p.exists():
        opened_file = p.open("rb")
        video = InputFile(opened_file, filename=p.name)

    bot = Bot(token=bot_token)
    await bot.send_video(
        video=video,
        caption=caption,
        duration=duration,
        width=width,
        height=height,
        chat_id=chat_id,
        supports_streaming=supports_streaming,
        write_timeout=300,
        read_timeout=120,
        **kwargs,
    )

# 运行测试

asyncio.run(send_video(""))
# asyncio.run(get_latest_message())

# asyncio.run(send_custom_emoji())
# 运行测试
# asyncio.run(send_emoji_message())
# asyncio.run(get_latest_message())
