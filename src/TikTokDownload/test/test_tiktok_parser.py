import json
import pytest
import os
import sys


# 为了让测试能够导入上一级目录的模块，需要添加到 sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from TikTokDownload.parser import TikTokParser, TikTokURLParsingError, TikTokParseError
from TikTokDownload.models import TikTokPost, TikTokMusicOption, TikTokVideoOption, TikTokImage

# Fixture for mock data
@pytest.fixture
def universal_data():
    """Load mock universal data for testing."""
    mock_file_path = os.path.join(os.path.dirname(__file__), 'mock_data', 'universal_data_mock.json')
    with open(mock_file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

@pytest.fixture
def api_detail_data():
    """Load mock API detail data for testing."""
    mock_file_path = os.path.join(os.path.dirname(__file__), 'mock_data', 'api_detail_mock.json')
    with open(mock_file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

@pytest.fixture
def tiktok_data_processor():
    """Provide an instance of TikTokParser for tests."""
    return TikTokParser()

class TestTikTokDataProcessor:

    def test_extract_short_url_valid(self, tiktok_data_processor):
        url = "https://vm.tiktok.com/ZMeXxxxx/"
        assert tiktok_data_processor.extract_short_url(url) == url

        url_with_text = "Check out this video: https://vt.tiktok.com/ZSeYyyyy/"
        assert tiktok_data_processor.extract_short_url(url_with_text) == "https://vt.tiktok.com/ZSeYyyyy/"

    def test_extract_short_url_invalid(self, tiktok_data_processor):
        with pytest.raises(TikTokURLParsingError):
            tiktok_data_processor.extract_short_url("https://www.youtube.com/watch?v=xxxx")

        with pytest.raises(TikTokURLParsingError):
            tiktok_data_processor.extract_short_url("just some text")

    def test_parse_music_data(self, tiktok_data_processor, universal_data):
        music_raw = universal_data["WebAppPage"]["itemInfo"]["itemStruct"]["music"]
        music_option = tiktok_data_processor._parse_music_data(music_raw)

        assert isinstance(music_option, TikTokMusicOption)
        assert music_option.id == "78901234567"
        assert music_option.title == "测试背景音乐"
        assert music_option.author_name == "音乐作者"
        assert music_option.url == "https://example.com/tiktok_music.mp3"
        assert music_option.cover_url == "https://example.com/tiktok_music_cover.jpg"
        assert music_option.duration == 30
        assert music_option.album == "测试专辑"

    def test_parse_video_files(self, tiktok_data_processor, universal_data):
        video_raw = universal_data["WebAppPage"]["itemInfo"]["itemStruct"]["video"]
        aweme_id = universal_data["WebAppPage"]["itemInfo"]["itemStruct"]["id"]
        video_files = tiktok_data_processor._parse_video_datas(video_raw, aweme_id)

        assert isinstance(video_files, list)
        assert len(video_files) == 2

        # Test 1080p option
        v_1080p = next((v for v in video_files if v.resolution == 1080), None)
        assert v_1080p is not None
        assert v_1080p.aweme_id == aweme_id
        assert v_1080p.bit_rate == 2000
        assert v_1080p.url == "https://example.com/tiktok_video_1080p.mp4?nodewatermark=1"
        assert v_1080p.size_mb == pytest.approx(20.0) # 20971520 bytes / (1024*1024)
        assert v_1080p.height == 1080
        assert v_1080p.width == 720
        assert v_1080p.duration == 15

        # Test 720p option
        v_720p = next((v for v in video_files if v.resolution == 720), None)
        assert v_720p is not None
        assert v_720p.url == "https://example.com/tiktok_video_720p.mp4?nodewatermark=1"
        assert v_720p.size_mb == pytest.approx(10.0) # 10485760 bytes / (1024*1024)

    def test_parse_image_data(self, tiktok_data_processor, universal_data):
        images_raw = universal_data["WebAppPage"]["itemInfo"]["itemStruct"]["imagePost"]["images"]
        images = tiktok_data_processor._parse_image_data(images_raw)

        assert isinstance(images, list)
        assert len(images) == 2

        img1 = images[0]
        assert isinstance(img1, TikTokImage)
        assert img1.url == "img1_uri"
        assert img1.url_list == ["https://example.com/tiktok_image_1_large.jpg", "https://example.com/tiktok_image_1_medium.jpg"]
        assert img1.download_url_list == ["https://example.com/tiktok_image_1_download.jpg"]
        assert img1.width == 1080
        assert img1.height == 1920

    def test_parse_universal_data_to_tiktok_post(self, tiktok_data_processor, universal_data):
        post = tiktok_data_processor.parse_universal_data_to_tiktok_post(universal_data)

        assert isinstance(post, TikTokPost)
        assert post.aweme_id == "7123456789012345678"
        assert post.title == "这是一个测试视频的描述 #测试 #TikTok"
        assert post.description == "这是一个测试视频的描述 #测试 #TikTok"
        assert post.author_nickname == "测试用户"
        assert post.region == "US"
        assert post.is_video is True
        assert post.is_image_album is False # Universal data has both video and imagePost, but it's a video item.
        assert len(post.video) == 2
        assert post.music is not None
        assert post.view_count == 100000
        assert post.like_count == 5000
        assert post.hashtags == ["挑战一", "挑战二"]
        assert post.cover_image_url == "https://example.com/tiktok_video_cover.jpg"

    def test_parse_api_detail_to_tiktok_post(self, tiktok_data_processor, api_detail_data):
        post = tiktok_data_processor.parse_api_detail_to_tiktok_post(api_detail_data)

        assert isinstance(post, TikTokPost)
        assert post.aweme_id == "7123456789012345678"
        assert post.title == "这是一个API测试视频的描述 #API测试"
        assert post.description == "这是一个API测试视频的描述 #API测试"
        assert post.author_nickname == "API测试用户"
        assert post.region == "JP"
        assert post.is_video is True
        assert post.is_image_album is False
        assert len(post.video) == 2
        assert post.music is not None
        assert post.view_count == 200000
        assert post.like_count == 6000
        assert post.hashtags == ["API标签一", "API标签二"]
        assert post.cover_image_url == "https://example.com/tiktok_api_video_cover.jpg"

    def test_parse_universal_data_image_album_only(self, tiktok_data_processor, universal_data):
        # Modify universal_data to simulate an image album post
        image_album_data = universal_data.copy()
        item_struct = image_album_data["WebAppPage"]["itemInfo"]["itemStruct"]
        item_struct["video"] = {} # Remove video data
        item_struct["is_image_album"] = True # Explicitly set for testing

        post = tiktok_data_processor.parse_universal_data_to_tiktok_post(image_album_data)

        assert isinstance(post, TikTokPost)
        assert post.is_video is False
        assert post.is_image_album is True
        assert len(post.video) == 0
        assert len(post.images) == 2
        assert post.images[0].url == "img1_uri"
        assert post.images[0].download_url_list == ["https://example.com/tiktok_image_1_download.jpg"]