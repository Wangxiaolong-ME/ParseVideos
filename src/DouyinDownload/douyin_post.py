# douyin_post.py
"""
定义核心业务类 DouyinPost，封装对单个抖音作品的所有操作。
Defines the core business class, DouyinPost, which encapsulates all operations for a single Douyin post.
"""
import json
import os
import re
from datetime import datetime
from typing import List, Optional, Union

import requests

from DouyinDownload.config import DEFAULT_SAVE_DIR, DOWNLOAD_HEADERS
from PublicMethods.m_download import Downloader
from DouyinDownload.exceptions import ParseError
from DouyinDownload.models import VideoOption,AudioOptions
from DouyinDownload.parser import DouyinParser
from TelegramBot.config import DOUYIN_DOWNLOAD_THREADS, DOUYIN_SESSION_COUNTS
import logging

log = logging.getLogger(__name__)


class DouyinPost:
    """
    代表一个抖音作品（视频）。
    Represents a Douyin post (video).

    这是一个有状态的类，其实例化后，会通过其方法逐步填充自身属性，并最终执行下载等操作。
    This is a stateful class. After instantiation, it progressively populates its attributes
    through its methods, and finally performs actions like downloading.
    """

    # --- 类属性：作为对象的状态 ---
    # --- Class Attributes: Serving as the object's state ---
    short_url: str
    """用户输入的原始短链接 (The original short URL provided by the user)"""

    save_dir: str = DEFAULT_SAVE_DIR
    """视频文件保存的目录 (The directory where video files will be saved)"""

    video_title: Optional[str] = None
    """解析出的视频标题 (The parsed video title)"""

    raw_video_options: List[VideoOption] = []
    """解析API直接得到的、未经过滤的所有视频下载选项 (All video options parsed directly from the API, unfiltered)"""

    processed_video_options: List[VideoOption] = []
    """经过筛选、排序等处理后的视频下载选项，下载时将从此列表中选择 (Video options after filtering and sorting, used for downloading)"""

    def __init__(self, short_url_text: str, save_dir: str = DEFAULT_SAVE_DIR, trust_env: bool = False,
                 threads: int = DOUYIN_DOWNLOAD_THREADS):
        """
        构造函数，初始化一个抖音作品对象。
        Constructor to initialize a DouyinPost object.

        :param short_url_text: 包含抖音短链接的文本 (Text containing a Douyin short URL).
        :param save_dir: 视频保存目录 (Directory to save the video).
        :param trust_env: 是否信任系统代理设置 (Whether to trust system proxy settings).
        :param threads: 下载时使用的线程数 (Number of threads for downloading).
        """
        self.audio = AudioOptions
        self.parser = DouyinParser()
        self.short_url = self.parser.extract_short_url(short_url_text)
        self.save_dir = save_dir

        self._session = requests.Session()
        self._session.trust_env = trust_env
        log.debug(f"代理状态：{trust_env}")
        self.downloader = Downloader(session=self._session, threads=threads)

        # 初始化状态属性
        self.video_id = None
        self.video_title = None
        self.processed_video_title = None
        self.raw_video_options = []
        self.processed_video_options = []

        self.content_type = 'video'
        self.gear_name = None  # 视频去重后才会生成

        log.debug(f"抖音作品已初始化 (DouyinPost initialized). 短链接 (Short URL): {self.short_url}")

    async def fetch_details(self) -> 'DouyinPost':
        """
        获取视频详情，填充 raw_video_options 和 processed_video_options 属性。
        Fetches video details, populating the raw_video_options and processed_video_options attributes.
        """
        log.debug("正在获取作品详情 (Fetching post details)...")
        if not self.video_title:  # 避免重复获取
            self.video_title, self.raw_video_options = await self.parser.fetch(self.short_url)
            if not self.raw_video_options:
                raise ParseError("未能获取到作品详情 (Failed to get valid video details).")
            # 保留原始标题，并创建一个处理后的标题用于文件命名
            self.processed_video_title = re.sub(r'[#].*?(\s|$)', '', self.video_title.replace('\n', ' ')).strip()
            self.video_id = self.raw_video_options[0].aweme_id
            # 初始状态下，处理后的列表等于原始列表
            self.processed_video_options = self.raw_video_options.copy()
            log.info(f"标题:{self.video_title}")
            log.info(f"vid:{self.video_id}")

            self.audio = self.parser.audio  # 音频

            # 默认按分辨率降序排序
            self.sort_options(by='resolution', descending=True)
        return self

    def get_content_type(self, short_url: str) -> str:
        """
        通过 HEAD 请求重定向地址判断给定短链接指向的内容类型 (video 或 image_album)。
        Returns: "video", "image_album", or "unknown"
        """
        try:
            # 不能没有头，第二条会成功；也不能有准确的头，第三台跳会444，所以设置模糊头
            headers = DOWNLOAD_HEADERS
            headers['User-Agent'] = 'p'
            final_url = self.downloader._get_final_url(short_url, headers=headers, return_filed_url=True)
            log.debug(f"通过 HEAD 请求重定向判断指向内容类型: {final_url}")
            if "/video/" in final_url:
                log.debug(f"指向内容为视频")
                return "video"
            elif "/note/" in final_url:
                log.debug(f"指向内容为图集")
                return "image"
            else:
                log.debug(f"指向内容未知")
                return "unknown"

        except requests.exceptions.RequestException as e:
            # 捕获所有 requests 相关的异常，例如连接错误、超时、HTTP 错误等
            log.error(f"HEAD 请求失败或发生错误: {e}")  # 可以替换为 logging.error
            return "unknown"
        except Exception as e:
            # 捕获其他未知异常
            log.error(f"判断内容类型时发生未知错误: {e}")  # 可以替换为 logging.error
            return "unknown"

    # --- 链接处理方法 (Link Processing Methods) ---

    def sort_options(self, by: str = 'resolution', descending: bool = True,  exclude_resolution=None) -> 'DouyinPost':
        """
        对 'processed_video_options' 列表进行排序。
        Sorts the 'processed_video_options' list.

        :param by: 排序依据，可选 'resolution' 或 'size'.
        :param descending: 是否降序排列.
        :param exclude_resolution: 排除的分辨率
        :return: self, 以支持链式调用 (self, for chainable calls).
        """
        if by not in ['resolution', 'size']:
            raise ValueError(
                "排序关键字 'by' 必须是 'resolution' 或 'size' (Sort key 'by' must be 'resolution' or 'size').")

        key_func = lambda option: getattr(option, 'resolution' if by == 'resolution' else 'size_mb') or 0
        self.processed_video_options.sort(key=key_func, reverse=descending)
        log.debug(
            f"已按 '{by}' {'降序' if descending else '升序'} 重新排序视频选项 (Video options have been re-sorted by '{by}' in {'descending' if descending else 'ascending'} order).")
        if exclude_resolution:
            excluded_videos = []
            for video in self.processed_video_options:
                if video.resolution in exclude_resolution:
                    log.debug(f"已过滤 {video.resolution} 分辨率视频")
                    continue
                excluded_videos.append(video)
            self.processed_video_options = excluded_videos

        return self

    def filter_by_size(self, min_mb: Optional[float] = None, max_mb: Optional[float] = None) -> 'DouyinPost':
        """
        根据文件大小(MB)筛选视频选项。
        Filters video options by file size (in MB).

        :param min_mb: 最小大小（包含）. 如果为None则不限制下限.
        :param max_mb: 最大大小（包含）. 如果为None则不限制上限.
        :return: self, 以支持链式调用.
        """
        if min_mb is None and max_mb is None:
            return self  # 无操作

        original_count = len(self.processed_video_options)

        def is_valid(option: VideoOption) -> bool:
            if option.size_mb is None:
                return False  # 无法判断大小的选项不保留
            if min_mb is not None and option.size_mb < min_mb:
                return False
            if max_mb is not None and option.size_mb > max_mb:
                return False
            return True

        options = [opt for opt in self.processed_video_options if is_valid(opt)]
        log.debug(
            f"按大小筛选：从 {original_count} 个选项中保留了 {len(options)} 个 (Filtered by size: kept {len(self.processed_video_options)} of {original_count} options).")
        # 兜底,取最小文件
        if not options:
            self.sort_options('size')
            self.processed_video_options = [self.processed_video_options[-1]]
            log.warning("筛选无符合条件的结果，兜底保留1个最小文件")
            return self
        self.processed_video_options = options
        return self

    def deduplicate_by_resolution(self, keep: str = 'highest_bitrate') -> 'DouyinPost':
        """
        对每个分辨率，只保留一个最佳的视频选项。默认保留最高
        For each resolution, keeps only the best video option.

        :param keep: 保留策略, 可选:
                     'highest_bitrate' (最高码率),
                     'lowest_bitrate' (最低码率),
                     'largest_size' (最大文件),
                     'smallest_size' (最小文件).
        :return: self, 以支持链式调用.
        """
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
            # 过滤掉sort_key为None的选项
            valid_options = [opt for opt in options if getattr(opt, sort_key) is not None]
            if not valid_options:
                continue

            # 根据策略选择最大或最小
            chosen = max(valid_options, key=lambda x: getattr(x, sort_key)) if is_max_preferred else \
                min(valid_options, key=lambda x: getattr(x, sort_key))
            deduped_list.append(chosen)

        original_count = len(self.processed_video_options)
        self.processed_video_options = deduped_list
        self.gear_name = self.processed_video_options[0].gear_name  # 取默认第一个的gear_name
        log.debug(
            f"分辨率去重 ('{keep}'): 从 {original_count} 个选项中保留了 {len(self.processed_video_options)} 个 (Deduplicated by resolution ('{keep}'): kept {len(self.processed_video_options)} of {original_count} options).")
        option = self.processed_video_options[0]
        log.debug(f"去重后第一个视频参数:{option.resolution}>>{option.gear_name}>>{option.size_mb}")
        return self

    def get_option(self, resolution: Optional[int] = None, strategy: str = "highest_resolution") -> Optional[
        VideoOption]:

        if not self.processed_video_options:
            raise ParseError("请先调用 .fetch_details() 填充 processed_video_options")

        # --- 1. 若用户指定了分辨率 ---
        if resolution is not None:
            for opt in self.processed_video_options:
                if opt.resolution == resolution:
                    return opt
            # 没找到就直接返回 第一个
            return self.processed_video_options[0]

        # --- 2. 按策略自动选择 ---
        opts = self.processed_video_options
        if strategy == "highest_resolution":
            # 列表已按 resolution 降序排过；直接取第一个即可
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

    # --- 核心动作方法 (Core Action Methods) ---

    def download_video(self, resolution: Optional[int] = None, download_all: bool = False, timeout=60) -> List[str]:
        """
        下载视频。
        Downloads the video(s).

        :param timeout: 超时时长 s
        :param resolution: 指定要下载的分辨率 (e.g., 720, 1080). 如果为 None，则默认下载最高分辨率/质量的视频.
        :param download_all: 是否下载 `processed_video_options` 中的所有视频.
        :return: 一个包含所有成功下载文件路径的列表.
        """
        if not self.processed_video_options:
            raise ParseError(
                "没有可供下载的视频链接。请先调用 .fetch_details() (No video links available for download. Please call .fetch_details() first).")

        targets: List[VideoOption] = []
        if download_all:
            targets = self.processed_video_options
        elif resolution is not None:
            targets = [opt for opt in self.processed_video_options if opt.resolution == resolution]
            if not targets:
                log.warning(
                    f"[警告] 未找到指定分辨率 {resolution}p 的视频，将自动下载当前列表中的最佳选项 (Could not find {resolution}p, downloading the best available option).")

        # 如果没有匹配到目标（或未指定），则选择 processed_video_options 中的第一个（通常是最佳的）
        if not targets:
            # 确保列表已排序，以便选择最佳
            self.sort_options(by='resolution', descending=True)
            targets = [self.processed_video_options[0]]

        os.makedirs(self.save_dir, exist_ok=True)
        saved_paths: List[str] = []

        for option in targets:
            filename = f"{self.video_id}_{option.gear_name}.mp4"
            output_path = os.path.join(self.save_dir, filename)

            log.debug(f"开始下载 (Starting download): {filename}")
            log.debug(f"URL: {option.url}")
            log.debug(
                f"预计大小 (Estimated size): {option.size_mb:.2f} MB" if option.size_mb else "大小未知 (Unknown size)")

            start_time = datetime.now()
            # self.downloader.download_with_fallback(option.url, output_path)
            self.downloader.download(option.url, output_path, timeout=timeout)
            end_time = datetime.now()

            elapsed_seconds = (end_time - start_time).total_seconds()
            file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
            speed = file_size_mb / elapsed_seconds if elapsed_seconds > 0 else 0

            log.debug(f"下载完成 (Download complete): {filename}")
            log.debug(f"存路径 (Saved to): {output_path}")
            log.debug(f"文件大小 (File size): {file_size_mb:.2f} MB")
            log.debug(f"耗时 (Time elapsed): {elapsed_seconds:.2f} s, 平均速度 (Avg. speed): {speed:.2f} MB/s")
            saved_paths.append(output_path)

        return saved_paths

    def download_option(self, option: VideoOption, timeout: int = 20) -> str:
        """
        直接按给定的 VideoOption 下载，返回本地文件路径。

        Args:
            option (VideoOption): 需要下载的流对象（可来自任何列表）。
            timeout (int): 单个下载请求的超时 (秒)。
            rename_by_id (bool): True -> 以 aweme_id/ge ar_name 命名，
                                 False -> 保留原 `option.url` 中的文件名。

        Returns:
            str: 下载后文件的绝对路径。
        """
        # —— 生成保存文件名 ——
        filename = f"{option.aweme_id}_{option.gear_name}.mp4"

        os.makedirs(self.save_dir, exist_ok=True)
        out_path = os.path.join(self.save_dir, filename)

        log.debug(f"[download_option] 开始下载 {filename}")
        log.debug(f"  URL: {option.url}")
        log.debug(f"  预计大小: {option.size_mb or '未知'} MB")

        start = datetime.now()
        self.downloader.download(option.url, out_path, timeout=timeout, multi_session=True,
                                 session_pool_size=DOUYIN_SESSION_COUNTS)
        cost = (datetime.now() - start).total_seconds()

        size_mb = os.path.getsize(out_path) / (1024 * 1024)
        speed = size_mb / cost if cost else 0
        log.debug(f"[download_option]下载完成: {size_mb:.2f}MB, 耗时{cost:.2f}s, 平均速度：{speed:.2f} MB/s")

        return out_path

    # --- 元数据 I/O 方法 (Metadata I/O Methods) ---

    def save_metadata(self, filepath: Optional[str] = None) -> str:
        """
        将当前作品的原始解析数据保存到 JSON 文件。
        Saves the raw parsed data of the current post to a JSON file.

        :param filepath: 保存的文件路径. 如果为None, 则默认保存在 save_dir 下以标题命名.
        :return: 最终保存的文件路径.
        """
        if not self.raw_video_options:
            raise ParseError(
                "没有元数据可保存。请先调用 .fetch_details() (No metadata to save. Please call .fetch_details() first).")

        if filepath is None:
            os.makedirs(self.save_dir, exist_ok=True)
            filepath = os.path.join(self.save_dir, f"{self.processed_video_title}_metadata.json")

        metadata = {
            self.short_url: {
                "video_title": self.video_title,
                "fetched_at": datetime.now().isoformat(),
                # 将 VideoOption 对象转换为字典
                "raw_video_options": [vars(opt) for opt in self.raw_video_options]
            }
        }
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=4)
        except Exception as e:
            log.error(f"元数据保存失败,{e}")

        log.debug(f"元数据已保存至 (Metadata saved to): {filepath}")
        return filepath

    @classmethod
    def load_from_metadata(cls, filepath: str, **kwargs) -> 'DouyinPost':
        """
        从元数据文件加载并创建一个 DouyinPost 实例，跳过网络请求。
        Loads and creates a DouyinPost instance from a metadata file, skipping network requests.

        :param filepath: 元数据JSON文件路径.
        :param kwargs: 传递给 DouyinPost 构造函数的额外参数 (e.g., save_dir).
        :return: 一个填充了数据的 DouyinPost 实例.
        """
        with open(filepath, 'r', encoding='utf-8') as f:
            metadata = json.load(f)

        short_url = next(iter(metadata))
        data = metadata[short_url]

        # 使用 short_url 初始化实例
        instance = cls(short_url_text=short_url, **kwargs)

        # 手动填充属性
        instance.video_title = data["video_title"]
        instance.raw_video_options = [VideoOption(**opt_data) for opt_data in data["raw_video_options"]]
        instance.processed_video_options = instance.raw_video_options.copy()

        log.debug(f"已从文件加载元数据 (Metadata loaded from file): {filepath}")
        log.debug(f"标题 (Title): '{instance.video_title}', 共 {len(instance.raw_video_options)} 个视频流 (streams).")
        return instance
