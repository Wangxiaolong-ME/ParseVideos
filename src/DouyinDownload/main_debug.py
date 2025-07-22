# main_debug.py
"""
一个用于调试和测试的入口文件，直接调用 DouyinPost 逻辑，不依赖命令行参数。
An entry point for debugging and testing, directly invoking DouyinPost logic without relying on command-line arguments.
"""
import os
from PublicMethods.logger import get_logger, setup_log
import logging

setup_log(logging.DEBUG, 'DouYinDownloader')
log = get_logger(__name__)

from DouyinDownload.douyin_post import DouyinPost
from DouyinDownload.exceptions import DouyinDownloadException


def run_downloader_programmatically(
        url: str,
        resolution: int = None,
        download_all: bool = False,
        save_dir: str = None,
        threads: int = 8,
        min_size: float = None,
        max_size: float = None,
        dedup: str = None,
        save_meta: bool = False,
        load_meta: str = None,
        no_proxy: bool = False
):
    """
    以编程方式运行抖音视频下载器。
    Runs the Douyin video downloader programmatically.

    :param url: 抖音短链接文本。
    :param resolution: 指定下载的分辨率。
    :param download_all: 是否下载所有可用清晰度。
    :param save_dir: 视频保存目录。
    :param threads: 分段下载的线程数。
    :param min_size: 筛选视频的最小文件大小 (MB)。
    :param max_size: 筛选视频的最大文件大小 (MB)。
    :param dedup: 分辨率去重策略。
    :param save_meta: 是否保存元数据。
    :param load_meta: 从指定的json文件加载元数据。
    :param no_proxy: 是否禁用系统代理。
    """
    try:
        # --- 1. 初始化或从元数据加载 ---
        current_save_dir = save_dir if save_dir is not None else DEFAULT_SAVE_DIR  # 使用配置中的默认值

        if load_meta:
            post = DouyinPost.load_from_metadata(
                load_meta,
                save_dir=current_save_dir,
                trust_env=not no_proxy,
                threads=threads
            )
        else:
            post = DouyinPost(
                short_url_text=url,
                save_dir=current_save_dir,
                trust_env=not no_proxy,
                threads=threads
            )
            # --- 2. 获取在线详情 ---
            post.fetch_details()

        # --- 3. (可选) 筛选和处理 ---
        if min_size is not None or max_size is not None:
            post.filter_by_size(min_mb=min_size, max_mb=max_size)

        if dedup:
            post.deduplicate_by_resolution(keep=dedup)

        # 默认按分辨率降序排序
        post.sort_options(by='resolution', descending=True)

        log.info("最终待处理的视频选项 (Final video options to be processed):")
        if not post.processed_video_options:
            log.warning("  无可用选项 (No options available).")
        for option in post.processed_video_options:
            log.info(f"{option}")

        if not post.processed_video_options:
            log.warning("\n经过筛选，没有可下载的视频选项。(After filtering, no downloadable options remain.)")
            return []  # 返回空列表表示没有下载

        # --- 4. (可选) 保存元数据 ---
        if save_meta:
            post.save_metadata()

        # --- 5. 执行下载 ---
        log.info("准备开始下载任务... (Preparing to start download task...)")
        saved_paths = post.download_video(resolution=resolution, download_all=download_all)

        log.info("--- 所有任务完成 (All tasks completed) ---")
        log.info("成功保存的文件 (Successfully saved files):")
        for path in saved_paths:
            log.info(f" - {path}")
        return saved_paths

    except DouyinDownloadException as e:
        log.error(f"\n[错误] 操作失败 (An error occurred): {e}")
        return []
    except Exception as e:
        log.error(f"\n[致命错误] 发生未知异常 (An unexpected error occurred): {e}")
        return []


if __name__ == "__main__":
    # 导入 config 以获取 DEFAULT_SAVE_DIR
    from config import DEFAULT_SAVE_DIR

    url = "4.66 11/14 C@U.YZ EhB:/ 神秘出餐口！ # 2025鸡斯卡星火计划 # pubg暑期吃鸡训练营  https://v.douyin.com/UYoCOpbDRIs/ 复制此链接，打开Dou音搜索，直接观看视频！"
    # --- 调试示例 1: 仅获取详情并保存元数据 ---
    log.info("--- 调试示例 1: 仅获取详情并保存元数据 ---")
    test_url_1 = url  # 替换成一个真实的抖音短链接
    run_downloader_programmatically(
        url=test_url_1,
        save_meta=True,
        resolution=720,
        save_dir=os.path.join(DEFAULT_SAVE_DIR, "debug_meta_only"),
        no_proxy=True,
        # min_size=10,
        # max_size=50,
        dedup="smallest_size"
    )
    log.info("" + "=" * 50)

    # # --- 调试示例 2: 下载最高分辨率视频 ---
    # log.info("--- 调试示例 2: 下载最高分辨率视频 ---")
    # test_url_2 = url # 替换成另一个真实的抖音短链接
    # run_downloader_programmatically(
    #     url=test_url_2,
    #     save_dir=os.path.join(DEFAULT_SAVE_DIR, "debug_highest_res"),
    #     threads=4 # 可以调整线程数
    # )
    # log.info("\n" + "="*50 + "\n")
    #
    # # --- 调试示例 3: 下载指定分辨率 (如果存在) 并进行筛选和去重 ---
    # log.info("--- 调试示例 3: 下载指定分辨率并进行筛选和去重 ---")
    # test_url_3 = url # 替换成一个真实的抖音短链接，最好是多清晰度的
    # run_downloader_programmatically(
    #     url=test_url_3,
    #     resolution=720, # 尝试下载720p
    #     min_size=5.0,   # 筛选大于5MB的
    #     max_size=50.0,  # 筛选小于50MB的
    #     dedup='highest_bitrate', # 每个分辨率只保留最高码率
    #     save_dir=os.path.join(DEFAULT_SAVE_DIR, "debug_filtered_720p")
    # )
    # log.info("\n" + "="*50 + "\n")
    #
    # --- 调试示例 4: 从元数据文件加载并下载 ---
    # 这个需要你先运行示例1或手动生成一个metadata.json文件
    # log.info("--- 调试示例 4: 从元数据文件加载并下载 ---")
    # # 假设你已经保存了一个名为 '你的抖音标题_metadata.json' 的文件
    # # 请替换为实际的元数据文件路径
    # # 例如: metadata_file_path = os.path.join(DEFAULT_SAVE_DIR, "debug_meta_only", "你的抖音标题_metadata.json")
    # metadata_file_path = r"C:\Users\axlxlw\PycharmProjects\DouyinDownload\src\video_downloads\debug_meta_only\Max的自信重建挑战3_找陌生人互动～ 今天去到海边啦！_metadata.json"  # 请修改为实际路径
    # if os.path.exists(metadata_file_path):
    #     run_downloader_programmatically(
    #         url="dummy_url_for_loading",  # 这个URL在此处不重要，因为是从文件加载
    #         load_meta=metadata_file_path,
    #         download_all=False,  # 加载后下载所有可用选项
    #         save_dir=os.path.join(DEFAULT_SAVE_DIR, "debug_from_meta")
    #     )
    # else:
    #     log.info(f"警告: 未找到元数据文件 '{metadata_file_path}', 跳过示例 4.")
    # log.info("\n" + "=" * 50 + "\n")

    log.info("所有调试示例运行完毕。请检查输出和下载目录。")
