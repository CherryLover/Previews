#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CDN 缓存功能测试套件
测试两层缓存机制：内存缓存 + 文件缓存
"""

import os
import sys
import time
import unittest
import shutil
from unittest.mock import Mock, patch

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入主应用
from main import app, cdn_memory_cache, CDN_CACHE_DIR, get_url_hash


class TestCDNCacheFunctionality(unittest.TestCase):
    """测试 CDN 缓存核心功能"""

    def setUp(self):
        """测试前设置"""
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

        # 清空缓存
        cdn_memory_cache.clear()
        if os.path.exists(CDN_CACHE_DIR):
            shutil.rmtree(CDN_CACHE_DIR)
        os.makedirs(CDN_CACHE_DIR, exist_ok=True)

        # 获取 CSRF token
        response = self.client.get('/api/csrf-token')
        self.csrf_token = response.json['csrf_token']

    def tearDown(self):
        """测试后清理"""
        cdn_memory_cache.clear()
        if os.path.exists(CDN_CACHE_DIR):
            shutil.rmtree(CDN_CACHE_DIR)

    @patch('main.requests.get')
    def test_cdn_cache_miss_and_store(self, mock_get):
        """测试缓存未命中时从外部获取并存储"""
        # 模拟外部 CDN 响应
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'Content-Type': 'text/css'}
        mock_response.iter_content = lambda chunk_size: [b'.test { color: red; }']
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # 第一次请求 - 缓存未命中
        response = self.client.get('/proxy?url=https://cdn.tailwindcss.com/test.css')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('X-Cache-Status'), 'MISS')
        self.assertEqual(response.data, b'.test { color: red; }')

        # 验证已存储到内存缓存
        url_hash = get_url_hash('https://cdn.tailwindcss.com/test.css')
        self.assertIn(url_hash, cdn_memory_cache)

        # 验证已存储到文件缓存
        cache_files = os.listdir(CDN_CACHE_DIR)
        self.assertEqual(len(cache_files), 1)
        self.assertTrue(cache_files[0].endswith('.css'))

    @patch('main.requests.get')
    def test_cdn_memory_cache_hit(self, mock_get):
        """测试内存缓存命中"""
        # 模拟外部 CDN 响应
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'Content-Type': 'application/javascript'}
        mock_response.iter_content = lambda chunk_size: [b'console.log("test");']
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # 第一次请求 - 缓存未命中
        response1 = self.client.get('/proxy?url=https://cdn.jsdelivr.net/test.js')
        self.assertEqual(response1.headers.get('X-Cache-Status'), 'MISS')

        # 第二次请求 - 内存缓存命中
        response2 = self.client.get('/proxy?url=https://cdn.jsdelivr.net/test.js')
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(response2.headers.get('X-Cache-Status'), 'HIT-MEMORY')
        self.assertEqual(response2.data, b'console.log("test");')

        # 验证只请求了一次外部资源
        self.assertEqual(mock_get.call_count, 1)

    @patch('main.requests.get')
    def test_cdn_file_cache_hit(self, mock_get):
        """测试文件缓存命中（内存缓存未命中）"""
        # 模拟外部 CDN 响应
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'Content-Type': 'text/css'}
        mock_response.iter_content = lambda chunk_size: [b'.cached { display: block; }']
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # 第一次请求 - 缓存未命中
        response1 = self.client.get('/proxy?url=https://unpkg.com/test.css')
        self.assertEqual(response1.headers.get('X-Cache-Status'), 'MISS')

        # 清空内存缓存（但保留文件缓存）
        cdn_memory_cache.clear()

        # 第二次请求 - 文件缓存命中
        # 注意：由于我们的实现，会先请求外部获取 Content-Type
        # 所以这里会有第二次外部请求
        response2 = self.client.get('/proxy?url=https://unpkg.com/test.css')
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(response2.headers.get('X-Cache-Status'), 'HIT-DISK')
        self.assertEqual(response2.data, b'.cached { display: block; }')

    def test_cdn_cache_stats_api(self):
        """测试缓存统计 API"""
        response = self.client.get('/api/cdn-cache/stats')

        self.assertEqual(response.status_code, 200)
        data = response.json

        self.assertIn('memory_cache', data)
        self.assertIn('file_cache', data)
        self.assertIn('total', data)

        self.assertEqual(data['memory_cache']['items'], 0)
        self.assertEqual(data['file_cache']['items'], 0)

    @patch('main.requests.get')
    def test_cdn_cache_stats_with_data(self, mock_get):
        """测试有数据时的缓存统计"""
        # 模拟外部 CDN 响应
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'Content-Type': 'text/css'}
        mock_response.iter_content = lambda chunk_size: [b'.test { margin: 0; }']
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # 添加一些缓存数据
        self.client.get('/proxy?url=https://cdn.tailwindcss.com/style1.css')

        # 获取统计
        response = self.client.get('/api/cdn-cache/stats')
        data = response.json

        self.assertEqual(data['memory_cache']['items'], 1)
        self.assertEqual(data['file_cache']['items'], 1)
        self.assertEqual(data['total']['items'], 2)  # 内存 + 文件各1个
        self.assertGreater(data['total']['size_bytes'], 0)

    @patch('main.requests.get')
    def test_cdn_cache_clear_api(self, mock_get):
        """测试清空缓存 API"""
        # 模拟外部 CDN 响应
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'Content-Type': 'application/javascript'}
        mock_response.iter_content = lambda chunk_size: [b'var x = 1;']
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # 添加一些缓存数据
        self.client.get('/proxy?url=https://cdnjs.cloudflare.com/script.js')

        # 验证缓存存在
        self.assertEqual(len(cdn_memory_cache), 1)
        self.assertEqual(len(os.listdir(CDN_CACHE_DIR)), 1)

        # 清空缓存
        response = self.client.post(
            '/api/cdn-cache/clear',
            headers={'X-CSRFToken': self.csrf_token}
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['success'])

        # 验证缓存已清空
        self.assertEqual(len(cdn_memory_cache), 0)
        self.assertEqual(len(os.listdir(CDN_CACHE_DIR)), 0)

    @patch('main.requests.get')
    def test_cdn_cache_cleanup_expired(self, mock_get):
        """测试清理过期缓存"""
        # 模拟外部 CDN 响应
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'Content-Type': 'text/css'}
        mock_response.iter_content = lambda chunk_size: [b'.expired { }']
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # 添加缓存数据
        self.client.get('/proxy?url=https://cdn.jsdelivr.net/expired.css')

        # 获取缓存文件路径
        cache_files = os.listdir(CDN_CACHE_DIR)
        self.assertEqual(len(cache_files), 1)

        cache_file_path = os.path.join(CDN_CACHE_DIR, cache_files[0])

        # 修改文件时间为过期时间（8 天前，超过 7 天 TTL）
        old_time = time.time() - (8 * 24 * 3600)
        os.utime(cache_file_path, (old_time, old_time))

        # 执行清理
        response = self.client.post(
            '/api/cdn-cache/cleanup',
            headers={'X-CSRFToken': self.csrf_token}
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['success'])
        self.assertIn('删除了 1 个过期文件', response.json['message'])

        # 验证过期文件已删除
        self.assertEqual(len(os.listdir(CDN_CACHE_DIR)), 0)

    def test_cdn_cache_domain_whitelist(self):
        """测试 CDN 域名白名单验证"""
        # 尝试代理不在白名单中的域名
        response = self.client.get('/proxy?url=https://evil.com/malicious.js')

        self.assertEqual(response.status_code, 403)
        self.assertIn('error', response.json)

    @patch('main.requests.get')
    def test_cdn_cache_size_limit(self, mock_get):
        """测试 CDN 代理大小限制"""
        # 模拟超过大小限制的响应
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {
            'Content-Type': 'application/javascript',
            'Content-Length': str(11 * 1024 * 1024)  # 11MB，超过 10MB 限制
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        response = self.client.get('/proxy?url=https://cdn.jsdelivr.net/huge.js')

        self.assertEqual(response.status_code, 413)
        self.assertIn('error', response.json)


class TestCDNCacheHelpers(unittest.TestCase):
    """测试 CDN 缓存辅助函数"""

    def test_get_url_hash(self):
        """测试 URL 哈希生成"""
        url1 = "https://cdn.tailwindcss.com/test.css"
        url2 = "https://cdn.tailwindcss.com/test.css"
        url3 = "https://cdn.tailwindcss.com/different.css"

        hash1 = get_url_hash(url1)
        hash2 = get_url_hash(url2)
        hash3 = get_url_hash(url3)

        # 相同 URL 应该生成相同哈希
        self.assertEqual(hash1, hash2)

        # 不同 URL 应该生成不同哈希
        self.assertNotEqual(hash1, hash3)

        # 哈希应该是 64 个字符（SHA256）
        self.assertEqual(len(hash1), 64)


if __name__ == '__main__':
    print("运行 CDN 缓存功能测试...")
    print("=" * 70)

    # 运行测试
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # 添加测试用例
    suite.addTests(loader.loadTestsFromTestCase(TestCDNCacheFunctionality))
    suite.addTests(loader.loadTestsFromTestCase(TestCDNCacheHelpers))

    # 运行测试并输出结果
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 70)
    print(f"测试完成: 运行 {result.testsRun} 个测试")
    print(f"成功: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"失败: {len(result.failures)}")
    print(f"错误: {len(result.errors)}")

    # 退出码：如果有失败或错误则返回 1
    sys.exit(0 if result.wasSuccessful() else 1)
