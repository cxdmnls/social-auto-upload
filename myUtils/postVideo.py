import asyncio
from pathlib import Path

from conf import BASE_DIR
from uploader.douyin_uploader.main import DouYinVideo
from uploader.ks_uploader.main import KSVideo
from uploader.tencent_uploader.main import TencentVideo
from uploader.xiaohongshu_uploader.main import XiaoHongShuVideo
from uploader.bilibili_uploader.main import BilibiliVideo
from utils.constant import TencentZoneTypes
from utils.files_times import generate_schedule_time_next_day
from uploader.bilibili_uploader.main import bilibili_setup 

def process_tags(tags):
    """
    清洗逻辑：
    1. 替换中文/英文逗号为空格
    2. 移除所有 '#' 号 (防止生成 ##风景)
    3. 按空格切割成列表
    """
    if not tags:
        return []
    
    # 如果已经是列表，遍历清洗每一项
    if isinstance(tags, list):
        return [str(t).replace("#", "").strip() for t in tags if str(t).strip()]
    
    # 如果是字符串
    if isinstance(tags, str):
        # 1. 替换逗号
        cleaned = tags.replace("，", " ").replace(",", " ")
        # 2. 移除井号 (关键修改)
        cleaned = cleaned.replace("#", "")
        # 3. 切割并去空
        tag_list = [t for t in cleaned.split(" ") if t]
        return tag_list
    
    return []

def post_video_tencent(title,files,tags,account_file,category=TencentZoneTypes.LIFESTYLE.value,enableTimer=False,videos_per_day = 1, daily_times=None,start_days = 0, is_draft=False):
    # 生成文件的完整路径
    account_file = [Path(BASE_DIR / "cookiesFile" / file) for file in account_file]
    files = [Path(BASE_DIR / "videoFile" / file) for file in files]
    tag_list = process_tags(tags)
    if enableTimer:
        publish_datetimes = generate_schedule_time_next_day(len(files), videos_per_day, daily_times,start_days)
    else:
        publish_datetimes = [0 for i in range(len(files))]
    for index, file in enumerate(files):
        for cookie in account_file:
            print(f"文件路径{str(file)}")
            # 打印视频文件名、标题和 hashtag
            print(f"视频文件名：{file}")
            print(f"标题：{title}")
            print(f"Hashtag：{tags}")
            app = TencentVideo(title, str(file), tag_list, publish_datetimes[index], cookie, category, is_draft)
            asyncio.run(app.main(), debug=False)


def post_video_DouYin(title,files,tags,account_file,category=TencentZoneTypes.LIFESTYLE.value,enableTimer=False,videos_per_day = 1, daily_times=None,start_days = 0,
                      thumbnail_path = '',
                      productLink = '', productTitle = ''):
    # 生成文件的完整路径
    account_file = [Path(BASE_DIR / "cookiesFile" / file) for file in account_file]
    files = [Path(BASE_DIR / "videoFile" / file) for file in files]
    tag_list = process_tags(tags)
    if enableTimer:
        publish_datetimes = generate_schedule_time_next_day(len(files), videos_per_day, daily_times,start_days)
    else:
        publish_datetimes = [0 for i in range(len(files))]
    for index, file in enumerate(files):
        for cookie in account_file:
            print(f"文件路径{str(file)}")
            # 打印视频文件名、标题和 hashtag
            print(f"视频文件名：{file}")
            print(f"标题：{title}")
            print(f"Hashtag：{tags}")
            app = DouYinVideo(title, str(file), tag_list, publish_datetimes[index], cookie, thumbnail_path, productLink, productTitle)
            asyncio.run(app.main(), debug=False)


def post_video_ks(title,files,tags,account_file,category=TencentZoneTypes.LIFESTYLE.value,enableTimer=False,videos_per_day = 1, daily_times=None,start_days = 0):
    # 生成文件的完整路径
    account_file = [Path(BASE_DIR / "cookiesFile" / file) for file in account_file]
    files = [Path(BASE_DIR / "videoFile" / file) for file in files]
    tag_list = process_tags(tags)
    if enableTimer:
        publish_datetimes = generate_schedule_time_next_day(len(files), videos_per_day, daily_times,start_days)
    else:
        publish_datetimes = [0 for i in range(len(files))]
    for index, file in enumerate(files):
        for cookie in account_file:
            print(f"文件路径{str(file)}")
            # 打印视频文件名、标题和 hashtag
            print(f"视频文件名：{file}")
            print(f"标题：{title}")
            print(f"Hashtag：{tags}")
            app = KSVideo(title, str(file), tag_list, publish_datetimes[index], cookie)
            asyncio.run(app.main(), debug=False)

def post_video_xhs(title,files,tags,account_file,category=TencentZoneTypes.LIFESTYLE.value,enableTimer=False,videos_per_day = 1, daily_times=None,start_days = 0):
    # 生成文件的完整路径
    account_file = [Path(BASE_DIR / "cookiesFile" / file) for file in account_file]
    files = [Path(BASE_DIR / "videoFile" / file) for file in files]
    tag_list = process_tags(tags)
    file_num = len(files)
    if enableTimer:
        publish_datetimes = generate_schedule_time_next_day(file_num, videos_per_day, daily_times,start_days)
    else:
        publish_datetimes = 0
    for index, file in enumerate(files):
        for cookie in account_file:
            # 打印视频文件名、标题和 hashtag
            print(f"视频文件名：{file}")
            print(f"标题：{title}")
            print(f"Hashtag：{tags}")
            app = XiaoHongShuVideo(title, file, tag_list, publish_datetimes, cookie)
            asyncio.run(app.main(), debug=False)

# 引入之前的检查函数
def post_video_bilibili(title, file_list, tags, account_list, category=None, enableTimer=False, videos_per_day=1, daily_times=None, start_days=0):
    """
    完全复用 cli_main.py 的逻辑：
    1. 构造路径
    2. 调用 bilibili_setup 检查/修复 Cookie
    3. 调用 BilibiliVideo 发布
    """
    # 1. 路径处理
    # 后端传过来的是文件名（如 uuid.json），需要拼成绝对路径字符串
    # 注意：BilibiliVideo 接收的是 str 类型的 path
    account_file = str(BASE_DIR / "cookiesFile" / account_list[0])
    
    # 视频文件路径处理 (假设 file_list 里是绝对路径，如果不是则需要拼接)
    # 你的 app.py 里传过来的是 absolute path，这里直接用
    video_file = str(file_list[0])
    tag_list = process_tags(tags)

    # 2. 定义异步任务 (复刻 CLI 的 main 函数逻辑)
    async def task():
        print(f"[-] [B站] 正在验证账号: {account_file}")
        
        # 【关键步骤】调用 setup 进行预检查
        # handle=True 表示如果失效会弹窗修复，和 CLI 一样
        is_valid = await bilibili_setup(account_file, handle=True)
        
        if not is_valid:
            print(f"[-] [B站] 账号验证失败，跳过发布")
            return

        print(f"[-] [B站] 账号有效，开始发布: {title}")
        
        # 计算发布时间 (复用你的逻辑)
        publish_date = 0
        if enableTimer:
            # 这里简单处理，如果需要具体时间逻辑可以引用 utils.files_times
            from datetime import datetime, timedelta
            publish_date = datetime.now() + timedelta(days=start_days) # 示例

        # 【关键步骤】初始化上传对象
        # 注意：这里直接用你项目里原本的 BilibiliVideo 类
        app = BilibiliVideo(title, video_file, tag_list, publish_date, account_file)
        
        # 执行
        await app.main()

    # 3. 运行异步循环
    try:
        asyncio.run(task())
    except Exception as e:
        print(f"❌ [B站] 发布流程出错: {e}")



# post_video("333",["demo.mp4"],"d","d")
# post_video_DouYin("333",["demo.mp4"],"d","d")