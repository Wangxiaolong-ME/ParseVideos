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

logger = logging.getLogger(__name__)

CACHE_FILE = Path(__file__).with_name("file_id_cache.json")
_cache: dict[str, str] = {}


def load() -> None:
    global _cache
    if CACHE_FILE.exists():
        try:
            _cache = json.loads(CACHE_FILE.read_text("utf-8"))
        except Exception:
            logger.error("加载缓存失败，使用空缓存。", exc_info=True)
            _cache = {}


def save() -> None:
    """
    先写入到同目录下的临时文件，写入成功后再用 os.replace 原子替换掉旧文件。
    任何异常都不会影响到已有的 CACHE_FILE。
    """
    try:
        # 创建临时文件
        dir_ = CACHE_FILE.parent
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=dir_, delete=False
        ) as tf:
            json.dump(_cache, tf, ensure_ascii=False)
            tf.flush()
            os.fsync(tf.fileno())
            tmp_path = Path(tf.name)

        # 原子替换
        os.replace(str(tmp_path), str(CACHE_FILE))
        logger.info("save cache success.")
    except Exception:
        logger.error("保存缓存失败，保留旧文件不变。", exc_info=True)
        # 如果临时文件还存在，尝试清理
        try:
            if 'tmp_path' in locals() and tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass


def get(key: str) -> str or list | None:
    logger.debug(f"get cache:{_cache.get(key)}")
    return _cache.get(key)


def put(key: str, file_id: str or list) -> None:
    if not file_id:
        logger.error("cache file_id = None! skip.")
        return
    _cache[key] = file_id
    logger.debug(f"put cache:_cache[key] = {file_id}")
    save()


def peek(key: str) -> str | list | None:
    """只读获取指定 key 对应的缓存内容，不触发写入。"""
    return _cache.get(key)


def keys() -> list[str]:
    """返回当前缓存中的全部 key（列表拷贝，避免外部修改）。"""
    return list(_cache.keys())


def delete(key: str) -> bool:
    """
    删除指定 key 的缓存条目。
    返回 True 表示删除成功，False 表示 key 不存在。
    """
    if key in _cache:
        _cache.pop(key, None)
        save()  # 立即持久化到磁盘
        logger.info("delete cache success: %s", key)
        return True
    logger.warning("delete cache failed, key not found: %s", key)
    return False


# 启动时自动加载，退出前自动保存
load()
atexit.register(save)
