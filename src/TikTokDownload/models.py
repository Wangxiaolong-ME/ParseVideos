from typing import Optional, Dict, Any, List, Union
from dataclasses import dataclass, field


@dataclass
class TikTokMusicOption:
    """
    表示 TikTok 视频背景音乐的详细信息。
    """
    id: str
    title: str
    author_name: str
    url: Optional[str] = None
    cover_url: Optional[str] = None  # 音乐封面
    duration: int = 0  # 音乐时长 (秒)

    def to_dict(self) -> Dict[str, Any]:
        """将数据类实例转换为字典，方便JSON序列化。"""
        return {
            "id": self.id,
            "title": self.title,
            "author_name": self.author_name,
            "url": self.url,
            "cover_url": self.cover_url,
            "duration": self.duration,
        }


@dataclass
class TikTokImage:
    """
    表示 TikTok 图集中的单张图片信息。
    """
    url: str
    url_list: List[str] = field(default_factory=list)
    title: str = None
    width: int = 0
    height: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "url_list": self.url_list,
            "title": self.title,
            "width": self.width,
            "height": self.height
        }


@dataclass
class TikTokVideoOption:
    """
    表示 TikTok 视频文件（流）的详细信息，对应不同的分辨率和码率。
    这类似于 DouyinParser 中的 VideoOption。
    """
    aweme_id: str
    resolution: int
    bit_rate: int
    url: str
    size_mb: Optional[float] = None
    gear_name: Optional[str] = None  # 例如 "normal_720", "normal_1080"
    quality: Optional[str] = None  # 例如 "h264", "h265"
    height: int = 0
    width: int = 0
    duration: int = 0  # 视频文件本身的持续时间，可能与作品总时长略有不同
    ocr_content: str = ''

    def to_dict(self) -> Dict[str, Any]:
        """将数据类实例转换为字典。"""
        return {
            "aweme_id": self.aweme_id,
            "resolution": self.resolution,
            "bit_rate": self.bit_rate,
            "url": self.url,
            "size_mb": self.size_mb,
            "gear_name": self.gear_name,
            "quality": self.quality,
            "height": self.height,
            "width": self.width,
            "duration": self.duration
        }


@dataclass
class TikTokPost:
    """
    表示一个 TikTok 作品（视频或图集）的整体信息。
    """
    aweme_id: str  # 对应 aweme_id 或 item_id
    title: str
    description: str
    create_time: int  # Unix timestamp
    author_id: str
    author_nickname: str
    region: str = ""  # 作品发布区域，如 "US", "JP"
    video: List[TikTokVideoOption] = field(default_factory=list)  # 如果是视频，包含所有可用视频流
    images: List[Union[TikTokImage, TikTokVideoOption]] = field(default_factory=list)  # 如果是图集，包含所有图片也有可能图片视频混搭
    music: Optional[TikTokMusicOption] = None
    is_video: bool = False
    is_image_album: bool = False
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    share_count: Optional[int] = None
    hashtags: List[str] = field(default_factory=list)
    cover_image_url: Optional[str] = None  # 作品封面图

    def to_dict(self) -> Dict[str, Any]:
        """将数据类实例转换为字典，方便JSON序列化。"""
        return {
            "aweme_id": self.aweme_id,
            "title": self.title,
            "description": self.description,
            "create_time": self.create_time,
            "author_id": self.author_id,
            "author_nickname": self.author_nickname,
            "region": self.region,
            "video": [vf.to_dict() for vf in self.video],
            "images": [img.to_dict() for img in self.images],
            "music": self.music.to_dict() if self.music else None,
            "is_video": self.is_video,
            "is_image_album": self.is_image_album,
            "view_count": self.view_count,
            "like_count": self.like_count,
            "comment_count": self.comment_count,
            "share_count": self.share_count,
            "hashtags": self.hashtags,
            "cover_image_url": self.cover_image_url
        }
