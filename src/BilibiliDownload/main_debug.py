# main_debug.py
"""
用于调试和测试 Bilibili 下载流程的入口脚本，
无需通过命令行参数，直接在代码中配置测试用例。
"""
import os
import logging
from src.PublicMethods.logger import setup_log, get_logger

# 全局日志初始化，设置为 DEBUG 级别以便调试
setup_log(logging.DEBUG, 'BilibiliDownload')
log = get_logger(__name__)
from src.BilibiliDownload.bilibili_post import BilibiliPost
from src.BilibiliDownload.config import DEFAULT_SAVE_DIR


def run_bilibili_debug(
        url: str,
        resolution: str = None,
        highest: bool = True,
        lowest: bool = False,
        save_dir: str = None,
        merge: bool = True,
        output_name: str = None
) -> list:
    """
    以编程方式执行 Bilibili 下载流程。

    :param url:         Bilibili 视频链接
    :param resolution:  指定分辨率 ID 或描述（优先级最高）
    :param highest:     若未指定 resolution，是否选择最高画质
    :param lowest:      若未指定 resolution，是否选择最低画质
    :param save_dir:    保存目录（默认 DEFAULT_SAVE_DIR）
    :param merge:       是否合并视频和音频（默认 True）
    :param output_name: 合并后输出文件名（可选）
    :return:            下载（或合并）后生成的文件路径列表
    """
    results = []
    try:
        # cookie可以在网站上登录找到Cookie中的SESSDATA字段复制过来添加，这样就能获取1080清晰度，如果你是会员那就更高
        cookie = {
            "SESSDATA": "fa7088b5%2C1767070776%2Ce455f%2A72CjAsGSV6dG0MTVfy-7xMP1n4kfCRwUsAx0KYcYx9PRLKpySeIDrgnrsdmNsZtn0HA0cSVmUyY1A1QmhkQ2RqWE9pVVBfb2FuVFRtU0FubmFLN0pQb2Vjc2VMcXA1Y3VsSmh5M0p2TDB0TXFqU1djTUI4bVRXaEoxWFJqTzc1SzI4ZmRHOEpKVHdBIIEC"
        }
        # 1. 初始化并获取信息
        post = BilibiliPost(
            url=url,
            save_dir=save_dir or DEFAULT_SAVE_DIR,
            cookie=cookie
        ).fetch()
        log.debug(f"视频标题: {post.title}，可选清晰度: {[v['description'] for v in post.video_options]}")

        # 2. 选择分辨率
        if resolution:
            post.filter_resolution(resolution)
            log.debug(f"已按指定分辨率筛选: {post.selected_video['description']}")
        elif lowest:
            post.select_lowest()
            log.debug(f"已选择最低画质: {post.selected_video['description']}")
        else:
            post.select_highest()
            log.debug(f"已选择最高画质: {post.selected_video['description']}")

        # 3. 下载
        vpath, apath = post.download()
        results.extend([vpath, apath])
        log.info(f"下载完成: 视频 {vpath}，音频 {apath}")

        # 4. 合并（可选）
        if merge:
            out = post.merge(vpath, apath, output_name)
            results = [out]
            log.info(f"合并完成: {out}")

    except Exception as e:
        log.error(f"调试过程中发生错误: {e}")
    return results


if __name__ == "__main__":
    # ====== 在这里修改测试用例 ======
    # TEST_URL = "https://www.bilibili.com/video/BV1JDMQzUEwy"
    TEST_URL = "https://b23.tv/vz2iDoC"
    TEST_RESOLUTION = None  # 例如: "1080", "高清"
    TEST_HIGHEST = True  # 不指定分辨率时，是否选最高
    TEST_LOWEST = False  # 不指定分辨率时，是否选最低
    TEST_SAVE_DIR = os.path.join(DEFAULT_SAVE_DIR, "debug")
    TEST_MERGE = True  # 是否合并
    TEST_OUTPUT = None  # 合并后自定义文件名（不含路径）

    # 执行下载流程
    saved = run_bilibili_debug(
        url=TEST_URL,
        resolution=TEST_RESOLUTION,
        highest=TEST_HIGHEST,
        lowest=TEST_LOWEST,
        save_dir=TEST_SAVE_DIR,
        merge=TEST_MERGE,
        output_name=TEST_OUTPUT
    )

    if saved:
        log.info("调试完成，生成文件：")
        for p in saved:
            log.info(f" - {p}")
    else:
        log.warning("调试未产生任何输出文件，请检查错误日志。")
