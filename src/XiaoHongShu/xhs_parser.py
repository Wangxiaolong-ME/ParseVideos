import json
import re
import requests
from bs4 import BeautifulSoup
from PublicMethods.tools import prepared_to_curl
from PublicMethods.m_download import Downloader
import logging
from TelegramBot.config import XIAOHONGSHU_SAVE_DIR
from XiaoHongShu.config import XHS_DOWNLOAD_HEADERS

log = logging.getLogger(__name__)


class XiaohongshuPost:
    """
    该类用于解析小红书的页面，提取视频、图片、标题、描述等关键信息。
    This class is used to parse the Xiaohongshu page and extract key information such as videos, images, title, description, etc.
    """

    def __init__(self):
        self.data = None
        self.images = []
        self.videos = []
        self.download = Downloader()
        self.save_dir = XIAOHONGSHU_SAVE_DIR

    def extract_final_url(self, url_string):
        url = self.extract_short_url(url_string) or self.extract_base_url(url_string)
        if not url:
            raise ValueError("该URL不是有效的小红书URL (This is not a valid Xiaohongshu URL).")
        return url

    @staticmethod
    def is_xhs_url(url: str) -> bool:
        """
        判断给定的URL是否为小红书URL。
        Checks whether the given URL is a Xiaohongshu URL.

        参数:
        url (str): 待检查的URL。

        返回:
        bool: 如果是小红书URL返回True，否则返回False。
        """
        return bool(re.search(r'https://www\.xiaohongshu\.com/[\w\S]+', url))

    def extract_short_url(self, url: str) -> str:
        """ 提取短链接 """
        # 使用正则表达式去掉分享时可能附加的中文部分或其他参数
        match = re.search(r'https?://xhslink\.com/[\w\S]+', url)
        if u := match:
            base_url = self.download._get_final_url(u.group(), headers=XHS_DOWNLOAD_HEADERS, use_get=True)
            if base_url:
                return base_url
        return url

    @staticmethod
    def extract_base_url(url: str) -> str:
        """
        提取小红书页面的基本URL部分，去掉分享链接中的中文和不必要的参数部分。
        Extracts the base URL part from the Xiaohongshu URL, removing any extra parameters or share-related text.

        参数:
        url (str): 小红书的完整URL。

        返回:
        str: 提取出的基本URL。
        """
        # 使用正则表达式去掉分享时可能附加的中文部分或其他参数
        match = re.search(r'https://www\.xiaohongshu\.com/[\w\S]+', url)
        if match:
            return match.group(0)
        return url

    @staticmethod
    def extract_explore_id(url: str) -> str:
        """
        从小红书URL中提取explore部分的ID。

        参数:
        url (str): 小红书页面的URL。

        返回:
        str: 提取的explore ID。
        """
        # 提取explore后面的ID部分
        match = re.search(r'(?<=/)([a-zA-Z0-9]{24})\b', url)
        if match:
            return match.group(1)
        return ''

    def download_image(self, url: str, path: str):
        out = self.download._single_download(url, path, skip_head=True, headers=XHS_DOWNLOAD_HEADERS, timeout=20,
                                             retry=5)
        self.images.append(out)
        return self

    def download_video(self, url: str, path: str):
        out = self.download.download(url, path, headers=XHS_DOWNLOAD_HEADERS)
        self.videos.append(out)
        return self

    def parser_downloader(self, data):
        """
        下载所有的图片和视频。
        Downloads all images and videos from the current page.
        """
        # 遍历所有图片URL，下载并保存
        if 'images' in data and data['images']:
            for i, img_url in enumerate(data['images']):
                image_path = self.save_dir / f"image_{data['id']}_{i + 1}.jpg"  # 定义下载文件名
                try:
                    self.download_image(img_url, str(image_path))
                except Exception as e:
                    log.warning(f"图片 {i + 1} 下载失败,url:{img_url}")
                    log.warning(f"错误信息:{e}")
                log.info(f"图片 {i + 1} 下载完成，保存路径: {image_path}")

        # 遍历所有视频URL，下载并保存
        if 'videos' in data and data['videos']:
            for i, video_url in enumerate(data['videos']):
                video_path = self.save_dir / f"video_{data['id']}_{i + 1}.mp4"  # 定义下载文件名
                try:
                    self.download_video(video_url, str(video_path))
                except Exception as e:
                    log.warning(f"视频 {i + 1} 下载失败,url:{video_url}")
                    log.warning(f"错误信息:{e}")
                log.info(f"视频 {i + 1} 下载完成，保存路径: {video_path}")

        log.info("所有图片和视频下载完成。")

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

    def _parse_initial_state(self, soup: BeautifulSoup):
        """window.__INITIAL_STATE__ = {}, 取这个脚本下的json"""
        script_tags = soup.find_all('script')
        # 提取 playinfo 与 initial state
        note_detail = r'window.__INITIAL_STATE__'
        # 定义目标 JSON 所在的 JavaScript 变量名
        # 使用正则表达式匹配，确保能找到 window.__INITIAL_STATE__ = { ... }; 这种模式
        initial_state_pattern = re.compile(r'window\.__INITIAL_STATE__\s*=\s*(\{.*\})', re.DOTALL)

        # 遍历所有 script 标签
        for script in script_tags:
            if script.string:  # 如果 <script> 标签有内容
                script_content = script.string
                if script_content and isinstance(script_content, str):
                    match = initial_state_pattern.search(script_content)
                    if match:
                        json_str = match.group(1)
                        final_text = re.sub(r'\\{1,}"', '"', json_str)
                        final_text = re.sub(r'"{', '{', final_text)
                        final_text = re.sub(r'}"', '}', final_text)
                        """
                        只匹配完整的"["string"]" 或者 "[123]"格式的内容，"[玫瑰]"这种属于表情字符串，不匹配；然后替换加上不带双引号的[],从而达到去除引号的目的
                        不应匹配："[玫瑰]"
                        应匹配："["玫瑰"]"或者 "[123]"
                        "["normal_720_0","normal_720_0"]"
                        """
                        final_text = re.sub(r'"(\[(?:"[^"]+"(?:,"[^"]+")*|\d+)\])"', r'\1', final_text)
                        final_text = re.sub(r"\$?undefined",'null', final_text, 0, re.DOTALL)
                        try:
                            target_dict = self._try_parse_json(final_text)
                            return target_dict
                        except Exception as e:
                            log.error(f"格式化JSON错误:{e},处理前json_str:{final_text}")
                            return None
        log.error("未匹配到标签内的目标内容")
        return None


    def backup_parse(self, soup, explore_id):
        # 初始化字典存储提取的数据
        data = {}

        # 提取所有图片链接
        images = [meta['content'] for meta in soup.find_all('meta', attrs={'name': 'og:image'})]

        # 提取视频链接
        video_tags = soup.find_all('meta', attrs={'name': 'og:video'})

        # 提取页面的关键词
        keywords = soup.find('meta', attrs={'name': 'keywords'})['content'] if soup.find('meta', attrs={
            'name': 'keywords'}) else None

        # 提取页面的描述
        description = soup.find('meta', attrs={'name': 'description'})['content'] if soup.find('meta', attrs={
            'name': 'description'}) else None

        # 提取标题，并去除小红书后缀
        title = soup.find('meta', attrs={'name': 'og:title'})['content'] if soup.find('meta', attrs={
            'name': 'og:title'}) else None
        if title:
            title = title.replace(" - 小红书", "")

        # 提取评论数
        comment = soup.find('meta', attrs={'name': 'og:xhs:note_comment'})['content'] if soup.find('meta', attrs={
            'name': 'og:xhs:note_comment'}) else None

        # 提取点赞数
        like = soup.find('meta', attrs={'name': 'og:xhs:note_like'})['content'] if soup.find('meta', attrs={
            'name': 'og:xhs:note_like'}) else None

        # 提取收藏数
        collect = soup.find('meta', attrs={'name': 'og:xhs:note_collect'})['content'] if soup.find('meta', attrs={
            'name': 'og:xhs:note_collect'}) else None

        # 提取视频时长
        videotime = soup.find('meta', attrs={'name': 'og:videotime'})['content'] if soup.find('meta', attrs={
            'name': 'og:videotime'}) else None

        # 处理description 后的#标签
        tags = [tag.strip(' ') for tag in keywords.split(',')]
        description = re.sub(fr"#{tags[0]}.*{tags[-1]}", '', description, re.DOTALL)

        # 处理换行,空格就属于换行,但是data当中不体现
        description = re.sub(r"\s{2,}", '\\n', description, re.DOTALL)
        # 拼接标签
        tags = "#" + ' #'.join(tags)
        description += f"\n{tags}"

        # 将提取的数据存入字典
        data['id'] = explore_id
        data['title'] = title
        data['description'] = description
        data['keywords'] = keywords
        data['like'] = like
        data['collect'] = collect
        data['comment'] = comment
        data['videotime'] = videotime
        data['images'] = images
        data['videos'] = [tag['content'] for tag in video_tags] if video_tags else []

        # 提取封面图链接
        cover_img = [link.get('href') for link in soup.find_all('link', rel="preload") if link.get('href')]
        if cover_img:
            data['cover_img'] = cover_img

        # 返回格式化的JSON
        return data

    def _get_video_data(self, initial_state):
        try:
            # 核心数据路径：initial_state -> note -> noteDetailMap -> [firstNoteId] -> note
            # 这部分是提取视频数据所必需的上下文，不能删除
            first_note_id = initial_state.get("note", {}).get("firstNoteId")
            if not first_note_id:
                log.warning("未找到 'firstNoteId'，无法提取视频详情。")
                return {}

            note_detail = initial_state.get("note", {}).get("noteDetailMap", {}).get(first_note_id, {})
            note_content = note_detail.get("note", {})

            # 提取 Videos (只提取 H265 编码的视频流)
            video_streams_container = note_content.get('video', {}).get('media', {}).get('stream', {})
            extracted_videos = []

            h265_streams = video_streams_container.get('h265', [])
            for stream in h265_streams:
                master_url = stream.get('masterUrl')
                if master_url:
                    master_url = master_url.replace('\\u002F', '/')
                    extracted_videos.append(master_url)
            log.debug(f"提取 Videos ({len(extracted_videos)} 条，H265)")
            return [extracted_videos[-1]]    # 留一个就够,不然传多了都下载,视频会发多条

        except Exception as e:
            # 修改日志信息，更具体地指明是 _get_video_data 发生的错误
            log.error(f"在 _get_video_data 方法中提取数据时发生错误: {e}", exc_info=True)


    def get_xhs(self,url: str, cookies=None) -> dict:
        """
        从小红书页面中提取关键信息，包括标题、描述、关键词、图片、视频等。
        Extracts key information such as title, description, keywords, images, videos from the Xiaohongshu page.

        参数:
        url (str): 小红书页面的URL。

        返回:
        str: 格式化的JSON字符串，包含提取的数据。
        """
        if cookies is None:
            cookies = {}

        # 判断URL是否为小红书URL
        if not XiaohongshuPost.is_xhs_url(url):
            raise ValueError("该URL不是有效的小红书URL (This is not a valid Xiaohongshu URL).")

        # 提取基本的URL
        base_url = XiaohongshuPost.extract_base_url(url)

        # 提取explore部分的ID
        explore_id = XiaohongshuPost.extract_explore_id(url)
        log.info(f"Extracted Explore ID: {explore_id}")

        headers = {
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0',
        }

        try:
            # 发送GET请求并获取页面内容
            response = requests.get(base_url, headers=headers, cookies=cookies, allow_redirects=False)
            response.raise_for_status()
            curl = prepared_to_curl(response.request)
            log.debug(f"小红书请求:{curl}")
            # 输出CURL命令，方便调试
            log.info(prepared_to_curl(response.request))

            # 获取页面的文本内容
            content = response.text
        except Exception as e:
            # 如果请求失败，返回错误信息
            raise f"Error occurred: {e}"

        # 使用BeautifulSoup解析页面HTML
        soup = BeautifulSoup(content, 'html.parser')
        data = self._parse_initial_state(soup)
        parse_data = self.backup_parse(soup, explore_id)

        # 尝试获取无水印视频,如果没获取到返回兜底
        videos = self._get_video_data(data)
        if videos:
            parse_data["videos"] = videos
        return parse_data