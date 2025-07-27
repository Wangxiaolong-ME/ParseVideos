# tests/test_parsers.py
import pytest
from pathlib import Path

# 直接引入重构后的解析器
from TelegramBot.parsers.bilibili_parser import BilibiliParser, ParseResult
from TelegramBot.parsers.music_parser import MusicParser

# ---- 测试 BilibiliParser ----

class DummyPostPreview:
    """模拟 preview_video 分支的返回对象"""
    def __init__(self):
        self.preview_video = "https://www.bilibili.com/video/BV182xPeEEAc/"
        self.title = "测试视频"
        self.bvid = "BV_TEST"
        # preview_video_download 返回的 base name
    def preview_video_download(self):
        return "preview_file"
    def fetch(self):
        return self

class DummyPostBigVideo:
    """模拟 size_mb > 50 分支的返回对象"""
    def __init__(self):
        self.preview_video = None
        self.title = "大文件测试"
        self.bvid = "BV_BIG"
        self.selected_video = {"url": "https://www.bilibili.com/video/BV182xPeEEAc/"}
        self.gear_name = "720P"
        self.size_mb = 60
        self.width = 1280
        self.height = 720
        self.duration = 42
    def fetch(self):
        return self
    def filter_by_size(self, max_mb):
        # 同原代码，无需修改
        return

@pytest.fixture(autouse=True)
def patch_bili_dependencies(monkeypatch, tmp_path):
    from TelegramBot.parsers import bilibili_parser as mod

    # BilibiliPost 构造函数先返回一个实例，再 .fetch() 拿到 DummyPost
    def fake_factory(url, threads, cookie):
        # 根据 url 决定返回哪种 DummyPost
        if "preview" in url:
            return DummyPostPreview()
        else:
            return DummyPostBigVideo()
    monkeypatch.setattr(mod, "BilibiliPost", fake_factory)

    # 不需要真实文件，直接返回一个固定大小
    monkeypatch.setattr(mod, "check_file_size", lambda *args, **kwargs: 1.0)

    # 测试时都写到 tmp_path
    monkeypatch.setenv("BILI_SAVE_DIR", str(tmp_path))

    return tmp_path

def test_bilibili_parser_preview(tmp_path):
    """preview_video=True 的分支应当返回 video 媒体项"""
    url = "https://www.bilibili.com/video/BV1kWgkzAE2u"
    parser = BilibiliParser(url, save_dir=Path(tmp_path))
    res: ParseResult = parser.parse()

    assert res.success is True
    assert res.content_type == "video"
    # download_url 来自 DummyPostPreview.preview_video
    assert res.download_url == "https://www.bilibili.com/video/BV182xPeEEAc/"
    # 媒体列表应该只有一个本地文件项
    assert len(res.media_items) == 1
    mp = res.media_items[0]
    assert mp.local_path.name == "preview_file.mp4"

def test_bilibili_parser_big_file(tmp_path):
    """size_mb>50 的分支应当返回 link 类型，并生成 Markdown 链接"""
    url = "https://bilibili.com/not_preview"
    parser = BilibiliParser(url, save_dir=Path(tmp_path))
    res = parser.parse()

    assert res.success is True
    assert res.content_type == "link"
    # text_message 中应包含 “点击下方链接下载”
    assert "点击下方链接下载" in res.text_message
    # download_url 来自 DummyPostBigVideo.selected_video
    assert "http://fake/big.mp4" in res.text_message

# ---- 测试 MusicParser ----

@pytest.fixture(autouse=True)
def patch_music_dependencies(monkeypatch, tmp_path):
    from TelegramBot.parsers import music_parser as mod

    # get_download_link(target, return_song_id=True) -> (_, song_name, song_id)
    monkeypatch.setattr(mod, "get_download_link", lambda tgt, return_song_id: (None, "我的歌", "321"))

    # download_single: 在 output_dir 下生成文件，并返回 (url, download_url)
    def fake_download_single(target, output_dir):
        out = Path(output_dir) / "我的歌.mp3"
        out.write_bytes(b"dummy content")
        return "http://fake/url", "http://fake/download"
    monkeypatch.setattr(mod, "download_single", fake_download_single)

    # 环境变量或配置
    monkeypatch.setenv("MUSIC_SAVE_DIR", str(tmp_path))
    return tmp_path

def test_music_parser_download(tmp_path):
    """首次下载：文件不存在，应调用 download_single 并生成媒体项"""
    parser = MusicParser("任意ID", save_dir=Path(tmp_path))
    res = parser.parse()

    assert res.success is True
    assert res.vid == "MUSIC321"
    assert res.title == "我的歌"
    # 本地文件确实写进了 tmp_path
    expected = tmp_path / "我的歌.mp3"
    assert expected.exists()
    assert len(res.media_items) == 1
    assert res.media_items[0].file_type == "audio"

def test_music_parser_cache_hit(tmp_path, monkeypatch):
    """缓存命中：文件已存在时，不调用 download_single"""
    p = tmp_path / "我的歌.mp3"
    p.write_bytes(b"already there")

    called = False
    def fake_download_single2(target, output_dir):
        nonlocal called
        called = True
        return ("", "")
    monkeypatch.setattr("TelegramBot.parsers.music_parser.download_single", fake_download_single2)

    parser = MusicParser("任意ID", save_dir=Path(tmp_path))
    res = parser.parse()

    assert res.success is True
    # download_single 不应被调用
    assert not called
    # 媒体列表依旧包含那个已存在文件
    assert res.media_items[0].local_path == p
