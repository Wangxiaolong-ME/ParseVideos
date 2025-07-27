from pathlib import Path
import logging
import json
import os

log = logging.getLogger(__name__)
# 主黑名单文件
BLACK_FILE = Path(__file__).with_name("blacklist.json")
# 备份及临时文件
BLACK_FILE_BAK = BLACK_FILE.with_stem(BLACK_FILE.stem + "_backup").with_suffix(".json")
BLACK_FILE_TMP = BLACK_FILE.with_stem(BLACK_FILE.stem + "_tmp").with_suffix(".json")


def load_blacklist() -> list[int]:
    """
    读取黑名单，失败或不存在时返回空列表。
    """
    if not BLACK_FILE.exists():
        return []

    try:
        with BLACK_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # 文件损坏或内容非法，按需做额外处理
        return []


def save_blacklist(data: list[int]) -> None:
    """
    安全写入黑名单：
    1. 如有旧文件，先备份到 *_backup.json
    2. 将数据写入 *_tmp.json 并 fsync 落盘
    3. 使用 os.replace 原子替换正式文件
    任何一步异常都会抛出，让上层决定是否回滚
    """
    # 确保目录存在
    BLACK_FILE.parent.mkdir(parents=True, exist_ok=True)

    # 写入前备份旧文件
    if BLACK_FILE.exists():
        with BLACK_FILE.open("rb") as src, BLACK_FILE_BAK.open("wb") as dst:
            dst.write(src.read())
            dst.flush()
            os.fsync(dst.fileno())  # 备份也保证落盘

    # 将新内容写到临时文件并刷新到磁盘
    with BLACK_FILE_TMP.open("w", encoding="utf-8") as f:
        json.dump(sorted(set(data)), f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())

    # 原子替换
    os.replace(BLACK_FILE_TMP, BLACK_FILE)