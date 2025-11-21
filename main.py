import os
import secrets
import re
import requests
import json
import datetime
import base64
from flask import Flask, request, render_template, jsonify, send_from_directory, Response, make_response
from bs4 import BeautifulSoup
import bleach

app = Flask(__name__, static_folder=None)  # 禁用默认静态文件夹,使用自定义路由

# 配置
UPLOAD_FOLDER = 'static'
DEFAULT_PORT = 5010
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

port = os.environ.get('PORT', DEFAULT_PORT)

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
        print(f"保存元数据失败: {e}")
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
        print(f"加载元数据失败: {e}")

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
        print(f"从HTML提取元数据失败: {e}")

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
        print(f"保存缩略图失败: {e}")
        return False

def has_thumbnail(project_id):
    """
    检查项目是否有缩略图
    """
    thumbnail_path = os.path.join(app.config['UPLOAD_FOLDER'], project_id, 'thumbnail.png')
    return os.path.exists(thumbnail_path) and os.path.getsize(thumbnail_path) > 0

def get_all_projects():
    """
    获取所有已部署的项目列表
    """
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

    except Exception as e:
        print(f"获取项目列表失败: {e}")

    return projects

@app.route('/')
def index():
    """主页面 - 显示HTML输入表单"""
    return render_template('index.html')

@app.route('/proxy')
def proxy_resource():
    """代理外部CDN资源"""
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
        
        # 请求外部资源
        response = requests.get(decoded_url, timeout=10)
        response.raise_for_status()
        
        # 创建Flask响应
        flask_response = Response(
            response.content,
            status=response.status_code,
            headers={
                'Content-Type': response.headers.get('Content-Type', 'text/plain'),
                'Cache-Control': 'public, max-age=3600',  # 缓存1小时
                'Access-Control-Allow-Origin': '*',  # 允许跨域
            }
        )
        
        return flask_response
        
    except requests.exceptions.Timeout:
        return jsonify({'error': '请求超时'}), 504
    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'请求失败: {str(e)}'}), 502
    except Exception as e:
        return jsonify({'error': f'代理失败: {str(e)}'}), 500

@app.route('/upload', methods=['POST'])
def upload_html():
    """处理HTML上传请求"""
    try:
        # 获取HTML内容
        html_content = request.form.get('html_content', '')
        if not html_content.strip():
            return jsonify({'error': '请输入HTML内容'}), 400

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

        return jsonify({
            'success': True,
            'url': access_url,
            'project_id': random_dir,
            'message': 'HTML文件已成功保存，CDN资源已自动代理'
        })

    except Exception as e:
        return jsonify({'error': f'保存失败: {str(e)}'}), 500

@app.route('/api/projects', methods=['GET'])
def get_projects():
    """获取所有已部署项目的API接口"""
    try:
        projects = get_all_projects()
        return jsonify({
            'success': True,
            'projects': projects,
            'total': len(projects)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'获取项目列表失败: {str(e)}'
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
        return jsonify({
            'success': False,
            'error': f'上传缩略图失败: {str(e)}'
        }), 500

@app.route('/static/<path:filename>')
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

if __name__ == '__main__':
    # 确保static目录存在
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.run(debug=True, port=port, host='0.0.0.0') 