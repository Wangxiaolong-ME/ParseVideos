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
from DouyinDownload.models import ImageOptions, Image
from DouyinDownload.parser import DouyinParser
from TelegramBot.config import DOUYIN_DOWNLOAD_THREADS, DOUYIN_SESSION_COUNTS, DOUYIN_SAVE_DIR

log = logging.getLogger(__name__)


class DouyinImagePost:
    """
    代表一个抖音图片作品。
    Represents a Douyin image post.
    """

    short_url: str
    save_dir: str = DOUYIN_SAVE_DIR
    image_options: Optional[ImageOptions] = None
    processed_image_title: Optional[str] = None
    title: str = ''
    aweme_id: Optional[str] = None

    def __init__(self, short_url_text: str, save_dir: str = DOUYIN_SAVE_DIR, trust_env: bool = False,
                 threads: int = DOUYIN_DOWNLOAD_THREADS):
        self.parser = DouyinParser()
        self.short_url = self.parser.extract_short_url(short_url_text)
        self.save_dir = save_dir

        self._session = requests.Session()
        self._session.trust_env = trust_env
        log.debug(f"图片下载代理状态：{trust_env}")
        self.downloader = Downloader(session=self._session, threads=threads)

        log.debug(f"抖音图片作品已初始化 (DouyinImagePost initialized). 短链接 (Short URL): {self.short_url}")

    def fetch_details(self) -> 'DouyinImagePost':
        """
        获取图片作品详情，填充 image_options 属性。
        Fetches image post details, populating the image_options attribute.
        """
        log.debug("正在获取图片作品详情 (Fetching image post details)...")
        if not self.image_options:  # 避免重复获取
            self.image_options = self.parser.fetch_images(self.short_url)
            if not self.image_options:
                raise ParseError("未能获取到有效的图片详情 (Failed to get valid image details).")
            self.title = self.image_options.desc
            self.aweme_id = self.image_options.aweme_id
            # 根据ID用于文件命名
            self.processed_image_title = f"douyin_image_{self.aweme_id}"

            log.debug(f"获取图片详情成功！标题 (Success! Title): '{self.processed_image_title}'. "
                      f"共找到 {len(self.image_options.images)} 张图片 (Found {len(self.image_options.images)} images).")
        return self

    def download_images(self, timeout: int = 60) -> List[Image]:  # 返回类型修改为 List[Image]
        """
        下载图片作品中的所有图片。
        Downloads all images from the image post.

        :param timeout: 单个下载请求的超时 (秒)。
        :return: 一个包含所有成功下载 Image 对象的列表。
        """
        if not self.image_options or not self.image_options.images:
            raise ParseError(
                "没有可供下载的图片。请先调用 .fetch_details() (No images available for download. Please call .fetch_details() first).")

        os.makedirs(self.save_dir, exist_ok=True)
        # 修改 saved_paths 的类型，用于存储 Image 对象
        saved_images_info: List[Image] = []

        start_time = datetime.now()

        size_merge = 0
        for idx, img_data in enumerate(self.image_options.images):
            url_list = img_data.get("urlList")
            if not url_list:
                log.warning(
                    f"图片 {idx + 1} 没有可用的下载URL，跳过 (Image {idx + 1} has no available download URL, skipping).")
                continue

            download_url = url_list[-1]  # 选择最后一个链接

            filename = f"{self.aweme_id}_img_{idx + 1}.jpg"
            output_path = os.path.join(self.save_dir, filename)

            log.debug(f"开始下载图片 (Starting image download): {filename}")
            log.debug(f"URL: {download_url}")

            try:
                self.downloader.download(download_url, output_path, timeout=timeout, multi_session=True,
                                         session_pool_size=DOUYIN_SESSION_COUNTS)

                size_merge += os.path.getsize(output_path) / (1024 * 1024) if os.path.exists(
                    output_path) and os.path.getsize(output_path) > 0 else 0

                # 创建 Image 对象并添加到列表中
                downloaded_image = Image(
                    width=img_data.get("width"),
                    height=img_data.get("height"),
                    url=download_url,  # 使用实际下载的URL
                    local_path=output_path
                )
                saved_images_info.append(downloaded_image)
            except Exception as e:
                log.error(f"下载图片 {filename} 失败: {e}")
        end_time = datetime.now()
        elapsed_seconds = (end_time - start_time).total_seconds()
        speed = size_merge / elapsed_seconds if elapsed_seconds > 0 else 0
        log.debug(f"下载完成 (Download complete): {self.aweme_id}_img_1-{len(saved_images_info)}")
        log.debug(f"文件大小 (File size): {size_merge:.2f} MB")
        log.debug(f"耗时 (Time elapsed): {elapsed_seconds:.2f} s, 平均速度 (Avg. speed): {speed:.2f} MB/s")

        return saved_images_info  # 返回 Image 对象列表