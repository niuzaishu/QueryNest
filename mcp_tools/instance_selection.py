# -*- coding: utf-8 -*-
"""实例选择工具"""

from typing import Dict, List, Any, Optional
import structlog
from mcp.types import Tool, TextContent

from database.connection_manager import ConnectionManager
from database.metadata_manager import MetadataManager
from utils.parameter_validator import (
    ParameterValidator, MCPParameterHelper, ValidationResult,
    is_string
)
from utils.tool_context import get_context_manager, ToolExecutionContext
from utils.error_handler import with_error_handling, with_retry, RetryConfig
from utils.workflow_manager import get_workflow_manager, WorkflowStage


logger = structlog.get_logger(__name__)


class InstanceSelectionTool:
    """实例选择工具"""
    
    def __init__(self, connection_manager: ConnectionManager, metadata_manager: MetadataManager):
        self.connection_manager = connection_manager
        self.metadata_manager = metadata_manager
        self.context_manager = get_context_manager()
        self.workflow_manager = get_workflow_manager()
        self.validator = self._setup_validator()
    
    def get_tool_definition(self) -> Tool:
        """获取工具定义"""
        return Tool(
            name="select_instance",
            description="选择要使用的MongoDB实例，并推进工作流到下一阶段",
            inputSchema={
                "type": "object",
                "properties": {
                    "instance_id": {
                        "type": "string",
                        "description": "要选择的MongoDB实例ID"
                    },
                    "session_id": {
                        "type": "string",
                        "description": "会话标识符，默认为'default'",
                        "default": "default"
                    }
                },
                "required": ["instance_id"]
            }
        )
    
    def _setup_validator(self) -> ParameterValidator:
        """设置参数验证器"""
        validator = ParameterValidator()
        
        validator.add_required_parameter(
            name="instance_id",
            type_check=is_string,
            description="要选择的MongoDB实例ID",
            user_friendly_name="实例ID"
        )
        
        validator.add_optional_parameter(
            name="session_id",
            type_check=is_string,
            description="会话标识符",
            user_friendly_name="会话ID"
        )
        
        return validator

    @with_error_handling({"component": "instance_selection", "operation": "execute"})
    @with_retry(RetryConfig(max_attempts=2, base_delay=1.0))
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """执行实例选择"""
        # 参数验证
        context = self.context_manager.get_or_create_context()
        context.connection_manager = self.connection_manager
        
        validation_result, errors = await self.validator.validate_parameters(arguments, context)
        
        if validation_result != ValidationResult.VALID:
            return MCPParameterHelper.create_error_response(errors)
        
        # 记录工具调用到上下文
        context.add_to_chain("select_instance", arguments)
        
        instance_id = arguments["instance_id"]
        session_id = arguments.get("session_id", "default")
        
        logger.info("开始选择MongoDB实例", instance_id=instance_id, session_id=session_id)
        
        try:
            # 验证实例ID是否存在
            instances = await self.connection_manager.get_all_instances()
            if instance_id not in instances:
                available_instances = list(instances.keys())
                error_msg = f"实例 '{instance_id}' 不存在。可用的实例: {', '.join(available_instances)}"
                logger.error("实例选择失败", instance_id=instance_id, available_instances=available_instances)
                return [TextContent(type="text", text=error_msg)]
            
            # 检查实例健康状态
            health_status = await self.connection_manager.check_instance_health(instance_id)
            if not health_status["healthy"]:
                warning_msg = f"⚠️ 警告: 实例 '{instance_id}' 当前不健康: {health_status.get('error', 'Unknown error')}"
                logger.warning("选择的实例不健康", instance_id=instance_id, error=health_status.get('error'))
                # 继续执行，但给出警告
            
            # 获取实例配置信息
            instance_config = instances[instance_id]
            display_name = getattr(instance_config, 'name', instance_id)
            
            # 更新工作流状态
            update_data = {
                "instance_id": instance_id,
                "selected_instance_name": display_name
            }
            
            # 尝试推进工作流到INSTANCE_SELECTION阶段
            success, message = await self.workflow_manager.transition_to(
                session_id, 
                WorkflowStage.INSTANCE_SELECTION, 
                update_data
            )
            
            if not success:
                error_msg = f"工作流推进失败: {message}"
                logger.error("工作流推进失败", session_id=session_id, error=message)
                return [TextContent(type="text", text=error_msg)]
            
            # 构建成功响应
            result_text = f"## ✅ 实例选择成功\n\n"
            result_text += f"**选择的实例**: {display_name} ({instance_id})\n"
            result_text += f"**连接字符串**: {instance_config.connection_string}\n"
            result_text += f"**环境**: {instance_config.environment}\n"
            
            if not health_status["healthy"]:
                result_text += f"**健康状态**: ❌ 不健康 - {health_status.get('error', 'Unknown error')}\n"
            else:
                result_text += f"**健康状态**: ✅ 健康\n"
                result_text += f"**延迟**: {health_status.get('latency_ms', 'N/A')}ms\n"
            
            result_text += f"\n**工作流状态**: {message}\n\n"
            
            # 添加下一步提示
            result_text += "## 下一步操作\n\n"
            result_text += "现在可以使用以下工具继续查询流程:\n"
            result_text += f"- `discover_databases` - 发现实例 '{instance_id}' 中的数据库\n"
            result_text += f"- `analyze_collection` - 分析特定集合的结构\n"
            result_text += "- `workflow_status` - 查看当前工作流状态\n"
            
            logger.info("实例选择完成", instance_id=instance_id, session_id=session_id)
            
            return [TextContent(type="text", text=result_text)]
            
        except Exception as e:
            error_msg = f"选择实例时发生错误: {str(e)}"
            logger.error("实例选择失败", instance_id=instance_id, error=str(e))
            return [TextContent(type="text", text=error_msg)]
    
    async def get_available_instances(self) -> List[Dict[str, Any]]:
        """获取可用实例列表"""
        try:
            instances = await self.connection_manager.get_all_instances()
            result = []
            
            for instance_id, instance_config in instances.items():
                display_name = getattr(instance_config, 'name', instance_id)
                health_status = await self.connection_manager.check_instance_health(instance_id)
                
                result.append({
                    "instance_id": instance_id,
                    "display_name": display_name,
                    "connection_string": instance_config.connection_string,
                    "environment": instance_config.environment,
                    "healthy": health_status["healthy"],
                    "error": health_status.get("error") if not health_status["healthy"] else None
                })
            
            return result
            
        except Exception as e:
            logger.error("获取可用实例失败", error=str(e))
            return []
    
    def validate_instance_selection(self, instance_id: str, available_instances: List[str]) -> bool:
        """验证实例选择是否有效"""
        return instance_id in available_instances