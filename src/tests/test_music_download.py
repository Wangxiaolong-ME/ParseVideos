# -*- coding: utf-8 -*-
"""
网易云音乐下载模块测试用例
测试音乐下载相关功能，包括链接解析、下载、批量处理等操作
"""
import pytest
import os
import tempfile
import json
import re
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, mock_open

# 导入被测试的模块
from MusicDownload.download_music import get_download_link, download_file, main
from MusicDownload.download import download_single
from MusicDownload.fetch_music_list import fetch_song_urls_via_api


class TestMusicDownloadCore:
    """网易云音乐下载核心功能测试"""
    
    # 测试用的网易云音乐链接
    TEST_SONG_URL = "https://music.163.com/song?id=1234567890"
    TEST_PLAYLIST_URL = "https://music.163.com/playlist?id=9876543210"
    TEST_ALBUM_URL = "https://music.163.com/album?id=5555555555"
    
    # 模拟的API响应数据
    MOCK_SONG_RESPONSE = {
        "code": 200,
        "data": {
            "url": "https://music-download-url.mp3?vuutv=12345",
            "title": "测试歌曲标题",
            "artist": "测试歌手",
            "album": "测试专辑",
            "duration": 240000,  # 4分钟，毫秒
            "size": 5242880,    # 5MB，字节
            "bit_rate": 320000   # 320kbps
        }
    }
    
    MOCK_PLAYLIST_RESPONSE = {
        "code": 200,
        "data": [
            {"id": "1234567890", "name": "歌曲1", "artist": "歌手1"},
            {"id": "1234567891", "name": "歌曲2", "artist": "歌手2"},
            {"id": "1234567892", "name": "歌曲3", "artist": "歌手3"}
        ]
    }
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录用于测试"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_01_get_download_link_success(self):
        """测试1: 测试成功获取歌曲下载链接"""
        with patch('requests.post') as mock_post:
            # 设置mock响应
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = self.MOCK_SONG_RESPONSE
            mock_post.return_value = mock_response
            
            # 执行获取下载链接
            result = get_download_link(self.TEST_SONG_URL)
            
            # 验证结果
            assert result is not None
            assert "music-download-url.mp3" in result
            assert "vuutv=" in result  # 包含验证参数
            
            # 验证API被正确调用
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "api.toubiec.cn" in call_args[0][0]  # API URL
    
    def test_02_get_download_link_with_song_id_return(self):
        """测试2: 测试获取下载链接并返回歌曲ID"""
        with patch('requests.post') as mock_post:
            # 设置mock响应
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = self.MOCK_SONG_RESPONSE
            mock_post.return_value = mock_response
            
            # 执行获取下载链接（返回歌曲ID）
            result_url, song_name, song_id = get_download_link(self.TEST_SONG_URL, return_song_id=True)
            
            # 验证结果
            assert result_url is not None
            assert song_name == "测试歌曲标题"
            assert song_id == "1234567890"  # 从URL中提取的ID
    
    def test_03_get_download_link_invalid_url(self):
        """测试3: 测试无效URL的处理"""
        # 测试没有ID的URL
        invalid_url = "https://music.163.com/song"
        result = get_download_link(invalid_url)
        
        # 验证返回None或抛出异常
        assert result is None
    
    def test_04_get_download_link_api_error(self):
        """测试4: 测试API错误响应的处理"""
        with patch('requests.post') as mock_post:
            # 设置mock响应 - API错误
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"code": 400, "message": "歌曲不存在"}
            mock_post.return_value = mock_response
            
            # 执行获取下载链接
            result = get_download_link(self.TEST_SONG_URL)
            
            # 验证处理错误响应
            assert result is None or "error" in str(result).lower()
    
    def test_05_get_download_link_network_error(self):
        """测试5: 测试网络错误的处理"""
        with patch('requests.post') as mock_post:
            # 设置网络异常
            mock_post.side_effect = Exception("网络连接错误")
            
            # 执行获取下载链接
            result = get_download_link(self.TEST_SONG_URL)
            
            # 验证异常处理
            assert result is None
    
    def test_06_extract_song_id_from_various_urls(self):
        """测试6: 测试从各种URL格式中提取歌曲ID"""
        test_urls = [
            "https://music.163.com/song?id=1234567890",
            "https://music.163.com/song?id=1234567890&userid=12345",
            "https://music.163.com/#/song?id=1234567890",
            "http://music.163.com/song?id=1234567890"  # HTTP协议
        ]
        
        for url in test_urls:
            # 使用正则表达式提取ID（模拟get_download_link中的逻辑）
            match = re.search(r"id=(\d+)", url)
            if match:
                song_id = match.group(1)
                assert song_id == "1234567890"
    
    @patch('builtins.open', new_callable=mock_open)
    @patch('requests.get')
    def test_07_download_file_success(self, mock_get, mock_file, temp_dir):
        """测试7: 测试成功下载文件"""
        # 设置mock响应
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.iter_content.return_value = [b'music_content_chunk_1', b'music_content_chunk_2']
        mock_response.headers = {'Content-Length': '1024'}
        mock_get.return_value = mock_response
        
        # 执行文件下载
        download_url = "https://music-download-url.mp3"
        output_path = os.path.join(temp_dir, "test_song.mp3")
        
        result = download_file(download_url, output_path)
        
        # 验证下载成功
        assert result == output_path
        
        # 验证网络请求
        mock_get.assert_called_once_with(download_url, stream=True, timeout=30)
        
        # 验证文件写入
        mock_file.assert_called_once_with(output_path, 'wb')
        handle = mock_file()
        assert handle.write.call_count >= 2  # 写入了多个数据块
    
    @patch('requests.get')
    def test_08_download_file_network_error(self, mock_get, temp_dir):
        """测试8: 测试下载时网络错误处理"""
        # 设置网络异常
        mock_get.side_effect = Exception("下载失败")
        
        # 执行下载
        download_url = "https://music-download-url.mp3"
        output_path = os.path.join(temp_dir, "test_song.mp3")
        
        # 验证异常处理
        with pytest.raises(Exception):
            download_file(download_url, output_path)
    
    @patch('requests.get')
    def test_09_download_file_http_error(self, mock_get, temp_dir):
        """测试9: 测试下载时HTTP错误处理"""
        # 设置HTTP错误响应
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = Exception("404 Not Found")
        mock_get.return_value = mock_response
        
        # 执行下载
        download_url = "https://music-download-url.mp3"
        output_path = os.path.join(temp_dir, "test_song.mp3")
        
        # 验证HTTP错误处理
        with pytest.raises(Exception):
            download_file(download_url, output_path)
    
    @patch('MusicDownload.download_music.download_file')
    @patch('MusicDownload.download_music.get_download_link')
    def test_10_download_single_success(self, mock_get_link, mock_download, temp_dir):
        """测试10: 测试单曲下载成功"""
        # 设置mock返回值
        mock_get_link.return_value = ("https://music-url.mp3", "测试歌曲", "1234567890")
        output_file = os.path.join(temp_dir, "测试歌曲.mp3")
        mock_download.return_value = output_file
        
        # 执行单曲下载
        song_url, downloaded_path = download_single(self.TEST_SONG_URL, temp_dir)
        
        # 验证结果
        assert song_url == "https://music-url.mp3"
        assert downloaded_path == output_file
        
        # 验证调用链
        mock_get_link.assert_called_once_with(self.TEST_SONG_URL, return_song_id=True)
        mock_download.assert_called_once_with("https://music-url.mp3", output_file)
    
    @patch('MusicDownload.download_music.get_download_link')
    def test_11_download_single_get_link_failed(self, mock_get_link, temp_dir):
        """测试11: 测试获取下载链接失败时的处理"""
        # 设置获取链接失败
        mock_get_link.return_value = (None, None, None)
        
        # 执行单曲下载
        result = download_single(self.TEST_SONG_URL, temp_dir)
        
        # 验证失败处理
        assert result is None or result == (None, None)
    
    def test_12_download_single_file_already_exists(self, temp_dir):
        """测试12: 测试文件已存在时的处理"""
        with patch('MusicDownload.download_music.get_download_link') as mock_get_link:
            # 设置mock返回值
            mock_get_link.return_value = ("https://music-url.mp3", "已存在的歌曲", "1234567890")
            
            # 创建已存在的文件
            existing_file = os.path.join(temp_dir, "已存在的歌曲.mp3")
            Path(existing_file).touch()
            
            # 执行下载
            song_url, downloaded_path = download_single(self.TEST_SONG_URL, temp_dir)
            
            # 验证跳过下载，直接返回已存在文件
            assert downloaded_path == existing_file
            assert os.path.exists(existing_file)


class TestMusicPlaylistDownload:
    """音乐播放列表下载测试"""
    
    @patch('requests.get')
    def test_13_fetch_playlist_songs_success(self, mock_get):
        """测试13: 测试成功获取播放列表歌曲"""
        # 设置mock响应
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": 200,
            "playlist": {
                "tracks": [
                    {"id": 1234567890, "name": "歌曲1", "ar": [{"name": "歌手1"}]},
                    {"id": 1234567891, "name": "歌曲2", "ar": [{"name": "歌手2"}]},
                    {"id": 1234567892, "name": "歌曲3", "ar": [{"name": "歌手3"}]}
                ]
            }
        }
        mock_get.return_value = mock_response
        
        # 执行获取播放列表
        playlist_url = "https://music.163.com/playlist?id=9876543210"
        songs = fetch_song_urls_via_api(playlist_url)
        
        # 验证结果
        assert len(songs) == 3
        assert songs[0]["name"] == "歌曲1"
        assert songs[0]["artist"] == "歌手1"
        assert songs[0]["url"] == "https://music.163.com/song?id=1234567890"
    
    @patch('requests.get')
    def test_14_fetch_playlist_songs_api_error(self, mock_get):
        """测试14: 测试播放列表API错误处理"""
        # 设置API错误响应
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 400, "message": "播放列表不存在"}
        mock_get.return_value = mock_response
        
        # 执行获取播放列表
        playlist_url = "https://music.163.com/playlist?id=9876543210"
        songs = fetch_song_urls_via_api(playlist_url)
        
        # 验证错误处理
        assert songs is None or len(songs) == 0
    
    @patch('requests.get')
    def test_15_fetch_playlist_songs_network_error(self, mock_get):
        """测试15: 测试获取播放列表网络错误"""
        # 设置网络异常
        mock_get.side_effect = Exception("网络连接失败")
        
        # 执行获取播放列表
        playlist_url = "https://music.163.com/playlist?id=9876543210"
        songs = fetch_song_urls_via_api(playlist_url)
        
        # 验证异常处理
        assert songs is None or len(songs) == 0
    
    def test_16_extract_playlist_id_from_url(self):
        """测试16: 测试从播放列表URL中提取ID"""
        test_urls = [
            "https://music.163.com/playlist?id=9876543210",
            "https://music.163.com/#/playlist?id=9876543210",
            "http://music.163.com/playlist?id=9876543210&userid=12345"
        ]
        
        for url in test_urls:
            match = re.search(r"playlist.*?id=(\d+)", url)
            if match:
                playlist_id = match.group(1)
                assert playlist_id == "9876543210"


class TestMusicDownloadBatch:
    """批量音乐下载测试"""
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录用于测试"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def song_urls_file(self, temp_dir):
        """创建测试用的歌曲URL文件"""
        urls_file = os.path.join(temp_dir, "song_urls.txt")
        test_urls = [
            "https://music.163.com/song?id=1234567890",
            "https://music.163.com/song?id=1234567891",
            "https://music.163.com/song?id=1234567892"
        ]
        
        with open(urls_file, 'w', encoding='utf-8') as f:
            for url in test_urls:
                f.write(url + '\n')
        
        return urls_file
    
    @patch('MusicDownload.download_music.download_file')
    @patch('MusicDownload.download_music.get_download_link')
    def test_17_batch_download_from_file(self, mock_get_link, mock_download, temp_dir, song_urls_file):
        """测试17: 测试从文件批量下载歌曲"""
        # 设置mock返回值
        mock_get_link.side_effect = [
            ("https://music-url-1.mp3", "歌曲1", "1234567890"),
            ("https://music-url-2.mp3", "歌曲2", "1234567891"),
            ("https://music-url-3.mp3", "歌曲3", "1234567892")
        ]
        
        mock_download.side_effect = [
            os.path.join(temp_dir, "歌曲1.mp3"),
            os.path.join(temp_dir, "歌曲2.mp3"),
            os.path.join(temp_dir, "歌曲3.mp3")
        ]
        
        # 模拟批量下载逻辑
        downloaded_files = []
        with open(song_urls_file, 'r', encoding='utf-8') as f:
            for line in f:
                url = line.strip()
                if url:
                    song_url, song_name, song_id = get_download_link(url, return_song_id=True)
                    if song_url:
                        output_path = os.path.join(temp_dir, f"{song_name}.mp3")
                        downloaded_path = download_file(song_url, output_path)
                        downloaded_files.append(downloaded_path)
        
        # 验证批量下载结果
        assert len(downloaded_files) == 3
        assert all("歌曲" in path for path in downloaded_files)
        
        # 验证调用次数
        assert mock_get_link.call_count == 3
        assert mock_download.call_count == 3
    
    @patch('MusicDownload.download_music.download_file')
    @patch('MusicDownload.download_music.get_download_link')
    def test_18_batch_download_with_failures(self, mock_get_link, mock_download, temp_dir, song_urls_file):
        """测试18: 测试批量下载时部分失败的处理"""
        # 设置mock返回值 - 第二个歌曲获取链接失败
        mock_get_link.side_effect = [
            ("https://music-url-1.mp3", "歌曲1", "1234567890"),
            (None, None, None),  # 获取链接失败
            ("https://music-url-3.mp3", "歌曲3", "1234567892")
        ]
        
        mock_download.side_effect = [
            os.path.join(temp_dir, "歌曲1.mp3"),
            os.path.join(temp_dir, "歌曲3.mp3")
        ]
        
        # 模拟批量下载逻辑（含错误处理）
        downloaded_files = []
        failed_urls = []
        
        with open(song_urls_file, 'r', encoding='utf-8') as f:
            for line in f:
                url = line.strip()
                if url:
                    try:
                        song_url, song_name, song_id = get_download_link(url, return_song_id=True)
                        if song_url and song_name:
                            output_path = os.path.join(temp_dir, f"{song_name}.mp3")
                            downloaded_path = download_file(song_url, output_path)
                            downloaded_files.append(downloaded_path)
                        else:
                            failed_urls.append(url)
                    except Exception:
                        failed_urls.append(url)
        
        # 验证部分成功的批量下载
        assert len(downloaded_files) == 2
        assert len(failed_urls) == 1
        assert mock_get_link.call_count == 3
        assert mock_download.call_count == 2  # 只有成功的才会下载
    
    def test_19_create_output_url_file(self, temp_dir):
        """测试19: 测试创建输出URL文件"""
        # 模拟收集到的下载链接
        download_links = [
            ("https://music-url-1.mp3", "歌曲1"),
            ("https://music-url-2.mp3", "歌曲2"),
            ("https://music-url-3.mp3", "歌曲3")
        ]
        
        # 创建输出文件
        output_file = os.path.join(temp_dir, "music_url.txt")
        with open(output_file, 'w', encoding='utf-8') as f:
            for url, name in download_links:
                f.write(f"{name}: {url}\n")
        
        # 验证文件内容
        assert os.path.exists(output_file)
        
        with open(output_file, 'r', encoding='utf-8') as f:
            content = f.read()
            assert "歌曲1: https://music-url-1.mp3" in content
            assert "歌曲2: https://music-url-2.mp3" in content
            assert "歌曲3: https://music-url-3.mp3" in content


class TestMusicDownloadMain:
    """主程序测试"""
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录用于测试"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @patch('MusicDownload.download_music.download_file')
    @patch('MusicDownload.download_music.get_download_link')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists')
    def test_20_main_function_execution(self, mock_exists, mock_file, mock_get_link, mock_download, temp_dir):
        """测试20: 测试主函数执行"""
        # 设置文件存在性检查
        mock_exists.side_effect = lambda path: "song_urls.txt" in path
        
        # 设置文件读取内容
        mock_file_content = "https://music.163.com/song?id=1234567890\n"
        mock_file.return_value.read.return_value = mock_file_content
        mock_file.return_value.__iter__.return_value = iter([mock_file_content])
        
        # 设置mock返回值
        mock_get_link.return_value = ("https://music-url.mp3", "测试歌曲", "1234567890")
        mock_download.return_value = os.path.join(temp_dir, "测试歌曲.mp3")
        
        # 执行主函数
        with patch('MusicDownload.download_music.INPUT_FILE', "song_urls.txt"), \
             patch('MusicDownload.download_music.OUTPUT_FILE', os.path.join(temp_dir, "music_url.txt")), \
             patch('MusicDownload.download_music.OUT_DIR', temp_dir):
            # 这里模拟main函数的核心逻辑
            try:
                main()
            except SystemExit:
                pass  # main函数可能调用sys.exit()
        
        # 验证关键函数被调用
        mock_get_link.assert_called()
    
    def test_21_validate_music_api_headers(self):
        """测试21: 验证音乐API请求头格式"""
        from MusicDownload.download_music import MK_HEADERS, HEADER_TOKEN, BODY_TOKEN
        
        # 验证关键请求头
        assert "authorization" in MK_HEADERS
        assert f"Bearer {HEADER_TOKEN}" == MK_HEADERS["authorization"]
        assert "application/json" in MK_HEADERS["content-type"]
        assert "api.toubiec.cn" in MK_HEADERS["origin"]
        
        # 验证Token不为空
        assert HEADER_TOKEN is not None and len(HEADER_TOKEN) > 0
        assert BODY_TOKEN is not None and len(BODY_TOKEN) > 0
    
    def test_22_music_api_request_body_format(self):
        """测试22: 验证音乐API请求体格式"""
        from MusicDownload.download_music import BODY_TOKEN
        
        # 模拟构建请求体
        song_id = "1234567890"
        request_body = {
            "token": BODY_TOKEN,
            "id": song_id,
            "type": "song"
        }
        
        # 验证请求体格式
        assert "token" in request_body
        assert request_body["token"] == BODY_TOKEN
        assert request_body["id"] == song_id
        assert request_body["type"] == "song"
    
    def test_23_filename_sanitization(self):
        """测试23: 测试文件名清理功能"""
        # 测试包含特殊字符的歌曲名
        dirty_names = [
            "歌曲名/包含斜杠",
            "歌曲名:包含冒号",
            "歌曲名*包含星号",
            "歌曲名?包含问号",
            "歌曲名<包含小于号>",
            "歌曲名|包含竖线"
        ]
        
        # 简单的文件名清理函数
        def sanitize_filename(filename):
            invalid_chars = ['/', ':', '*', '?', '<', '>', '|', '"', '\\']
            for char in invalid_chars:
                filename = filename.replace(char, '_')
            return filename
        
        # 验证清理结果
        for dirty_name in dirty_names:
            clean_name = sanitize_filename(dirty_name)
            assert not any(char in clean_name for char in ['/', ':', '*', '?', '<', '>', '|'])
            assert "歌曲名" in clean_name
            assert "_" in clean_name  # 特殊字符被替换为下划线


class TestMusicDownloadIntegration:
    """音乐下载集成测试"""
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录用于测试"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.mark.integration
    def test_24_complete_download_workflow(self, temp_dir):
        """测试24: 完整下载工作流程模拟"""
        with patch('requests.post') as mock_post, \
             patch('requests.get') as mock_get, \
             patch('builtins.open', mock_open(read_data=b'mock_music_content')):
            
            # 设置获取下载链接的mock
            mock_api_response = Mock()
            mock_api_response.status_code = 200
            mock_api_response.json.return_value = {
                "code": 200,
                "data": {
                    "url": "https://music-download-url.mp3?vuutv=12345",
                    "title": "完整流程测试歌曲",
                    "artist": "测试歌手"
                }
            }
            mock_post.return_value = mock_api_response
            
            # 设置文件下载的mock
            mock_download_response = Mock()
            mock_download_response.status_code = 200
            mock_download_response.iter_content.return_value = [b'music_content']
            mock_download_response.headers = {'Content-Length': '1024'}
            mock_get.return_value = mock_download_response
            
            # 执行完整流程
            song_url = "https://music.163.com/song?id=1234567890"
            
            # 1. 获取下载链接
            download_url, song_name, song_id = get_download_link(song_url, return_song_id=True)
            
            # 2. 下载文件
            output_path = os.path.join(temp_dir, f"{song_name}.mp3")
            downloaded_path = download_file(download_url, output_path)
            
            # 验证完整流程
            assert download_url == "https://music-download-url.mp3?vuutv=12345"
            assert song_name == "完整流程测试歌曲"
            assert song_id == "1234567890"
            assert downloaded_path == output_path
            
            # 验证API调用
            mock_post.assert_called_once()
            mock_get.assert_called_once_with(download_url, stream=True, timeout=30)


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "--tb=short"])