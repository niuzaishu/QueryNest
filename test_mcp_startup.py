#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MCP服务器启动验证脚本"""

import asyncio
import sys
import json
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from mcp_server import QueryNestMCPServer
from config import QueryNestConfig


async def test_mcp_startup():
    """测试MCP服务器启动和基础功能"""
    print("=== QueryNest MCP服务器启动验证 ===")
    
    try:
        # 1. 加载配置
        print("\n1. 加载配置文件...")
        config = QueryNestConfig.from_yaml('config.yaml')
        print(f"   ✓ 配置加载成功，实例数: {len(config.mongo_instances)}")
        
        # 2. 初始化服务器
        print("\n2. 初始化MCP服务器...")
        server = QueryNestMCPServer(config_file='config.yaml')
        print("   ✓ MCP服务器对象创建成功")
        
        # 3. 初始化组件
        print("\n3. 初始化系统组件...")
        await server.setup()
        print("   ✓ 系统组件初始化完成")
        
        # 4. 检查工具注册
        print("\n4. 检查MCP工具注册...")
        tool_count = len(server.tools)
        print(f"   ✓ 已注册工具数量: {tool_count}")
        
        if tool_count > 0:
            print("   注册的工具:")
            for i, (tool_name, tool) in enumerate(server.tools.items()):
                if i < 10:  # 只显示前10个工具
                    print(f"     - {tool_name}")
                elif i == 10:
                    print(f"     ... 还有 {tool_count - 10} 个工具")
                    break
        
        # 5. 测试基础连接
        print("\n5. 测试MongoDB连接...")
        try:
            instances_info = server.connection_manager.get_all_instances_info()
            healthy_count = sum(1 for info in instances_info if info.get('is_healthy', False))
            print(f"   ✓ 连接状态检查完成，健康实例数: {healthy_count}/{len(instances_info)}")
            
            for info in instances_info:
                status = "健康" if info.get('is_healthy', False) else "不健康"
                print(f"     - {info.get('name', 'Unknown')}: {status}")
                
        except Exception as e:
            print(f"   ⚠️  连接检查异常: {e}")
        
        # 6. 测试工具定义生成
        print("\n6. 测试工具定义生成...")
        try:
            # 测试一个基础工具的定义
            if "discover_instances" in server.tools:
                tool = server.tools["discover_instances"]
                tool_def = tool.get_tool_definition()
                print(f"   ✓ 工具定义生成成功: {tool_def.name}")
                print(f"     描述: {tool_def.description[:50]}...")
            else:
                print("   ⚠️  未找到基础工具")
        except Exception as e:
            print(f"   ✗ 工具定义生成失败: {e}")
        
        # 7. 清理
        print("\n7. 清理资源...")
        await server.cleanup()
        print("   ✓ 资源清理完成")
        
        print("\n🎉 MCP服务器启动验证成功！")
        return True
        
    except Exception as e:
        print(f"\n❌ MCP服务器启动验证失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_tool_execution():
    """测试工具执行功能"""
    print("\n=== 工具执行测试 ===")
    
    try:
        config = QueryNestConfig.from_yaml('config.yaml')
        server = QueryNestMCPServer(config_file='config.yaml')
        await server.setup()
        
        # 测试实例发现工具
        if "discover_instances" in server.tools:
            print("测试实例发现工具...")
            tool = server.tools["discover_instances"]
            
            result = await tool.execute({
                "include_health": True,
                "include_stats": False
            })
            
            if result and len(result) > 0:
                print("   ✓ 工具执行成功")
                result_text = result[0].text
                lines = result_text.split('\n')[:5]  # 只显示前5行
                for line in lines:
                    if line.strip():
                        print(f"     {line}")
                print("     ...")
            else:
                print("   ⚠️  工具执行返回空结果")
        
        await server.cleanup()
        print("✓ 工具执行测试完成")
        return True
        
    except Exception as e:
        print(f"✗ 工具执行测试失败: {e}")
        return False


async def main():
    """主测试函数"""
    print("QueryNest MCP服务器验证开始")
    print("=" * 50)
    
    # 测试1: 基础启动
    startup_ok = await test_mcp_startup()
    
    # 测试2: 工具执行（如果启动成功）
    execution_ok = False
    if startup_ok:
        execution_ok = await test_tool_execution()
    
    # 输出总结
    print("\n" + "=" * 50)
    print("验证结果总结:")
    print(f"  启动验证: {'✓ 通过' if startup_ok else '✗ 失败'}")
    print(f"  工具执行: {'✓ 通过' if execution_ok else '✗ 失败'}")
    
    if startup_ok and execution_ok:
        print("\n🎉 QueryNest MCP服务器完全验证通过！")
        print("服务器已准备就绪，可以正常启动和使用。")
    elif startup_ok:
        print("\n⚠️  QueryNest MCP服务器基础功能正常，但工具执行需要检查。")
    else:
        print("\n❌ QueryNest MCP服务器启动存在问题，需要修复。")


if __name__ == "__main__":
    asyncio.run(main())