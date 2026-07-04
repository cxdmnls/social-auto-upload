# social-auto-upload

一个面向多平台短视频发布的 Web 工具。项目基于开源自动上传能力做二次开发，当前重点是把原本偏脚本化、偏本机浏览器操作的流程，整理成可以通过前端页面完成账号登录、视频上传、账号选择和发布的工作流。

## 当前状态

项目目前可以在本机运行后端服务，并通过根目录的 `index.html` 使用前端页面完成主要操作：

- 上传待发布的视频文件。
- 管理发布账号。
- 通过前端页面展示平台登录二维码。
- 用户扫码登录，后端保存 Cookie。
- 发布前统一校验 Cookie 是否有效。
- Cookie 有效时调用对应平台的 uploader 执行发布。
- Cookie 失效时跳过该账号，并返回“登录已过期，请重新扫码”的提示。

需要注意：项目还在向服务器部署形态适配中。本地开发时可以看到后端 Playwright 打开的浏览器窗口；部署到服务器后，通常无法直接看到或操作后端浏览器。因此登录流程不能长期依赖“人在服务器浏览器里操作”，而应尽量让用户在前端页面和手机端完成扫码、短信验证等步骤。

当前已经做的方向是：后端负责打开平台登录页并抓取二维码，前端通过 SSE 实时接收并显示二维码；如果平台要求身份验证，后端把提示发送给前端，由用户按提示在手机或平台页面完成操作。

## 支持平台

当前 Web 发布流程主要适配以下平台：

| 平台 | type |
| --- | --- |
| 小红书 | `1` / `xhs` / `xiaohongshu` |
| 视频号 | `2` / `shipinhao` / `tencent` / `channels` |
| 抖音 | `3` / `douyin` |
| 快手 | `4` / `kuaishou` / `ks` |
| Bilibili | `5` / `bilibili` / `bili` |

仓库里仍保留了部分原项目的 uploader 和 examples，例如百家号、TikTok 等示例脚本。这些可以作为后续扩展参考，但当前 Web 主流程请以上表为准。

## 项目结构

```text
.
├── sau_backend.py          # Flask 后端入口，提供前端页面所需 API
├── index.html              # 当前主要使用的单文件前端页面
├── myUtils/                # 登录、Cookie 校验、发布调度等封装
├── uploader/               # 各平台上传实现
├── db/                     # SQLite 初始化脚本，database.db 不提交
├── examples/               # 原项目示例脚本，可作为平台调用参考
├── media/                  # README 或项目展示资源
├── cookiesFile/            # 运行时 Cookie 文件目录，不提交
├── videoFile/              # 前端上传的视频文件目录，不提交
└── videos/                 # 本地测试视频目录，不提交
```

## 本地运行

建议使用 Python 3.10。

1. 克隆项目：

```bash
git clone https://github.com/cxdmnls/social-auto-upload.git
cd social-auto-upload
```

2. 创建并进入虚拟环境：

```bash
conda create -n social-auto-upload python=3.10
conda activate social-auto-upload
```

也可以使用 `venv`：

```bash
python -m venv .venv
.venv\Scripts\activate
```

3. 安装依赖：

```bash
pip install -r requirements.txt
playwright install chromium firefox
```

4. 初始化数据库：

```bash
cd db
python createTable.py
cd ..
```

5. 启动后端：

```bash
python sau_backend.py
```

后端默认监听：

```text
http://127.0.0.1:5409
```

6. 打开前端：

直接用浏览器打开根目录的 `index.html`。如果是本地文件方式打开，前端会默认请求：

```text
http://127.0.0.1:5409
```

## 使用流程

1. 启动后端 `python sau_backend.py`。
2. 打开 `index.html`。
3. 在“文件管理”里上传待发布的视频。
4. 在“账号管理”里新增或选择账号，点击登录。
5. 前端弹窗显示二维码后，用对应平台 App 扫码。
6. 如果平台要求短信验证或身份验证，按页面提示继续完成。
7. 登录成功后，后端保存 Cookie 到 `cookiesFile/`，并在数据库中记录账号信息。
8. 在“视频发布”里选择视频、账号、标题和标签。
9. 点击发布，后端会先校验 Cookie，再进入对应平台发布流程。

## Cookie 策略

用户通常只需要扫码一次。只要平台 Cookie 没有失效，后续发布会复用本地保存的 Cookie。

发布前后端会统一执行 Cookie 校验：

- Cookie 文件不存在：跳过该账号。
- Cookie 已失效：跳过该账号，并提示“登录已过期，请重新扫码”。
- Cookie 有效：继续调用对应平台 uploader。

这样可以避免某个账号登录失效时影响其他账号继续发布。

## 主要接口

| 接口 | 方法 | 说明 |
| --- | --- | --- |
| `/uploadSave` | POST | 上传视频或图片文件 |
| `/getFiles` | GET | 获取已上传文件列表 |
| `/deleteFile` | GET | 删除文件记录和本地文件 |
| `/getAccounts` | GET | 获取账号列表 |
| `/getValidAccounts` | GET | 获取账号列表，目前不额外启动浏览器校验 |
| `/login` | GET | SSE 登录流，向前端推送二维码和状态 |
| `/postVideo` | POST | 发布视频，发布前会校验 Cookie |
| `/uploadCookie` | POST | 手动上传 Cookie 文件 |
| `/downloadCookie` | GET | 下载 Cookie 文件 |

## 服务器部署说明

这个项目当前仍处于服务器部署适配阶段。

本机运行时，后端 Playwright 浏览器窗口可以被开发者看到，所以调试二维码、身份验证和页面元素定位比较方便。部署到服务器后，后端浏览器通常运行在无界面环境中，用户无法直接操作它。

因此服务器部署的核心问题不是简单地把 Flask 服务跑起来，而是要保证：

- 二维码能稳定从后端浏览器截图或提取后推送到前端。
- 前端能实时显示二维码。
- 平台出现短信验证、身份验证、人机验证时，前端能给用户明确提示。
- 用户操作完成后，后端能继续保存 Cookie。
- Cookie 失效后，用户可以重新扫码登录。

当前项目已经按这个方向进行改造，但不同平台登录页经常变化，服务器部署前需要逐个平台做真实验证。

## 不要提交到 GitHub 的文件

以下内容是本地运行数据、敏感信息或大文件，不应该上传到 GitHub：

```text
conf.py
cookies/
cookiesFile/
videoFile/
videos/
db/database.db
.venv/
node_modules/
__pycache__/
*.log
```

这些已经在 `.gitignore` 中配置。提交前建议执行：

```bash
git status --short
```

确认没有 Cookie、数据库、测试视频等文件出现在待提交列表里。

## examples 目录说明

`examples/` 目录来自原项目，里面是各平台获取 Cookie 和上传视频的示例脚本。它不是用户上传的视频目录，可以提交到 GitHub，用于后续开发时参考 uploader 的调用方式。

真正的视频素材目录是 `videos/` 和运行时上传目录 `videoFile/`，这两个目录不应该提交。

## 开发验证

修改后端代码后，可以先做静态语法检查：

```bash
python -m py_compile sau_backend.py myUtils/login.py myUtils/auth.py
```

本地功能验证建议按顺序测试：

1. 启动后端。
2. 打开 `index.html`。
3. 用“二维码显示测试”确认前端可以显示二维码。
4. 选择真实平台扫码登录。
5. 上传一个测试视频。
6. 选择已登录账号发布。
7. 删除或改名 Cookie 文件，再次发布，确认提示重新扫码。

## 免责声明

本项目仅用于学习、研究和个人内容管理自动化。使用时请遵守各平台规则，不要用于垃圾内容发布、批量骚扰、绕过平台风控或其他违规用途。平台页面和登录策略可能随时变化，相关自动化逻辑需要持续维护。
