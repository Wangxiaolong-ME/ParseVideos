# Telegram机器人：https://t.me/IntelligentAxlxlbot
# 可以下载到本地使用-基础用法：下载最高清晰度
## 抖音视频下载
>示例：

`python -m src.DouyinDownload.main https://抖音视频链接.com`

```
usage: main.py [-h] [-r RESOLUTION] [--all] [-d SAVE_DIR] [-t THREADS] [--min-size MIN_SIZE] [--max-size MAX_SIZE]
               [--dedup {highest_bitrate,lowest_bitrate,largest_size,smallest_size}] [--save-meta] [--load-meta LOAD_META]
               url

抖音视频下载器 (Next-Gen Douyin Video Downloader)

positional arguments:
  url                   包含抖音短链接的文本或URL (Text or URL containing a Douyin short link)

options:
  -h, --help            show this help message and exit

下载控制 (Download Control):
  -r, --resolution RESOLUTION
                        指定下载的分辨率，如 720 (Specify a resolution to download, e.g., 720)
  --all                 下载所有经过筛选后可用的清晰度 (Download all available resolutions after filtering)
  -d, --save-dir SAVE_DIR
                        视频保存目录 (默认: C:\Users\axlxlw\PycharmProjects\DownloadHandler\src\DouyinDownload\video_downloads) (Directory to save videos)       
  -t, --threads THREADS
                        分段下载的线程数 (默认: 8) (Number of threads for segmented download)

链接筛选与处理 (Link Filtering & Processing):
  --min-size MIN_SIZE   筛选视频：最小文件大小 (MB) (Filter videos: minimum file size in MB)
  --max-size MAX_SIZE   筛选视频：最大文件大小 (MB) (Filter videos: maximum file size in MB)
  --dedup {highest_bitrate,lowest_bitrate,largest_size,smallest_size}
                        分辨率去重策略 (Deduplication strategy for resolutions)

元数据操作 (Metadata Operations):
  --save-meta           获取详情后，将元数据保存为json文件 (Save metadata to a JSON file after fetching details)
  --load-meta LOAD_META
                        从指定的json文件加载元数据，跳过在线获取步骤 (Load metadata from a JSON file, skipping online fetching)

```
## B站视频下载
> 示例：

`python -m src.BilibiliDownload.main https://bilibili视频链接.com`

```
usage: main.py [-h] [-d SAVE_DIR] [-r RESOLUTION | --highest | --lowest] [-o OUTPUT] [--no-merge] url

Bilibili 视频下载工具

positional arguments:
  url                   Bilibili 视频链接

options:
  -h, --help            show this help message and exit
  -d, --save-dir SAVE_DIR
                        保存目录
  -r, --resolution RESOLUTION
                        指定分辨率 ID 或描述
  --highest             下载最高画质
  --lowest              下载最低画质
  -o, --output OUTPUT   合并后输出文件名
  --no-merge            只下载但不合并视频和音频（默认会合并）

```
