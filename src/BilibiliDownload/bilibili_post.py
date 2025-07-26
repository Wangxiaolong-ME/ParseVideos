# bilibili_post.py
"""
业务层：链式调用方案，支持分辨率筛选、最高/最低选择、下载与合并操作。
"""
import os
import subprocess
from BilibiliDownload.parser import BilibiliParser
from PublicMethods.m_download import Downloader
from BilibiliDownload.config import DEFAULT_SAVE_DIR, DEFAULT_MERGE_DIR, DEFAULT_HEADERS
from BilibiliDownload.exceptions import BilibiliParseError, BilibiliDownloadError
from TelegramBot.config import DEFAULT_DOWNLOAD_THREADS
import  logging
log = logging.getLogger(__name__)


class BilibiliPost:
    def __init__(self, url: str, save_dir: str = None, merge_dir: str = None, headers: dict = None,
                 cookie: dict = None, threads=DEFAULT_DOWNLOAD_THREADS):
        self.duration = None
        self.gear_name = None
        self.size_mb = None
        self.audio_options = None
        self.video_options = None
        self.bvid = None
        self.title = None
        self.url = url
        self.raw_url = None
        self.height = None
        self.width = None
        self.save_dir = save_dir or DEFAULT_SAVE_DIR
        self.merge_dir = merge_dir or DEFAULT_MERGE_DIR
        self.headers = headers or DEFAULT_HEADERS.copy()
        self.logger = log
        self.selected_video = None
        self.selected_audio = None
        self.parser = BilibiliParser(url, headers=self.headers, cookie=cookie)
        self.downloader = Downloader(session=self.parser.session, threads=threads)
        self.preview_video = None

        # ensure dirs
        os.makedirs(self.save_dir, exist_ok=True)
        os.makedirs(self.merge_dir, exist_ok=True)

    def fetch(self):
        self.logger.info(f"Fetching info from {self.url}")
        try:
            self.parser.fetch()
            self.raw_url = self.parser.url
            self.title = self.parser.title
            self.bvid = self.parser.bvid
            log.info(f"标题:{self.title}")
            log.info(f"bvid:{self.bvid}")
            if self.parser.preview_video_url:
                log.warning(f"该视频为私人视频或VIP会员视频的预览片段")
                self.preview_video = self.parser.preview_video_url
                return self

            self.video_options = self.parser.video_options
            self.audio_options = self.parser.audio_options
            self.selected_video = self.video_options[-1] if self.audio_options else None
            self.selected_audio = self.audio_options[-1] if self.audio_options else None
            self.size_mb = self.selected_video['size_mb'] + self.selected_audio['size_mb']
            self.duration = self.selected_video['duration'] or 0
        except Exception as e:
            raise BilibiliParseError(e)
        return self

    def filter_resolution(self, resolution):
        """按 quality id 或 description 筛选"""
        for v in self.video_options:
            if str(v['quality']) == str(resolution) or v['description'] == str(resolution):
                self.selected_video = v
                break
        if self.selected_video:
            self._update_self_data()
        else:
            log.warning(f"未找到匹配分辨率: {resolution}, 默认选取最低分辨率")
            self.select_lowest()
            raise BilibiliParseError(f"未找到匹配分辨率: {resolution}")
        return self

    def select_highest(self):
        """选择最高质量，"""
        self.selected_video = self.video_options[0] if self.video_options else None
        self.selected_audio = self.audio_options[0] if self.audio_options else None
        self._update_self_data()
        log.debug(f"select_highest:{self.selected_video}")
        return self

    def select_lowest(self):
        """选择最低质量"""
        self.selected_video = self.video_options[-1] if self.video_options else None
        self.selected_audio = self.audio_options[-1] if self.audio_options else None
        self._update_self_data()
        log.debug(f"select_lowest:{self.selected_video}")
        return self

    def _update_self_data(self):
        if self.selected_video and self.selected_audio:
            self.gear_name = self.selected_video['gear_name']
            # 计算合并后大小=(视频比特率+音频比特率)×时长 / 8 /(1024*1024)
            bit = ((self.selected_video['bandwidth'] + self.selected_audio['bandwidth']) * self.duration) / 8
            self.size_mb = round(bit / (1024 * 1024), 3)  # 转MB
            self.height = self.selected_video['height']
            self.width = self.selected_video['width']

    def filter_by_size(self, *, min_mb: float = 0, max_mb: float | None = None, options=None):
        """
        按文件大小区间筛选视频清晰度。筛选条件是以合并后的大小为准
        - min_mb: 保留 ≥ 该大小的选项
        - max_mb: 保留 ≤ 该大小的选项；None 表示无限制
        若筛选后为空，则兜底选择“最小文件”。
        """
        if not self.video_options:
            raise BilibiliParseError("video_options 为空，需先 fetch()")

        kept = []
        for opt in self.video_options:
            sz = opt["size_mb"]
            if sz >= min_mb and (max_mb is None or sz <= max_mb):
                log.debug(f"复合筛选条件的视频大小：{sz}MB")
                self.selected_video = opt
                self._update_self_data()
                sz = self.size_mb
                if sz >= min_mb and (max_mb is None or sz <= max_mb):
                    # log.debug(f"粗略估算合并音频后的大小为: {sz} MB")
                    kept.append(opt)
                else:
                    log.warning(f"计算合并音频后的大小超出筛选条件")
                    continue

        # 如果筛选结果为空，兜底取最小文件
        if not kept:
            self.select_lowest()
            log.warning(f"筛选结果为空，选择最小文件")
        else:
            self.selected_video = kept[0]   # 0为质量最好的
            log.debug(f"筛选保留{len(kept)}个视频,(min={min_mb}MB, max={max_mb}MB)")
            log.debug(f"保留视频列表:{kept}")
            self._update_self_data()
            log.debug(f"从筛选的视频中选择质量最高的:{self.selected_video}")

        self.logger.debug(
            f"按大小筛选：从 {len(self.video_options)} 个选项中保留 {len(kept)} 个"
            f" (min={min_mb}MB, max={max_mb}MB)"
        )
        return self

    def preview_video_download(self):
        if not self.preview_video:
            raise BilibiliDownloadError(f"未知预览视频链接:{self.preview_video}")
        # 文件名
        base = f"{self.bvid}_preview"
        vpath = os.path.join(self.save_dir, base + '.mp4')
        self.downloader.download(self.preview_video, vpath, headers=self.headers)
        return base

    def download(self, is_preview=False):
        """下载已选视频和音频"""
        if not self.selected_video or not self.selected_audio:
            raise BilibiliDownloadError("请先调用 select_highest/select_lowest 或 filter_resolution 方法")
        vid = self.selected_video
        aud = self.selected_audio
        # 文件名
        base = f"{self.bvid}_{vid['gear_name']}"
        vpath = os.path.join(self.save_dir, base + '.mp4')
        apath = os.path.join(self.save_dir, base + '.m4a')
        self.logger.debug(f"vpath:{vpath}")
        self.logger.debug(f"apath:{apath}")
        self.logger.debug(f"Downloading video {vid['description']}")
        self.downloader.download(vid['url'], vpath, headers=self.headers)
        self.logger.debug(f"Downloading audio {aud['quality']}")
        self.downloader.download(aud['url'], apath, headers=self.headers)
        return vpath, apath

    def merge(self, vpath: str, apath: str, output_name: str = None):
        """调用 ffmpeg 合并"""
        if not output_name:
            output_name = f"{self.bvid}_{self.selected_video['gear_name']}_merged.mp4"
        out = os.path.join(self.merge_dir, output_name)
        cmd = ['ffmpeg', '-loglevel', 'error', '-y', '-i', vpath, '-i', apath, '-c', 'copy', out]
        # self.logger.info(f"Merging to {out}")
        subprocess.run(cmd, check=True)
        self.logger.debug(f"合并完成：{out}")
        return out
