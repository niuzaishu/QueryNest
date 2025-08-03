# -*- coding: utf-8 -*-
"""QueryNest MCP服务器 - 调试版本"""

def cli_main():
    """命令行入口点 - 逐步测试导入"""
    print("🔍 开始导入测试...")
    
    try:
        print("1. 测试基础模块...")
        import asyncio
        import sys
        from pathlib import Path
        print("✅ 基础模块导入成功")
        
        print("2. 测试structlog...")
        import structlog
        print("✅ structlog导入成功")
        
        print("3. 测试config...")
        from config import QueryNestConfig
        print("✅ config导入成功")
        
        print("4. 测试配置文件加载...")
        project_root = Path(__file__).parent
        config_file = project_root / "config.yaml"
        
        if config_file.exists():
            config = QueryNestConfig.from_yaml("config.yaml")
            print(f"✅ 配置文件加载成功 - MongoDB实例: {len(config.mongo_instances)}")
        else:
            print(f"❌ 配置文件不存在: {config_file}")
            return
            
        print("5. 测试MCP模块...")
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        print("✅ MCP模块导入成功")
        
        print("🎉 所有核心模块测试通过！")
        print("MCP服务器可以正常启动")
        
    except Exception as e:
        print(f"❌ 导入测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    cli_main()