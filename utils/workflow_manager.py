# -*- coding: utf-8 -*-
"""工作流管理器 - 约束和引导用户按照预期流程操作"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import json
import structlog
from datetime import datetime, timedelta

logger = structlog.get_logger(__name__)


class WorkflowStage(Enum):
    """精简的工作流阶段枚举"""
    INIT = "init"                           # 初始化
    INSTANCE_ANALYSIS = "instance_analysis" # 发现和分析实例
    INSTANCE_SELECTION = "instance_selection" # 选择实例
    DATABASE_ANALYSIS = "database_analysis" # 发现和分析数据库
    DATABASE_SELECTION = "database_selection" # 选择数据库
    COLLECTION_ANALYSIS = "collection_analysis" # 发现和分析集合
    COLLECTION_SELECTION = "collection_selection" # 选择集合
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
    
    def __init__(self, storage=None):
        self._workflows: Dict[str, WorkflowState] = {}  # 内存缓存
        self.storage = storage  # 持久化存储
        self._cache_expiry = {}  # 缓存过期时间
        
        # 定义灵活的阶段转换规则 - 支持跳跃和回退
        self._stage_transitions = {
            WorkflowStage.INIT: [
                WorkflowStage.INSTANCE_ANALYSIS,    # 标准路径
                WorkflowStage.QUERY_GENERATION       # 快速路径（如果有完整上下文）
            ],
            WorkflowStage.INSTANCE_ANALYSIS: [
                WorkflowStage.INSTANCE_SELECTION,   # 选择实例
                WorkflowStage.DATABASE_ANALYSIS,    # 快速跳转（如果只有一个实例）
                WorkflowStage.QUERY_GENERATION       # 超快路径
            ],
            WorkflowStage.INSTANCE_SELECTION: [
                WorkflowStage.DATABASE_ANALYSIS,    # 标准下一步：分析数据库
                WorkflowStage.DATABASE_SELECTION,   # 直接选择数据库（如果已知数据库列表）
                WorkflowStage.COLLECTION_ANALYSIS,  # 跳过数据库选择（如果明确数据库和集合）
                WorkflowStage.QUERY_GENERATION,     # 直接查询（如果有完整上下文）
                WorkflowStage.INSTANCE_ANALYSIS     # 重新选择实例
            ],
            WorkflowStage.DATABASE_ANALYSIS: [
                WorkflowStage.DATABASE_SELECTION,   # 选择数据库
                WorkflowStage.COLLECTION_ANALYSIS,  # 快速跳转
                WorkflowStage.INSTANCE_SELECTION    # 回退
            ],
            WorkflowStage.DATABASE_SELECTION: [
                WorkflowStage.COLLECTION_ANALYSIS,  # 标准下一步：分析集合
                WorkflowStage.COLLECTION_SELECTION, # 直接选择集合（如果已知集合列表）
                WorkflowStage.QUERY_GENERATION,     # 跳过字段分析（如果有完整上下文）
                WorkflowStage.DATABASE_ANALYSIS     # 重新分析数据库
            ],
            WorkflowStage.COLLECTION_ANALYSIS: [
                WorkflowStage.COLLECTION_SELECTION, # 选择集合
                WorkflowStage.QUERY_GENERATION,     # 直接查询
                WorkflowStage.DATABASE_SELECTION    # 回退
            ],
            WorkflowStage.COLLECTION_SELECTION: [
                WorkflowStage.FIELD_ANALYSIS,       # 标准路径
                WorkflowStage.QUERY_GENERATION,     # 跳过字段分析
                WorkflowStage.COLLECTION_ANALYSIS   # 重新选择集合
            ],
            WorkflowStage.FIELD_ANALYSIS: [
                WorkflowStage.QUERY_GENERATION,     # 标准下一步
                WorkflowStage.COLLECTION_SELECTION  # 回退
            ],
            WorkflowStage.QUERY_GENERATION: [
                WorkflowStage.QUERY_REFINEMENT,     # 优化查询
                WorkflowStage.QUERY_EXECUTION,      # 直接执行
                WorkflowStage.FIELD_ANALYSIS        # 重新分析字段
            ],
            WorkflowStage.QUERY_REFINEMENT: [
                WorkflowStage.QUERY_GENERATION,     # 重新生成
                WorkflowStage.QUERY_EXECUTION       # 执行优化后查询
            ],
            WorkflowStage.QUERY_EXECUTION: [
                WorkflowStage.RESULT_PRESENTATION,  # 展示结果
                WorkflowStage.QUERY_REFINEMENT,     # 继续优化
                WorkflowStage.QUERY_GENERATION      # 重新生成查询
            ],
            WorkflowStage.RESULT_PRESENTATION: [
                WorkflowStage.COMPLETED,            # 完成
                WorkflowStage.QUERY_GENERATION,     # 新查询
                WorkflowStage.QUERY_REFINEMENT      # 改进查询
            ],
            WorkflowStage.COMPLETED: [
                WorkflowStage.INIT                  # 重新开始
            ]
        }
        
        # 定义每个阶段需要的数据（简化后的要求）
        self._stage_requirements = {
            WorkflowStage.INIT: [],
            WorkflowStage.INSTANCE_ANALYSIS: [],
            WorkflowStage.INSTANCE_SELECTION: [],
            WorkflowStage.DATABASE_ANALYSIS: ['instance_id'],
            WorkflowStage.DATABASE_SELECTION: ['instance_id'],
            WorkflowStage.COLLECTION_ANALYSIS: ['instance_id', 'database_name'],
            WorkflowStage.COLLECTION_SELECTION: ['instance_id', 'database_name'],
            WorkflowStage.FIELD_ANALYSIS: ['instance_id', 'database_name', 'collection_name'],
            WorkflowStage.QUERY_GENERATION: ['instance_id', 'database_name', 'collection_name'],
            WorkflowStage.QUERY_REFINEMENT: ['instance_id', 'database_name', 'collection_name', 'generated_query'],
            WorkflowStage.QUERY_EXECUTION: ['instance_id', 'database_name', 'collection_name', 'generated_query'],
            WorkflowStage.RESULT_PRESENTATION: ['instance_id', 'database_name', 'collection_name', 'generated_query'],
            WorkflowStage.COMPLETED: []
        }
    
    async def create_workflow(self, session_id: str) -> WorkflowState:
        """创建新的工作流"""
        workflow = WorkflowState(
            current_stage=WorkflowStage.INIT,
            session_id=session_id
        )
        
        # 存储到缓存和持久化存储
        self._workflows[session_id] = workflow
        if self.storage:
            await self.storage.save_workflow_state(workflow)
        
        logger.info("创建新工作流", session_id=session_id)
        return workflow
    
    async def get_workflow(self, session_id: str) -> Optional[WorkflowState]:
        """获取工作流状态"""
        # 先从缓存获取
        if session_id in self._workflows:
            return self._workflows[session_id]
        
        # 缓存中没有，尝试从持久化存储加载
        if self.storage:
            workflow = await self.storage.load_workflow_state(session_id)
            if workflow:
                # 加载到缓存
                self._workflows[session_id] = workflow
                logger.debug("从持久化存储加载工作流", session_id=session_id)
                return workflow
        
        return None
    
    async def get_or_create_workflow(self, session_id: str) -> WorkflowState:
        """获取或创建工作流"""
        workflow = await self.get_workflow(session_id)
        if workflow is None:
            workflow = await self.create_workflow(session_id)
        return workflow
    
    async def can_transition_to(self, session_id: str, target_stage: WorkflowStage) -> Tuple[bool, str]:
        """检查是否可以转换到目标阶段"""
        workflow = await self.get_workflow(session_id)
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
    
    async def transition_to(self, session_id: str, target_stage: WorkflowStage, 
                           update_data: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
        """转换到目标阶段"""
        can_transition, message = await self.can_transition_to(session_id, target_stage)
        
        if not can_transition:
            return False, message
        
        workflow = await self.get_workflow(session_id)
        if not workflow:
            return False, "工作流不存在"
        
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
        
        # 保存到持久化存储
        if self.storage:
            await self.storage.save_workflow_state(workflow)
        
        logger.info("工作流阶段转换", 
                   session_id=session_id, 
                   target_stage=target_stage.value)
        
        return True, f"已转换到 {target_stage.value} 阶段"
    
    async def get_next_stage_suggestions(self, session_id: str) -> List[Dict[str, str]]:
        """获取下一阶段建议"""
        workflow = await self.get_workflow(session_id)
        if not workflow:
            return []
        
        current_stage = workflow.current_stage
        allowed_transitions = self._stage_transitions.get(current_stage, [])
        
        suggestions = []
        for stage in allowed_transitions:
            can_transition, message = await self.can_transition_to(session_id, stage)
            
            suggestions.append({
                'stage': stage.value,
                'stage_name': self._get_stage_name(stage),
                'can_transition': can_transition,
                'message': message,
                'description': self._get_stage_description(stage)
            })
        
        return suggestions
    
    async def get_current_stage_info(self, session_id: str) -> Dict[str, Any]:
        """获取当前阶段信息"""
        workflow = await self.get_workflow(session_id)
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
            'next_suggestions': await self.get_next_stage_suggestions(session_id),
            'progress': self._calculate_progress(workflow)
        }
    
    async def reset_workflow(self, session_id: str) -> bool:
        """重置工作流"""
        if session_id in self._workflows:
            workflow = WorkflowState(
                current_stage=WorkflowStage.INIT,
                session_id=session_id
            )
            self._workflows[session_id] = workflow
            
            # 同时更新持久化存储
            if self.storage:
                await self.storage.save_workflow_state(workflow)
            
            logger.info("工作流已重置", session_id=session_id)
            return True
        return False
    
    async def get_workflow_summary(self, session_id: str) -> Dict[str, Any]:
        """获取工作流摘要"""
        workflow = await self.get_workflow(session_id)
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
    
    async def get_workflow_data(self, session_id: str) -> Dict[str, Any]:
        """获取工作流数据（兼容性方法，与get_workflow_summary相同）"""
        return await self.get_workflow_summary(session_id)
    
    async def try_advance_to_stage(self, session_id: str, target_stage: WorkflowStage, 
                           update_data: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
        """尝试推进到目标阶段（兼容性方法，与transition_to相同）"""
        return await self.transition_to(session_id, target_stage, update_data)
    
    async def update_workflow_data(self, session_id: str, update_data: Dict[str, Any]) -> bool:
        """更新工作流数据"""
        try:
            workflow = await self.get_workflow(session_id)
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
            self._workflows[session_id] = workflow
            
            # 同时更新持久化存储
            if self.storage:
                await self.storage.save_workflow_state(workflow)
            
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
            WorkflowStage.INSTANCE_ANALYSIS: "发现和分析实例",  # 合并功能描述
            WorkflowStage.INSTANCE_SELECTION: "选择实例",
            WorkflowStage.DATABASE_ANALYSIS: "发现和分析数据库",  # 合并功能描述
            WorkflowStage.DATABASE_SELECTION: "选择数据库",
            WorkflowStage.COLLECTION_ANALYSIS: "发现和分析集合",  # 合并功能描述
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
            WorkflowStage.INSTANCE_ANALYSIS: "发现可用的MongoDB实例，分析连接状态并更新语义库",  # 合并描述
            WorkflowStage.INSTANCE_SELECTION: "选择要查询的MongoDB实例",
            WorkflowStage.DATABASE_ANALYSIS: "发现实例中的数据库，分析结构并更新语义库",  # 合并描述
            WorkflowStage.DATABASE_SELECTION: "选择要查询的数据库",
            WorkflowStage.COLLECTION_ANALYSIS: "发现数据库中的集合，分析结构并更新语义库",  # 合并描述
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
        """计算工作流进度（基于精简的13个阶段）"""
        # 定义标准进度路径
        progress_stages = [
            WorkflowStage.INIT,
            WorkflowStage.INSTANCE_ANALYSIS,
            WorkflowStage.INSTANCE_SELECTION,
            WorkflowStage.DATABASE_ANALYSIS,
            WorkflowStage.DATABASE_SELECTION,
            WorkflowStage.COLLECTION_ANALYSIS,
            WorkflowStage.COLLECTION_SELECTION,
            WorkflowStage.FIELD_ANALYSIS,
            WorkflowStage.QUERY_GENERATION,
            WorkflowStage.QUERY_REFINEMENT,
            WorkflowStage.QUERY_EXECUTION,
            WorkflowStage.RESULT_PRESENTATION,
            WorkflowStage.COMPLETED
        ]
        
        try:
            current_index = progress_stages.index(workflow.current_stage)
            return round(current_index / (len(progress_stages) - 1) * 100, 1)
        except ValueError:
            # 如果当前阶段不在标准路径中，基于阶段特征估算进度
            return self._estimate_progress_by_stage_type(workflow.current_stage)
    
    def _estimate_progress_by_stage_type(self, stage: WorkflowStage) -> float:
        """基于阶段类型估算进度"""
        stage_progress_map = {
            WorkflowStage.INIT: 0.0,
            WorkflowStage.INSTANCE_ANALYSIS: 15.0,
            WorkflowStage.INSTANCE_SELECTION: 25.0,
            WorkflowStage.DATABASE_ANALYSIS: 35.0,
            WorkflowStage.DATABASE_SELECTION: 45.0,
            WorkflowStage.COLLECTION_ANALYSIS: 55.0,
            WorkflowStage.COLLECTION_SELECTION: 65.0,
            WorkflowStage.FIELD_ANALYSIS: 75.0,
            WorkflowStage.QUERY_GENERATION: 85.0,
            WorkflowStage.QUERY_REFINEMENT: 90.0,
            WorkflowStage.QUERY_EXECUTION: 95.0,
            WorkflowStage.RESULT_PRESENTATION: 98.0,
            WorkflowStage.COMPLETED: 100.0
        }
        return stage_progress_map.get(stage, 50.0)  # 默认50%
    
    async def validate_tool_call(self, session_id: str, tool_name: str) -> Tuple[bool, str, Dict[str, Any]]:
        """验证工具调用是否符合当前工作流阶段"""
        workflow = await self.get_workflow(session_id)
        if not workflow:
            # 如果没有工作流，创建一个新的
            workflow = await self.create_workflow(session_id)
        
        current_stage = workflow.current_stage
        
        # 定义灵活的工具与阶段映射关系
        tool_stage_mapping = {
            # 发现类工具 - 更宽松的限制
            'discover_instances': [WorkflowStage.INIT, WorkflowStage.INSTANCE_ANALYSIS],
            'discover_databases': [WorkflowStage.INSTANCE_SELECTION, WorkflowStage.DATABASE_ANALYSIS],
            'analyze_collection': [WorkflowStage.DATABASE_SELECTION, WorkflowStage.COLLECTION_ANALYSIS],
            'analyze_fields': [WorkflowStage.COLLECTION_SELECTION, WorkflowStage.FIELD_ANALYSIS],
            
            # 选择类工具 - 更灵活的限制，支持智能跳转
            'select_instance': [WorkflowStage.INIT, WorkflowStage.INSTANCE_ANALYSIS, WorkflowStage.INSTANCE_SELECTION],
            'select_database': [WorkflowStage.INSTANCE_SELECTION, WorkflowStage.DATABASE_ANALYSIS, WorkflowStage.DATABASE_SELECTION],
            'select_collection': [WorkflowStage.INIT, WorkflowStage.DATABASE_SELECTION, WorkflowStage.COLLECTION_ANALYSIS, WorkflowStage.COLLECTION_SELECTION],
            
            # 查询类工具 - 有数据即可使用
            'generate_query': [WorkflowStage.COLLECTION_SELECTION, WorkflowStage.FIELD_ANALYSIS, WorkflowStage.QUERY_GENERATION],
            'refine_query': [WorkflowStage.QUERY_GENERATION, WorkflowStage.QUERY_REFINEMENT],
            'confirm_query': [WorkflowStage.QUERY_GENERATION, WorkflowStage.QUERY_REFINEMENT, WorkflowStage.QUERY_EXECUTION],
            'present_results': [WorkflowStage.QUERY_EXECUTION, WorkflowStage.RESULT_PRESENTATION],
            
            # 无限制工具 - 任何时候都可以调用
            'workflow_status': [],
            'workflow_reset': [],
            'unified_semantic_operations': [],
            'unified_semantic': [],
        }
        
        allowed_stages = tool_stage_mapping.get(tool_name, [])
        
        # 特殊工具可以在任何阶段调用
        if not allowed_stages:
            return True, "工具调用允许", await self.get_current_stage_info(session_id)
        
        # 检查是否可以通过上下文感知跳过阶段限制
        can_skip, skip_reason = await self._can_skip_stage_validation(workflow, tool_name)
        if can_skip:
            return True, f"上下文感知允许: {skip_reason}", await self.get_current_stage_info(session_id)
        
        if current_stage not in allowed_stages:
            expected_stages = [self._get_stage_name(stage) for stage in allowed_stages]
            current_stage_info = await self.get_current_stage_info(session_id)
            
            return False, (
                f"当前阶段 '{self._get_stage_name(current_stage)}' 不允许调用工具 '{tool_name}'。\n"
                f"该工具应在以下阶段调用: {', '.join(expected_stages)}"
            ), current_stage_info
        
        return True, "工具调用符合流程要求", await self.get_current_stage_info(session_id)
    
    async def _can_skip_stage_validation(self, workflow: WorkflowState, tool_name: str) -> tuple[bool, str]:
        """检查是否可以基于上下文跳过阶段验证"""
        
        # 定义需要特定数据的工具及其要求
        tool_requirements = {
            'select_database': ['instance_id'],
            'discover_databases': ['instance_id'],
            'select_collection': ['instance_id', 'database_name'],
            'analyze_collection': ['instance_id', 'database_name'],
            'generate_query': ['instance_id', 'database_name', 'collection_name'],
            'confirm_query': ['instance_id', 'database_name', 'collection_name'],
        }
        
        # 检查是否是需要特殊处理的工具
        if tool_name not in tool_requirements:
            return False, "无需跳过验证"
        
        required_data = tool_requirements[tool_name]
        
        # 检查工作流中是否已有所需数据
        missing_data = []
        for req in required_data:
            if not getattr(workflow, req, None):
                missing_data.append(req)
        
        # 如果所有必需数据都存在，允许跳过阶段限制
        if not missing_data:
            return True, f"已具备所需数据: {', '.join(required_data)}"
        
        return False, f"缺少必需数据: {', '.join(missing_data)}"
    
    async def suggest_next_action(self, session_id: str, user_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """基于当前状态和用户上下文智能推荐下一步操作"""
        workflow = await self.get_workflow(session_id)
        if not workflow:
            return {
                "suggested_tool": "discover_instances",
                "reason": "需要先发现可用的MongoDB实例",
                "can_skip_to": None
            }
        
        current_stage = workflow.current_stage
        
        # 检查是否可以基于用户提供的上下文跳过阶段
        if user_context:
            skip_suggestion = await self._analyze_context_for_skip(workflow, user_context)
            if skip_suggestion:
                return skip_suggestion
        
        # 基于当前阶段推荐标准下一步（简化后的建议）
        standard_suggestions = {
            WorkflowStage.INIT: {
                "suggested_tool": "discover_instances", 
                "reason": "开始查询流程，需要先发现MongoDB实例"
            },
            WorkflowStage.INSTANCE_ANALYSIS: {
                "suggested_tool": "select_instance",
                "reason": "请选择要使用的MongoDB实例"
            },
            WorkflowStage.INSTANCE_SELECTION: {
                "suggested_tool": "discover_databases",
                "reason": "查看选定实例中的可用数据库"
            },
            WorkflowStage.DATABASE_ANALYSIS: {
                "suggested_tool": "select_database",
                "reason": "请选择要查询的数据库"
            },
            WorkflowStage.DATABASE_SELECTION: {
                "suggested_tool": "analyze_collection",
                "reason": "分析数据库中的集合结构"
            },
            WorkflowStage.COLLECTION_ANALYSIS: {
                "suggested_tool": "select_collection",
                "reason": "请选择要查询的集合"
            },
            WorkflowStage.COLLECTION_SELECTION: {
                "suggested_tool": "generate_query",
                "reason": "现在可以生成查询语句"
            }
        }
        
        return standard_suggestions.get(current_stage, {
            "suggested_tool": "workflow_status",
            "reason": "查看当前工作流状态以确定下一步"
        })
    
    async def _analyze_context_for_skip(self, workflow: WorkflowState, user_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """分析用户上下文，判断是否可以跳过某些阶段"""
        
        # 如果用户提供了完整的查询上下文
        if all(key in user_context for key in ['instance_id', 'database_name', 'collection_name']):
            return {
                "suggested_tool": "generate_query",
                "reason": "检测到完整查询上下文，可直接生成查询",
                "can_skip_to": "QUERY_GENERATION",
                "auto_fill_data": {
                    "instance_id": user_context['instance_id'],
                    "database_name": user_context['database_name'], 
                    "collection_name": user_context['collection_name']
                }
            }
        
        # 如果用户提供了实例和数据库信息
        elif all(key in user_context for key in ['instance_id', 'database_name']):
            return {
                "suggested_tool": "analyze_collection",
                "reason": "检测到实例和数据库信息，可直接分析集合",
                "can_skip_to": "COLLECTION_ANALYSIS",
                "auto_fill_data": {
                    "instance_id": user_context['instance_id'],
                    "database_name": user_context['database_name']
                }
            }
        
        # 如果用户只提供了实例信息
        elif 'instance_id' in user_context:
            return {
                "suggested_tool": "discover_databases",
                "reason": "检测到实例信息，可直接查看数据库",
                "can_skip_to": "DATABASE_ANALYSIS",  # 更改为ANALYSIS
                "auto_fill_data": {
                    "instance_id": user_context['instance_id']
                }
            }
        
        return None
    
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
    
    async def delete_workflow(self, session_id: str) -> bool:
        """删除工作流状态"""
        try:
            # 从缓存中删除
            if session_id in self._workflows:
                del self._workflows[session_id]
            
            # 从持久化存储中删除
            if self.storage:
                success = await self.storage.delete_workflow_state(session_id)
                if success:
                    logger.info("工作流状态已删除", session_id=session_id)
                return success
            
            return True
            
        except Exception as e:
            logger.error("删除工作流状态失败", session_id=session_id, error=str(e))
            return False
    
    async def list_all_workflows(self) -> List[Dict[str, Any]]:
        """列出所有工作流状态"""
        try:
            workflows = []
            
            # 获取缓存中的工作流
            for session_id, workflow in self._workflows.items():
                workflows.append({
                    "session_id": session_id,
                    "current_stage": workflow.current_stage.value,
                    "created_at": workflow.created_at,
                    "updated_at": workflow.updated_at,
                    "source": "cache"
                })
            
            # 如果有持久化存储，获取存储中的工作流
            if self.storage:
                stored_sessions = await self.storage.list_sessions()
                for session_info in stored_sessions:
                    # 避免重复添加已经在缓存中的会话
                    if session_info["session_id"] not in self._workflows:
                        workflows.append({
                            **session_info,
                            "source": "storage"
                        })
            
            return sorted(workflows, key=lambda x: x.get("updated_at", ""), reverse=True)
            
        except Exception as e:
            logger.error("列出工作流状态失败", error=str(e))
            return []
    
    async def cleanup_expired_workflows(self, max_age_hours: int = 24) -> int:
        """清理过期的工作流状态"""
        try:
            cleaned_count = 0
            
            # 清理缓存中的过期工作流
            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
            expired_sessions = []
            
            for session_id, workflow in self._workflows.items():
                if workflow.updated_at < cutoff_time:
                    expired_sessions.append(session_id)
            
            for session_id in expired_sessions:
                del self._workflows[session_id]
                cleaned_count += 1
            
            # 清理持久化存储中的过期工作流
            if self.storage:
                storage_cleaned = await self.storage.cleanup_old_sessions(max_age_hours // 24)
                cleaned_count += storage_cleaned
            
            if cleaned_count > 0:
                logger.info(f"清理了 {cleaned_count} 个过期工作流", max_age_hours=max_age_hours)
            
            return cleaned_count
            
        except Exception as e:
            logger.error("清理过期工作流失败", error=str(e))
            return 0
    
    async def backup_all_workflows(self) -> bool:
        """备份所有工作流状态"""
        try:
            if not self.storage:
                return False
            
            backup_count = await self.storage.backup_all_sessions()
            logger.info(f"备份了 {backup_count} 个工作流状态")
            return True
            
        except Exception as e:
            logger.error("备份工作流状态失败", error=str(e))
            return False
    
    def set_storage(self, storage):
        """设置持久化存储"""
        self.storage = storage
        logger.info("工作流管理器存储已配置", 
                   storage_type=storage.__class__.__name__)


# 全局工作流管理器实例
global_workflow_manager = WorkflowManager()


def get_workflow_manager() -> WorkflowManager:
    """获取全局工作流管理器"""
    return global_workflow_manager


def setup_workflow_manager(storage=None) -> WorkflowManager:
    """设置工作流管理器"""
    global global_workflow_manager
    if storage:
        global_workflow_manager.set_storage(storage)
    return global_workflow_manager