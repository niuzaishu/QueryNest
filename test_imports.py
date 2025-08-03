#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试模块导入"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_imports():
    """测试所有模块导入"""
    print("🧪 测试模块导入...")
    
    # 1. 基础配置
    try:
        from config import QueryNestConfig
        print("✅ config 模块导入成功")
    except Exception as e:
        print(f"❌ config 模块导入失败: {e}")
        return False
    
    # 2. 数据库模块
    try:
        from database.connection_manager import ConnectionManager
        from database.metadata_manager import MetadataManager
        from database.query_engine import QueryEngine
        print("✅ database 模块导入成功")
    except Exception as e:
        print(f"❌ database 模块导入失败: {e}")
        return False
    
    # 3. 扫描器模块
    try:
        from scanner.structure_scanner import StructureScanner
        from scanner.semantic_analyzer import SemanticAnalyzer
        print("✅ scanner 模块导入成功")
    except Exception as e:
        print(f"❌ scanner 模块导入失败: {e}")
        return False
    
    # 4. MCP 工具模块
    try:
        from mcp_tools import (
            InstanceDiscoveryTool,
            DatabaseDiscoveryTool,
            CollectionAnalysisTool,
            SemanticManagementTool,
            SemanticCompletionTool,
            QueryGenerationTool,
            QueryConfirmationTool,
            FeedbackTools,
        )
        print("✅ mcp_tools 模块导入成功")
    except Exception as e:
        print(f"❌ mcp_tools 模块导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 5. MCP 服务器
    try:
        import mcp_server
        print("✅ mcp_server 模块导入成功")
    except Exception as e:
        print(f"❌ mcp_server 模块导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("🎉 所有模块导入成功！")
    return True

if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)