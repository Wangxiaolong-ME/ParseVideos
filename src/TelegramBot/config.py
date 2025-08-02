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
SEND_TEXT_TIMEOUT = [10, 2]
SEND_VIDEO_TIMEOUT = [60, 2]
SEND_MEDIA_GROUP_TIMEOUT = [20, 2]
USAGE_TEXT = "使用方法: 发送视频链接开始使用\n例：https://v.douyin.com/7kSRzFPFob4/"
LESS_FLAG = "Downloaded via:\n@IntelligentAxlxlbot"
# —————————— TelegramBot配置 ——————————

# —————————— 通用配置 ——————————
ENABLE_CACHE = False    # 是否开启缓存机制,历史解析过的会被记录在缓存当中,命中会直接从缓存拉取发送
MAX_THREAD_WORKERS = 5  # download 线程池大小
EXCEPTION_MSG = "解析失败,请检查链接或作品为私密状态."
EXCEPTION_MSG_TO_LOG = ""
IMAGES_CACHE_SWITCH = False     # 图集走缓存策略开关
PREVIEW_SIZE = 20  # 预览视频大小优先选取
# EXCLUDE_RESOLUTION = [1440, 2160]   # 上传排除的分辨率
EXCLUDE_RESOLUTION = None   # 上传排除的分辨率
PROMPT_WORD = "总结内容,罗列清晰,不要回复其余无关话术,内容不要有markdown格式,纯文本;总结包括大三要素:核心摘要,关键论点,结论."
# —————————— 通用配置 ——————————


# —————————— 抖音配置 ——————————

DOWNLOAD_TIMEOUT = 20  # 多线程下载超时 时间
DOUYIN_DOWNLOAD_THREADS = 8  # 抖音下载线程
DOUYIN_SESSION_COUNTS = 3  # 多线程下载时session池数量
DOUYIN_SAVE_DIR = BASE_DIR / "dy_downloads"
# 超时 设置
DOUYIN_FETCH_IMAGE_TIMEOUT = 40  # 下载图集
DOUYIN_FETCH_VIDEO_TIMEOUT = 60  # 下载视频
DOUYIN_PARSE_IMAGE_TIMEOUT = [30, 3]  # 解析图集信息 [超时时间，重试次数]
DOUYIN_PARSE_VIDEO_TIMEOUT = [30, 3]  # 解析视频信息 [超时时间，重试次数]
DOUYIN_OVER_SIZE = "⚠️注意：视频体积超50M无法上传, 请选择下方分辨率点击下载"
# —————————— 抖音配置 ——————————

# —————————— TikTok配置 ——————————
TIKTOK_NEEDS_QUALITY_SELECTION_SWITCH = False   # 是否走分辨率选项规则发送,目前不走,因为CDN下载直链有有效期,发了也没用打开看不了
TIKTOK_DOWNLOAD_TIMEOUT = 20  # 多线程下载超时 时间
TIKTOK_SAVE_DIR = BASE_DIR / "tiktok_downloads"
# 超时 设置
TIKTOK_FETCH_IMAGE_TIMEOUT = 40  # 下载图集
TIKTOK_FETCH_VIDEO_TIMEOUT = 60  # 下载视频
TIKTOK_PARSE_IMAGE_TIMEOUT = [20, 3]  # 解析图集信息 [超时时间，重试次数]
TIKTOK_PARSE_VIDEO_TIMEOUT = [20, 3]  # 解析视频信息 [超时时间，重试次数]
TIKTOK_OVER_SIZE = "⚠️注意：视频体积超50M无法上传, 请选择下方分辨率点击下载"
# —————————— TikTok配置 ——————————




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
XIAOHONGSHU_OVER_SIZE = "⚠️注意：视频体积超过50M无法发送"
# —————————— 小红书 ——————————


# —————————— 网易云音乐配置 ——————————
MUSIC_SAVE_DIR = BASE_DIR / "music_downloads"
# —————————— 网易云音乐配置 ——————————


for _p in (BILI_SAVE_DIR, DOUYIN_SAVE_DIR, MUSIC_SAVE_DIR):
    _p.mkdir(exist_ok=True)
