# src/TelegramBot/uploader.py
import asyncio
import shlex
import subprocess
import time

import aiohttp
import httpx, pathlib, logging
from telegram.constants import ParseMode

from TelegramBot.utils import MsgSender

logger = logging.getLogger(__name__)

CATBOX_URL = "https://catbox.moe/user/api.php"


class ProgressFile:
    """文件包装器：每次 read 后异步更新进度消息"""

    def __init__(self, path: pathlib.Path, progress_msg, chunk: int = 1 << 20):
        self._f = path.open("rb")
        self.size = path.stat().st_size
        self.sent = 0
        self.last = time.perf_counter()
        self.chunk = chunk
        self._msg = progress_msg  # telegram.Message

    def _maybe_update(self):
        now = time.perf_counter()
        if now - self.last >= 1 or self.sent == self.size:  # ≥1 s 或已完
            pct = self.sent / self.size * 100
            # 计算进度条中的 '==' 数量，每 10% 增加 2 个 '='
            num_equals = int(pct // 10) * 2
            bar = '==' * num_equals

            # -1让最终100%为 99%
            pct -= 1
            # 实时更新进度信息，进度条长度和 '=' 数量变化
            asyncio.get_running_loop().create_task(
                self._msg.edit_text(f"上传中 {bar} {pct:5.1f} %")
            )
            self.last = now

    def read(self, n: int = -1):
        data = self._f.read(n if n > 0 else self.chunk)
        if data:
            self.sent += len(data)
            logger.info("Catbox %5.1f%% (%s / %s)",
                        self.sent / self.size * 100,
                        _fmt(self.sent), _fmt(self.size))
            self._maybe_update()
        return data or b""  # httpx 7.x 需要即便 EOF 也返回 b""

    def close(self):
        self._f.close()


def _fmt(b: int, unit: str = "MB") -> str:
    """把字节数转成指定单位，默认 MB。unit 可选 B/KB/MB/GB"""
    factor = {
        "B": 1,
        "KB": 1024,
        "MB": 1024 ** 2,
        "GB": 1024 ** 3,
    }[unit.upper()]
    return f"{b / factor:.1f} {unit.upper()}"


async def upload(path: pathlib.Path, sender: MsgSender | None = None):
    """
    上传至 Catbox，实时在同一条消息里刷新进度。
    返回直链 URL。
    """
    # 配置代理地址（假设代理为 HTTP 协议）
    proxy_url = "http://127.0.0.1:7890"
    prams = {}
    # if PROXY_SWITCH:
    #     prams["proxy"] = proxy_url
    #     logger.debug(f"当前系统为Windows，已开启代理")

    start = time.perf_counter()

    # ① 先发占位消息并显示上传状态
    progress_msg = await sender.send("上传中 0 %")

    pf = ProgressFile(path, progress_msg)  # ← 传入消息实例
    data = {"reqtype": "fileupload"}
    files = {"fileToUpload": (path.name, pf, "application/octet-stream")}

    async with httpx.AsyncClient(timeout=None, http2=False) as cli:
        r = await cli.post(CATBOX_URL, data=data, files=files)
    r.raise_for_status()
    pf.close()

    url = r.text.strip()
    await progress_msg.delete()  # 最终 100 %

    logger.info("Catbox 上传完成 → %s (耗时 %.1f s)", url, time.perf_counter() - start)
    return url
