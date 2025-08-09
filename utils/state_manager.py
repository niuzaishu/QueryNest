"""轻量级状态持久化管理器"""

import json
import os
from datetime import datetime
from typing import Dict, Any, Optional, List
import asyncio
from pathlib import Path
import structlog
from enum import Enum
from dataclasses import dataclass

logger = structlog.get_logger(__name__)

class WorkflowState(Enum):
    """工作流状态枚举"""
    INITIAL = "initial"
    DISCOVERING_INSTANCES = "discovering_instances"
    INSTANCE_SELECTED = "instance_selected"
    DISCOVERING_DATABASES = "discovering_databases"
    DATABASE_SELECTED = "database_selected"
    ANALYZING_COLLECTIONS = "analyzing_collections"
    COLLECTION_SELECTED = "collection_selected"
    SEMANTIC_ANALYSIS = "semantic_analysis"
    GENERATING_QUERY = "generating_query"
    QUERY_READY = "query_ready"
    COMPLETED = "completed"
    ERROR = "error"

@dataclass
class StateTransition:
    """状态转换记录"""
    from_state: WorkflowState
    to_state: WorkflowState
    timestamp: datetime
    context: Dict[str, Any]

class SimpleWorkflowStateManager:
    """简单的工作流状态管理器
    
    使用文件系统存储状态，内存缓存提升性能
    """
    
    def __init__(self, state_dir: str = "workflow_states"):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(exist_ok=True)
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_timestamps: Dict[str, datetime] = {}
        self._lock = asyncio.Lock()
        
    async def save_state(self, workflow_id: str, state: Dict[str, Any]) -> bool:
        """保存工作流状态"""
        async with self._lock:
            try:
                # 添加时间戳
                state_with_meta = {
                    "workflow_id": workflow_id,
                    "state": state,
                    "timestamp": datetime.now().isoformat(),
                    "version": state.get("version", 1)
                }
                
                # 保存到文件
                state_file = self.state_dir / f"{workflow_id}.json"
                with open(state_file, 'w', encoding='utf-8') as f:
                    json.dump(state_with_meta, f, indent=2, ensure_ascii=False)
                
                # 更新内存缓存
                self._memory_cache[workflow_id] = state_with_meta
                self._cache_timestamps[workflow_id] = datetime.now()
                
                logger.info(f"工作流状态已保存: {workflow_id}")
                return True
                
            except Exception as e:
                logger.error(f"保存工作流状态失败: {workflow_id}", error=str(e))
                return False
    
    async def load_state(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """加载工作流状态"""
        async with self._lock:
            try:
                # 先检查内存缓存
                if workflow_id in self._memory_cache:
                    cache_time = self._cache_timestamps.get(workflow_id)
                    if cache_time and (datetime.now() - cache_time).total_seconds() < 300:  # 5分钟缓存
                        logger.debug(f"从缓存加载工作流状态: {workflow_id}")
                        return self._memory_cache[workflow_id]["state"]
                
                # 从文件加载
                state_file = self.state_dir / f"{workflow_id}.json"
                if not state_file.exists():
                    logger.debug(f"工作流状态文件不存在: {workflow_id}")
                    return None
                
                with open(state_file, 'r', encoding='utf-8') as f:
                    state_with_meta = json.load(f)
                
                # 更新缓存
                self._memory_cache[workflow_id] = state_with_meta
                self._cache_timestamps[workflow_id] = datetime.now()
                
                logger.debug(f"从文件加载工作流状态: {workflow_id}")
                return state_with_meta["state"]
                
            except Exception as e:
                logger.error(f"加载工作流状态失败: {workflow_id}", error=str(e))
                return None
    
    async def delete_state(self, workflow_id: str) -> bool:
        """删除工作流状态"""
        async with self._lock:
            try:
                # 删除文件
                state_file = self.state_dir / f"{workflow_id}.json"
                if state_file.exists():
                    state_file.unlink()
                
                # 清除缓存
                self._memory_cache.pop(workflow_id, None)
                self._cache_timestamps.pop(workflow_id, None)
                
                logger.info(f"工作流状态已删除: {workflow_id}")
                return True
                
            except Exception as e:
                logger.error(f"删除工作流状态失败: {workflow_id}", error=str(e))
                return False
    
    async def list_workflows(self) -> list[str]:
        """列出所有工作流ID"""
        try:
            workflow_ids = []
            for state_file in self.state_dir.glob("*.json"):
                workflow_id = state_file.stem
                workflow_ids.append(workflow_id)
            
            return sorted(workflow_ids)
            
        except Exception as e:
            logger.error(f"列出工作流失败", error=str(e))
            return []
    
    async def get_workflow_info(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """获取工作流基本信息"""
        try:
            state_file = self.state_dir / f"{workflow_id}.json"
            if not state_file.exists():
                return None
            
            with open(state_file, 'r', encoding='utf-8') as f:
                state_with_meta = json.load(f)
            
            return {
                "workflow_id": workflow_id,
                "timestamp": state_with_meta.get("timestamp"),
                "version": state_with_meta.get("version", 1),
                "file_size": state_file.stat().st_size
            }
            
        except Exception as e:
            logger.error(f"获取工作流信息失败: {workflow_id}", error=str(e))
            return None
    
    async def cleanup_old_states(self, max_age_days: int = 30) -> int:
        """清理过期状态"""
        try:
            cleaned_count = 0
            cutoff_time = datetime.now().timestamp() - (max_age_days * 24 * 3600)
            
            for state_file in self.state_dir.glob("*.json"):
                if state_file.stat().st_mtime < cutoff_time:
                    workflow_id = state_file.stem
                    if await self.delete_state(workflow_id):
                        cleaned_count += 1
            
            logger.info(f"清理了 {cleaned_count} 个过期工作流状态")
            return cleaned_count
            
        except Exception as e:
            logger.error(f"清理过期状态失败", error=str(e))
            return 0
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        return {
            "cached_workflows": len(self._memory_cache),
            "cache_timestamps": len(self._cache_timestamps),
            "state_dir": str(self.state_dir),
            "total_files": len(list(self.state_dir.glob("*.json")))
        }

class WorkflowStateMachine:
    """工作流状态机"""
    
    def __init__(self, workflow_id: str, initial_state: WorkflowState = WorkflowState.INITIAL):
        self.workflow_id = workflow_id
        self.current_state = initial_state
        self.state_data: Dict[str, Any] = {}
        self.transition_history: List[StateTransition] = []
        
    def transition_to(self, new_state: WorkflowState, context: Dict[str, Any] = None) -> bool:
        """转换到新状态"""
        if not self._can_transition_to(new_state):
            return False
        
        # 预处理上下文数据
        processed_context = self._preprocess_transition_context(context or {})
        
        # 记录状态转换
        transition = StateTransition(
            from_state=self.current_state,
            to_state=new_state,
            timestamp=datetime.now(),
            context=processed_context
        )
        
        self.transition_history.append(transition)
        self.current_state = new_state
        
        # 更新状态数据
        self._update_state_data(processed_context)
        
        return True
    
    def _preprocess_transition_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """预处理状态转换上下文"""
        processed = context.copy()
        
        # 确保关键参数的正确性
        if 'instance_id' in processed:
            processed['instance_id'] = str(processed['instance_id']).strip()
        
        if 'database_name' in processed:
            processed['database_name'] = str(processed['database_name']).strip()
        
        if 'collection_name' in processed:
            processed['collection_name'] = str(processed['collection_name']).strip()
        
        # 添加时间戳
        processed['transition_timestamp'] = datetime.now().isoformat()
        
        return processed
    
    def _update_state_data(self, context: Dict[str, Any]) -> None:
        """更新状态数据"""
        # 智能合并状态数据
        for key, value in context.items():
            if key in ['instance_id', 'database_name', 'collection_name']:
                # 核心参数直接更新
                self.state_data[key] = value
            elif key.startswith('temp_'):
                # 临时参数存储在临时区域
                if 'temp_data' not in self.state_data:
                    self.state_data['temp_data'] = {}
                self.state_data['temp_data'][key] = value
            else:
                # 其他参数正常更新
                self.state_data[key] = value
    
    def _can_transition_to(self, new_state: WorkflowState) -> bool:
        """检查是否可以转换到指定状态"""
        available_transitions = self.get_available_transitions()
        return new_state in available_transitions
    
    def get_available_transitions(self) -> List[WorkflowState]:
        """获取当前状态可以转换到的状态列表"""
        transitions = {
            WorkflowState.INITIAL: [WorkflowState.DISCOVERING_INSTANCES],
            WorkflowState.DISCOVERING_INSTANCES: [
                WorkflowState.INSTANCE_SELECTED,
                WorkflowState.ERROR
            ],
            WorkflowState.INSTANCE_SELECTED: [
                WorkflowState.DISCOVERING_DATABASES,
                WorkflowState.ERROR
            ],
            WorkflowState.DISCOVERING_DATABASES: [
                WorkflowState.DATABASE_SELECTED,
                WorkflowState.ERROR
            ],
            WorkflowState.DATABASE_SELECTED: [
                WorkflowState.ANALYZING_COLLECTIONS,
                WorkflowState.ERROR
            ],
            WorkflowState.ANALYZING_COLLECTIONS: [
                WorkflowState.COLLECTION_SELECTED,
                WorkflowState.ERROR
            ],
            WorkflowState.COLLECTION_SELECTED: [
                WorkflowState.GENERATING_QUERY,
                WorkflowState.SEMANTIC_ANALYSIS,
                WorkflowState.ERROR
            ],
            WorkflowState.SEMANTIC_ANALYSIS: [
                WorkflowState.GENERATING_QUERY,
                WorkflowState.COLLECTION_SELECTED,
                WorkflowState.ERROR
            ],
            WorkflowState.GENERATING_QUERY: [
                WorkflowState.QUERY_READY,
                WorkflowState.COLLECTION_SELECTED,
                WorkflowState.ERROR
            ],
            WorkflowState.QUERY_READY: [
                WorkflowState.COMPLETED,
                WorkflowState.GENERATING_QUERY,
                WorkflowState.ERROR
            ],
            WorkflowState.ERROR: [
                WorkflowState.INITIAL,
                WorkflowState.DISCOVERING_INSTANCES,
                WorkflowState.INSTANCE_SELECTED,
                WorkflowState.DATABASE_SELECTED,
                WorkflowState.COLLECTION_SELECTED
            ],
            WorkflowState.COMPLETED: [WorkflowState.INITIAL]
        }
        
        return transitions.get(self.current_state, [])
    
    def get_smart_transitions(self, context: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """获取智能状态转换建议"""
        available_states = self.get_available_transitions()
        suggestions = []
        
        for state in available_states:
            suggestion = {
                'state': state,
                'name': state.value,
                'description': self._get_state_description(state),
                'required_context': self._get_required_context_for_state(state),
                'can_transition': self._can_transition_with_context(state, context or {})
            }
            suggestions.append(suggestion)
        
        return suggestions
    
    def _get_state_description(self, state: WorkflowState) -> str:
        """获取状态描述"""
        descriptions = {
            WorkflowState.DISCOVERING_INSTANCES: "发现MongoDB实例",
            WorkflowState.INSTANCE_SELECTED: "已选择实例",
            WorkflowState.DISCOVERING_DATABASES: "发现数据库",
            WorkflowState.DATABASE_SELECTED: "已选择数据库",
            WorkflowState.ANALYZING_COLLECTIONS: "分析集合",
            WorkflowState.COLLECTION_SELECTED: "已选择集合",
            WorkflowState.SEMANTIC_ANALYSIS: "语义分析",
            WorkflowState.GENERATING_QUERY: "生成查询",
            WorkflowState.QUERY_READY: "查询就绪",
            WorkflowState.COMPLETED: "完成",
            WorkflowState.ERROR: "错误状态"
        }
        return descriptions.get(state, state.value)
    
    def _get_required_context_for_state(self, state: WorkflowState) -> List[str]:
        """获取状态转换所需的上下文参数"""
        requirements = {
            WorkflowState.INSTANCE_SELECTED: ['instance_id'],
            WorkflowState.DATABASE_SELECTED: ['instance_id', 'database_name'],
            WorkflowState.COLLECTION_SELECTED: ['instance_id', 'database_name', 'collection_name'],
            WorkflowState.GENERATING_QUERY: ['instance_id', 'database_name', 'collection_name'],
            WorkflowState.QUERY_READY: ['instance_id', 'database_name', 'collection_name', 'query']
        }
        return requirements.get(state, [])
    
    def _can_transition_with_context(self, state: WorkflowState, context: Dict[str, Any]) -> bool:
        """检查是否可以在给定上下文下转换到指定状态"""
        if not self._can_transition_to(state):
            return False
        
        required_context = self._get_required_context_for_state(state)
        current_data = {**self.state_data, **context}
        
        for param in required_context:
            if param not in current_data or not current_data[param]:
                return False
        
        return True
    
    def get_state_summary(self) -> Dict[str, Any]:
        """获取状态摘要"""
        return {
            'workflow_id': self.workflow_id,
            'current_state': self.current_state.value,
            'state_data': self.state_data,
            'transition_count': len(self.transition_history),
            'available_transitions': [s.value for s in self.get_available_transitions()]
        }