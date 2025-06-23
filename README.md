# HTML 预览工具

一个简单而强大的HTML代码预览工具，支持CDN资源代理和即时预览。

## 🚀 功能特点

- **即时预览**: 粘贴HTML代码，立即生成可分享的预览链接
- **CDN代理**: 自动代理常见CDN资源，确保外部资源能够正常加载
- **安全隔离**: 每个预览都在独立的随机目录中，确保安全性
- **响应式设计**: 现代化的用户界面，支持移动端访问
- **一键分享**: 生成的链接可以轻松分享给他人

## 📋 系统要求

- Python 3.7+
- Flask 2.3.3
- 其他依赖见 `requirements.txt`

## 🛠️ 安装与运行

### 1. 克隆项目

```bash
git clone <项目地址>
cd Preview
```

### 2. 创建虚拟环境

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或
.venv\Scripts\activate     # Windows
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 运行应用

```bash
python main.py
```

应用将在 `http://localhost:5010` 启动。

## 🌐 环境变量配置

| 变量名 | 描述 | 默认值 |
|--------|------|--------|
| `PORT` | 应用运行端口 | 5010 |
| `HOST_URL` | 主机URL（用于生成预览链接） | http://127.0.0.1:5010 |

### 部署示例

```bash
export PORT=8080
export HOST_URL=https://your-domain.com
python main.py
```

## 📁 项目结构

```
Preview/
├── main.py              # 主应用文件
├── requirements.txt     # Python依赖
├── templates/
│   └── index.html      # 主页模板
├── static/             # 静态文件和生成的预览文件
│   ├── <random>/      # 用户生成的预览文件
│   └── ...
└── .venv/             # 虚拟环境
```

## 🔧 使用方法

1. 访问主页面
2. 在文本框中粘贴您的HTML代码
3. 点击"生成预览链接"按钮
4. 获得可分享的预览链接

### 支持的CDN资源

工具自动代理以下CDN域名的资源：

- `cdn.tailwindcss.com`
- `cdn.jsdelivr.net`
- `unpkg.com`
- `cdnjs.cloudflare.com`
- `fonts.googleapis.com`
- `fonts.gstatic.com`
- `ajax.googleapis.com`
- `code.jquery.com`
- `stackpath.bootstrapcdn.com`
- `maxcdn.bootstrapcdn.com`
- `use.fontawesome.com`

## 🤝 贡献

欢迎提交Issue和Pull Request来改进这个项目！

## 📄 许可证

本项目采用 MIT 许可证。 