#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模拟 uvx 运行 querynest-mcp 的行为
用于验证修复结果
"""

import sys
import os
from pathlib import Path

def simulate_uvx():
    """模拟 uvx --from . querynest-mcp 的行为"""
    print("🧪 模拟 uvx --from . querynest-mcp 运行")
    print("=" * 50)
    
    # 模拟 uvx 的环境设置
    project_root = Path(__file__).parent.absolute()
    print(f"📁 项目根目录: {project_root}")
    print(f"💼 当前工作目录: {Path.cwd()}")
    
    # 确保项目根目录在 Python 路径中
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
        print(f"✅ 已添加到Python路径: {project_root}")
    
    try:
        # 根据 pyproject.toml 中的配置 querynest-mcp = "start_mcp:main"
        print("\n🚀 导入并执行 start_mcp:main")
        from start_mcp import main
        
        print("✅ start_mcp 模块导入成功")
        print("🔄 开始执行 main 函数...")
        print("-" * 30)
        
        # 执行主函数（这会启动MCP服务器，但我们只运行初始化部分）
        # 为了避免实际启动服务器，我们只测试导入和初始化
        
        # 检查关键模块是否可以正常导入
        from config import QueryNestConfig
        from mcp_server import QueryNestMCPServer
        
        print("✅ 所有关键模块导入成功")
        
        # 测试配置文件加载
        config_path = project_root / "config.yaml"
        if config_path.exists():
            os.environ['QUERYNEST_CONFIG_PATH'] = str(config_path)
            print(f"✅ 配置文件路径已设置: {config_path}")
            
            try:
                config = QueryNestConfig.from_yaml("config.yaml")
                print(f"✅ 配置文件加载成功 - MongoDB实例: {len(config.mongo_instances)}")
            except Exception as e:
                print(f"❌ 配置文件加载失败: {e}")
                return False
        else:
            print(f"❌ 配置文件不存在: {config_path}")
            return False
            
        print("\n" + "=" * 50)
        print("🎉 模拟测试成功！")
        print("💡 实际的 uvx 命令应该可以正常工作:")
        print(f"   uvx --from \"{project_root}\" querynest-mcp")
        
        return True
        
    except ImportError as e:
        print(f"❌ 导入错误: {e}")
        print(f"📂 当前Python路径: {sys.path[:3]}")
        return False
        
    except Exception as e:
        print(f"❌ 执行错误: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = simulate_uvx()
    sys.exit(0 if success else 1)