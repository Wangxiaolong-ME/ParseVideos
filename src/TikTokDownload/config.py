# config.py
import os

# 下载时使用的HTTP请求头
# HTTP headers used for downloading
DOWNLOAD_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Linux; Android 8.0.0; SM-G955U Build/R16NW) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/138.0.0.0 Mobile Safari/537.36'
    ),
    'Referer': 'https://tiktok.com',
}

# 默认的视频保存目录
# Default directory for saving videos
MODULE_DIR = os.path.dirname(os.path.abspath(__file__))     # 当前config所在目录

# 代理配置(仅本地测试时开启)
TIKTOK_PROXY = {"server": "http://127.0.0.1:7890"}

TIKTOK_DEFAULT_SAVE_DIR = os.path.join(MODULE_DIR, 'tiktok_downloads')
TIKTOK_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
TIKTOK_DOWNLOAD_THREADS = 8
TIKTOK_SESSION_COUNTS = 4
TIKTOK_ITEM_DETAIL_API_URL = "https://www.tiktok.com/api/item/detail/"  # 示例API，实际可能需要动态获取


# Playwright 拦截API的超时时间 (毫秒)
# Timeout for Playwright API interception (in milliseconds)
PLAYWRIGHT_TIMEOUT = 15000

# 抖音作品详情API的URL特征
# URL feature for Douyin post detail API
IMAGE_DETAIL_API_URL = "/api/item/detail/"