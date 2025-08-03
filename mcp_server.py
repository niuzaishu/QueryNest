# -*- coding: utf-8 -*-
"""QueryNest MCP服务器"""

import asyncio
import sys
from typing import Any, Sequence
import structlog
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequest,
    ListToolsRequest,
    Tool,
    TextContent,
)

from config import QueryNestConfig
from database.connection_manager import ConnectionManager
from database.metadata_manager import MetadataManager
from database.query_engine import QueryEngine
from scanner.structure_scanner import StructureScanner
from scanner.semantic_analyzer import SemanticAnalyzer
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


# 配置日志
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


class QueryNestMCPServer:
    """QueryNest MCP服务器"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.config = None
        self.connection_manager = None
        self.metadata_manager = None
        self.query_engine = None
        self.structure_scanner = None
        self.semantic_analyzer = None
        
        # MCP工具
        self.tools = {}
        
        # MCP服务器
        self.server = Server("querynest")
        
        # 注册MCP处理器
        self._register_handlers()
    
    async def initialize(self):
        """初始化服务器"""
        try:
            logger.info("Starting QueryNest MCP server initialization", config_path=self.config_path)
            
            # 加载配置
            self.config = QueryNestConfig.from_yaml(self.config_path)
            logger.info("Configuration loaded successfully", instances_count=len(self.config.mongo_instances))
            
            # 初始化连接管理器
            self.connection_manager = ConnectionManager(self.config)
            await self.connection_manager.initialize()
            logger.info("Connection manager initialized successfully")
            
            # 初始化元数据管理器
            self.metadata_manager = MetadataManager(self.connection_manager)
            await self.metadata_manager.initialize()
            logger.info("Metadata manager initialized successfully")
            
            # 初始化查询引擎
            self.query_engine = QueryEngine(self.connection_manager, self.metadata_manager, self.config)
            logger.info("Query engine initialized successfully")
            
            # 初始化结构扫描器
            self.structure_scanner = StructureScanner(self.connection_manager, self.metadata_manager, self.config)
            logger.info("Structure scanner initialized successfully")
            
            # 初始化语义分析器
            self.semantic_analyzer = SemanticAnalyzer(self.metadata_manager)
            logger.info("Semantic analyzer initialized successfully")
            
            # 初始化MCP工具
            await self._initialize_tools()
            logger.info("MCP tools initialized successfully", tools_count=len(self.tools))
            
            # 健康检查功能暂时禁用
            # asyncio.create_task(self.connection_manager.start_health_check_loop())
            logger.info("Health check loop started")
            
            logger.info("QueryNest MCP server initialization completed")
            
        except Exception as e:
            logger.error("Server initialization failed", error=str(e))
            raise
    
    async def _initialize_tools(self):
        """初始化MCP工具"""
        # 实例发现工具
        instance_discovery = InstanceDiscoveryTool(self.connection_manager, self.metadata_manager)
        self.tools["discover_instances"] = instance_discovery
        
        # 数据库发现工具
        database_discovery = DatabaseDiscoveryTool(self.connection_manager, self.metadata_manager)
        self.tools["discover_databases"] = database_discovery
        
        # 集合分析工具
        collection_analysis = CollectionAnalysisTool(
            self.connection_manager, self.metadata_manager, self.semantic_analyzer
        )
        self.tools["analyze_collection"] = collection_analysis
        
        # 语义管理工具
        semantic_management = SemanticManagementTool(
            self.connection_manager, self.metadata_manager, self.semantic_analyzer
        )
        self.tools["manage_semantics"] = semantic_management
        
        # 语义补全工具
        semantic_completion = SemanticCompletionTool(
            self.connection_manager, self.metadata_manager, self.semantic_analyzer
        )
        self.tools["semantic_completion"] = semantic_completion
        
        # 查询生成工具
        query_generation = QueryGenerationTool(
            self.connection_manager, self.metadata_manager, self.semantic_analyzer
        )
        self.tools["generate_query"] = query_generation
        
        # 查询确认工具
        query_confirmation = QueryConfirmationTool(
            self.connection_manager, self.metadata_manager, self.query_engine
        )
        self.tools["confirm_query"] = query_confirmation
        
        # 反馈工具
        feedback_tool = FeedbackTools(self.metadata_manager)
        self.tools["submit_feedback"] = feedback_tool
        self.tools["get_feedback_status"] = feedback_tool
        self.tools["get_help_content"] = feedback_tool
        self.tools["get_faq"] = feedback_tool
        self.tools["search_help"] = feedback_tool
        self.tools["get_feedback_summary"] = feedback_tool
    
    def _register_handlers(self):
        """注册MCP处理器"""
        
        @self.server.list_tools()
        async def handle_list_tools() -> list[Tool]:
            """列出所有可用工具"""
            tools = []
            for tool_name, tool_instance in self.tools.items():
                try:
                    tool_def = tool_instance.get_tool_definition()
                    tools.append(tool_def)
                except Exception as e:
                    logger.error(f"获取工具定义失败", tool_name=tool_name, error=str(e))
            
            logger.info("列出工具", tools_count=len(tools))
            return tools
        
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
            """调用工具"""
            if arguments is None:
                arguments = {}
            
            logger.info("调用工具", tool_name=name, arguments=arguments)
            
            try:
                if name not in self.tools:
                    raise ValueError(f"未知工具: {name}")
                
                tool_instance = self.tools[name]
                result = await tool_instance.execute(arguments)
                
                logger.info("工具调用完成", tool_name=name, result_count=len(result))
                return result
                
            except Exception as e:
                logger.error("工具调用失败", tool_name=name, error=str(e))
                raise ValueError(f"工具执行失败: {str(e)}")
    
    async def cleanup(self):
        """清理资源"""
        try:
            logger.info("Starting resource cleanup")
            
            if self.connection_manager:
                await self.connection_manager.shutdown()
                logger.info("Connection manager closed")
            
            logger.info("Resource cleanup completed")
            
        except Exception as e:
            logger.error("清理资源失败", error=str(e))
    
    async def run(self):
        """运行MCP服务器"""
        try:
            # 初始化服务器
            await self.initialize()
            
            # 检查传输方式配置
            import os
            transport = os.getenv('QUERYNEST_MCP_TRANSPORT', 'stdio')
            
            if transport.lower() == 'http':
                # HTTP传输模式
                host = os.getenv('QUERYNEST_MCP_HOST', '0.0.0.0')
                port = int(os.getenv('QUERYNEST_MCP_PORT', '8000'))
                logger.info(f"启动HTTP MCP服务器: {host}:{port}")
                
                # 注意：这里需要根据实际的MCP HTTP实现来调整
                # 当前示例假设存在HTTP传输支持
                raise NotImplementedError("HTTP传输模式尚未实现")
            else:
                # 默认使用stdio传输
                logger.info("Starting stdio MCP server")
                
                async with stdio_server() as (read_stream, write_stream):
                    await self.server.run(
                        read_stream,
                        write_stream,
                        InitializationOptions(
                            server_name="querynest",
                            server_version="1.0.0",
                            capabilities=self.server.get_capabilities(
                                notification_options=NotificationOptions(),
                                experimental_capabilities={}
                            )
                        )
                    )
                
        except KeyboardInterrupt:
            logger.info("Received interrupt signal, shutting down server")
        except Exception as e:
            logger.error("Server execution failed", error=str(e))
            raise
        finally:
            await self.cleanup()


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="QueryNest MCP MongoDB查询服务")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="配置文件路径 (默认: config.yaml)"
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


def cli_main():
    """命令行入口点"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n服务器已停止")
    except Exception as e:
        print(f"服务器启动失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    cli_main()