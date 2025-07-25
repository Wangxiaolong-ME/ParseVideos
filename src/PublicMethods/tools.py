import os
from pathlib import Path

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