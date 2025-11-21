#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一的单元测试运行脚本
只运行不需要应用运行的单元测试
"""

import sys
import unittest

# 导入所有单元测试模块
from test_cdn_cache import TestCDNCacheFunctionality, TestCDNCacheHelpers

if __name__ == '__main__':
    print("=" * 70)
    print("运行单元测试套件")
    print("=" * 70)
    print()

    # 创建测试套件
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # 添加 CDN 缓存测试
    print("添加 CDN 缓存测试...")
    suite.addTests(loader.loadTestsFromTestCase(TestCDNCacheFunctionality))
    suite.addTests(loader.loadTestsFromTestCase(TestCDNCacheHelpers))

    print(f"总共 {suite.countTestCases()} 个测试用例\n")

    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 输出总结
    print("\n" + "=" * 70)
    print("测试总结")
    print("=" * 70)
    print(f"运行测试数: {result.testsRun}")
    print(f"成功: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"失败: {len(result.failures)}")
    print(f"错误: {len(result.errors)}")

    if result.wasSuccessful():
        print("\n✓ 所有测试通过!")
    else:
        print("\n✗ 部分测试失败")

    # 退出码
    sys.exit(0 if result.wasSuccessful() else 1)
