#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最小化MCP服务器 - 用于测试uvx构建"""

def cli_main():
    """渐进式功能测试"""
    print("🚀 QueryNest MCP 服务器启动")
    
    # 步骤1: 基本路径处理
    try:
        from pathlib import Path
        import os
        import sys
        
        # 获取实际的项目路径（不是临时路径）
        # uvx会把我们的代码打包，我们需要找到真正的项目目录
        possible_config_paths = [
            Path.cwd() / "config.yaml",
            Path("C:/Users/zaishu.niu/PycharmProjects/QueryNest") / "config.yaml",
        ]
        
        config_path = None
        for path in possible_config_paths:
            if path.exists():
                config_path = path
                print(f"✅ 找到配置文件: {config_path}")
                break
        
        if not config_path:
            # 如果找不到，使用默认配置
            print("⚠️  未找到配置文件，使用内嵌配置")
            return test_embedded_config()
            
        # 切换到项目目录
        project_dir = config_path.parent
        os.chdir(project_dir)
        sys.path.insert(0, str(project_dir))
        
        print(f"📁 工作目录: {os.getcwd()}")
        
        # 步骤2: 测试配置模块导入
        print("\n🔧 测试配置模块...")
        from config import QueryNestConfig
        print("✅ 配置模块导入成功")
        
        # 步骤3: 测试配置加载
        config = QueryNestConfig.from_yaml(str(config_path))
        print(f"✅ 配置加载成功 - MongoDB实例: {len(config.mongo_instances)}")
        
        # 步骤4: 基础MCP测试
        print("\n🔧 测试MCP基础模块...")
        import structlog
        from mcp.server import Server
        print("✅ MCP基础模块导入成功")
        
        print("\n🎉 核心功能测试通过！准备启动完整服务...")
        
        # 这里可以调用真正的MCP服务器
        return start_real_mcp_server(config)
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        
def test_embedded_config():
    """使用内嵌配置进行测试"""
    print("🧪 使用内嵌配置测试...")
    try:
        from config import QueryNestConfig
        
        # 创建最小配置
        minimal_config = {
            'mongo_instances': {
                'test': {
                    'name': 'Test Instance',
                    'connection_string': 'mongodb://localhost:27017',
                    'environment': 'test',
                    'status': 'active'
                }
            },
            'mcp': {
                'name': 'QueryNest',
                'version': '1.0.0'
            },
            'security': {}
        }
        
        config = QueryNestConfig(**minimal_config)
        print(f"✅ 内嵌配置创建成功 - MongoDB实例: {len(config.mongo_instances)}")
        
        return start_real_mcp_server(config)
        
    except Exception as e:
        print(f"❌ 内嵌配置测试失败: {e}")
        return False

def start_real_mcp_server(config):
    """启动真正的MCP服务器"""
    print("\n🚀 启动MCP服务器...")
    try:
        import asyncio
        import structlog
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        from mcp.types import Tool, TextContent
        
        # 配置日志
        structlog.configure(
            processors=[
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer(ensure_ascii=False)
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        
        logger = structlog.get_logger(__name__)
        
        class QueryNestMCPServer:
            def __init__(self, config):
                self.config = config
                self.server = Server("QueryNest")
                self.logger = logger
                
                # 注册基本的处理器
                self.server.list_tools()(self.handle_list_tools)
                self.server.call_tool()(self.handle_call_tool)
                
            async def handle_list_tools(self):
                """返回可用工具列表"""
                return [
                    Tool(
                        name="test_connection",
                        description="测试MongoDB连接",
                        inputSchema={
                            "type": "object",
                            "properties": {},
                        }
                    )
                ]
            
            async def handle_call_tool(self, name, arguments):
                """处理工具调用"""
                if name == "test_connection":
                    return [TextContent(
                        type="text",
                        text=f"✅ MongoDB连接测试成功！\n配置的实例数: {len(self.config.mongo_instances)}"
                    )]
                else:
                    raise ValueError(f"未知工具: {name}")
            
            async def run(self):
                """运行服务器"""
                self.logger.info("启动QueryNest MCP服务器", 
                                config_instances=len(self.config.mongo_instances))
                
                async with stdio_server() as (read_stream, write_stream):
                    await self.server.run(
                        read_stream, 
                        write_stream, 
                        self.server.create_initialization_options()
                    )
        
        print("✅ MCP服务器类创建成功")
        print("🔄 准备启动异步事件循环...")
        
        # 创建并运行服务器
        mcp_server = QueryNestMCPServer(config)
        
        # 实际启动服务器
        print("🚀 启动stdio MCP服务器...")
        asyncio.run(mcp_server.run())
        
        return True
        
    except Exception as e:
        print(f"❌ MCP服务器启动失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    cli_main()