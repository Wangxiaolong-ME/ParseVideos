# 基础用法：下载最高清晰度
`python main.py "https://v.douyin.com/iYyD11A/"`

# 指定分辨率下载
`python main.py "抖音短链接" -r 1080`

# 复杂用法：筛选大小在10-50MB之间，对每个分辨率保留文件最大的版本，然后全部下载
`python main.py "抖音短链接" --min-size 10 --max-size 50 --dedup largest_size --all`
>##### --dedup可选参数:

>'highest_bitrate' (最高码率),

>'lowest_bitrate' (最低码率),

>'largest_size' (最大文件),

>'smallest_size' (最小文件).

# 先获取并保存元数据，之后再从元数据加载并下载
## 第一步：获取并保存
`python main.py "抖音短链接" --save-meta`
## 第二步：从文件加载并下载
`python main.py "随意填" --load-meta "./douyin_downloads/视频标题_metadata.json"`