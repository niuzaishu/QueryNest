# -*- coding: utf-8 -*-
"""
工作流状态存储工厂

提供统一的工作流状态存储接口和多种存储实现
"""

import os
from typing import Dict, Any, Optional, List, Union, Type
from enum import Enum
import structlog
from pathlib import Path
import importlib
import inspect
from abc import ABC, abstractmethod

from utils.workflow_state import WorkflowState

logger = structlog.get_logger(__name__)


class StorageType(Enum):
    """存储类型"""
    FILE = "file"         # 文件存储
    REDIS = "redis"       # Redis存储
    MONGODB = "mongodb"   # MongoDB存储
    MEMORY = "memory"     # 内存存储
    CUSTOM = "custom"     # 自定义存储


class StorageOptions:
    """存储选项配置"""
    
    def __init__(self, **kwargs):
        """初始化存储选项"""
        # 通用配置
        self.auto_cleanup = kwargs.get("auto_cleanup", True)
        self.ttl_days = kwargs.get("ttl_days", 30)
        self.backup_enabled = kwargs.get("backup_enabled", True)
        self.backup_interval = kwargs.get("backup_interval", 3600)
        self.max_backups = kwargs.get("max_backups", 5)
        
        # 文件存储特定配置
        self.base_path = kwargs.get("base_path", "data/workflow")
        
        # Redis存储特定配置
        self.redis_url = kwargs.get("redis_url", "redis://localhost:6379/0")
        self.redis_prefix = kwargs.get("redis_prefix", "workflow:")
        
        # MongoDB存储特定配置
        self.mongodb_url = kwargs.get("mongodb_url", "mongodb://localhost:27017")
        self.mongodb_db = kwargs.get("mongodb_db", "querynest")
        self.mongodb_collection = kwargs.get("mongodb_collection", "workflow_states")
        
        # 附加配置
        self.extra = {k: v for k, v in kwargs.items() if k not in {
            "auto_cleanup", "ttl_days", "backup_enabled", "backup_interval", "max_backups",
            "base_path", "redis_url", "redis_prefix", "mongodb_url", "mongodb_db", 
            "mongodb_collection"
        }}


class WorkflowStateStorage(ABC):
    """工作流状态存储基类"""
    
    @abstractmethod
    async def save(self, state: WorkflowState) -> bool:
        """保存工作流状态"""
        pass
    
    @abstractmethod
    async def load(self, session_id: str) -> Optional[WorkflowState]:
        """加载工作流状态"""
        pass
    
    @abstractmethod
    async def delete(self, session_id: str) -> bool:
        """删除工作流状态"""
        pass
    
    @abstractmethod
    async def exists(self, session_id: str) -> bool:
        """检查工作流状态是否存在"""
        pass
    
    @abstractmethod
    async def list_sessions(self) -> List[Dict[str, Any]]:
        """列出所有会话"""
        pass
    
    @abstractmethod
    async def cleanup(self, days: int = 30) -> int:
        """清理旧的会话"""
        pass
    
    @abstractmethod
    async def backup(self) -> bool:
        """备份所有会话"""
        pass


class WorkflowStateStorageFactory:
    """工作流状态存储工厂"""
    
    _instance = None
    _storage_implementations = {}
    
    @classmethod
    def get_instance(cls):
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = WorkflowStateStorageFactory()
        return cls._instance
    
    def __init__(self):
        """初始化存储工厂"""
        self._discover_storage_implementations()
    
    def _discover_storage_implementations(self):
        """发现所有存储实现类"""
        # 寻找当前模块中的所有存储实现
        storage_dir = Path(__file__).parent
        
        # 注册内置存储实现
        from storage.workflow_state_storage import WorkflowStateStorage as FileWorkflowStateStorage
        self._storage_implementations[StorageType.FILE] = FileWorkflowStateStorage
        
        # 尝试导入其他可能的存储实现
        self._try_import_storage("redis_storage", StorageType.REDIS)
        self._try_import_storage("mongodb_storage", StorageType.MONGODB)
        self._try_import_storage("memory_storage", StorageType.MEMORY)
        
        logger.info("已发现工作流状态存储实现", 
                   implementations=list(self._storage_implementations.keys()))
    
    def _try_import_storage(self, module_name: str, storage_type: StorageType):
        """尝试导入存储模块"""
        try:
            module_path = f"storage.{module_name}"
            module = importlib.import_module(module_path)
            
            # 查找模块中的WorkflowStateStorage子类
            for name, obj in inspect.getmembers(module):
                if (inspect.isclass(obj) and issubclass(obj, WorkflowStateStorage) 
                    and obj != WorkflowStateStorage):
                    self._storage_implementations[storage_type] = obj
                    logger.info(f"已注册存储实现: {storage_type.value}", class_name=name)
                    break
        except ImportError:
            logger.debug(f"未找到存储模块: {module_name}")
        except Exception as e:
            logger.warning(f"导入存储模块失败: {module_name}", error=str(e))
    
    def create_storage(self, storage_type: StorageType, options: Optional[StorageOptions] = None) -> WorkflowStateStorage:
        """创建存储实例"""
        if options is None:
            options = StorageOptions()
        
        if storage_type not in self._storage_implementations:
            raise ValueError(f"不支持的存储类型: {storage_type}")
        
        storage_class = self._storage_implementations[storage_type]
        
        # 将options转换为构造函数需要的参数
        if storage_type == StorageType.FILE:
            return storage_class(base_path=options.base_path)
        elif storage_type == StorageType.REDIS:
            return storage_class(redis_url=options.redis_url, redis_prefix=options.redis_prefix)
        elif storage_type == StorageType.MONGODB:
            return storage_class(mongodb_url=options.mongodb_url, 
                              mongodb_db=options.mongodb_db, 
                              mongodb_collection=options.mongodb_collection)
        elif storage_type == StorageType.MEMORY:
            return storage_class()
        else:
            # 对于自定义存储，尝试使用extra参数
            return storage_class(**options.extra)
    
    def create_default_storage(self) -> WorkflowStateStorage:
        """创建默认存储实现"""
        # 从环境变量或配置获取默认存储类型
        storage_type_str = os.environ.get("QUERYNEST_WORKFLOW_STORAGE", "file")
        
        try:
            storage_type = StorageType(storage_type_str.lower())
        except ValueError:
            logger.warning(f"未知的存储类型: {storage_type_str}，使用默认文件存储")
            storage_type = StorageType.FILE
        
        # 创建存储选项
        options = StorageOptions(
            base_path=os.environ.get("QUERYNEST_WORKFLOW_PATH", "data/workflow"),
            redis_url=os.environ.get("QUERYNEST_REDIS_URL", "redis://localhost:6379/0"),
            mongodb_url=os.environ.get("QUERYNEST_MONGODB_URL", "mongodb://localhost:27017"),
            mongodb_db=os.environ.get("QUERYNEST_MONGODB_DB", "querynest"),
            mongodb_collection=os.environ.get("QUERYNEST_MONGODB_COLLECTION", "workflow_states"),
        )
        
        try:
            return self.create_storage(storage_type, options)
        except Exception as e:
            logger.error("创建默认存储失败，回退到文件存储", error=str(e))
            return self.create_storage(StorageType.FILE, options)


# 便捷函数，用于获取存储实例
def get_workflow_storage(storage_type: Optional[StorageType] = None, 
                         options: Optional[StorageOptions] = None) -> WorkflowStateStorage:
    """获取工作流状态存储实例"""
    factory = WorkflowStateStorageFactory.get_instance()
    
    if storage_type is None:
        return factory.create_default_storage()
    else:
        return factory.create_storage(storage_type, options)