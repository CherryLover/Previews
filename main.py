import os
import secrets
from flask import Flask, request, render_template, jsonify, send_from_directory
import bleach

app = Flask(__name__)

# 配置
UPLOAD_FOLDER = 'static'
DEFAULT_PORT = 5010
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

port = os.environ.get('PORT', DEFAULT_PORT)

def get_host_url():
    """获取主机URL，从环境变量读取，如果没有则使用默认值"""
    host_url = os.environ.get('HOST_URL', f'http://127.0.0.1:{port}')
    if not host_url.startswith(('http://', 'https://')):
        host_url = 'https://' + host_url
    return host_url

def generate_random_string(length=8):
    """生成随机字符串作为目录名"""
    return secrets.token_urlsafe(length)[:length]

def sanitize_html(html_content):
    """
    HTML内容清理函数（暂不实现）
    后续可以使用bleach库进行安全清理
    """
    # TODO: 实现HTML清理逻辑
    return html_content

@app.route('/')
def index():
    """主页面 - 显示HTML输入表单"""
    return render_template('index.html')

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
        
        # 暂不清理HTML（后续实现）
        # cleaned_html = sanitize_html(html_content)
        cleaned_html = html_content
        
        # 保存为index.html
        file_path = os.path.join(dir_path, 'index.html')
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(cleaned_html)
        
        # 生成访问URL
        host_url = get_host_url()
        access_url = f"{host_url}/static/{random_dir}/index.html"
        
        return jsonify({
            'success': True,
            'url': access_url,
            'message': 'HTML文件已成功保存'
        })
        
    except Exception as e:
        return jsonify({'error': f'保存失败: {str(e)}'}), 500

@app.route('/static/<path:filename>')
def serve_static(filename):
    """提供静态文件访问"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    # 确保static目录存在
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.run(debug=True, port=port, host='0.0.0.0') 