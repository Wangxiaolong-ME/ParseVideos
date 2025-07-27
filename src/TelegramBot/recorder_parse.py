import json
import os
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
import logging
log = logging.getLogger(__name__)

STATS_FILE = Path(__file__).with_name("user_stats.json")
# 定义一个备份文件路径，用于在写入前备份原始数据
STATS_FILE_BAK = STATS_FILE.with_stem(STATS_FILE.stem + "_backup").with_suffix(".json")
# 定义一个临时文件路径，用于原子性写入
STATS_FILE_TMP = STATS_FILE.with_stem(STATS_FILE.stem + "_tmp").with_suffix(".json")


@dataclass
class UserParseResult:
    """
    表示一次用户解析操作的结果。保持与现有结构一致，无需修改。
    """
    uid: int
    uname: str = None
    full_name: str = None
    platform: str = None
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
    input_content: str = None


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
    input_content: str = None
    title: str or None = None  # 视频标题
    vid: str or None = None  # 视频ID
    url: str or None = None  # 原始请求URL
    parsed_url: str = None  # 解析后的URL (仅新解析成功时有)
    work_time_s: float = None
    size: float or int = None  # 视频大小 (仅新解析成功时有)
    is_cached_hit: bool = False  # 核心字段：是否命中缓存
    parse_success: bool = False  # 解析是否成功
    parse_exception: str = None  # 解析失败的异常信息
    cache_info: dict = field(default_factory=dict)  # 缓存相关信息，例如fid



def _record_user_parse(info: UserParseResult):
    """
    将用户解析记录写入统计文件中，包含时间戳。
    在函数内部根据 info.fid 字段判断是否为缓存命中，从而无需修改调用方。
    """
    log.debug(f"用户解析详情信息：{info.__dict__}")
    current_data = {}

    # 1. 尝试从主文件加载数据
    if STATS_FILE.exists():
        try:
            with open(STATS_FILE, 'r', encoding='utf-8') as f:
                current_data = json.load(f)
            log.debug(f"成功从主文件 '{STATS_FILE}' 加载数据。")
        except json.JSONDecodeError as e:
            log.error(f"警告: 统计文件 '{STATS_FILE}' 内容损坏或为空 ({e})。尝试从备份文件恢复。")
            # 如果主文件损坏，尝试从备份文件恢复
            if STATS_FILE_BAK.exists():
                try:
                    with open(STATS_FILE_BAK, 'r', encoding='utf-8') as f_bak:
                        current_data = json.load(f_bak)
                    log.info(f"成功从备份文件 '{STATS_FILE_BAK}' 恢复数据。")
                except json.JSONDecodeError as e_bak:
                    log.error(f"严重错误: 备份文件 '{STATS_FILE_BAK}' 也损坏 ({e_bak})。将从空记录开始，数据可能丢失！")
                    current_data = {}  # 备份也损坏，只能从空开始
                except Exception as e_bak:
                    log.error(f"读取备份文件时发生未知错误: {e_bak}。将从空记录开始。")
                    current_data = {}
            else:
                log.warning(f"没有找到备份文件 '{STATS_FILE_BAK}'。将从空记录开始，数据可能丢失。")
                current_data = {}  # 没有备份文件，只能从空开始
        except Exception as e:
            log.error(f"读取主文件 '{STATS_FILE}' 时发生未知错误: {e}。将从空记录开始。")
            current_data = {}

    user_key = str(info.uid)
    if user_key not in current_data:
        current_data[user_key] = {"records": []}

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

    if is_cached_hit:
        # 缓存命中时，**只**包含这些你需要的字段
        record_data = {
            "timestamp": datetime.now().isoformat(),
            "uid": info.uid,  # 根据之前的逻辑，UID 是每个记录的基础标识，保留
            "uname": info.uname,
            "full_name": info.full_name,
            "input_content": info.input_content,
            "title": info.title,
            "platform": info.platform,
            "cache_info": info.fid,
            "is_cached_hit": True,
            "parse_success": info.success,
            "work_time_s": work_time_s,
        }
    else:
        # 非缓存命中（新解析）时，构建完整记录
        record_data = {
            "timestamp": datetime.now().isoformat(),
            "uid": info.uid,
            "uname": info.uname,
            "full_name": info.full_name,
            "platform": info.platform,
            "input_content": info.input_content,
            "url": info.url,
            "vid": info.vid,
            "title": info.title,
            "is_cached_hit": False,
            "parse_success": info.success,
            "parse_exception": str(info.exception),
            "size": info.size if info.success else None,
            "parsed_url": info.parsed_url if info.success else None,
            "work_time_s": work_time_s,
            "cache_info": {},  # 非缓存命中时记录空字典
        }

    record_entry = UserRecordEntry(**record_data)

    """ 管他命不命中的, 只要发起解析了就记录 """
    # # 对于缓存命中，即使 vid 相同也应该记录，因为每次命中都是一次新的统计事件
    # if not is_cached_hit:  # 如果是新视频解析 (即 info.fid 为空)
    #     # 只有当 info.vid 不为 None 且存在重复时才跳过
    #     if info.vid is not None and any(rec.get("vid") == info.vid and not rec.get("is_cached_hit") for rec in
    #                                     current_data[user_key]["records"]):
    #         log.warning(f"检测到重复的新视频记录 (VID: {info.vid})，跳过追加。")
    #         return  # 避免重复记录新视频

    # 追加记录
    current_data[user_key]["records"].append(asdict(record_entry))

    # 2. 原子性写入：先写入临时文件
    try:
        with open(STATS_FILE_TMP, 'w', encoding='utf-8') as f_tmp:
            json.dump(current_data, f_tmp, ensure_ascii=False, indent=2)
        log.debug(f"数据成功写入临时文件 '{STATS_FILE_TMP.name}'。")
    except Exception as e:
        log.error(f"写入临时文件 '{STATS_FILE_TMP}' 时发生错误: {e}。本次记录将失败，且主文件未被修改。")
        # 写入临时文件失败，直接返回，不影响主文件
        return

    # 3. 替换主文件：先备份，再移动
    try:
        if STATS_FILE.exists():
            # 先将现有主文件备份
            os.replace(STATS_FILE, STATS_FILE_BAK)
            log.debug(f"主文件 '{STATS_FILE.name}' 已备份至 '{STATS_FILE_BAK}'。")

        # 将临时文件重命名为 STATS_FILE，这是原子操作
        os.replace(STATS_FILE_TMP, STATS_FILE)
        log.debug(f"用户解析记录成功保存到 '{STATS_FILE.name}'。")

        log.info(f"record user parsed info success.")
        # 理论上可以删除备份文件，但为了更高的安全性，可以保留备份文件作为历史快照
        # os.remove(STATS_FILE_BAK)
        # log.debug(f"备份文件 '{STATS_FILE_BAK}' 已删除。")

    except Exception as e:
        log.error(
            f"执行原子性文件替换时发生错误: {e}。数据可能处于不一致状态，请检查 '{STATS_FILE}' 和 '{STATS_FILE_BAK}'。")
        # 这种情况下，可能需要人工介入检查文件状态
        # 主文件可能已经损坏或丢失，但至少备份文件可能还在


def load_users() -> dict[int, dict]:
    """加载所有用户的 ID、用户名和全名"""
    if not os.path.exists(STATS_FILE):
        return {}

    with open(STATS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 返回一个字典，键是用户的 UID，值是包含 uname 和 full_name 的字典
    users = {
        int(uid): {
            'uname': user_info.get('records', [])[0].get('uname', ''),
            'full_name': user_info.get('records', [])[0].get('full_name', '')
        }
        for uid, user_info in data.items()
    }

    return users