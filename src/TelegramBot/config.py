"""全局配置。可改成 dotenv 或其他配置管理工具。"""
import os
from pathlib import Path
from dotenv import load_dotenv
import platform

os_name = platform.system()

# 从 .env 读取配置
load_dotenv()

BASE_DIR = Path.cwd()

# —— 基本 ——
PROXY_SWITCH = 'Win' in os_name  # 代理开关

# —————————— TelegramBot配置 ——————————
MIN_MSG_INTERVAL = 2.0  # 2 秒只能发一次，速率限制
TELEGRAM_TOKEN_ENV = os.getenv('TELEGRAM_TOKEN', '')
ADMIN_ID = 6040522700  # 管理员 TG ID
ALLOWED_USERS = {ADMIN_ID}  # 白名单用户，可扩展为数据库
# —————————— TelegramBot配置 ——————————


# —————————— 抖音配置 ——————————

DOWNLOAD_TIMEOUT = 20  # 多线程下载超时 时间
DOUYIN_DOWNLOAD_THREADS = 8  # 抖音下载线程
DOUYIN_SAVE_DIR = BASE_DIR / "dy_downloads"

# —————————— 抖音配置 ——————————


# —————————— B站配置 ——————————

BILI_SAVE_DIR = BASE_DIR / "bili_downloads"  # 保存路径
DEFAULT_DOWNLOAD_THREADS = 8  # 默认线程
BILI_COOKIE = {'SESSDATA': os.getenv('SESSDATA')}

# —————————— B站配置 ——————————


# —————————— 网易云音乐配置 ——————————
MUSIC_SAVE_DIR = BASE_DIR / "music_downloads"
# —————————— 网易云音乐配置 ——————————


# —————————— 通用配置 ——————————
MAX_THREAD_WORKERS = 4  # download 线程池大小
EXCEPTION_MSG = "出了点错误! 请稍候重试\n或将错误链接发送给 @axlxlw"
EXCEPTION_MSG_TO_LOG = ""
# —————————— 通用配置 ——————————


for _p in (BILI_SAVE_DIR, DOUYIN_SAVE_DIR, MUSIC_SAVE_DIR):
    _p.mkdir(exist_ok=True)
