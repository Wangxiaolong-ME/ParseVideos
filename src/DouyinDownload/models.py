# models.py
"""
定义数据模型，用于结构化地表示业务对象。
Defines data models to structurally represent business objects.
"""
from dataclasses import dataclass
from typing import Optional, Any, Dict, List


@dataclass
class VideoOption:
    """
    封装单个视频下载选项的所有信息。
    Encapsulates all information for a single video download option.

    Attributes:
        resolution (int): 视频分辨率，如 720, 1080, 2160 (4K).
        bit_rate (int): 视频码率 (bps).
        url (str): 最终选择的下载地址.
        size_mb (Optional[float]): 视频文件大小 (MB). 如果未知则为 None.
        gear_name (str): 抖音API返回的原始档位名称，用于调试.
        quality (str): 视频质量描述，如 'normal_720_0'.
    """
    resolution: int
    bit_rate: int
    url: str
    size_mb: Optional[float]
    gear_name: str
    quality: str
    aweme_id: int
    height: int
    width: int
    duration: int | float

    def __repr__(self) -> str:
        size_str = f"{self.size_mb:.2f} MB" if self.size_mb is not None else "Unknown Size"
        return (
            f"<VideoOption resolution={self.resolution}p, "
            f"bit_rate={self.bit_rate}, size={size_str}, url='{self.url}'>"
        )
@dataclass
class ImageOptions:
    """
    封装单个视频下载选项的所有信息。
    """
    aweme_id: str
    desc: str
    create_time: int
    author_info: Optional[Dict[str, Any]]
    images: Optional[List[Dict[str, Any]]]

@dataclass
class AudioOptions:
    title: str
    author: str
    uri: str


@dataclass
class Image:
    width: int
    height: int
    url: str
    local_path: str = None
    aweme_id: Optional[str] = None
    duration: int = None
    file_type: str = None