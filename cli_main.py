import asyncio
import os
import sqlite3
import threading
import time
import uuid
import logging
from pathlib import Path
from queue import Queue

from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS

# ================= 1. 基础配置与日志 =================
# 配置日志输出，方便调试
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 尝试加载配置文件
try:
    from conf import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
    logger.warning(f"未找到 conf.py，使用默认路径: {BASE_DIR}")

# 尝试加载业务模块 (myUtils)
# 如果加载失败，将相关函数置为 None，防止启动报错
MODULES_LOADED = False
try:
    from myUtils.auth import check_cookie
    from myUtils.login import get_tencent_cookie, douyin_cookie_gen, get_ks_cookie, xiaohongshu_cookie_gen,bilibili_cookie_gen
    from myUtils.postVideo import post_video_tencent, post_video_DouYin, post_video_ks, post_video_xhs, post_video_bilibili
    MODULES_LOADED = True
    logger.info("✅ 业务模块 (myUtils) 加载成功")
except ImportError as e:
    logger.error(f"⚠️ 业务模块加载失败: {e}")
    logger.error("请确保 myUtils 文件夹在当前目录下，且安装了所有依赖。")
    # 定义空变量防止 NameError
    get_tencent_cookie = douyin_cookie_gen = get_ks_cookie = xiaohongshu_cookie_gen = None
    post_video_tencent = post_video_DouYin = post_video_ks = post_video_xhs = None

app = Flask(__name__)
# 允许所有跨域请求
CORS(app)
# 限制上传大小 160MB
app.config['MAX_CONTENT_LENGTH'] = 160 * 1024 * 1024
active_queues = {}

# 数据库连接辅助函数
def get_db_connection():
    db_path = BASE_DIR / "db" / "database.db"
    if not db_path.parent.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row # 让结果可以通过列名访问
    return conn

# ================= 2. 静态资源与首页 =================
@app.route('/')
def index():
    return "后端服务正常运行中。请直接打开 index.html 使用前端。"

@app.route('/assets/<path:filename>')
def custom_static(filename):
    return send_from_directory(os.path.join(os.path.dirname(__file__), 'assets'), filename)

# ================= 3. 文件管理模块 =================
@app.route('/uploadSave', methods=['POST'])
def upload_save():
    
    logger.info("收到文件上传请求")
    if 'file' not in request.files:
        return jsonify({"code": 400, "msg": "未找到文件"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"code": 400, "msg": "文件名为空"}), 400

    try:
        # 生成唯一文件名
        uuid_v1 = str(uuid.uuid1())
        save_filename = f"{uuid_v1}_{file.filename}"
        
        save_dir = BASE_DIR / "videoFile"
        if not save_dir.exists():
            save_dir.mkdir(parents=True, exist_ok=True)
        
        filepath = save_dir / save_filename
        file.save(str(filepath))
        logger.info(f"文件已保存: {filepath}")

        # 写入数据库
        file_size_mb = round(float(os.path.getsize(filepath)) / (1024 * 1024), 2)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # 建表防报错
            cursor.execute('''CREATE TABLE IF NOT EXISTS file_records 
                              (id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT, filesize REAL, file_path TEXT)''')
            cursor.execute('''INSERT INTO file_records (filename, filesize, file_path) 
                              VALUES (?, ?, ?)''', (file.filename, file_size_mb, save_filename))
            conn.commit()

        return jsonify({
            "code": 200, 
            "msg": "上传成功", 
            "data": {"filename": file.filename, "filepath": save_filename}
        })
    except Exception as e:
        logger.error(f"上传出错: {e}", exc_info=True)
        return jsonify({"code": 500, "msg": str(e)}), 500

@app.route('/getFiles', methods=['GET'])
def get_all_files():
    try:
        with get_db_connection() as conn:
            # 检查表是否存在
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='file_records'")
            if not cursor.fetchone():
                return jsonify({"code": 200, "data": []})

            cursor.execute("SELECT * FROM file_records ORDER BY id DESC")
            rows = cursor.fetchall()
            data = [dict(row) for row in rows]
            return jsonify({"code": 200, "data": data})
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500

@app.route('/deleteFile', methods=['GET'])
def delete_file():
    file_id = request.args.get('id')
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM file_records WHERE id = ?", (file_id,))
            record = cursor.fetchone()
            if record:
                file_path = BASE_DIR / "videoFile" / record['file_path']
                if file_path.exists():
                    try:
                        file_path.unlink() # 删除物理文件
                    except: pass
                cursor.execute("DELETE FROM file_records WHERE id = ?", (file_id,))
                conn.commit()
        return jsonify({"code": 200, "msg": "删除成功"}), 200
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500

# ================= 4. 账号管理模块 =================
@app.route("/getAccounts", methods=['GET'])
def getAccounts():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''CREATE TABLE IF NOT EXISTS user_info 
                              (id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT, userName TEXT, filePath TEXT, status INTEGER)''')
            cursor.execute('SELECT * FROM user_info')
            rows = cursor.fetchall()
            
            data_list = []
            for row in rows:
                item = dict(row)
                # 兼容前端字段: userName -> name
                if 'userName' in item and 'name' not in item:
                    item['name'] = item['userName']
                # 兼容下载字段: filePath -> cookie_path
                if 'filePath' in item:
                    item['cookie_path'] = item['filePath']
                data_list.append(item)
            return jsonify({"code": 200, "data": data_list})
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500

@app.route('/updateUserinfo', methods=['POST'])
def updateUserinfo():
    data = request.get_json()
    user_id = data.get('id')
    type_ = data.get('type')
    # 兼容前端传 name，后端存 userName
    name = data.get('name') or data.get('userName')
    
    try:
        with get_db_connection() as conn:
            conn.execute('UPDATE user_info SET type=?, userName=? WHERE id=?', (type_, name, user_id))
            conn.commit()
        return jsonify({"code": 200, "msg": "更新成功"}), 200
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500

@app.route('/deleteAccount', methods=['GET'])
def delete_account():
    id_ = request.args.get('id')
    with get_db_connection() as conn:
        conn.execute("DELETE FROM user_info WHERE id=?", (id_,))
        conn.commit()
    return jsonify({"code": 200, "msg": "删除成功"}), 200

# ================= 5. SSE 实时登录模块 =================
def run_async_login(type_, id_, status_queue):
    """后台线程：执行登录逻辑"""
    if not MODULES_LOADED:
        status_queue.put("❌ 错误: myUtils 模块未加载，无法执行登录")
        return

    try:
        func = None
        # 平台类型映射
        t_str = str(type_).lower()
        if t_str in ['xiaohongshu', 'xhs', '1']:
            func = xiaohongshu_cookie_gen
        elif t_str in ['shipinhao', '2']:
            func = get_tencent_cookie
        elif t_str in ['douyin', '3']:
            func = douyin_cookie_gen
        elif t_str in ['kuaishou', 'ks', '4']:
            func = get_ks_cookie
        elif t_str in ['bilibili','5']:
            func=bilibili_cookie_gen
        
        if not func:
            status_queue.put(f"❌ 错误: 未知的平台类型 {type_}")
            return

        status_queue.put(f"🚀 开始执行 {type_} (ID:{id_}) 登录...")
        
        # 创建新的事件循环运行异步代码
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(func(id_, status_queue))
        loop.close()
        
        status_queue.put("✅ 流程结束")

    except Exception as e:
        logger.error(f"SSE Error: {e}", exc_info=True)
        status_queue.put(f"❌ 发生异常: {str(e)}")

def sse_stream(status_queue):
    """SSE 数据流生成器"""
    yield f"data: 连接成功\n\n"
    while True:
        if not status_queue.empty():
            msg = status_queue.get()
            yield f"data: {msg}\n\n"
            # 简单判断结束条件
            if any(k in str(msg) for k in ["结束", "成功", "失败", "Error", "Failed"]):
                time.sleep(1) # 等待前端接收
                break
        else:
            time.sleep(0.1)

@app.route('/login')
def login():
    type_ = request.args.get('type')
    id_ = request.args.get('id')
    logger.info(f"收到 SSE 登录请求: Type={type_}, ID={id_}")

    status_queue = Queue()
    thread = threading.Thread(target=run_async_login, args=(type_, id_, status_queue), daemon=True)
    thread.start()

    return Response(
        sse_stream(status_queue),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*'
        }
    )

# ================= 6. 视频发布模块 (修复 Path/dict 报错) =================
@app.route('/postVideo', methods=['POST'])
def postVideo():
    """
    接收前端参数 -> 查数据库获取真实路径/账号 -> 调用 myUtils 发布
    """
    if not MODULES_LOADED:
        return jsonify({"code": 500, "msg": "后端 myUtils 模块未加载，无法发布"}), 500

    data = request.get_json()
    logger.info(f"收到发布请求数据: {data}")
    file_id = data.get('file_id')
    account_ids = data.get('account_ids', [])
    title = data.get('title', '')
    tags = data.get('tags', '')

    if not file_id or not account_ids:
        return jsonify({"code": 400, "msg": "缺少文件或账号信息"}), 400

    real_file_path = None
    real_account_list = []

    # 1. 查数据库
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 获取文件路径
            cursor.execute("SELECT file_path FROM file_records WHERE id = ?", (file_id,))
            file_row = cursor.fetchone()
            if file_row:
                real_file_path = str(BASE_DIR / "videoFile" / file_row['file_path'])
            
            # 获取账号列表
            if account_ids:
                placeholders = ','.join('?' * len(account_ids))
                query = f"SELECT * FROM user_info WHERE id IN ({placeholders})"
                cursor.execute(query, account_ids)
                account_rows = cursor.fetchall()
                for row in account_rows:
                    real_account_list.append(dict(row))
    except Exception as e:
        logger.error(f"数据库查询失败: {e}")
        return jsonify({"code": 500, "msg": f"数据库错误: {str(e)}"}), 500

    # 2. 校验文件
    if not real_file_path or not os.path.exists(real_file_path):
        return jsonify({"code": 404, "msg": f"文件不存在或已丢失: {real_file_path}"}), 404

    # 3. 执行发布 (按平台分发)
    results = []
    file_list = [real_file_path] # 包装成列表
    
    # 默认参数
    default_category = None
    default_enableTimer = False
    default_vpday = 1
    default_daily = []
    default_start = []
    
    for account in real_account_list:
        platform = str(account.get('type', '')).lower()
        acc_name = account.get('userName', '未知用户')
        
        # 【核心修复】提取 Cookie 文件名 (字符串)，而不是传整个字典
        # 优先取 filePath，如果没有则取 userName
        cookie_identifier = account.get('filePath') or account.get('cookie_path') or acc_name
        
        # 将字符串放入列表传给 myUtils
        acc_list = [cookie_identifier] 

        logger.info(f"正在调度任务: 账号={acc_name}, 标识={cookie_identifier}, 平台={platform}")
        
        try:
            # --- 抖音 ---
            if platform in ['douyin', '3']:
                if post_video_DouYin:
                    post_video_DouYin(title, file_list, tags, acc_list, default_category, 
                                      default_enableTimer, default_vpday, default_daily, default_start, 
                                      "", "", "") 
                    results.append(f"抖音({acc_name}): ✅ 提交成功")
                else:
                    results.append(f"抖音({acc_name}): ❌ 模块缺失")

            # --- 小红书 ---
            elif platform in ['xhs', 'xiaohongshu', '1']:
                if post_video_xhs:
                    post_video_xhs(title, file_list, tags, acc_list, default_category, 
                                   default_enableTimer, default_vpday, default_daily, default_start)
                    results.append(f"小红书({acc_name}): ✅ 提交成功")
                else:
                    results.append(f"小红书({acc_name}): ❌ 模块缺失")

            # --- 视频号 ---
            elif platform in ['shipinhao', '2']:
                if post_video_tencent:
                    post_video_tencent(title, file_list, tags, acc_list, default_category, 
                                       default_enableTimer, default_vpday, default_daily, default_start, False)
                    results.append(f"视频号({acc_name}): ✅ 提交成功")
                else:
                    results.append(f"视频号({acc_name}): ❌ 模块缺失")

            # --- 快手 ---
            elif platform in ['kuaishou', 'ks', '4']:
                if post_video_ks:
                    post_video_ks(title, file_list, tags, acc_list, default_category, 
                                  default_enableTimer, default_vpday, default_daily, default_start)
                    results.append(f"快手({acc_name}): ✅ 提交成功")
                else:
                    results.append(f"快手({acc_name}): ❌ 模块缺失")

            # --- bilibili ---
            elif platform in ['bilibili', 'ks', '5']:
                if post_video_bilibili:
                    post_video_bilibili(title, file_list, tags, acc_list, default_category, 
                                  default_enableTimer, default_vpday, default_daily, default_start)
                    results.append(f"bilibili({acc_name}): ✅ 提交成功")
                else:
                    results.append(f"bilibili({acc_name}): ❌ 模块缺失")
            
            else:
                results.append(f"未知平台({acc_name}): {platform}")

        except Exception as e:
            logger.error(f"发布任务异常: {e}", exc_info=True)
            results.append(f"❌ {acc_name} 发布失败: {str(e)}")

    return jsonify({
        "code": 200, 
        "msg": "所有任务处理完成", 
        "data": results
    })

# ================= 7. Cookie 上传/下载 =================
@app.route('/uploadCookie', methods=['POST'])
def upload_cookie():
    if 'file' not in request.files:
        return jsonify({"code": 400, "msg": "No file"}), 400
    file = request.files['file']
    try:
        save_dir = BASE_DIR / "cookiesFile"
        if not save_dir.exists(): save_dir.mkdir(parents=True)
        file.save(save_dir / file.filename)
        return jsonify({"code": 200, "msg": "Cookie已保存"}), 200
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500

@app.route('/downloadCookie', methods=['GET'])
def download_cookie():
    file_path = request.args.get('filePath')
    if not file_path or '..' in file_path:
        return jsonify({"code": 400, "msg": "Invalid path"}), 400
    return send_from_directory(BASE_DIR / "cookiesFile", file_path, as_attachment=True)

# ================= 启动入口 =================
if __name__ == '__main__':
    # 初始化目录
    (BASE_DIR / "videoFile").mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "db").mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "cookiesFile").mkdir(parents=True, exist_ok=True)

    print(f"🚀 后端服务已启动: http://127.0.0.1:5409")
    print(f"📄 请确保前端 index.html 中的端口也是 5409")
    
    # 强制使用 5409 端口
    app.run(host='0.0.0.0', port=5409, debug=True)