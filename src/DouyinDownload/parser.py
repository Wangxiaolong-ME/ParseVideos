# parser.py
"""
负责从抖音URL解析出视频的详细信息。
Responsible for parsing detailed video information from a Douyin URL.
"""
import json
import re
import time
from typing import Dict, Any, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Page, Response, TimeoutError

from DouyinDownload.config import AWEME_DETAIL_API_URL, PLAYWRIGHT_TIMEOUT, IMAGES_NEED_COOKIES, DOWNLOAD_HEADERS
from DouyinDownload.exceptions import URLExtractionError, ParseError
from DouyinDownload.models import VideoOption, ImageOptions
import logging
from PublicMethods.tools import prepared_to_curl

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

    @staticmethod
    def _try_parse_json(final_text):
        # 创建一个 JSON 解码器实例
        decoder = json.JSONDecoder()

        # 尝试解析 JSON 字符串
        while final_text:
            try:
                # 尝试解析 JSON，找到完整的 JSON 数据
                target_dict, index = decoder.raw_decode(final_text)
                return target_dict
            except json.JSONDecodeError as e:
                # 解析失败，裁剪字符串直到找到一个合法的 JSON
                if 'extra data' in str(e):  # 如果是多余的数据
                    # 截断字符串，直到找到 `}` 为止
                    final_text = final_text[:e.pos].rstrip()  # 只保留有效的部分
                else:
                    # 如果是其他错误，直接返回 None
                    return None

        return None

    def _search_scripts_from_scripts(self, script_tags, target_script_regex, flag):
        """
        target_script_regex: 正则主要匹配script头部，命中即返回其json
        flag: 标志信息1
        """
        for script in script_tags:
            if script.string:  # 如果 <script> 标签有内容
                if re.search(target_script_regex, script.string, re.DOTALL):
                    match = re.search(flag, script.text, re.DOTALL)
                    if match:
                        head = r".*?(?={)"
                        tail = r"](?!.*}).*$"
                        head = re.search(head, script.text, re.DOTALL)
                        tail = re.findall(tail, script.text, re.DOTALL)
                        if head and tail:
                            head = head.group()
                            tail = tail[-1]
                            final_text = script.text.replace(head, '')
                            final_text = final_text.replace(tail, '')
                            final_text = re.sub(r'\\{1,}"', '"', final_text)
                            final_text = re.sub(r'"{', '{', final_text)
                            final_text = re.sub(r'}"', '}', final_text)
                            final_text = final_text.replace('$undefined', 'null')
                            # final_text = final_text.replace(r'\\"', '"')
                            log.debug(f"正则拿到json_str:{final_text}")
                            try:
                                # j = json.loads(final_text)
                                target_dict = self._try_parse_json(final_text)
                                return target_dict
                            except Exception as e:
                                log.error(f"格式化JSON错误:{e}")
                                return None
        log.error("未匹配到标签内的目标内容")
        return None

    def _get_cookies(self, page: Page, cookie_names: List[str]) -> Dict[str, str]:
        """
        从 Playwright Page 对象中提取指定名称的 Cookie。

        Args:
            page: playwright.sync_api.Page 实例，已加载目标页面。
            cookie_names: 一个字符串列表，包含你想要获取的 Cookie 名称。

        Returns:
            一个字典，键为 Cookie 名称，值为 Cookie 值。
            如果 Cookie 不存在，则不会包含在该字典中。
        """
        extracted_cookies: Dict[str, str] = {}
        try:
            # 获取当前浏览器上下文中的所有 Cookie
            # 注意：context.cookies() 获取的是当前上下文所有域的 Cookie
            # 如果需要特定域的，可能需要进一步过滤 domain
            all_cookies = page.context.cookies()

            for cookie_obj in all_cookies:
                cookie_name = cookie_obj.get("name")
                cookie_value = cookie_obj.get("value")

                if cookie_name and cookie_name in cookie_names:
                    extracted_cookies[cookie_name] = cookie_value
                    log.debug(f"已获取 Cookie: {cookie_name}={cookie_value}")

            if not extracted_cookies:
                log.warning(f"未能获取到任何指定名称的 Cookie: {cookie_names}")

            return extracted_cookies
        except Exception as e:
            log.error(f"获取指定 Cookie 时发生错误: {e}", exc_info=True)
            return {}

    def _intercept_detail_api(self, page: Page, short_url: str, target_api) -> Optional[Dict[str, Any]]:
        """
        核心拦截逻辑：访问页面并捕获包含视频详情的JSON响应。
        Core interception logic: visits the page and captures the JSON response containing video details.
        """

        detail_response_json: Optional[Dict[str, Any]] = None
        g_start = time.time()

        def handle_response(response: Response):
            nonlocal detail_response_json
            if target_api in response.url and response.ok:
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
                    timeout=PLAYWRIGHT_TIMEOUT,  # 给一个短点的超时
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

    def _parse_images_options(self, detail_json: Dict[str, Any]) -> ImageOptions:
        aweme_detail = detail_json.get("aweme", {}).get("detail", {})
        if not aweme_detail:
            raise ParseError("API响应中缺少 'aweme_detail' 关键字段 (Missing 'aweme_detail' key in API response).")

        aweme_id = aweme_detail.get("awemeId")
        desc = aweme_detail.get("desc")
        create_time = aweme_detail.get("createTime")
        author_info = aweme_detail.get("authorInfo")
        images = aweme_detail.get("images")

        """
                images 结构示例,-1是效果最好的jpg
                "images": [
                            {
                                 "width": 1056,
                                 "height": 1920,
                                 "uri": "tos-cn-i-0813/b4e8b236b5904f95810cb6691c4e8cc9",
                                 "urlList": [
                                      "https://p3-pc-sign.douyinpic.com/tos-cn-i-0813/b4e8b236b5xx",
                                      "https://p9-pc-sign.douyinpic.com/tos-cn-i-0813/b4e8b236b5xx",
                                      "https://p3-pc-sign.douyinpic.com/tos-cn-i-0813/b4e8b236bxx"
                                 ],
                                 "downloadUrlList": [
                                      "https://p3-pc-sign.douyinpic.com/tos-cn-i-0813/b4e8b236bxx",
                                      "https://p9-pc-sign.douyinpic.com/tos-cn-i-0813/b4e8b236xx",
                                      "https://p3-pc-sign.douyinpic.com/tos-cn-i-0813/b4e8b236xx"
                                 ],
                                 "video": null,
                                 "clipType": "null",
                                 "livePhotoType": "null"
                            }
                """

        return ImageOptions(
            aweme_id=aweme_id,
            desc=desc,
            create_time=create_time,
            author_info=author_info,
            images=images
        )

    def fetch_images(self, short_url):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--disable-images'])
            page = browser.new_page()
            try:
                page.route("**/*.{png,jpg,jpeg,svg,css,woff,woff2,ttf}", lambda route: route.abort())
                page.goto(short_url)
                cookies = self._get_cookies(page, IMAGES_NEED_COOKIES)
                resp = requests.get(short_url, cookies=cookies, headers=DOWNLOAD_HEADERS)
                curl = prepared_to_curl(resp.request)
                print(curl)
                html = resp.text
                html = html.replace('\n', '')
                soup = BeautifulSoup(html, 'html.parser')
                script_tags = soup.find_all('script')
                # 提取 playinfo 与 initial state
                note_detail = r'__pace_f.push'

                aweme_json = self._search_scripts_from_scripts(script_tags, note_detail, f'(awemeId|liveReason)')
                print(aweme_json)
                return self._parse_images_options(aweme_json)

            finally:
                browser.close()

    def fetch(self, short_url: str, target_api=AWEME_DETAIL_API_URL) -> Tuple[str, List[VideoOption]]:
        """
        执行解析的主流程。
        Executes the main parsing flow.

        Returns:
            A tuple containing: (video_title, list_of_video_options)
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--disable-images'])
            page = browser.new_page()
            log.debug(f"short url:{short_url}")
            try:
                detail_json = self._intercept_detail_api(page, short_url, target_api)
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
