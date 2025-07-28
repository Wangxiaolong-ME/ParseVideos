# TelegramBot/file_cache.py
"""
把 <key, file_id> 存到磁盘 (JSON)，Bot 重启后仍可秒回。
默认存到 TelegramBot/file_id_cache.json
"""
import json
import atexit
import logging
from pathlib import Path
import tempfile
import os
from typing import Union, List, Dict, Any

logger = logging.getLogger(__name__)

CACHE_FILE = Path(__file__).with_name("file_id_cache.json")
# 统一的内部类型：dict[str, dict(title:str, value:str|list)]
_cache: Dict[str, Dict[str, Union[str, List[str]]]] = {}
_DEFAULT_TITLE = ""  # 目前暂时为空，可按需修改


# ───────────────────────── 内部辅助 ──────────────────────────
def _normalize_entry(raw: Any) -> Dict[str, Union[str, List[str]]]:
    """
    把磁盘读出的旧格式（str / list）或新格式统一转换成
    {"title": str, "value": str|list} 结构。
    """
    # 新格式
    if isinstance(raw, dict) and "value" in raw:
        title = raw.get("title", _DEFAULT_TITLE)
        return {"title": title, "value": raw["value"]}
    # 旧格式：直接是字符串或列表
    return {"title": _DEFAULT_TITLE, "value": raw}


# ───────────────────────── I/O ──────────────────────────
def load() -> None:
    global _cache
    if CACHE_FILE.exists():
        try:
            raw_cache = json.loads(CACHE_FILE.read_text("utf-8"))
            if not isinstance(raw_cache, dict):
                raise ValueError("cache file root must be dict")
            _cache = {k: _normalize_entry(v) for k, v in raw_cache.items()}
        except Exception:
            logger.error("加载缓存失败，使用空缓存。", exc_info=True)
            _cache = {}


def _atomic_write(data: str) -> Path:
    """原子性写入，防止写坏文件。"""
    dir_ = CACHE_FILE.parent
    with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=dir_, delete=False
    ) as tf:
        tf.write(data)
        tf.flush()
        os.fsync(tf.fileno())
        tmp_path = Path(tf.name)
    os.replace(str(tmp_path), str(CACHE_FILE))
    return tmp_path


def save() -> None:
    """
    先写入到同目录下的临时文件，写入成功后再用 os.replace 原子替换旧文件。
    """
    tmp_path: Path | None = None
    try:
        tmp_path = _atomic_write(json.dumps(_cache, ensure_ascii=False))
        logger.info("save cache success.")
    except Exception:
        logger.error("保存缓存失败，保留旧文件不变。", exc_info=True)
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass


# ───────────────────────── 公共 API ──────────────────────────
def get(key: str) -> Union[str, List[str], None]:
    """
    返回指定 key 的 value（向后兼容旧用法）。
    """
    entry = _cache.get(key)
    return None if entry is None else entry["value"]


def peek(key: str) -> Union[str, List[str], None]:
    """同 get，保持别名。"""
    return get(key)


def keys() -> List[str]:
    """返回全部 key（列表拷贝，避免外部修改）。"""
    return list(_cache.keys())


def put(key: str, file_id: Union[str, List[str]], *, title: str | None = None) -> None:
    """
    插入 / 更新缓存。保持旧签名兼容：旧代码仍可调用 put(key, file_id)。
    新增可选参数 title（不传则保持之前的 title 或默认空）。
    """
    if not file_id:
        logger.error("cache file_id = None! skip.")
        return

    if key in _cache:
        # 保留旧 title，除非显式传入
        entry = _cache[key]
        entry["value"] = file_id
        if title is not None:
            entry["title"] = title
    else:
        _cache[key] = {"title": title or _DEFAULT_TITLE, "value": file_id}

    logger.debug("put cache: %s → %s", key, _cache[key])
    save()


def delete(key: str) -> bool:
    """
    删除指定 key 的缓存条目。
    返回 True 表示删除成功，False 表示 key 不存在。
    """
    if key in _cache:
        _cache.pop(key, None)
        save()  # 立即持久化
        logger.info("delete cache success: %s", key)
        return True
    logger.warning("delete cache failed, key not found: %s", key)
    return False


def get_title(key: str) -> str | None:
    """返回指定 key 的 title，供日后需要时使用。"""
    entry = _cache.get(key)
    title = entry.get("title", "")
    var = title.replace("\n", "")[:20]
    return var


def key_title_pairs() -> list[tuple[str, str]]:
    """
    返回 [(key, title), …]，保持插入顺序。
    方便上层做“ID  title” 一行一个的展示。
    """
    return [(k, v.get("title", "")) for k, v in _cache.items()]


# ───────────────────────── 启动 & 退出挂钩 ──────────────────────────
load()
atexit.register(save)
