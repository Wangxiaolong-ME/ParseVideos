# tiktok_parser.py
import re
import time
from typing import Dict, Any, List, Optional
import logging

import httpx

from PublicMethods.playwrigth_manager import PlaywrightManager
from TikTokDownload.scraper import TikTokScraper
from TikTokDownload.config import IMAGE_DETAIL_API_URL, TIKTOK_USER_AGENT
from TikTokDownload.models import TikTokPost, TikTokVideoOption, TikTokMusicOption, TikTokImage
from PublicMethods.tools import collect_values, prepared_to_curl

log = logging.getLogger(__name__)


# 定义自定义异常
class TikTokParseError(Exception):
    """TikTok 数据解析错误"""
    pass


class TikTokURLParsingError(Exception):
    """TikTok URL 提取错误"""
    pass


# tiktok_parser.py (续写部分)
# ... (之前的导入和异常定义)

class TikTokParser:
    """
    负责将从 TikTok 网页或 API 获取的原始 JSON 数据转换为结构化的数据模型。
    这是一个纯粹的数据处理层，不涉及网络请求。
    """

    def __init__(self):
        self.scraper = TikTokScraper(user_agent=TIKTOK_USER_AGENT)
        pass

    def extract_valid_url(self, text) -> str:
        short_url = self.extract_short_url(text)
        long_url = self.extract_long_url(text)
        valid_url = long_url or short_url
        if not valid_url:
            raise TikTokURLParsingError(f'未从输入中识别到有效的 TikTok URL: "{text}"')
        return valid_url

    @staticmethod
    def extract_short_url(text: str) -> str:
        """
        从输入文本中正则匹配出 TikTok 短链接。
        """
        match = re.search(r'https?://(?:vm|vt)\.tiktok\.com/[-\w/]+', text)
        if not match:
            log.warning(f'未从输入中识别到有效的 TikTok 短链URL: "{text}"')
            return ''
        log.debug(f"extract_short_url:{match.group(0)}")
        return match.group(0)

    @staticmethod
    def extract_long_url(text: str) -> str:
        """
        从输入文本中正则匹配出 TikTok 长链接。
        """
        match = re.search(r'https?://www\.tiktok\.com/[\S]+', text)
        if not match:
            log.warning(f'未从输入中识别到有效的 TikTok 长链URL: "{text}"')
            return ''
        log.debug(f"extract_long_url:{match.group(0)}")
        return match.group(0)

    @staticmethod
    def get_final_url(short_url: str) -> httpx.Response.url:
        try:
            http = httpx.Client(headers={"User-Agent": TIKTOK_USER_AGENT}, follow_redirects=True, timeout=30)
            r = http.get(short_url)
            log.debug(f"通过 HEAD 请求重定向判断指向: {r.url}")
            return r.url
        except Exception as e:
            # 捕获其他未知异常
            log.error(f"请求失败或发生错误: {e}")
            return None

    def get_content_type(self, short_url: str) -> str:
        """
        通过 HEAD 请求重定向地址判断给定短链接指向的内容类型 (video 或 image_album)。
        Returns: "video", "image_album", or "unknown"
        """
        try:
            url = self.get_final_url(short_url)  # type:httpx.URL
            path = url.path
            if "/video/" in path:
                log.debug(f"指向内容为视频")
                return "video"
            elif "/photo/" in path:
                log.debug(f"指向内容为图集")
                return "image"
            else:
                log.debug(f"指向内容未知")
                return "unknown"

        except Exception as e:
            # 捕获其他未知异常
            log.error(f"请求失败或发生错误: {e}")
            return "unknown"

    async def fetch_video(self, url) -> TikTokPost | None:
        # 首先尝试从网页内容中解析
        html_content = self.scraper.fetch_page_content(url)
        if html_content:
            universal_data = self.scraper.extract_universal_data(html_content)
            if universal_data:
                try:
                    tiktok_post_data = self.parse_universal_data_to_tiktok_post(universal_data)
                    log.info(f"成功解析作品: {tiktok_post_data.title}")
                    return tiktok_post_data
                except Exception as e:
                    log.error(f"从通用数据解析失败: {e}")
            else:
                log.error("未能从网页内容中提取到 __UNIVERSAL_DATA_FOR_REHYDRATION__ 数据")
        else:
            log.error("未能获取到网页内容")

    async def fetch_images(self, url) -> TikTokPost | None:
        try:
            tiktok_post_data = await self.parse_images_data_by_playwright(url)
            log.info(f"成功解析图集作品: {tiktok_post_data.title}")
            return tiktok_post_data
        except TikTokParseError as e:
            log.error(f"图集解析失败: {e}")
        return None

    def _parse_music_data(self, music_data: Dict[str, Any]) -> Optional[TikTokMusicOption]:
        """
        解析音乐信息，返回 TikTokMusicOption
        只取 urlList 中的第一个链接；若字段不存在则给空串 / 默认值。
        """
        if not music_data:
            return None

        # -------- 处理 playUrl --------
        play_url = music_data.get("playUrl", "")

        # -------- 处理 coverLarge --------
        cover_url = music_data.get("coverLarge", "")

        # -------- 构造返回对象 --------
        return TikTokMusicOption(
            id=str(music_data.get("id", "")),
            title=music_data.get("title", "未知音乐"),
            author_name=music_data.get("authorName", "未知作者"),
            url=play_url,
            cover_url=cover_url,
            duration=music_data.get("duration", 0)
        )

    def _parse_image_data(self, image_post: Dict) -> List[TikTokImage]:
        """
        根据 TikTok 图集数据结构
        imagePost.images.[].imageURL.urlList[0]
        解析出 TikTokImage 列表。
        """
        images: List[TikTokImage] = []
        raw_images = collect_values(image_post, "images")
        title = image_post.get('title')
        for img_item in raw_images:
            if video := collect_values(img_item, 'video'):
                self._parse_video_datas(video)
            # -------- 逐层拿到 urlList --------
            image_url = img_item.get("imageURL", {})  # cover.imageURL
            url_list = image_url.get("urlList", []) or []  # imageURL.urlList

            # -------- 其余字段：能拿到就拿，拿不到给默认 --------
            uri = url_list[0]

            images.append(
                TikTokImage(
                    url=uri,
                    url_list=url_list,
                    title=title,
                )
            )

        return images

    def _parse_video_datas(self, video_data: Dict[str, Any]) -> list[TikTokVideoOption] | None:
        """
        从原始视频数据中解析出所有可用的 TikTokVideoOption 列表。
        使用 collect_values 简化部分数据提取。
        """

        aweme_id = video_data.get("id")
        duration = video_data.get("duration", 0)  # 视频总时长
        bit_rate_list = video_data.get("bitrateInfo")

        video_files: List[TikTokVideoOption] = []
        for item in bit_rate_list:

            # 使用 collect_values 提取 url_list
            urls = collect_values(item, "UrlList")
            if not urls:  # collect_values 返回 None 或空列表
                continue
            if not isinstance(urls, list):  # collect_values 可能返回单值，确保是列表
                urls = [urls]

            # 优先选择无水印URL，TikTok可能通过特定参数或子域名提供
            chosen_url = next((u for u in urls if "aweme/v1/play" in u), urls[0])
            if not chosen_url:
                log.warning(f"视频流 {item.get('gear_name')} 无可用播放URL.")
                continue

            # 使用 collect_values 提取 height 和 width
            gear_name = item.get("GearName", "")
            bitrate = item.get("Bitrate", 0)
            height = collect_values(item, "Height") or 0
            width = collect_values(item, "Width") or 0
            raw_bytes = int(collect_values(item, "DataSize"))
            size_mb = round(raw_bytes / (1024 * 1024), 2) if isinstance(raw_bytes, (int, float)) else None

            resolution = 0
            res_match = re.search(r'(540|720|1080|1440|2160|(?<=_)4(?=_))', gear_name)
            if res_match:
                resolution = int(res_match.group(1) or res_match.group(2))
            elif height:  # 兜底使用 height
                resolution = height

            r = TikTokVideoOption(
                aweme_id=aweme_id,
                resolution=resolution,
                bit_rate=bitrate,
                url=chosen_url,
                size_mb=size_mb,
                gear_name=gear_name,
                quality=item.get("QualityType", ""),
                height=height,
                width=width,
                duration=duration
            )
            log.debug(f"解析视频流数据: {r.to_dict()}")
            video_files.append(r)
        return video_files

    def parse_universal_data_to_tiktok_post(self, universal_data: Dict[str, Any]) -> TikTokPost:
        """
        从 __UNIVERSAL_DATA_FOR_REHYDRATION__ 中提取并解析为 TikTokPost 对象。
        使用 collect_values 简化深层数据提取。
        """
        # 对于固定的深层路径，collect_values 也能用，但直接 .get().get() 链式调用也同样清晰。
        # 真正优势体现在 target_key 可能出现在不同父级路径下，或者需要扁平化收集多个值时。
        # 这里主要将视频封面图的提取进行优化。
        item_struct = collect_values(universal_data, 'itemStruct')

        if not item_struct:
            log.error("在 __UNIVERSAL_DATA_FOR_REHYDRATION__ 中未找到 itemStruct。")
            raise TikTokParseError("未能从通用数据中解析出作品详情。")

        aweme_id = item_struct.get("id")
        desc = item_struct.get("desc", "")
        create_time = item_struct.get("createTime", 0)  # Unix timestamp
        author_info = item_struct.get("author", {})
        author_id = author_info.get("id")
        author_nickname = author_info.get("nickname")
        statistics_data = item_struct.get("stats", {})
        challenges_data = item_struct.get("challenges", [])  # 话题/标签

        video_data = item_struct.get("video", {})
        image_data = item_struct.get("imagePost", {})  # 图集数据
        music_data = item_struct.get("music", {})  # 音乐数据

        video_options = []
        if video_data and video_data.get("bitrateInfo"):
            video_options = self._parse_video_datas(video_data)

        is_video = bool(video_options)

        images = []
        is_image_album = False
        if image_data:
            images = self._parse_image_data(image_data)
            is_image_album = bool(images)

        music = self._parse_music_data(music_data)

        hashtags = [c.get("title") for c in challenges_data if challenges_data]

        # 使用 collect_values 提取封面图片 URL
        cover_urls = collect_values(item_struct, "url_list", "video.cover")
        cover_image_url = cover_urls[0] if isinstance(cover_urls, list) and cover_urls else None

        return TikTokPost(
            aweme_id=aweme_id,
            title=desc,
            description=desc,
            create_time=create_time,
            author_id=author_id,
            author_nickname=author_nickname,
            video=video_options,
            images=images,
            music=music,
            is_video=is_video,
            is_image_album=is_image_album,
            view_count=statistics_data.get("playCount"),
            like_count=statistics_data.get("diggCount"),
            comment_count=statistics_data.get("commentCount"),
            share_count=statistics_data.get("shareCount"),
            hashtags=hashtags,
            cover_image_url=cover_image_url
        )

    async def parse_images_data_by_playwright(self, short_url: str) -> TikTokPost:
        """
        解析图集作品：
        1. 通过 Playwright 获取页面 HTML
        2. 提取 __UNIVERSAL_DATA_FOR_REHYDRATION__
        3. 复用通用解析，返回 TikTokPost
        """
        p = PlaywrightManager
        p.set_default_fingerprint()
        context = await p.new_cookie_context(headless=True)
        page = await context.new_page()
        log.debug(f"short url: {short_url}")
        url = self.get_final_url(short_url)  # type:httpx.URL
        try:
            # 过滤静态资源，提高加载速度
            await page.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in ("stylesheet", "image", "media", "font")
                else route.continue_(),
            )

            start = time.time()
            async with page.expect_response(
                    lambda r: IMAGE_DETAIL_API_URL in r.url and r.status == 200,
                    timeout=30000
            ) as resp_info:
                await page.goto(str(url), wait_until="domcontentloaded", timeout=30000)
            log.debug(f"_intercept_page.route 捕获目标请求 耗时 {round(time.time() - start, 2)}")

            response = await resp_info.value  # 返回 Response 对象
            try:
                detail_json = await response.json()
            except Exception as e:
                log.error(f"解析 JSON 失败: {e}")
                raise Exception("解析 API JSON 失败。")
            item_struct = collect_values(detail_json, "itemStruct")
            aweme_id = item_struct.get("id")
            desc = item_struct.get("desc", "")
            create_time = item_struct.get("createTime", 0)  # Unix timestamp
            author_info = item_struct.get("author", {})
            author_id = author_info.get("id")
            author_nickname = author_info.get("nickname")
            statistics_data = item_struct.get("stats", {})

            # 图集
            image_post = item_struct.get("imagePost")
            images_option = self._parse_image_data(image_post)
            if not images_option:
                raise TikTokParseError("图集获取失败，或图集字段缺失")

            # 音乐
            music_post = item_struct.get("music")
            music_option = self._parse_music_data(music_post)

            # ─── 组装 TikTokPost ───
            return TikTokPost(
                aweme_id=aweme_id,
                title=desc,
                description=desc,
                create_time=create_time,
                author_id=author_id,
                author_nickname=author_nickname,
                images=images_option,
                music=music_option,
                is_video=False,
                is_image_album=True,
                view_count=statistics_data.get("playCount"),
                like_count=statistics_data.get("diggCount"),
                comment_count=statistics_data.get("commentCount"),
                share_count=statistics_data.get("shareCount"),
            )

        finally:
            await context.close()
