"""全局配置。可改成 dotenv 或其他配置管理工具。"""
import os
from pathlib import Path
from dotenv import load_dotenv
import platform
import logging

log = logging.getLogger(__name__)

os_name = platform.system()

# 从 .env 读取配置
load_dotenv()

BASE_DIR = Path.cwd()

# —— 基本 ——
PROXY_SWITCH = 'Win' in os_name  # 代理开关

# —————————— TelegramBot配置 ——————————
MIN_MSG_INTERVAL = 3.0  # 2 秒只能发一次，速率限制
TELEGRAM_TOKEN_ENV = os.getenv('TELEGRAM_TOKEN', '')
log.debug(f"TELEGRAM_TOKEN={TELEGRAM_TOKEN_ENV[:10]}*********")
ADMIN_ID = 6040522700  # 管理员 TG ID
ALLOWED_USERS = {ADMIN_ID}  # 白名单用户，可扩展为数据库
GENERIC_HANDLER_UPLOAD_TIMEOUT = [35, 2]  # 主流程中上传超时
SEND_TEXT_TIMEOUT = [10, 1]
SEND_VIDEO_TIMEOUT = [35, 2]
SEND_MEDIA_GROUP_TIMEOUT = [20, 1]

# —————————— TelegramBot配置 ——————————


# —————————— 抖音配置 ——————————

DOWNLOAD_TIMEOUT = 20  # 多线程下载超时 时间
DOUYIN_DOWNLOAD_THREADS = 8  # 抖音下载线程
DOUYIN_SESSION_COUNTS = 3  # 多线程下载时session池数量
DOUYIN_SAVE_DIR = BASE_DIR / "dy_downloads"
# 超时 设置
DOUYIN_FETCH_IMAGE_TIMEOUT = 40  # 下载图集
DOUYIN_FETCH_VIDEO_TIMEOUT = 60  # 下载视频
DOUYIN_PARSE_IMAGE_TIMEOUT = [10, 3]  # 解析图集信息 [超时时间，重试次数]
DOUYIN_PARSE_VIDEO_TIMEOUT = [10, 3]  # 解析视频信息 [超时时间，重试次数]

# —————————— 抖音配置 ——————————


# —————————— B站配置 ——————————

BILI_SAVE_DIR = BASE_DIR / "bili_downloads"  # 保存路径
DEFAULT_DOWNLOAD_THREADS = 8  # 默认线程
BILI_COOKIE = {'SESSDATA': os.getenv('SESSDATA', '')}
log.debug(f"SESSDATA={BILI_COOKIE['SESSDATA'][:10]}*********")
BILI_PREVIEW_VIDEO_TITLE = "⚠️注意：该视频为私人视频或会员视频,仅提供预览片段"

# —————————— B站配置 ——————————

# —————————— 小红书 ——————————
XIAOHONGSHU_SAVE_DIR = BASE_DIR / "xhs_downloads"
XIAOHONGSHU_COOKIE = {'web_session': os.getenv('WEB_SESSION', '')}
log.debug(f"web_session={XIAOHONGSHU_COOKIE['web_session'][:10]}*********")
# —————————— 小红书 ——————————


# —————————— 网易云音乐配置 ——————————
MUSIC_SAVE_DIR = BASE_DIR / "music_downloads"
# —————————— 网易云音乐配置 ——————————


# —————————— 通用配置 ——————————
MAX_THREAD_WORKERS = 5  # download 线程池大小
EXCEPTION_MSG = "请检查链接或作品为私密状态.\n若有其他错误可反馈 @axlxlw"
EXCEPTION_MSG_TO_LOG = ""
# —————————— 通用配置 ——————————


for _p in (BILI_SAVE_DIR, DOUYIN_SAVE_DIR, MUSIC_SAVE_DIR):
    _p.mkdir(exist_ok=True)
