# -*- coding: utf-8 -*-
"""
语义存储工厂

提供统一的语义存储工厂，支持多种存储后端
"""

import os
import importlib
import inspect
from typing import Dict, Any, Optional, Type
from pathlib import Path
import structlog

from storage.semantic_storage_interface import (
    SemanticStorageInterface, 
    SemanticStorageType, 
    SemanticStorageConfig
)

logger = structlog.get_logger(__name__)


class SemanticStorageFactory:
    """语义存储工厂"""
    
    _instance = None
    _storage_implementations = {}
    
    @classmethod
    def get_instance(cls):
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = SemanticStorageFactory()
        return cls._instance
    
    def __init__(self):
        """初始化存储工厂"""
        self._discover_storage_implementations()
    
    def _discover_storage_implementations(self):
        """发现所有存储实现类"""
        logger.info("开始发现语义存储实现")
        
        # 注册内置存储实现
        self._register_builtin_implementations()
        
        # 尝试导入其他可能的存储实现
        self._try_import_storage("semantic_mongodb_storage", SemanticStorageType.MONGODB)
        self._try_import_storage("semantic_redis_storage", SemanticStorageType.REDIS)
        self._try_import_storage("semantic_elasticsearch_storage", SemanticStorageType.ELASTICSEARCH)
        self._try_import_storage("semantic_memory_storage", SemanticStorageType.MEMORY)
        
        logger.info("语义存储实现发现完成", 
                   implementations=list(self._storage_implementations.keys()))
    
    def _register_builtin_implementations(self):
        """注册内置存储实现"""
        try:
            # 注册文件存储实现
            from storage.enhanced_local_semantic_storage import EnhancedLocalSemanticStorage
            self._storage_implementations[SemanticStorageType.FILE] = EnhancedLocalSemanticStorage
            logger.info("已注册文件存储实现", class_name="EnhancedLocalSemanticStorage")
        except ImportError:
            # 回退到原有的本地存储
            try:
                from storage.local_semantic_storage import LocalSemanticStorage
                self._storage_implementations[SemanticStorageType.FILE] = LocalSemanticStorage
                logger.info("已注册本地文件存储实现", class_name="LocalSemanticStorage")
            except ImportError:
                logger.warning("无法导入本地文件存储实现")
    
    def _try_import_storage(self, module_name: str, storage_type: SemanticStorageType):
        """尝试导入存储模块"""
        try:
            module_path = f"storage.{module_name}"
            module = importlib.import_module(module_path)
            
            # 查找模块中的SemanticStorageInterface子类
            for name, obj in inspect.getmembers(module):
                if (inspect.isclass(obj) and 
                    issubclass(obj, SemanticStorageInterface) and 
                    obj != SemanticStorageInterface):
                    
                    self._storage_implementations[storage_type] = obj
                    logger.info(f"已注册存储实现: {storage_type.value}", class_name=name)
                    break
        except ImportError:
            logger.debug(f"未找到存储模块: {module_name}")
        except Exception as e:
            logger.warning(f"导入存储模块失败: {module_name}", error=str(e))
    
    def create_storage(self, config: Optional[SemanticStorageConfig] = None) -> SemanticStorageInterface:
        """创建存储实例"""
        if config is None:
            config = SemanticStorageConfig()
        
        storage_type = config.storage_type
        
        if storage_type not in self._storage_implementations:
            # 如果指定的存储类型不可用，回退到文件存储
            logger.warning(f"不支持的存储类型: {storage_type}，回退到文件存储")
            storage_type = SemanticStorageType.FILE
            
            if storage_type not in self._storage_implementations:
                raise ValueError(f"无可用的存储实现")
        
        storage_class = self._storage_implementations[storage_type]
        
        try:
            # 根据存储类型创建实例
            if storage_type == SemanticStorageType.FILE:
                return storage_class(
                    base_path=config.base_path,
                    enable_compression=config.enable_compression,
                    enable_cache=config.enable_cache,
                    cache_ttl=config.cache_ttl,
                    cache_size=config.cache_size
                )
            
            elif storage_type == SemanticStorageType.MONGODB:
                return storage_class(
                    mongodb_url=config.mongodb_url,
                    database_name=config.mongodb_database,
                    collection_name=config.mongodb_collection,
                    enable_versioning=config.enable_versioning,
                    max_versions=config.max_versions
                )
            
            elif storage_type == SemanticStorageType.REDIS:
                return storage_class(
                    redis_url=config.redis_url,
                    redis_prefix=config.redis_prefix,
                    enable_cache=config.enable_cache,
                    cache_ttl=config.cache_ttl
                )
            
            elif storage_type == SemanticStorageType.ELASTICSEARCH:
                return storage_class(
                    elasticsearch_url=config.elasticsearch_url,
                    index_name=config.elasticsearch_index,
                    enable_versioning=config.enable_versioning
                )
            
            elif storage_type == SemanticStorageType.MEMORY:
                return storage_class(
                    max_size=config.cache_size,
                    ttl=config.cache_ttl
                )
            
            else:
                # 对于自定义存储，尝试使用额外配置
                return storage_class(**config.extra)
                
        except Exception as e:
            logger.error(f"创建存储实例失败: {storage_type}", error=str(e))
            raise
    
    def create_default_storage(self) -> SemanticStorageInterface:
        """创建默认存储实现"""
        # 从环境变量获取配置
        storage_type_str = os.environ.get("QUERYNEST_SEMANTIC_STORAGE", "file")
        
        try:
            storage_type = SemanticStorageType(storage_type_str.lower())
        except ValueError:
            logger.warning(f"未知的语义存储类型: {storage_type_str}，使用默认文件存储")
            storage_type = SemanticStorageType.FILE
        
        # 创建存储配置
        config = SemanticStorageConfig(
            storage_type=storage_type,
            base_path=os.environ.get("QUERYNEST_SEMANTIC_PATH", "data/semantics"),
            enable_versioning=os.environ.get("QUERYNEST_SEMANTIC_VERSIONING", "true").lower() == "true",
            enable_conflict_detection=os.environ.get("QUERYNEST_CONFLICT_DETECTION", "true").lower() == "true",
            mongodb_url=os.environ.get("QUERYNEST_MONGODB_URL", "mongodb://localhost:27017"),
            mongodb_database=os.environ.get("QUERYNEST_SEMANTIC_DB", "querynest_semantics"),
            redis_url=os.environ.get("QUERYNEST_REDIS_URL", "redis://localhost:6379/1"),
            elasticsearch_url=os.environ.get("QUERYNEST_ES_URL", "http://localhost:9200"),
            enable_cache=os.environ.get("QUERYNEST_SEMANTIC_CACHE", "true").lower() == "true",
            cache_ttl=int(os.environ.get("QUERYNEST_SEMANTIC_CACHE_TTL", "3600")),
            cache_size=int(os.environ.get("QUERYNEST_SEMANTIC_CACHE_SIZE", "1000"))
        )
        
        try:
            return self.create_storage(config)
        except Exception as e:
            logger.error("创建默认语义存储失败，回退到文件存储", error=str(e))
            # 最后的回退方案
            fallback_config = SemanticStorageConfig(
                storage_type=SemanticStorageType.FILE,
                base_path="data/semantics"
            )
            return self.create_storage(fallback_config)
    
    def register_storage(self, storage_type: SemanticStorageType, 
                        storage_class: Type[SemanticStorageInterface]) -> bool:
        """手动注册存储实现"""
        if not issubclass(storage_class, SemanticStorageInterface):
            logger.error(f"无效的存储类: {storage_class.__name__}，必须是SemanticStorageInterface的子类")
            return False
        
        self._storage_implementations[storage_type] = storage_class
        logger.info(f"已手动注册语义存储: {storage_type.value}", class_name=storage_class.__name__)
        return True
    
    def get_available_storage_types(self) -> Dict[SemanticStorageType, Type[SemanticStorageInterface]]:
        """获取可用的存储类型"""
        return self._storage_implementations.copy()


# 便捷函数，用于获取存储实例
def get_semantic_storage(config: Optional[SemanticStorageConfig] = None) -> SemanticStorageInterface:
    """获取语义存储实例"""
    factory = SemanticStorageFactory.get_instance()
    
    if config is None:
        return factory.create_default_storage()
    else:
        return factory.create_storage(config)