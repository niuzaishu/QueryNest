# -*- coding: utf-8 -*-
"""数据库选择工具"""

from typing import Dict, List, Any, Optional
import structlog
from mcp.types import Tool, TextContent

from database.connection_manager import ConnectionManager
from database.metadata_manager import MetadataManager
from utils.parameter_validator import (
    ParameterValidator, MCPParameterHelper, ValidationResult,
    is_non_empty_string, is_valid_instance_id, validate_instance_exists
)
from utils.tool_context import get_context_manager, ToolExecutionContext
from utils.error_handler import with_error_handling, with_retry, RetryConfig
from utils.workflow_manager import get_workflow_manager, WorkflowStage


logger = structlog.get_logger(__name__)


class DatabaseSelectionTool:
    """数据库选择工具"""
    
    def __init__(self, connection_manager: ConnectionManager, metadata_manager: MetadataManager):
        self.connection_manager = connection_manager
        self.metadata_manager = metadata_manager
        self.context_manager = get_context_manager()
        self.workflow_manager = get_workflow_manager()
        self.validator = self._setup_validator()
    
    def get_tool_definition(self) -> Tool:
        """获取工具定义"""
        return Tool(
            name="select_database",
            description="选择要查询的数据库，并推进工作流到下一阶段",
            inputSchema={
                "type": "object",
                "properties": {
                    "instance_id": {
                        "type": "string",
                        "description": "MongoDB实例ID"
                    },
                    "database_name": {
                        "type": "string",
                        "description": "要选择的数据库名称"
                    },
                    "session_id": {
                        "type": "string",
                        "description": "会话标识符，默认为'default'",
                        "default": "default"
                    }
                },
                "required": ["instance_id", "database_name"]
            }
        )
    
    def _setup_validator(self) -> ParameterValidator:
        """设置参数验证器"""
        validator = ParameterValidator()
        
        async def get_instance_options():
            """获取可用实例选项"""
            try:
                instances = await self.connection_manager.get_all_instances()
                options = []
                for instance_id, instance_config in instances.items():
                    options.append({
                        'value': instance_id,
                        'display_name': instance_id,
                        'description': f"{instance_config.environment} 环境 - {instance_config.description or '无描述'}",
                        'extra_info': f"状态: {instance_config.status}"
                    })
                return options
            except Exception as e:
                logger.warning("获取实例选项失败", error=str(e))
                return []
        
        async def get_database_options(instance_id: str):
            """获取指定实例的数据库选项"""
            try:
                if not self.connection_manager.has_instance(instance_id):
                    return []
                
                # 获取数据库列表
                databases = await self._get_databases(instance_id)
                options = []
                for db_info in databases:
                    db_name = db_info["database_name"]
                    options.append({
                        'value': db_name,
                        'display_name': db_name,
                        'description': db_info.get('description', '无描述'),
                        'extra_info': f"集合数量: {db_info.get('collection_count', '未知')}"
                    })
                return options
            except Exception as e:
                logger.warning("获取数据库选项失败", error=str(e))
                return []
        
        validator.add_required_parameter(
            name="instance_id",
            type_check=lambda x: is_non_empty_string(x) and is_valid_instance_id(x),
            validator=lambda x, ctx: validate_instance_exists(x, ctx.connection_manager),
            options_provider=get_instance_options,
            description="MongoDB实例名称",
            user_friendly_name="MongoDB实例"
        )
        
        validator.add_required_parameter(
            name="database_name",
            type_check=is_non_empty_string,
            validator=self._validate_database_exists,
            options_provider=lambda: get_database_options("local_test"),  # 默认实例
            description="要选择的数据库名称",
            user_friendly_name="数据库名称"
        )
        
        return validator
    
    async def _validate_database_exists(self, database_name: str, context: ToolExecutionContext) -> bool:
        """验证数据库是否存在"""
        try:
            # 从上下文获取instance_id
            instance_id = context.get_parameter("instance_id")
            if not instance_id:
                # 如果无法从上下文获取，尝试从工作流状态获取
                workflow_manager = get_workflow_manager()
                workflow_state = workflow_manager.get_current_state()
                instance_id = workflow_state.get("selected_instance")
                if not instance_id:
                    logger.warning("无法获取instance_id进行数据库验证")
                    return True  # 暂时跳过验证，让后续执行时处理
            
            if not self.connection_manager.has_instance(instance_id):
                return False
            
            # 获取数据库列表
            databases = await self._get_databases(instance_id)
            db_names = [db["database_name"] for db in databases]
            return database_name in db_names
            
        except Exception as e:
            logger.warning("验证数据库存在性失败", error=str(e))
            return True  # 验证失败时暂时跳过，让后续执行时处理
    
    @with_retry(RetryConfig(max_attempts=3, base_delay=1.0))
    async def _get_databases(self, instance_id: str, filter_system: bool = True) -> List[Dict[str, Any]]:
        """获取数据库列表"""
        try:
            client = await self.connection_manager.get_client(instance_id)
            db_names = await client.list_database_names()
            
            # 过滤系统数据库
            if filter_system:
                system_dbs = {'admin', 'local', 'config'}
                db_names = [name for name in db_names if name not in system_dbs]
            
            databases = []
            for db_name in db_names:
                db_info = {
                    "database_name": db_name,
                    "description": f"数据库 {db_name}"
                }
                
                # 获取集合数量
                try:
                    db = client[db_name]
                    collections = await db.list_collection_names()
                    db_info["collection_count"] = len(collections)
                except Exception as e:
                    logger.warning(f"获取数据库 {db_name} 集合信息失败", error=str(e))
                    db_info["collection_count"] = 0
                
                databases.append(db_info)
            
            return databases
            
        except Exception as e:
            logger.error(f"获取实例 {instance_id} 数据库列表失败", error=str(e))
            raise
    
    @with_error_handling("数据库选择")
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """执行数据库选择"""
        # 参数验证
        context = self.context_manager.get_or_create_context()
        context.connection_manager = self.connection_manager
        
        validation_result, errors = await self.validator.validate_parameters(arguments, context)
        
        if validation_result != ValidationResult.VALID:
            return MCPParameterHelper.create_error_response(errors)
        
        instance_id = arguments["instance_id"]
        database_name = arguments["database_name"]
        session_id = arguments.get("session_id", "default")
        
        logger.info(
            "开始选择数据库",
            instance_id=instance_id,
            database_name=database_name,
            session_id=session_id
        )
        
        # 验证实例是否存在
        if not self.connection_manager.has_instance(instance_id):
            return [TextContent(
                type="text",
                text=f"实例 '{instance_id}' 不存在。请使用 discover_instances 工具查看可用实例。"
            )]
        
        # 检查实例健康状态
        health_status = await self.connection_manager.check_instance_health(instance_id)
        if not health_status["healthy"]:
            return [TextContent(
                type="text",
                text=f"实例 '{instance_id}' 不健康: {health_status.get('error', 'Unknown error')}"
            )]
        
        # 验证数据库是否存在
        databases = await self._get_databases(instance_id)
        db_names = [db["database_name"] for db in databases]
        
        if database_name not in db_names:
            available_dbs = ", ".join(db_names[:5])  # 显示前5个数据库
            return [TextContent(
                type="text",
                text=f"数据库 '{database_name}' 在实例 '{instance_id}' 中不存在。\n可用数据库: {available_dbs}"
            )]
        
        # 获取数据库详细信息
        selected_db = next((db for db in databases if db["database_name"] == database_name), None)
        
        # 更新工作流状态
        success, message = self.workflow_manager.transition_to(
            session_id=session_id,
            target_stage=WorkflowStage.DATABASE_SELECTION,
            update_data={
                "instance_id": instance_id,
                "database_name": database_name
            }
        )
        
        if not success:
            return [TextContent(
                type="text",
                text=f"工作流转换失败: {message}"
            )]
        
        # 记录到上下文
        context.add_to_chain("select_database", arguments)
        self.context_manager.update_context(
            instance_id=instance_id,
            database_name=database_name
        )
        
        # 构建响应
        result_text = "## ✅ 数据库选择成功\n\n"
        result_text += f"**选择的数据库**: {database_name}\n"
        result_text += f"**所属实例**: {instance_id}\n"
        
        if selected_db:
            result_text += f"**集合数量**: {selected_db.get('collection_count', '未知')}\n"
        
        result_text += f"\n**工作流状态**: 已转换到 database_selection 阶段\n\n"
        
        result_text += "## 下一步操作\n\n"
        result_text += "现在可以使用以下工具继续查询流程:\n"
        result_text += f"- `analyze_collection` - 分析数据库 '{database_name}' 中的集合结构\n"
        result_text += f"- `discover_collections` - 发现数据库 '{database_name}' 中的集合\n"
        result_text += "- `workflow_status` - 查看当前工作流状态\n\n"
        
        # 获取下一步建议
        suggestions = self.workflow_manager.get_next_stage_suggestions(session_id)
        if suggestions:
            result_text += "\n---\n\n## 🎯 下一步建议\n\n"
            for i, suggestion in enumerate(suggestions, 1):
                result_text += f"{i}. **{suggestion['name']}**: {suggestion['description']}\n"
        
        result_text += "\n💡 *提示: 使用 `workflow_status` 查看完整工作流状态*"
        
        return [TextContent(type="text", text=result_text)]