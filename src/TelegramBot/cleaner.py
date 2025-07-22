# src/TelegramBot/cleaner.py
from pathlib import Path
import time, logging, datetime

logger = logging.getLogger(__name__)

MAX_DIR_BYTES = 300 * 1024 * 1024          # 300 MB

def _fmt_size(bytes_: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if bytes_ < 1024:
            return f"{bytes_:.2f} {unit}"
        bytes_ /= 1024
    return f"{bytes_:.2f} PB"

def _fmt_ctime(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")

def purge_old_files(folder: Path, keep_hours: int = 2) -> list[str]:
    """
    1  先删 “最后修改时间超过 keep_hours 的普通文件”
    2  若删完后目录仍 >300 MB，则继续从最旧文件开始删，直到 ≤300 MB
    3  返回所有被删除的文件名列表
    """
    now = time.time()
    cutoff = keep_hours * 3600
    deleted: list[str] = []

    def _delete_file(file_path: Path):
        try:
            size = _fmt_size(file_path.stat().st_size)
            ctime = _fmt_ctime(file_path.stat().st_ctime)
            file_path.unlink()
            deleted.append(f"{ctime}  {file_path.name}  {size}")
            logger.info("🗑 删除 -> %s", file_path.name)
        except Exception as e:
            logger.warning("删除 %s 失败: %s", file_path, e)

    # ① 按时间阈值删
    for f in folder.iterdir():
        if not f.is_file() or f.suffix == ".part":
            continue
        if now - f.stat().st_mtime > cutoff:
            _delete_file(f)

    # ② 按容量清空
    total = sum(f.stat().st_size for f in folder.iterdir() if f.is_file())
    if total > MAX_DIR_BYTES:
        logger.warning("💾 目录占用 %.1f MB，执行整目录清空", total / 1_048_576)
        for f in folder.iterdir():
            if f.is_file() and f.suffix != ".part":
                _delete_file(f)

    return deleted