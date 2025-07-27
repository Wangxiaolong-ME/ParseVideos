# douyin_image_post.py
"""
定义核心业务类 DouyinImagePost，封装对单个抖音图片作品的所有操作。
Defines the core business class, DouyinImagePost, which encapsulates all operations for a single Douyin image post.
"""
import os
import json
import logging
import re
from datetime import datetime
from typing import List, Optional, Union, Dict, Any

import requests

from PublicMethods.m_download import Downloader
from DouyinDownload.exceptions import ParseError
from DouyinDownload.models import ImageOptions, Image, AudioOptions
from DouyinDownload.parser import DouyinParser
from DouyinDownload.config import DOWNLOAD_HEADERS
from TelegramBot.config import DOUYIN_DOWNLOAD_THREADS, DOUYIN_SESSION_COUNTS, DOUYIN_SAVE_DIR

log = logging.getLogger(__name__)


class DouyinImagePost:
    """
    代表一个抖音图片作品。
    Represents a Douyin image post.
    """

    short_url: str
    save_dir: str = DOUYIN_SAVE_DIR
    aweme_detail: Optional[ImageOptions] = None
    processed_image_title: Optional[str] = None
    title: str = ''
    aweme_id: Optional[str] = None

    def __init__(self, short_url_text: str, save_dir: str = DOUYIN_SAVE_DIR, trust_env: bool = False,
                 threads: int = DOUYIN_DOWNLOAD_THREADS):
        self.parser = DouyinParser()
        self.audio = AudioOptions
        self.short_url = self.parser.extract_short_url(short_url_text)
        self.save_dir = save_dir

        self._session = requests.Session()
        self._session.trust_env = trust_env
        log.debug(f"图片下载代理状态：{trust_env}")
        self.downloader = Downloader(session=self._session, threads=threads)

        log.debug(f"抖音图片作品已初始化 (DouyinImagePost initialized). 短链接 (Short URL): {self.short_url}")

    async def fetch_details(self) -> 'DouyinImagePost':
        """
        获取图片作品详情，填充 aweme_detail 属性。
        Fetches image post details, populating the aweme_detail attribute.
        """
        log.info("正在获取图片作品详情 (Fetching image post details)...")
        if not self.aweme_detail:  # 避免重复获取
            self.aweme_detail = await self.parser.fetch_images(self.short_url)
            if not self.aweme_detail:
                raise ParseError("未能获取到有效的图片详情 (Failed to get valid image details).")
            self.title = self.aweme_detail.desc
            self.aweme_id = self.aweme_detail.aweme_id
            # 根据ID用于文件命名
            self.processed_image_title = f"douyin_image_{self.aweme_id}"

            self.audio = self.parser.audio

            log.debug(f"获取图片详情成功！标题 (Success! Title): '{self.processed_image_title}'. "
                      f"共找到 {len(self.aweme_detail.images)} 张图片 (Found {len(self.aweme_detail.images)} images).")
        return self

    def download_images(self, timeout: int = 60) -> List[Image]:  # 返回类型修改为 List[Image]
        """
        下载图片作品中的所有图片或视频。
        Downloads all images or videos from the image/mix post.

        :param timeout: 单个下载请求的超时 (秒)。
        :return: 一个包含所有成功下载 Image 对象（现在可代表视频）的列表。
        """
        if not self.aweme_detail or not self.aweme_detail.images:
            raise ParseError(
                "没有可供下载的图片/视频。请先调用 .fetch_details() (No images/videos available for download. Please call .fetch_details() first).")

        os.makedirs(self.save_dir, exist_ok=True)
        # 修改 saved_images_info 的类型，用于存储 Image 对象（现在可以代表视频）
        saved_media_info: List[Image] = []

        start_time = datetime.now()

        size_merge = 0
        for idx, media_data in enumerate(self.aweme_detail.images):
            download_url = None
            filename = None
            file_type = "image"
            media_width = media_data.get("width")
            media_height = media_data.get("height")
            media_duration = None

            # 检查是否存在 video 字段，如果存在且不为 null，则优先下载视频
            if media_data.get("video"):
                video_info = media_data["video"]
                media_duration = video_info.get("duration")
                bit_rate_list = video_info.get("bitRateList")
                if bit_rate_list and isinstance(bit_rate_list, list) and bit_rate_list:
                    # 选择第一个可用的视频URL
                    download_url = bit_rate_list[0].get("playApi")
                    file_type = "video"
                    media_width = video_info.get("width")
                    media_height = video_info.get("height")

                    # 尝试从 videoFormat 获取文件后缀，否则默认为 mp4
                    video_format = video_info.get("videoFormat", "mp4")
                    filename = f"{self.aweme_id}_video_{idx + 1}.{video_format}"
                else:
                    log.warning(
                        f"视频 {idx + 1} 没有可用的播放地址，尝试下载图片 (Video {idx + 1} has no available play address, trying to download image).")

            # 如果没有视频URL或视频下载失败，则尝试下载图片
            if not download_url:
                url_list = media_data.get("urlList")
                if not url_list:
                    log.warning(
                        f"图片 {idx + 1} 没有可用的下载URL，跳过 (Image {idx + 1} has no available download URL, skipping).")
                    continue
                download_url = url_list[-1]  # 选择最后一个链接
                filename = f"{self.aweme_id}_img_{idx + 1}.jpg"  # 图片默认后缀为jpg
                file_type = "image"

            if not download_url:  # 再次检查是否获取到有效的下载URL
                log.warning(
                    f"媒体 {idx + 1} 既没有可用视频URL也没有可用图片URL，跳过 (Media {idx + 1} has no available video or image URL, skipping).")
                continue

            output_path = os.path.join(self.save_dir, filename)

            log.debug(f"开始下载 {file_type} (Starting {file_type} download): {filename}")
            log.debug(f"URL: {download_url}")

            for i in range(0, 3):
                try:
                    # 图集单个都不大，不需要多session
                    self.downloader.download(download_url, headers=DOWNLOAD_HEADERS, path=output_path, timeout=timeout)

                    size_merge += os.path.getsize(output_path) / (1024 * 1024) if os.path.exists(
                        output_path) and os.path.getsize(output_path) > 0 else 0

                    # 创建 Image 对象（现在可代表视频）并添加到列表中
                    downloaded_media = Image(
                        width=media_width,
                        height=media_height,
                        url=download_url,  # 使用实际下载的URL
                        local_path=output_path,
                        duration=media_duration,
                        file_type=file_type
                    )
                    saved_media_info.append(downloaded_media)
                    break
                except Exception as e:
                    log.error(f"下载 {file_type} {filename} 失败: {e}")
                    continue

        end_time = datetime.now()
        elapsed_seconds = (end_time - start_time).total_seconds()
        speed = size_merge / elapsed_seconds if elapsed_seconds > 0 else 0
        log.debug(f"下载完成 (Download complete): {self.aweme_id}_media_1-{len(saved_media_info)}")
        log.debug(f"文件大小 (File size): {size_merge:.2f} MB")
        log.debug(f"耗时 (Time elapsed): {elapsed_seconds:.2f} s, 平均速度 (Avg. speed): {speed:.2f} MB/s")

        return saved_media_info  # 返回 Image 对象列表（现在可以包含视频信息）
