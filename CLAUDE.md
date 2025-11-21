# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个基于 Flask 的 HTML 预览工具，允许用户粘贴 HTML 代码并生成可分享的预览链接。主要特性包括：
- CDN 资源自动代理（支持常见 CDN 如 Tailwind、jsdelivr、unpkg 等）
- 项目元数据自动提取（标题、描述）
- 缩略图自动生成（使用 html2canvas）
- 所有预览项目独立存储在随机生成的目录中

## 开发环境设置

### 启动开发服务器
```bash
# 安装依赖（推荐使用虚拟环境）
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
pip install -r requirements.txt

# 运行应用（默认端口 5010）
python main.py

# 使用自定义端口和主机 URL
export PORT=8080
export HOST_URL=https://your-domain.com
python main.py
```

### Docker 部署
```bash
# 构建镜像
docker build -t html-preview-tool .

# 运行容器
docker run -p 5010:5010 -v $(pwd)/static:/app/static html-preview-tool

# 使用环境变量
docker run -p 8080:8080 -e PORT=8080 -e HOST_URL=https://your-domain.com html-preview-tool
```

## 项目架构

### 核心文件结构
- `main.py`: Flask 应用主文件，包含所有路由和核心逻辑
- `templates/index.html`: 前端单页应用，包含所有 UI 和 JavaScript 逻辑
- `static/`: 存储用户生成的预览项目，每个项目在独立的随机目录中
  - `static/<random-id>/index.html`: 用户上传的 HTML 文件
  - `static/<random-id>/metadata.json`: 项目元数据（标题、描述、创建时间）
  - `static/<random-id>/thumbnail.png`: 自动生成的缩略图

### 关键功能模块

#### CDN 代理机制 (main.py:47-66, 242-288)
- `replace_cdn_links()`: 将 HTML 中的 CDN 链接替换为 `/proxy?url=<encoded_url>` 代理链接
- `/proxy` 路由: 验证域名白名单后转发请求，添加 CORS 和缓存头
- 支持的 CDN 列表定义在 `CDN_DOMAINS` (main.py:22-34)

#### 元数据提取 (main.py:76-158)
- `extract_html_metadata()`: 使用 BeautifulSoup 提取 HTML 标题和描述
- 优先级: `<title>` > `<h1>` > "未命名项目"
- 描述优先级: `<meta name="description">` > 第一个 `<p>` 标签

#### 缩略图生成流程 (templates/index.html:641-871)
1. 前端首先检查是否已有缩略图 (img.onload/onerror)
2. 若无缩略图，创建隐藏 iframe 加载项目页面
3. 等待 10 秒让页面完全加载（显示倒计时）
4. 使用 html2canvas 截图（智能检测内容边界）
5. 将 base64 图片数据上传到服务器 `/api/projects/<id>/upload-thumbnail`
6. 服务器保存为 thumbnail.png

#### API 端点
- `POST /upload`: 上传 HTML 内容，返回预览链接和项目 ID
- `GET /api/projects`: 获取所有已部署项目列表
- `POST /api/projects/<id>/upload-thumbnail`: 上传项目缩略图
- `GET /proxy`: CDN 资源代理
- `GET /static/<path>`: 静态文件服务

## 开发注意事项

### 环境变量
- `PORT`: 应用运行端口（默认 5010）
- `HOST_URL`: 生成预览链接的主机 URL（默认 http://127.0.0.1:5010）

### 关键依赖
- Flask 2.3.3: Web 框架
- BeautifulSoup4 4.12.2: HTML 解析
- requests 2.31.0: HTTP 请求代理
- bleach 6.0.0: HTML 清理（目前未启用）

### 缩略图生成优化
- 使用智能内容边界检测 (getContentBounds) 避免大量空白
- 输出格式为 JPEG (0.85 质量) 以减小文件大小
- 生成 400px 宽缩略图，保持 4:3 比例
- 降级策略: 若截图失败，保留 iframe 实时预览

### 安全考虑
- HTML 清理功能预留但未实现 (main.py:68-74)
- CDN 代理仅允许白名单域名
- 用户上传内容隔离在独立目录中
- Docker 容器使用非 root 用户运行

## 常见任务

### 添加新的 CDN 域名支持
在 `main.py` 的 `CDN_DOMAINS` 列表中添加域名

### 修改缩略图生成时间
调整 `templates/index.html` 中 `startIframeThumbnailGeneration()` 的倒计时时长（默认 10 秒）

### 调整截图质量和尺寸
修改 `templates/index.html:818-819` 中的 `toDataURL()` 参数和画布缩放比例
