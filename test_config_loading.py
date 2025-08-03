#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试配置文件加载功能
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_config_loading():
    """测试配置文件加载"""
    try:
        from config import QueryNestConfig
        
        # 测试从YAML文件加载配置
        config_path = "config.yaml"
        print(f"尝试加载配置文件: {config_path}")
        
        config = QueryNestConfig.from_yaml(config_path)
        
        print("✅ 配置文件加载成功！")
        print(f"MongoDB 实例数量: {len(config.mongo_instances)}")
        print(f"MCP 服务名称: {config.mcp.name}")
        print(f"安全配置 - 查询超时: {config.security.query_timeout}秒")
        
        return True
        
    except FileNotFoundError as e:
        print(f"❌ 配置文件未找到: {e}")
        return False
    except Exception as e:
        print(f"❌ 配置加载失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_config_loading()