# main.py
"""
主程序入口，负责解析命令行参数并调用核心业务逻辑。
Main program entry point, responsible for parsing command-line arguments and invoking core business logic.
"""
import argparse
import sys
from src.PublicMethods.logger import get_logger, setup_log
import logging

setup_log(logging.DEBUG, 'DouYinDownloader')
log = get_logger(__name__)

from src.DouyinDownload.douyin_post import DouyinPost
from src.DouyinDownload.exceptions import DouyinDownloadException


def main():
    parser = argparse.ArgumentParser(
        description="抖音视频下载器 (Next-Gen Douyin Video Downloader)",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("url", help="包含抖音短链接的文本或URL (Text or URL containing a Douyin short link)")

    # 下载相关参数
    download_group = parser.add_argument_group('下载控制 (Download Control)')
    download_group.add_argument("-r", "--resolution", type=int,
                                help="指定下载的分辨率，如 720 (Specify a resolution to download, e.g., 720)")
    download_group.add_argument("--all", action="store_true",
                                help="下载所有经过筛选后可用的清晰度 (Download all available resolutions after filtering)")
    download_group.add_argument("-d", "--save-dir", default=None,
                                help=f"视频保存目录 (默认: {DouyinPost.save_dir}) (Directory to save videos)")
    download_group.add_argument("-t", "--threads", type=int, default=8,
                                help="分段下载的线程数 (默认: 8) (Number of threads for segmented download)")

    # 链接处理参数
    filter_group = parser.add_argument_group('链接筛选与处理 (Link Filtering & Processing)')
    filter_group.add_argument("--min-size", type=float,
                              help="筛选视频：最小文件大小 (MB) (Filter videos: minimum file size in MB)")
    filter_group.add_argument("--max-size", type=float,
                              help="筛选视频：最大文件大小 (MB) (Filter videos: maximum file size in MB)")
    filter_group.add_argument(
        "--dedup",
        choices=['highest_bitrate', 'lowest_bitrate', 'largest_size', 'smallest_size'],
        help="分辨率去重策略 (Deduplication strategy for resolutions)"
    )

    # 元数据参数
    meta_group = parser.add_argument_group('元数据操作 (Metadata Operations)')
    meta_group.add_argument("--save-meta", action="store_true",
                            help="获取详情后，将元数据保存为json文件 (Save metadata to a JSON file after fetching details)")
    meta_group.add_argument("--load-meta",
                            help="从指定的json文件加载元数据，跳过在线获取步骤 (Load metadata from a JSON file, skipping online fetching)")

    # # 其他参数
    # other_group = parser.add_argument_group('其他 (Others)')
    # other_group.add_argument("--no-proxy", action="store_false", help="禁用系统代理 (Disable system proxy)")

    args = parser.parse_args()

    try:
        # --- 1. 初始化或从元数据加载 ---
        if args.load_meta:
            post = DouyinPost.load_from_metadata(
                args.load_meta,
                save_dir=args.save_dir or DouyinPost.save_dir,
                # trust_env=not args.no_proxy,
                threads=args.threads
            )
        else:
            post = DouyinPost(
                short_url_text=args.url,
                save_dir=args.save_dir or DouyinPost.save_dir,
                # trust_env=not args.no_proxy,
                threads=args.threads
            )
            # --- 2. 获取在线详情 ---
            post.fetch_details()

        # --- 3. (可选) 筛选和处理 ---
        # 链式调用展示
        if args.min_size or args.max_size:
            post.filter_by_size(min_mb=args.min_size, max_mb=args.max_size)

        if args.dedup:
            post.deduplicate_by_resolution(keep=args.dedup)

        # 默认按分辨率降序排序
        post.sort_options(by='resolution', descending=True)

        log.info("最终待处理的视频选项 (Final video options to be processed):")
        for option in post.processed_video_options:
            log.info(f" - {option}")

        if not post.processed_video_options:
            log.warning("经过筛选，没有可下载的视频选项。(After filtering, no downloadable options remain.)")
            sys.exit(0)

        # --- 4. (可选) 保存元数据 ---
        if args.save_meta:
            post.save_metadata()

        # --- 5. 执行下载 ---
        log.info("准备开始下载任务... (Preparing to start download task...)")
        saved_paths = post.download_video(resolution=args.resolution, download_all=args.all)

        log.info("--- 所有任务完成 (All tasks completed) ---")
        log.info("成功保存的文件 (Successfully saved files):")
        for path in saved_paths:
            log.info(f" - {path}")

    except DouyinDownloadException as e:
        log.error(f"[错误] 操作失败 (An error occurred): {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        log.error(f"[致命错误] 发生未知异常 (An unexpected error occurred): {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
