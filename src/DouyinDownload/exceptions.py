# exceptions.py
"""
定义项目专用的自定义异常类型。
Defines custom exception types for the project.
"""

class DouyinDownloadException(Exception):
    """项目所有异常的基类 (Base exception for the project)"""
    pass

class URLExtractionError(DouyinDownloadException):
    """无法从输入文本中提取有效的抖音URL (Failed to extract a valid Douyin URL)"""
    pass

class ParseError(DouyinDownloadException):
    """解析API响应失败或数据不完整 (Failed to parse API response or data is incomplete)"""
    pass

class DownloadError(DouyinDownloadException):
    """文件下载过程中发生错误 (An error occurred during file download)"""
    pass