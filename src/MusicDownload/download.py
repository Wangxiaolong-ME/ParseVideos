"""
脚本功能：自动下载网易云资源，支持批量下载歌单或单首下载。
结合 fetch_music_list.py 与 download.py，并支持命令行与代码调用两种方式。
下载的文件以歌曲名命名。
"""
import os
import re
import argparse

import requests

from MusicDownload.fetch_music_list import fetch_song_urls_via_api
from MusicDownload.download_music import get_download_link, download_file
from PublicMethods.logger import setup_log, get_logger
setup_log(log_name="Music")
log = get_logger(__name__)

def extract_id(input_str, *, item_type):
    """
    从任意文本中提取歌单或单曲 ID。
    支持：
      - 纯数字 ID
      - 标准 URL（如 https://music.163.com/song?id=xxx）
      - 手机短链（如 http://163cn.tv/HdAPCIk）
      - 文本中包含上述任意一种形式
    """
    # 1) 先在全文中查找 163cn.tv 短链
    m_short = re.search(r'https?://163cn\.tv/[A-Za-z0-9]+', input_str)
    if m_short:
        short_url = m_short.group(0)
        # 跟随跳转
        resp = requests.get(short_url, allow_redirects=True, timeout=5)
        real_url = resp.url
        log.debug(f"[DEBUG] 短链跳转到: {real_url}")
        input_str = real_url

    # 2) 再在文本中查找标准 URL
    m_url = re.search(r'https?://music\.163\.com/(?:#/)?.*?[?&]id=(\d+)', input_str)
    if m_url:
        return m_url.group(1)

    # 3) 最后看是否纯数字
    m_num = re.search(r'(?<!\d)(\d{5,})(?!\d)', input_str)
    if m_num:
        return m_num.group(1)

    raise ValueError(f"无法从输入中提取{item_type} ID: {input_str}")


def download_playlist(playlist_input, limit=None, output_dir='downloads'):
    """
    批量下载歌单。
    参数 playlist_input: 歌单 ID 或 URL。
    """
    pid = extract_id(playlist_input, item_type='playlist')
    log.debug(f"获取歌单ID {pid}...")
    urls = fetch_song_urls_via_api(pid)
    log.debug(f"歌单下共找到歌曲数量： {len(urls)} songs")
    if limit is not None:
        urls = urls[:limit]
        log.debug(f"此次下载数量： {len(urls)} songs")
    os.makedirs(output_dir, exist_ok=True)
    for idx, page_url in enumerate(urls, 1):
        try:
            real_url, song_name = get_download_link(page_url)
            log.debug(f"[{idx}/{len(urls)}] {song_name}")
            saved = download_file(real_url, song_name, output_dir)
            log.debug(f"\tSaved: {saved}")
        except Exception as e:
            log.debug(f"\tError: {e}")
    log.debug("Playlist download complete.")


def download_single(single_input, output_dir='downloads'):
    """
    下载单曲。
    参数 single_input: 单曲 ID 或 URL。
    """
    sid = extract_id(single_input, item_type='song')
    page_url = f"https://music.163.com/song?id={sid}"
    real_url, song_name = get_download_link(page_url)
    log.debug(f"Downloading: {song_name}")
    os.makedirs(output_dir, exist_ok=True)
    saved = download_file(real_url, song_name, output_dir)
    log.debug(f"Saved: {saved}")
    log.debug("Single download complete.")


def main():
    parser = argparse.ArgumentParser(description="下载歌单或单曲，ID 或 URL 均可。")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-p','--playlist', help='歌单 ID 或 URL')
    group.add_argument('-s','--song',     help='单曲 ID 或 URL')
    parser.add_argument('-n','--limit',    type=int, default=None,
                        help='歌单下载数量限制')
    parser.add_argument('-o','--output-dir', default='downloads',
                        help='保存目录')
    args = parser.parse_args()
    if args.playlist:
        download_playlist(args.playlist, args.limit, args.output_dir)
    else:
        download_single(args.song, args.output_dir)

if __name__=='__main__':
    main()