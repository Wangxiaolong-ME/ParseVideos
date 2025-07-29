import httpx
import re
import json
from typing import Optional, Dict, Any
import logging

log = logging.getLogger(__name__)


class TikTokScraper:
    """
    用于从 TikTok 视频页面抓取数据的类。
    """

    def __init__(self, user_agent: str):
        self.headers = {
            "User-Agent": user_agent
        }
        self.client = httpx.Client(headers=self.headers, follow_redirects=True)

    def fetch_page_content(self, url: str) -> Optional[str]:
        """
        发送 GET 请求获取指定 URL 的页面内容。
        """
        try:
            log.debug(f"正在请求 URL: {url}")
            response = self.client.get(url, timeout=10, headers={"Referer": url})
            response.raise_for_status()
            log.debug(f"请求成功，状态码: {response.status_code}")
            return response.text
        except httpx.HTTPStatusError as e:
            log.warning(f"HTTP 错误发生: {e.response.status_code} - {e.response.text}")
            return None
        except httpx.RequestError as e:
            log.warning(f"请求发生错误: {e}")
            return None
        except Exception as e:
            log.warning(f"发生意外错误: {e}")
            return None

    @staticmethod
    # --- extract_universal_data 函数保持不变，用于提取通用数据 ---
    def extract_universal_data(html_content: str) -> Optional[Dict[str, Any]]:
        """
        从 HTML 内容中提取 <script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">
        标签下的 JSON 数据。
        """
        if not html_content:
            return None

        pattern = re.compile(r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">(.*?)</script>',
                             re.DOTALL)
        match = pattern.search(html_content)

        if match:
            json_str = match.group(1)
            try:
                data = json.loads(json_str)
                log.info("成功提取HTML内容__UNIVERSAL_DATA_FOR_REHYDRATION__")
                return data
            except json.JSONDecodeError as e:
                log.warning(f"解析 __UNIVERSAL_DATA_FOR_REHYDRATION__ 中的 JSON 数据失败: {e}")
                return None
            except Exception as e:
                log.warning(f"处理 __UNIVERSAL_DATA_FOR_REHYDRATION__ 数据时发生未知错误: {e}")
                return None
        else:
            return None

    def close(self):
        """
        关闭 httpx 客户端连接。
        """
        self.client.close()
