# main.py
"""
命令行入口，支持指定分辨率、最高/最低画质、可选合并。
"""
import argparse
import logging

from PublicMethods.logger import setup_log, get_logger

# 全局日志初始化，设置为 DEBUG 级别以便调试
setup_log(logging.DEBUG, 'BilibiliDownload')
log = get_logger(__name__)
from BilibiliDownload.bilibili_post import BilibiliPost
from BilibiliDownload.config import DEFAULT_SAVE_DIR


def main():
    parser = argparse.ArgumentParser(description='Bilibili 视频下载工具')
    parser.add_argument('url', help='Bilibili 视频链接')
    parser.add_argument('-d', '--save-dir', default=DEFAULT_SAVE_DIR, help='保存目录')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-r', '--resolution', help='指定分辨率 ID 或描述')
    group.add_argument('--highest', action='store_true', help='下载最高画质')
    group.add_argument('--lowest', action='store_true', help='下载最低画质')
    parser.add_argument('-o', '--output', help='合并后输出文件名')
    # 默认自动合并：merge=True
    parser.add_argument(
        '--no-merge',
        dest='merge',
        action='store_false',
        help='只下载但不合并视频和音频（默认会合并）'
    )
    args = parser.parse_args()

    # cookie可以在网站上登录找到Cookie中的SESSDATA字段复制过来添加，这样就能获取1080清晰度，如果你是会员那就更高
    cookie = {
        "SESSDATA": "fa7088b5%2C1767070776%2Ce455f%2A72CjAsGSV6dG0MTVfy-7xMP1n4kfCRwUsAx0KYcYx9PRLKpySeIDrgnrsdmNsZtn0HA0cSVmUyY1A1QmhkQ2RqWE9pVVBfb2FuVFRtU0FubmFLN0pQb2Vjc2VMcXA1Y3VsSmh5M0p2TDB0TXFqU1djTUI4bVRXaEoxWFJqTzc1SzI4ZmRHOEpKVHdBIIEC"
    }
    post = BilibiliPost(
        url=args.url,
        save_dir=args.save_dir,
        cookie=cookie
    ).fetch()

    if args.resolution:
        post.filter_resolution(args.resolution)
    elif args.lowest:
        post.select_lowest()
    else:
        # 默认最高
        post.select_highest()

    vpath, apath = post.download()
    if args.merge:
        out = post.merge(vpath, apath, args.output)
    else:
        log.info(f"下载完成，文件保存在: {vpath} 和 {apath}")


if __name__ == '__main__':
    main()
