import json
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path

STATS_FILE = Path(__file__).with_name("user_stats.json")


@dataclass
class UserParseResult:
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
    fid: dict[str, str] = field(default_factory=dict)
    to_fid: bool = False


def _record_user_parse(info: UserParseResult):
    """
    将用户解析记录写入统计文件中，包含时间戳。
    """
    data = {}
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = {}

    user_key = str(info.uid)
    if user_key not in data:
        data[user_key] = {"records": []}

    # 如果该链接已记录过，不再重复添加
    if any(record["url"] == info.url for record in data[user_key]["records"]):
        if info.to_fid:
            # 更新记录
            data[user_key]["records"].append({
                "time": datetime.now().isoformat(),
                "to_fid": info.to_fid,
                "uname":info.uname,
                "full_name": info.full_name,
                "platform": info.platform,
                "vid": info.vid,
                "title": info.title,
                "fid": info.fid,
            })
    else:
        # 添加新记录
        data[user_key]["records"].append({
            "time": datetime.now().isoformat(),
            **asdict(info)
        })

    # 写回文件
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
