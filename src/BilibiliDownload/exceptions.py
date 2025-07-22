# exceptions.py
"""
Bilibili 下载模块异常定义。
"""

class BilibiliDownloadException(Exception):
    """所有 Bilibili 下载相关异常基类"""
    pass

class BilibiliParseError(BilibiliDownloadException):
    """解析 Bilibili 页面或数据格式异常"""
    pass

class BilibiliDownloadError(BilibiliDownloadException):
    """文件下载过程异常"""
    pass
