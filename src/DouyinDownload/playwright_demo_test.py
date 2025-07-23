import re
import time
from typing import Dict, Any, Optional
from playwright.sync_api import sync_playwright, Page, Response, TimeoutError
from PublicMethods.logger import get_logger, setup_log

setup_log()
log = get_logger(__name__)

AWEME_DETAIL_API_URL = "/aweme/v1/web/aweme/detail/"
PLAYWRIGHT_TIMEOUT = 60000  # 60秒

def intercept_detail_api(page: Page, short_url: str) -> Optional[Dict[str, Any]]:
    detail_response_json: Optional[Dict[str, Any]] = None
    g_start = time.time()

    def handle_response(response: Response):
        nonlocal detail_response_json
        if AWEME_DETAIL_API_URL in response.url and response.ok:
            try:
                detail_response_json = response.json()
                log.info("成功拦截到目标 API 响应")
            except Exception:
                pass

    # 拦截无关资源
    page.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2,ttf,webm,ogg,m3u8,ts,flv,mov,m4v,avi}", lambda route: route.abort())
    log.debug("已设置资源拦截规则")

    # 设置响应监听
    page.on("response", handle_response)


    try:
        log.info(f"开始导航至: {short_url}")
        start = time.time()
        page.goto(short_url, wait_until="domcontentloaded", timeout=PLAYWRIGHT_TIMEOUT)
        log.info(f"导航完成，耗时: {time.time() - start:.2f}s")

        # 等待目标响应
        wait_start = time.time()
        page.wait_for_event(
            "response",
            timeout=PLAYWRIGHT_TIMEOUT / 2,
            predicate=lambda r: AWEME_DETAIL_API_URL in r.url and r.status == 200
        )
        log.info(f"目标 API 响应捕获，等待耗时: {time.time() - wait_start:.2f}s")
    except TimeoutError:
        log.error("超时未捕获到目标 API 响应")
        return None
    finally:
        page.remove_listener("response", handle_response)
        log.info(f"总耗时: {time.time() - g_start:.2f}s")

    return detail_response_json

def main():
    short_url = "https://v.douyin.com/EBe_OwR8Lnk/"  # 测试用短链接
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--disable-images'])
        page = browser.new_page()
        try:
            result = intercept_detail_api(page, short_url)
            if result:
                log.info(f"解析结果: {result.get('aweme_detail', {}).get('preview_title', '无标题')}")
                log.info(f"{result.get('aweme_detail', {}).get('video', '无标题')}")
            else:
                log.warning("未获取到有效结果")
        finally:
            browser.close()

if __name__ == "__main__":
    main()