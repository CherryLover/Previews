# 共享任务记录

## 当前状态

### 已完成修复 (2025-11-21)
- ✅ **XSS 防护** - 实现了 `sanitize_html()` 函数并添加安全响应头
  - 实现位置: main.py:68-144, main.py:469-501
  - 关键修改: 禁用 Flask 默认 static 文件夹 (`static_folder=None`) 以确保自定义路由生效
  - 安全头: CSP, X-Frame-Options, X-Content-Type-Options

## 下一步任务

按照 ISSUES.md 的修复顺序,下一个应该修复的是 P0 级别的其他安全问题:

1. **CDN 代理速率限制** - 防止滥用
   - 需要: 安装 Flask-Limiter
   - 文件: main.py:242-288 (proxy 路由)

2. **代理请求大小限制** - 防止带宽滥用
   - 限制响应大小为 10MB

3. **HTML 上传大小限制** - 防止磁盘耗尽
   - 限制上传大小为 1MB
   - 文件: main.py:359 (upload 路由)

4. **总存储配额限制** - 防止无限增长

5. **调试模式安全** - 关闭生产环境调试模式
   - 文件: main.py:506
   - 改为从环境变量读取: `debug=os.environ.get('DEBUG', 'False').lower() == 'true'`

## 重要提示

- HTML 预览工具的特殊性: 不应该清理用户的 HTML 内容,而应该通过安全头隔离
- Flask 默认会自动服务 `static/` 文件夹,需要设置 `static_folder=None` 来禁用
- 测试文件可以删除: test_sanitize.py, test_headers.py, test_minimal.py
