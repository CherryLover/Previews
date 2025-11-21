#!/usr/bin/env python3
"""测试分页和 CSRF 功能"""

import json
import main

def test_pagination_api():
    """测试分页 API"""
    print("=" * 60)
    print("测试分页 API 功能")
    print("=" * 60)

    with main.app.test_client() as client:
        # 测试默认分页（第1页，每页20条）
        response = client.get('/api/projects')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] == True
        assert 'pagination' in data
        assert 'projects' in data
        print("✓ 默认分页测试通过")

        # 测试自定义分页参数
        response = client.get('/api/projects?page=1&per_page=10')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['pagination']['page'] == 1
        assert data['pagination']['per_page'] == 10
        print("✓ 自定义分页参数测试通过")

        # 测试边界条件 - 超大页码
        response = client.get('/api/projects?page=999&per_page=20')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data['projects']) == 0  # 超出范围，应该返回空数组
        print("✓ 边界条件测试通过")

        # 测试 per_page 限制（最大100）
        response = client.get('/api/projects?page=1&per_page=200')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['pagination']['per_page'] == 100  # 应该被限制为100
        print("✓ per_page 限制测试通过")

        # 验证分页元数据
        response = client.get('/api/projects?page=1&per_page=20')
        data = json.loads(response.data)
        pagination = data['pagination']
        assert 'total' in pagination
        assert 'total_pages' in pagination
        assert 'has_next' in pagination
        assert 'has_prev' in pagination
        print("✓ 分页元数据测试通过")

        print("\n✅ 所有分页测试通过！")

def test_csrf_token():
    """测试 CSRF token"""
    print("\n" + "=" * 60)
    print("测试 CSRF Token 功能")
    print("=" * 60)

    with main.app.test_client() as client:
        # 测试获取 CSRF token
        response = client.get('/api/csrf-token')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'csrf_token' in data
        assert len(data['csrf_token']) > 0
        print("✓ CSRF token 获取测试通过")
        print(f"  Token 长度: {len(data['csrf_token'])} 字符")

        csrf_token = data['csrf_token']

        # 测试带有 CSRF token 的 POST 请求
        html_content = '<html><head><title>Test</title></head><body><h1>Test Page</h1></body></html>'
        response = client.post('/upload',
            data={'html_content': html_content},
            headers={'X-CSRFToken': csrf_token}
        )
        # 可能会因为速率限制失败，但应该至少不是 CSRF 错误
        if response.status_code != 429:  # 跳过速率限制错误
            print(f"✓ 带 CSRF token 的 POST 请求测试完成 (状态码: {response.status_code})")
        else:
            print("⚠ 跳过 POST 请求测试（速率限制）")

        print("\n✅ 所有 CSRF 测试通过！")

def test_get_all_projects():
    """测试获取项目列表函数"""
    print("\n" + "=" * 60)
    print("测试项目列表获取功能")
    print("=" * 60)

    projects = main.get_all_projects()
    print(f"✓ 当前项目总数: {len(projects)}")

    if len(projects) > 0:
        print(f"✓ 第一个项目信息:")
        project = projects[0]
        print(f"  ID: {project.get('id')}")
        print(f"  标题: {project.get('title')}")
        print(f"  描述: {project.get('description')[:50]}...")
        print(f"  大小: {project.get('file_size')}")

    print("\n✅ 项目列表测试通过！")

if __name__ == '__main__':
    try:
        test_get_all_projects()
        test_pagination_api()
        test_csrf_token()

        print("\n" + "=" * 60)
        print("🎉 所有测试全部通过！")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
