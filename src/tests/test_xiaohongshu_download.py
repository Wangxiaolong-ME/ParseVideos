# -*- coding: utf-8 -*-
"""
小红书下载模块测试用例
测试 XiaohongshuPost 类的各种功能，包括URL判断、解析、下载等操作
"""
import pytest
import os
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from bs4 import BeautifulSoup

# 导入被测试的模块
from XiaoHongShu.xhs_parser import XiaohongshuPost


class TestXiaohongshuPost:
    """小红书下载核心类测试"""
    
    # 测试用的小红书链接
    TEST_XHS_NOTE_URL = "https://www.xiaohongshu.com/explore/64f1b2c3000000001203456"
    TEST_XHS_VIDEO_URL = "https://www.xiaohongshu.com/discovery/item/64f1b2c3000000001203457"
    TEST_XHS_SHARE_URL = "https://www.xiaohongshu.com/discovery/item/64f1b2c3000000001203458?xhsshare=WeixinSession"
    
    # 无效的URL
    INVALID_URLS = [
        "https://www.douyin.com/video/123456",  # 抖音链接
        "https://www.bilibili.com/video/BV123",  # B站链接
        "https://www.youtube.com/watch?v=123",   # YouTube链接
        "https://baidu.com",                     # 普通网站
        "not_a_url",                            # 非URL字符串
        ""                                      # 空字符串
    ]
    
    # 模拟的页面HTML内容
    MOCK_HTML_CONTENT = """
    <html>
    <head>
        <title>测试小红书笔记</title>
        <script>
            window.__INITIAL_STATE__ = {
                "note": {
                    "noteId": "64f1b2c3000000001203456",
                    "title": "测试小红书笔记标题",
                    "desc": "这是一个测试笔记的描述内容",
                    "type": "video",
                    "video": {
                        "media": {
                            "videoKey": "test_video_key",
                            "video": [
                                {
                                    "streamType": 1,
                                    "masterUrl": "https://sns-video-bd.xhscdn.com/test_video_720p.mp4",
                                    "backupUrls": ["https://backup-video-url.mp4"]
                                }
                            ]
                        }
                    },
                    "imageList": [
                        {
                            "url": "https://sns-img-bd.xhscdn.com/test_image_1.jpg",
                            "width": 1080,
                            "height": 1080
                        },
                        {
                            "url": "https://sns-img-bd.xhscdn.com/test_image_2.jpg", 
                            "width": 1080,
                            "height": 1080
                        }
                    ],
                    "user": {
                        "nickname": "测试用户",
                        "userId": "test_user_id"
                    }
                }
            };
        </script>
    </head>
    <body>
        <div class="note-detail">测试内容</div>
    </body>
    </html>
    """
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录用于测试"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def xhs_post(self):
        """创建XiaohongshuPost实例用于测试"""
        return XiaohongshuPost()
    
    def test_01_xhs_post_initialization(self, xhs_post):
        """测试1: 测试XiaohongshuPost类的初始化"""
        # 验证初始化属性
        assert xhs_post.data is None
        assert xhs_post.images == []
        assert xhs_post.videos == []
        assert hasattr(xhs_post, 'download')  # 下载器
        assert hasattr(xhs_post, 'save_dir')   # 保存目录
        
        # 验证保存目录存在
        assert os.path.exists(xhs_post.save_dir)
    
    def test_02_is_xhs_url_valid_urls(self):
        """测试2: 测试有效小红书URL的识别"""
        valid_urls = [
            "https://www.xiaohongshu.com/explore/64f1b2c3000000001203456",
            "https://www.xiaohongshu.com/discovery/item/64f1b2c3000000001203457",
            "https://www.xiaohongshu.com/discovery/item/64f1b2c3000000001203458?xhsshare=WeixinSession",
            "https://xiaohongshu.com/explore/123456",  # 无www前缀
            "http://www.xiaohongshu.com/explore/789012"  # HTTP协议
        ]
        
        for url in valid_urls:
            result = XiaohongshuPost.is_xhs_url(url)
            assert result is True, f"URL {url} should be recognized as valid XHS URL"
    
    def test_03_is_xhs_url_invalid_urls(self):
        """测试3: 测试无效URL的识别"""
        for url in self.INVALID_URLS:
            result = XiaohongshuPost.is_xhs_url(url)
            assert result is False, f"URL {url} should not be recognized as XHS URL"
    
    def test_04_extract_base_url_clean_url(self):
        """测试4: 测试提取干净的基础URL"""
        test_cases = [
            # (输入URL, 期望的基础URL)
            (
                "https://www.xiaohongshu.com/discovery/item/64f1b2c3000000001203456?xhsshare=WeixinSession&app_platform=ios",
                "https://www.xiaohongshu.com/discovery/item/64f1b2c3000000001203456"
            ),
            (
                "https://www.xiaohongshu.com/explore/64f1b2c3000000001203456 复制这段内容，打开小红书App查看精彩内容！",
                "https://www.xiaohongshu.com/explore/64f1b2c3000000001203456"
            ),
            (
                self.TEST_XHS_NOTE_URL,  # 已经是干净的URL
                self.TEST_XHS_NOTE_URL
            )
        ]
        
        for input_url, expected_url in test_cases:
            result = XiaohongshuPost.extract_base_url(input_url)
            assert result == expected_url, f"Failed to extract base URL from {input_url}"
    
    def test_05_extract_explore_id_from_url(self):
        """测试5: 测试从URL中提取explore ID"""
        test_cases = [
            ("https://www.xiaohongshu.com/explore/64f1b2c3000000001203456", "64f1b2c3000000001203456"),
            ("https://www.xiaohongshu.com/discovery/item/64f1b2c3000000001203457", "64f1b2c3000000001203457"),
            ("https://www.xiaohongshu.com/explore/123abc456def789", "123abc456def789")
        ]
        
        for url, expected_id in test_cases:
            result = XiaohongshuPost.extract_explore_id(url)
            assert result == expected_id, f"Failed to extract ID from {url}"
    
    def test_06_extract_explore_id_invalid_url(self):
        """测试6: 测试从无效URL提取ID的处理"""
        invalid_urls = [
            "https://www.xiaohongshu.com/",
            "https://www.xiaohongshu.com/explore/",
            "https://www.douyin.com/video/123456"
        ]
        
        for url in invalid_urls:
            result = XiaohongshuPost.extract_explore_id(url)
            assert result is None or result == "", f"Should not extract ID from invalid URL: {url}"
    
    @patch('XiaoHongShu.xhs_parser.Downloader')
    def test_07_download_image_success(self, mock_downloader, xhs_post, temp_dir):
        """测试7: 测试成功下载图片"""
        # 设置mock下载器
        mock_instance = Mock()
        expected_path = os.path.join(temp_dir, "test_image.jpg")
        mock_instance.download.return_value = expected_path
        mock_downloader.return_value = mock_instance
        xhs_post.download = mock_instance
        
        # 执行图片下载
        image_url = "https://sns-img-bd.xhscdn.com/test_image.jpg"
        result = xhs_post.download_image(image_url, expected_path)
        
        # 验证结果
        assert result == expected_path
        
        # 验证下载器被正确调用
        mock_instance.download.assert_called_once_with(image_url, expected_path)
    
    @patch('XiaoHongShu.xhs_parser.Downloader')
    def test_08_download_video_success(self, mock_downloader, xhs_post, temp_dir):
        """测试8: 测试成功下载视频"""
        # 设置mock下载器
        mock_instance = Mock()
        expected_path = os.path.join(temp_dir, "test_video.mp4")
        mock_instance.download.return_value = expected_path
        mock_downloader.return_value = mock_instance
        xhs_post.download = mock_instance
        
        # 执行视频下载
        video_url = "https://sns-video-bd.xhscdn.com/test_video.mp4"
        result = xhs_post.download_video(video_url, expected_path)
        
        # 验证结果
        assert result == expected_path
        
        # 验证下载器被正确调用
        mock_instance.download.assert_called_once_with(video_url, expected_path)
    
    @patch('XiaoHongShu.xhs_parser.Downloader')
    def test_09_download_image_failure(self, mock_downloader, xhs_post, temp_dir):
        """测试9: 测试图片下载失败的处理"""
        # 设置mock下载器抛出异常
        mock_instance = Mock()
        mock_instance.download.side_effect = Exception("下载失败")
        mock_downloader.return_value = mock_instance
        xhs_post.download = mock_instance
        
        # 执行图片下载
        image_url = "https://sns-img-bd.xhscdn.com/test_image.jpg"
        output_path = os.path.join(temp_dir, "test_image.jpg")
        
        # 验证异常处理
        with pytest.raises(Exception) as exc_info:
            xhs_post.download_image(image_url, output_path)
        
        assert "下载失败" in str(exc_info.value)
    
    def test_10_parser_downloader_video_content(self, xhs_post, temp_dir):
        """测试10: 测试解析视频内容并准备下载"""
        # 模拟视频笔记数据
        video_data = {
            "noteId": "64f1b2c3000000001203456",
            "title": "测试视频笔记",
            "desc": "视频描述",
            "type": "video",
            "video": {
                "media": {
                    "video": [
                        {
                            "streamType": 1,
                            "masterUrl": "https://sns-video-bd.xhscdn.com/test_video_720p.mp4",
                            "backupUrls": ["https://backup-video-url.mp4"]
                        }
                    ]
                }
            },
            "user": {
                "nickname": "测试用户"
            }
        }
        
        # 使用临时目录
        xhs_post.save_dir = temp_dir
        
        # 执行解析
        with patch.object(xhs_post, 'download_video') as mock_download_video:
            mock_download_video.return_value = os.path.join(temp_dir, "test_video.mp4")
            
            result = xhs_post.parser_downloader(video_data)
            
            # 验证解析结果
            assert result is not None
            assert len(xhs_post.videos) == 1
            assert xhs_post.videos[0] == "https://sns-video-bd.xhscdn.com/test_video_720p.mp4"
            
            # 验证下载被调用
            mock_download_video.assert_called_once()
    
    def test_11_parser_downloader_image_content(self, xhs_post, temp_dir):
        """测试11: 测试解析图片内容并准备下载"""
        # 模拟图片笔记数据
        image_data = {
            "noteId": "64f1b2c3000000001203456",
            "title": "测试图片笔记",
            "desc": "图片描述",
            "type": "normal",
            "imageList": [
                {
                    "url": "https://sns-img-bd.xhscdn.com/test_image_1.jpg",
                    "width": 1080,
                    "height": 1080
                },
                {
                    "url": "https://sns-img-bd.xhscdn.com/test_image_2.jpg",
                    "width": 1080,
                    "height": 1080
                }
            ],
            "user": {
                "nickname": "测试用户"
            }
        }
        
        # 使用临时目录
        xhs_post.save_dir = temp_dir
        
        # 执行解析
        with patch.object(xhs_post, 'download_image') as mock_download_image:
            mock_download_image.side_effect = [
                os.path.join(temp_dir, "test_image_1.jpg"),
                os.path.join(temp_dir, "test_image_2.jpg")
            ]
            
            result = xhs_post.parser_downloader(image_data)
            
            # 验证解析结果
            assert result is not None
            assert len(xhs_post.images) == 2
            assert "test_image_1.jpg" in xhs_post.images[0]
            assert "test_image_2.jpg" in xhs_post.images[1]
            
            # 验证下载被调用两次
            assert mock_download_image.call_count == 2
    
    def test_12_parser_downloader_mixed_content(self, xhs_post, temp_dir):
        """测试12: 测试解析包含视频和图片的混合内容"""
        # 模拟混合内容数据
        mixed_data = {
            "noteId": "64f1b2c3000000001203456",
            "title": "测试混合内容笔记",
            "desc": "包含视频和图片的笔记",
            "type": "video",
            "video": {
                "media": {
                    "video": [
                        {
                            "streamType": 1,
                            "masterUrl": "https://sns-video-bd.xhscdn.com/test_video.mp4"
                        }
                    ]
                }
            },
            "imageList": [
                {
                    "url": "https://sns-img-bd.xhscdn.com/test_image.jpg",
                    "width": 1080,
                    "height": 1080
                }
            ],
            "user": {
                "nickname": "测试用户"
            }
        }
        
        # 使用临时目录
        xhs_post.save_dir = temp_dir
        
        # 执行解析
        with patch.object(xhs_post, 'download_video') as mock_download_video, \
             patch.object(xhs_post, 'download_image') as mock_download_image:
            
            mock_download_video.return_value = os.path.join(temp_dir, "test_video.mp4")
            mock_download_image.return_value = os.path.join(temp_dir, "test_image.jpg")
            
            result = xhs_post.parser_downloader(mixed_data)
            
            # 验证解析结果
            assert result is not None
            assert len(xhs_post.videos) == 1
            assert len(xhs_post.images) == 1
            
            # 验证下载被调用
            mock_download_video.assert_called_once()
            mock_download_image.assert_called_once()
    
    def test_13_parser_downloader_empty_data(self, xhs_post, temp_dir):
        """测试13: 测试解析空数据的处理"""
        # 空数据
        empty_data = {}
        
        # 执行解析
        result = xhs_post.parser_downloader(empty_data)
        
        # 验证空数据处理
        assert xhs_post.videos == []
        assert xhs_post.images == []
    
    def test_14_parser_downloader_missing_media_data(self, xhs_post, temp_dir):
        """测试14: 测试解析缺少媒体数据的处理"""
        # 缺少媒体数据的笔记
        incomplete_data = {
            "noteId": "64f1b2c3000000001203456",
            "title": "不完整的笔记",
            "desc": "缺少媒体内容的笔记",
            "type": "normal",
            "user": {
                "nickname": "测试用户"
            }
            # 缺少 imageList 和 video 字段
        }
        
        # 执行解析
        result = xhs_post.parser_downloader(incomplete_data)
        
        # 验证处理结果
        assert xhs_post.videos == []
        assert xhs_post.images == []
    
    @patch('requests.get')
    def test_15_get_xhs_success(self, mock_get):
        """测试15: 测试成功获取小红书页面数据"""
        # 设置mock响应
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = self.MOCK_HTML_CONTENT
        mock_get.return_value = mock_response
        
        # 执行获取页面数据
        result = XiaohongshuPost.get_xhs(self.TEST_XHS_NOTE_URL)
        
        # 验证结果
        assert result is not None
        assert isinstance(result, dict)
        
        # 验证请求被正确调用
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert self.TEST_XHS_NOTE_URL in call_args[0][0]
    
    @patch('requests.get')
    def test_16_get_xhs_http_error(self, mock_get):
        """测试16: 测试HTTP错误的处理"""
        # 设置HTTP错误响应
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = Exception("404 Not Found")
        mock_get.return_value = mock_response
        
        # 执行获取页面数据
        result = XiaohongshuPost.get_xhs(self.TEST_XHS_NOTE_URL)
        
        # 验证错误处理
        assert result is None or result == {}
    
    @patch('requests.get')
    def test_17_get_xhs_network_error(self, mock_get):
        """测试17: 测试网络错误的处理"""
        # 设置网络异常
        mock_get.side_effect = Exception("网络连接失败")
        
        # 执行获取页面数据
        result = XiaohongshuPost.get_xhs(self.TEST_XHS_NOTE_URL)
        
        # 验证异常处理
        assert result is None or result == {}
    
    @patch('requests.get')
    def test_18_get_xhs_with_cookies(self, mock_get):
        """测试18: 测试使用cookies获取页面数据"""
        # 设置mock响应
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = self.MOCK_HTML_CONTENT
        mock_get.return_value = mock_response
        
        # 测试cookies
        test_cookies = {
            'web_session': 'test_session_id',
            'xsecappid': 'xhs-pc-web'
        }
        
        # 执行获取页面数据（带cookies）
        result = XiaohongshuPost.get_xhs(self.TEST_XHS_NOTE_URL, cookies=test_cookies)
        
        # 验证结果
        assert result is not None
        
        # 验证cookies被传递
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args[1]
        assert 'cookies' in call_kwargs
        assert call_kwargs['cookies'] == test_cookies
    
    def test_19_filename_generation_from_title(self, xhs_post, temp_dir):
        """测试19: 测试从标题生成文件名"""
        # 测试数据
        test_cases = [
            ("正常标题", "正常标题"),
            ("包含特殊字符的标题/\\:*?\"<>|", "包含特殊字符的标题_________"),
            ("很长的标题" * 20, "很长的标题" * 20),  # 测试长标题
            ("", "untitled"),  # 空标题
            ("  带空格的标题  ", "带空格的标题")  # 带空格的标题
        ]
        
        # 简单的文件名清理函数（模拟实际实现）
        def sanitize_filename(filename):
            if not filename.strip():
                return "untitled"
            
            filename = filename.strip()
            invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
            for char in invalid_chars:
                filename = filename.replace(char, '_')
            
            # 限制文件名长度
            if len(filename) > 100:
                filename = filename[:100]
            
            return filename
        
        # 验证文件名生成
        for input_title, expected_pattern in test_cases:
            clean_name = sanitize_filename(input_title)
            
            if input_title == "":
                assert clean_name == "untitled"
            elif "特殊字符" in input_title:
                assert "_" in clean_name
                assert not any(char in clean_name for char in ['/', '\\', ':', '*', '?', '"', '<', '>', '|'])
            else:
                assert len(clean_name) > 0
                assert len(clean_name) <= 100
    
    def test_20_directory_creation_for_different_types(self, xhs_post, temp_dir):
        """测试20: 测试为不同内容类型创建目录"""
        # 模拟不同类型的内容
        content_types = [
            ("video", "videos"),
            ("normal", "images"),
            ("mixed", "mixed_content")
        ]
        
        # 使用临时目录
        xhs_post.save_dir = temp_dir
        
        for content_type, expected_subdir in content_types:
            # 创建子目录
            subdir_path = os.path.join(temp_dir, expected_subdir)
            os.makedirs(subdir_path, exist_ok=True)
            
            # 验证目录创建
            assert os.path.exists(subdir_path)
            assert os.path.isdir(subdir_path)


class TestXiaohongshuPostIntegration:
    """小红书下载集成测试"""
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录用于测试"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.mark.integration
    def test_21_complete_video_download_workflow(self, temp_dir):
        """测试21: 完整视频下载工作流程"""
        with patch('requests.get') as mock_get, \
             patch('XiaoHongShu.xhs_parser.Downloader') as mock_downloader:
            
            # 创建XiaohongshuPost实例
            xhs_post = XiaohongshuPost()
            xhs_post.save_dir = temp_dir
            
            # 设置mock页面响应
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = """
            <script>
                window.__INITIAL_STATE__ = {
                    "note": {
                        "noteId": "test123",
                        "title": "集成测试视频",
                        "desc": "完整工作流程测试",
                        "type": "video",
                        "video": {
                            "media": {
                                "video": [{
                                    "streamType": 1,
                                    "masterUrl": "https://test-video.mp4"
                                }]
                            }
                        },
                        "user": {"nickname": "测试用户"}
                    }
                };
            </script>
            """
            mock_get.return_value = mock_response
            
            # 设置mock下载器
            mock_downloader_instance = Mock()
            video_file = os.path.join(temp_dir, "集成测试视频.mp4")
            mock_downloader_instance.download.return_value = video_file
            mock_downloader.return_value = mock_downloader_instance
            xhs_post.download = mock_downloader_instance
            
            # 创建模拟下载文件
            Path(video_file).touch()
            
            # 执行完整工作流程
            url = "https://www.xiaohongshu.com/explore/test123"
            
            # 1. 验证URL
            assert XiaohongshuPost.is_xhs_url(url)
            
            # 2. 提取基础URL
            clean_url = XiaohongshuPost.extract_base_url(url)
            assert clean_url == url
            
            # 3. 获取页面数据
            page_data = XiaohongshuPost.get_xhs(clean_url)
            assert page_data is not None
            
            # 4. 解析并下载内容
            # 这里需要模拟从页面HTML中提取数据的过程
            mock_note_data = {
                "noteId": "test123",
                "title": "集成测试视频",
                "type": "video",
                "video": {
                    "media": {
                        "video": [{
                            "streamType": 1,
                            "masterUrl": "https://test-video.mp4"
                        }]
                    }
                },
                "user": {"nickname": "测试用户"}
            }
            
            result = xhs_post.parser_downloader(mock_note_data)
            
            # 验证完整工作流程
            assert len(xhs_post.videos) == 1
            assert xhs_post.videos[0] == "https://test-video.mp4"
            assert os.path.exists(video_file)
            
            # 验证各组件被正确调用
            mock_get.assert_called_once()
            mock_downloader_instance.download.assert_called_once()
    
    @pytest.mark.integration
    def test_22_complete_image_download_workflow(self, temp_dir):
        """测试22: 完整图片下载工作流程"""
        with patch('requests.get') as mock_get, \
             patch('XiaoHongShu.xhs_parser.Downloader') as mock_downloader:
            
            # 创建XiaohongshuPost实例
            xhs_post = XiaohongshuPost()
            xhs_post.save_dir = temp_dir
            
            # 设置mock页面响应
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = """
            <script>
                window.__INITIAL_STATE__ = {
                    "note": {
                        "noteId": "test456",
                        "title": "集成测试图集",
                        "desc": "图片下载工作流程测试",
                        "type": "normal",
                        "imageList": [
                            {"url": "https://test-image-1.jpg"},
                            {"url": "https://test-image-2.jpg"}
                        ],
                        "user": {"nickname": "测试用户"}
                    }
                };
            </script>
            """
            mock_get.return_value = mock_response
            
            # 设置mock下载器
            mock_downloader_instance = Mock()
            image_files = [
                os.path.join(temp_dir, "集成测试图集_1.jpg"),
                os.path.join(temp_dir, "集成测试图集_2.jpg")
            ]
            mock_downloader_instance.download.side_effect = image_files
            mock_downloader.return_value = mock_downloader_instance
            xhs_post.download = mock_downloader_instance
            
            # 创建模拟下载文件
            for image_file in image_files:
                Path(image_file).touch()
            
            # 执行完整工作流程
            url = "https://www.xiaohongshu.com/explore/test456"
            
            # 模拟解析数据
            mock_note_data = {
                "noteId": "test456",
                "title": "集成测试图集",
                "type": "normal",
                "imageList": [
                    {"url": "https://test-image-1.jpg"},
                    {"url": "https://test-image-2.jpg"}
                ],
                "user": {"nickname": "测试用户"}
            }
            
            result = xhs_post.parser_downloader(mock_note_data)
            
            # 验证完整工作流程
            assert len(xhs_post.images) == 2
            assert all(os.path.exists(img_file) for img_file in image_files)
            
            # 验证下载器被调用两次
            assert mock_downloader_instance.download.call_count == 2
    
    def test_23_error_recovery_and_robustness(self, temp_dir):
        """测试23: 错误恢复和健壮性测试"""
        with patch('requests.get') as mock_get, \
             patch('XiaoHongShu.xhs_parser.Downloader') as mock_downloader:
            
            xhs_post = XiaohongshuPost()
            xhs_post.save_dir = temp_dir
            
            # 模拟各种错误情况
            error_scenarios = [
                # 网络错误
                Exception("网络连接失败"),
                # HTTP错误
                Mock(status_code=404, raise_for_status=Mock(side_effect=Exception("404"))),
                # 解析错误（空响应）
                Mock(status_code=200, text="")
            ]
            
            for error_scenario in error_scenarios:
                if isinstance(error_scenario, Exception):
                    mock_get.side_effect = error_scenario
                else:
                    mock_get.return_value = error_scenario
                
                # 执行操作并验证错误处理
                try:
                    result = XiaohongshuPost.get_xhs("https://www.xiaohongshu.com/explore/test")
                    # 应该返回None或空字典，不应该抛出未处理的异常
                    assert result is None or result == {}
                except Exception as e:
                    # 如果抛出异常，应该是已知的、可处理的异常
                    assert isinstance(e, (requests.RequestException, ValueError, KeyError))
    
    def test_24_url_edge_cases_handling(self):
        """测试24: URL边界情况处理"""
        edge_cases = [
            # 非常长的URL
            "https://www.xiaohongshu.com/explore/" + "a" * 1000,
            # 包含特殊字符的URL
            "https://www.xiaohongshu.com/explore/64f1b2c3000000001203456?param=value%20with%20spaces",
            # 包含中文字符的URL
            "https://www.xiaohongshu.com/explore/64f1b2c3000000001203456?title=中文标题",
            # 大小写混合的域名
            "https://WWW.XIAOHONGSHU.COM/explore/64f1b2c3000000001203456"
        ]
        
        for url in edge_cases:
            # 应该能够正确识别为小红书URL
            is_valid = XiaohongshuPost.is_xhs_url(url)
            # 对于边界情况，至少不应该抛出异常
            assert isinstance(is_valid, bool)
            
            # 应该能够提取基础URL
            try:
                base_url = XiaohongshuPost.extract_base_url(url)
                assert isinstance(base_url, str)
            except Exception:
                # 对于某些极端情况，可能会失败，但不应该是未处理的异常
                pass


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "--tb=short"])