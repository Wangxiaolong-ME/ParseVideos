# -*- coding: utf-8 -*-
"""
抖音下载模块测试用例
测试 DouyinPost 类的各种功能，包括解析、筛选、下载等操作
"""
import pytest
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from typing import List

# 导入被测试的模块
import sys
sys.path.append('.')
from src.DouyinDownload.douyin_post import DouyinPost
from src.DouyinDownload.models import VideoOption
from src.DouyinDownload.exceptions import ParseError, DouyinDownloadException


class TestDouyinPost:
    """抖音下载核心类测试"""
    
    # 测试用的抖音链接
    TEST_DOUYIN_VIDEO_URL = "https://v.douyin.com/iRNBho6G/"
    TEST_DOUYIN_IMAGE_URL = "https://v.douyin.com/iRNBho6H/"
    
    # 模拟的视频选项数据
    MOCK_VIDEO_OPTIONS = [
        VideoOption(
            resolution=720,
            bitrate=1000000,
            size_mb=15.5,
            url="https://mock-video-720p.mp4",
            format_id="720p"
        ),
        VideoOption(
            resolution=1080,
            bitrate=2000000,
            size_mb=25.8,
            url="https://mock-video-1080p.mp4",
            format_id="1080p"
        ),
        VideoOption(
            resolution=480,
            bitrate=500000,
            size_mb=8.2,
            url="https://mock-video-480p.mp4",
            format_id="480p"
        )
    ]
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录用于测试"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def douyin_post(self, temp_dir):
        """创建DouyinPost实例用于测试"""
        return DouyinPost(
            short_url_text=self.TEST_DOUYIN_VIDEO_URL,
            save_dir=temp_dir,
            trust_env=False,
            threads=4
        )
    
    @pytest.fixture
    def mock_parser_response(self):
        """模拟解析器返回的数据"""
        return {
            'title': '测试抖音视频标题',
            'video_options': self.MOCK_VIDEO_OPTIONS,
            'content_type': 'video',
            'duration': 30,
            'author': '测试用户'
        }
    
    def test_01_douyin_post_initialization(self, temp_dir):
        """测试1: 测试DouyinPost类的初始化"""
        # 测试正常初始化
        post = DouyinPost(
            short_url_text=self.TEST_DOUYIN_VIDEO_URL,
            save_dir=temp_dir
        )
        
        assert post.short_url == self.TEST_DOUYIN_VIDEO_URL
        assert post.save_dir == temp_dir
        assert post.video_title is None  # 初始化时为空
        assert post.raw_video_options == []
        assert post.processed_video_options == []
        
        # 测试默认参数
        post_default = DouyinPost(short_url_text=self.TEST_DOUYIN_VIDEO_URL)
        assert post_default.save_dir is not None
        assert post_default.threads > 0
    
    @patch('DouyinDownload.douyin_post.DouyinParser')
    async def test_02_fetch_details_success(self, mock_parser, douyin_post, mock_parser_response):
        """测试2: 测试成功获取视频详情"""
        # 设置mock解析器
        mock_instance = Mock()
        mock_instance.parse.return_value = mock_parser_response
        mock_parser.return_value = mock_instance
        
        # 执行获取详情
        result = await douyin_post.fetch_details()
        
        # 验证结果
        assert result is douyin_post  # 返回自身支持链式调用
        assert douyin_post.video_title == '测试抖音视频标题'
        assert len(douyin_post.raw_video_options) == 3
        assert len(douyin_post.processed_video_options) == 3  # 初始时processed等于raw
        
        # 验证解析器被正确调用
        mock_parser.assert_called_once()
        mock_instance.parse.assert_called_once()
    
    @patch('DouyinDownload.douyin_post.DouyinParser')
    async def test_03_fetch_details_parse_error(self, mock_parser, douyin_post):
        """测试3: 测试解析失败的情况"""
        # 设置mock解析器抛出异常
        mock_instance = Mock()
        mock_instance.parse.side_effect = ParseError("解析失败")
        mock_parser.return_value = mock_instance
        
        # 验证抛出异常
        with pytest.raises(DouyinDownloadException) as exc_info:
            await douyin_post.fetch_details()
        
        assert "解析失败" in str(exc_info.value)
    
    def test_04_get_content_type_detection(self, douyin_post):
        """测试4: 测试内容类型检测"""
        # 测试视频链接
        video_type = douyin_post.get_content_type(self.TEST_DOUYIN_VIDEO_URL)
        assert video_type in ['video', 'image']  # 根据实际链接特征判断
        
        # 测试图片链接
        image_type = douyin_post.get_content_type(self.TEST_DOUYIN_IMAGE_URL)
        assert image_type in ['video', 'image']
    
    def test_05_sort_options_by_resolution(self, douyin_post):
        """测试5: 测试按分辨率排序功能"""
        # 设置测试数据
        douyin_post.processed_video_options = self.MOCK_VIDEO_OPTIONS.copy()
        
        # 测试降序排序（默认）
        result = douyin_post.sort_options(by='resolution', descending=True)
        assert result is douyin_post  # 支持链式调用
        
        resolutions = [opt.resolution for opt in douyin_post.processed_video_options]
        assert resolutions == [1080, 720, 480]  # 降序排列
        
        # 测试升序排序
        douyin_post.sort_options(by='resolution', descending=False)
        resolutions = [opt.resolution for opt in douyin_post.processed_video_options]
        assert resolutions == [480, 720, 1080]  # 升序排列
    
    def test_06_sort_options_by_bitrate(self, douyin_post):
        """测试6: 测试按码率排序功能"""
        douyin_post.processed_video_options = self.MOCK_VIDEO_OPTIONS.copy()
        
        # 按码率降序排序
        douyin_post.sort_options(by='bitrate', descending=True)
        bitrates = [opt.bitrate for opt in douyin_post.processed_video_options]
        assert bitrates == [2000000, 1000000, 500000]
    
    def test_07_sort_options_by_size(self, douyin_post):
        """测试7: 测试按文件大小排序功能"""
        douyin_post.processed_video_options = self.MOCK_VIDEO_OPTIONS.copy()
        
        # 按文件大小降序排序
        douyin_post.sort_options(by='size_mb', descending=True)
        sizes = [opt.size_mb for opt in douyin_post.processed_video_options]
        assert sizes == [25.8, 15.5, 8.2]
    
    def test_08_filter_by_size_range(self, douyin_post):
        """测试8: 测试按文件大小范围筛选"""
        douyin_post.processed_video_options = self.MOCK_VIDEO_OPTIONS.copy()
        
        # 筛选10MB到20MB之间的视频
        result = douyin_post.filter_by_size(min_mb=10.0, max_mb=20.0)
        assert result is douyin_post  # 支持链式调用
        
        # 验证筛选结果
        assert len(douyin_post.processed_video_options) == 1
        assert douyin_post.processed_video_options[0].size_mb == 15.5
    
    def test_09_filter_by_min_size_only(self, douyin_post):
        """测试9: 测试只设置最小文件大小筛选"""
        douyin_post.processed_video_options = self.MOCK_VIDEO_OPTIONS.copy()
        
        # 筛选大于15MB的视频
        douyin_post.filter_by_size(min_mb=15.0)
        
        # 验证结果
        assert len(douyin_post.processed_video_options) == 2
        sizes = [opt.size_mb for opt in douyin_post.processed_video_options]
        assert all(size >= 15.0 for size in sizes)
    
    def test_10_filter_by_max_size_only(self, douyin_post):
        """测试10: 测试只设置最大文件大小筛选"""
        douyin_post.processed_video_options = self.MOCK_VIDEO_OPTIONS.copy()
        
        # 筛选小于20MB的视频
        douyin_post.filter_by_size(max_mb=20.0)
        
        # 验证结果
        assert len(douyin_post.processed_video_options) == 2
        sizes = [opt.size_mb for opt in douyin_post.processed_video_options]
        assert all(size <= 20.0 for size in sizes)
    
    def test_11_deduplicate_by_highest_bitrate(self, douyin_post):
        """测试11: 测试按最高码率去重"""
        # 创建包含重复分辨率的测试数据
        duplicate_options = [
            VideoOption(resolution=720, bitrate=1000000, size_mb=15.5, url="url1", format_id="720p_1"),
            VideoOption(resolution=720, bitrate=1500000, size_mb=18.2, url="url2", format_id="720p_2"),  # 更高码率
            VideoOption(resolution=1080, bitrate=2000000, size_mb=25.8, url="url3", format_id="1080p"),
        ]
        douyin_post.processed_video_options = duplicate_options
        
        # 执行去重
        result = douyin_post.deduplicate_by_resolution(keep='highest_bitrate')
        assert result is douyin_post
        
        # 验证结果
        assert len(douyin_post.processed_video_options) == 2  # 720p重复项被去除
        resolutions = [opt.resolution for opt in douyin_post.processed_video_options]
        assert set(resolutions) == {720, 1080}
        
        # 验证保留的是高码率版本
        for opt in douyin_post.processed_video_options:
            if opt.resolution == 720:
                assert opt.bitrate == 1500000
    
    def test_12_deduplicate_by_lowest_bitrate(self, douyin_post):
        """测试12: 测试按最低码率去重"""
        duplicate_options = [
            VideoOption(resolution=720, bitrate=1000000, size_mb=15.5, url="url1", format_id="720p_1"),  # 更低码率
            VideoOption(resolution=720, bitrate=1500000, size_mb=18.2, url="url2", format_id="720p_2"),
            VideoOption(resolution=1080, bitrate=2000000, size_mb=25.8, url="url3", format_id="1080p"),
        ]
        douyin_post.processed_video_options = duplicate_options
        
        # 执行去重
        douyin_post.deduplicate_by_resolution(keep='lowest_bitrate')
        
        # 验证保留的是低码率版本
        for opt in douyin_post.processed_video_options:
            if opt.resolution == 720:
                assert opt.bitrate == 1000000
    
    def test_13_deduplicate_by_largest_size(self, douyin_post):
        """测试13: 测试按最大文件大小去重"""
        duplicate_options = [
            VideoOption(resolution=720, bitrate=1000000, size_mb=15.5, url="url1", format_id="720p_1"),
            VideoOption(resolution=720, bitrate=1500000, size_mb=18.2, url="url2", format_id="720p_2"),  # 更大文件
            VideoOption(resolution=1080, bitrate=2000000, size_mb=25.8, url="url3", format_id="1080p"),
        ]
        douyin_post.processed_video_options = duplicate_options
        
        # 执行去重
        douyin_post.deduplicate_by_resolution(keep='largest_size')
        
        # 验证保留的是大文件版本
        for opt in douyin_post.processed_video_options:
            if opt.resolution == 720:
                assert opt.size_mb == 18.2
    
    def test_14_get_option_by_resolution(self, douyin_post):
        """测试14: 测试按指定分辨率获取选项"""
        douyin_post.processed_video_options = self.MOCK_VIDEO_OPTIONS.copy()
        
        # 获取720p选项
        option = douyin_post.get_option(resolution=720)
        assert option is not None
        assert option.resolution == 720
        
        # 获取不存在的分辨率
        option = douyin_post.get_option(resolution=2160)
        assert option is None
    
    def test_15_get_option_highest_resolution_strategy(self, douyin_post):
        """测试15: 测试获取最高分辨率选项策略"""
        douyin_post.processed_video_options = self.MOCK_VIDEO_OPTIONS.copy()
        
        # 获取最高分辨率选项
        option = douyin_post.get_option(strategy="highest_resolution")
        assert option is not None
        assert option.resolution == 1080  # 最高分辨率
    
    def test_16_get_option_lowest_resolution_strategy(self, douyin_post):
        """测试16: 测试获取最低分辨率选项策略"""
        douyin_post.processed_video_options = self.MOCK_VIDEO_OPTIONS.copy()
        
        # 获取最低分辨率选项
        option = douyin_post.get_option(strategy="lowest_resolution")
        assert option is not None
        assert option.resolution == 480  # 最低分辨率
    
    def test_17_get_option_highest_bitrate_strategy(self, douyin_post):
        """测试17: 测试获取最高码率选项策略"""
        douyin_post.processed_video_options = self.MOCK_VIDEO_OPTIONS.copy()
        
        # 获取最高码率选项
        option = douyin_post.get_option(strategy="highest_bitrate")
        assert option is not None
        assert option.bitrate == 2000000  # 最高码率
    
    def test_18_get_option_empty_options(self, douyin_post):
        """测试18: 测试空选项列表情况"""
        douyin_post.processed_video_options = []
        
        # 所有策略都应该返回None
        assert douyin_post.get_option(resolution=720) is None
        assert douyin_post.get_option(strategy="highest_resolution") is None
        assert douyin_post.get_option(strategy="lowest_resolution") is None
    
    @patch('DouyinDownload.douyin_post.Downloader')
    async def test_19_download_video_by_resolution(self, mock_downloader, douyin_post, temp_dir):
        """测试19: 测试按指定分辨率下载视频"""
        # 设置测试数据
        douyin_post.video_title = "测试视频"
        douyin_post.processed_video_options = self.MOCK_VIDEO_OPTIONS.copy()
        
        # 模拟下载器
        mock_instance = Mock()
        mock_instance.download.return_value = os.path.join(temp_dir, "test_video_720p.mp4")
        mock_downloader.return_value = mock_instance
        
        # 执行下载
        saved_paths = await douyin_post.download_video(resolution=720)
        
        # 验证结果
        assert len(saved_paths) == 1
        assert "720p" in saved_paths[0] or "test_video" in saved_paths[0]
        
        # 验证下载器被调用
        mock_instance.download.assert_called_once()
    
    @patch('DouyinDownload.douyin_post.Downloader')
    async def test_20_download_all_videos(self, mock_downloader, douyin_post, temp_dir):
        """测试20: 测试下载所有可用分辨率视频"""
        # 设置测试数据
        douyin_post.video_title = "测试视频"
        douyin_post.processed_video_options = self.MOCK_VIDEO_OPTIONS.copy()
        
        # 模拟下载器
        mock_instance = Mock()
        mock_instance.download.side_effect = [
            os.path.join(temp_dir, "test_video_480p.mp4"),
            os.path.join(temp_dir, "test_video_720p.mp4"),
            os.path.join(temp_dir, "test_video_1080p.mp4")
        ]
        mock_downloader.return_value = mock_instance
        
        # 执行下载所有
        saved_paths = await douyin_post.download_video(download_all=True)
        
        # 验证结果
        assert len(saved_paths) == 3
        assert mock_instance.download.call_count == 3
    
    def test_21_save_metadata(self, douyin_post, temp_dir):
        """测试21: 测试保存元数据功能"""
        # 设置测试数据
        douyin_post.video_title = "测试视频"
        douyin_post.raw_video_options = self.MOCK_VIDEO_OPTIONS.copy()
        douyin_post.processed_video_options = self.MOCK_VIDEO_OPTIONS.copy()
        
        # 保存元数据
        saved_path = douyin_post.save_metadata()
        
        # 验证文件存在
        assert os.path.exists(saved_path)
        assert saved_path.endswith('.json')
        
        # 验证文件内容
        with open(saved_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        assert metadata['video_title'] == "测试视频"
        assert len(metadata['raw_video_options']) == 3
        assert len(metadata['processed_video_options']) == 3
    
    def test_22_save_metadata_custom_path(self, douyin_post, temp_dir):
        """测试22: 测试保存元数据到指定路径"""
        # 设置测试数据
        douyin_post.video_title = "测试视频"
        douyin_post.raw_video_options = self.MOCK_VIDEO_OPTIONS.copy()
        
        # 指定保存路径
        custom_path = os.path.join(temp_dir, "custom_metadata.json")
        saved_path = douyin_post.save_metadata(filepath=custom_path)
        
        # 验证保存到指定路径
        assert saved_path == custom_path
        assert os.path.exists(custom_path)
    
    def test_23_load_from_metadata(self, temp_dir):
        """测试23: 测试从元数据文件加载DouyinPost实例"""
        # 创建测试元数据文件
        metadata = {
            'short_url': self.TEST_DOUYIN_VIDEO_URL,
            'video_title': '从元数据加载的视频',
            'raw_video_options': [opt.__dict__ for opt in self.MOCK_VIDEO_OPTIONS],
            'processed_video_options': [opt.__dict__ for opt in self.MOCK_VIDEO_OPTIONS],
            'save_dir': temp_dir
        }
        
        metadata_path = os.path.join(temp_dir, "test_metadata.json")
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        # 从元数据加载
        loaded_post = DouyinPost.load_from_metadata(metadata_path)
        
        # 验证加载结果
        assert loaded_post.short_url == self.TEST_DOUYIN_VIDEO_URL
        assert loaded_post.video_title == '从元数据加载的视频'
        assert len(loaded_post.raw_video_options) == 3
        assert loaded_post.save_dir == temp_dir
    
    def test_24_chain_operations(self, douyin_post):
        """测试24: 测试链式操作功能"""
        # 设置测试数据
        douyin_post.processed_video_options = self.MOCK_VIDEO_OPTIONS.copy()
        
        # 执行链式操作：筛选大小 -> 去重 -> 排序
        result = (douyin_post
                 .filter_by_size(min_mb=10.0)
                 .deduplicate_by_resolution(keep='highest_bitrate')
                 .sort_options(by='resolution', descending=True))
        
        # 验证每个操作都返回自身支持链式调用
        assert result is douyin_post
        
        # 验证操作结果
        assert len(douyin_post.processed_video_options) >= 1
        # 验证是按分辨率降序排列的
        if len(douyin_post.processed_video_options) > 1:
            resolutions = [opt.resolution for opt in douyin_post.processed_video_options]
            assert resolutions == sorted(resolutions, reverse=True)
    
    def test_25_error_handling_invalid_url(self, temp_dir):
        """测试25: 测试无效URL的错误处理"""
        # 测试空URL
        with pytest.raises((ValueError, DouyinDownloadException)):
            DouyinPost(short_url_text="", save_dir=temp_dir)
        
        # 测试无效URL格式
        with pytest.raises((ValueError, DouyinDownloadException)):
            DouyinPost(short_url_text="not_a_valid_url", save_dir=temp_dir)


class TestVideoOption:
    """测试VideoOption数据模型"""
    
    def test_26_video_option_creation(self):
        """测试26: 测试VideoOption对象创建"""
        option = VideoOption(
            resolution=1080,
            bitrate=2000000,
            size_mb=25.8,
            url="https://test-video.mp4",
            format_id="1080p"
        )
        
        assert option.resolution == 1080
        assert option.bitrate == 2000000
        assert option.size_mb == 25.8
        assert option.url == "https://test-video.mp4"
        assert option.format_id == "1080p"
    
    def test_27_video_option_comparison(self):
        """测试27: 测试VideoOption对象比较"""
        option1 = VideoOption(resolution=720, bitrate=1000000, size_mb=15.5, url="url1", format_id="720p")
        option2 = VideoOption(resolution=1080, bitrate=2000000, size_mb=25.8, url="url2", format_id="1080p")
        
        # 测试不同选项不相等
        assert option1 != option2
        
        # 测试相同选项相等
        option3 = VideoOption(resolution=720, bitrate=1000000, size_mb=15.5, url="url1", format_id="720p")
        assert option1 == option3


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "--tb=short"])