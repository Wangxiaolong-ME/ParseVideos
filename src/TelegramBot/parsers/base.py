# TelegramBot/parsers/base.py
from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Union, Literal, Optional

from DouyinDownload.models import VideoOption,AudioOptions
from TikTokDownload.models import TikTokVideoOption

logger = logging.getLogger(__name__)

# 定义内容类型，便于通用处理器判断如何发送
ContentType = Literal["video", "audio", "image_gallery", "link", "unknown"]


@dataclass
class MediaItem:
    """标准化的媒体项目，用于图集或单个文件"""
    local_path: Union[str, Path]
    file_type: Literal["video", "photo"] = "photo"
    width: int | None = None
    height: int | None = None
    duration: int | None = None


@dataclass
class VideoQualityOption(VideoOption):
    """视频质量选项，用于按钮选择"""
    resolution: int  # 分辨率 (720, 1080等)
    quality_name: str  # 显示名 (720p, 1080p等)
    download_url: str  # 下载链接
    size_mb: float  # 文件大小
    is_default: bool = False  # 是否默认选项（50M以内头部展示）

@dataclass
class TikTokVideoQualityOption(TikTokVideoOption):
    """视频质量选项，用于按钮选择"""
    size_mb: float  # 文件大小
    is_default: bool = False  # 是否默认选项（50M以内头部展示）

@dataclass
class ParseResult:
    """
    所有平台解析器必须返回的标准数据结构。
    通用处理器将根据这个结构来执行后续操作。
    """
    # ---- 核心字段 ----
    success: bool = False
    content_type: ContentType = "unknown"
    media_items: List[MediaItem] = field(default_factory=list)  # 媒体文件列表（视频、图片集）

    # ---- 元数据字段 ----
    title: str | None = None
    vid: str | None = None  # 平台唯一ID (用于缓存key)
    original_url: str | None = None  # 原始输入链接
    download_url: str | None = None  # 解析出的下载链接 (用于日志)
    size_mb: float | None = None  # 文件大小
    audio_uri : str | None = None   # 音乐直链
    audio_title: str | None = None
    html_title: str | None = None   # HTML格式化后的标题

    # ---- 特殊情况字段 ----
    text_message: str | None = None  # 如果需要直接发送文本消息（例如 >50MB 的链接）
    bili_preview_video: bool | None = None  # B站私人视频或会员视频
    download_url_list: List[str] = field(default_factory=list)   # 多个下载链接列表
    
    # ---- 多分辨率选择字段 ----
    quality_options: List[VideoQualityOption] = field(default_factory=list)  # 视频质量选项列表
    needs_quality_selection: bool = False  # 是否需要用户选择分辨率
    preview_url: str | None = None  # ≤20MB视频的预览链接，用于TG自动预览

    # ---- 异常信息 ----
    error_message: str | None = None

    def add_media(self, local_path: Union[str, Path], **kwargs):
        """辅助方法，方便添加媒体项目"""
        self.media_items.append(MediaItem(local_path=local_path, **kwargs))


class BaseParser(ABC):
    """
    所有平台解析器的抽象基类 (Abstract Base Class)。
    定义了所有解析器必须实现的 `parse` 方法契约。
    """

    def __init__(self, url: str, save_dir: Path):
        self.url = url
        self.save_dir = save_dir
        self.result = ParseResult(original_url=url)
        # 确保保存目录存在
        self.save_dir.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    async def parse(self) -> ParseResult:
        """
        核心解析方法。
        子类必须实现此方法，执行下载或解析，并填充 self.result 对象。
        - I/O密集型操作应在此方法内完成。
        - 必须返回一个填充好的 ParseResult 对象。
        """
        raise NotImplementedError

    async def peek(self) -> tuple[str, str]:
        """
         只返回 (vid, title)，不做下载。
        """
        raise NotImplementedError

    def _safe_filename(self, name: str) -> str:
        """提供一个通用的安全文件名方法。"""
        return "".join(c for c in name if c not in r'\/:*?"<>|').strip()
