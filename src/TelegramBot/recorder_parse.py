import json
import os
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
import logging
log = logging.getLogger(__name__)

STATS_FILE = Path(__file__).with_name("user_stats.json")


@dataclass
class UserParseResult:
    """
    表示一次用户解析操作的结果。保持与现有结构一致，无需修改。
    """
    uid: int
    uname: str = None
    full_name: str = None
    platform: str or None = None
    url: str or None = None
    vid: str or None = None
    title: str or None = None
    size: float or int = None
    parsed_url: str or None = None
    success: bool = False
    exception: str or None = None
    fid: dict[str, str] = field(default_factory=dict)  # 缓存ID信息
    to_fid: bool = False  # 现有字段，虽然在新逻辑中不再直接用于判断，但保留以保持兼容性
    start_time: float = None


@dataclass
class UserRecordEntry:
    """
    表示单个用户操作的统计记录。新增此结构以标准化统计数据。
    """
    timestamp: str  # ISO格式的时间戳
    uid: int  # 用户ID
    uname: str = None  # 用户名
    full_name: str = None  # 用户全名
    platform: str or None = None  # 平台名称
    url: str or None = None  # 原始请求URL
    vid: str or None = None  # 视频ID
    title: str or None = None  # 视频标题
    work_time_s: float = None
    is_cached_hit: bool = False  # 核心字段：是否命中缓存
    cache_info: dict = field(default_factory=dict)  # 缓存相关信息，例如fid
    parse_success: bool = False  # 解析是否成功
    parse_exception: str = None  # 解析失败的异常信息
    size: float or int = None  # 视频大小 (仅新解析成功时有)
    parsed_url: str = None  # 解析后的URL (仅新解析成功时有)



def _record_user_parse(info: UserParseResult):
    """
    将用户解析记录写入统计文件中，包含时间戳。
    在函数内部根据 info.fid 字段判断是否为缓存命中，从而无需修改调用方。
    """
    data = {}
    if STATS_FILE.exists():
        try:
            with open(STATS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError:
            print(f"警告: 统计文件 '{STATS_FILE}' 内容损坏或为空，将初始化空记录。")
            data = {}
        except Exception as e:
            print(f"读取统计文件时发生错误: {e}。将初始化空记录。")
            data = {}

    user_key = str(info.uid)
    if user_key not in data:
        data[user_key] = {"records": []}

    # 核心改动：在函数内部判断是否为缓存命中
    # 如果 info.fid 不为空，则认为是缓存命中
    is_cached_hit = bool(info.fid)

    # 计算操作耗时（秒，保留两位小数）
    work_time_s = None
    if info.start_time is not None:
        raw_duration = time.perf_counter() - info.start_time
        if raw_duration < 0:
            work_time_s = 0.0
        elif raw_duration > 3600.0:  # 假设最大耗时1小时（秒），防止异常值
            work_time_s = None
        else:
            work_time_s = round(raw_duration, 2)  # 四舍五入到两位小数

    # 构建统计记录条目
    record_entry = UserRecordEntry(
        timestamp=datetime.now().isoformat(),
        uid=info.uid,
        uname=info.uname,
        full_name=info.full_name,
        platform=info.platform,
        url=info.url,  # 原始请求URL，对于缓存命中和新解析都存在
        vid=info.vid,
        title=info.title,
        is_cached_hit=is_cached_hit,
        cache_info=info.fid if is_cached_hit else {},  # 仅缓存命中时记录fid
        parse_success=info.success,
        parse_exception=info.exception,
        # 只有新解析成功时才记录大小和解析URL
        size=info.size if not is_cached_hit and info.success else None,
        parsed_url=info.parsed_url if not is_cached_hit and info.success else None,
        work_time_s=work_time_s,
    )

    # 对于新视频（非缓存命中），可以考虑去重逻辑
    # 对于缓存命中，即使 vid 相同也应该记录，因为每次命中都是一次新的统计事件
    if not is_cached_hit:  # 如果是新视频解析 (即 info.fid 为空)
        # 假设我们不希望重复记录同一个 vid 的新解析成功事件
        # 您可以根据实际需求调整这里的去重策略
        if any(rec.get("vid") == info.vid and not rec.get("is_cached_hit") for rec in data[user_key]["records"]):
            print(f"检测到重复的新视频记录 (VID: {info.vid})，跳过追加。")
            return  # 避免重复记录新视频

    # 追加记录
    data[user_key]["records"].append(asdict(record_entry))

    # 写回文件
    try:
        with open(STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        log.info(f"record user parsed info success.")
    except Exception as e:
        print(f"写入统计文件时发生错误: {e}")