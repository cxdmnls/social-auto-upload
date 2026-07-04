# -*- coding: utf-8 -*-
from datetime import datetime
import asyncio
import os

from playwright.async_api import Playwright, async_playwright, Page

# 假设你在 conf 和 utils 中有相应的配置
from conf import LOCAL_CHROME_PATH, LOCAL_CHROME_HEADLESS
from utils.base_social_media import set_init_script
# 请确保在 utils/log.py 中添加了 bilibili_logger
from utils.log import bilibili_logger 


async def cookie_auth(account_file):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=LOCAL_CHROME_HEADLESS)
        context = await browser.new_context(storage_state=account_file)
        context = await set_init_script(context)
        # 创建一个新的页面
        page = await context.new_page()
        # 访问 B站创作中心上传页
        await page.goto("https://member.bilibili.com/platform/upload/video/frame")
        try:
            await page.wait_for_url("https://member.bilibili.com/platform/upload/video/frame", timeout=5000)
        except:
            print("[+] 等待5秒 cookie 失效")
            await context.close()
            await browser.close()
            return False
            
        # 判断是否跳转到了登录页 (passport.bilibili.com)
        if "passport.bilibili.com" in page.url:
            print("[+] 等待5秒 cookie 失效")
            return False
        else:
            print("[+] cookie 有效")
            return True


async def bilibili_setup(account_file, handle=False):
    if not os.path.exists(account_file) or not await cookie_auth(account_file):
        if not handle:
            # Todo alert message
            return False
        bilibili_logger.info('[+] cookie文件不存在或已失效，即将自动打开浏览器，请扫码登录，登陆后会自动生成cookie文件')
        await bilibili_cookie_gen(account_file)
    return True


async def bilibili_cookie_gen(account_file):
    async with async_playwright() as playwright:
        options = {
            'headless': False,  # 必须开启浏览器窗口
            'args': ['--start-maximized'] # 最大化窗口方便扫码
        }
        browser = await playwright.chromium.launch(**options)
        context = await browser.new_context()
        # 注入 stealth 脚本防止被检测（建议加上）
        await set_init_script(context) 
        page = await context.new_page()
        
        await page.goto("https://passport.bilibili.com/login")
        
        print(">>> 请在浏览器中扫码登录...")
        print(">>> 注意：登录成功后，请确保页面加载完成...")

        while "passport" in page.url:
            await asyncio.sleep(1)
        
        print(">>> 检测到跳转，等待 Cookie 写入...")
        # 跳转后稍微等一下，确保 Cookie 写入本地存储
        await page.wait_for_load_state("networkidle") 
        await asyncio.sleep(3) 

        # 保存 Cookie
        await context.storage_state(path=account_file)
        print(f">>> Cookie 已保存至: {account_file}")
        
        await browser.close()


class BilibiliVideo(object):
    def __init__(self, title, file_path, tags, publish_date: datetime, account_file, thumbnail_path=None, desc=''):
        self.title = title
        self.file_path = file_path
        self.tags = tags
        self.publish_date = publish_date
        self.account_file = account_file
        self.date_format = '%Y-%m-%d %H:%M'
        self.local_executable_path = LOCAL_CHROME_PATH
        self.headless = LOCAL_CHROME_HEADLESS
        self.thumbnail_path = thumbnail_path
        self.desc = desc # B站更常用简介，而不是商品链接

    async def set_schedule_time_bilibili(self, page, publish_date):
        bilibili_logger.info(" [-] 正在设置定时发布 (HTML精准适配版)...")

        # =======================================================
        # 1. 开启定时发布开关
        # =======================================================
        # 定位依据：image_63ea17.png 显示开关容器类名为 .switch-container
        switch_btn = page.locator(".switch-container").first
        
        # 判断依据：image_63dbb3.png 显示日期选择器的类名为 .date-picker-date
        # 如果这个元素可见，说明开关已经是【开启】状态
        is_open = await page.locator(".date-picker-date").is_visible()

        if is_open:
            bilibili_logger.info("  [!] 检测到日期选择器已显示，开关已开启，跳过点击")
        else:
            bilibili_logger.info("  [-] 开关未开启，正在点击...")
            if await switch_btn.count():
                await switch_btn.click()
                # 必须等待 DOM 变化，等待日期组件渲染出来
                try:
                    await page.wait_for_selector(".date-picker-date", state="visible", timeout=3000)
                    bilibili_logger.success("  [+] 开关开启成功")
                except:
                    bilibili_logger.error("  [x] 开关点击后未出现日期选择器，可能点击失败")
                    return
            else:
                bilibili_logger.error("  [x] 找不到 .switch-container 元素")
                return

        # =======================================================
        # 2. 设置日期
        # =======================================================
        # 定位依据：image_63dbb3.png -> div.date-picker-date
        date_trigger = page.locator(".date-picker-date").first
        
        if await date_trigger.count():
            bilibili_logger.info(f"  [-] 点击日期选择框...")
            await date_trigger.click()
            # 依据 image_638559.png，日历主体结构出现
            await page.wait_for_selector(".date-picker-nav-wrp", timeout=3000)

            # --- 日历面板翻页逻辑 ---
            target_year = str(publish_date.year)
            target_month = str(publish_date.month) # 注意：这里不要补0，B站通常显示 "12月" 而不是 "01月"
            
            # 循环检测面板标题 (最多翻12次)
            for _ in range(12):
                # 依据 image_638559.png: 头部导航是 .date-picker-nav-wrp
                nav_wrp = page.locator(".date-picker-nav-wrp").first
                nav_text = await nav_wrp.inner_text()
                
                # 检查是否包含目标年份和月份 (例如 "2025" 和 "12")
                # 加 "月" 字匹配防止把年份当成月份
                if target_year in nav_text and f"{target_month}月" in nav_text:
                    bilibili_logger.info(f"  [+] 年月匹配成功: {nav_text}")
                    break 
                else:
                    # 点击“下个月”
                    # 依据 flex 布局，通常最后一个 div/span/svg 是下一月按钮
                    # 这里尝试点击头部导航栏里的最后一个可点击元素
                    # 也可以尝试找 iconfont 或 svg
                    next_btn = nav_wrp.locator("div, span, i").last
                    if await next_btn.count():
                        await next_btn.click()
                        await asyncio.sleep(0.3)
                    else:
                        bilibili_logger.warning("  [-] 未找到翻页按钮，尝试直接寻找日期")
                        break

            # --- 点击具体的日期 ---
            day_text = str(publish_date.day)
            # 依据 image_638559.png: 日期主体是 .date-picker-body-wrp
            # 我们在 body 里找文本为当前日期的元素
            # exact=True 防止 "1" 匹配到 "11"
            # 并排除可能存在的 disable 元素 (虽然类名不确定，但通常点击也没事)
            day_cell = page.locator(".date-picker-body-wrp div, .date-picker-body-wrp span").get_by_text(day_text, exact=True).first
            
            if await day_cell.count():
                await day_cell.click()
                bilibili_logger.success(f"  [+] 日期 {day_text} 设置成功")
            else:
                bilibili_logger.error(f"  [x] 在日历面板中没找到日期: {day_text}")
            
            await asyncio.sleep(0.5)

        # =======================================================
        # 3. 设置时间
        # =======================================================
        # 定位依据：image_63dbb3.png -> div.date-picker-timer
        time_trigger = page.locator(".date-picker-timer").first
        
        if await time_trigger.count():
            target_hour = publish_date.strftime("%H")
            target_minute = publish_date.strftime("%M")
            bilibili_logger.info(f"  [-] 点击时间选择框... 目标: {target_hour}:{target_minute}")
            
            await time_trigger.click()
            # 依据 image_6384b9.png，等待时间面板 .time-picker-body-wrp
            await page.wait_for_selector(".time-picker-body-wrp", timeout=3000)

            # 依据 image_6384b9.png: 每一列是 .time-picker-panel-select-wrp
            # 每一个选项是 .time-picker-panel-select-item
            
            # --- 选择小时 (第1列) ---
            # 找到包含目标小时文本的 item
            hour_item = page.locator(".time-picker-panel-select-wrp").nth(0).locator(f".time-picker-panel-select-item:text-is('{target_hour}')")
            
            if await hour_item.count():
                # 检查是否被禁用 (image_6384b9.png 显示有 disabled 类)
                if "disabled" in await hour_item.get_attribute("class") or "":
                    bilibili_logger.error(f"  [x] 目标小时 {target_hour} 不可由 (被禁用)")
                else:
                    await hour_item.scroll_into_view_if_needed()
                    await hour_item.click()
            else:
                bilibili_logger.error(f"  [x] 未找到小时选项: {target_hour}")

            # --- 选择分钟 (第2列) ---
            # 找到包含目标分钟文本的 item
            minute_item = page.locator(".time-picker-panel-select-wrp").nth(1).locator(f".time-picker-panel-select-item:text-is('{target_minute}')")
            
            if await minute_item.count():
                if "disabled" in await minute_item.get_attribute("class") or "":
                    bilibili_logger.error(f"  [x] 目标分钟 {target_minute} 不可用 (被禁用)")
                else:
                    await minute_item.scroll_into_view_if_needed()
                    await minute_item.click()
            else:
                # B站分钟可能是5分钟间隔，如果找不到精确的，可能需要找最近的？
                # 这里暂且假设你能精确匹配，或者你传进来的时间是符合B站规则的
                bilibili_logger.error(f"  [x] 未找到分钟选项: {target_minute}")

            # 点击空白处关闭下拉 (防止遮挡)
            await page.click("body")
            bilibili_logger.success("  [+] 时间设置成功")
            await asyncio.sleep(1)

    async def handle_upload_error(self, page):
        bilibili_logger.info('视频出错了，重新上传中')
        # B站通常需要刷新页面或点击特定的重试按钮，这里假设是刷新重来
        await page.reload()
        await self.upload_file(page)

    async def upload_file(self, page):
        bilibili_logger.info("  [-] 正在定位视频上传入口...")

        try:
            # 1. 定义选择器：找支持 .mp4 的 input
            selector = "input[type='file'][accept*='.mp4']"
            
            # 2. 关键修复：使用 .first 属性
            upload_input = page.locator(selector).first
            
            # 3. 如果找不到带 accept 的（防备B站改版），就找任意 input
            if await upload_input.count() == 0:
                bilibili_logger.warning("  [-] 未找到精确匹配的视频Input，尝试使用通用Input...")
                upload_input = page.locator("input[type='file']").first

            # 4. 注入文件
            await upload_input.set_input_files(self.file_path)
            bilibili_logger.info("  [+] 视频文件注入成功")
            
        except Exception as e:
            bilibili_logger.error(f"  [-] 上传失败: {e}")
            raise e

    async def upload(self, playwright: Playwright) -> None:
        if self.local_executable_path:
            browser = await playwright.chromium.launch(headless=self.headless, executable_path=self.local_executable_path)
        else:
            browser = await playwright.chromium.launch(headless=self.headless)
        
        context = await browser.new_context(storage_state=f"{self.account_file}")
        context = await set_init_script(context)
        page = await context.new_page()

        # 访问 B站上传页
        await page.goto("https://member.bilibili.com/platform/upload/video/frame")
        bilibili_logger.info(f'[+]正在上传-------{self.title}.mp4')
        
        try:
            await page.wait_for_url("https://member.bilibili.com/platform/upload/video/frame", timeout=10000)
        except:
             bilibili_logger.error(" [-] 进入上传页超时")

        # 上传文件
        try:
            # B站 Input 比较隐蔽，通常直接 set_input_files 到页面唯一的 file input 即可
            await page.locator("input[type='file']").set_input_files(self.file_path)
        except Exception as e:
            bilibili_logger.info(" [-] 常规上传失败，尝试点击上传模式...")
            await self.upload_file(page)

        # 等待文件开始解析，通常会显示进度条或编辑界面出现
        # B站上传后会立即展示编辑表单，不需要像抖音那样等很久跳转
        try:
            await page.wait_for_selector("input[placeholder*='标题']", timeout=20000)
        except:
             bilibili_logger.error(" [-] 未检测到编辑界面，上传可能失败")

        # 1. 填写标题
        await asyncio.sleep(1)
        bilibili_logger.info(f'  [-] 正在填充标题...')
        title_input = page.locator("input[placeholder*='标题']")
        # 清空默认文件名标题
        await title_input.click()
        await title_input.press("Control+A")
        await title_input.press("Backspace")
        await title_input.fill(self.title[:80]) # B站标题限制80字

        # 2. 填写简介
        if self.desc:
            bilibili_logger.info(f'  [-] 正在填充简介...')
            # B站简介是 contenteditable 的 div
            desc_editor = page.locator("div.ql-editor[contenteditable='true']")
            if await desc_editor.count():
                await desc_editor.fill(self.desc)

        # 3. 填写标签
        bilibili_logger.info(f'  [-] 正在添加标签...')
        tag_input = page.locator("input[placeholder*='标签']").first
        # 确保焦点在标签输入框
        await tag_input.click()
        for tag in self.tags:
            await tag_input.fill(tag)
            await asyncio.sleep(0.5)
            await tag_input.press("Enter")
            await asyncio.sleep(0.5)
        
        bilibili_logger.info(f'总共添加{len(self.tags)}个标签')

        # 4. 设置封面 (如果有)
        if self.thumbnail_path:
            await self.set_thumbnail(page, self.thumbnail_path)

        detect_count = 0
        max_wait_time = 60 # 最多等1分钟
        
        while True:
            detect_count += 2
            if detect_count > max_wait_time:
                bilibili_logger.error("  [-] 等待上传超时！强制退出")
                break

            try:
                # === 成功标志检测 ===
                # 标志1: 明确的“上传成功”文本
                is_success = await page.locator("text=上传完成").count() > 0
                # 标志2: “转码中”也算成功（说明文件已经传完了，服务器在处理）
                is_transcoding = await page.locator("text=转码中").count() > 0
                # 标志3: 出现了“更改封面”按钮（说明视频已就绪）
                has_cover_btn = await page.locator("text=更改封面").count() > 0
                
                if is_success or is_transcoding or has_cover_btn:
                    bilibili_logger.success("  [-] 视频上传完毕 (检测到成功标志)")
                    break
                
                # === 失败标志检测 ===
                if await page.locator("text=上传失败").count() > 0:
                    bilibili_logger.error("  [-] 发现上传出错了...")
                    # 可以在这里添加重试逻辑
                    raise Exception("B站提示上传失败")

                detect_count_log = f"({detect_count}s)"
                bilibili_logger.info(f"  [-] 正在上传视频中... {detect_count_log}")
                
                # 截图调试
                # await page.screenshot(path=f"debug_uploading_{detect_count}.png")
                
                await asyncio.sleep(2)
                
            except Exception as e:
                # 忽略检测过程中的微小报错，继续等待
                detect_count_log = f"({detect_count}s)"
                bilibili_logger.info(f"  [-] 等待中... {detect_count_log}")
                await asyncio.sleep(2)

        # 6. 定时发布
        if self.publish_date != 0:
            await self.set_schedule_time_bilibili(page, self.publish_date)

        # 7. 提交
        bilibili_logger.info("  [-] 准备发布...")
        
        # 优化点：使用截图中的精确类名 .submit-add
        submit_btn = page.locator(".submit-add").first
        
        # 最大重试次数，防止无限死循环
        max_retries = 20
        retry_count = 0
        
        while retry_count < max_retries:
            retry_count += 1
            try:
                if await submit_btn.count():
                    # 1. 点击按钮
                    await submit_btn.click(force=True)
                    await asyncio.sleep(2) 
                    
                    if "upload-manager" in page.url:
                        bilibili_logger.success("  [+] URL跳转成功，视频发布完成！")
                        break
                    
                    if await page.locator("text=稿件投递成功").count():
                        bilibili_logger.success("  [+] 检测到成功提示，视频发布完成！")
                        break
                
                else:
                    bilibili_logger.error("  [x] 找不到 .submit-add 按钮，请检查选择器")
                    break
                
                await asyncio.sleep(2)
                
            except Exception as e:
                bilibili_logger.error(f"  [-] 发布过程发生错误: {e}")
                await asyncio.sleep(2)
        
        if retry_count >= max_retries:
             bilibili_logger.error("  [x] 发布超时，请检查 debug_timeout.png")
             await page.screenshot(path="debug_timeout.png")

        await context.storage_state(path=self.account_file)
        bilibili_logger.success('  [-]cookie更新完毕！')
        await asyncio.sleep(2)
        await context.close()
        await browser.close()

    async def set_thumbnail(self, page: Page, thumbnail_path: str):
        if thumbnail_path:
            bilibili_logger.info('  [-] 正在设置视频封面...')
            
            # 1. 触发封面上传弹窗
            # B站界面可能有变化，通常有一个 "更改封面" 或 input
            # 先找 visible 的上传入口
            cover_input = page.locator("div.cover-upload-container input[type='file']")
            
            # 如果找不到特定的 container，尝试点击“上传封面”按钮触发
            if await cover_input.count() == 0:
                await page.click("text=更改封面") # 或者 text=上传封面
                # 等待弹窗里的 input 出现
                cover_input = page.locator("div.modal-content input[type='file']")

            if await cover_input.count():
                 await cover_input.set_input_files(thumbnail_path)
            else:
                 bilibili_logger.error("  [-] 未找到封面上传入口")
                 return

            # 2. 处理裁剪确认弹窗
            # B站上传图片后，通常会弹出一个裁剪框，需要点击“确定”
            try:
                await page.wait_for_selector("text=裁剪封面", timeout=5000)
                await asyncio.sleep(1) 
                # 点击确定/完成按钮
                confirm_btn = page.locator("div.modal-footer span:text-is('完成')")
                if not await confirm_btn.count():
                     confirm_btn = page.locator("div.modal-footer span:text-is('确定')")
                
                if await confirm_btn.count():
                    await confirm_btn.click()
                    bilibili_logger.info('  [+] 视频封面设置完成！')
                    # 等待弹窗消失
                    await asyncio.sleep(1)
            except:
                bilibili_logger.warning("  [-] 未检测到封面裁剪弹窗，可能自动通过")
    
    async def main(self):
        async with async_playwright() as playwright:
            await self.upload(playwright)