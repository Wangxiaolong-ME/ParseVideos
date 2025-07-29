import asyncio
import logging
from TikTokDownload.tiktok_post import TikTokPostManager  # 直接导入您的类

# 配置日志，方便查看实际抓取和解析过程
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(lineno)s - %(levelname)s - %(message)s')
logging.getLogger('httpx').setLevel(logging.WARN)
logging.getLogger('httpcore').setLevel(logging.WARN)

async def main():
    # 请替换为实际的 TikTok 短链接
    tiktok_short_url = "https://vm.tiktok.com/ZMScnvXJ5/"   # 视频
    # tiktok_short_url = "https://vt.tiktok.com/ZSSj46cho/"   # 图集

    print(f"尝试从链接获取 TikTok 作品详情: {tiktok_short_url}")

    try:
        # 创建 TikTokPostManager 实例
        manager = TikTokPostManager(tiktok_short_url)

        # 调用 fetch_details 方法
        await manager.fetch_details()
        post_data = manager.tiktok_post_data
        video = manager.processed_video_options
        image = manager.processed_images
        # 打印获取到的作品详情
        if manager.tiktok_post_data:
            print("\n--- 成功获取作品详情 ---")
            print(f"标题: {manager.tiktok_post_data.title}")
            print(f"是否为视频: {manager.tiktok_post_data.is_video}")
            if manager.tiktok_post_data.is_video:
                print(f"视频文件数量: {len(manager.processed_video_options)}")
                for i, video in enumerate(manager.processed_video_options):
                    print(f"  视频 {i + 1} URL: {video.url} (分辨率: {video.resolution})")
            else:
                print(f"图片文件数量: {len(manager.processed_images)}")
                for i, image in enumerate(manager.processed_images):
                    print(f"  图片 {i + 1} URL: {image.url}")
        else:
            print("未能获取到作品详情，tiktok_post_data 为空。")

        await manager.download_video(video)
        await manager.download_image_album()
        await manager.download_music()

    except Exception as e:
        print(f"\n--- 获取作品详情时发生错误 ---")
        print(f"错误类型: {type(e).__name__}")
        print(f"错误信息: {e}")


if __name__ == "__main__":
    asyncio.run(main())