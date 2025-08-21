#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试连接管理器"""

import asyncio
import sys
import os

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.connection_manager import ConnectionManager
from config import QueryNestConfig

async def test_connection():
    """测试连接"""
    try:
        print("初始化配置...")
        config = QueryNestConfig.from_yaml("config.yaml")
        print(f"配置加载成功，实例数量: {len(config.mongo_instances)}")
        for key, instance in config.mongo_instances.items():
            print(f"  实例 {key}: {instance.name} ({instance.environment})")
        
        print("初始化连接管理器...")
        cm = ConnectionManager(config)
        success = await cm.initialize()
        print(f"连接管理器初始化结果: {success}")
        
        if not success:
            print("连接管理器初始化失败")
            return
        
        # 检查连接
        print("检查实例连接...")
        connection = cm.get_instance_connection('local_dev')
        print(f"Connection exists: {connection is not None}")
        
        if connection:
            print(f"Client exists: {connection.client is not None}")
            print(f"Is healthy: {connection.is_healthy}")
            
            if connection.client and connection.is_healthy:
                print("测试数据库列表获取...")
                try:
                    db_names = await connection.client.list_database_names()
                    print(f"数据库列表: {db_names}")
                except Exception as e:
                    print(f"获取数据库列表失败: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print("连接不健康或客户端不存在")
        else:
            print("无法获取实例连接")
            # 显示所有可用实例
            instances = cm.get_all_instances_info()
            print(f"可用实例: {instances}")
        
        print("关闭连接...")
        await cm.shutdown()
        print("测试完成")
        
    except Exception as e:
        print(f"测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_connection())