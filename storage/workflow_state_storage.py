# -*- coding: utf-8 -*-
"""
工作流状态存储管理器

提供工作流状态的持久化存储和管理功能
"""

import json
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import aiofiles
import structlog
import os

from utils.workflow_manager import WorkflowState, WorkflowStage

logger = structlog.get_logger(__name__)


class WorkflowStateStorage:
    """工作流状态存储管理器"""
    
    def __init__(self, base_path: str = "data/workflow"):
        self.base_path = Path(base_path)
        self.ensure_directory_structure()
        self._file_locks = {}  # 文件锁字典
        
    def ensure_directory_structure(self):
        """确保目录结构存在"""
        self.base_path.mkdir(parents=True, exist_ok=True)
        (self.base_path / "sessions").mkdir(exist_ok=True)
        
        # 创建全局配置文件
        global_config_path = self.base_path / "global_config.json"
        if not global_config_path.exists():
            default_config = {
                "storage": {
                    "base_path": str(self.base_path),
                    "backup_enabled": True,
                    "backup_interval": 3600,
                    "max_backups": 5,
                    "auto_cleanup_sessions": True,
                    "session_ttl_days": 30
                },
                "created_at": datetime.now().isoformat(),
                "version": "1.0.0"
            }
            
            with open(global_config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, ensure_ascii=False, indent=2)
    
    def _get_session_file_path(self, session_id: str) -> Path:
        """获取会话文件路径"""
        return self.base_path / "sessions" / f"{session_id}.json"
    
    async def _acquire_lock(self, file_path: Path):
        """获取文件锁"""
        str_path = str(file_path)
        if str_path not in self._file_locks:
            self._file_locks[str_path] = asyncio.Lock()
        
        await self._file_locks[str_path].acquire()
    
    def _release_lock(self, file_path: Path):
        """释放文件锁"""
        str_path = str(file_path)
        if str_path in self._file_locks:
            self._file_locks[str_path].release()
    
    async def _atomic_write(self, file_path: Path, data: Dict[str, Any]) -> bool:
        """原子性写入文件"""
        temp_path = file_path.with_suffix('.tmp')
        try:
            # 确保目录存在
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            async with aiofiles.open(temp_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2))
            
            # 原子性重命名
            temp_path.replace(file_path)
            return True
        except Exception as e:
            logger.error("原子性写入失败", file_path=str(file_path), error=str(e))
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            return False
    
    async def _read_json_file(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """读取JSON文件"""
        try:
            if not file_path.exists():
                return None
                
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content)
        except Exception as e:
            logger.error("读取JSON文件失败", file_path=str(file_path), error=str(e))
            return None
    
    async def save_workflow_state(self, workflow_state: WorkflowState) -> bool:
        """保存工作流状态"""
        try:
            session_id = workflow_state.session_id
            file_path = self._get_session_file_path(session_id)
            
            # 构建存储数据
            data = workflow_state.to_dict()
            # 添加元数据
            data["_metadata"] = {
                "storage_version": "1.0.0",
                "last_saved": datetime.now().isoformat(),
                "session_id": session_id
            }
            
            # 获取文件锁
            await self._acquire_lock(file_path)
            try:
                success = await self._atomic_write(file_path, data)
                
                if success:
                    logger.info(
                        "工作流状态保存成功",
                        session_id=session_id,
                        current_stage=workflow_state.current_stage.value
                    )
                return success
            finally:
                self._release_lock(file_path)
                
        except Exception as e:
            logger.error(
                "保存工作流状态失败",
                session_id=workflow_state.session_id,
                error=str(e)
            )
            return False
    
    async def load_workflow_state(self, session_id: str) -> Optional[WorkflowState]:
        """加载工作流状态"""
        try:
            file_path = self._get_session_file_path(session_id)
            
            # 获取文件锁
            await self._acquire_lock(file_path)
            try:
                data = await self._read_json_file(file_path)
                
                if not data:
                    logger.info("工作流状态不存在", session_id=session_id)
                    return None
                
                # 更新元数据
                data["_metadata"] = data.get("_metadata", {})
                data["_metadata"]["last_loaded"] = datetime.now().isoformat()
                
                # 重新保存更新的元数据
                await self._atomic_write(file_path, data)
                
                # 移除元数据以便WorkflowState.from_dict能正常工作
                if "_metadata" in data:
                    del data["_metadata"]
                
                # 构建WorkflowState对象
                workflow_state = WorkflowState.from_dict(data)
                
                logger.info(
                    "工作流状态加载成功", 
                    session_id=session_id,
                    current_stage=workflow_state.current_stage.value
                )
                
                return workflow_state
            finally:
                self._release_lock(file_path)
                
        except Exception as e:
            logger.error(
                "加载工作流状态失败",
                session_id=session_id,
                error=str(e)
            )
            return None
    
    async def delete_workflow_state(self, session_id: str) -> bool:
        """删除工作流状态"""
        try:
            file_path = self._get_session_file_path(session_id)
            
            # 获取文件锁
            await self._acquire_lock(file_path)
            try:
                if file_path.exists():
                    # 创建备份
                    backup_dir = self.base_path / "backups"
                    backup_dir.mkdir(exist_ok=True)
                    
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    backup_path = backup_dir / f"{session_id}_{timestamp}.json"
                    
                    # 复制到备份
                    async with aiofiles.open(file_path, 'r', encoding='utf-8') as src_file:
                        content = await src_file.read()
                        async with aiofiles.open(backup_path, 'w', encoding='utf-8') as dst_file:
                            await dst_file.write(content)
                    
                    # 删除原文件
                    file_path.unlink()
                    
                    logger.info(
                        "工作流状态删除成功",
                        session_id=session_id,
                        backup_path=str(backup_path)
                    )
                    return True
                else:
                    logger.info("工作流状态不存在，无需删除", session_id=session_id)
                    return False
            finally:
                self._release_lock(file_path)
                
        except Exception as e:
            logger.error(
                "删除工作流状态失败",
                session_id=session_id,
                error=str(e)
            )
            return False
    
    async def exists_workflow_state(self, session_id: str) -> bool:
        """检查工作流状态是否存在"""
        file_path = self._get_session_file_path(session_id)
        return file_path.exists()
    
    async def list_sessions(self) -> List[Dict[str, Any]]:
        """列出所有会话"""
        result = []
        sessions_dir = self.base_path / "sessions"
        
        try:
            if not sessions_dir.exists():
                return []
            
            for file_path in sessions_dir.glob("*.json"):
                try:
                    session_id = file_path.stem
                    data = await self._read_json_file(file_path)
                    
                    if data and "_metadata" in data:
                        metadata = data["_metadata"]
                        result.append({
                            "session_id": session_id,
                            "current_stage": data.get("current_stage", "unknown"),
                            "last_saved": metadata.get("last_saved"),
                            "last_loaded": metadata.get("last_loaded"),
                            "file_size": file_path.stat().st_size,
                            "modified_time": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                        })
                    else:
                        result.append({
                            "session_id": session_id,
                            "current_stage": data.get("current_stage", "unknown") if data else "unknown",
                            "file_size": file_path.stat().st_size,
                            "modified_time": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                        })
                except Exception as e:
                    logger.error(f"处理会话文件失败: {file_path}", error=str(e))
            
            # 按修改时间降序排序
            result.sort(key=lambda x: x.get("modified_time", ""), reverse=True)
            
            return result
        except Exception as e:
            logger.error("列出会话失败", error=str(e))
            return []
    
    async def cleanup_old_sessions(self, days: int = 30) -> int:
        """清理旧的会话文件"""
        try:
            sessions_dir = self.base_path / "sessions"
            if not sessions_dir.exists():
                return 0
            
            now = datetime.now().timestamp()
            cutoff = now - (days * 24 * 60 * 60)  # days转换为秒
            
            count = 0
            for file_path in sessions_dir.glob("*.json"):
                try:
                    if file_path.stat().st_mtime < cutoff:
                        session_id = file_path.stem
                        await self.delete_workflow_state(session_id)
                        count += 1
                except Exception as e:
                    logger.error(f"删除旧会话文件失败: {file_path}", error=str(e))
            
            logger.info(f"清理了{count}个旧会话文件", days=days)
            return count
        except Exception as e:
            logger.error("清理旧会话文件失败", error=str(e))
            return 0
    
    async def backup_all_sessions(self) -> int:
        """备份所有会话文件"""
        try:
            sessions_dir = self.base_path / "sessions"
            backup_dir = self.base_path / "backups"
            backup_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            session_backup_dir = backup_dir / f"all_sessions_{timestamp}"
            session_backup_dir.mkdir(exist_ok=True)
            
            count = 0
            for file_path in sessions_dir.glob("*.json"):
                try:
                    session_id = file_path.stem
                    backup_path = session_backup_dir / f"{session_id}.json"
                    
                    # 复制文件
                    async with aiofiles.open(file_path, 'r', encoding='utf-8') as src_file:
                        content = await src_file.read()
                        async with aiofiles.open(backup_path, 'w', encoding='utf-8') as dst_file:
                            await dst_file.write(content)
                    
                    count += 1
                except Exception as e:
                    logger.error(f"备份会话文件失败: {file_path}", error=str(e))
            
            logger.info(f"备份了{count}个会话文件", backup_dir=str(session_backup_dir))
            return count
        except Exception as e:
            logger.error("备份所有会话文件失败", error=str(e))
            return 0