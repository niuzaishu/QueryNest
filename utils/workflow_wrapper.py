# -*- coding: utf-8 -*-
"""工作流包装器 - 为MCP工具添加流程约束和引导"""

from typing import Dict, List, Any, Optional, Callable
import structlog
from mcp.types import TextContent

from utils.workflow_manager import get_workflow_manager, WorkflowStage, WorkflowTransition

logger = structlog.get_logger(__name__)


class WorkflowConstrainedTool:
    """工作流约束的工具包装器"""
    
    def __init__(self, tool_instance, tool_name: str, required_stage: Optional[WorkflowStage] = None):
        self.tool_instance = tool_instance
        self.tool_name = tool_name
        self.required_stage = required_stage
        self.workflow_manager = get_workflow_manager()
    
    def get_tool_definition(self):
        """获取工具定义（保持原始接口）"""
        return self.tool_instance.get_tool_definition()
    
    async def execute(self, arguments: Dict[str, Any], session_id: str = "default") -> List[TextContent]:
        """执行工具（添加工作流约束）"""
        # 验证工具调用是否符合当前工作流
        can_call, message, stage_info = self.workflow_manager.validate_tool_call(session_id, self.tool_name)
        
        if not can_call:
            return self._create_workflow_constraint_response(message, stage_info)
        
        # 如果是工作流管理工具，直接处理
        if self.tool_name in ['workflow_status', 'workflow_reset', 'workflow_next', 'workflow_back']:
            return await self._handle_workflow_command(arguments, session_id)
        
        # 执行原始工具
        try:
            result = await self.tool_instance.execute(arguments)
            
            # 根据工具执行结果更新工作流状态
            await self._update_workflow_after_execution(session_id, arguments, result)
            
            # 在结果中添加工作流指导信息
            enhanced_result = await self._enhance_result_with_workflow_guidance(result, session_id)
            
            return enhanced_result
            
        except Exception as e:
            logger.error("工具执行失败", tool_name=self.tool_name, error=str(e))
            return [TextContent(
                type="text", 
                text=f"工具执行失败: {str(e)}\n\n请检查参数或联系管理员。"
            )]
    
    def _create_workflow_constraint_response(self, message: str, stage_info: Dict[str, Any]) -> List[TextContent]:
        """创建工作流约束响应"""
        response_text = f"## 🚫 工作流约束\n\n{message}\n\n"
        
        # 当前阶段信息
        current_stage = stage_info.get('stage_name', '未知')
        description = stage_info.get('description', '')
        progress = stage_info.get('progress', 0)
        
        response_text += f"### 📍 当前阶段\n"
        response_text += f"**{current_stage}** (进度: {progress}%)\n"
        response_text += f"{description}\n\n"
        
        # 缺失数据提示
        missing_data = stage_info.get('missing_data', [])
        if missing_data:
            response_text += f"### ❌ 缺失数据\n"
            response_text += f"当前阶段需要以下数据：\n"
            for data in missing_data:
                response_text += f"- {data}\n"
            response_text += "\n"
        
        # 下一步建议
        suggestions = stage_info.get('next_suggestions', [])
        if suggestions:
            response_text += f"### 💡 建议的下一步操作\n"
            for suggestion in suggestions:
                stage_name = suggestion.get('stage_name', '')
                can_transition = suggestion.get('can_transition', False)
                suggestion_message = suggestion.get('message', '')
                
                if can_transition:
                    response_text += f"✅ **{stage_name}**: {suggestion_message}\n"
                else:
                    response_text += f"❌ **{stage_name}**: {suggestion_message}\n"
            
            response_text += "\n"
        
        # 工作流状态查看提示
        response_text += f"### 📊 查看完整工作流状态\n"
        response_text += f"使用 `workflow_status` 工具查看详细的工作流状态和操作建议。\n\n"
        response_text += f"使用 `workflow_reset` 工具重置工作流（如果需要重新开始）。"
        
        return [TextContent(type="text", text=response_text)]
    
    async def _handle_workflow_command(self, arguments: Dict[str, Any], session_id: str) -> List[TextContent]:
        """处理工作流管理命令"""
        if self.tool_name == 'workflow_status':
            return await self._handle_workflow_status(session_id)
        elif self.tool_name == 'workflow_reset':
            return await self._handle_workflow_reset(session_id)
        elif self.tool_name == 'workflow_next':
            return await self._handle_workflow_next(arguments, session_id)
        elif self.tool_name == 'workflow_back':
            return await self._handle_workflow_back(session_id)
        
        return [TextContent(type="text", text="未知的工作流命令")]
    
    async def _handle_workflow_status(self, session_id: str) -> List[TextContent]:
        """处理工作流状态查询"""
        workflow = self.workflow_manager.get_workflow(session_id)
        if not workflow:
            workflow = self.workflow_manager.create_workflow(session_id)
        
        stage_info = self.workflow_manager.get_current_stage_info(session_id)
        summary = self.workflow_manager.get_workflow_summary(session_id)
        
        response_text = f"## 📊 QueryNest 查询工作流状态\n\n"
        
        # 基本信息
        response_text += f"### 🔍 会话信息\n"
        response_text += f"- **会话ID**: {summary.get('session_id')}\n"
        response_text += f"- **创建时间**: {summary.get('created_at', '未知')}\n"
        response_text += f"- **更新时间**: {summary.get('updated_at', '未知')}\n\n"
        
        # 进度信息
        progress = summary.get('progress', 0)
        response_text += f"### 📈 总体进度\n"
        response_text += f"**{progress}%** 完成\n\n"
        response_text += f"```\n"
        progress_bar = "█" * int(progress / 10) + "░" * (10 - int(progress / 10))
        response_text += f"[{progress_bar}] {progress}%\n"
        response_text += f"```\n\n"
        
        # 当前阶段
        current_stage = stage_info.get('stage_name')
        description = stage_info.get('description')
        response_text += f"### 📍 当前阶段: **{current_stage}**\n"
        response_text += f"{description}\n\n"
        
        # 已完成的数据
        response_text += f"### ✅ 已收集的数据\n"
        if summary.get('instance_id'):
            response_text += f"- **MongoDB实例**: {summary.get('instance_id')}\n"
        if summary.get('database_name'):
            response_text += f"- **数据库**: {summary.get('database_name')}\n"
        if summary.get('collection_name'):
            response_text += f"- **集合**: {summary.get('collection_name')}\n"
        if summary.get('query_description'):
            response_text += f"- **查询描述**: {summary.get('query_description')}\n"
        
        if not any([summary.get('instance_id'), summary.get('database_name'), 
                   summary.get('collection_name'), summary.get('query_description')]):
            response_text += "暂无已收集的数据\n"
        
        response_text += "\n"
        
        # 下一步建议
        suggestions = stage_info.get('next_suggestions', [])
        if suggestions:
            response_text += f"### 💡 下一步操作建议\n"
            for i, suggestion in enumerate(suggestions, 1):
                stage_name = suggestion.get('stage_name')
                can_transition = suggestion.get('can_transition')
                suggestion_desc = suggestion.get('description')
                
                status = "✅" if can_transition else "❌"
                response_text += f"{i}. {status} **{stage_name}**\n"
                response_text += f"   {suggestion_desc}\n\n"
        
        # 工作流历史
        history_count = summary.get('stage_history_count', 0)
        if history_count > 0:
            response_text += f"### 📜 历史记录\n"
            response_text += f"已完成 {history_count} 个阶段转换\n\n"
        
        # 操作提示
        response_text += f"### 🛠️ 可用的工作流命令\n"
        response_text += f"- `workflow_reset`: 重置工作流，重新开始\n"
        response_text += f"- `workflow_status`: 查看当前状态（当前命令）\n\n"
        
        response_text += f"### 📝 使用提示\n"
        response_text += f"1. 按照建议的顺序执行操作以获得最佳体验\n"
        response_text += f"2. 每个阶段完成后会自动进入下一阶段\n"
        response_text += f"3. 如遇到问题，可以使用 `workflow_reset` 重新开始\n"
        
        return [TextContent(type="text", text=response_text)]
    
    async def _handle_workflow_reset(self, session_id: str) -> List[TextContent]:
        """处理工作流重置"""
        success = self.workflow_manager.reset_workflow(session_id)
        
        if success:
            response_text = f"## 🔄 工作流已重置\n\n"
            response_text += f"您的查询工作流已重置到初始状态。\n\n"
            response_text += f"### 📍 下一步操作\n"
            response_text += f"1. 使用 `discover_instances` 开始分析可用的MongoDB实例\n"
            response_text += f"2. 或使用 `workflow_status` 查看详细的工作流指导\n\n"
            response_text += f"### 💡 温馨提示\n"
            response_text += f"按照推荐的工作流程操作可以获得最佳的查询体验和结果质量。"
        else:
            response_text = f"## ❌ 重置失败\n\n工作流重置失败，请稍后重试。"
        
        return [TextContent(type="text", text=response_text)]
    
    async def _update_workflow_after_execution(self, session_id: str, 
                                             arguments: Dict[str, Any], 
                                             result: List[TextContent]):
        """根据工具执行结果更新工作流状态"""
        try:
            # 根据工具名称和执行结果决定工作流转换
            update_data = {}
            target_stage = None
            
            if self.tool_name == 'discover_instances':
                # 实例分析完成，准备选择实例
                target_stage = WorkflowStage.INSTANCE_SELECTION
            
            elif self.tool_name == 'discover_databases':
                # 数据库分析完成，准备选择数据库
                target_stage = WorkflowStage.DATABASE_SELECTION
                if arguments.get('instance_id'):
                    update_data['instance_id'] = arguments['instance_id']
            
            elif self.tool_name == 'analyze_collection':
                # 集合分析完成，准备选择集合或分析字段
                target_stage = WorkflowStage.COLLECTION_SELECTION
                if arguments.get('instance_id'):
                    update_data['instance_id'] = arguments['instance_id']
                if arguments.get('database_name'):
                    update_data['database_name'] = arguments['database_name']
            
            elif self.tool_name == 'generate_query':
                # 查询生成完成，准备执行或优化
                target_stage = WorkflowStage.QUERY_EXECUTION
                if arguments.get('instance_id'):
                    update_data['instance_id'] = arguments['instance_id']
                if arguments.get('database_name'):
                    update_data['database_name'] = arguments['database_name']
                if arguments.get('collection_name'):
                    update_data['collection_name'] = arguments['collection_name']
                if arguments.get('query_description'):
                    update_data['query_description'] = arguments['query_description']
                
                # 尝试从结果中提取生成的查询
                # 这里需要根据实际的result格式来解析
            
            elif self.tool_name == 'confirm_query':
                # 查询执行完成，准备展示结果
                target_stage = WorkflowStage.RESULT_PRESENTATION
            
            # 执行状态转换
            if target_stage:
                success, message = self.workflow_manager.transition_to(
                    session_id, target_stage, update_data
                )
                if success:
                    logger.info("工作流自动转换", 
                               session_id=session_id, 
                               target_stage=target_stage.value)
        
        except Exception as e:
            logger.warning("更新工作流状态失败", error=str(e))
    
    async def _enhance_result_with_workflow_guidance(self, 
                                                   original_result: List[TextContent], 
                                                   session_id: str) -> List[TextContent]:
        """在原始结果中添加工作流指导信息"""
        if not original_result:
            return original_result
        
        # 获取当前工作流状态
        stage_info = self.workflow_manager.get_current_stage_info(session_id)
        suggestions = stage_info.get('next_suggestions', [])
        
        # 只在有明确下一步建议时添加指导信息
        valid_suggestions = [s for s in suggestions if s.get('can_transition', False)]
        
        if not valid_suggestions:
            return original_result
        
        # 构建指导信息
        guidance_text = "\n\n---\n\n## 🎯 下一步建议\n\n"
        
        for i, suggestion in enumerate(valid_suggestions, 1):
            stage_name = suggestion.get('stage_name')
            description = suggestion.get('description')
            guidance_text += f"{i}. **{stage_name}**: {description}\n"
        
        guidance_text += f"\n💡 *提示: 使用 `workflow_status` 查看完整工作流状态*"
        
        # 将指导信息添加到第一个TextContent中
        enhanced_result = original_result.copy()
        if enhanced_result:
            first_content = enhanced_result[0]
            enhanced_result[0] = TextContent(
                type=first_content.type,
                text=first_content.text + guidance_text
            )
        
        return enhanced_result