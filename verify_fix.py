#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证修复结果"""

import sys
from pathlib import Path
import os

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def main():
    print("🔍 验证QueryNest配置修复结果")
    print("=" * 50)
    
    # 1. 检查项目结构
    print("1. 检查项目结构:")
    required_files = [
        "config.yaml",
        "config.py", 
        "mcp_server.py",
        "start_mcp.py"
    ]
    
    for file in required_files:
        if (project_root / file).exists():
            print(f"  ✅ {file} - 存在")
        else:
            print(f"  ❌ {file} - 不存在")
    
    # 2. 测试配置文件加载
    print("\n2. 测试配置文件加载:")
    try:
        from config import QueryNestConfig
        
        # 使用新的查找策略
        config = QueryNestConfig.from_yaml("config.yaml")
        print("  ✅ 配置文件加载成功")
        print(f"  📊 MongoDB实例数: {len(config.mongo_instances)}")
        print(f"  🏷️  MCP服务名: {config.mcp.name}")
        
    except Exception as e:
        print(f"  ❌ 配置文件加载失败: {e}")
        return False
    
    # 3. 检查启动脚本
    print("\n3. 检查启动脚本:")
    try:
        from start_mcp import main as start_main
        print("  ✅ start_mcp.py 可正常导入")
    except Exception as e:
        print(f"  ❌ start_mcp.py 导入失败: {e}")
        return False
    
    # 4. 检查MCP服务器入口
    print("\n4. 检查MCP服务器:")
    try:
        from mcp_server import QueryNestMCPServer, cli_main
        print("  ✅ MCP服务器可正常导入")
    except Exception as e:
        print(f"  ❌ MCP服务器导入失败: {e}")
        return False
    
    # 5. 模拟配置文件查找
    print("\n5. 模拟配置文件查找策略:")
    search_paths = [
        Path.cwd() / "config.yaml",
        Path(__file__).parent / "config.yaml",
        Path(os.environ.get('QUERYNEST_CONFIG_DIR', '.')) / "config.yaml",
    ]
    
    found_config = None
    for i, path in enumerate(search_paths, 1):
        if path.exists():
            print(f"  ✅ 路径{i}: {path} - 找到")
            if found_config is None:
                found_config = path
        else:
            print(f"  ⚠️  路径{i}: {path} - 未找到")
    
    if found_config:
        print(f"  🎯 将使用配置文件: {found_config}")
    
    print("\n" + "=" * 50)
    print("✅ 验证完成！所有核心组件可正常导入和使用")
    print("\n💡 建议的uvx运行方式:")
    print(f"   uvx --from \"{project_root}\" querynest-mcp")
    print(f"   uvx --from \"{project_root}\" querynest-mcp --config \"{project_root / 'config.yaml'}\"")
    
    return True

if __name__ == "__main__":
    main()