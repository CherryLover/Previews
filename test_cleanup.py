#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试自动清理功能
"""
import sys
import os

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """测试所有必要的模块导入"""
    print("测试模块导入...")
    try:
        import main
        print("✓ 主模块导入成功")

        # 检查调度器是否已启动
        if hasattr(main, 'scheduler') and main.scheduler.running:
            print("✓ 后台调度器已启动")
        else:
            print("✗ 后台调度器未启动")
            return False

        # 检查清理函数是否存在
        if hasattr(main, 'cleanup_expired_projects'):
            print("✓ 清理函数已定义")
        else:
            print("✗ 清理函数未定义")
            return False

        # 检查配置是否正确
        print(f"  - 项目过期天数: {main.PROJECT_EXPIRY_DAYS}")
        print(f"  - 清理间隔(小时): {main.CLEANUP_INTERVAL_HOURS}")

        return True
    except Exception as e:
        print(f"✗ 导入失败: {e}")
        return False

def test_cleanup_function():
    """测试清理函数"""
    print("\n测试清理函数...")
    try:
        import main

        # 调用清理函数
        main.cleanup_expired_projects()
        print("✓ 清理函数执行成功")
        return True
    except Exception as e:
        print(f"✗ 清理函数执行失败: {e}")
        return False

def test_api_routes():
    """测试新的API路由是否注册"""
    print("\n测试API路由...")
    try:
        import main

        routes = [rule.rule for rule in main.app.url_map.iter_rules()]

        # 检查清理相关的端点
        expected_routes = [
            '/api/cleanup/run',
            '/api/cleanup/status'
        ]

        all_exist = True
        for route in expected_routes:
            if route in routes:
                print(f"✓ 路由 {route} 已注册")
            else:
                print(f"✗ 路由 {route} 未注册")
                all_exist = False

        return all_exist
    except Exception as e:
        print(f"✗ 路由检查失败: {e}")
        return False

def test_scheduler_jobs():
    """测试调度器任务"""
    print("\n测试调度器任务...")
    try:
        import main

        jobs = main.scheduler.get_jobs()
        print(f"  调度器中的任务数: {len(jobs)}")

        for job in jobs:
            print(f"  - 任务ID: {job.id}")
            print(f"    任务名称: {job.name}")
            print(f"    下次运行: {job.next_run_time}")

        # 检查是否有清理任务
        cleanup_job = main.scheduler.get_job('cleanup_expired_projects')
        if cleanup_job:
            print("✓ 清理任务已注册到调度器")
            return True
        else:
            print("✗ 清理任务未注册到调度器")
            return False
    except Exception as e:
        print(f"✗ 调度器任务检查失败: {e}")
        return False

def main_test():
    """主测试函数"""
    print("=" * 50)
    print("自动清理功能测试")
    print("=" * 50)

    results = []

    # 运行所有测试
    results.append(("模块导入", test_imports()))
    results.append(("清理函数", test_cleanup_function()))
    results.append(("API路由", test_api_routes()))
    results.append(("调度器任务", test_scheduler_jobs()))

    # 输出测试结果
    print("\n" + "=" * 50)
    print("测试结果总结")
    print("=" * 50)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{test_name:20s} {status}")

    print(f"\n总计: {passed}/{total} 测试通过")

    if passed == total:
        print("\n🎉 所有测试通过！")
        return 0
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败")
        return 1

if __name__ == '__main__':
    sys.exit(main_test())
