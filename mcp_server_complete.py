# -*- coding: utf-8 -*-
"""QueryNest MCP服务器 - 完整版本"""

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
    import logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    
    # 配置structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(ensure_ascii=False)
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
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
    """QueryNest MCP服务器 - 完整功能版本"""
    
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.server = Server("QueryNest")
        self.logger = structlog.get_logger(__name__)
        
        # 加载配置
        self._load_config()
        
        # 初始化组件
        self._initialize_components()
        
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
    
    def _initialize_components(self):
        """初始化各个组件"""
        try:
            # 延迟导入以避免构建时的循环依赖
            self.tools = {}
            
            # 初始化基础工具（不需要MongoDB连接的）
            self._initialize_basic_tools()
            
            # 尝试初始化数据库相关工具
            self._initialize_database_tools()
            
            # 尝试初始化MCP工具
            self._initialize_mcp_tools()
            
        except Exception as e:
            self.logger.warning("部分组件初始化失败，将使用基础功能", error=str(e))
    
    def _initialize_basic_tools(self):
        """初始化基础工具"""
        self.tools["discover_instances"] = self._discover_instances
        self.tools["get_config_info"] = self._get_config_info
        
    def _initialize_database_tools(self):
        """初始化数据库相关工具"""
        try:
            from database.connection_manager import ConnectionManager
            from database.metadata_manager import MetadataManager  
            from database.query_engine import QueryEngine
            
            self.connection_manager = ConnectionManager(self.config)
            self.metadata_manager = MetadataManager(self.connection_manager)
            # QueryEngine需要三个参数：connection_manager, metadata_manager, config
            self.query_engine = QueryEngine(self.connection_manager, self.metadata_manager, self.config)
            
            # 添加数据库工具
            self.tools["test_connection"] = self._test_connection_real
            self.tools["list_databases"] = self._list_databases
            self.tools["list_collections"] = self._list_collections
            
            self.logger.info("数据库组件初始化成功")
            
        except Exception as e:
            self.logger.warning("数据库组件初始化失败，使用模拟功能", error=str(e))
            import traceback
            self.logger.debug("详细错误信息", traceback=traceback.format_exc())
            self.tools["test_connection"] = self._test_connection_mock
    
    def _initialize_mcp_tools(self):
        """初始化MCP工具"""
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
            from scanner.semantic_analyzer import SemanticAnalyzer
            from scanner.structure_scanner import StructureScanner
            
            # 需要先初始化scanner组件
            structure_scanner = StructureScanner(self.connection_manager, self.metadata_manager, self.config)
            semantic_analyzer = SemanticAnalyzer(self.connection_manager, self.metadata_manager, self.config)
            
            # 创建工具实例 - 使用正确的构造函数参数
            self.mcp_tools = {}
            
            # 基础发现工具
            self.mcp_tools["discover_instances"] = InstanceDiscoveryTool(self.connection_manager, self.config)
            self.mcp_tools["discover_databases"] = DatabaseDiscoveryTool(self.connection_manager, self.config)
            
            # 需要metadata_manager的工具
            if hasattr(self, 'metadata_manager'):
                self.mcp_tools["analyze_collection"] = CollectionAnalysisTool(
                    self.connection_manager, self.metadata_manager, structure_scanner, self.config)
                self.mcp_tools["manage_semantics"] = SemanticManagementTool(
                    self.connection_manager, self.metadata_manager, semantic_analyzer)
                self.mcp_tools["semantic_completion"] = SemanticCompletionTool(
                    self.metadata_manager, semantic_analyzer, self.config)
                self.mcp_tools["collect_feedback"] = FeedbackTools(self.metadata_manager, self.config)
            
            # 需要query_engine的工具
            if hasattr(self, 'query_engine'):
                self.mcp_tools["generate_query"] = QueryGenerationTool(
                    self.query_engine, self.metadata_manager, semantic_analyzer, self.config)
                self.mcp_tools["confirm_query"] = QueryConfirmationTool(self.query_engine, self.config)
            
            self.logger.info("MCP工具初始化成功", tool_count=len(self.mcp_tools))
            
        except Exception as e:
            self.logger.warning("MCP工具初始化失败", error=str(e))
            import traceback
            self.logger.debug("详细错误信息", traceback=traceback.format_exc())
            self.mcp_tools = {}

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
                name="get_config_info", 
                description="获取配置信息",
                inputSchema={
                    "type": "object",
                    "properties": {},
                }
            )
        ]
        
        # 添加数据库工具
        if "test_connection" in self.tools:
            tools.append(Tool(
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
            ))
        
        if "list_databases" in self.tools:
            tools.append(Tool(
                name="list_databases",
                description="列出数据库",
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
            ))
        
        # 添加MCP工具定义
        for tool_name, tool_instance in self.mcp_tools.items():
            try:
                tool_def = tool_instance.get_tool_definition()
                tools.append(tool_def)
            except Exception as e:
                self.logger.warning(f"获取工具定义失败: {tool_name}", error=str(e))
        
        return tools

    async def handle_call_tool(self, name: str, arguments: dict) -> list[TextContent]:
        """处理工具调用"""
        try:
            # 处理基础工具
            if name in self.tools:
                if name in ["discover_instances", "get_config_info"]:
                    return await self.tools[name]()
                else:
                    return await self.tools[name](arguments)
            
            # 处理MCP工具
            if name in self.mcp_tools:
                result = await self.mcp_tools[name].execute(arguments)
                if isinstance(result, list):
                    return result
                else:
                    return [TextContent(type="text", text=str(result))]
            
            raise ValueError(f"未知工具: {name}")
            
        except Exception as e:
            self.logger.error("工具调用失败", tool=name, error=str(e))
            import traceback
            error_details = traceback.format_exc()
            return [TextContent(
                type="text",
                text=f"工具调用失败: {str(e)}\n\n详细错误:\n{error_details}"
            )]

    async def _discover_instances(self) -> list[TextContent]:
        """发现MongoDB实例"""
        instances = []
        for name, config in self.config.mongo_instances.items():
            instances.append(f"- {name}: {config.name} ({config.environment})")
        
        result = f"发现 {len(instances)} 个MongoDB实例:\n" + "\n".join(instances)
        return [TextContent(type="text", text=result)]

    async def _get_config_info(self) -> list[TextContent]:
        """获取配置信息"""
        info = f"QueryNest MCP服务器配置信息:\n"
        info += f"- MCP服务名: {self.config.mcp.name}\n"
        info += f"- 服务版本: {self.config.mcp.version}\n" 
        info += f"- MongoDB实例数: {len(self.config.mongo_instances)}\n"
        info += f"- 配置文件: {self.config_path}\n"
        info += f"- 可用工具数: {len(self.tools) + len(self.mcp_tools)}"
        
        return [TextContent(type="text", text=info)]

    async def _test_connection_mock(self, arguments: dict) -> list[TextContent]:
        """测试连接（模拟版本）"""
        instance_name = arguments.get("instance_name")
        if instance_name not in self.config.mongo_instances:
            return [TextContent(
                type="text",
                text=f"实例 '{instance_name}' 不存在"
            )]
        
        instance = self.config.mongo_instances[instance_name]
        result = f"✅ 实例 '{instance_name}' 配置验证成功（模拟模式）\n"
        result += f"名称: {instance.name}\n"
        result += f"环境: {instance.environment}\n"
        result += f"状态: {instance.status}\n"
        result += f"连接字符串: {instance.connection_string}"
        
        return [TextContent(type="text", text=result)]

    async def _test_connection_real(self, arguments: dict) -> list[TextContent]:
        """测试连接（真实版本）"""
        instance_name = arguments.get("instance_name")
        try:
            health = await self.connection_manager.check_instance_health(instance_name)
            
            if health["status"] == "healthy":
                result = f"✅ 实例 '{instance_name}' 连接成功\n"
                result += f"响应时间: {health.get('response_time', 'N/A')}ms\n"
                result += f"MongoDB版本: {health.get('version', 'N/A')}\n"
                result += f"最后检查时间: {health.get('last_check', 'N/A')}"
            else:
                result = f"❌ 实例 '{instance_name}' 连接失败\n"
                result += f"错误: {health.get('error', 'Unknown error')}"
            
            return [TextContent(type="text", text=result)]
            
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"连接测试失败: {str(e)}"
            )]

    async def _list_databases(self, arguments: dict) -> list[TextContent]:
        """列出数据库"""
        instance_name = arguments.get("instance_name")
        try:
            databases = await self.connection_manager.list_databases(instance_name)
            
            result = f"实例 '{instance_name}' 的数据库列表:\n"
            for db in databases:
                result += f"- {db['name']} ({db.get('sizeOnDisk', 'N/A')} bytes)\n"
            
            return [TextContent(type="text", text=result)]
            
        except Exception as e:
            return [TextContent(
                type="text", 
                text=f"获取数据库列表失败: {str(e)}"
            )]

    async def run(self):
        """运行服务器"""
        self.logger.info("Starting QueryNest MCP server initialization",
                        config_path=self.config_path,
                        tools_count=len(self.tools) + len(self.mcp_tools))
        
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )

if __name__ == "__main__":
    cli_main()