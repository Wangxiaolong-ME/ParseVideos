# parser.py
"""
负责从抖音URL解析出视频的详细信息。
Responsible for parsing detailed video information from a Douyin URL.
"""
import re
import time
from typing import Dict, Any, List, Optional, Tuple

from playwright.sync_api import sync_playwright, Page, Response, TimeoutError

from DouyinDownload.config import AWEME_DETAIL_API_URL, PLAYWRIGHT_TIMEOUT
from DouyinDownload.exceptions import URLExtractionError, ParseError
from DouyinDownload.models import VideoOption
import  logging
log = logging.getLogger(__name__)

class DouyinParser:
    """
    使用 Playwright 模拟浏览器行为，拦截API请求来获取抖音无水印视频数据。
    Uses Playwright to simulate browser behavior and intercept API requests to get Douyin watermark-free video data.
    """

    @staticmethod
    def extract_short_url(text: str) -> str:
        """
        从输入文本中正则匹配出抖音短链接。
        Extracts a Douyin short URL from the input text using regex.
        """
        match = re.search(r'https?://v\.douyin\.com/[-\w/]+', text)
        if not match:
            raise URLExtractionError(f'未从输入中识别到有效的抖音短链URL: "{text}"')
        return match.group(0)

    def _intercept_detail_api(self, page: Page, short_url: str) -> Optional[Dict[str, Any]]:
        """
        核心拦截逻辑：访问页面并捕获包含视频详情的JSON响应。
        Core interception logic: visits the page and captures the JSON response containing video details.
        """
        detail_response_json: Optional[Dict[str, Any]] = None
        g_start = time.time()

        def handle_response(response: Response):
            nonlocal detail_response_json
            if AWEME_DETAIL_API_URL in response.url and response.ok:
                try:
                    detail_response_json = response.json()
                except Exception:
                    # 避免JSON解析失败导致程序崩溃
                    pass

        # 拦截并阻止图片、CSS等无关资源加载，加快速度
        # Intercept and block irrelevant resources like images and CSS to speed up the process
        page.route("**/*.{png,jpg,jpeg,svg,css,woff,woff2,ttf}", lambda route: route.abort())
        start = time.time()
        log.debug(f"_intercept_detail_api 核心拦截逻辑 page.on.response 1")
        page.on("response", handle_response)
        log.debug(f"_intercept_detail_api 核心拦截逻辑 page.on.response 2 {(time.time() - start):.2f}")

        try:
            start = time.time()
            log.debug(f"_intercept_detail_api 核心拦截逻辑 page.goto domcontentloaded 1")
            page.goto(short_url, wait_until="domcontentloaded", timeout=PLAYWRIGHT_TIMEOUT)
            log.debug(f"_intercept_detail_api 核心拦截逻辑 page.goto domcontentloaded 2 {(time.time() - start):.2f}")
            # 等待目标API响应，确保数据被捕获
            start = time.time()
            log.debug(f"_intercept_detail_api 核心拦截逻辑 page.wait_for_event 1")
            page.wait_for_event(
                "response",
                timeout=PLAYWRIGHT_TIMEOUT / 2,
                predicate=lambda r: AWEME_DETAIL_API_URL in r.url and r.status == 200
            )
            log.debug(f"_intercept_detail_api 核心拦截逻辑 page.wait_for_event 2 {(time.time() - start):.2f}")
        except TimeoutError:
            # 如果上面的wait_for_function不可靠，可以回退到等待response事件
            try:
                page.wait_for_event(
                    "response",
                    timeout=PLAYWRIGHT_TIMEOUT / 2,  # 给一个短点的超时
                    predicate=lambda r: AWEME_DETAIL_API_URL in r.url and r.status == 200
                )
            except TimeoutError:
                raise ParseError(f"在 {PLAYWRIGHT_TIMEOUT}ms 内未能拦截到作品详情API请求，请检查网络或链接是否有效。")
        finally:
            # 移除事件监听器
            try:
                log.debug("移除响应事件监听器")
                page.remove_listener("response", handle_response)
                log.debug(f"_intercept_detail_api 核心拦截逻辑 总耗时 {round(time.time() - g_start, 2)}")
            except KeyError as e:
                log.error(f"移除监听器时发生错误: {e}")

        return detail_response_json

    def _parse_video_options(self, detail_json: Dict[str, Any]) -> List[VideoOption]:
        """
        从API的JSON数据中解析出所有可用的视频下载选项。
        Parses all available video download options from the API JSON data.
        """
        aweme_detail = detail_json.get("aweme_detail", {})
        if not aweme_detail:
            raise ParseError("API响应中缺少 'aweme_detail' 关键字段 (Missing 'aweme_detail' key in API response).")

        aweme_id = aweme_detail.get("aweme_id")
        bit_rate_list = aweme_detail.get("video", {}).get("bit_rate", [])
        log.debug(f"DouYin_aweme_detail 视频流: {bit_rate_list}")
        # log.debug(f"DouYin_aweme_detail 原始数据: {aweme_detail}")
        duration = aweme_detail.get("duration")

        # 过滤掉DASH格式，它需要特定的播放器，不适合直接下载合并
        # Filter out DASH format, which requires a specific player and is not suitable for direct download and merge
        options = []
        for item in bit_rate_list:
            if item.get("format") == "dash" or not item.get("play_addr", {}).get("url_list"):
                continue

            gear_name = item.get("gear_name", "")
            res_match = re.search(r'(\d+)', gear_name)
            resolution = int(res_match.group(1)) if res_match else 0

            # 抖音的 '4' 分辨率标识通常代表4K
            # Douyin's '4' resolution identifier usually represents 4K
            if resolution == 4:
                resolution = 2160

            # 优先选择官方播放接口URL
            # Prioritize the official play API URL
            urls = item.get("play_addr", {}).get("url_list", [])
            chosen_url = next((u for u in urls if "aweme/v1/play" in u), urls[0])

            raw_bytes = item.get("play_addr", {}).get("data_size")
            size_mb = round(raw_bytes / (1024 * 1024), 2) if isinstance(raw_bytes, (int, float)) else None
            options.append(
                VideoOption(
                    aweme_id=aweme_id,
                    resolution=resolution,
                    bit_rate=item.get("bit_rate", 0),
                    url=chosen_url,
                    size_mb=size_mb,
                    gear_name=gear_name,
                    quality=item.get("quality_type", ""),
                    height=item.get("play_addr").get("height", 720),
                    width=item.get("play_addr").get("width", 1280),
                    duration=duration,
                )
            )

        return options

    def fetch(self, short_url: str) -> Tuple[str, List[VideoOption]]:
        """
        执行解析的主流程。
        Executes the main parsing flow.

        Returns:
            A tuple containing: (video_title, list_of_video_options)
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True,args=['--disable-images'])
            page = browser.new_page()
            try:
                detail_json = self._intercept_detail_api(page, short_url)
                if not detail_json:
                    raise ParseError("未能获取到有效的API JSON响应 (Failed to get a valid API JSON response).")

                title_raw = detail_json.get("aweme_detail", {}).get("preview_title", "")
                # 清理文件名中的非法字符
                # Sanitize illegal characters from the filename
                video_title = re.sub(r'[\\/:*?"<>|]', '_',
                                     title_raw) or short_url

                video_options = self._parse_video_options(detail_json)
                if not video_options:
                    raise ParseError(
                        "从API响应中未能解析出任何可下载的视频链接 (No downloadable links could be parsed).")

                return video_title, video_options
            finally:
                browser.close()
