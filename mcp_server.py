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
    InstanceSelectionTool,
    DatabaseSelectionTool,
    DatabaseDiscoveryTool,
    CollectionAnalysisTool,
    QueryGenerationTool,
    QueryConfirmationTool,
    # FeedbackTools,  # 已移除
    WorkflowStatusTool,
    WorkflowResetTool,
)
from mcp_tools.unified_semantic_tool import UnifiedSemanticTool
from utils.workflow_wrapper import WorkflowConstrainedTool


# 配置日志 - 初步配置，将在initialize方法中根据配置文件进一步设置
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
    
    def _setup_file_logging(self, config: QueryNestConfig):
        """设置文件日志输出"""
        import logging
        import logging.handlers
        from pathlib import Path
        import yaml
        
        try:
            # 尝试从原始配置数据中读取日志配置
            config_data = {}
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config_data = yaml.safe_load(f)
            except Exception:
                logger.warning("无法读取配置文件，使用默认日志配置")
                return
            
            logging_config = config_data.get('logging', {})
            output_config = logging_config.get('output', {})
            file_config = output_config.get('file', {})
            
            # 检查是否启用文件日志
            if not file_config.get('enabled', False):
                logger.info("文件日志未启用")
                return
            
            # 创建日志目录
            log_path_str = file_config.get('path', 'logs/querynest.log')
            log_path = Path(log_path_str)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 获取根日志记录器
            root_logger = logging.getLogger()
            
            # 设置日志级别
            log_level_str = logging_config.get('level', 'INFO')
            log_level = getattr(logging, log_level_str.upper(), logging.INFO)
            root_logger.setLevel(log_level)
            
            # 检查是否已有文件处理器
            has_file_handler = any(
                isinstance(handler, logging.handlers.RotatingFileHandler) 
                for handler in root_logger.handlers
            )
            
            if not has_file_handler:
                # 创建文件处理器
                max_size_str = file_config.get('max_size', '100MB')
                max_size_bytes = self._parse_size(max_size_str)
                backup_count = file_config.get('backup_count', 5)
                
                file_handler = logging.handlers.RotatingFileHandler(
                    filename=str(log_path),
                    maxBytes=max_size_bytes,
                    backupCount=backup_count,
                    encoding='utf-8'
                )
                
                # 设置文件处理器级别
                file_log_level_str = file_config.get('level', 'DEBUG')
                file_log_level = getattr(logging, file_log_level_str.upper(), logging.DEBUG)
                file_handler.setLevel(file_log_level)
                
                # 创建格式化器
                log_format = logging_config.get('format', 'json')
                if log_format == "json":
                    # JSON格式 - 使用structlog的JSON格式化器
                    formatter = logging.Formatter('%(message)s')
                else:
                    # 文本格式
                    formatter = logging.Formatter(
                        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S'
                    )
                
                file_handler.setFormatter(formatter)
                root_logger.addHandler(file_handler)
                
                logger.info(
                    "文件日志配置完成", 
                    log_path=str(log_path), 
                    level=file_log_level_str,
                    max_size=max_size_str,
                    backup_count=backup_count
                )
                
        except Exception as e:
            logger.warning("文件日志配置失败", error=str(e))
    
    def _parse_size(self, size_str: str) -> int:
        """解析大小字符串为字节数"""
        size_str = size_str.upper()
        if size_str.endswith('KB'):
            return int(size_str[:-2]) * 1024
        elif size_str.endswith('MB'):
            return int(size_str[:-2]) * 1024 * 1024
        elif size_str.endswith('GB'):
            return int(size_str[:-2]) * 1024 * 1024 * 1024
        else:
            try:
                return int(size_str)
            except ValueError:
                return 100 * 1024 * 1024  # 默认100MB
    
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
            
            # 设置文件日志
            self._setup_file_logging(self.config)
            
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
            self.semantic_analyzer = SemanticAnalyzer(self.metadata_manager, self.connection_manager)
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
        """初始化MCP工具（带工作流约束）"""
        # 创建原始工具实例
        instance_discovery = InstanceDiscoveryTool(self.connection_manager, self.metadata_manager)
        instance_selection = InstanceSelectionTool(self.connection_manager, self.metadata_manager)
        database_selection = DatabaseSelectionTool(self.connection_manager, self.metadata_manager)
        database_discovery = DatabaseDiscoveryTool(self.connection_manager, self.metadata_manager)
        collection_analysis = CollectionAnalysisTool(
            self.connection_manager, self.metadata_manager, self.semantic_analyzer
        )
        # 统一语义工具（替换原有的多个语义工具）
        unified_semantic = UnifiedSemanticTool(
            self.connection_manager, self.metadata_manager, self.semantic_analyzer
        )
        query_generation = QueryGenerationTool(
            self.connection_manager, self.metadata_manager, self.semantic_analyzer
        )
        query_confirmation = QueryConfirmationTool(
            self.connection_manager, self.metadata_manager, self.query_engine
        )
        # feedback_tool = FeedbackTools(self.metadata_manager)  # 已移除
        
        # 工作流管理工具
        workflow_status = WorkflowStatusTool()
        workflow_reset = WorkflowResetTool()
        
        # 包装主要工具以添加工作流约束
        self.tools["discover_instances"] = WorkflowConstrainedTool(
            instance_discovery, "discover_instances"
        )
        self.tools["select_instance"] = WorkflowConstrainedTool(
            instance_selection, "select_instance"
        )
        self.tools["select_database"] = WorkflowConstrainedTool(
            database_selection, "select_database"
        )
        self.tools["discover_databases"] = WorkflowConstrainedTool(
            database_discovery, "discover_databases"
        )
        self.tools["analyze_collection"] = WorkflowConstrainedTool(
            collection_analysis, "analyze_collection"
        )
        self.tools["generate_query"] = WorkflowConstrainedTool(
            query_generation, "generate_query"
        )
        self.tools["confirm_query"] = WorkflowConstrainedTool(
            query_confirmation, "confirm_query"
        )
        
        # 工具链管理和状态工具（不需要包装）
        self.tools["workflow_status"] = workflow_status
        self.tools["workflow_reset"] = workflow_reset
        
        # 统一语义操作工具（替换原有的多个分散的语义工具）
        self.tools["unified_semantic_operations"] = unified_semantic
        
        # 反馈工具（保持原样）
        # 反馈工具已移除
        # self.tools["submit_feedback"] = feedback_tool
        # self.tools["get_feedback_status"] = feedback_tool
        # self.tools["get_help_content"] = feedback_tool
        # self.tools["get_faq"] = feedback_tool
        # self.tools["search_help"] = feedback_tool
        # self.tools["get_feedback_summary"] = feedback_tool
    
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
                
                # 检查是否为工作流包装的工具
                if isinstance(tool_instance, WorkflowConstrainedTool):
                    # 工作流包装工具需要session_id
                    session_id = arguments.get("session_id", "default")
                    result = await tool_instance.execute(arguments, session_id)
                else:
                    # 普通工具
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
    
    # 默认配置路径：优先使用环境变量
    import os
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


def cli_main():
    """命令行入口点"""
    # 启动时的路径修复逻辑
    import os
    from pathlib import Path
    
    # 获取logger
    logger = structlog.get_logger(__name__)
    
    # 尝试找到项目根目录和配置文件
    possible_roots = [
        Path.cwd(),  # 当前工作目录
        Path(__file__).parent,  # mcp_server.py 所在目录
        Path("C:/my/QueryNest"),  # 更新的项目路径
        Path("C:/Users/zaishu.niu/PycharmProjects/QueryNest"),  # 原路径作为后备
    ]
    
    # 查找配置文件并设置环境变量
    config_found = False
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
                logger.info(f"Added to Python path: {root}")
            config_found = True
            break
    
    # 如果没有找到配置文件，但用户可能通过命令行参数或环境变量指定了路径
    if not config_found:
        custom_config = os.environ.get('QUERYNEST_CONFIG_PATH')
        if custom_config and Path(custom_config).exists():
            logger.info(f"Using custom config from environment: {custom_config}")
            config_found = True
        else:
            logger.warning("Config file not found in standard locations. Will attempt to use command line arguments or environment variables.")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n服务器已停止")
    except Exception as e:
        print(f"服务器启动失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    cli_main()