"""全局配置。可改成 dotenv 或其他配置管理工具。"""
import os
from pathlib import Path
from dotenv import load_dotenv
import platform

os_name = platform.system()

# 从 .env 读取配置
load_dotenv()

# —— 基本 ——
PROXY_SWITCH = 'Win' in os_name  # 代理开关
TELEGRAM_TOKEN_ENV = os.getenv('TELEGRAM_TOKEN', '')
ADMIN_ID = 6040522700  # 管理员 TG ID
ALLOWED_USERS = {ADMIN_ID}  # 白名单用户，可扩展为数据库


BILI_COOKIE = {
    'SESSDATA': os.getenv('SESSDATA')
}


# —— 速率限制 ——
MIN_MSG_INTERVAL = 2.0  # 2 秒只能发一次
DEFAULT_DOWNLOAD_THREADS = 8    # 默认线程
DOUYIN_DOWNLOAD_THREADS = 4 # 抖音下载线程

# —— 任务控制 ——
MAX_THREAD_WORKERS = 4  # download 线程池大小

# —— 保存路径 (示例，可随意修改) ——
BASE_DIR = Path.cwd()
BILI_SAVE_DIR = BASE_DIR / "bili_downloads"

DOUYIN_SAVE_DIR = BASE_DIR / "dy_downloads"
MUSIC_SAVE_DIR = BASE_DIR / "music_downloads"

EXCEPTION_MSG = "出了点错误! 请稍候重试\n或将错误链接发送给 @axlxlw"

for _p in (BILI_SAVE_DIR, DOUYIN_SAVE_DIR, MUSIC_SAVE_DIR):
    _p.mkdir(exist_ok=True)

# 下载文件临时目录
DOWNLOAD_DIR = "./downloads"
