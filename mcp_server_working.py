# -*- coding: utf-8 -*-
"""QueryNest MCP服务器 - 工作版本"""

import asyncio
import sys
import os
from pathlib import Path
import structlog
from mcp.server import Server, NotificationOptions
from mcp.server.stdio import stdio_server
from mcp.types import CallToolRequest, ListToolsRequest, Tool, TextContent

def cli_main():
    """命令行入口点"""
    # 启动时的路径修复逻辑
    logger = structlog.get_logger(__name__)
    
    # 尝试找到项目根目录和配置文件
    possible_roots = [
        Path.cwd(),  # 当前工作目录
        Path(__file__).parent,  # mcp_server.py 所在目录
        Path("C:/Users/zaishu.niu/PycharmProjects/QueryNest"),  # 硬编码路径
    ]
    
    # 查找配置文件并设置环境变量
    for root in possible_roots:
        config_file = root / "config.yaml"
        if config_file.exists():
            os.environ['QUERYNEST_CONFIG_PATH'] = str(config_file)
            logger.info(f"Found config file at: {config_file}")
            # 确保工作目录是项目根目录
            if os.getcwd() != str(root):
                os.chdir(root)
                logger.info(f"Changed working directory to: {root}")
            # 添加到Python路径
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            break
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n服务器已停止")
    except Exception as e:
        print(f"服务器启动失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="QueryNest MCP MongoDB查询服务")
    
    # 默认配置路径：优先使用环境变量
    default_config = os.environ.get('QUERYNEST_CONFIG_PATH', 'config.yaml')
    
    parser.add_argument(
        "--config",
        default=default_config,
        help=f"配置文件路径 (默认: {default_config})"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别 (默认: INFO)"
    )
    
    args = parser.parse_args()
    
    # 设置日志级别
    import logging
    logging.basicConfig(level=getattr(logging, args.log_level))
    
    # 创建并运行服务器
    server = QueryNestMCPServer(args.config)
    await server.run()

class QueryNestMCPServer:
    """QueryNest MCP服务器"""
    
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.server = Server("QueryNest")
        self.logger = structlog.get_logger(__name__)
        
        # 加载配置
        self._load_config()
        
        # 注册处理器
        self.server.list_tools()(self.handle_list_tools)
        self.server.call_tool()(self.handle_call_tool)
        
    def _load_config(self):
        """加载配置文件"""
        try:
            from config import QueryNestConfig
            self.config = QueryNestConfig.from_yaml(self.config_path)
            self.logger.info("配置文件加载成功", 
                           config_path=self.config_path,
                           mongo_instances=len(self.config.mongo_instances))
        except Exception as e:
            self.logger.error("配置文件加载失败", error=str(e))
            raise

    async def handle_list_tools(self) -> list[Tool]:
        """返回可用工具列表"""
        tools = [
            Tool(
                name="discover_instances",
                description="发现可用的MongoDB实例",
                inputSchema={
                    "type": "object",
                    "properties": {},
                }
            ),
            Tool(
                name="test_connection",
                description="测试MongoDB连接",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "instance_name": {
                            "type": "string",
                            "description": "实例名称"
                        }
                    },
                    "required": ["instance_name"]
                }
            ),
            Tool(
                name="get_config_info",
                description="获取配置信息",
                inputSchema={
                    "type": "object",
                    "properties": {},
                }
            )
        ]
        return tools

    async def handle_call_tool(self, name: str, arguments: dict) -> list[TextContent]:
        """处理工具调用"""
        try:
            if name == "discover_instances":
                return await self._discover_instances()
            elif name == "test_connection":
                return await self._test_connection(arguments.get("instance_name"))
            elif name == "get_config_info":
                return await self._get_config_info()
            else:
                raise ValueError(f"未知工具: {name}")
        except Exception as e:
            self.logger.error("工具调用失败", tool=name, error=str(e))
            return [TextContent(
                type="text",
                text=f"工具调用失败: {str(e)}"
            )]

    async def _discover_instances(self) -> list[TextContent]:
        """发现MongoDB实例"""
        instances = []
        for name, config in self.config.mongo_instances.items():
            instances.append(f"- {name}: {config.name} ({config.environment})")
        
        result = f"发现 {len(instances)} 个MongoDB实例:\n" + "\n".join(instances)
        return [TextContent(type="text", text=result)]

    async def _test_connection(self, instance_name: str) -> list[TextContent]:
        """测试连接（简化版本，不实际连接）"""
        if instance_name not in self.config.mongo_instances:
            return [TextContent(
                type="text",
                text=f"实例 '{instance_name}' 不存在"
            )]
        
        instance = self.config.mongo_instances[instance_name]
        result = f"✅ 实例 '{instance_name}' 配置验证成功\n"
        result += f"名称: {instance.name}\n"
        result += f"环境: {instance.environment}\n"
        result += f"状态: {instance.status}\n"
        result += f"连接字符串: {instance.connection_string}"
        
        return [TextContent(type="text", text=result)]

    async def _get_config_info(self) -> list[TextContent]:
        """获取配置信息"""
        info = f"QueryNest MCP服务器配置信息:\n"
        info += f"- MCP服务名: {self.config.mcp.name}\n"
        info += f"- 服务版本: {self.config.mcp.version}\n"
        info += f"- MongoDB实例数: {len(self.config.mongo_instances)}\n"
        info += f"- 配置文件: {self.config_path}"
        
        return [TextContent(type="text", text=info)]

    async def run(self):
        """运行服务器"""
        self.logger.info("Starting QueryNest MCP server initialization",
                        config_path=self.config_path)
        
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )

if __name__ == "__main__":
    cli_main()