# -*- coding: utf-8 -*-
"""
语义存储抽象接口

定义统一的语义存储接口规范，支持多种存储后端实现
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)


class SemanticStorageType(Enum):
    """语义存储类型枚举"""
    FILE = "file"           # 文件存储
    MONGODB = "mongodb"     # MongoDB存储
    REDIS = "redis"         # Redis存储
    ELASTICSEARCH = "elasticsearch"  # Elasticsearch存储
    MEMORY = "memory"       # 内存存储（测试用）


@dataclass
class SemanticField:
    """语义字段数据模型"""
    business_meaning: str
    confidence: float
    data_type: str
    examples: List[Any]
    analysis_result: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    source: str
    version: str = "1.0.0"
    tags: List[str] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "business_meaning": self.business_meaning,
            "confidence": self.confidence,
            "data_type": self.data_type,
            "examples": self.examples,
            "analysis_result": self.analysis_result,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "source": self.source,
            "version": self.version,
            "tags": self.tags,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SemanticField':
        """从字典创建"""
        created_at = None
        if data.get('created_at'):
            try:
                created_at = datetime.fromisoformat(data['created_at'])
            except ValueError:
                created_at = datetime.now()
                
        updated_at = None
        if data.get('updated_at'):
            try:
                updated_at = datetime.fromisoformat(data['updated_at'])
            except ValueError:
                updated_at = datetime.now()
        
        return cls(
            business_meaning=data.get('business_meaning', ''),
            confidence=data.get('confidence', 0.0),
            data_type=data.get('data_type', ''),
            examples=data.get('examples', []),
            analysis_result=data.get('analysis_result', {}),
            created_at=created_at,
            updated_at=updated_at,
            source=data.get('source', ''),
            version=data.get('version', '1.0.0'),
            tags=data.get('tags', []),
            metadata=data.get('metadata', {})
        )


@dataclass
class SemanticSearchQuery:
    """语义搜索查询条件"""
    search_term: Optional[str] = None
    instance_name: Optional[str] = None
    database_name: Optional[str] = None
    collection_name: Optional[str] = None
    field_path: Optional[str] = None
    tags: List[str] = None
    confidence_min: Optional[float] = None
    confidence_max: Optional[float] = None
    source: Optional[str] = None
    limit: int = 100
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []


@dataclass
class SemanticConflictInfo:
    """语义冲突信息"""
    field_path: str
    existing_meaning: str
    new_meaning: str
    confidence_diff: float
    resolution_strategy: str = "manual"  # manual, auto_merge, prefer_existing, prefer_new


class SemanticStorageInterface(ABC):
    """语义存储抽象接口"""
    
    @abstractmethod
    async def save_field_semantic(
        self, 
        instance_name: str,
        database_name: str, 
        collection_name: str,
        field_path: str,
        semantic_field: SemanticField
    ) -> bool:
        """保存字段语义信息"""
        pass
    
    @abstractmethod
    async def get_field_semantic(
        self,
        instance_name: str,
        database_name: str,
        collection_name: str, 
        field_path: str
    ) -> Optional[SemanticField]:
        """获取字段语义信息"""
        pass
    
    @abstractmethod
    async def batch_save_semantics(
        self,
        instance_name: str,
        database_name: str,
        collection_name: str,
        semantic_data: Dict[str, SemanticField]
    ) -> Dict[str, bool]:
        """批量保存字段语义信息"""
        pass
    
    @abstractmethod
    async def batch_get_semantics(
        self,
        instance_name: str,
        database_name: str,
        collection_name: str,
        field_paths: List[str]
    ) -> Dict[str, Optional[SemanticField]]:
        """批量获取字段语义信息"""
        pass
    
    @abstractmethod
    async def search_semantics(
        self, 
        query: SemanticSearchQuery
    ) -> List[Tuple[str, SemanticField]]:
        """搜索语义信息"""
        pass
    
    @abstractmethod
    async def delete_field_semantic(
        self,
        instance_name: str,
        database_name: str,
        collection_name: str,
        field_path: str
    ) -> bool:
        """删除字段语义信息"""
        pass
    
    @abstractmethod
    async def get_collection_semantics(
        self,
        instance_name: str,
        database_name: str,
        collection_name: str
    ) -> Dict[str, SemanticField]:
        """获取集合的所有字段语义信息"""
        pass
    
    @abstractmethod
    async def detect_conflicts(
        self,
        instance_name: str,
        database_name: str,
        collection_name: str,
        field_path: str,
        new_semantic: SemanticField
    ) -> List[SemanticConflictInfo]:
        """检测语义冲突"""
        pass
    
    @abstractmethod
    async def resolve_conflict(
        self,
        conflict: SemanticConflictInfo,
        resolution_strategy: str
    ) -> bool:
        """解决语义冲突"""
        pass
    
    @abstractmethod
    async def get_semantic_history(
        self,
        instance_name: str,
        database_name: str,
        collection_name: str,
        field_path: str,
        limit: int = 10
    ) -> List[SemanticField]:
        """获取字段语义变更历史"""
        pass
    
    @abstractmethod
    async def create_semantic_snapshot(
        self, 
        instance_name: str,
        database_name: str,
        collection_name: str,
        snapshot_name: str
    ) -> bool:
        """创建语义快照"""
        pass
    
    @abstractmethod
    async def restore_from_snapshot(
        self,
        instance_name: str,
        database_name: str,
        collection_name: str,
        snapshot_name: str
    ) -> bool:
        """从快照恢复"""
        pass
    
    @abstractmethod
    async def cleanup_old_versions(
        self,
        days: int = 30
    ) -> int:
        """清理旧版本数据"""
        pass
    
    @abstractmethod
    async def get_storage_stats(self) -> Dict[str, Any]:
        """获取存储统计信息"""
        pass
    
    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        pass


class SemanticStorageConfig:
    """语义存储配置"""
    
    def __init__(self, **kwargs):
        # 通用配置
        self.storage_type = kwargs.get("storage_type", SemanticStorageType.FILE)
        self.enable_versioning = kwargs.get("enable_versioning", True)
        self.enable_conflict_detection = kwargs.get("enable_conflict_detection", True)
        self.max_versions = kwargs.get("max_versions", 10)
        self.cleanup_interval = kwargs.get("cleanup_interval", 24 * 3600)  # 24小时
        
        # 文件存储配置
        self.base_path = kwargs.get("base_path", "data/semantics")
        self.enable_compression = kwargs.get("enable_compression", False)
        
        # MongoDB配置
        self.mongodb_url = kwargs.get("mongodb_url", "mongodb://localhost:27017")
        self.mongodb_database = kwargs.get("mongodb_database", "querynest_semantics")
        self.mongodb_collection = kwargs.get("mongodb_collection", "field_semantics")
        
        # Redis配置
        self.redis_url = kwargs.get("redis_url", "redis://localhost:6379/1")
        self.redis_prefix = kwargs.get("redis_prefix", "semantics:")
        
        # Elasticsearch配置
        self.elasticsearch_url = kwargs.get("elasticsearch_url", "http://localhost:9200")
        self.elasticsearch_index = kwargs.get("elasticsearch_index", "querynest_semantics")
        
        # 缓存配置
        self.enable_cache = kwargs.get("enable_cache", True)
        self.cache_ttl = kwargs.get("cache_ttl", 3600)  # 1小时
        self.cache_size = kwargs.get("cache_size", 1000)
        
        # 其他配置
        self.extra = {k: v for k, v in kwargs.items() if not hasattr(self, k)}