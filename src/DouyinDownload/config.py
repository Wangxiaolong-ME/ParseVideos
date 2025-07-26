# config.py
"""
该文件用于存放项目的所有配置和常量。
This file stores all configurations and constants for the project.
"""
import os

# 下载时使用的HTTP请求头
# HTTP headers used for downloading
DOWNLOAD_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Linux; Android 8.0.0; SM-G955U Build/R16NW) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/138.0.0.0 Mobile Safari/537.36'
    ),
    'Accept': '*/*',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Referer': 'https://www.douyin.com/',
}

# 默认的视频保存目录
# Default directory for saving videos
MODULE_DIR = os.path.dirname(os.path.abspath(__file__))     # 当前config所在目录
DEFAULT_SAVE_DIR = os.path.join(MODULE_DIR, 'video_downloads')

# 默认的分段下载并发线程数
# Default number of concurrent threads for segmented download
DEFAULT_DOWNLOAD_THREADS = 8
DOUYIN_DOWNLOAD_THREADS = 4

# Playwright 拦截API的超时时间 (毫秒)
# Timeout for Playwright API interception (in milliseconds)
PLAYWRIGHT_TIMEOUT = 15000

# 抖音作品详情API的URL特征
# URL feature for Douyin post detail API
AWEME_DETAIL_API_URL = "/aweme/v1/web/aweme/detail/"
# 图集网页所需Cookie字段，请求接口时校验
IMAGES_NEED_COOKIES = ['__ac_signature', '__ac_nonce']