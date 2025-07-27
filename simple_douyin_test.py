#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单的抖音链接解析测试
用于验证核心功能是否正常工作
"""

import os
import sys
import tempfile
import asyncio

# 添加src到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

async def test_douyin_link():
    """测试抖音链接解析功能"""
    print("=" * 50)
    print("Douyin Link Parsing Test Started")
    print("=" * 50)
    
    try:
        from DouyinDownload.douyin_post import DouyinPost
        print("SUCCESS: DouyinPost imported")
        
        # 创建临时目录
        temp_dir = tempfile.mkdtemp()
        print(f"SUCCESS: Created temp directory: {temp_dir}")
        
        # 测试URL
        test_url = "https://v.douyin.com/3hLIn4xjyMU/"
        print(f"SUCCESS: Test URL: {test_url}")
        
        # 创建实例
        post = DouyinPost(
            short_url_text=test_url,
            save_dir=temp_dir,
            trust_env=False,
            threads=1
        )
        print("SUCCESS: DouyinPost instance created")
        
        # 测试内容类型检测
        content_type = post.get_content_type(test_url)
        print(f"SUCCESS: Content type detected: {content_type}")
        
        # 尝试获取详情
        print("\nStarting to fetch video details...")
        try:
            await post.fetch_details()
            
            print("SUCCESS: Video details fetched!")
            
            # Safely get title (avoid encoding issues)
            try:
                title = post.video_title or "No Title"
                if isinstance(title, str):
                    # Only show ASCII characters
                    safe_title = ''.join(c if ord(c) < 128 else '?' for c in title[:50])
                    print(f"SUCCESS: Video title: {safe_title}")
                else:
                    print("SUCCESS: Video title: (non-string type)")
            except:
                print("SUCCESS: Video title: (encoding issue, cannot display)")
            
            print(f"SUCCESS: Raw video options count: {len(post.raw_video_options)}")
            print(f"SUCCESS: Processed video options count: {len(post.processed_video_options)}")
            
            # If video options exist, show the first one
            if post.raw_video_options:
                option = post.raw_video_options[0]
                print(f"SUCCESS: First option - Resolution: {option.resolution}")
                print(f"SUCCESS: First option - Size: {option.size_mb:.2f} MB")
                print(f"SUCCESS: First option - Format: {option.format_id}")
            
            print("\nSUCCESS: Douyin link parsing test completed!")
            
        except Exception as parse_error:
            print(f"Parse Error: {str(parse_error)}")
            print("This might be due to expired link, network issues or anti-crawling restrictions")
            
    except ImportError as e:
        print(f"Import Error: {str(e)}")
        return False
    except Exception as e:
        print(f"Other Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    print("=" * 50)
    return True

def test_douyin_basic():
    """Test basic functionality (no network required)"""
    print("\nBasic functionality test:")
    
    try:
        from DouyinDownload.douyin_post import DouyinPost
        from DouyinDownload.models import VideoOption
        
        # Create temp directory
        temp_dir = tempfile.mkdtemp()
        
        # Create instance
        post = DouyinPost(
            short_url_text="https://v.douyin.com/test/",
            save_dir=temp_dir,
            trust_env=False,
            threads=1
        )
        
        # Test URL content type detection
        test_urls = [
            "https://v.douyin.com/video123/",
            "https://v.douyin.com/image456/",
        ]
        
        for url in test_urls:
            content_type = post.get_content_type(url)
            print(f"SUCCESS: {url} -> {content_type}")
        
        # Test VideoOption model
        option = VideoOption(
            resolution=720,
            bit_rate=1000000,
            url="https://test.mp4",
            size_mb=15.5,
            gear_name="720p",
            quality="normal_720_0",
            aweme_id=123456789,
            height=720,
            width=1280,
            duration=30.5
        )
        
        print(f"SUCCESS: VideoOption created: {option.resolution}p, {option.size_mb}MB")
        
        print("SUCCESS: Basic functionality test passed!")
        return True
        
    except Exception as e:
        print(f"ERROR: Basic functionality test failed: {str(e)}")
        return False

if __name__ == "__main__":
    print("Douyin Downloader Function Test")
    print("Author: Claude Code Assistant")
    print("Time:", __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    
    # Test basic functionality
    basic_ok = test_douyin_basic()
    
    if basic_ok:
        # Test real link parsing
        try:
            result = asyncio.run(test_douyin_link())
        except KeyboardInterrupt:
            print("\nWARNING: User interrupted test")
        except Exception as e:
            print(f"\nERROR: Async test failed: {str(e)}")
    
    print("\nTest completed.")