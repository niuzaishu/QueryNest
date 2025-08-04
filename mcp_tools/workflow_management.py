# -*- coding: utf-8 -*-
"""工作流管理工具"""

from typing import Dict, List, Any, Optional
import structlog
from mcp.types import Tool, TextContent

from utils.workflow_manager import get_workflow_manager, WorkflowStage
from utils.parameter_validator import ParameterValidator, MCPParameterHelper, ValidationResult, is_string

logger = structlog.get_logger(__name__)


class WorkflowStatusTool:
    """工作流状态查询工具"""
    
    def __init__(self):
        self.workflow_manager = get_workflow_manager()
        self.validator = self._setup_validator()
    
    def _setup_validator(self) -> ParameterValidator:
        """设置参数验证器"""
        validator = ParameterValidator()
        
        validator.add_optional_parameter(
            name="session_id",
            type_check=is_string,
            description="会话标识符，默认为'default'",
            user_friendly_name="会话ID"
        )
        
        return validator
    
    def get_tool_definition(self) -> Tool:
        """获取工具定义"""
        return Tool(
            name="workflow_status",
            description="查看当前查询工作流的状态、进度和下一步建议",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "会话标识符，默认为'default'",
                        "default": "default"
                    }
                },
                "required": []
            }
        )
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """执行工作流状态查询"""
        # 参数验证
        validation_result, errors = await self.validator.validate_parameters(arguments)
        if validation_result != ValidationResult.VALID:
            return MCPParameterHelper.create_error_response(errors)
        
        session_id = arguments.get("session_id", "default")
        
        # 获取或创建工作流
        workflow = self.workflow_manager.get_or_create_workflow(session_id)
        stage_info = self.workflow_manager.get_current_stage_info(session_id)
        summary = self.workflow_manager.get_workflow_summary(session_id)
        
        # 构建详细的状态报告
        response_text = self._build_status_response(stage_info, summary)
        
        return [TextContent(type="text", text=response_text)]
    
    def _build_status_response(self, stage_info: Dict[str, Any], summary: Dict[str, Any]) -> str:
        """构建状态响应"""
        response_text = "# 🔍 QueryNest 工作流状态\n\n"
        
        # 会话基本信息
        response_text += "## 📋 会话信息\n\n"
        response_text += f"- **会话ID**: {summary.get('session_id', 'default')}\n"
        response_text += f"- **创建时间**: {summary.get('created_at', '未知')}\n"
        response_text += f"- **最后更新**: {summary.get('updated_at', '未知')}\n\n"
        
        # 总体进度
        progress = summary.get('progress', 0)
        response_text += "## 📊 总体进度\n\n"
        progress_bar = "█" * int(progress / 10) + "░" * (10 - int(progress / 10))
        response_text += f"```\n[{progress_bar}] {progress}%\n```\n\n"
        
        # 当前阶段详情
        current_stage = stage_info.get('stage_name', '未知')
        description = stage_info.get('description', '')
        is_complete = stage_info.get('is_complete', False)
        
        response_text += f"## 📍 当前阶段: **{current_stage}**\n\n"
        response_text += f"{description}\n\n"
        
        # 阶段完成状态
        status_emoji = "✅" if is_complete else "⏳"
        status_text = "已完成" if is_complete else "进行中"
        response_text += f"**状态**: {status_emoji} {status_text}\n\n"
        
        # 缺失数据提醒
        missing_data = stage_info.get('missing_data', [])
        if missing_data:
            response_text += "### ❌ 待收集数据\n\n"
            data_names = {
                'instance_id': 'MongoDB实例',
                'database_name': '数据库名称',
                'collection_name': '集合名称',
                'query_description': '查询描述',
                'generated_query': '生成的查询'
            }
            for data in missing_data:
                friendly_name = data_names.get(data, data)
                response_text += f"- {friendly_name}\n"
            response_text += "\n"
        
        # 已收集数据
        response_text += "## 📦 已收集数据\n\n"
        collected_data = []
        
        if summary.get('instance_id'):
            collected_data.append(f"**MongoDB实例**: {summary['instance_id']}")
        if summary.get('database_name'):
            collected_data.append(f"**数据库**: {summary['database_name']}")
        if summary.get('collection_name'):
            collected_data.append(f"**集合**: {summary['collection_name']}")
        if summary.get('query_description'):
            collected_data.append(f"**查询描述**: {summary['query_description']}")
        
        if collected_data:
            for data in collected_data:
                response_text += f"- {data}\n"
        else:
            response_text += "暂无已收集的数据\n"
        
        response_text += "\n"
        
        # 查询优化轮次
        refinement_count = summary.get('refinement_count', 0)
        if refinement_count > 0:
            response_text += f"## 🔧 查询优化\n\n"
            response_text += f"已进行 **{refinement_count}** 轮查询优化\n\n"
        
        # 下一步操作建议
        suggestions = stage_info.get('next_suggestions', [])
        if suggestions:
            response_text += "## 💡 下一步操作建议\n\n"
            
            can_do_suggestions = [s for s in suggestions if s.get('can_transition', False)]
            cannot_do_suggestions = [s for s in suggestions if not s.get('can_transition', False)]
            
            if can_do_suggestions:
                response_text += "### ✅ 可以执行的操作\n\n"
                for i, suggestion in enumerate(can_do_suggestions, 1):
                    stage_name = suggestion.get('stage_name')
                    description = suggestion.get('description')
                    response_text += f"{i}. **{stage_name}**\n   {description}\n\n"
            
            if cannot_do_suggestions:
                response_text += "### ❌ 暂时无法执行的操作\n\n"
                for suggestion in cannot_do_suggestions:
                    stage_name = suggestion.get('stage_name')
                    message = suggestion.get('message', '')
                    response_text += f"- **{stage_name}**: {message}\n"
                response_text += "\n"
        
        # 工作流概览
        response_text += "## 🗺️ 完整工作流程\n\n"
        response_text += self._get_workflow_overview(summary.get('current_stage'))
        
        # 操作指南
        response_text += "## 🛠️ 可用命令\n\n"
        response_text += "- `workflow_reset`: 重置工作流，重新开始查询过程\n"
        response_text += "- `workflow_status`: 查看当前状态（当前命令）\n\n"
        
        response_text += "## 💡 使用提示\n\n"
        response_text += "1. 建议按照工作流程顺序执行操作，以获得最佳查询体验\n"
        response_text += "2. 每完成一个阶段，系统会自动引导您进入下一阶段\n"
        response_text += "3. 如果遇到问题或想重新开始，可以使用 `workflow_reset` 重置\n"
        response_text += "4. 语义库会在各个分析阶段自动更新，提高后续查询的准确性\n"
        
        return response_text
    
    def _get_workflow_overview(self, current_stage: str) -> str:
        """获取工作流概览"""
        stages = [
            ("初始化", "开始新的查询会话"),
            ("分析实例", "发现并分析MongoDB实例，更新实例语义库"),
            ("选择实例", "选择要查询的MongoDB实例"),
            ("分析数据库", "分析实例中的数据库，更新数据库语义库"),
            ("选择数据库", "选择要查询的数据库"),
            ("分析集合", "分析数据库中的集合，更新集合语义库"),
            ("选择集合", "选择要查询的集合"),
            ("分析字段", "分析集合中的字段结构，更新字段语义库"),
            ("生成查询", "基于需求生成MongoDB查询语句"),
            ("优化查询", "根据用户反馈优化查询语句"),
            ("执行查询", "执行查询并获取结果"),
            ("展示结果", "以用户友好的方式展示查询结果"),
            ("完成", "查询流程完成")
        ]
        
        overview = ""
        for i, (stage_name, stage_desc) in enumerate(stages, 1):
            if current_stage and stage_name == current_stage:
                overview += f"{i}. **👉 {stage_name}** ← *当前位置*\n   {stage_desc}\n\n"
            else:
                overview += f"{i}. {stage_name}\n   {stage_desc}\n\n"
        
        return overview


class WorkflowResetTool:
    """工作流重置工具"""
    
    def __init__(self):
        self.workflow_manager = get_workflow_manager()
        self.validator = self._setup_validator()
    
    def _setup_validator(self) -> ParameterValidator:
        """设置参数验证器"""
        validator = ParameterValidator()
        
        validator.add_optional_parameter(
            name="session_id",
            type_check=is_string,
            description="会话标识符，默认为'default'",
            user_friendly_name="会话ID"
        )
        
        validator.add_optional_parameter(
            name="confirm",
            type_check=lambda x: isinstance(x, bool),
            description="确认重置，设为true表示确认重置工作流",
            user_friendly_name="确认重置"
        )
        
        return validator
    
    def get_tool_definition(self) -> Tool:
        """获取工具定义"""
        return Tool(
            name="workflow_reset",
            description="重置查询工作流，清除所有进度和数据，重新开始",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "会话标识符，默认为'default'",
                        "default": "default"
                    },
                    "confirm": {
                        "type": "boolean",
                        "description": "确认重置，设为true表示确认重置工作流",
                        "default": False
                    }
                },
                "required": []
            }
        )
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """执行工作流重置"""
        # 参数验证
        validation_result, errors = await self.validator.validate_parameters(arguments)
        if validation_result != ValidationResult.VALID:
            return MCPParameterHelper.create_error_response(errors)
        
        session_id = arguments.get("session_id", "default")
        confirm = arguments.get("confirm", False)
        
        # 如果没有确认，提示用户确认
        if not confirm:
            return [TextContent(
                type="text",
                text=(
                    "## ⚠️ 重置确认\n\n"
                    "您即将重置整个查询工作流，这将清除以下内容：\n\n"
                    "- 所有已选择的实例、数据库、集合信息\n"
                    "- 当前的查询描述和生成的查询语句\n"
                    "- 工作流进度和历史记录\n\n"
                    "**注意**: 语义库中的数据不会被清除，已学习的语义信息将保留。\n\n"
                    "### 确认重置\n"
                    "如果确定要重置，请重新调用此工具并设置 `confirm: true`：\n\n"
                    "```json\n"
                    "{\n"
                    '  "confirm": true\n'
                    "}\n"
                    "```\n\n"
                    "或者使用 `workflow_status` 查看当前状态。"
                )
            )]
        
        # 执行重置
        success = self.workflow_manager.reset_workflow(session_id)
        
        if success:
            response_text = (
                "# ✅ 工作流重置成功\n\n"
                "您的查询工作流已重置到初始状态。\n\n"
                "## 🚀 开始新的查询流程\n\n"
                "### 推荐的第一步操作\n\n"
                "1. **分析MongoDB实例**: 使用 `discover_instances` 工具\n"
                "   - 发现并分析所有可用的MongoDB实例\n"
                "   - 自动更新实例语义库\n\n"
                "2. **查看工作流状态**: 使用 `workflow_status` 工具\n"
                "   - 查看详细的工作流指导\n"
                "   - 了解完整的查询流程\n\n"
                "### 💡 流程提醒\n\n"
                "按照以下顺序操作将获得最佳查询体验：\n"
                "分析实例 → 选择实例 → 分析数据库 → 选择数据库 → "
                "分析集合 → 选择集合 → 分析字段 → 生成查询 → 执行查询\n\n"
                "每个阶段完成后，系统会自动提供下一步建议。"
            )
        else:
            response_text = (
                "# ❌ 重置失败\n\n"
                "工作流重置失败，请稍后重试。\n\n"
                "如果问题持续存在，请联系系统管理员。"
            )
        
        return [TextContent(type="text", text=response_text)]