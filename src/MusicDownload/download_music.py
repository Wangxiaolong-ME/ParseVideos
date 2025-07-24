#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本功能：批量通过 toubiec.cn API（使用您提供的静态 header/body Token）
获取网易云单曲真实下载链接（带 vuutv 参数），并写入 music_url.txt。
如需下载 MP3，可取消 download_file 调用的注释。
"""

import os
import re
import requests

# ———— 配置区 ————
INPUT_FILE      = "song_urls.txt"    # 输入：每行一个 https://music.163.com/song?id=xxx
OUTPUT_FILE     = "music_url.txt"    # 输出：写入所有真实下载链接
OUT_DIR         = "downloads"        # 可选：下载目录

MUSIC_API_URL   = "https://api.toubiec.cn/api/music_v1.php"

# 您从 curl 测试中使用的两个 Token
HEADER_TOKEN    = "94cca773f0024168cf490c5aa529c1cc"  # 用于 Authorization header
BODY_TOKEN      = "ca8215539004b7ac6871bb27107013d9"  # 用于 请求体中的 token 字段

# 请求头：严格按照您的 curl 示例
MK_HEADERS = {
    "accept":             "application/json, text/plain, */*",
    "accept-language":    "zh-CN,zh;q=0.9,en;q=0.8",
    "authorization":      f"Bearer {HEADER_TOKEN}",
    "content-type":       "application/json",
    "origin":             "https://api.toubiec.cn",
    "priority":           "u=1, i",
    "referer":            "https://api.toubiec.cn/wyapi.html",
    "sec-ch-ua":          "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Google Chrome\";v=\"138\"",
    "sec-ch-ua-mobile":   "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest":     "empty",
    "sec-fetch-mode":     "cors",
    "sec-fetch-site":     "same-origin",
    "user-agent":         "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/138.0.0.0 Safari/537.36"
}
# ——————————————

def get_download_link(song_page_url, return_song_id= False):
    """
    调用 music_v1.php，返回单曲的真实下载 URL。
    使用静态 HEADER_TOKEN 和 BODY_TOKEN。
    """
    m = re.search(r"id=(\d+)", song_page_url)
    if not m:
        raise RuntimeError("无法从 URL 提取 song ID")
    song_id = m.group(1)

    payload = {
        "url":   song_page_url,
        "level": "exhigh",
        "type":  "song",
        "token": BODY_TOKEN
    }

    resp = requests.post(MUSIC_API_URL, json=payload, headers=MK_HEADERS, timeout=10)
    resp.raise_for_status()
    js = resp.json()
    if js.get("status") != 200:
        raise RuntimeError(f"解析失败，响应：{js}")

    download_url = js.get("url_info", {}).get("url")
    if not download_url:
        raise RuntimeError(f"未获取到下载链接：{js}")
    # 从接口里拿 song_info.name
    song_name = js.get("song_info", {}).get("name", song_id)
    if return_song_id:
        return download_url, song_name, song_id
    return download_url, song_name

def download_file(download_url, song_name, save_dir):
    """
    流式下载并保存到本地，返回文件路径
    """
    os.makedirs(save_dir, exist_ok=True)
    # fn = download_url.split("/")[-1].split("?")[0]
    # path = os.path.join(save_dir, fn)
    # 确保文件名带上 .mp3 后缀
    filename = song_name if song_name.lower().endswith('.mp3') else f"{song_name}.mp3"
    path = os.path.join(save_dir, filename)
    with requests.get(download_url, stream=True, timeout=30) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
    return path

def main():
    if not os.path.isfile(INPUT_FILE):
        print(f"错误：未找到输入文件 {INPUT_FILE}")
        return
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        urls = [l.strip() for l in f if l.strip()]

    if not urls:
        print(f"错误：{INPUT_FILE} 中无有效 URL")
        return

    with open(OUTPUT_FILE, "w", encoding="utf-8") as wf:
        for url in urls:
            try:
                print(f"正在处理：{url}")
                real_url, song_name = get_download_link(url)
                print(f"  获取真实链接：{real_url}")
                wf.write(real_url + "\n")
                # 如需自动下载，取消下一行注释：
                saved = download_file(real_url, song_name, OUT_DIR)
                print(f"  已下载至：{saved}")
            except Exception as e:
                print(f"  错误：{e}")

    print(f"\n完成，所有链接已写入 {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
