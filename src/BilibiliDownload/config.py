# config.py
"""
默认配置：保存目录、合并目录、HTTP 请求头等。
"""
import os

# 默认视频保存目录
MODULE_DIR = os.path.dirname(os.path.abspath(__file__))     # 当前config所在目录
DEFAULT_SAVE_DIR = os.path.join(MODULE_DIR, 'bilibili_downloads')
# DEFAULT_SAVE_DIR = os.getenv('BILIBILI_SAVE_DIR', './DEFAULT_SAVE_DIR')

# 默认合并输出目录
DEFAULT_MERGE_DIR = os.path.join(MODULE_DIR, 'bilibili_merged')
# DEFAULT_MERGE_DIR = os.getenv('BILIBILI_MERGE_DIR', './bilibili_merged')

# 默认请求头
DEFAULT_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
        ' AppleWebKit/537.36 (KHTML, like Gecko)'
        ' Chrome/91.0.4472.124 Safari/537.36'
    ),
    'Referer': 'https://www.bilibili.com/',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}

# 确保目录存在
os.makedirs(DEFAULT_SAVE_DIR, exist_ok=True)
os.makedirs(DEFAULT_MERGE_DIR, exist_ok=True)

