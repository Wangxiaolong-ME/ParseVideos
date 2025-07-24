# TelegramBot/file_cache.py
"""
把 <key, file_id> 存到磁盘 (JSON)，Bot 重启后仍可秒回。
默认存到 TelegramBot/file_id_cache.json
"""
import json, atexit
import logging
from pathlib import Path
logger = logging.getLogger(__name__)

CACHE_FILE = Path(__file__).with_name("file_id_cache.json")
_cache: dict[str, str] = {}

def load() -> None:
    global _cache
    if CACHE_FILE.exists():
        try:
            _cache = json.loads(CACHE_FILE.read_text("utf-8"))
        except Exception:
            _cache = {}

def save() -> None:
    try:
        CACHE_FILE.write_text(json.dumps(_cache, ensure_ascii=False), "utf-8")
        logger.info(f"save cache success.")
    except Exception:
        pass                               # 避免影响主流程

def get(key: str) -> str | None:
    logger.debug(f"get cache:{_cache.get(key)}")
    return _cache.get(key)

def put(key: str, file_id: str) -> None:
    if not file_id:
        logger.error("cache file_id = None! skip.")
        return
    _cache[key] = file_id
    logger.debug(f"put cache:_cache[key] = {file_id}")
    save()

# 启动时自动加载，退出前自动保存
load()
atexit.register(save)