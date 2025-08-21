#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试数据库选择工具"""

import asyncio
import sys
import os

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.connection_manager import ConnectionManager
from database.metadata_manager import MetadataManager
from config import QueryNestConfig
from mcp_tools.database_selection import DatabaseSelectionTool

async def test_database_selection():
    """测试数据库选择工具"""
    try:
        print("初始化配置...")
        config = QueryNestConfig.from_yaml("config.yaml")
        
        print("初始化连接管理器...")
        connection_manager = ConnectionManager(config)
        success = await connection_manager.initialize()
        print(f"连接管理器初始化结果: {success}")
        
        if not success:
            print("连接管理器初始化失败")
            return
        
        print("初始化元数据管理器...")
        metadata_manager = MetadataManager(config)
        
        print("创建数据库选择工具...")
        db_selection_tool = DatabaseSelectionTool(connection_manager, metadata_manager)
        
        print("测试选择数据库...")
        arguments = {
            "instance_id": "local_dev",
            "database_name": "za_bank_ras"
        }
        
        result = await db_selection_tool.execute(arguments)
        print(f"执行结果: {result}")
        
        print("关闭连接...")
        await connection_manager.shutdown()
        print("测试完成")
        
    except Exception as e:
        print(f"测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_database_selection())