# src/app.py

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field
import os
import logging
from typing import Optional, List
import requests
from contextlib import asynccontextmanager
import asyncio # 新增导入 asyncio

# 导入您的核心业务逻辑和日志模块
from douyin_post import DouyinPost
from exceptions import DouyinDownloadException, URLExtractionError, ParseError, DownloadError
from src.PublicMethods.logger import setup_log, get_logger
from config import DEFAULT_SAVE_DIR, DEFAULT_DOWNLOAD_THREADS


# 定义请求模型
class DownloadRequest(BaseModel):
    url: Optional[str] = Field(None, description="抖音短链接或包含短链接的文本。如果使用 load_meta，此项可留空。")
    load_meta: Optional[str] = Field(None, description="从元数据文件路径加载视频信息，跳过URL解析。")
    save_dir: Optional[str] = Field(None, description=f"视频保存目录 (默认: {DEFAULT_SAVE_DIR})")
    resolution: Optional[int] = Field(None, description="指定下载的分辨率，如 720。")
    download_all: Optional[bool] = Field(False, description="下载所有经过筛选后可用的清晰度。")
    threads: Optional[int] = Field(DEFAULT_DOWNLOAD_THREADS, description="分段下载的线程数 (默认: 8)。")
    min_size: Optional[float] = Field(None, description="筛选视频的最小文件大小 (MB)。")
    max_size: Optional[float] = Field(None, description="筛选视频的最大文件大小 (MB)。")
    dedup: Optional[str] = Field(None, description="分辨率去重策略，可选 'highest_bitrate', 'lowest_bitrate' 等。")
    save_meta: Optional[bool] = Field(False, description="是否保存视频元数据到文件。")
    no_proxy: Optional[bool] = Field(False, description="是否在请求中使用代理。")


# 定义响应模型
class DownloadResponse(BaseModel):
    message: str = Field(..., description="操作结果消息。")
    download_paths: Optional[List[str]] = Field(None, description="成功下载的视频文件路径列表。")
    video_title: Optional[str] = Field(None, description="下载视频的标题。")
    error_details: Optional[str] = Field(None, description="错误详情，如果有的话。")


# 日志初始化
global_logger = None

@asynccontextmanager
async def lifespan_context(app: FastAPI):
    global global_logger
    setup_log(logging.DEBUG)
    global_logger = get_logger(__name__)
    global_logger.info("FastAPI 应用启动并已初始化日志系统。")

    if not os.path.exists(DEFAULT_SAVE_DIR):
        os.makedirs(DEFAULT_SAVE_DIR)
        global_logger.info(f"创建下载目录: {DEFAULT_SAVE_DIR}")

    yield

    global_logger.info("FastAPI 应用正在关闭。")


app = FastAPI(
    title="抖音下载器 API",
    description="一个用于下载抖音视频的 API 服务，支持无水印下载和多种筛选选项。",
    version="1.0.0",
    lifespan=lifespan_context
)


@app.get("/")
async def read_root():
    return {"message": "欢迎使用抖音下载器 API！请访问 /docs 查看API文档。"}


@app.post("/download", response_model=DownloadResponse, status_code=status.HTTP_200_OK)
async def download_douyin_video(request: DownloadRequest):
    global_logger.info(f"收到下载请求: {request.dict()}")

    url = request.url

    if not url and not request.load_meta:
        global_logger.warning("请求中未提供URL或元数据文件路径。")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL 和 load_meta 至少需要提供一个。"
        )

    if url and request.load_meta:
        global_logger.warning("同时提供了URL和元数据文件路径，将优先使用load_meta。")

    post = None
    try:
        if request.load_meta:
            global_logger.info(f"正在从元数据文件加载: {request.load_meta}")
            # load_from_metadata 是同步的，如果文件读取很快，不需 special 处理
            post = DouyinPost.load_from_metadata(request.load_meta, save_dir=request.save_dir or DEFAULT_SAVE_DIR)
        else:
            global_logger.info(f"正在通过URL初始化: {url}")
            post = DouyinPost(
                url,
                save_dir=request.save_dir or DEFAULT_SAVE_DIR,
                threads=request.threads or DEFAULT_DOWNLOAD_THREADS,
                session=requests.Session()
            )
            # 核心改动：将同步的 fetch_details 放入线程池
            # await asyncio.to_thread(同步函数, 参数1, 参数2, ...)
            await asyncio.to_thread(post.fetch_details, no_proxy=request.no_proxy)


        # --- 应用筛选和去重逻辑 ---
        if request.min_size or request.max_size:
            global_logger.info(f"应用大小筛选: min={request.min_size}MB, max={request.max_size}MB")
            post.filter_by_size(min_mb=request.min_size, max_mb=request.max_size)

        if request.dedup:
            global_logger.info(f"应用去重策略: {request.dedup}")
            post.deduplicate_by_resolution(keep=request.dedup)

        post.sort_options(by='resolution', descending=True)

        if not post.processed_video_options:
            message = "经过筛选，没有可下载的视频选项。"
            global_logger.warning(message)
            return DownloadResponse(message=message, download_paths=[], video_title=post.video_title)

        global_logger.info(f"最终待下载的视频选项数量: {len(post.processed_video_options)}")

        # --- (可选) 保存元数据 ---
        meta_filepath = None
        if request.save_meta:
            global_logger.info("正在保存元数据...")
            # save_metadata 也是同步的，但通常写入很快，可以不加 to_thread
            meta_filepath = post.save_metadata()
            global_logger.info(f"元数据已保存至: {meta_filepath}")

        # --- 执行下载 ---
        global_logger.info("准备开始下载任务...")
        # 核心改动：将同步的 download_video 也放入线程池，因为下载可能是长时间阻塞操作
        saved_paths = await asyncio.to_thread(post.download_video, resolution=request.resolution, download_all=request.download_all)


        global_logger.info("所有任务完成。")
        return DownloadResponse(
            message="视频下载任务完成！",
            download_paths=saved_paths,
            video_title=post.video_title
        )

    except DouyinDownloadException as e:
        global_logger.error(f"下载过程中发生业务错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"下载失败: {e}"
        )
    except Exception as e:
        global_logger.critical(f"发生未知错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"服务器内部错误: {e}"
        )