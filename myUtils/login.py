import asyncio
import base64
import json
import sqlite3

from playwright.async_api import async_playwright

from myUtils.auth import check_cookie
from utils.base_social_media import set_init_script
import uuid
from pathlib import Path
from conf import BASE_DIR, LOCAL_CHROME_HEADLESS

def _emit_qrcode(status_queue, image_data, platform):
    if not image_data:
        status_queue.put("500")
        return
    status_queue.put(json.dumps({
        "type": "qrcode",
        "platform": platform,
        "data": image_data
    }, ensure_ascii=False))

def _emit_verification(status_queue, platform, method, message):
    status_queue.put(json.dumps({
        "type": "verification",
        "platform": platform,
        "method": method,
        "message": message
    }, ensure_ascii=False))


async def _send_qrcode_from_locator(status_queue, locator, platform):
    await locator.wait_for(state="visible", timeout=30000)
    image_bytes = await locator.screenshot()
    image_data = "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")
    _emit_qrcode(status_queue, image_data, platform)
    return image_data


async def _send_qrcode_from_candidates(status_queue, page, selectors, platform):
    for selector in selectors:
        locator = page.locator(selector)
        try:
            count = await locator.count()
        except Exception:
            continue

        for index in range(min(count, 10)):
            candidate = locator.nth(index)
            try:
                await candidate.wait_for(state="visible", timeout=3000)
                box = await candidate.bounding_box()
                if box and box.get("width", 0) >= 80 and box.get("height", 0) >= 80:
                    return await _send_qrcode_from_locator(status_queue, candidate, platform)
            except Exception:
                continue

    raise RuntimeError(f"未找到 {platform} 登录二维码")


async def _handle_identity_verification(page, status_queue, platform):
    """平台扫码后可能出现身份验证页。优先选择短信验证，并提示前端用户继续完成。"""
    try:
        if await page.get_by_text("身份验证").count() == 0:
            return False

        _emit_verification(
            status_queue,
            platform,
            "sms",
            "平台要求身份验证，正在尝试选择短信验证。请按前端提示和手机短信继续完成验证。"
        )

        sms_entry = page.get_by_text("发送短信验证").first
        if await sms_entry.count():
            await sms_entry.click()
            _emit_verification(
                status_queue,
                platform,
                "sms",
                "已选择短信验证。请查看手机短信/平台提示并完成验证，完成后系统会继续保存登录状态。"
            )
            return True

        _emit_verification(
            status_queue,
            platform,
            "manual",
            "检测到身份验证页，但没有找到短信验证入口。请在平台提示中选择可用验证方式完成验证。"
        )
        return True
    except Exception as e:
        _emit_verification(
            status_queue,
            platform,
            "manual",
            f"处理身份验证时出现异常：{e}。请根据平台页面提示完成验证。"
        )
        return True


async def _wait_after_identity_verification(page, original_url, status_queue, platform, timeout=300):
    handled = await _handle_identity_verification(page, status_queue, platform)
    if not handled:
        return

    end_time = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < end_time:
        if page.url != original_url and "verify" not in page.url.lower():
            return
        if await page.get_by_text("身份验证").count() == 0:
            return
        await asyncio.sleep(1)

    raise asyncio.TimeoutError(f"{platform} 身份验证超时")


# 抖音登录
async def douyin_cookie_gen(id,status_queue):
    url_changed_event = asyncio.Event()
    async def on_url_change():
        # 检查是否是主框架的变化
        if page.url != original_url:
            url_changed_event.set()
    async with async_playwright() as playwright:
        options = {
            'headless': LOCAL_CHROME_HEADLESS
        }
        # Make sure to run headed.
        browser = await playwright.chromium.launch(**options)
        # Setup context however you like.
        context = await browser.new_context()  # Pass any options
        context = await set_init_script(context)
        # Pause the page, and start recording manually.
        page = await context.new_page()
        await page.goto("https://creator.douyin.com/")
        original_url = page.url
        img_locator = page.get_by_role("img", name="二维码")
        # 获取二维码并发送到前端
        src = await _send_qrcode_from_locator(status_queue, img_locator, "douyin")
        print("✅ 图片地址:", src)
        # 监听页面的 'framenavigated' 事件，只关注主框架的变化
        page.on('framenavigated',
                lambda frame: asyncio.create_task(on_url_change()) if frame == page.main_frame else None)
        try:
            # 等待 URL 变化或超时
            await asyncio.wait_for(url_changed_event.wait(), timeout=200)  # 最多等待 200 秒
            print("监听页面跳转成功")
        except asyncio.TimeoutError:
            try:
                await _wait_after_identity_verification(page, original_url, status_queue, "douyin")
            except asyncio.TimeoutError:
                print("监听页面跳转/身份验证超时")
                await page.close()
                await context.close()
                await browser.close()
                status_queue.put("500")
                return None
        await _wait_after_identity_verification(page, original_url, status_queue, "douyin")
        uuid_v1 = uuid.uuid1()
        print(f"UUID v1: {uuid_v1}")
        # 确保cookiesFile目录存在
        cookies_dir = Path(BASE_DIR / "cookiesFile")
        cookies_dir.mkdir(exist_ok=True)
        await context.storage_state(path=cookies_dir / f"{uuid_v1}.json")
        result = await check_cookie(3, f"{uuid_v1}.json")
        if not result:
            status_queue.put("500")
            await page.close()
            await context.close()
            await browser.close()
            return None
        await page.close()
        await context.close()
        await browser.close()
        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                                INSERT INTO user_info (type, filePath, userName, status)
                                VALUES (?, ?, ?, ?)
                                ''', (3, f"{uuid_v1}.json", id, 1))
            conn.commit()
            print("✅ 用户状态已记录")
        status_queue.put("200")


# 视频号登录
async def get_tencent_cookie(id,status_queue):
    url_changed_event = asyncio.Event()
    async def on_url_change():
        # 检查是否是主框架的变化
        if page.url != original_url:
            url_changed_event.set()

    async with async_playwright() as playwright:
        options = {
            'args': [
                '--lang en-GB'
            ],
            'headless': LOCAL_CHROME_HEADLESS,  # Set headless option here
        }
        # Make sure to run headed.
        browser = await playwright.chromium.launch(**options)
        # Setup context however you like.
        context = await browser.new_context()  # Pass any options
        # Pause the page, and start recording manually.
        context = await set_init_script(context)
        page = await context.new_page()
        await page.goto("https://channels.weixin.qq.com")
        original_url = page.url

        # 监听页面的 'framenavigated' 事件，只关注主框架的变化
        page.on('framenavigated',
                lambda frame: asyncio.create_task(on_url_change()) if frame == page.main_frame else None)

        # 等待 iframe 出现（最多等 60 秒）
        iframe_locator = page.frame_locator("iframe").first

        # 获取 iframe 中的第一个 img 元素
        img_locator = iframe_locator.get_by_role("img").first

        # 获取二维码并发送到前端
        src = await _send_qrcode_from_locator(status_queue, img_locator, "shipinhao")
        print("✅ 图片地址:", src)

        try:
            # 等待 URL 变化或超时
            await asyncio.wait_for(url_changed_event.wait(), timeout=200)  # 最多等待 200 秒
            print("监听页面跳转成功")
        except asyncio.TimeoutError:
            status_queue.put("500")
            print("监听页面跳转超时")
            await page.close()
            await context.close()
            await browser.close()
            return None
        uuid_v1 = uuid.uuid1()
        print(f"UUID v1: {uuid_v1}")
        # 确保cookiesFile目录存在
        cookies_dir = Path(BASE_DIR / "cookiesFile")
        cookies_dir.mkdir(exist_ok=True)
        await context.storage_state(path=cookies_dir / f"{uuid_v1}.json")
        result = await check_cookie(2,f"{uuid_v1}.json")
        if not result:
            status_queue.put("500")
            await page.close()
            await context.close()
            await browser.close()
            return None
        await page.close()
        await context.close()
        await browser.close()

        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                                INSERT INTO user_info (type, filePath, userName, status)
                                VALUES (?, ?, ?, ?)
                                ''', (2, f"{uuid_v1}.json", id, 1))
            conn.commit()
            print("✅ 用户状态已记录")
        status_queue.put("200")

# 快手登录
async def get_ks_cookie(id,status_queue):
    url_changed_event = asyncio.Event()
    async def on_url_change():
        # 检查是否是主框架的变化
        if page.url != original_url:
            url_changed_event.set()
    async with async_playwright() as playwright:
        options = {
            'args': [
                '--lang en-GB'
            ],
            'headless': LOCAL_CHROME_HEADLESS,  # Set headless option here
        }
        # Make sure to run headed.
        browser = await playwright.chromium.launch(**options)
        # Setup context however you like.
        context = await browser.new_context()  # Pass any options
        context = await set_init_script(context)
        # Pause the page, and start recording manually.
        page = await context.new_page()
        await page.goto("https://cp.kuaishou.com")

        # 定位并点击“立即登录”按钮（类型为 link）
        await page.get_by_role("link", name="立即登录").click()
        await page.get_by_text("扫码登录").click()
        img_locator = page.get_by_role("img", name="qrcode")
        # 获取二维码并发送到前端
        src = await _send_qrcode_from_locator(status_queue, img_locator, "kuaishou")
        original_url = page.url
        print("✅ 图片地址:", src)
        # 监听页面的 'framenavigated' 事件，只关注主框架的变化
        page.on('framenavigated',
                lambda frame: asyncio.create_task(on_url_change()) if frame == page.main_frame else None)

        try:
            # 等待 URL 变化或超时
            await asyncio.wait_for(url_changed_event.wait(), timeout=200)  # 最多等待 200 秒
            print("监听页面跳转成功")
        except asyncio.TimeoutError:
            status_queue.put("500")
            print("监听页面跳转超时")
            await page.close()
            await context.close()
            await browser.close()
            return None
        uuid_v1 = uuid.uuid1()
        print(f"UUID v1: {uuid_v1}")
        # 确保cookiesFile目录存在
        cookies_dir = Path(BASE_DIR / "cookiesFile")
        cookies_dir.mkdir(exist_ok=True)
        await context.storage_state(path=cookies_dir / f"{uuid_v1}.json")
        result = await check_cookie(4, f"{uuid_v1}.json")
        if not result:
            status_queue.put("500")
            await page.close()
            await context.close()
            await browser.close()
            return None
        await page.close()
        await context.close()
        await browser.close()

        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                                        INSERT INTO user_info (type, filePath, userName, status)
                                        VALUES (?, ?, ?, ?)
                                        ''', (4, f"{uuid_v1}.json", id, 1))
            conn.commit()
            print("✅ 用户状态已记录")
        status_queue.put("200")

# 小红书登录
async def xiaohongshu_cookie_gen(id,status_queue):
    url_changed_event = asyncio.Event()

    async def on_url_change():
        # 检查是否是主框架的变化
        if page.url != original_url:
            url_changed_event.set()

    async with async_playwright() as playwright:
        options = {
            'args': [
                '--lang en-GB'
            ],
            'headless': LOCAL_CHROME_HEADLESS,  # Set headless option here
        }
        # Make sure to run headed.
        browser = await playwright.chromium.launch(**options)
        # Setup context however you like.
        context = await browser.new_context()  # Pass any options
        context = await set_init_script(context)
        # Pause the page, and start recording manually.
        page = await context.new_page()
        await page.goto("https://creator.xiaohongshu.com/")
        await page.locator('img.css-wemwzq').click()

        img_locator = page.get_by_role("img").nth(2)
        # 获取二维码并发送到前端
        src = await _send_qrcode_from_locator(status_queue, img_locator, "xiaohongshu")
        original_url = page.url
        print("✅ 图片地址:", src)
        # 监听页面的 'framenavigated' 事件，只关注主框架的变化
        page.on('framenavigated',
                lambda frame: asyncio.create_task(on_url_change()) if frame == page.main_frame else None)

        try:
            # 等待 URL 变化或超时
            await asyncio.wait_for(url_changed_event.wait(), timeout=200)  # 最多等待 200 秒
            print("监听页面跳转成功")
        except asyncio.TimeoutError:
            status_queue.put("500")
            print("监听页面跳转超时")
            await page.close()
            await context.close()
            await browser.close()
            return None
        uuid_v1 = uuid.uuid1()
        print(f"UUID v1: {uuid_v1}")
        # 确保cookiesFile目录存在
        cookies_dir = Path(BASE_DIR / "cookiesFile")
        cookies_dir.mkdir(exist_ok=True)
        await context.storage_state(path=cookies_dir / f"{uuid_v1}.json")
        result = await check_cookie(1, f"{uuid_v1}.json")
        if not result:
            status_queue.put("500")
            await page.close()
            await context.close()
            await browser.close()
            return None
        await page.close()
        await context.close()
        await browser.close()

        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                           INSERT INTO user_info (type, filePath, userName, status)
                           VALUES (?, ?, ?, ?)
                           ''', (1, f"{uuid_v1}.json", id, 1))
            conn.commit()
            print("✅ 用户状态已记录")
        status_queue.put("200")

async def bilibili_cookie_gen(id, status_queue):
    """
    Bilibili 登录适配版：
    通过前端二维码区域扫码登录，
    成功后自动存入数据库供后端使用。
    """
    async with async_playwright() as playwright:
        options = {
            'headless': LOCAL_CHROME_HEADLESS,
            'args': ['--start-maximized', '--disable-blink-features=AutomationControlled']
        }
        
        # 启动浏览器
        browser = await playwright.chromium.launch(**options)
        context = await browser.new_context(no_viewport=True)
        
        # 尝试注入防检测脚本 (如果你的 myUtils 里有这个函数就保留，没有就删掉这行)
        try:
            await set_init_script(context)
        except:
            pass

        page = await context.new_page()
        
        try:
            status_queue.put("正在打开 B站登录页...")
            # 1. 打开登录页
            await page.goto("https://passport.bilibili.com/login")
            
            # 2. 获取二维码并发送到前端
            src = await _send_qrcode_from_candidates(status_queue, page, [
                ".login-scan-box img",
                ".qrcode-img img",
                ".qr-code img",
                "img[src*='qrcode']",
                "img[src*='qr']",
                ".login-scan-box canvas",
                ".qrcode-img canvas",
                ".qr-code canvas",
                "canvas",
            ], "bilibili")
            print("✅ B站二维码已发送到前端:", src[:80] if src else src)
            status_queue.put(">>> 请在前端二维码区域扫码登录 <<<")
            print(">>> 请在浏览器中扫码登录...")

            # 3. 【保留你的原始逻辑】死循环等待 URL 变化
            # 只要 URL 里还有 "passport"，就说明还没登录成功/跳转
            end_time = asyncio.get_event_loop().time() + 300
            while "passport" in page.url:
                if asyncio.get_event_loop().time() >= end_time:
                    raise asyncio.TimeoutError("B站登录等待超时")
                await _handle_identity_verification(page, status_queue, "bilibili")
                await asyncio.sleep(1)
            
            status_queue.put("✅ 检测到跳转，登录成功！正在保存...")
            print(">>> 检测到跳转，等待 Cookie 写入...")

            # 4. 等待加载，确保 Cookie 写入
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)

            # 5. 生成文件名并保存 Cookie
            uuid_v1 = str(uuid.uuid1())
            cookies_dir = Path(BASE_DIR / "cookiesFile")
            if not cookies_dir.exists():
                cookies_dir.mkdir(parents=True, exist_ok=True)
            
            cookie_file_path = f"{uuid_v1}.json"
            save_path = cookies_dir / cookie_file_path
            
            await context.storage_state(path=save_path)
            print(f">>> Cookie 已保存至: {save_path}")

            # 6. 【关键】写入数据库 (这样前端列表才能显示出来)
            # type='5' 对应前端的 "哔哩哔哩"
            with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO user_info (type, filePath, userName, status) 
                    VALUES (?, ?, ?, ?)
                ''', ('5', cookie_file_path, id, 1))
                conn.commit()
                print("✅ 数据库写入完成")

            # 7. 通知前端完成
            status_queue.put("200")
            status_queue.put("✅ 账号已添加")

        except Exception as e:
            print(f"登录出错: {e}")
            status_queue.put(f"❌ 出错: {str(e)}")
        
        finally:
            # 关闭浏览器
            if browser:
                await browser.close()

# a = asyncio.run(xiaohongshu_cookie_gen(4,None))
# print(a)
