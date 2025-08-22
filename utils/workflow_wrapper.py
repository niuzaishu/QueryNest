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
        can_call, message, stage_info = await self.workflow_manager.validate_tool_call(session_id, self.tool_name)
        
        if not can_call:
            return self._create_workflow_constraint_response(message, stage_info)
        
        # 如果是工作流管理工具，直接处理
        if self.tool_name in ['workflow_status', 'workflow_reset', 'workflow_next', 'workflow_back']:
            return await self._handle_workflow_command(arguments, session_id)
        
        # 执行原始工具
        try:
            # 预处理参数
            processed_arguments = await self._preprocess_arguments(arguments, session_id)
            
            # 智能参数推断
            enhanced_arguments = await self._enhance_arguments_with_context(processed_arguments, session_id)
            
            # 参数验证
            validation_result = await self._validate_arguments(enhanced_arguments)
            if not validation_result['valid']:
                return [TextContent(
                    type="text",
                    text=f"参数验证失败: {validation_result['message']}\n\n{validation_result.get('suggestions', '')}"
                )]
            
            result = await self.tool_instance.execute(enhanced_arguments)
            
            # 根据工具执行结果更新工作流状态
            await self._update_workflow_after_execution(session_id, enhanced_arguments, result)
            
            # 在结果中添加工作流指导信息
            enhanced_result = await self._enhance_result_with_workflow_guidance(result, session_id)
            
            return enhanced_result
        
        except Exception as e:
            logger.error("工具执行失败", tool_name=self.tool_name, error=str(e))
            return [TextContent(
                type="text", 
                text=f"工具执行失败: {str(e)}\n\n请检查参数或联系管理员。"
            )]
    
    async def _preprocess_arguments(self, arguments: Dict[str, Any], session_id: str) -> Dict[str, Any]:
        """预处理参数"""
        processed = arguments.copy()
        
        # 标准化参数名称
        processed = self._normalize_parameter_names(processed)
        
        # 类型转换
        processed = self._convert_parameter_types(processed)
        
        return processed
    
    def _normalize_parameter_names(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """标准化参数名称"""
        normalized = {}
        
        # 参数名称映射
        name_mapping = {
            'instance': 'instance_id',
            'db': 'database_name',
            'database': 'database_name',
            'collection': 'collection_name',
            'col': 'collection_name'
        }
        
        for key, value in arguments.items():
            normalized_key = name_mapping.get(key, key)
            normalized[normalized_key] = value
        
        return normalized
    
    def _convert_parameter_types(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """转换参数类型"""
        converted = arguments.copy()
        
        # 数值类型转换
        for key in ['limit', 'skip', 'timeout']:
            if key in converted and isinstance(converted[key], str):
                try:
                    converted[key] = int(converted[key])
                except ValueError:
                    # 保持原值或设置默认值
                    if key == 'limit':
                        converted[key] = 10
                    elif key == 'skip':
                        converted[key] = 0
                    elif key == 'timeout':
                        converted[key] = 30
        
        # 布尔类型转换
        for key in ['include_system_dbs', 'detailed', 'force']:
            if key in converted and isinstance(converted[key], str):
                converted[key] = converted[key].lower() in ['true', '1', 'yes', 'on']
        
        return converted
    
    async def _enhance_arguments_with_context(self, arguments: Dict[str, Any], session_id: str) -> Dict[str, Any]:
        """使用工作流上下文增强参数"""
        enhanced = arguments.copy()
        workflow_data = await self.workflow_manager.get_workflow_data(session_id)
        
        # 从工作流上下文推断缺失参数
        if 'instance_id' not in enhanced or not enhanced['instance_id']:
            if workflow_data.get('instance_id'):
                enhanced['instance_id'] = workflow_data['instance_id']
        
        if 'database_name' not in enhanced or not enhanced['database_name']:
            if workflow_data.get('database_name'):
                enhanced['database_name'] = workflow_data['database_name']
        
        if 'collection_name' not in enhanced or not enhanced['collection_name']:
            if workflow_data.get('collection_name'):
                enhanced['collection_name'] = workflow_data['collection_name']
        
        return enhanced
    
    async def _validate_arguments(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """验证参数"""
        # 基础验证逻辑
        required_params = self._get_required_parameters()
        missing_params = []
        
        for param in required_params:
            if param not in arguments or arguments[param] is None or arguments[param] == '':
                missing_params.append(param)
        
        if missing_params:
            return {
                'valid': False,
                'message': f"缺少必需参数: {', '.join(missing_params)}",
                'suggestions': f"请提供以下参数: {', '.join(missing_params)}"
            }
        
        return {'valid': True}
    
    def _get_required_parameters(self) -> List[str]:
        """获取工具的必需参数"""
        # 根据工具类型返回必需参数
        tool_requirements = {
            'discover_databases': ['instance_id'],
            'analyze_collection': ['instance_id', 'database_name'],
            'generate_query': ['instance_id', 'database_name', 'collection_name'],
            'confirm_query': ['instance_id', 'database_name', 'collection_name']
        }
        
        return tool_requirements.get(self.tool_name, [])
    
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
        next_actions = stage_info.get('next_actions', [])
        if next_actions:
            response_text += f"### 💡 建议操作\n"
            for i, action in enumerate(next_actions, 1):
                response_text += f"{i}. {action}\n"
            response_text += "\n"
        
        response_text += "---\n\n"
        response_text += "💡 *提示: 使用 `workflow_status` 查看完整工作流状态*"
        
        return [TextContent(type="text", text=response_text)]
    
    async def _handle_workflow_command(self, arguments: Dict[str, Any], session_id: str) -> List[TextContent]:
        """处理工作流命令"""
        if self.tool_name == 'workflow_status':
            return await self._handle_workflow_status(session_id)
        elif self.tool_name == 'workflow_reset':
            return await self._handle_workflow_reset(session_id)
        elif self.tool_name == 'workflow_next':
            return await self._handle_workflow_next(session_id)
        elif self.tool_name == 'workflow_back':
            return await self._handle_workflow_back(session_id)
        else:
            return [TextContent(type="text", text="未知的工作流命令")]
    
    async def _handle_workflow_status(self, session_id: str) -> List[TextContent]:
        """处理工作流状态查询"""
        stage_info = await self.workflow_manager.get_current_stage_info(session_id)
        workflow_data = await self.workflow_manager.get_workflow_summary(session_id)
        
        response_text = "## 📊 工作流状态\n\n"
        
        # 当前阶段
        current_stage = stage_info.get('stage_name', '未知')
        description = stage_info.get('description', '')
        progress = stage_info.get('progress', 0)
        
        response_text += f"### 📍 当前阶段\n"
        response_text += f"**{current_stage}** (进度: {progress}%)\n"
        response_text += f"{description}\n\n"
        
        # 工作流数据
        response_text += f"### 📋 已收集数据\n"
        if workflow_data.get('instance_id'):
            response_text += f"- **实例ID**: {workflow_data['instance_id']}\n"
        if workflow_data.get('database_name'):
            response_text += f"- **数据库**: {workflow_data['database_name']}\n"
        if workflow_data.get('collection_name'):
            response_text += f"- **集合**: {workflow_data['collection_name']}\n"
        
        if not any([workflow_data.get('instance_id'), workflow_data.get('database_name'), workflow_data.get('collection_name')]):
            response_text += "*暂无数据*\n"
        
        response_text += "\n"
        
        # 可用操作
        available_tools = stage_info.get('available_tools', [])
        if available_tools:
            response_text += f"### 🔧 可用操作\n"
            for tool in available_tools:
                response_text += f"- `{tool}`\n"
            response_text += "\n"
        
        # 下一步建议
        next_suggestions = stage_info.get('next_suggestions', [])
        if next_suggestions:
            response_text += f"### 💡 下一步建议\n"
            for i, suggestion in enumerate(next_suggestions, 1):
                stage_name = suggestion.get('stage_name')
                desc = suggestion.get('description')
                response_text += f"{i}. **{stage_name}**: {desc}\n"
            response_text += "\n"
        
        response_text += "---\n\n"
        response_text += "💡 *提示: 使用相应的工具继续工作流程*"
        
        return [TextContent(type="text", text=response_text)]
    
    async def _handle_workflow_reset(self, session_id: str) -> List[TextContent]:
        """处理工作流重置"""
        await self.workflow_manager.reset_workflow(session_id)
        
        response_text = "## 🔄 工作流已重置\n\n"
        response_text += "所有工作流数据已清除，您可以重新开始。\n\n"
        response_text += "### 💡 建议下一步\n"
        response_text += "1. 使用 `discover_instances` 发现可用的数据库实例\n"
        response_text += "2. 使用 `workflow_status` 查看当前状态\n"
        
        return [TextContent(type="text", text=response_text)]
    
    async def _handle_workflow_next(self, session_id: str) -> List[TextContent]:
        """处理工作流前进"""
        success = await self.workflow_manager.advance_stage(session_id)
        
        if success:
            stage_info = await self.workflow_manager.get_current_stage_info(session_id)
            response_text = f"## ⏭️ 工作流已前进\n\n"
            response_text += f"当前阶段: **{stage_info.get('stage_name')}**\n"
            response_text += f"{stage_info.get('description')}\n"
        else:
            response_text = "## ❌ 无法前进\n\n"
            response_text += "当前阶段不允许前进，请完成必要的操作。\n"
        
        return [TextContent(type="text", text=response_text)]
    
    async def _handle_workflow_back(self, session_id: str) -> List[TextContent]:
        """处理工作流后退"""
        success = await self.workflow_manager.go_back_stage(session_id)
        
        if success:
            stage_info = await self.workflow_manager.get_current_stage_info(session_id)
            response_text = f"## ⏮️ 工作流已后退\n\n"
            response_text += f"当前阶段: **{stage_info.get('stage_name')}**\n"
            response_text += f"{stage_info.get('description')}\n"
        else:
            response_text = "## ❌ 无法后退\n\n"
            response_text += "已经在第一个阶段，无法继续后退。\n"
        
        return [TextContent(type="text", text=response_text)]
    
    async def _update_workflow_after_execution(self, session_id: str, 
                                             arguments: Dict[str, Any], 
                                             result: List[TextContent]):
        """根据工具执行结果更新工作流状态"""
        # 更新工作流数据
        updates = {}
        
        if 'instance_id' in arguments:
            updates['instance_id'] = arguments['instance_id']
        
        if 'database_name' in arguments:
            updates['database_name'] = arguments['database_name']
        
        if 'collection_name' in arguments:
            updates['collection_name'] = arguments['collection_name']
        
        if updates:
            await self.workflow_manager.update_workflow_data(session_id, updates)
        
        # 根据工具类型自动推进工作流
        if self.tool_name == 'discover_instances':
            # 发现实例后，推进到实例分析阶段
            await self.workflow_manager.try_advance_to_stage(session_id, WorkflowStage.INSTANCE_ANALYSIS)
        
        elif self.tool_name == 'discover_databases':
            # 发现数据库后，可以进入集合分析阶段
            await self.workflow_manager.try_advance_to_stage(session_id, WorkflowStage.COLLECTION_ANALYSIS)
        
        elif self.tool_name == 'analyze_collection':
            # 分析集合后，可以进入查询生成阶段
            await self.workflow_manager.try_advance_to_stage(session_id, WorkflowStage.QUERY_GENERATION)
        
        elif self.tool_name == 'generate_query':
            # 生成查询后，可以进入查询执行阶段
            await self.workflow_manager.try_advance_to_stage(session_id, WorkflowStage.QUERY_EXECUTION)
    
    async def _enhance_result_with_workflow_guidance(self, 
                                                   original_result: List[TextContent], 
                                                   session_id: str) -> List[TextContent]:
        """在结果中添加工作流指导信息"""
        # 获取当前阶段的下一步建议
        stage_info = await self.workflow_manager.get_current_stage_info(session_id)
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


class WorkflowWrapper:
    """工作流包装器 - 兼容性别名"""
    
    def __init__(self):
        pass
    
    @staticmethod
    def wrap_tool(tool_instance, tool_name: str, required_stage: Optional[WorkflowStage] = None):
        """包装工具为工作流约束工具"""
        return WorkflowConstrainedTool(tool_instance, tool_name, required_stage)