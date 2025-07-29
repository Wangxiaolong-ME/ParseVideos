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
    _fingerprint: dict | None = None  # ← 一定要有

    @classmethod
    def set_default_fingerprint(cls) -> None:
        """
        载入“真实浏览器”指纹。
        调一次即可；后面 new_context() 会自动引用。
        """
        cls._fingerprint = {
            # —— 基础 ——
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/138.0.0.0 Safari/537.36",
            "locale": "zh-CN",
            "timezone_id": "Asia/Hong_Kong",

            # —— 请求头 ——
            "extra_http_headers": {
                "Accept-Language": "zh-CN",
                # 如有 Cookie 就写这儿或用 cookies 字段
            },

            # —— 屏幕 ——
            "viewport": {"width": 1920, "height": 1080},

            # —— WebGL ——
            "webgl_vendor": "Google Inc. (NVIDIA)",
            "webgl_renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 Ti (0x00002782) Direct3D11 vs_5_0 ps_5_0, D3D11)",

            # —— 额外可选 ——
            "hardware_concurrency": 20,
            "device_memory": 8,
            "plugins": [
                "PDF Viewer", "Chrome PDF Viewer",
                "Chromium PDF Viewer", "Microsoft Edge PDF Viewer",
                "WebKit built-in PDF",
            ],
        }
        log.info("[PlaywrightManager] 已载入默认指纹配置")

    @classmethod
    async def init(cls, headless=True, simple_args=True) -> tuple[Playwright, Browser]:
        """
        初始化 Playwright 和 Browser（只在第一次调用时真正启动）
        """
        if cls._playwright is None:
            cls._playwright = await async_playwright().start()
            if simple_args:
                cls._browser = await cls._playwright.chromium.launch(
                    headless=headless,
                    args=['--disable-images'],  # 保留原注释：禁用图片
                    # args=[
                    #     '--disable-blink-features=AutomationControlled',  # 去掉AutomationControlled标识
                    #     "--disable-features=IsolateOrigins,site-per-process"]  # ③ 常见跨站检测绕过
                )
            else:
                cls._browser = await cls._playwright.chromium.launch(
                    headless=headless,
                    # args=['--disable-images'],  # 保留原注释：禁用图片
                    args=[
                        '--disable-blink-features=AutomationControlled',  # 去掉AutomationControlled标识
                        "--disable-features=IsolateOrigins,site-per-process"]  # ③ 常见跨站检测绕过
                )
            # 第一次启动时生成唯一 ID
            cls._browser_id = str(uuid.uuid4())
            log.info(f"[PlaywrightManager] 浏览器首次启动，Browser ID={cls._browser_id}")
        else:
            log.debug(f"[PlaywrightManager] 已复用浏览器，Browser ID={cls._browser_id}")
        return cls._playwright, cls._browser  # type: ignore

    @classmethod
    async def get_browser(cls, headless=True, simple_args=True) -> Browser:
        """
        获取全局浏览器实例，并打印当前 Browser ID
        """
        # 避免下次取到“尸体” Browse
        if cls._browser is None:
            # 还未 init，则先初始化
            await cls.init(headless, simple_args)
        # 每次取用时都 log 一下 ID，方便排查是否复用
        log.debug(f"[PlaywrightManager] get_browser 调用，当前 Browser ID={cls._browser_id}")
        return cls._browser  # type: ignore

    @classmethod
    async def new_context(cls, headless=True, proxy_config=None, simple_args=True) -> BrowserContext:
        """
        为每次业务请求创建隔离的 Context
        """
        browser = await cls.get_browser(headless, simple_args)
        return await browser.new_context(proxy=proxy_config)

    @classmethod
    async def new_cookie_context(
            cls,
            headless: bool = True,
            proxy_config: dict | None = None,
            with_fingerprint: bool = True,
    ) -> BrowserContext:

        browser = await cls.get_browser(headless, simple_args=False)
        ctx_kwargs: dict = {"proxy": proxy_config} if proxy_config else {}

        if with_fingerprint and cls._fingerprint:
            fp = cls._fingerprint
            ctx_kwargs.update(
                user_agent=fp["user_agent"],
                locale=fp["locale"],
                timezone_id=fp["timezone_id"],
                extra_http_headers=fp["extra_http_headers"],
                viewport=fp["viewport"],
            )

        # ★ 创建前再次打印，确保真正写进了 ctx_kwargs
        log.debug(
            "[PlaywrightManager] 即将创建 Context, 指纹片段: %s",
            {k: ctx_kwargs.get(k) for k in ("user_agent", "locale", "timezone_id", "viewport")}
        )

        ctx = await browser.new_context(**ctx_kwargs)
        return ctx

    @classmethod
    async def close(cls):
        """安全关闭 Browser 与 Playwright，允许多次调用且不抛异常"""
        try:
            # 1️⃣ 先停 Playwright（它会顺带关掉所有 Browser）
            if cls._playwright is not None:
                await cls._playwright.stop()
                cls._playwright = None

            # 2️⃣ 如果仍然持有 Browser 对象，且还连着，再手动关一次
            if cls._browser is not None:
                try:
                    if getattr(cls._browser, "is_connected", lambda: False)():
                        await cls._browser.close()
                except AttributeError:
                    # impl 已失效，无需再次关闭
                    log.debug("[PlaywrightManager] Browser 已被自动关闭，跳过显式 close()")
                cls._browser = None
                cls._browser_id = None

        except Exception as e:
            # 捕获所有异常，防止退出流程中断
            log.warning(f"[PlaywrightManager] 关闭时出现非致命异常: {e!r}")


# 注册进程退出时的清理钩子，保证整个程序结束前关闭浏览器
def _shutdown():
    """
    atexit 钩子：在解释器退出前确保异步资源被清理
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    async def _safe_close():
        try:
            await PlaywrightManager.close()
        except Exception as e:
            # 最终兜底，绝不让异常向外冒
            log.debug(f"[PlaywrightManager] _shutdown 忽略异常: {e!r}")

    if loop.is_closed():
        # 已经没有事件循环 → 同步跑完
        asyncio.run(_safe_close())
    elif loop.is_running():
        # 事件循环还在跑 → 排队到事件循环里
        asyncio.ensure_future(_safe_close())
    else:
        loop.run_until_complete(_safe_close())


atexit.register(_shutdown)
