# playwright_manager.py
import atexit
import uuid
from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext
import logging
import asyncio

log = logging.getLogger(__name__)


class PlaywrightManager:
    _playwright: Playwright | None = None
    _browser: Browser | None = None
    _browser_id: str | None = None  # 新增：全局唯一标识

    @classmethod
    async def init(cls) -> tuple[Playwright, Browser]:
        """
        初始化 Playwright 和 Browser（只在第一次调用时真正启动）
        """
        if cls._playwright is None:
            cls._playwright = await async_playwright().start()
            cls._browser = await cls._playwright.chromium.launch(
                headless=True,
                args=['--disable-images']  # 保留原注释：禁用图片
            )
            # 第一次启动时生成唯一 ID
            cls._browser_id = str(uuid.uuid4())
            log.info(f"[PlaywrightManager] 浏览器首次启动，Browser ID={cls._browser_id}")
        else:
            log.debug(f"[PlaywrightManager] 已复用浏览器，Browser ID={cls._browser_id}")
        return cls._playwright, cls._browser  # type: ignore

    @classmethod
    async def get_browser(cls) -> Browser:
        """
        获取全局浏览器实例，并打印当前 Browser ID
        """
        if cls._browser is None:
            # 还未 init，则先初始化
            await cls.init()
        # 每次取用时都 log 一下 ID，方便排查是否复用
        log.debug(f"[PlaywrightManager] get_browser 调用，当前 Browser ID={cls._browser_id}")
        return cls._browser  # type: ignore

    @classmethod
    async def new_context(cls) -> BrowserContext:
        """
        为每次业务请求创建隔离的 Context
        """
        browser = await cls.get_browser()
        return await browser.new_context()

    @classmethod
    async def close(cls):
        """关闭浏览器和 playwright"""
        try:
            if cls._browser:
                log.info(f"[PlaywrightManager] 关闭浏览器，Browser ID={cls._browser_id}")
                await cls._browser.close()
                cls._browser = None
                cls._browser_id = None
            if cls._playwright:
                await cls._playwright.stop()
                cls._playwright = None
        except RuntimeError as e:
            # 捕捉事件循环关闭后的异常，防止程序崩溃
            log.error(f"关闭 Playwright 时出错: {e}")


# 注册进程退出时的清理钩子，保证整个程序结束前关闭浏览器
def _shutdown():
    loop = asyncio.get_event_loop()
    if loop.is_running():
        # 如果已经在事件循环里（如 uvicorn），则新起一个任务
        asyncio.ensure_future(PlaywrightManager.close())
    else:
        loop.run_until_complete(PlaywrightManager.close())


atexit.register(_shutdown)
