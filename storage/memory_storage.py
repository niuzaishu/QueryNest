# -*- coding: utf-8 -*-
"""
工作流状态内存存储实现

提供基于内存的工作流状态存储
"""

import asyncio
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
import structlog

from utils.workflow_state import WorkflowState
from storage.workflow_state_storage_factory import WorkflowStateStorage

logger = structlog.get_logger(__name__)


class MemoryWorkflowStateStorage(WorkflowStateStorage):
    """基于内存的工作流状态存储"""
    
    def __init__(self, **kwargs):
        """初始化内存存储"""
        self._storage = {}  # session_id -> WorkflowState
        self._metadata = {}  # session_id -> 元数据
        self._lock = asyncio.Lock()
    
    async def save(self, state: WorkflowState) -> bool:
        """保存工作流状态"""
        session_id = state.session_id
        
        async with self._lock:
            # 保存状态和元数据
            self._storage[session_id] = state
            self._metadata[session_id] = {
                'last_saved': datetime.now(),
                'save_count': self._metadata.get(session_id, {}).get('save_count', 0) + 1
            }
            
            logger.debug("工作流状态已保存到内存", session_id=session_id)
            return True
    
    async def load(self, session_id: str) -> Optional[WorkflowState]:
        """加载工作流状态"""
        async with self._lock:
            if session_id not in self._storage:
                return None
            
            # 更新元数据
            self._metadata[session_id]['last_loaded'] = datetime.now()
            self._metadata[session_id]['load_count'] = self._metadata[session_id].get('load_count', 0) + 1
            
            # 返回状态的深拷贝，避免外部修改
            return self._storage[session_id]
    
    async def delete(self, session_id: str) -> bool:
        """删除工作流状态"""
        async with self._lock:
            if session_id in self._storage:
                del self._storage[session_id]
                del self._metadata[session_id]
                logger.debug("工作流状态已从内存删除", session_id=session_id)
                return True
            return False
    
    async def exists(self, session_id: str) -> bool:
        """检查工作流状态是否存在"""
        async with self._lock:
            return session_id in self._storage
    
    async def list_sessions(self) -> List[Dict[str, Any]]:
        """列出所有会话"""
        async with self._lock:
            result = []
            
            for session_id, state in self._storage.items():
                meta = self._metadata.get(session_id, {})
                
                result.append({
                    'session_id': session_id,
                    'current_stage': state.current_stage.value,
                    'last_saved': meta.get('last_saved').isoformat() if meta.get('last_saved') else None,
                    'last_loaded': meta.get('last_loaded').isoformat() if meta.get('last_loaded') else None,
                    'save_count': meta.get('save_count', 0),
                    'load_count': meta.get('load_count', 0)
                })
            
            return result
    
    async def cleanup(self, days: int = 30) -> int:
        """清理旧的会话"""
        async with self._lock:
            now = datetime.now()
            cutoff = now.timestamp() - (days * 24 * 60 * 60)
            
            to_delete = []
            for session_id, meta in self._metadata.items():
                last_activity = max(
                    meta.get('last_saved', datetime.fromtimestamp(0)),
                    meta.get('last_loaded', datetime.fromtimestamp(0))
                )
                
                if last_activity.timestamp() < cutoff:
                    to_delete.append(session_id)
            
            # 删除过期的会话
            for session_id in to_delete:
                del self._storage[session_id]
                del self._metadata[session_id]
                
            count = len(to_delete)
            if count > 0:
                logger.info(f"已从内存清理{count}个过期会话", days=days)
                
            return count
    
    async def backup(self) -> bool:
        """备份所有会话（内存存储不需要备份）"""
        logger.info("内存存储无需备份")
        return True
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取存储统计信息"""
        async with self._lock:
            return {
                'session_count': len(self._storage),
                'memory_usage_estimate': sum(len(str(s.to_dict())) for s in self._storage.values())
            }