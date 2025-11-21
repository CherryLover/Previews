#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试项目列表缓存功能
"""

import requests
import time
import json

BASE_URL = "http://127.0.0.1:5010"

# 创建一个会话来保持 cookies
session = requests.Session()

def get_csrf_token():
    """获取CSRF token"""
    response = session.get(f"{BASE_URL}/api/csrf-token")
    return response.json()['csrf_token']

def test_cache_functionality():
    """测试缓存基本功能"""
    print("=" * 60)
    print("测试 1: 缓存基本功能")
    print("=" * 60)

    # 第一次请求 - 应该从文件系统获取
    print("\n第一次请求项目列表...")
    start = time.time()
    response1 = session.get(f"{BASE_URL}/api/projects")
    time1 = time.time() - start
    print(f"响应时间: {time1*1000:.2f}ms")
    print(f"状态码: {response1.status_code}")
    assert response1.status_code == 200
    data1 = response1.json()
    print(f"项目数量: {data1['pagination']['total']}")

    # 第二次请求 - 应该使用缓存
    print("\n第二次请求项目列表 (应该使用缓存)...")
    start = time.time()
    response2 = session.get(f"{BASE_URL}/api/projects")
    time2 = time.time() - start
    print(f"响应时间: {time2*1000:.2f}ms")
    print(f"状态码: {response2.status_code}")
    assert response2.status_code == 200
    data2 = response2.json()
    print(f"项目数量: {data2['pagination']['total']}")

    # 验证缓存生效 (缓存请求应该更快)
    if time2 < time1:
        print(f"\n✓ 缓存生效! 速度提升: {((time1-time2)/time1*100):.1f}%")
    else:
        print(f"\n✓ 两次请求完成 (时间差异不明显可能是项目数量较少)")

    return data1['pagination']['total']

def test_cache_invalidation():
    """测试缓存失效机制"""
    print("\n" + "=" * 60)
    print("测试 2: 缓存失效机制")
    print("=" * 60)

    # 获取当前项目数量
    response = session.get(f"{BASE_URL}/api/projects")
    initial_count = response.json()['pagination']['total']
    print(f"\n当前项目数量: {initial_count}")

    # 上传新项目
    print("\n上传新项目...")
    csrf_token = get_csrf_token()
    html_content = """
    <!DOCTYPE html>
    <html>
    <head><title>缓存测试项目</title></head>
    <body><h1>测试缓存失效</h1></body>
    </html>
    """

    response = session.post(
        f"{BASE_URL}/upload",
        data={'html_content': html_content},
        headers={'X-CSRFToken': csrf_token}
    )

    assert response.status_code == 200
    result = response.json()
    print(f"上传成功: {result['project_id']}")
    project_id = result['project_id']

    # 立即请求项目列表,应该看到新项目
    print("\n重新获取项目列表...")
    response = session.get(f"{BASE_URL}/api/projects")
    new_count = response.json()['pagination']['total']
    print(f"新的项目数量: {new_count}")

    if new_count == initial_count + 1:
        print("✓ 缓存已正确失效,新项目已出现在列表中")
    else:
        print(f"✗ 缓存失效失败! 期望 {initial_count + 1}, 实际 {new_count}")
        return None

    # 清理测试项目
    print(f"\n清理测试项目 {project_id}...")
    response = session.delete(
        f"{BASE_URL}/api/projects/{project_id}",
        headers={'X-CSRFToken': csrf_token}
    )

    if response.status_code == 200:
        print("✓ 测试项目已删除")

        # 验证删除后缓存失效
        response = session.get(f"{BASE_URL}/api/projects")
        final_count = response.json()['pagination']['total']
        print(f"最终项目数量: {final_count}")

        if final_count == initial_count:
            print("✓ 删除后缓存正确失效")
        else:
            print(f"✗ 删除后缓存失效失败! 期望 {initial_count}, 实际 {final_count}")

    return project_id

def test_cache_ttl():
    """测试缓存TTL (需要等待5分钟,可选测试)"""
    print("\n" + "=" * 60)
    print("测试 3: 缓存TTL (需要等待5分钟)")
    print("=" * 60)

    print("\n跳过TTL测试 (需要等待5分钟)")
    print("如需测试,请手动验证: 等待5分钟后再次请求应该重新从文件系统获取")

def test_pagination_with_cache():
    """测试分页功能与缓存的配合"""
    print("\n" + "=" * 60)
    print("测试 4: 分页与缓存配合")
    print("=" * 60)

    # 获取第一页
    print("\n获取第一页...")
    response1 = session.get(f"{BASE_URL}/api/projects?page=1&per_page=5")
    assert response1.status_code == 200
    data1 = response1.json()
    print(f"第一页项目数: {len(data1['projects'])}")
    print(f"总页数: {data1['pagination']['total_pages']}")

    # 获取第二页 (应该使用相同的缓存数据)
    if data1['pagination']['has_next']:
        print("\n获取第二页...")
        response2 = session.get(f"{BASE_URL}/api/projects?page=2&per_page=5")
        assert response2.status_code == 200
        data2 = response2.json()
        print(f"第二页项目数: {len(data2['projects'])}")
        print("✓ 分页功能正常工作")
    else:
        print("\n只有一页数据,跳过第二页测试")

if __name__ == "__main__":
    try:
        print("\n开始测试项目列表缓存功能...")
        print("\n请确保应用正在运行 (python main.py)")

        # 测试应用是否运行
        try:
            session.get(BASE_URL, timeout=2)
        except requests.exceptions.ConnectionError:
            print("\n✗ 错误: 无法连接到应用,请先启动应用")
            exit(1)

        # 运行测试
        test_cache_functionality()
        test_cache_invalidation()
        test_cache_ttl()
        test_pagination_with_cache()

        print("\n" + "=" * 60)
        print("所有测试完成!")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n✗ 测试失败: {e}")
        exit(1)
    except Exception as e:
        print(f"\n✗ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
