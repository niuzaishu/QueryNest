#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试修复后的select_collection工作流约束"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from mcp_server import QueryNestMCPServer


async def test_select_collection_constraints():
    """测试select_collection工具的工作流约束"""
    print("测试select_collection工作流约束...")
    
    server = QueryNestMCPServer('config.yaml')
    await server.initialize()
    
    print("MCP服务器初始化成功")
    
    # 重置工作流
    print("重置工作流...")
    reset_result = await server.tools['workflow_reset'].execute({
        'confirm': True,
        'session_id': 'test_session'
    })
    print("工作流重置完成")
    
    # 测试原始场景：直接调用select_collection
    print("测试场景1：直接调用select_collection（无上下文）")
    try:
        result = await server.tools['select_collection'].execute({
            'show_recommendations': True,
            'session_id': 'test_session'
        }, 'test_session')
        
        response_text = result[0].text
        print("响应内容:")
        print(response_text[:300] + "..." if len(response_text) > 300 else response_text)
        
        if "工作流约束" in response_text:
            print("仍然被工作流约束阻止")
        elif "缺少实例信息" in response_text or "缺少数据库信息" in response_text:
            print("正确显示了缺少信息的提示（比工作流约束更友好）")
        else:
            print("成功绕过工作流约束")
            
    except Exception as e:
        print(f"调用失败: {e}")
    
    # 测试改进场景：提供完整上下文
    print("测试场景2：提供完整上下文")
    try:
        result = await server.tools['select_collection'].execute({
            'instance_id': 'ras_sit',
            'database_name': 'za_bank_ras',
            'show_recommendations': True,
            'session_id': 'test_session'
        }, 'test_session')
        
        response_text = result[0].text
        print("响应内容:")
        print(response_text[:300] + "..." if len(response_text) > 300 else response_text)
        
        if "工作流约束" in response_text:
            print("仍然被工作流约束阻止")
        elif "选择集合" in response_text or "推荐" in response_text:
            print("成功显示集合选择界面")
        else:
            print("响应内容待分析")
            
    except Exception as e:
        print(f"调用失败: {e}")
    
    print("测试完成")


if __name__ == "__main__":
    asyncio.run(test_select_collection_constraints())