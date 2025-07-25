# src/TelegramBot/cleaner.py
from pathlib import Path
import time, logging, datetime

logger = logging.getLogger(__name__)

MAX_DIR_BYTES = 300 * 1024 * 1024  # 300 MB


def _fmt_size(bytes_: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if bytes_ < 1024:
            return f"{bytes_:.2f} {unit}"
        bytes_ /= 1024
    return f"{bytes_:.2f} PB"


def _fmt_ctime(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def purge_old_files(folder: Path, max_dir_mb: float, lower_limit: float) -> float:
    """
    超出 max_dir_mb 时，从最旧文件开始删，直到目录大小 ≤ 阈值。
    返回清理的空间大小（MB）。
    """
    if not folder.exists() or not folder.is_dir():
        logger.warning("目录不存在或不是文件夹，跳过清理：%s", folder)
        return 0.0

    # 列出待清理文件（排除 .part 临时文件）
    files = [f for f in folder.iterdir() if f.is_file() and f.suffix != ".part"]
    total_mb = sum(f.stat().st_size for f in files) / 1024 ** 2
    if total_mb <= max_dir_mb:
        return 0.0  # 未超阈值，无需清理

    # 按修改时间升序（最旧的先删）
    files.sort(key=lambda f: f.stat().st_mtime)
    logger.warning("目录占用 %.1f MB，开始按最旧顺序清理至 %.1f MB", total_mb, lower_limit)

    freed_mb = 0.0
    for f in files:
        size_mb = f.stat().st_size / 1024 ** 2
        try:
            f.unlink()
            freed_mb += size_mb
            logger.warning(" 删除旧文件 -> %s (%.2f MB)", f.name, size_mb)
        except Exception as e:
            logger.error("删除 %s 失败: %s", f, e)
        total_mb -= size_mb
        if total_mb <= lower_limit:
            break

    return freed_mb
