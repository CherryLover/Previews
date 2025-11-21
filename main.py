import os
import secrets
import re
import requests
import json
import datetime
import base64
import logging
import time
import shutil
import hashlib
from collections import OrderedDict
from flask import Flask, request, render_template, jsonify, send_from_directory, Response, make_response
from bs4 import BeautifulSoup
import bleach
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect, generate_csrf
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__, static_folder=None)  # 禁用默认静态文件夹,使用自定义路由

# 配置密钥（用于CSRF保护）
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or secrets.token_hex(32)

# 配置日志记录
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 初始化CSRF保护
csrf = CSRFProtect(app)

# 配置速率限制
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# 配置
UPLOAD_FOLDER = 'static'
DEFAULT_PORT = 5010
MAX_CONTENT_LENGTH = 1 * 1024 * 1024  # 1MB
MAX_PROXY_SIZE = 10 * 1024 * 1024  # 10MB
MAX_STORAGE_QUOTA = 500 * 1024 * 1024  # 500MB 总存储配额
PROJECT_EXPIRY_DAYS = int(os.environ.get('PROJECT_EXPIRY_DAYS', 30))  # 项目过期天数，默认30天
CLEANUP_INTERVAL_HOURS = int(os.environ.get('CLEANUP_INTERVAL_HOURS', 24))  # 清理任务间隔，默认24小时
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

port = os.environ.get('PORT', DEFAULT_PORT)

# 项目列表缓存配置
PROJECTS_CACHE = {
    'data': None,  # 缓存的项目列表
    'timestamp': 0,  # 缓存时间戳
    'ttl': 300  # 缓存有效期(秒),默认5分钟
}

# CDN 缓存配置
CDN_CACHE_DIR = os.path.join(UPLOAD_FOLDER, 'cdn_cache')
CDN_CACHE_TTL = int(os.environ.get('CDN_CACHE_TTL', 7 * 24 * 3600))  # 默认7天
CDN_CACHE_MAX_MEMORY_ITEMS = int(os.environ.get('CDN_CACHE_MAX_MEMORY_ITEMS', 100))  # 内存缓存最大条目数

# 内存缓存 - 使用 OrderedDict 实现简单的 LRU
cdn_memory_cache = OrderedDict()

# 常见CDN域名列表
CDN_DOMAINS = [
    'cdn.tailwindcss.com',
    'cdn.jsdelivr.net',
    'unpkg.com',
    'cdnjs.cloudflare.com',
    'fonts.googleapis.com',
    'fonts.gstatic.com',
    'ajax.googleapis.com',
    'code.jquery.com',
    'stackpath.bootstrapcdn.com',
    'maxcdn.bootstrapcdn.com',
    'use.fontawesome.com'
]

def get_host_url():
    """获取主机URL，从环境变量读取，如果没有则使用默认值"""
    host_url = os.environ.get('HOST_URL', f'http://127.0.0.1:{port}')
    if not host_url.startswith(('http://', 'https://')):
        host_url = 'https://' + host_url
    return host_url

def generate_random_string(length=8):
    """生成随机字符串作为目录名"""
    return secrets.token_urlsafe(length)[:length]

def get_url_hash(url):
    """
    生成 URL 的哈希值作为缓存文件名
    使用 SHA256 保证唯一性和安全性
    """
    return hashlib.sha256(url.encode('utf-8')).hexdigest()

def get_cdn_cache_path(url_hash, content_type):
    """
    获取 CDN 缓存文件路径
    根据 Content-Type 确定文件扩展名
    """
    # 根据 Content-Type 确定扩展名
    ext_map = {
        'text/css': '.css',
        'text/javascript': '.js',
        'application/javascript': '.js',
        'image/png': '.png',
        'image/jpeg': '.jpg',
        'image/svg+xml': '.svg',
        'image/webp': '.webp',
        'font/woff': '.woff',
        'font/woff2': '.woff2',
        'font/ttf': '.ttf',
        'font/otf': '.otf',
    }

    ext = ext_map.get(content_type, '.bin')
    return os.path.join(CDN_CACHE_DIR, f"{url_hash}{ext}")

def get_cdn_from_memory_cache(url_hash):
    """
    从内存缓存中获取 CDN 资源
    返回 (content, content_type, timestamp) 或 None
    """
    if url_hash in cdn_memory_cache:
        # LRU: 移动到末尾表示最近使用
        cdn_memory_cache.move_to_end(url_hash)
        return cdn_memory_cache[url_hash]
    return None

def set_cdn_to_memory_cache(url_hash, content, content_type):
    """
    将 CDN 资源存储到内存缓存
    使用 LRU 策略，超过最大条目数时删除最旧的
    """
    if url_hash in cdn_memory_cache:
        cdn_memory_cache.move_to_end(url_hash)
    else:
        cdn_memory_cache[url_hash] = (content, content_type, time.time())
        # LRU: 如果超过最大条目数，删除最旧的（第一个）
        if len(cdn_memory_cache) > CDN_CACHE_MAX_MEMORY_ITEMS:
            cdn_memory_cache.popitem(last=False)

def get_cdn_from_file_cache(url_hash, content_type):
    """
    从文件系统缓存中获取 CDN 资源
    返回 (content, content_type) 或 None
    """
    try:
        cache_path = get_cdn_cache_path(url_hash, content_type)

        if not os.path.exists(cache_path):
            return None

        # 检查缓存是否过期
        file_mtime = os.path.getmtime(cache_path)
        if time.time() - file_mtime > CDN_CACHE_TTL:
            # 缓存已过期，删除文件
            os.remove(cache_path)
            logger.info(f"CDN 缓存已过期并删除: {cache_path}")
            return None

        # 读取缓存文件
        with open(cache_path, 'rb') as f:
            content = f.read()

        return (content, content_type)

    except Exception as e:
        logger.error(f"读取 CDN 文件缓存失败: {e}")
        return None

def set_cdn_to_file_cache(url_hash, content, content_type):
    """
    将 CDN 资源存储到文件系统缓存
    """
    try:
        # 确保缓存目录存在
        os.makedirs(CDN_CACHE_DIR, exist_ok=True)

        cache_path = get_cdn_cache_path(url_hash, content_type)

        # 写入缓存文件
        with open(cache_path, 'wb') as f:
            f.write(content)

        logger.info(f"CDN 资源已缓存到文件: {cache_path} ({len(content)} bytes)")
        return True

    except Exception as e:
        logger.error(f"写入 CDN 文件缓存失败: {e}")
        return False

def get_directory_size(path):
    """
    计算目录的总大小（包括所有子文件和子目录）
    返回字节数
    """
    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                # 跳过符号链接
                if not os.path.islink(file_path):
                    total_size += os.path.getsize(file_path)
    except Exception as e:
        logger.error(f"计算目录大小失败: {e}")
    return total_size

def check_storage_quota():
    """
    检查当前存储使用情况是否超过配额
    返回 (is_within_quota, current_size, quota)
    """
    try:
        static_dir = app.config['UPLOAD_FOLDER']
        if not os.path.exists(static_dir):
            return True, 0, MAX_STORAGE_QUOTA

        current_size = get_directory_size(static_dir)
        is_within_quota = current_size < MAX_STORAGE_QUOTA
        return is_within_quota, current_size, MAX_STORAGE_QUOTA
    except Exception as e:
        logger.error(f"检查存储配额失败: {e}")
        # 出错时保守策略：允许上传
        return True, 0, MAX_STORAGE_QUOTA

def replace_cdn_links(html_content):
    """
    替换HTML中的CDN链接为代理链接
    """
    host_url = get_host_url()
    
    # 匹配CDN链接的正则表达式
    cdn_pattern = r'(https?://(?:' + '|'.join(re.escape(domain) for domain in CDN_DOMAINS) + r')[^\s"\'<>]*)'
    
    def replace_url(match):
        original_url = match.group(1)
        # 将URL编码后作为代理参数
        import urllib.parse
        encoded_url = urllib.parse.quote(original_url, safe='')
        proxy_url = f"{host_url}/proxy?url={encoded_url}"
        return proxy_url
    
    # 替换HTML中的CDN链接
    modified_html = re.sub(cdn_pattern, replace_url, html_content)
    return modified_html

def sanitize_html(html_content):
    """
    HTML内容清理函数
    使用bleach库进行安全清理,防止XSS攻击
    """
    # 允许的HTML标签列表(包含常用的HTML5标签)
    allowed_tags = [
        'a', 'abbr', 'acronym', 'address', 'article', 'aside', 'audio',
        'b', 'blockquote', 'body', 'br', 'button',
        'canvas', 'caption', 'cite', 'code', 'col', 'colgroup',
        'data', 'dd', 'del', 'details', 'dfn', 'div', 'dl', 'dt',
        'em',
        'figcaption', 'figure', 'footer', 'form',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'head', 'header', 'hr', 'html',
        'i', 'iframe', 'img', 'input', 'ins',
        'kbd',
        'label', 'legend', 'li', 'link',
        'main', 'map', 'mark', 'meta',
        'nav',
        'ol', 'optgroup', 'option', 'output',
        'p', 'pre', 'progress',
        'q',
        's', 'samp', 'section', 'select', 'small', 'source', 'span', 'strong', 'style', 'sub', 'summary', 'sup', 'svg',
        'table', 'tbody', 'td', 'textarea', 'tfoot', 'th', 'thead', 'time', 'title', 'tr', 'track',
        'u', 'ul',
        'var', 'video',
        'wbr',
        # SVG相关标签
        'circle', 'ellipse', 'line', 'path', 'polygon', 'polyline', 'rect', 'g', 'defs', 'clipPath', 'text', 'tspan',
    ]

    # 允许的属性(使用字典形式,可以为每个标签指定允许的属性)
    allowed_attributes = {
        '*': ['class', 'id', 'style', 'title', 'lang', 'dir', 'data-*', 'aria-*', 'role'],
        'a': ['href', 'target', 'rel', 'name'],
        'img': ['src', 'alt', 'width', 'height', 'loading', 'srcset', 'sizes'],
        'video': ['src', 'controls', 'autoplay', 'loop', 'muted', 'poster', 'width', 'height'],
        'audio': ['src', 'controls', 'autoplay', 'loop', 'muted'],
        'source': ['src', 'type', 'media'],
        'iframe': ['src', 'width', 'height', 'frameborder', 'allowfullscreen', 'allow', 'sandbox'],
        'link': ['href', 'rel', 'type', 'media'],
        'meta': ['charset', 'name', 'content', 'http-equiv'],
        'form': ['action', 'method', 'enctype', 'target'],
        'input': ['type', 'name', 'value', 'placeholder', 'required', 'disabled', 'readonly', 'checked', 'maxlength', 'min', 'max', 'step', 'pattern'],
        'button': ['type', 'name', 'value', 'disabled'],
        'textarea': ['name', 'rows', 'cols', 'placeholder', 'required', 'disabled', 'readonly', 'maxlength'],
        'select': ['name', 'required', 'disabled', 'multiple', 'size'],
        'option': ['value', 'selected', 'disabled'],
        'table': ['border', 'cellpadding', 'cellspacing'],
        'td': ['colspan', 'rowspan'],
        'th': ['colspan', 'rowspan', 'scope'],
        'canvas': ['width', 'height'],
        'svg': ['width', 'height', 'viewBox', 'xmlns', 'fill', 'stroke', 'stroke-width'],
        'path': ['d', 'fill', 'stroke', 'stroke-width'],
        'circle': ['cx', 'cy', 'r', 'fill', 'stroke', 'stroke-width'],
        'rect': ['x', 'y', 'width', 'height', 'fill', 'stroke', 'stroke-width'],
        'script': ['src', 'type'],
    }

    # 允许的协议
    allowed_protocols = ['http', 'https', 'mailto', 'tel', 'data']

    # 使用bleach清理HTML
    # strip=False: 不移除不允许的标签,而是转义它们
    # css_sanitizer=None: 允许所有CSS样式(如需限制CSS,可使用bleach.css_sanitizer.CSSSanitizer)
    cleaned_html = bleach.clean(
        html_content,
        tags=allowed_tags,
        attributes=allowed_attributes,
        protocols=allowed_protocols,
        strip=False,
        strip_comments=False,
        css_sanitizer=None
    )

    return cleaned_html

def extract_html_metadata(html_content):
    """
    从HTML内容中提取元数据（标题、描述等）
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')

        # 提取标题
        title = None
        if soup.title:
            title = soup.title.string.strip()
        elif soup.find('h1'):
            title = soup.find('h1').get_text().strip()

        # 提取描述
        description = None
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc:
            description = meta_desc.get('content', '').strip()
        elif soup.find('p'):
            # 取第一个段落作为描述，限制长度
            first_p = soup.find('p').get_text().strip()
            description = first_p[:100] + '...' if len(first_p) > 100 else first_p

        return {
            'title': title or '未命名项目',
            'description': description or '暂无描述'
        }
    except Exception as e:
        return {
            'title': '未命名项目',
            'description': '暂无描述'
        }

def save_project_metadata(project_id, metadata):
    """
    保存项目元数据到JSON文件
    """
    try:
        metadata_file = os.path.join(app.config['UPLOAD_FOLDER'], project_id, 'metadata.json')
        metadata['created_at'] = datetime.datetime.now().isoformat()
        metadata['id'] = project_id

        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"保存元数据失败: {e}")
        return False

def load_project_metadata(project_id):
    """
    加载项目元数据
    """
    try:
        metadata_file = os.path.join(app.config['UPLOAD_FOLDER'], project_id, 'metadata.json')
        if os.path.exists(metadata_file):
            with open(metadata_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"加载元数据失败: {e}")

    # 如果没有元数据文件，尝试从HTML中提取
    try:
        html_file = os.path.join(app.config['UPLOAD_FOLDER'], project_id, 'index.html')
        if os.path.exists(html_file):
            with open(html_file, 'r', encoding='utf-8') as f:
                html_content = f.read()
            metadata = extract_html_metadata(html_content)
            metadata['id'] = project_id
            metadata['created_at'] = datetime.datetime.fromtimestamp(
                os.path.getctime(html_file)
            ).isoformat()
            return metadata
    except Exception as e:
        logger.error(f"从HTML提取元数据失败: {e}")

    return {
        'id': project_id,
        'title': '未命名项目',
        'description': '暂无描述',
        'created_at': datetime.datetime.now().isoformat()
    }

def save_thumbnail_from_base64(project_id, base64_data):
    """
    从base64数据保存缩略图
    """
    try:
        # 移除data:image/png;base64,前缀
        if base64_data.startswith('data:image/'):
            base64_data = base64_data.split(',')[1]

        # 解码base64数据
        image_data = base64.b64decode(base64_data)

        # 保存到文件
        thumbnail_path = os.path.join(app.config['UPLOAD_FOLDER'], project_id, 'thumbnail.png')
        with open(thumbnail_path, 'wb') as f:
            f.write(image_data)

        return True
    except Exception as e:
        logger.error(f"保存缩略图失败: {e}")
        return False

def has_thumbnail(project_id):
    """
    检查项目是否有缩略图
    """
    thumbnail_path = os.path.join(app.config['UPLOAD_FOLDER'], project_id, 'thumbnail.png')
    return os.path.exists(thumbnail_path) and os.path.getsize(thumbnail_path) > 0

def invalidate_projects_cache():
    """
    使项目列表缓存失效
    在以下情况调用:上传项目、删除项目、清理过期项目、上传缩略图
    """
    PROJECTS_CACHE['data'] = None
    PROJECTS_CACHE['timestamp'] = 0
    logger.info("项目列表缓存已失效")

def get_all_projects():
    """
    获取所有已部署的项目列表
    使用缓存机制减少文件系统遍历开销
    """
    # 检查缓存是否有效
    current_time = time.time()
    cache_age = current_time - PROJECTS_CACHE['timestamp']

    if PROJECTS_CACHE['data'] is not None and cache_age < PROJECTS_CACHE['ttl']:
        logger.debug(f"使用缓存的项目列表 (缓存年龄: {cache_age:.1f}秒)")
        return PROJECTS_CACHE['data']

    # 缓存无效或过期，重新获取项目列表
    logger.info("重新获取项目列表并更新缓存")
    projects = []
    try:
        static_dir = app.config['UPLOAD_FOLDER']
        if not os.path.exists(static_dir):
            return projects

        for item in os.listdir(static_dir):
            item_path = os.path.join(static_dir, item)
            if os.path.isdir(item_path):
                index_file = os.path.join(item_path, 'index.html')
                if os.path.exists(index_file):
                    # 加载项目元数据
                    metadata = load_project_metadata(item)

                    # 获取文件信息
                    file_stat = os.stat(index_file)
                    file_size = file_stat.st_size

                    # 生成访问URL
                    host_url = get_host_url()
                    access_url = f"{host_url}/static/{item}/index.html"

                    # 生成预览图URL
                    thumbnail_url = f"{host_url}/static/{item}/thumbnail.png"

                    project_info = {
                        'id': item,
                        'title': metadata.get('title', '未命名项目'),
                        'description': metadata.get('description', '暂无描述'),
                        'url': access_url,
                        'thumbnail': thumbnail_url,
                        'created_at': metadata.get('created_at'),
                        'file_size': f"{file_size / 1024:.1f}KB" if file_size < 1024*1024 else f"{file_size / (1024*1024):.1f}MB"
                    }
                    projects.append(project_info)

        # 按创建时间倒序排列
        projects.sort(key=lambda x: x['created_at'], reverse=True)

        # 更新缓存
        PROJECTS_CACHE['data'] = projects
        PROJECTS_CACHE['timestamp'] = time.time()
        logger.info(f"项目列表已缓存 (共 {len(projects)} 个项目)")

    except Exception as e:
        logger.error(f"获取项目列表失败: {e}")

    return projects

@app.route('/')
def index():
    """主页面 - 显示HTML输入表单"""
    return render_template('index.html')

@app.route('/api/csrf-token', methods=['GET'])
@csrf.exempt  # 获取token的端点需要豁免CSRF检查
def get_csrf_token():
    """获取CSRF令牌"""
    token = generate_csrf()
    return jsonify({'csrf_token': token})

@app.route('/proxy')
@limiter.limit("100 per hour")  # CDN 代理速率限制
@csrf.exempt  # GET请求且用于资源代理,可以豁免CSRF
def proxy_resource():
    """代理外部CDN资源（带两层缓存：内存 + 文件系统）"""
    import urllib.parse

    # 获取要代理的URL
    target_url = request.args.get('url')
    if not target_url:
        return jsonify({'error': '缺少URL参数'}), 400

    try:
        # URL解码
        decoded_url = urllib.parse.unquote(target_url)

        # 验证URL是否为允许的CDN域名
        allowed = False
        for domain in CDN_DOMAINS:
            if domain in decoded_url:
                allowed = True
                break

        if not allowed:
            return jsonify({'error': '不允许的域名'}), 403

        # 生成 URL 哈希
        url_hash = get_url_hash(decoded_url)

        # 1. 尝试从内存缓存获取
        memory_cached = get_cdn_from_memory_cache(url_hash)
        if memory_cached:
            content, content_type, _ = memory_cached
            logger.info(f"CDN 缓存命中（内存）: {decoded_url}")
            return Response(
                content,
                headers={
                    'Content-Type': content_type,
                    'Cache-Control': 'public, max-age=86400',  # 客户端缓存1天
                    'Access-Control-Allow-Origin': '*',
                    'X-Cache-Status': 'HIT-MEMORY',
                }
            )

        # 2. 请求外部资源获取 content_type
        response = requests.get(decoded_url, timeout=10, stream=True)
        response.raise_for_status()

        content_type = response.headers.get('Content-Type', 'text/plain')

        # 3. 尝试从文件缓存获取
        file_cached = get_cdn_from_file_cache(url_hash, content_type)
        if file_cached:
            content, _ = file_cached
            logger.info(f"CDN 缓存命中（文件）: {decoded_url}")
            # 同时写入内存缓存
            set_cdn_to_memory_cache(url_hash, content, content_type)
            return Response(
                content,
                headers={
                    'Content-Type': content_type,
                    'Cache-Control': 'public, max-age=86400',
                    'Access-Control-Allow-Origin': '*',
                    'X-Cache-Status': 'HIT-DISK',
                }
            )

        # 4. 缓存未命中，从外部获取资源
        logger.info(f"CDN 缓存未命中，从外部获取: {decoded_url}")

        # 检查响应大小
        content_length = response.headers.get('Content-Length')
        if content_length and int(content_length) > MAX_PROXY_SIZE:
            return jsonify({'error': '文件过大,超过10MB限制'}), 413

        # 读取内容,限制大小
        content = b''
        for chunk in response.iter_content(chunk_size=8192):
            content += chunk
            if len(content) > MAX_PROXY_SIZE:
                return jsonify({'error': '文件过大,超过10MB限制'}), 413

        # 5. 存储到缓存
        set_cdn_to_memory_cache(url_hash, content, content_type)
        set_cdn_to_file_cache(url_hash, content, content_type)

        # 6. 返回响应
        flask_response = Response(
            content,
            status=response.status_code,
            headers={
                'Content-Type': content_type,
                'Cache-Control': 'public, max-age=86400',
                'Access-Control-Allow-Origin': '*',
                'X-Cache-Status': 'MISS',
            }
        )

        return flask_response

    except requests.exceptions.Timeout:
        logger.warning(f"CDN代理请求超时: {decoded_url}")
        return jsonify({'error': '请求超时'}), 504
    except requests.exceptions.RequestException as e:
        logger.error(f"CDN代理请求失败: {decoded_url}, 错误: {e}")
        return jsonify({'error': '请求失败'}), 502
    except Exception as e:
        logger.error(f"CDN代理异常: {e}")
        return jsonify({'error': '代理失败'}), 500

@app.route('/upload', methods=['POST'])
@limiter.limit("10 per hour")  # 上传速率限制
def upload_html():
    """处理HTML上传请求"""
    try:
        # 检查存储配额
        is_within_quota, current_size, quota = check_storage_quota()
        if not is_within_quota:
            return jsonify({
                'error': f'存储空间已满，当前使用: {current_size / (1024*1024):.1f}MB / {quota / (1024*1024):.1f}MB'
            }), 507  # 507 Insufficient Storage

        # 获取HTML内容
        html_content = request.form.get('html_content', '')
        if not html_content.strip():
            return jsonify({'error': '请输入HTML内容'}), 400

        # 检查内容大小 (双重检查,虽然Flask的MAX_CONTENT_LENGTH也会检查)
        content_size = len(html_content.encode('utf-8'))
        if content_size > MAX_CONTENT_LENGTH:
            return jsonify({'error': f'HTML内容过大,最大允许{MAX_CONTENT_LENGTH / (1024*1024):.1f}MB'}), 413

        # 生成随机目录名
        random_dir = generate_random_string()
        dir_path = os.path.join(app.config['UPLOAD_FOLDER'], random_dir)

        # 创建目录
        os.makedirs(dir_path, exist_ok=True)

        # 替换CDN链接为代理链接
        html_with_proxy = replace_cdn_links(html_content)

        # 注意: 这是一个HTML预览工具,用户需要能够使用JavaScript和完整HTML功能
        # 安全措施通过以下方式实现:
        # 1. 在 serve_static() 中添加 CSP 头限制恶意行为
        # 2. X-Frame-Options 防止被恶意嵌入
        # 3. 未来可以考虑将预览域名与主应用域名分离
        # 如需启用HTML清理,请取消下面一行的注释:
        # cleaned_html = sanitize_html(html_with_proxy)
        cleaned_html = html_with_proxy

        # 保存为index.html
        file_path = os.path.join(dir_path, 'index.html')
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(cleaned_html)

        # 提取并保存项目元数据
        metadata = extract_html_metadata(html_content)
        save_project_metadata(random_dir, metadata)

        # 生成访问URL
        host_url = get_host_url()
        access_url = f"{host_url}/static/{random_dir}/index.html"

        # 使项目列表缓存失效
        invalidate_projects_cache()

        return jsonify({
            'success': True,
            'url': access_url,
            'project_id': random_dir,
            'message': 'HTML文件已成功保存，CDN资源已自动代理'
        })

    except Exception as e:
        # 记录详细错误到日志
        logger.error(f"上传HTML失败: {e}")
        # 检查是否是413错误 (请求体过大)
        error_msg = str(e)
        if '413' in error_msg or 'Request Entity Too Large' in error_msg:
            return jsonify({'error': f'请求内容过大,最大允许{MAX_CONTENT_LENGTH / (1024*1024):.1f}MB'}), 413
        # 返回通用错误信息，避免泄漏系统细节
        return jsonify({'error': '保存失败,请稍后重试'}), 500

@app.route('/api/projects', methods=['GET'])
@csrf.exempt  # GET请求,只读操作,可以豁免CSRF
def get_projects():
    """获取已部署项目的API接口，支持分页"""
    try:
        # 获取分页参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)

        # 限制每页数量范围
        per_page = max(1, min(per_page, 100))  # 1-100之间
        page = max(1, page)  # 至少为1

        # 获取所有项目
        all_projects = get_all_projects()
        total = len(all_projects)

        # 计算分页
        start = (page - 1) * per_page
        end = start + per_page
        projects = all_projects[start:end]

        # 计算总页数
        total_pages = (total + per_page - 1) // per_page if total > 0 else 0

        return jsonify({
            'success': True,
            'projects': projects,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_prev': page > 1
            }
        })
    except Exception as e:
        logger.error(f"获取项目列表失败: {e}")
        return jsonify({
            'success': False,
            'error': '获取项目列表失败,请稍后重试'
        }), 500

@app.route('/api/storage/stats', methods=['GET'])
@csrf.exempt  # GET请求,只读操作,可以豁免CSRF
def get_storage_stats():
    """获取存储使用统计信息"""
    try:
        is_within_quota, current_size, quota = check_storage_quota()

        # 计算项目数量
        projects = get_all_projects()
        project_count = len(projects)

        return jsonify({
            'success': True,
            'storage': {
                'used': current_size,
                'used_mb': round(current_size / (1024*1024), 2),
                'quota': quota,
                'quota_mb': round(quota / (1024*1024), 2),
                'usage_percentage': round((current_size / quota) * 100, 2) if quota > 0 else 0,
                'available': quota - current_size,
                'available_mb': round((quota - current_size) / (1024*1024), 2),
                'is_within_quota': is_within_quota
            },
            'projects': {
                'total': project_count
            }
        })
    except Exception as e:
        logger.error(f"获取存储统计失败: {e}")
        return jsonify({
            'success': False,
            'error': '获取存储统计失败,请稍后重试'
        }), 500

@app.route('/api/cleanup/run', methods=['POST'])
@limiter.limit("5 per hour")  # 手动清理速率限制
def manual_cleanup():
    """手动触发清理过期项目"""
    try:
        cleanup_expired_projects()
        return jsonify({
            'success': True,
            'message': '清理任务已执行完成'
        })
    except Exception as e:
        logger.error(f"手动清理失败: {e}")
        return jsonify({
            'success': False,
            'error': '清理任务执行失败,请稍后重试'
        }), 500

@app.route('/api/cleanup/status', methods=['GET'])
@csrf.exempt  # GET请求,只读操作,可以豁免CSRF
def cleanup_status():
    """获取清理任务状态和配置"""
    try:
        return jsonify({
            'success': True,
            'config': {
                'expiry_days': PROJECT_EXPIRY_DAYS,
                'cleanup_interval_hours': CLEANUP_INTERVAL_HOURS,
                'enabled': scheduler.running
            }
        })
    except Exception as e:
        logger.error(f"获取清理状态失败: {e}")
        return jsonify({
            'success': False,
            'error': '获取清理状态失败,请稍后重试'
        }), 500

@app.route('/api/projects/<project_id>/upload-thumbnail', methods=['POST'])
def upload_thumbnail(project_id):
    """上传项目缩略图"""
    try:
        # 检查项目是否存在
        project_path = os.path.join(app.config['UPLOAD_FOLDER'], project_id)
        if not os.path.exists(project_path) or not os.path.isdir(project_path):
            return jsonify({
                'success': False,
                'error': '项目不存在'
            }), 404

        # 获取base64图片数据
        data = request.get_json()
        if not data or 'thumbnail' not in data:
            return jsonify({
                'success': False,
                'error': '缺少缩略图数据'
            }), 400

        # 保存缩略图
        success = save_thumbnail_from_base64(project_id, data['thumbnail'])

        if success:
            host_url = get_host_url()
            thumbnail_url = f"{host_url}/static/{project_id}/thumbnail.png"

            # 使项目列表缓存失效(虽然缩略图不影响项目列表,但为了保持数据一致性)
            invalidate_projects_cache()

            return jsonify({
                'success': True,
                'thumbnail_url': thumbnail_url,
                'message': '缩略图上传成功'
            })
        else:
            return jsonify({
                'success': False,
                'error': '缩略图保存失败'
            }), 500

    except Exception as e:
        logger.error(f"上传缩略图失败: 项目ID={project_id}, 错误={e}")
        return jsonify({
            'success': False,
            'error': '上传缩略图失败,请稍后重试'
        }), 500

@app.route('/api/projects/<project_id>', methods=['DELETE'])
@limiter.limit("20 per hour")  # 删除速率限制
def delete_project(project_id):
    """删除项目"""
    try:
        # 检查项目是否存在
        project_path = os.path.join(app.config['UPLOAD_FOLDER'], project_id)
        if not os.path.exists(project_path) or not os.path.isdir(project_path):
            return jsonify({
                'success': False,
                'error': '项目不存在'
            }), 404

        # 验证路径安全性，防止目录遍历攻击
        real_static_path = os.path.realpath(app.config['UPLOAD_FOLDER'])
        real_project_path = os.path.realpath(project_path)
        if not real_project_path.startswith(real_static_path):
            return jsonify({
                'success': False,
                'error': '非法的项目路径'
            }), 403

        # 删除整个项目目录
        shutil.rmtree(project_path)

        # 使项目列表缓存失效
        invalidate_projects_cache()

        return jsonify({
            'success': True,
            'message': '项目已成功删除'
        })

    except Exception as e:
        logger.error(f"删除项目失败: 项目ID={project_id}, 错误={e}")
        return jsonify({
            'success': False,
            'error': '删除项目失败,请稍后重试'
        }), 500

def cleanup_expired_projects():
    """
    清理过期项目的后台任务
    删除超过 PROJECT_EXPIRY_DAYS 天未访问的项目
    """
    try:
        logger.info(f"开始执行自动清理任务，过期天数: {PROJECT_EXPIRY_DAYS}")
        static_dir = app.config['UPLOAD_FOLDER']

        if not os.path.exists(static_dir):
            logger.info("静态文件目录不存在，跳过清理")
            return

        current_time = time.time()
        expiry_seconds = PROJECT_EXPIRY_DAYS * 24 * 60 * 60
        deleted_count = 0

        for item in os.listdir(static_dir):
            item_path = os.path.join(static_dir, item)

            # 只处理目录
            if not os.path.isdir(item_path):
                continue

            try:
                # 获取项目的最后修改时间
                # 使用 index.html 的修改时间作为参考
                index_file = os.path.join(item_path, 'index.html')
                if not os.path.exists(index_file):
                    continue

                # 获取文件的最后修改时间
                last_modified = os.path.getmtime(index_file)
                age_seconds = current_time - last_modified

                # 如果项目过期，删除它
                if age_seconds > expiry_seconds:
                    logger.info(f"删除过期项目: {item}, 年龄: {age_seconds / (24*60*60):.1f} 天")
                    shutil.rmtree(item_path)
                    deleted_count += 1

            except Exception as e:
                logger.error(f"清理项目 {item} 时出错: {e}")
                continue

        logger.info(f"自动清理任务完成，删除了 {deleted_count} 个过期项目")

        # 如果删除了任何项目，使缓存失效
        if deleted_count > 0:
            invalidate_projects_cache()

    except Exception as e:
        logger.error(f"执行自动清理任务失败: {e}")

# 初始化后台调度器
scheduler = BackgroundScheduler()
scheduler.add_job(
    func=cleanup_expired_projects,
    trigger="interval",
    hours=CLEANUP_INTERVAL_HOURS,
    id='cleanup_expired_projects',
    name='清理过期项目',
    replace_existing=True
)
scheduler.start()
logger.info(f"后台清理任务已启动，间隔: {CLEANUP_INTERVAL_HOURS} 小时")

@app.route('/static/<path:filename>')
@csrf.exempt  # 静态文件服务,可以豁免CSRF
def serve_static(filename):
    """
    提供静态文件访问
    添加安全头以隔离用户内容
    """
    # 先获取文件响应
    file_response = send_from_directory(app.config['UPLOAD_FOLDER'], filename)

    # 使用 make_response 创建响应对象以便修改头信息
    response = make_response(file_response)

    # 添加 Content-Security-Policy 头
    # 注意: 对于预览工具,我们允许脚本执行,因为这是用户的预期
    # 但我们限制外部资源加载,除非通过代理
    response.headers['Content-Security-Policy'] = (
        "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob:; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://unpkg.com https://cdnjs.cloudflare.com https://cdn.tailwindcss.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
        "img-src 'self' data: https:; "
        "font-src 'self' data: https://fonts.gstatic.com https://cdn.jsdelivr.net; "
        "connect-src 'self' https:; "
        "frame-ancestors 'none'; "
        "base-uri 'self';"
    )

    # 添加 X-Frame-Options 防止被嵌入
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'

    # 添加 X-Content-Type-Options
    response.headers['X-Content-Type-Options'] = 'nosniff'

    return response

# CDN 缓存管理 API
@app.route('/api/cdn-cache/stats', methods=['GET'])
@csrf.exempt  # GET 请求，可以豁免 CSRF
@limiter.limit("30 per hour")
def get_cdn_cache_stats():
    """获取 CDN 缓存统计信息"""
    try:
        # 统计内存缓存
        memory_items = len(cdn_memory_cache)
        memory_size = sum(len(item[0]) for item in cdn_memory_cache.values())

        # 统计文件缓存
        file_items = 0
        file_size = 0
        if os.path.exists(CDN_CACHE_DIR):
            for filename in os.listdir(CDN_CACHE_DIR):
                file_path = os.path.join(CDN_CACHE_DIR, filename)
                if os.path.isfile(file_path):
                    file_items += 1
                    file_size += os.path.getsize(file_path)

        return jsonify({
            'memory_cache': {
                'items': memory_items,
                'size_bytes': memory_size,
                'size_mb': round(memory_size / (1024 * 1024), 2),
                'max_items': CDN_CACHE_MAX_MEMORY_ITEMS,
            },
            'file_cache': {
                'items': file_items,
                'size_bytes': file_size,
                'size_mb': round(file_size / (1024 * 1024), 2),
                'ttl_days': CDN_CACHE_TTL / (24 * 3600),
            },
            'total': {
                'items': memory_items + file_items,
                'size_bytes': memory_size + file_size,
                'size_mb': round((memory_size + file_size) / (1024 * 1024), 2),
            }
        })
    except Exception as e:
        logger.error(f"获取 CDN 缓存统计失败: {e}")
        return jsonify({'error': '获取统计信息失败'}), 500

@app.route('/api/cdn-cache/clear', methods=['POST'])
@limiter.limit("5 per hour")
def clear_cdn_cache():
    """清空 CDN 缓存"""
    try:
        # 清空内存缓存
        cdn_memory_cache.clear()
        logger.info("内存缓存已清空")

        # 清空文件缓存
        deleted_files = 0
        if os.path.exists(CDN_CACHE_DIR):
            for filename in os.listdir(CDN_CACHE_DIR):
                file_path = os.path.join(CDN_CACHE_DIR, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    deleted_files += 1
            logger.info(f"文件缓存已清空，删除了 {deleted_files} 个文件")

        return jsonify({
            'success': True,
            'message': f'缓存已清空，删除了 {deleted_files} 个文件'
        })
    except Exception as e:
        logger.error(f"清空 CDN 缓存失败: {e}")
        return jsonify({'error': '清空缓存失败'}), 500

@app.route('/api/cdn-cache/cleanup', methods=['POST'])
@limiter.limit("5 per hour")
def cleanup_expired_cdn_cache():
    """清理过期的 CDN 缓存文件"""
    try:
        deleted_files = 0
        if os.path.exists(CDN_CACHE_DIR):
            current_time = time.time()
            for filename in os.listdir(CDN_CACHE_DIR):
                file_path = os.path.join(CDN_CACHE_DIR, filename)
                if os.path.isfile(file_path):
                    file_mtime = os.path.getmtime(file_path)
                    if current_time - file_mtime > CDN_CACHE_TTL:
                        os.remove(file_path)
                        deleted_files += 1
                        logger.info(f"删除过期缓存文件: {filename}")

        return jsonify({
            'success': True,
            'message': f'清理完成，删除了 {deleted_files} 个过期文件'
        })
    except Exception as e:
        logger.error(f"清理过期 CDN 缓存失败: {e}")
        return jsonify({'error': '清理过期缓存失败'}), 500

# 错误处理器
@app.errorhandler(413)
def request_entity_too_large(error):
    """处理请求体过大的错误"""
    return jsonify({
        'error': f'请求内容过大,最大允许{MAX_CONTENT_LENGTH / (1024*1024):.1f}MB'
    }), 413

@app.errorhandler(429)
def ratelimit_handler(error):
    """处理速率限制错误"""
    return jsonify({
        'error': '请求过于频繁,请稍后再试'
    }), 429

if __name__ == '__main__':
    # 确保static目录存在
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    # 从环境变量读取调试模式设置,生产环境应设置 DEBUG=False
    debug_mode = os.environ.get('DEBUG', 'False').lower() == 'true'
    try:
        app.run(debug=debug_mode, port=port, host='0.0.0.0')
    finally:
        # 应用关闭时停止调度器
        scheduler.shutdown()
        logger.info("后台清理任务已停止") 