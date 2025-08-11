# -*- coding: utf-8 -*-
"""工作流管理器 - 约束和引导用户按照预期流程操作"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import json
import structlog
from datetime import datetime

logger = structlog.get_logger(__name__)


class WorkflowStage(Enum):
    """工作流阶段枚举"""
    INIT = "init"                           # 初始化
    INSTANCE_ANALYSIS = "instance_analysis" # 分析实例
    INSTANCE_SELECTION = "instance_selection" # 选择实例
    INSTANCE_DISCOVERY = "instance_discovery" # 发现实例
    DATABASE_ANALYSIS = "database_analysis" # 分析数据库
    DATABASE_SELECTION = "database_selection" # 选择数据库
    DATABASE_DISCOVERY = "database_discovery" # 发现数据库
    COLLECTION_ANALYSIS = "collection_analysis" # 分析集合
    COLLECTION_SELECTION = "collection_selection" # 选择集合
    COLLECTION_DISCOVERY = "collection_discovery" # 发现集合
    FIELD_ANALYSIS = "field_analysis"       # 分析字段
    QUERY_GENERATION = "query_generation"   # 生成查询
    QUERY_REFINEMENT = "query_refinement"   # 查询优化
    QUERY_EXECUTION = "query_execution"     # 执行查询
    RESULT_PRESENTATION = "result_presentation" # 结果展示
    COMPLETED = "completed"                 # 完成


class WorkflowTransition(Enum):
    """工作流转换类型"""
    NEXT = "next"           # 进入下一阶段
    BACK = "back"           # 返回上一阶段
    RETRY = "retry"         # 重试当前阶段
    JUMP = "jump"           # 跳转到指定阶段
    RESET = "reset"         # 重置工作流


@dataclass
class WorkflowState:
    """工作流状态"""
    current_stage: WorkflowStage
    session_id: str
    instance_id: Optional[str] = None
    database_name: Optional[str] = None
    collection_name: Optional[str] = None
    query_description: Optional[str] = None
    generated_query: Optional[Dict[str, Any]] = None
    refinement_count: int = 0
    max_refinements: int = 5
    stage_data: Dict[str, Any] = None
    stage_history: List[WorkflowStage] = None
    created_at: datetime = None
    updated_at: datetime = None
    
    def __post_init__(self):
        if self.stage_data is None:
            self.stage_data = {}
        if self.stage_history is None:
            self.stage_history = []
        if self.created_at is None:
            self.created_at = datetime.now()
        self.updated_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'current_stage': self.current_stage.value,
            'session_id': self.session_id,
            'instance_id': self.instance_id,
            'database_name': self.database_name,
            'collection_name': self.collection_name,
            'query_description': self.query_description,
            'generated_query': self.generated_query,
            'refinement_count': self.refinement_count,
            'max_refinements': self.max_refinements,
            'stage_data': self.stage_data,
            'stage_history': [stage.value for stage in self.stage_history],
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkflowState':
        """从字典创建工作流状态"""
        state = cls(
            current_stage=WorkflowStage(data['current_stage']),
            session_id=data['session_id'],
            instance_id=data.get('instance_id'),
            database_name=data.get('database_name'),
            collection_name=data.get('collection_name'),
            query_description=data.get('query_description'),
            generated_query=data.get('generated_query'),
            refinement_count=data.get('refinement_count', 0),
            max_refinements=data.get('max_refinements', 5),
            stage_data=data.get('stage_data', {}),
            stage_history=[WorkflowStage(stage) for stage in data.get('stage_history', [])],
            created_at=datetime.fromisoformat(data['created_at']) if data.get('created_at') else None,
            updated_at=datetime.fromisoformat(data['updated_at']) if data.get('updated_at') else None
        )
        return state


class WorkflowManager:
    """工作流管理器"""
    
    def __init__(self):
        self._workflows: Dict[str, WorkflowState] = {}
        
        # 定义阶段转换规则
        self._stage_transitions = {
            WorkflowStage.INIT: [WorkflowStage.INSTANCE_ANALYSIS, WorkflowStage.INSTANCE_DISCOVERY],
            WorkflowStage.INSTANCE_ANALYSIS: [WorkflowStage.INSTANCE_SELECTION],
            WorkflowStage.INSTANCE_DISCOVERY: [WorkflowStage.INSTANCE_SELECTION],
            WorkflowStage.INSTANCE_SELECTION: [WorkflowStage.DATABASE_ANALYSIS, WorkflowStage.DATABASE_DISCOVERY, WorkflowStage.INSTANCE_ANALYSIS],
            WorkflowStage.DATABASE_ANALYSIS: [WorkflowStage.DATABASE_SELECTION, WorkflowStage.INSTANCE_SELECTION],
            WorkflowStage.DATABASE_DISCOVERY: [WorkflowStage.DATABASE_SELECTION, WorkflowStage.INSTANCE_SELECTION],
            WorkflowStage.DATABASE_SELECTION: [WorkflowStage.COLLECTION_ANALYSIS, WorkflowStage.COLLECTION_DISCOVERY, WorkflowStage.DATABASE_ANALYSIS],
            WorkflowStage.COLLECTION_ANALYSIS: [WorkflowStage.COLLECTION_SELECTION, WorkflowStage.DATABASE_SELECTION],
            WorkflowStage.COLLECTION_DISCOVERY: [WorkflowStage.COLLECTION_SELECTION, WorkflowStage.DATABASE_SELECTION],
            WorkflowStage.COLLECTION_SELECTION: [WorkflowStage.FIELD_ANALYSIS, WorkflowStage.COLLECTION_ANALYSIS],
            WorkflowStage.FIELD_ANALYSIS: [WorkflowStage.QUERY_GENERATION, WorkflowStage.COLLECTION_SELECTION],
            WorkflowStage.QUERY_GENERATION: [WorkflowStage.QUERY_REFINEMENT, WorkflowStage.QUERY_EXECUTION, WorkflowStage.FIELD_ANALYSIS],
            WorkflowStage.QUERY_REFINEMENT: [WorkflowStage.QUERY_GENERATION, WorkflowStage.QUERY_EXECUTION],
            WorkflowStage.QUERY_EXECUTION: [WorkflowStage.RESULT_PRESENTATION, WorkflowStage.QUERY_REFINEMENT],
            WorkflowStage.RESULT_PRESENTATION: [WorkflowStage.COMPLETED, WorkflowStage.QUERY_REFINEMENT],
            WorkflowStage.COMPLETED: []
        }
        
        # 定义每个阶段需要的数据
        self._stage_requirements = {
            WorkflowStage.INIT: [],
            WorkflowStage.INSTANCE_ANALYSIS: [],
            WorkflowStage.INSTANCE_DISCOVERY: [],
            WorkflowStage.INSTANCE_SELECTION: [],
            WorkflowStage.DATABASE_ANALYSIS: ['instance_id'],
            WorkflowStage.DATABASE_DISCOVERY: ['instance_id'],
            WorkflowStage.DATABASE_SELECTION: ['instance_id'],
            WorkflowStage.COLLECTION_ANALYSIS: ['instance_id', 'database_name'],
            WorkflowStage.COLLECTION_DISCOVERY: ['instance_id', 'database_name'],
            WorkflowStage.COLLECTION_SELECTION: ['instance_id', 'database_name'],
            WorkflowStage.FIELD_ANALYSIS: ['instance_id', 'database_name', 'collection_name'],
            WorkflowStage.QUERY_GENERATION: ['instance_id', 'database_name', 'collection_name'],
            WorkflowStage.QUERY_REFINEMENT: ['instance_id', 'database_name', 'collection_name', 'generated_query'],
            WorkflowStage.QUERY_EXECUTION: ['instance_id', 'database_name', 'collection_name', 'generated_query'],
            WorkflowStage.RESULT_PRESENTATION: ['instance_id', 'database_name', 'collection_name', 'generated_query'],
            WorkflowStage.COMPLETED: []
        }
    
    def create_workflow(self, session_id: str) -> WorkflowState:
        """创建新的工作流"""
        workflow = WorkflowState(
            current_stage=WorkflowStage.INIT,
            session_id=session_id
        )
        self._workflows[session_id] = workflow
        logger.info("创建新工作流", session_id=session_id)
        return workflow
    
    def get_workflow(self, session_id: str) -> Optional[WorkflowState]:
        """获取工作流状态"""
        return self._workflows.get(session_id)
    
    def get_or_create_workflow(self, session_id: str) -> WorkflowState:
        """获取或创建工作流"""
        workflow = self.get_workflow(session_id)
        if workflow is None:
            workflow = self.create_workflow(session_id)
        return workflow
    
    def can_transition_to(self, session_id: str, target_stage: WorkflowStage) -> Tuple[bool, str]:
        """检查是否可以转换到目标阶段"""
        workflow = self.get_workflow(session_id)
        if not workflow:
            return False, "工作流不存在"
        
        current_stage = workflow.current_stage
        
        # 检查转换规则
        allowed_transitions = self._stage_transitions.get(current_stage, [])
        if target_stage not in allowed_transitions:
            return False, f"不能从 {current_stage.value} 阶段转换到 {target_stage.value} 阶段"
        
        # 检查数据完整性
        requirements = self._stage_requirements.get(target_stage, [])
        for req in requirements:
            if not getattr(workflow, req, None):
                return False, f"缺少必需的数据: {req}"
        
        return True, "可以转换"
    
    def transition_to(self, session_id: str, target_stage: WorkflowStage, 
                     update_data: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
        """转换到目标阶段"""
        can_transition, message = self.can_transition_to(session_id, target_stage)
        
        if not can_transition:
            return False, message
        
        workflow = self._workflows[session_id]
        
        # 记录历史
        workflow.stage_history.append(workflow.current_stage)
        
        # 更新状态
        workflow.current_stage = target_stage
        workflow.updated_at = datetime.now()
        
        # 更新数据
        if update_data:
            for key, value in update_data.items():
                if hasattr(workflow, key):
                    setattr(workflow, key, value)
                else:
                    workflow.stage_data[key] = value
        
        logger.info("工作流阶段转换", 
                   session_id=session_id, 
                   target_stage=target_stage.value)
        
        return True, f"已转换到 {target_stage.value} 阶段"
    
    def get_next_stage_suggestions(self, session_id: str) -> List[Dict[str, str]]:
        """获取下一阶段建议"""
        workflow = self.get_workflow(session_id)
        if not workflow:
            return []
        
        current_stage = workflow.current_stage
        allowed_transitions = self._stage_transitions.get(current_stage, [])
        
        suggestions = []
        for stage in allowed_transitions:
            can_transition, message = self.can_transition_to(session_id, stage)
            
            suggestions.append({
                'stage': stage.value,
                'stage_name': self._get_stage_name(stage),
                'can_transition': can_transition,
                'message': message,
                'description': self._get_stage_description(stage)
            })
        
        return suggestions
    
    def get_current_stage_info(self, session_id: str) -> Dict[str, Any]:
        """获取当前阶段信息"""
        workflow = self.get_workflow(session_id)
        if not workflow:
            return {}
        
        stage = workflow.current_stage
        requirements = self._stage_requirements.get(stage, [])
        
        # 检查数据完整性
        missing_data = []
        for req in requirements:
            if not getattr(workflow, req, None):
                missing_data.append(req)
        
        return {
            'current_stage': stage.value,
            'stage_name': self._get_stage_name(stage),
            'description': self._get_stage_description(stage),
            'requirements': requirements,
            'missing_data': missing_data,
            'is_complete': len(missing_data) == 0,
            'next_suggestions': self.get_next_stage_suggestions(session_id),
            'progress': self._calculate_progress(workflow)
        }
    
    def reset_workflow(self, session_id: str) -> bool:
        """重置工作流"""
        if session_id in self._workflows:
            self._workflows[session_id] = WorkflowState(
                current_stage=WorkflowStage.INIT,
                session_id=session_id
            )
            logger.info("工作流已重置", session_id=session_id)
            return True
        return False
    
    def get_workflow_summary(self, session_id: str) -> Dict[str, Any]:
        """获取工作流摘要"""
        workflow = self.get_workflow(session_id)
        if not workflow:
            return {}
        
        return {
            'session_id': session_id,
            'current_stage': workflow.current_stage.value,
            'stage_name': self._get_stage_name(workflow.current_stage),
            'progress': self._calculate_progress(workflow),
            'instance_id': workflow.instance_id,
            'database_name': workflow.database_name,
            'collection_name': workflow.collection_name,
            'query_description': workflow.query_description,
            'refinement_count': workflow.refinement_count,
            'created_at': workflow.created_at.isoformat() if workflow.created_at else None,
            'updated_at': workflow.updated_at.isoformat() if workflow.updated_at else None,
            'stage_history_count': len(workflow.stage_history)
        }
    
    def get_workflow_data(self, session_id: str) -> Dict[str, Any]:
        """获取工作流数据（兼容性方法，与get_workflow_summary相同）"""
        return self.get_workflow_summary(session_id)
    
    def try_advance_to_stage(self, session_id: str, target_stage: WorkflowStage, 
                           update_data: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
        """尝试推进到目标阶段（兼容性方法，与transition_to相同）"""
        return self.transition_to(session_id, target_stage, update_data)
    
    def update_workflow_data(self, session_id: str, update_data: Dict[str, Any]) -> bool:
        """更新工作流数据"""
        try:
            workflow = self.get_workflow(session_id)
            if not workflow:
                logger.warning(f"Workflow not found for session {session_id}")
                return False
            
            # 更新工作流状态中的数据
            for key, value in update_data.items():
                if hasattr(workflow, key):
                    setattr(workflow, key, value)
                    logger.debug(f"Updated workflow {session_id}: {key} = {value}")
            
            # 更新时间戳
            workflow.updated_at = datetime.now()
            
            # 保存更新后的工作流状态
            self.workflows[session_id] = workflow
            
            logger.info(f"Successfully updated workflow data for session {session_id}", 
                       extra={"session_id": session_id, "updates": update_data})
            return True
            
        except Exception as e:
            logger.error(f"Failed to update workflow data for session {session_id}: {e}", 
                        extra={"session_id": session_id, "error": str(e)})
            return False
    
    def _get_stage_name(self, stage: WorkflowStage) -> str:
        """获取阶段中文名称"""
        stage_names = {
            WorkflowStage.INIT: "初始化",
            WorkflowStage.INSTANCE_ANALYSIS: "分析实例",
            WorkflowStage.INSTANCE_DISCOVERY: "发现实例",
            WorkflowStage.INSTANCE_SELECTION: "选择实例",
            WorkflowStage.DATABASE_ANALYSIS: "分析数据库",
            WorkflowStage.DATABASE_DISCOVERY: "发现数据库",
            WorkflowStage.DATABASE_SELECTION: "选择数据库",
            WorkflowStage.COLLECTION_ANALYSIS: "分析集合",
            WorkflowStage.COLLECTION_DISCOVERY: "发现集合",
            WorkflowStage.COLLECTION_SELECTION: "选择集合",
            WorkflowStage.FIELD_ANALYSIS: "分析字段",
            WorkflowStage.QUERY_GENERATION: "生成查询",
            WorkflowStage.QUERY_REFINEMENT: "优化查询",
            WorkflowStage.QUERY_EXECUTION: "执行查询",
            WorkflowStage.RESULT_PRESENTATION: "展示结果",
            WorkflowStage.COMPLETED: "完成"
        }
        return stage_names.get(stage, stage.value)
    
    def _get_stage_description(self, stage: WorkflowStage) -> str:
        """获取阶段描述"""
        descriptions = {
            WorkflowStage.INIT: "开始新的查询会话",
            WorkflowStage.INSTANCE_ANALYSIS: "分析可用的MongoDB实例并更新语义库",
            WorkflowStage.INSTANCE_DISCOVERY: "发现可用的MongoDB实例",
            WorkflowStage.INSTANCE_SELECTION: "选择要查询的MongoDB实例",
            WorkflowStage.DATABASE_ANALYSIS: "分析实例中的数据库并更新语义库",
            WorkflowStage.DATABASE_DISCOVERY: "发现实例中的数据库",
            WorkflowStage.DATABASE_SELECTION: "选择要查询的数据库",
            WorkflowStage.COLLECTION_ANALYSIS: "分析数据库中的集合并更新语义库",
            WorkflowStage.COLLECTION_DISCOVERY: "发现数据库中的集合",
            WorkflowStage.COLLECTION_SELECTION: "选择要查询的集合",
            WorkflowStage.FIELD_ANALYSIS: "分析集合中的字段结构并更新语义库",
            WorkflowStage.QUERY_GENERATION: "基于需求生成MongoDB查询语句",
            WorkflowStage.QUERY_REFINEMENT: "根据用户反馈优化查询语句",
            WorkflowStage.QUERY_EXECUTION: "执行查询并获取结果",
            WorkflowStage.RESULT_PRESENTATION: "以用户友好的方式展示查询结果",
            WorkflowStage.COMPLETED: "查询流程完成"
        }
        return descriptions.get(stage, "")
    
    def _calculate_progress(self, workflow: WorkflowState) -> float:
        """计算工作流进度"""
        all_stages = list(WorkflowStage)
        current_index = all_stages.index(workflow.current_stage)
        return round(current_index / (len(all_stages) - 1) * 100, 1)
    
    def validate_tool_call(self, session_id: str, tool_name: str) -> Tuple[bool, str, Dict[str, Any]]:
        """验证工具调用是否符合当前工作流阶段"""
        workflow = self.get_workflow(session_id)
        if not workflow:
            # 如果没有工作流，创建一个新的
            workflow = self.create_workflow(session_id)
        
        current_stage = workflow.current_stage
        
        # 定义工具与阶段的映射关系
        tool_stage_mapping = {
            'discover_instances': [WorkflowStage.INIT, WorkflowStage.INSTANCE_ANALYSIS],
            'select_instance': [WorkflowStage.INSTANCE_DISCOVERY],
            'select_database': [WorkflowStage.INSTANCE_SELECTION],
            'discover_databases': [WorkflowStage.INSTANCE_SELECTION, WorkflowStage.DATABASE_ANALYSIS],
            'analyze_collection': [WorkflowStage.COLLECTION_ANALYSIS],
            'select_collection': [WorkflowStage.COLLECTION_SELECTION],
            'analyze_fields': [WorkflowStage.FIELD_ANALYSIS],
            'generate_query': [WorkflowStage.QUERY_GENERATION],
            'refine_query': [WorkflowStage.QUERY_REFINEMENT],
            'confirm_query': [WorkflowStage.QUERY_EXECUTION],
            'present_results': [WorkflowStage.RESULT_PRESENTATION],
            'workflow_status': [],  # 可以在任何阶段调用
            'workflow_reset': []    # 可以在任何阶段调用
        }
        
        allowed_stages = tool_stage_mapping.get(tool_name, [])
        
        # 特殊工具可以在任何阶段调用
        if not allowed_stages:
            return True, "工具调用允许", self.get_current_stage_info(session_id)
        
        if current_stage not in allowed_stages:
            expected_stages = [self._get_stage_name(stage) for stage in allowed_stages]
            current_stage_info = self.get_current_stage_info(session_id)
            
            return False, (
                f"当前阶段 '{self._get_stage_name(current_stage)}' 不允许调用工具 '{tool_name}'。\n"
                f"该工具应在以下阶段调用: {', '.join(expected_stages)}"
            ), current_stage_info
        
        return True, "工具调用符合流程要求", self.get_current_stage_info(session_id)
    
    def _get_stage_for_tool(self, tool_name: str) -> str:
        """根据工具名称获取对应的工作流阶段"""
        stage_mapping = {
            'discover_instances': 'discovery',
            'discover_databases': 'discovery', 
            'collection_analysis': 'analysis',
            'query_generation': 'generation',
            'unified_semantic': 'semantic_analysis',
            'workflow_status': 'management',
            'workflow_reset': 'management',
            'select_instance': 'discovery',
            'select_database': 'selection'
        }
        return stage_mapping.get(tool_name, 'execution')
    
    def get_flexible_stage_mapping(self, tool_name: str, context: Dict[str, Any] = None) -> str:
        """灵活的阶段映射，支持上下文相关的阶段判断"""
        # 基础映射
        base_stage = self._get_stage_for_tool(tool_name)
        
        # 根据上下文调整阶段
        if context:
            # 如果是语义分析工具，根据操作类型细分阶段
            if tool_name == 'unified_semantic':
                operation = context.get('operation', '')
                if operation in ['view', 'search']:
                    return 'semantic_view'
                elif operation in ['update', 'batch_analyze']:
                    return 'semantic_update'
            
            # 如果是查询生成，根据查询类型细分
            elif tool_name == 'query_generation':
                query_type = context.get('query_type', '')
                if query_type in ['find', 'count']:
                    return 'query_basic'
                elif query_type in ['aggregate', 'distinct']:
                    return 'query_advanced'
        
        return base_stage
    
    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any], 
                          context_manager: Any = None) -> Dict[str, Any]:
        """执行工具并更新工作流状态"""
        try:
            # 获取工具对应的阶段（支持灵活映射）
            stage = self.get_flexible_stage_mapping(tool_name, arguments)
            
            # 预处理参数
            processed_arguments = await self._preprocess_arguments(tool_name, arguments, context_manager)
            
            # 执行工具
            result = await self._execute_tool_with_context(tool_name, processed_arguments, context_manager)
            
            return result
            
        except Exception as e:
            raise
    
    async def _preprocess_arguments(self, tool_name: str, arguments: Dict[str, Any], 
                                  context_manager: Any = None) -> Dict[str, Any]:
        """预处理参数，确保参数顺序和类型正确"""
        processed = arguments.copy()
        
        # 类型转换
        if 'limit' in processed and isinstance(processed['limit'], str):
            try:
                processed['limit'] = int(processed['limit'])
            except ValueError:
                processed['limit'] = 10  # 默认值
        
        if 'skip' in processed and isinstance(processed['skip'], str):
            try:
                processed['skip'] = int(processed['skip'])
            except ValueError:
                processed['skip'] = 0  # 默认值
        
        # 从上下文推断缺失参数
        if context_manager and hasattr(context_manager, 'infer_missing_parameters'):
            inferred = context_manager.infer_missing_parameters()
            for key, value in inferred.items():
                if key not in processed or processed[key] is None:
                    processed[key] = value
        
        return processed
    
    async def _execute_tool_with_context(self, tool_name: str, arguments: Dict[str, Any], 
                                       context_manager: Any = None) -> Dict[str, Any]:
        """带上下文的工具执行"""
        # 这里应该调用实际的工具执行逻辑
        # 暂时返回一个模拟结果
        return {
            'tool': tool_name,
            'arguments': arguments,
            'status': 'success',
            'timestamp': datetime.now().isoformat()
        }


# 全局工作流管理器实例
global_workflow_manager = WorkflowManager()


def get_workflow_manager() -> WorkflowManager:
    """获取全局工作流管理器"""
    return global_workflow_manager