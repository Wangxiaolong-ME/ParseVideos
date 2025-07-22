#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本功能：通过官方 JSON 接口获取网易云歌单的全部歌曲 ID，
并拼接成完整的歌曲 URL 列表（优先使用 trackIds 字段保证全量）。
用法：python fetch_ncm_playlist_full.py <playlist_id>
"""

import sys
import requests

def fetch_song_urls_via_api(playlist_id):
    base_url = 'https://music.163.com'
    # v6 版本接口，返回 playlist.trackIds（全量）以及 playlist.tracks（前10条）
    api_url = f'{base_url}/api/v6/playlist/detail'
    params = {'id': playlist_id, 'n': 1000, 'csrf_token': ''}
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/96.0.4664.45 Safari/537.36'
        ),
        'Referer': base_url
    }

    resp = requests.get(api_url, params=params, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    # —— 新增：处理私密歌单错误 ——
    if data.get("code") == 401:
        # message 字段里会有“该歌单已被创建者设置为隐私”
        raise RuntimeError(f"无法访问歌单 {playlist_id}：{data.get('message')}")

    # 1) 优先取完整的 trackIds 列表
    if 'playlist' in data and 'trackIds' in data['playlist']:
        id_list = [item['id'] for item in data['playlist']['trackIds']]
    elif 'result' in data and 'trackIds' in data['result']:
        id_list = [item['id'] for item in data['result']['trackIds']]
    # 2) 回退到前 10 条的 tracks 列表
    elif 'playlist' in data and 'tracks' in data['playlist']:
        id_list = [track['id'] for track in data['playlist']['tracks']]
    elif 'result' in data and 'tracks' in data['result']:
        id_list = [track['id'] for track in data['result']['tracks']]
    else:
        raise RuntimeError(
            '接口返回格式异常，未找到 trackIds 或 tracks 字段。'
        )

    # 拼接完整 URL
    return [f"{base_url}/song?id={sid}" for sid in id_list]


def main():
    # 直接在此处指定要抓取的歌单 ID
    playlist_id = '8794488756'

    try:
        urls = fetch_song_urls_via_api(playlist_id)
        print(f'共找到 {len(urls)} 首歌曲：')

        # 将每行链接写入 song_urls.txt
        with open('song_urls.txt', 'w', encoding='utf-8') as wf:
            for u in urls:
                print(u)
                wf.write(u + '\n')

    except Exception as e:
        print(f'错误：{e}')


if __name__ == '__main__':
    main()
