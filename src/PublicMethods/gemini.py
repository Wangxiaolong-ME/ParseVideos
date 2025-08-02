import os
import json
import time
from itertools import cycle
from datetime import datetime

from google import genai
from google.genai import types
import logging

log = logging.getLogger(__name__)


class GeminiClient:
    """
    Google Gemini API 客户端封装：
      - 支持文本和图片（内联字节或 URL）输入
      - 链式调用：reset → set_model → add_text / add_image_inline / add_image_uri → generate
    """

    def __init__(self, api_key: str = None):
        self.model = None
        self.api_keys = []
        self.key_iterator = None
        if not api_key:
            self._init_api_key()
            if not self.api_keys:
                raise ValueError("请通过环境变量 GEMINI_API_KEYS 提供 API Key")
            self.api_key = self._get_next_api_key()
        else:
            self.api_key = api_key
        # 初始化 SDK 客户端
        self.client = None
        self.reset()

    def _init_api_key(self):
        api_keys_str = os.getenv("GEMINI_API_KEYS")
        log.debug(f"gemini_keys:{api_keys_str}")
        if not api_keys_str:
            return
        try:
            # 假设环境变量是JSON字符串数组，例如 '["key1", "key2"]'
            self.api_keys = json.loads(api_keys_str)
            log.debug("gemini keys 为json字符串")
            if isinstance(self.api_keys, list) and self.api_keys:
                self.key_iterator = cycle(self.api_keys)
        except (json.JSONDecodeError, TypeError):
            # 对逗号分隔的密钥进行回退
            if isinstance(api_keys_str, str):
                self.api_keys = [key.strip() for key in api_keys_str.split(',')]
                log.debug("gemini keys 为list列表")
                self.api_keys[0] = self.api_keys[0].strip('[')
                self.api_keys[-1] = self.api_keys[-1].strip(']')
                if self.api_keys:
                    self.key_iterator = cycle(self.api_keys)

    def _get_next_api_key(self):
        if not self.key_iterator:
            return None
        key = next(self.key_iterator)
        log.debug(f"选取 gemini keys-{self.api_keys.index(key)} {key[:15]}*****")
        return next(self.key_iterator)

    def reset(self):
        """重置内容列表，准备新一轮请求"""
        self.contents = []  # 直接存放 types.Part 或 str
        self.set_model("gemini-2.5-pro")
        log.debug(f"")
        # 如果需要，每次重置也可以轮换密钥
        self.api_key = self._get_next_api_key()
        if self.api_key:
            self.client = self.test_connectivity()
        return self

    def set_model(self, model: str):
        """
        指定要使用的模型名称，
        例如 "gemini-2.5-flash" 或 "gemini-1.5-flash-001"
        """
        self.model = model
        log.debug(f"设置模型为:{model}")
        return self

    def add_text(self, text: str):
        """追加一段文本提示"""
        self.contents.append(text)
        return self

    def add_image_inline(self, image_path: str, mime_type: str = "image/jpeg"):
        """
        将本地小文件（<20MB）以内联字节方式传入。
        调用 types.Part.from_bytes() 构造图像 Part。:contentReference[oaicite:0]{index=0}

        Args:
          image_path: 本地图片路径
          mime_type: 图片 MIME 类型，如 "image/jpeg" 或 "image/png"
        """
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        part = types.Part.from_bytes(
            data=image_bytes,
            mime_type=mime_type
        )
        self.contents.append(part)
        return self

    def add_image_uri(self, uri: str):
        """
        将可公开访问的图片 URI 传入，让后端拉取。:contentReference[oaicite:1]{index=1}
        """
        part = types.Part.from_uri(
            uri=uri,
            mime_type=None  # SDK 根据 URI 扩展名自动识别
        )
        self.contents.append(part)
        return self

    def generate(self, config: types.GenerateContentConfig = None):
        """
        发起生成请求，返回 Response 对象。

        要传入生成参数，如 max_output_tokens、temperature、top_p 等，
        请先构造 GenerateContentConfig 对象并通过 config 参数传入。:contentReference[oaicite:2]{index=2}
        """
        if not self.model:
            raise ValueError("请先调用 set_model() 指定模型名称")
        return self.client.models.generate_content(
            model=self.model,
            contents=self.contents,
            config=config
        )

    def test_connectivity(self):
        """
        测试提供的 API Key 是否有效。
        """
        if not self.api_key:
            return None
        try:
            client = genai.client.Client(api_key=self.api_key)
            # 一个简单、低成本的操作来测试连接性
            list(client.models.list())
            return client
        except Exception as e:
            return None


gemini = GeminiClient()

if __name__ == '__main__':
    i = 0
    while i < 3:
        gemini.reset()
        gemini.add_text("hi there")
        r = gemini.generate()
        print(r.text)
        time.sleep(5)
        i += 1
