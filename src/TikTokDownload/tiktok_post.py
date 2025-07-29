# tiktok_post.py
import json
import os
import re
from datetime import datetime
from typing import List, Optional, Any, Coroutine

import httpx
import logging

from PublicMethods.m_download import Downloader
# 从新定义的模块中导入
from TikTokDownload.models import TikTokPost, TikTokVideoOption, TikTokImage, TikTokMusicOption
from TikTokDownload.parser import TikTokParser, TikTokParseError
from TikTokDownload.config import TIKTOK_DEFAULT_SAVE_DIR, TIKTOK_USER_AGENT, TIKTOK_DOWNLOAD_THREADS

log = logging.getLogger(__name__)


class TikTokPostManager:
    """
    代表一个 TikTok 作品（视频或图集），封装其获取、处理和下载的所有操作。
    这是一个有状态的类，其实例化后，会通过其方法逐步填充自身属性，并最终执行下载等操作。
    """

    short_url: str
    """用户输入的原始短链接 (The original short URL provided by the user)"""

    save_dir: str = TIKTOK_DEFAULT_SAVE_DIR
    """文件保存的目录 (The directory where files will be saved)"""

    tiktok_post_data: Optional[TikTokPost] = None
    """解析后的 TikTokPost 数据模型 (The parsed TikTokPost data model)"""

    processed_video_options: List[TikTokVideoOption] = []
    """经过筛选、排序等处理后的视频下载选项，下载时将从此列表中选择"""

    processed_images: List[TikTokImage] = []
    """经过筛选、处理后的图片下载选项"""

    def __init__(self, short_url_text: str, save_dir: str = TIKTOK_DEFAULT_SAVE_DIR,
                 user_agent: str = TIKTOK_USER_AGENT,
                 threads: int = TIKTOK_DOWNLOAD_THREADS):
        """
        构造函数，初始化一个 TikTok 作品对象。

        :param short_url_text: 包含 TikTok 短链接的文本.
        :param save_dir: 文件保存目录.
        :param user_agent: 用于 HTTP 请求的 User-Agent.
        :param threads: 下载时使用的线程数.
        """
        self.content_type = None
        self.headers = None
        self.raw_video_options = None
        self.valid_url = TikTokParser().extract_valid_url(short_url_text)
        self.save_dir = save_dir
        self.parser = TikTokParser()
        # 假设存在一个统一的下载器，这里简化为 httpx.Client
        self.downloader_client = httpx.Client(headers={"User-Agent": user_agent}, follow_redirects=True, timeout=30)
        self.m_download = Downloader()
        # self.downloader = Downloader(session=self._session, threads=threads) # 如果有更复杂的下载器

        # 初始化状态属性
        self.tiktok_post_data: TikTokPost | None
        self.processed_video_options = []
        self.processed_images = []

        log.debug(f"TikTok作品已初始化. 链接: {self.valid_url}")

    async def fetch_details(self) -> 'TikTokPostManager':
        """
        获取作品详情，填充 tiktok_post_data, processed_video_files 和 processed_images 属性。
        尝试从网页的通用数据中解析，如果失败，则尝试直接请求 API。
        """
        log.debug("正在获取作品详情...")
        if self.tiktok_post_data:  # 避免重复获取
            log.info("作品详情已存在，跳过重新获取。")
            return self

        # 作品类型
        content_type, long_url = self.get_content_type(self.valid_url)
        self.content_type = content_type

        url = long_url or self.valid_url  # 优先使用长链接,不用二次重定向

        if content_type == 'video':
            self.tiktok_post_data = await self.parser.fetch_video(url)
        # 图集作品
        elif content_type == 'image':
            self.tiktok_post_data = await self.parser.fetch_images(url)

        # 如果到此步 tiktok_post_data 仍然为空，说明所有尝试都失败了
        if not self.tiktok_post_data:
            raise TikTokParseError("未能获取到作品详情。")

        # 到达此行时，self.tiktok_post_data 必然已被成功赋值
        # 初始化处理后的列表
        self.raw_video_options = self.tiktok_post_data.video.copy()
        self.processed_video_options = self.tiktok_post_data.video.copy()
        self.processed_images = self.tiktok_post_data.images.copy()

        # 对视频文件进行默认排序（例如，按分辨率升序）
        if self.tiktok_post_data.is_video:
            # 确保 sort_video_options 是 TikTokPostManager 类的一个方法
            self.sort_video_options(by='resolution', descending=False)

        self.headers = {"Referer": self.valid_url}

        return self

    def get_content_type(self, short_url: str) -> str | tuple[str, str]:
        """
        通过 HEAD 请求重定向地址判断给定短链接指向的内容类型 (video 或 image_album)。
        Returns: "video", "image_album", or "unknown"
        """
        try:
            r = self.downloader_client.get(short_url)
            final_url = r.url
            log.debug(f"通过 HEAD 请求重定向判断指向内容类型: {final_url}")
            path = final_url.path
            if "/video/" in path:
                log.debug(f"指向内容为视频")
                return "video", str(final_url)
            elif "/photo/" in path:
                log.debug(f"指向内容为图集")
                return "image", str(final_url)
            else:
                log.debug(f"指向内容未知")
                return "unknown", ''

        except Exception as e:
            # 捕获其他未知异常
            log.error(f"请求失败或发生错误: {e}")
            return "unknown", ''

    # --- 视频文件处理方法 (Video File Processing Methods) ---

    def sort_video_options(self, by: str = 'resolution', descending: bool = True) -> 'TikTokPostManager':
        """
        对 'processed_video_files' 列表进行排序。

        :param by: 排序依据，可选 'resolution' 或 'size'.
        :param descending: 是否降序排列.
        :return: self, 以支持链式调用.
        """
        if not self.tiktok_post_data or not self.tiktok_post_data.is_video:
            log.warning("当前作品不是视频，跳过视频选项排序。")
            return self

        if by not in ['resolution', 'size_mb', 'bit_rate']:
            raise ValueError("排序关键字 'by' 必须是 'resolution', 'size_mb' 或 'bit_rate'.")

        key_func = lambda option: getattr(option, by) or 0
        self.processed_video_options.sort(key=key_func, reverse=descending)
        log.debug(f"已按 '{by}' {'降序' if descending else '升序'} 重新排序视频选项.")
        return self

    def filter_video_by_size(self, min_mb: Optional[float] = None,
                             max_mb: Optional[float] = None) -> 'TikTokPostManager':
        """
        根据文件大小(MB)筛选视频选项。

        :param min_mb: 最小大小（包含）. 如果为None则不限制下限.
        :param max_mb: 最大大小（包含）. 如果为None则不限制上限.
        :return: self, 以支持链式调用.
        """
        if not self.tiktok_post_data or not self.tiktok_post_data.is_video:
            log.warning("当前作品不是视频，跳过视频文件筛选。")
            return self

        if min_mb is None and max_mb is None:
            return self  # 无操作

        original_count = len(self.processed_video_options)

        def is_valid(option: TikTokVideoOption) -> bool:
            if option.size_mb is None:
                return False
            if min_mb is not None and option.size_mb < min_mb:
                return False
            if max_mb is not None and option.size_mb > max_mb:
                return False
            return True

        filtered_options = [opt for opt in self.processed_video_options if is_valid(opt)]
        if not filtered_options:
            log.warning("筛选无符合条件的结果，兜底保留1个最小文件。")
            self.sort_video_options('size_mb', descending=False)  # 找到最小的
            self.processed_video_options = [self.processed_video_options[0]] if self.processed_video_options else []
        else:
            self.processed_video_options = filtered_options

        log.debug(f"按大小筛选：从 {original_count} 个选项中保留了 {len(self.processed_video_options)} 个.")
        return self

    def deduplicate_video_options_by_resolution(self, keep: str = 'highest_bitrate') -> 'TikTokPostManager':
        """
        对每个分辨率，只保留一个最佳的视频选项。

        :param keep: 保留策略, 可选: 'highest_bitrate', 'lowest_bitrate', 'largest_size', 'smallest_size'.
        :return: self, 以支持链式调用.
        """
        if not self.tiktok_post_data or not self.tiktok_post_data.is_video:
            log.warning("当前作品不是视频，跳过视频文件去重。")
            return self

        if not self.processed_video_options:
            return self

        valid_keeps = ['highest_bitrate', 'lowest_bitrate', 'largest_size', 'smallest_size']
        if keep not in valid_keeps:
            raise ValueError(f"保留策略 'keep' 必须是 {valid_keeps} 中的一个.")

        key_map = {
            'highest_bitrate': 'bit_rate',
            'lowest_bitrate': 'bit_rate',
            'largest_size': 'size_mb',
            'smallest_size': 'size_mb'
        }
        is_max_preferred = keep in ['highest_bitrate', 'largest_size']
        sort_key = key_map[keep]

        grouped = {}
        for option in self.processed_video_options:
            res = option.resolution
            if res not in grouped:
                grouped[res] = []
            grouped[res].append(option)

        deduped_list = []
        for res, options in grouped.items():
            valid_options = [opt for opt in options if getattr(opt, sort_key) is not None]
            if not valid_options:
                continue

            chosen = max(valid_options, key=lambda x: getattr(x, sort_key)) if is_max_preferred else \
                min(valid_options, key=lambda x: getattr(x, sort_key))
            deduped_list.append(chosen)

        original_count = len(self.processed_video_options)
        self.processed_video_options = deduped_list
        log.debug(f"分辨率去重 ('{keep}'): 从 {original_count} 个选项中保留了 {len(self.processed_video_options)} 个.")
        return self

    def get_preferred_video_file(self, resolution: Optional[int] = None, strategy: str = "highest_resolution") -> \
            Optional[TikTokVideoOption]:
        """
        从处理后的视频文件中选择一个最优选项。
        """
        if not self.processed_video_options:
            log.warning("没有可供选择的视频文件。")
            return None

        if resolution is not None:
            for opt in self.processed_video_options:
                if opt.resolution == resolution:
                    return opt
            log.warning(f"未找到指定分辨率 {resolution}p 的视频，将根据策略选择。")
            # 如果没找到指定分辨率，则根据默认策略继续

        opts = self.processed_video_options
        if strategy == "highest_resolution":
            return max(opts, key=lambda o: o.resolution or 0)
        elif strategy == "smallest_size":
            return min(opts, key=lambda o: o.size_mb or float("inf"))
        elif strategy == "largest_size":
            return max(opts, key=lambda o: o.size_mb or -1)
        elif strategy == "lowest_bitrate":
            return min(opts, key=lambda o: o.bit_rate or float("inf"))
        elif strategy == "highest_bitrate":
            return max(opts, key=lambda o: o.bit_rate or -1)
        else:
            raise ValueError(f"未知 strategy: {strategy}")

    # --- 核心下载方法 (Core Download Methods) ---
    async def _downloader(self, url, output_path, timeout=60):
        for i in range(0, 3):
            try:
                out = self.m_download.download(url, output_path, self.headers, timeout=timeout)
                if not out:
                    raise "下载视频发生错误"
                log.debug(f"下载完成,保存路径: {output_path}")
                return out
            except Exception as e:
                log.error(f"重试 {i + 1} 下载时发生意外错误: {e}")
                continue
        return None

    async def download_video(
            self,
            video: TikTokVideoOption,
            timeout: int = 60,
    ) -> bool | None:
        """原子下载：仅负责下载 *单个* ``TikTokVideoOption``。

        **必选参数**
        - ``video``: 目标视频文件信息。

        **可选参数**
        - ``downloader``: 复用的 ``m_download.Downloader`` 实例；若为 ``None`` 将自动创建 ``threads=4`` 的实例。
        - ``timeout``: 单文件下载超时（秒）。

        **返回**
        - 成功：返回保存路径 ``str``；失败：返回 ``None``。
        """
        if not video:
            return None

        os.makedirs(self.save_dir, exist_ok=True)
        filename = f"{video.aweme_id}_{video.gear_name}.mp4"
        output_path = os.path.join(self.save_dir, filename)

        log.debug(f"开始下载: {filename}")
        log.debug(f"URL: {video.url}")
        if getattr(video, "size_mb", None):
            log.debug(f"预计大小: {video.size_mb:.2f} MB")

        for i in range(0, 3):
            try:
                await self._downloader(video.url, output_path, timeout=timeout)
                return True
            except Exception as e:
                log.error(f"重试 {i + 1} {video.aweme_id}下载时发生意外错误: {e}")
                continue
        return None

    async def download_image_album(self, timeout: int = 60) -> List[str]:
        """
        下载图集中的所有图片。

        :param timeout: 单个图片下载超时时长 s.
        :return: 一个包含所有成功下载图片路径的列表.
        """
        if not self.tiktok_post_data or not self.tiktok_post_data.is_image_album:
            raise TikTokParseError("当前作品不是图集，无法下载图片。")

        if not self.processed_images:
            raise TikTokParseError("没有可供下载的图片链接。请先调用 .fetch_details()。")

        os.makedirs(self.save_dir, exist_ok=True)
        saved_paths: List[str] = []

        for i, img_option in enumerate(self.processed_images):
            # TikTok 的图片通常有多个 URL，选择 download_url_list 中的最高质量
            target_url = img_option.url

            if not target_url:
                log.warning(f"图片 {i + 1} 无可用下载 URL，跳过。")
                continue

            filename = f"{self.tiktok_post_data.aweme_id}_image_{i + 1}.jpg"
            output_path = os.path.join(self.save_dir, filename)

            log.debug(f"开始下载图片: {filename}")
            log.debug(f"URL: {target_url}")

            start_time = datetime.now()
            try:
                out = await self._download_image(img_option, output_path, timeout=timeout)
                if not out:
                    raise "图片下载失败"
                end_time = datetime.now()
                elapsed_seconds = (end_time - start_time).total_seconds()
                file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
                speed = file_size_mb / elapsed_seconds if elapsed_seconds > 0 else 0

                log.debug(f"图片下载完成: {filename}")
                log.debug(f"保存路径: {output_path}")
                log.debug(f"文件大小: {file_size_mb:.2f} MB")
                log.debug(f"耗时: {elapsed_seconds:.2f} s, 平均速度: {speed:.2f} MB/s")
                saved_paths.append(output_path)
            except Exception as e:
                log.error(f"下载图片 {filename} 时发生意外错误: {e}")
        return saved_paths

    async def _download_image(self, image: TikTokImage, output_path, timeout: int = 60):
        if not image or not image.url:
            return None
        for i in range(0, 3):
            try:
                await self._downloader(image.url, output_path, timeout=timeout)
                return True
            except Exception as e:
                log.error(f"重试 {i + 1} 下载图片时发生意外错误: {e}")
                continue
        return None

    async def download_music(self, timeout: int = 40) -> Optional[str]:
        """
        下载作品的背景音乐。
        :param timeout: 下载超时时长 s.
        :return: 成功下载的音乐文件路径，如果无音乐或下载失败则为 None.
        """
        if not self.tiktok_post_data or not self.tiktok_post_data.music or not self.tiktok_post_data.music.url:
            log.warning("作品无背景音乐或音乐链接不可用，跳过音乐下载。")
            return None

        music_option = self.tiktok_post_data.music
        os.makedirs(self.save_dir, exist_ok=True)
        filename = f"{self.tiktok_post_data.aweme_id}_music_{music_option.id}.mp3"  # 假设是 mp3
        output_path = os.path.join(self.save_dir, filename)

        log.debug(f"开始下载音乐: {filename}")
        log.debug(f"URL: {music_option.url}")

        start_time = datetime.now()
        try:
            out = await self._download_music(music_option, output_path, timeout=timeout)
            if not out:
                raise "下载音乐错误"
            end_time = datetime.now()
            elapsed_seconds = (end_time - start_time).total_seconds()
            file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
            speed = file_size_mb / elapsed_seconds if elapsed_seconds > 0 else 0

            log.debug(f"音乐下载完成: {filename}")
            log.debug(f"保存路径: {output_path}")
            log.debug(f"文件大小: {file_size_mb:.2f} MB")
            log.debug(f"耗时: {elapsed_seconds:.2f} s, 平均速度: {speed:.2f} MB/s")
            return output_path
        except httpx.RequestError as e:
            log.error(f"下载音乐 {filename} 失败: {e}")
            return None
        except Exception as e:
            log.error(f"下载音乐 {filename} 时发生意外错误: {e}")
            return None

    async def _download_music(self, music: TikTokMusicOption, output_path, timeout=40):
        if not music or not music.url:
            return None

        for i in range(0, 3):
            try:
                await self._downloader(music.url, output_path, timeout=timeout)
                return True
            except Exception as e:
                log.error(f"重试 {i + 1} 下载音乐时发生意外错误: {e}")
                continue
        return None
