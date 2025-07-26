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
    def get_xhs(url: str, cookies=None) -> dict:
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
