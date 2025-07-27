# -*- coding: utf-8 -*-
"""
B站下载模块测试用例
测试 BilibiliPost 类的各种功能，包括解析、筛选、下载、合并等操作
"""
import pytest
import os
import tempfile
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call

# 导入被测试的模块
from BilibiliDownload.bilibili_post import BilibiliPost
from BilibiliDownload.exceptions import BilibiliParseError, BilibiliDownloadError


class TestBilibiliPost:
    """B站下载核心类测试"""
    
    # 测试用的B站链接
    TEST_BILIBILI_VIDEO_URL = "https://www.bilibili.com/video/BV1GJ411x7h7"
    TEST_BILIBILI_BV_URL = "https://www.bilibili.com/video/BV182xPeEEAc/"
    
    # 模拟的视频/音频选项数据
    MOCK_VIDEO_OPTIONS = [
        {'quality': 80, 'description': '1080P 高清', 'url': 'https://mock-video-1080p.mp4', 'width': 1920, 'height': 1080, 'size': 52428800},
        {'quality': 64, 'description': '720P 高清', 'url': 'https://mock-video-720p.mp4', 'width': 1280, 'height': 720, 'size': 31457280},
        {'quality': 32, 'description': '480P 清晰', 'url': 'https://mock-video-480p.mp4', 'width': 854, 'height': 480, 'size': 20971520},
        {'quality': 16, 'description': '360P 流畅', 'url': 'https://mock-video-360p.mp4', 'width': 640, 'height': 360, 'size': 15728640}
    ]
    
    MOCK_AUDIO_OPTIONS = [
        {'quality': 30280, 'description': '320K', 'url': 'https://mock-audio-320k.mp3', 'size': 10485760},
        {'quality': 30232, 'description': '128K', 'url': 'https://mock-audio-128k.mp3', 'size': 4194304}
    ]
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录用于测试"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def merge_temp_dir(self):
        """创建临时合并目录用于测试"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def bilibili_post(self, temp_dir, merge_temp_dir):
        """创建BilibiliPost实例用于测试"""
        return BilibiliPost(
            url=self.TEST_BILIBILI_VIDEO_URL,
            save_dir=temp_dir,
            merge_dir=merge_temp_dir,
            threads=4
        )
    
    def test_01_bilibili_post_initialization(self, temp_dir, merge_temp_dir):
        """测试1: 测试BilibiliPost类的初始化"""
        # 测试正常初始化
        post = BilibiliPost(
            url=self.TEST_BILIBILI_VIDEO_URL,
            save_dir=temp_dir,
            merge_dir=merge_temp_dir
        )
        
        assert post.url == self.TEST_BILIBILI_VIDEO_URL
        assert post.save_dir == temp_dir
        assert post.merge_dir == merge_temp_dir
        assert post.title is None  # 初始化时为空
        assert post.bvid is None
        assert post.video_options is None
        assert post.audio_options is None
        assert post.selected_video is None
        assert post.selected_audio is None
        
        # 验证目录被创建
        assert os.path.exists(temp_dir)
        assert os.path.exists(merge_temp_dir)
    
    def test_02_bilibili_post_default_initialization(self):
        """测试2: 测试使用默认参数初始化"""
        post = BilibiliPost(url=self.TEST_BILIBILI_VIDEO_URL)
        
        assert post.url == self.TEST_BILIBILI_VIDEO_URL
        assert post.save_dir is not None
        assert post.merge_dir is not None
        assert hasattr(post, 'parser')
        assert hasattr(post, 'downloader')
    
    @patch('BilibiliDownload.bilibili_post.BilibiliParser')
    def test_03_fetch_video_info_success(self, mock_parser, bilibili_post):
        """测试3: 测试成功获取视频信息"""
        # 设置mock解析器
        mock_instance = Mock()
        mock_instance.fetch.return_value = {
            'title': '测试B站视频标题',
            'bvid': 'BV1GJ411x7h7',
            'video_options': self.MOCK_VIDEO_OPTIONS,
            'audio_options': self.MOCK_AUDIO_OPTIONS,
            'duration': 300,
            'description': '测试视频描述'
        }
        mock_parser.return_value = mock_instance
        bilibili_post.parser = mock_instance
        
        # 执行获取信息
        result = bilibili_post.fetch()
        
        # 验证结果
        assert result is bilibili_post  # 返回自身支持链式调用
        assert bilibili_post.title == '测试B站视频标题'
        assert bilibili_post.bvid == 'BV1GJ411x7h7'
        assert bilibili_post.video_options == self.MOCK_VIDEO_OPTIONS
        assert bilibili_post.audio_options == self.MOCK_AUDIO_OPTIONS
        
        # 验证解析器被正确调用
        mock_instance.fetch.assert_called_once()
    
    @patch('BilibiliDownload.bilibili_post.BilibiliParser')
    def test_04_fetch_video_info_parse_error(self, mock_parser, bilibili_post):
        """测试4: 测试解析失败的情况"""
        # 设置mock解析器抛出异常
        mock_instance = Mock()
        mock_instance.fetch.side_effect = BilibiliParseError("解析B站视频失败")
        mock_parser.return_value = mock_instance
        bilibili_post.parser = mock_instance
        
        # 验证抛出异常
        with pytest.raises(BilibiliParseError) as exc_info:
            bilibili_post.fetch()
        
        assert "解析B站视频失败" in str(exc_info.value)
    
    def test_05_filter_resolution_by_quality_id(self, bilibili_post):
        """测试5: 测试按质量ID筛选分辨率"""
        # 设置测试数据
        bilibili_post.video_options = self.MOCK_VIDEO_OPTIONS.copy()
        bilibili_post.audio_options = self.MOCK_AUDIO_OPTIONS.copy()
        
        # 筛选720P（quality=64）
        result = bilibili_post.filter_resolution(64)
        assert result is bilibili_post  # 支持链式调用
        
        # 验证选中的视频质量
        assert bilibili_post.selected_video['quality'] == 64
        assert bilibili_post.selected_video['description'] == '720P 高清'
    
    def test_06_filter_resolution_by_description(self, bilibili_post):
        """测试6: 测试按描述筛选分辨率"""
        # 设置测试数据
        bilibili_post.video_options = self.MOCK_VIDEO_OPTIONS.copy()
        bilibili_post.audio_options = self.MOCK_AUDIO_OPTIONS.copy()
        
        # 筛选1080P
        bilibili_post.filter_resolution("1080P")
        
        # 验证选中的视频质量
        assert bilibili_post.selected_video['quality'] == 80
        assert "1080P" in bilibili_post.selected_video['description']
    
    def test_07_filter_resolution_not_found(self, bilibili_post):
        """测试7: 测试筛选不存在的分辨率"""
        # 设置测试数据
        bilibili_post.video_options = self.MOCK_VIDEO_OPTIONS.copy()
        bilibili_post.audio_options = self.MOCK_AUDIO_OPTIONS.copy()
        
        # 筛选不存在的分辨率
        with pytest.raises((ValueError, BilibiliParseError)):
            bilibili_post.filter_resolution("4K")
    
    def test_08_select_highest_quality(self, bilibili_post):
        """测试8: 测试选择最高画质"""
        # 设置测试数据
        bilibili_post.video_options = self.MOCK_VIDEO_OPTIONS.copy()
        bilibili_post.audio_options = self.MOCK_AUDIO_OPTIONS.copy()
        
        # 选择最高画质
        result = bilibili_post.select_highest()
        assert result is bilibili_post  # 支持链式调用
        
        # 验证选中最高质量（quality最大值）
        assert bilibili_post.selected_video['quality'] == 80  # 1080P
        assert bilibili_post.selected_audio['quality'] == 30280  # 320K
    
    def test_09_select_lowest_quality(self, bilibili_post):
        """测试9: 测试选择最低画质"""
        # 设置测试数据
        bilibili_post.video_options = self.MOCK_VIDEO_OPTIONS.copy()
        bilibili_post.audio_options = self.MOCK_AUDIO_OPTIONS.copy()
        
        # 选择最低画质
        result = bilibili_post.select_lowest()
        assert result is bilibili_post  # 支持链式调用
        
        # 验证选中最低质量（quality最小值）
        assert bilibili_post.selected_video['quality'] == 16  # 360P
        assert bilibili_post.selected_audio['quality'] == 30232  # 128K
    
    def test_10_update_self_data_after_selection(self, bilibili_post):
        """测试10: 测试选择后数据更新"""
        # 设置测试数据
        bilibili_post.video_options = self.MOCK_VIDEO_OPTIONS.copy()
        bilibili_post.audio_options = self.MOCK_AUDIO_OPTIONS.copy()
        
        # 选择1080P
        bilibili_post.select_highest()
        bilibili_post._update_self_data()
        
        # 验证数据更新
        assert bilibili_post.width == 1920
        assert bilibili_post.height == 1080
        assert bilibili_post.gear_name == '1080P 高清'
        assert bilibili_post.size_mb > 0  # 应该计算出文件大小（MB）
    
    def test_11_filter_by_size_range(self, bilibili_post):
        """测试11: 测试按文件大小范围筛选"""
        # 设置测试数据
        bilibili_post.video_options = self.MOCK_VIDEO_OPTIONS.copy()
        bilibili_post.audio_options = self.MOCK_AUDIO_OPTIONS.copy()
        
        # 筛选20MB到40MB之间的视频
        result = bilibili_post.filter_by_size(min_mb=20.0, max_mb=40.0)
        assert result is bilibili_post  # 支持链式调用
        
        # 验证筛选结果
        for option in bilibili_post.video_options:
            size_mb = option['size'] / (1024 * 1024)
            assert 20.0 <= size_mb <= 40.0
    
    def test_12_filter_by_min_size_only(self, bilibili_post):
        """测试12: 测试只设置最小文件大小筛选"""
        # 设置测试数据
        bilibili_post.video_options = self.MOCK_VIDEO_OPTIONS.copy()
        bilibili_post.audio_options = self.MOCK_AUDIO_OPTIONS.copy()
        
        # 筛选大于30MB的视频
        bilibili_post.filter_by_size(min_mb=30.0)
        
        # 验证结果
        for option in bilibili_post.video_options:
            size_mb = option['size'] / (1024 * 1024)
            assert size_mb >= 30.0
    
    def test_13_filter_by_max_size_only(self, bilibili_post):
        """测试13: 测试只设置最大文件大小筛选"""
        # 设置测试数据
        bilibili_post.video_options = self.MOCK_VIDEO_OPTIONS.copy()
        bilibili_post.audio_options = self.MOCK_AUDIO_OPTIONS.copy()
        
        # 筛选小于25MB的视频
        bilibili_post.filter_by_size(max_mb=25.0)
        
        # 验证结果
        for option in bilibili_post.video_options:
            size_mb = option['size'] / (1024 * 1024)
            assert size_mb <= 25.0
    
    def test_14_filter_by_size_no_options(self, bilibili_post):
        """测试14: 测试没有提供筛选选项时的行为"""
        # 设置测试数据
        original_options = self.MOCK_VIDEO_OPTIONS.copy()
        bilibili_post.video_options = original_options
        
        # 不提供任何筛选参数
        bilibili_post.filter_by_size()
        
        # 验证选项未被修改
        assert bilibili_post.video_options == original_options
    
    @patch('BilibiliDownload.bilibili_post.Downloader')
    def test_15_preview_video_download(self, mock_downloader, bilibili_post, temp_dir):
        """测试15: 测试预览视频下载"""
        # 设置测试数据
        bilibili_post.title = "测试视频"
        bilibili_post.bvid = "BV1GJ411x7h7"
        bilibili_post.preview_video = "https://preview-video-url.mp4"
        
        # 模拟下载器
        mock_instance = Mock()
        expected_filename = "测试视频_BV1GJ411x7h7_preview.mp4"
        expected_path = os.path.join(temp_dir, expected_filename)
        mock_instance.download.return_value = expected_path
        mock_downloader.return_value = mock_instance
        bilibili_post.downloader = mock_instance
        
        # 执行预览视频下载
        result = bilibili_post.preview_video_download()
        
        # 验证结果
        assert result == "测试视频_BV1GJ411x7h7_preview"  # 返回基础文件名
        
        # 验证下载器被正确调用
        mock_instance.download.assert_called_once_with(
            "https://preview-video-url.mp4",
            expected_path
        )
    
    @patch('BilibiliDownload.bilibili_post.Downloader')
    def test_16_download_video_and_audio(self, mock_downloader, bilibili_post, temp_dir):
        """测试16: 测试下载视频和音频"""
        # 设置测试数据
        bilibili_post.title = "测试视频"
        bilibili_post.bvid = "BV1GJ411x7h7"
        bilibili_post.selected_video = self.MOCK_VIDEO_OPTIONS[0]  # 1080P
        bilibili_post.selected_audio = self.MOCK_AUDIO_OPTIONS[0]  # 320K
        
        # 模拟下载器
        mock_instance = Mock()
        video_path = os.path.join(temp_dir, "test_video.mp4")
        audio_path = os.path.join(temp_dir, "test_audio.mp3")
        mock_instance.download.side_effect = [video_path, audio_path]
        mock_downloader.return_value = mock_instance
        bilibili_post.downloader = mock_instance
        
        # 执行下载
        vpath, apath = bilibili_post.download()
        
        # 验证结果
        assert vpath == video_path
        assert apath == audio_path
        
        # 验证下载器被调用两次（视频+音频）
        assert mock_instance.download.call_count == 2
    
    @patch('BilibiliDownload.bilibili_post.Downloader')
    def test_17_download_preview_video(self, mock_downloader, bilibili_post, temp_dir):
        """测试17: 测试下载预览视频"""
        # 设置测试数据 - 预览视频场景
        bilibili_post.title = "预览视频"
        bilibili_post.bvid = "BV1GJ411x7h7"
        bilibili_post.preview_video = "https://preview-video-url.mp4"
        bilibili_post.selected_video = None  # 没有选中的视频表示是预览模式
        
        # 模拟下载器
        mock_instance = Mock()
        preview_path = os.path.join(temp_dir, "preview_video.mp4")
        mock_instance.download.return_value = preview_path
        mock_downloader.return_value = mock_instance
        bilibili_post.downloader = mock_instance
        
        # 执行下载（预览模式）
        vpath, apath = bilibili_post.download(is_preview=True)
        
        # 验证结果
        assert vpath == preview_path
        assert apath is None  # 预览视频没有音频
        
        # 验证只调用了一次下载（只下载预览视频）
        mock_instance.download.assert_called_once()
    
    @patch('subprocess.run')
    def test_18_merge_video_audio_success(self, mock_subprocess, bilibili_post, merge_temp_dir):
        """测试18: 测试成功合并视频和音频"""
        # 创建测试文件
        video_path = os.path.join(merge_temp_dir, "test_video.mp4")
        audio_path = os.path.join(merge_temp_dir, "test_audio.mp3")
        
        # 创建空文件用于测试
        Path(video_path).touch()
        Path(audio_path).touch()
        
        # 设置测试数据
        bilibili_post.title = "测试合并视频"
        
        # 模拟ffmpeg成功执行
        mock_subprocess.return_value = Mock(returncode=0)
        
        # 执行合并
        result = bilibili_post.merge(video_path, audio_path)
        
        # 验证结果
        assert result is not None
        assert result.endswith('.mp4')
        assert "测试合并视频" in result
        
        # 验证ffmpeg被调用
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args[0][0]  # 获取命令参数
        assert 'ffmpeg' in call_args[0]
        assert video_path in call_args
        assert audio_path in call_args
    
    @patch('subprocess.run')
    def test_19_merge_video_audio_custom_output(self, mock_subprocess, bilibili_post, merge_temp_dir):
        """测试19: 测试使用自定义输出文件名合并"""
        # 创建测试文件
        video_path = os.path.join(merge_temp_dir, "test_video.mp4")
        audio_path = os.path.join(merge_temp_dir, "test_audio.mp3")
        
        Path(video_path).touch()
        Path(audio_path).touch()
        
        # 模拟ffmpeg成功执行
        mock_subprocess.return_value = Mock(returncode=0)
        
        # 执行合并（使用自定义输出名）
        custom_name = "自定义合并视频"
        result = bilibili_post.merge(video_path, audio_path, output_name=custom_name)
        
        # 验证结果
        assert custom_name in result
        assert result.endswith('.mp4')
    
    @patch('subprocess.run')
    def test_20_merge_video_audio_ffmpeg_error(self, mock_subprocess, bilibili_post, merge_temp_dir):
        """测试20: 测试ffmpeg合并失败的情况"""
        # 创建测试文件
        video_path = os.path.join(merge_temp_dir, "test_video.mp4")
        audio_path = os.path.join(merge_temp_dir, "test_audio.mp3")
        
        Path(video_path).touch()
        Path(audio_path).touch()
        
        # 设置测试数据
        bilibili_post.title = "测试视频"
        
        # 模拟ffmpeg失败
        mock_subprocess.return_value = Mock(returncode=1, stderr="ffmpeg error")
        
        # 验证抛出异常
        with pytest.raises(BilibiliDownloadError) as exc_info:
            bilibili_post.merge(video_path, audio_path)
        
        assert "合并失败" in str(exc_info.value)
    
    def test_21_merge_missing_video_file(self, bilibili_post, merge_temp_dir):
        """测试21: 测试视频文件不存在时合并失败"""
        # 只创建音频文件
        audio_path = os.path.join(merge_temp_dir, "test_audio.mp3")
        Path(audio_path).touch()
        
        # 不存在的视频文件路径
        video_path = os.path.join(merge_temp_dir, "nonexistent_video.mp4")
        
        # 验证抛出异常
        with pytest.raises((FileNotFoundError, BilibiliDownloadError)):
            bilibili_post.merge(video_path, audio_path)
    
    def test_22_merge_missing_audio_file(self, bilibili_post, merge_temp_dir):
        """测试22: 测试音频文件不存在时合并失败"""
        # 只创建视频文件
        video_path = os.path.join(merge_temp_dir, "test_video.mp4")
        Path(video_path).touch()
        
        # 不存在的音频文件路径
        audio_path = os.path.join(merge_temp_dir, "nonexistent_audio.mp3")
        
        # 验证抛出异常
        with pytest.raises((FileNotFoundError, BilibiliDownloadError)):
            bilibili_post.merge(video_path, audio_path)
    
    def test_23_chain_operations_fetch_select_download(self, bilibili_post, temp_dir):
        """测试23: 测试链式操作 - 获取信息→选择质量→下载"""
        with patch('BilibiliDownload.bilibili_post.BilibiliParser') as mock_parser, \
             patch('BilibiliDownload.bilibili_post.Downloader') as mock_downloader:
            
            # 设置mock解析器
            mock_parser_instance = Mock()
            mock_parser_instance.fetch.return_value = {
                'title': '链式操作测试视频',
                'bvid': 'BV1GJ411x7h7',
                'video_options': self.MOCK_VIDEO_OPTIONS,
                'audio_options': self.MOCK_AUDIO_OPTIONS
            }
            mock_parser.return_value = mock_parser_instance
            bilibili_post.parser = mock_parser_instance
            
            # 设置mock下载器
            mock_downloader_instance = Mock()
            mock_downloader_instance.download.side_effect = [
                os.path.join(temp_dir, "video.mp4"),
                os.path.join(temp_dir, "audio.mp3")
            ]
            mock_downloader.return_value = mock_downloader_instance
            bilibili_post.downloader = mock_downloader_instance
            
            # 执行链式操作：获取信息 → 选择最高质量 → 下载
            result = (bilibili_post
                     .fetch()
                     .select_highest())
            
            vpath, apath = result.download()
            
            # 验证每个操作都返回自身支持链式调用
            assert result is bilibili_post
            
            # 验证最终结果
            assert bilibili_post.title == '链式操作测试视频'
            assert bilibili_post.selected_video['quality'] == 80  # 最高质量
            assert vpath.endswith('video.mp4')
            assert apath.endswith('audio.mp3')
    
    def test_24_chain_operations_filter_by_size_and_resolution(self, bilibili_post):
        """测试24: 测试链式操作 - 按大小筛选→按分辨率筛选"""
        with patch('BilibiliDownload.bilibili_post.BilibiliParser') as mock_parser:
            # 设置mock解析器
            mock_parser_instance = Mock()
            mock_parser_instance.fetch.return_value = {
                'title': '筛选测试视频',
                'bvid': 'BV1GJ411x7h7',
                'video_options': self.MOCK_VIDEO_OPTIONS,
                'audio_options': self.MOCK_AUDIO_OPTIONS
            }
            mock_parser.return_value = mock_parser_instance
            bilibili_post.parser = mock_parser_instance
            
            # 执行链式操作：获取信息 → 按大小筛选 → 按分辨率筛选
            result = (bilibili_post
                     .fetch()
                     .filter_by_size(min_mb=15.0, max_mb=35.0)
                     .filter_resolution("720P"))
            
            # 验证链式调用
            assert result is bilibili_post
            
            # 验证筛选结果
            assert bilibili_post.selected_video['description'] == '720P 高清'
    
    def test_25_error_handling_empty_video_options(self, bilibili_post):
        """测试25: 测试视频选项为空时的错误处理"""
        # 设置空的视频选项
        bilibili_post.video_options = []
        bilibili_post.audio_options = self.MOCK_AUDIO_OPTIONS.copy()
        
        # 验证选择操作抛出异常
        with pytest.raises((ValueError, BilibiliParseError)):
            bilibili_post.select_highest()
        
        with pytest.raises((ValueError, BilibiliParseError)):
            bilibili_post.select_lowest()
    
    def test_26_error_handling_no_audio_options(self, bilibili_post):
        """测试26: 测试音频选项为空时的错误处理"""
        # 设置空的音频选项
        bilibili_post.video_options = self.MOCK_VIDEO_OPTIONS.copy()
        bilibili_post.audio_options = []
        
        # 应该能选择视频但音频选择可能有问题
        bilibili_post.select_highest()
        
        # 验证视频被正确选择
        assert bilibili_post.selected_video is not None
        # 音频可能为None或抛出异常，取决于实现
    
    def test_27_error_handling_invalid_resolution_filter(self, bilibili_post):
        """测试27: 测试无效分辨率筛选的错误处理"""
        # 设置测试数据
        bilibili_post.video_options = self.MOCK_VIDEO_OPTIONS.copy()
        bilibili_post.audio_options = self.MOCK_AUDIO_OPTIONS.copy()
        
        # 验证无效分辨率抛出异常
        with pytest.raises((ValueError, BilibiliParseError)):
            bilibili_post.filter_resolution("8K")  # 不存在的分辨率
        
        with pytest.raises((ValueError, BilibiliParseError)):
            bilibili_post.filter_resolution(999)  # 不存在的质量ID


class TestBilibiliPostIntegration:
    """B站下载集成测试"""
    
    @pytest.mark.integration
    def test_28_full_workflow_simulation(self, temp_dir):
        """测试28: 完整工作流程模拟测试"""
        merge_dir = os.path.join(temp_dir, "merge")
        os.makedirs(merge_dir, exist_ok=True)
        
        with patch('BilibiliDownload.bilibili_post.BilibiliParser') as mock_parser, \
             patch('BilibiliDownload.bilibili_post.Downloader') as mock_downloader, \
             patch('subprocess.run') as mock_subprocess:
            
            # 创建BilibiliPost实例
            post = BilibiliPost(
                url="https://www.bilibili.com/video/BV1GJ411x7h7",
                save_dir=temp_dir,
                merge_dir=merge_dir
            )
            
            # 设置mock解析器
            mock_parser_instance = Mock()
            mock_parser_instance.fetch.return_value = {
                'title': '完整流程测试视频',
                'bvid': 'BV1GJ411x7h7',
                'video_options': [
                    {'quality': 80, 'description': '1080P 高清', 'url': 'https://video-1080p.mp4', 'width': 1920, 'height': 1080, 'size': 52428800},
                    {'quality': 64, 'description': '720P 高清', 'url': 'https://video-720p.mp4', 'width': 1280, 'height': 720, 'size': 31457280}
                ],
                'audio_options': [
                    {'quality': 30280, 'description': '320K', 'url': 'https://audio-320k.mp3', 'size': 10485760}
                ]
            }
            mock_parser.return_value = mock_parser_instance
            post.parser = mock_parser_instance
            
            # 设置mock下载器
            mock_downloader_instance = Mock()
            video_file = os.path.join(temp_dir, "test_video.mp4")
            audio_file = os.path.join(temp_dir, "test_audio.mp3")
            mock_downloader_instance.download.side_effect = [video_file, audio_file]
            mock_downloader.return_value = mock_downloader_instance
            post.downloader = mock_downloader_instance
            
            # 创建模拟的下载文件
            Path(video_file).touch()
            Path(audio_file).touch()
            
            # 设置mock ffmpeg
            mock_subprocess.return_value = Mock(returncode=0)
            
            # 执行完整流程
            merged_file = (post
                          .fetch()
                          .filter_by_size(min_mb=20.0)  # 筛选大于20MB的视频
                          .select_highest()
                          .download())
            
            vpath, apath = merged_file
            final_output = post.merge(vpath, apath)
            
            # 验证完整流程
            assert post.title == '完整流程测试视频'
            assert post.selected_video['quality'] == 80  # 1080P被选择
            assert len(post.video_options) == 1  # 720P被过滤掉（小于20MB）
            assert final_output.endswith('.mp4')
            assert "完整流程测试视频" in final_output
            
            # 验证各个组件被正确调用
            mock_parser_instance.fetch.assert_called_once()
            assert mock_downloader_instance.download.call_count == 2  # 视频+音频
            mock_subprocess.assert_called_once()  # ffmpeg合并


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "--tb=short"])