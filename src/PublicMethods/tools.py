import os
from pathlib import Path
from typing import Any, List, Optional, Union
from requests import PreparedRequest
from shlex import quote as sh

def check_file_size(file_path: str or Path, max_size_mb: float = None, ndigits=2) -> bool | float:
    """
    检查文件大小，是否超过指定限制。
    :param file_path: 文件路径
    :param max_size_mb: 最大文件大小，单位 MB
    :return: 如果文件大小小于等于 max_size_mb，则返回 True，否则返回 False
    """
    file_size = os.path.getsize(file_path) / (1024 * 1024)  # 转换为 MB
    if max_size_mb:
        return file_size <= max_size_mb
    else:
        return round(file_size, ndigits)


def prepared_to_curl(prep: PreparedRequest) -> str:
    """
    把 PreparedRequest 转换成等效 cURL 命令。
    Usage:
        resp = session.send(prep)
        print(prepared_to_curl(prep))
    """
    cmd = ["curl", "-X", prep.method]
    # headers
    for k, v in prep.headers.items():
        cmd += ["-H", sh(f"{k}: {v}")]
    # body
    if prep.body:
        cmd += ["--data-binary", sh(prep.body if isinstance(prep.body, str) else prep.body.decode())]
    cmd.append(sh(prep.url))
    return ' '.join(cmd)

# 嵌套JSON直取目标值
def collect_values(
    obj: Any,
    target_key: str,
    parent_path: str | None = None
) -> Optional[Union[Any, List[Any]]] or dict:
    """
    在嵌套 dict / list 结构中查找：
        • 父级键路径后缀 == parent_path（为空则忽略）
        • 且当前 dict 包含 target_key
    返回规则：
        • 0 个命中  → None
        • 1 个命中  → 单值，保持原始类型
        • ≥2 个命中 → 列表
    """
    path_parts = parent_path.split('.') if parent_path else []
    matches: List[Any] = []

    def dfs(node: Any, key_stack: List[str]) -> None:
        if isinstance(node, dict):
            # 满足父级路径条件时收集
            if (not path_parts or
                len(key_stack) >= len(path_parts) and
                key_stack[-len(path_parts):] == path_parts):
                if target_key in node:
                    matches.append(node[target_key])

            for k, v in node.items():
                dfs(v, key_stack + [k])

        elif isinstance(node, list):
            for item in node:
                dfs(item, key_stack)

    dfs(obj, [])

    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    return matches