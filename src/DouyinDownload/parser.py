# parser.py
"""
负责从抖音URL解析出视频的详细信息。
Responsible for parsing detailed video information from a Douyin URL.
"""
import json
import re
import time
from typing import Dict, Any, List, Optional, Coroutine

import requests
from bs4 import BeautifulSoup
from playwright.async_api import Page

from DouyinDownload.config import AWEME_DETAIL_API_URL, PLAYWRIGHT_TIMEOUT, IMAGES_NEED_COOKIES, DOWNLOAD_HEADERS
from DouyinDownload.exceptions import URLExtractionError, ParseError
from DouyinDownload.models import VideoOption, ImageOptions
import logging

from PublicMethods.tools import prepared_to_curl
from PublicMethods.playwrigth_manager import PlaywrightManager
from PublicMethods.functool_timeout import retry_on_timeout_async
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
                            """
                            只匹配完整的"["string"]" 或者 "[123]"格式的内容，"[玫瑰]"这种属于表情字符串，不匹配；然后替换加上不带双引号的[],从而达到去除引号的目的
                            不应匹配："[玫瑰]"
                            应匹配："["玫瑰"]"或者 "[123]"
                            "["normal_720_0","normal_720_0"]"
                            """
                            final_text = re.sub(r'"(\[(?:"[^"]+"(?:,"[^"]+")*|\d+)\])"', r'\1', final_text)
                            final_text = final_text.replace('$undefined', 'null')
                            try:
                                target_dict = self._try_parse_json(final_text)
                                return target_dict
                            except Exception as e:
                                log.error(f"格式化JSON错误:{e},处理前json_str:{final_text}")
                                return None
        log.error("未匹配到标签内的目标内容")
        return None

    async def _get_cookies(self, page: Page, cookie_names: List[str]) -> Dict[str, str]:
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
            all_cookies = await page.context.cookies()

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

    async def _intercept_detail_api(self, page: Page, short_url: str, target_api) -> Optional[Dict[str, Any]]:
        """
        核心拦截逻辑：访问页面并捕获包含视频详情的JSON响应。
        Core interception logic: visits the page and captures the JSON response containing video details.
        """
        g_start = time.time()

        try:
            INTERCEPT_RULES = [
                # INTERCEPT_SCRIPT_ALL,
                ("stylesheet", None),
                ("css" , None),
                ("image", None),
                ("png", None),
                ("gif", None),
                ("media", None),
                ("websocket", None),
                ("preflight", None),
                ("front", None),
                ("ping", None),
            ]
            ACCEPT_RULES = [
                ("document", "v.douyin.com"),
                ("document", "www.douyin.com"),
                ("xhr", target_api),
                ("script", "obj/security-secsdk"),
            ]
            async def _route_handler(route):
                # 如果页面已关闭，则跳过 abort
                if page.is_closed():
                    return
                r = route.request
                # start = time.time()
                allow = True
                # 允许放行
                for resource_type, fragment in ACCEPT_RULES:
                    if r.resource_type == resource_type and fragment in r.url:
                        # log.debug(f"命中允许放行  {r.url}")
                        break
                        # await route.continue_()
                        # return
                # 拦截所有 script OR 指定片段的 script
                for rt, _ in INTERCEPT_RULES:
                    if r.resource_type == rt:
                        allow = False
                        break

                if allow:
                    await route.continue_()
                    # log.debug(f"允许放行 {round(time.time() - start, 2)} {r.resource_type} {r.url}")
                else:
                    await route.abort()
                    # log.debug(f"拦截 {round(time.time() - start, 2)} {r.resource_type} {r.url}")
                return

            # 拦截并阻止图片、CSS等无关资源加载，加快速度
            # Intercept and block irrelevant resources like images and CSS to speed up the process
            # await page.route("**/*{stylesheet,css,image,media,ping,front,websocket,preflight}",lambda route: route.abort())
            await page.route("**/*", _route_handler)

            start = time.time()
            # 在导航前启动等待，确保能捕获到随后发出的目标请求
            async with page.expect_response(
                    lambda r: target_api in r.url and r.status == 200,
                    timeout=PLAYWRIGHT_TIMEOUT
            ) as resp_info:
                await page.goto(short_url, wait_until="domcontentloaded", timeout=PLAYWRIGHT_TIMEOUT)
            log.debug(f"_intercept_page.route 捕获目标请求 耗时 {round(time.time() - start, 2)}")

            response = await resp_info.value  # 返回 Response 对象

            try:
                detail_json = await response.json()
                return detail_json
            except Exception as e:
                log.error(f"解析 JSON 失败: {e}")
                raise ParseError("解析 API JSON 失败。")
        finally:
            await page.unroute_all(behavior="ignoreErrors")
            log.debug(f"_intercept_detail_api 核心拦截逻辑 总耗时 {round(time.time() - g_start, 2)}")

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

    @retry_on_timeout_async(10, 3)
    async def fetch_images(self, short_url):
        context = await PlaywrightManager.new_context()
        page = await context.new_page()
        log.debug(f"short url:{short_url}")
        try:
            await page.route("**/*{stylesheet,css,image,media,ping,front,websocket,preflight}", lambda route: route.abort())
            await page.goto(short_url)
            cookies = await self._get_cookies(page, IMAGES_NEED_COOKIES)
            resp = requests.get(short_url, cookies=cookies, headers=DOWNLOAD_HEADERS)
            curl = prepared_to_curl(resp.request)
            log.debug(curl)
            html = resp.text
            html = html.replace('\n', '')
            soup = BeautifulSoup(html, 'html.parser')
            script_tags = soup.find_all('script')
            # 提取 playinfo 与 initial state
            note_detail = r'__pace_f.push'

            aweme_json = self._search_scripts_from_scripts(script_tags, note_detail, f'(awemeId|liveReason)')
            return self._parse_images_options(aweme_json)

        finally:
            await context.close()

    @retry_on_timeout_async(10, 3)
    async def fetch(self, short_url: str, target_api=AWEME_DETAIL_API_URL) -> tuple[str, list[VideoOption]] | None:
        """
        执行解析的主流程。
        Executes the main parsing flow.

        Returns:
            A tuple containing: (video_title, list_of_video_options)
        """
        context = await PlaywrightManager.new_context()
        page = await context.new_page()
        log.debug(f"short url:{short_url}")
        try:
            detail_json = await self._intercept_detail_api(page, short_url, target_api)
            if not detail_json:
                raise ParseError("未能获取到有效的API JSON响应 (Failed to get a valid API JSON response).")

            title_raw = detail_json.get("aweme_detail", {}).get("preview_title", "")
            # 清理文件名中的非法字符
            # Sanitize illegal characters from the filename
            video_title = re.sub(r'[\\/:*?"<>|]', '_', title_raw) or short_url

            video_options = self._parse_video_options(detail_json)
            if not video_options:
                raise ParseError(
                    "从API响应中未能解析出任何可下载的视频链接 (No downloadable links could be parsed).")

            return video_title, video_options
        except Exception as e:
            log.error(e)
        finally:
            await context.close()
