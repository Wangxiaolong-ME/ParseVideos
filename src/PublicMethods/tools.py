import os


def check_file_size(file_path: str, max_size_mb: float = None, ndigits=2) -> bool | float:
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
