# -*- coding: utf-8 -*-
"""实例选择工具 - 支持智能推荐+用户确认"""

from typing import Dict, List, Any, Optional
import structlog
from mcp.types import Tool, TextContent

from database.connection_manager import ConnectionManager
from database.metadata_manager import MetadataManager
from utils.parameter_validator import ParameterValidator, MCPParameterHelper, ValidationResult
from utils.tool_context import get_context_manager
from utils.error_handler import with_error_handling, with_retry, RetryConfig
from utils.workflow_manager import get_workflow_manager, WorkflowStage
from utils.user_confirmation import UserConfirmationHelper, ConfirmationParser

logger = structlog.get_logger(__name__)


class InstanceSelectionTool:
    """实例选择工具 - 支持推荐+确认模式"""
    
    def __init__(self, connection_manager: ConnectionManager, metadata_manager: MetadataManager):
        self.connection_manager = connection_manager
        self.metadata_manager = metadata_manager
        self.context_manager = get_context_manager()
        self.workflow_manager = get_workflow_manager()
    
    def get_tool_definition(self) -> Tool:
        """获取工具定义"""
        return Tool(
            name="select_instance",
            description="智能实例选择工具：提供推荐选项，需要用户确认后执行",
            inputSchema={
                "type": "object",
                "properties": {
                    "instance_id": {
                        "type": "string",
                        "description": "要选择的MongoDB实例ID（可选，如果不提供则显示推荐选项）"
                    },
                    "session_id": {
                        "type": "string",
                        "description": "会话标识符，默认为'default'",
                        "default": "default"
                    },
                    "user_choice": {
                        "type": "string",
                        "description": "用户选择（A, B, C等），用于确认推荐选项"
                    },
                    "show_recommendations": {
                        "type": "boolean",
                        "description": "强制显示推荐选项",
                        "default": False
                    }
                },
                "required": []
            }
        )
    
    @with_error_handling("实例选择")
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """执行实例选择"""
        session_id = arguments.get("session_id", "default")
        instance_id = arguments.get("instance_id")
        user_choice = arguments.get("user_choice")
        show_recommendations = arguments.get("show_recommendations", False)
        
        # 获取所有可用实例
        instances = await self.connection_manager.get_all_instances()
        
        if not instances:
            return [TextContent(
                type="text",
                text="## ❌ 没有可用的MongoDB实例\n\n请检查配置文件中的实例配置。"
            )]
        
        # 情况1：直接指定了instance_id，进行选择
        if instance_id and not show_recommendations:
            return await self._execute_selection(instance_id, session_id, instances)
        
        # 情况2：需要显示推荐选项
        if not user_choice:
            return await self._show_recommendations(instances, session_id)
        
        # 情况3：用户已做出选择，处理选择
        return await self._handle_user_choice(user_choice, instances, session_id)
    
    async def _show_recommendations(self, instances: Dict[str, Any], session_id: str) -> List[TextContent]:
        """显示推荐选项"""
        logger.info("显示实例推荐选项", session_id=session_id, instance_count=len(instances))
        
        # 增强实例信息
        enhanced_instances = {}
        for instance_id, config in instances.items():
            health = await self.connection_manager.check_instance_health(instance_id)
            enhanced_instances[instance_id] = {
                **config.__dict__,
                "health_status": health,
                "instance_id": instance_id
            }
        
        # 生成推荐提示
        return [UserConfirmationHelper.create_instance_selection_prompt(enhanced_instances)]
    
    async def _handle_user_choice(self, user_choice: str, instances: Dict[str, Any], session_id: str) -> List[TextContent]:
        """处理用户选择"""
        instance_ids = list(instances.keys())
        
        # 处理特殊选择
        choice_upper = user_choice.upper()
        
        if choice_upper in ['Z', 'CANCEL']:
            return [TextContent(type="text", text="## ❌ 已取消实例选择")]
        
        if choice_upper in ['B', 'VIEW', 'DETAILS']:
            # 显示详细信息后再次显示推荐
            return await self._show_detailed_instances(instances, session_id)
        
        # 解析用户选择
        is_valid, selected_instance, error_msg = ConfirmationParser.parse_selection(
            user_choice, instance_ids
        )
        
        if not is_valid:
            error_text = f"## ❌ 选择无效\n\n{error_msg}\n\n"
            error_text += "请重新选择或使用 `select_instance(show_recommendations=True)` 查看选项。"
            return [TextContent(type="text", text=error_text)]
        
        # 执行选择
        return await self._execute_selection(selected_instance, session_id, instances)
    
    async def _show_detailed_instances(self, instances: Dict[str, Any], session_id: str) -> List[TextContent]:
        """显示详细实例信息"""
        text = "## 📋 详细实例信息\n\n"
        
        for i, (instance_id, config) in enumerate(instances.items(), 1):
            display_name = getattr(config, 'name', instance_id)
            health = await self.connection_manager.check_instance_health(instance_id)
            
            text += f"### {chr(64+i)}) {display_name}\n"
            text += f"- **实例ID**: `{instance_id}`\n"
            text += f"- **环境**: {config.environment}\n"
            text += f"- **状态**: {config.status}\n"
            text += f"- **连接字符串**: {config.connection_string}\n"
            
            if health["healthy"]:
                text += f"- **健康状态**: ✅ 健康 (延迟: {health.get('latency_ms', 'N/A')}ms)\n"
            else:
                text += f"- **健康状态**: ❌ 不健康 - {health.get('error', 'Unknown')}\n"
            
            if config.description:
                text += f"- **描述**: {config.description}\n"
            
            text += "\n"
        
        text += "### 📋 请选择实例\n\n"
        for i, (instance_id, _) in enumerate(instances.items(), 1):
            text += f"**{chr(64+i)}) 选择** `{instance_id}`\n"
        
        text += "**Z) ❌ 取消选择**\n\n"
        text += "💡 **提示**: 输入字母（如A、B）来选择对应的实例"
        
        return [TextContent(type="text", text=text)]
    
    async def _execute_selection(self, instance_id: str, session_id: str, instances: Dict[str, Any]) -> List[TextContent]:
        """执行实例选择"""
        logger.info("执行实例选择", instance_id=instance_id, session_id=session_id)
        
        # 验证实例存在
        if instance_id not in instances:
            available = list(instances.keys())
            return [TextContent(
                type="text",
                text=f"## ❌ 实例不存在\n\n实例 `{instance_id}` 不存在。\n\n**可用实例**: {', '.join(available)}"
            )]
        
        # 检查健康状态
        health_status = await self.connection_manager.check_instance_health(instance_id)
        instance_config = instances[instance_id]
        display_name = getattr(instance_config, 'name', instance_id)
        
        # 更新工作流状态
        update_data = {
            "instance_id": instance_id,
            "selected_instance_name": display_name
        }
        
        success, message = await self.workflow_manager.transition_to(
            session_id, 
            WorkflowStage.INSTANCE_SELECTION, 
            update_data
        )
        
        if not success:
            return [TextContent(
                type="text",
                text=f"## ❌ 工作流更新失败\n\n{message}"
            )]
        
        # 构建成功响应
        result_text = f"## ✅ 实例选择成功\n\n"
        result_text += f"**选择的实例**: {display_name} (`{instance_id}`)\n"
        result_text += f"**环境**: {instance_config.environment}\n"
        result_text += f"**状态**: {instance_config.status}\n"
        
        if health_status["healthy"]:
            result_text += f"**健康状态**: ✅ 健康 (延迟: {health_status.get('latency_ms', 'N/A')}ms)\n"
        else:
            result_text += f"**健康状态**: ⚠️ 不健康 - {health_status.get('error', 'Unknown')}\n"
        
        result_text += f"\n**工作流状态**: {message}\n\n"
        
        # 下一步建议
        result_text += "## 🎯 下一步操作\n\n"
        result_text += "现在可以继续以下操作：\n"
        result_text += f"- `discover_databases(instance_id=\"{instance_id}\")` - 发现数据库\n"
        result_text += f"- `select_database()` - 智能数据库选择\n"
        result_text += "- `workflow_status()` - 查看工作流状态\n"
        
        logger.info("实例选择完成", instance_id=instance_id, session_id=session_id)
        
        return [TextContent(type="text", text=result_text)]