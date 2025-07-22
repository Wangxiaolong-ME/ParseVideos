# parser.py
"""
解析 Bilibili __playinfo__ 和 __INITIAL_STATE__，提取 DASH 流列表。
"""
import re
import json
from typing import Any
import requests
from bs4 import BeautifulSoup

from BilibiliDownload.exceptions import BilibiliParseError
from PublicMethods.logger import get_logger, setup_log
from PublicMethods.m_download import Downloader
from PublicMethods.tools import prepared_to_curl

setup_log()
log = get_logger(__name__)


class BilibiliParser:
    def __init__(self, url: str, headers: dict = None, session: requests.Session = None, cookie: dict = None):
        self.url = url
        self._parse_url()
        log.debug(f"_parse_url: {self.url}")
        self.headers = headers or {}
        self.cookie = cookie or {}
        self.session = session or requests.Session()
        self.bvid = None
        self.title = None
        self.video_options = []  # 列表项: {'quality': int, 'description': str, 'url': str}
        self.audio_options = []  # 列表项: {'quality': int, 'url': str}
        self.preview_video_url = None   # 如果视频是预览视频，后续直通车，下载上传，无需其余逻辑判断

    def _parse_url(self):
        """
        从 self.url 中提取 BV 号（形如 BVxxxxxxxxxx），
        并将 self.url 标准化为 https://www.bilibili.com/video/{BV号} 形式。
        移动端链接： https://b23.tv/vzxxxx,访问会重定向在location中给带BV号的标准链接
        番剧类：https://bilibili.com/bangumi/play/xxxx
        """
        host = "https://www.bilibili.com"
        # 匹配 BV 号
        if m := re.search(r'(BV[0-9A-Za-z]{10})', self.url):
            self.bvid = m.group(1)
            self.url = f"{host}/video/{self.bvid}"
        # 移动链接
        elif m := re.search(r'(b23.tv\/\w{7})', self.url):
            short_url = f"https://{m.group()}"
            final_url = Downloader()._get_final_url(short_url, max_redirects=1, return_flag="bilibili.com/video")
            self.url = final_url
            self._parse_url()
            return
        # 番剧链接
        elif re.search(r'bangumi\/play', self.url):
            ep_id = re.search(r'(?<=\/)ep\w+', self.url)
            if ep_id:
                self.url = f"{host}/bangumi/play/{ep_id.group()}?from_spmid=666.25.episode.0"
        else:
            raise BilibiliParseError(f"无效的 Bilibili 视频链接: {self.url}")
        return self

    def _extract_json(self, html: str, pattern: str) -> Any | None:
        m = re.search(pattern, html)
        if not m:
            log.error(f"未找到 JSON 数据，页面结构或已变化。")
            return None
            # raise BilibiliParseError(f"未找到 {var_name} JSON 数据，页面结构或已变化。")
        try:
            idx = m.start(1)
            decoder = json.JSONDecoder()
            data, _ = decoder.raw_decode(html[idx:])
            return data
        except json.JSONDecodeError as e:
            log.error(f"解析 JSON 数据失败: {e}")
            return None
            # raise BilibiliParseError(f"解析 {var_name} 数据失败: {e}")

    @staticmethod
    def _try_parse_json(final_text):
        # 创建一个 JSON 解码器实例
        decoder = json.JSONDecoder()

        # 尝试解析 JSON 字符串
        while final_text:
            try:
                # 尝试解析 JSON，找到完整的 JSON 数据
                target_dict, index = decoder.raw_decode(final_text)
                return target_dict
            except json.JSONDecodeError as e:
                # 解析失败，裁剪字符串直到找到一个合法的 JSON
                if 'extra data' in str(e):  # 如果是多余的数据
                    # 截断字符串，直到找到 `}` 为止
                    final_text = final_text[:e.pos].rstrip()  # 只保留有效的部分
                else:
                    # 如果是其他错误，直接返回 None
                    return None

        return None

    def _search_scripts_from_scripts(self, script_tags, target_script_regex, select_reg=None):
        """
        target_script_regex: 正则主要匹配script头部，命中即返回其json
        select_reg: 选择正则，如果没有就按照target_script_regex加上.*匹配全部
        """
        for script in script_tags:
            if script.string:  # 如果 <script> 标签有内容
                if re.search(target_script_regex, script.string, re.DOTALL):
                    select_reg = select_reg or f"{target_script_regex}.*"
                    match = re.search(select_reg, script.text, re.DOTALL)
                    if match:
                        text = match.group()
                        # 去除xxx=开头
                        del_text = re.search(target_script_regex, text).group()
                        final_text = text.replace(del_text, '')
                        log.debug(f"正则拿到json_str:{final_text}")
                        try:
                            target_dict = self._try_parse_json(final_text)
                            return target_dict
                        except Exception as e:
                            log.error(f"格式化JSON错误:{e}")
                            return None
        log.error("未匹配到标签内的目标内容")
        return None

    def fetch(self):
        resp = self.session.get(self.url, headers=self.headers, cookies=self.cookie, timeout=10)
        curl = prepared_to_curl(resp.request)
        log.warning(f"curl请求： {curl}")
        resp.raise_for_status()
        html = resp.text
        html = html.replace('\n', '')
        log.debug(f"fetch_resp:  {html}")
        soup = BeautifulSoup(html, 'html.parser')
        script_tags = soup.find_all('script')

        def _normal_fetch():
            # 提取 playinfo 与 initial state
            reg_playinfo = r'window\.__playinfo__\s?=\s?'
            reg_initial_state = r'window\.__INITIAL_STATE__\s?=\s?'

            playinfo = self._search_scripts_from_scripts(script_tags, reg_playinfo)
            initstate = self._search_scripts_from_scripts(script_tags, reg_initial_state)

            # 取标题与 bvid
            if 'videoData' in initstate and 'title' in initstate['videoData']:
                self.title = initstate['videoData']['title']
                self.bvid = initstate.get('bvid')

            video_info = playinfo.get('data')
            dash = video_info.get('dash')
            _parse(dash, video_info)

        def _bangumi_fetch():
            # 有的在playurlSSRData中 = \{.*\}
            reg_playurl = r'playurlSSRData\s?=\s?'
            playurl_data = self._search_scripts_from_scripts(script_tags, reg_playurl)
            # 取标题与 bvid，这里的episode_id就当做bvid
            title = soup.find_all('title')[0]
            self.title = title.text
            log.debug(f"_bangumi_fetch_title: {title.text}")
            log.debug(f"_bangumi_fetch_playurl_data: {playurl_data}")
            if not playurl_data:
                log.error(f"_bangumi_fetch, 无法提取视频信息")
                raise Exception("_bangumi_fetch, 无法提取视频信息")

            result = playurl_data.get('data', {}).get('result', {})
            log.debug(f"_bangumi_fetch_result: {result}")
            self.bvid = result.get('arc').get('bvid')
            play_type = result.get('play_video_type')
            video_info = result.get('video_info')
            log.debug(f"_bangumi_fetch_play_type: {play_type}")
            log.debug(f"_bangumi_fetch_video_info: {video_info}")
            # 预览视频，基本是因为当前账户没有会员，视频是给非会员提供的预览片段
            if 'preview' in play_type:
                dash = video_info.get('durl')[0]
                if not dash:
                    raise Exception("未拿到预览视频")
                _parse(dash, video_info, is_preview=True)
            else:
                dash = video_info.get('dash')
                _parse(dash, video_info)

        def _parse(dash, video_info, is_preview=False):
            duration = dash.get('duration', 0)  # 视频时长
            if duration == 0:
                log.error(f"duration 获取为0，dash数据：{dash}")

            if is_preview:
                self.preview_video_url = dash.get('url')
                return

            # 映射 quality 到描述
            q_list = video_info.get('accept_quality', [])
            d_list = video_info.get('accept_description', [])
            q_map = {q: d for q, d in zip(q_list, d_list)}

            # 视频轨
            for v in dash.get('video', []):
                q = v.get('id')
                url = v.get('baseUrl') or v.get('base_url')
                size_mb = v['bandwidth'] * duration / 8 / 1024 / 1024
                if q and url:
                    self.video_options.append({
                        'quality': q,
                        'description': q_map.get(q, str(q)),  # 清晰 480P
                        'url': url,
                        'gear_name': f"{v['height']}P",  # 480P
                        'size_mb': round(size_mb, 2),
                        'duration':duration,    # 内容时长
                        'bandwidth': v['bandwidth'],    # # 比特率用于后续精准计算文件大小
                        'height': v['height'],
                        'width': v['width'],
                    })
            # 音频轨
            for a in dash.get('audio', []):
                q = a.get('id')
                url = a.get('baseUrl') or a.get('base_url')
                size_mb = a['bandwidth'] * duration / 8 / 1024 / 1024
                if q and url:
                    self.audio_options.append({
                        'quality': q,
                        'url': url,
                        'size_mb': round(size_mb, 2),
                        'duration': duration,   # # 内容时长
                        'bandwidth': a['bandwidth'],    # 比特率用于后续精准计算文件大小
                    })

        if '/bangumi' in self.url:
            _bangumi_fetch()
        else:
            _normal_fetch()

        # 排序，降序
        self.video_options.sort(key=lambda x: x['quality'], reverse=True)
        self.audio_options.sort(key=lambda x: x['quality'], reverse=True)
        return self
