# -*- coding: utf-8 -*-
"""
基于文件存储的元数据管理器

替代原有的MongoDB元数据存储，使用JSON文件存储结构化元数据
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import structlog
import asyncio
from pathlib import Path

from database.connection_manager import ConnectionManager
from storage.file_metadata_manager import FileMetadataManager
from storage.local_semantic_storage import LocalSemanticStorage
from storage.semantic_file_manager import SemanticFileManager
from config import get_config


logger = structlog.get_logger(__name__)


class FileBasedMetadataManager:
    """基于文件存储的元数据管理器"""
    
    def __init__(self, connection_manager: ConnectionManager):
        self.connection_manager = connection_manager
        
        # 从配置获取存储路径
        try:
            config = get_config()
            metadata_path = config.storage.metadata_path
            semantic_path = config.storage.semantic_path
        except:
            # 回退到默认路径
            metadata_path = "data/metadata"
            semantic_path = "data/semantics"
        
        self.file_metadata_manager = FileMetadataManager(metadata_path)
        
        # 语义存储组件
        self.local_storage = LocalSemanticStorage()
        self.file_manager = SemanticFileManager(self.local_storage)
        
        # 缓存和统计
        self.metadata_cache: Dict[str, Dict] = {}
        self.last_scan_time: Dict[str, datetime] = {}
        self._lock = asyncio.Lock()
        self._scan_stats = {
            'total_scans': 0,
            'incremental_scans': 0,
            'full_scans': 0,
            'cache_hits': 0,
            'cache_misses': 0
        }
        self._collection_timestamps: Dict[str, Dict[str, datetime]] = {}
    
    async def initialize(self) -> bool:
        """初始化元数据管理器"""
        try:
            # 初始化文件存储
            await self.file_metadata_manager.initialize()
            logger.info("基于文件的元数据管理器初始化完成")
            return True
        except Exception as e:
            logger.error("元数据管理器初始化失败", error=str(e))
            return False
    
    def _should_perform_full_scan(self, instance_name: str) -> bool:
        """判断是否应该执行全量扫描"""
        last_scan = self.last_scan_time.get(instance_name)
        if not last_scan:
            return True
        
        # 如果距离上次扫描超过24小时，执行全量扫描
        time_diff = datetime.now() - last_scan
        return time_diff.total_seconds() > 86400  # 24小时
    
    async def scan_all_metadata(self, force_full_scan: bool = False) -> bool:
        """扫描所有实例的元数据"""
        try:
            scan_tasks = []
            for instance_name in self.connection_manager.get_instance_names():
                if force_full_scan or self._should_perform_full_scan(instance_name):
                    scan_tasks.append(self.scan_instance_metadata(instance_name, full_scan=True))
                else:
                    scan_tasks.append(self.scan_instance_metadata_incremental(instance_name))
            
            # 并发执行扫描任务
            results = await asyncio.gather(*scan_tasks, return_exceptions=True)
            
            # 检查结果
            success_count = sum(1 for result in results if result is True)
            total_count = len(results)
            
            self._scan_stats['total_scans'] += 1
            if force_full_scan:
                self._scan_stats['full_scans'] += 1
            else:
                self._scan_stats['incremental_scans'] += 1
            
            logger.info(f"元数据扫描完成: {success_count}/{total_count} 个实例成功")
            return success_count == total_count
            
        except Exception as e:
            logger.error(f"扫描所有元数据失败: {e}")
            return False
    
    async def scan_instance_metadata(self, instance_name: str, full_scan: bool = False) -> bool:
        """扫描指定实例的元数据"""
        try:
            # 确保实例元数据已初始化
            if not await self.init_instance_metadata(instance_name):
                logger.error(f"实例 {instance_name} 元数据初始化失败")
                return False
            
            # 获取实例连接
            instance_connection = self.connection_manager.get_instance_connection(instance_name)
            if not instance_connection or not instance_connection.client:
                logger.error(f"无法获取实例 {instance_name} 的连接")
                return False
            
            # 扫描实例信息
            await self._scan_instance_info(instance_name)
            
            # 扫描数据库信息
            await self._scan_databases(instance_name)
            
            self.last_scan_time[instance_name] = datetime.now()
            
            logger.info(f"实例 {instance_name} 元数据扫描完成", full_scan=full_scan)
            return True
            
        except Exception as e:
            logger.error(f"扫描实例 {instance_name} 元数据失败", error=str(e))
            return False
    
    async def scan_instance_metadata_incremental(self, instance_name: str) -> bool:
        """增量扫描实例元数据"""
        return await self.scan_instance_metadata(instance_name, full_scan=False)
    
    async def _scan_instance_info(self, instance_name: str) -> None:
        """扫描实例基本信息"""
        try:
            # 从配置获取实例信息
            instance_config = self.connection_manager.config.mongo_instances.get(instance_name)
            if instance_config:
                instance_info = {
                    "name": instance_config.name,
                    "alias": instance_name,
                    "connection_string": instance_config.connection_string,
                    "description": instance_config.description,
                    "environment": instance_config.environment,
                    "status": instance_config.status
                }
                await self.file_metadata_manager.save_instance(instance_name, instance_info)
        except Exception as e:
            logger.error(f"扫描实例 {instance_name} 信息失败", error=str(e))
    
    async def _scan_databases(self, instance_name: str) -> None:
        """扫描实例的数据库信息"""
        try:
            instance_connection = self.connection_manager.get_instance_connection(instance_name)
            if not instance_connection:
                return
            
            # 获取实例ID
            instance_data = await self.file_metadata_manager.get_instance_by_name(instance_name, instance_name)
            if not instance_data:
                return
                
            instance_id = instance_data["id"]
            
            # 列出所有数据库
            database_names = await instance_connection.client.list_database_names()
            
            for db_name in database_names:
                # 跳过系统数据库
                if db_name in ['admin', 'local', 'config']:
                    continue
                
                try:
                    db = instance_connection.client[db_name]
                    
                    # 获取集合列表
                    collection_names = await db.list_collection_names()
                    
                    # 计算数据库统计信息
                    db_stats = await db.command("dbStats")
                    
                    db_info = {
                        "name": db_name,
                        "collection_count": len(collection_names),
                        "size_bytes": db_stats.get("dataSize", 0),
                        "description": f"数据库 {db_name}"
                    }
                    
                    await self.file_metadata_manager.save_database(instance_name, instance_id, db_info)
                    
                    # 扫描集合信息
                    await self._scan_collections(instance_name, instance_id, db_name, collection_names)
                    
                except Exception as e:
                    logger.error(f"扫描数据库 {db_name} 失败", error=str(e))
                    
        except Exception as e:
            logger.error(f"扫描实例 {instance_name} 数据库失败", error=str(e))
    
    async def _scan_collections(self, instance_name: str, instance_id: str, 
                               database_name: str, collection_names: List[str]) -> None:
        """扫描集合信息"""
        try:
            instance_connection = self.connection_manager.get_instance_connection(instance_name)
            if not instance_connection:
                return
                
            db = instance_connection.client[database_name]
            
            for collection_name in collection_names:
                try:
                    collection = db[collection_name]
                    
                    # 获取集合统计信息
                    collection_stats = await db.command("collStats", collection_name)
                    document_count = collection_stats.get("count", 0)
                    
                    # 获取样本文档
                    sample_document = None
                    async for doc in collection.find().limit(1):
                        sample_document = doc
                        break
                    
                    # 获取索引信息
                    indexes = await collection.list_indexes().to_list(None)
                    has_index = len(indexes) > 1  # 除了默认的_id索引
                    
                    collection_info = {
                        "database_name": database_name,
                        "name": collection_name,
                        "document_count": document_count,
                        "size_bytes": collection_stats.get("size", 0),
                        "has_index": has_index,
                        "field_count": len(sample_document.keys()) if sample_document else 0,
                        "sample_document": sample_document
                    }
                    
                    await self.file_metadata_manager.save_collection(instance_name, instance_id, collection_info)
                    
                except Exception as e:
                    logger.error(f"扫描集合 {collection_name} 失败", error=str(e))
                    
        except Exception as e:
            logger.error(f"扫描实例 {instance_name} 集合失败", error=str(e))
    
    # ==================== 实例管理 ====================
    
    async def save_instance(self, target_instance_name: str, instance_config: Dict[str, Any]) -> str:
        """保存实例配置"""
        return await self.file_metadata_manager.save_instance(target_instance_name, instance_config)
    
    async def get_instance_by_name(self, target_instance_name: str, instance_name: str) -> Optional[Dict[str, Any]]:
        """根据名称获取实例信息"""
        return await self.file_metadata_manager.get_instance_by_name(target_instance_name, instance_name)
    
    async def get_all_instances(self, target_instance_name: str, environment: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取所有实例"""
        return await self.file_metadata_manager.get_all_instances(target_instance_name, environment)
    
    # ==================== 数据库管理 ====================
    
    async def save_database(self, target_instance_name: str, instance_id: str, db_info: Dict[str, Any]) -> str:
        """保存数据库信息"""
        return await self.file_metadata_manager.save_database(target_instance_name, instance_id, db_info)
    
    async def get_databases_by_instance(self, target_instance_name: str, instance_id: str) -> List[Dict[str, Any]]:
        """获取实例的所有数据库"""
        return await self.file_metadata_manager.get_databases_by_instance(target_instance_name, instance_id)
    
    # ==================== 集合管理 ====================
    
    async def save_collection(self, target_instance_name: str, instance_id: str, collection_info: Dict[str, Any]) -> str:
        """保存集合信息"""
        return await self.file_metadata_manager.save_collection(target_instance_name, instance_id, collection_info)
    
    async def get_collections_by_database(self, target_instance_name: str, instance_id: str, database_name: str) -> List[Dict[str, Any]]:
        """获取数据库的所有集合"""
        return await self.file_metadata_manager.get_collections_by_database(target_instance_name, instance_id, database_name)
    
    # ==================== 字段管理 ====================
    
    async def save_field(self, target_instance_name: str, instance_id: str, field_info: Dict[str, Any]) -> str:
        """保存字段信息"""
        return await self.file_metadata_manager.save_field(target_instance_name, instance_id, field_info)
    
    async def get_fields_by_collection(self, target_instance_name: str, instance_id: str, 
                                     database_name: str, collection_name: str) -> List[Dict[str, Any]]:
        """获取集合的所有字段"""
        return await self.file_metadata_manager.get_fields_by_collection(
            target_instance_name, instance_id, database_name, collection_name)
    
    # ==================== 查询历史管理 ====================
    
    async def save_query_history(self, target_instance_name: str, query_info: Dict[str, Any]) -> str:
        """保存查询历史"""
        return await self.file_metadata_manager.save_query_history(target_instance_name, query_info)
    
    async def get_query_history(self, target_instance_name: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取查询历史"""
        return await self.file_metadata_manager.get_query_history(target_instance_name, limit)
    
    # ==================== 初始化和管理 ====================
    
    async def init_instance_metadata(self, instance_name: str) -> bool:
        """初始化实例元数据"""
        return await self.file_metadata_manager.init_instance_metadata(instance_name)
    
    async def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return await self.file_metadata_manager.get_statistics()
    
    async def get_scan_stats(self) -> Dict[str, Any]:
        """获取扫描统计信息"""
        return await self.file_metadata_manager.get_scan_stats()
    
    # ==================== 兼容性方法 ====================
    
    def _get_instance_collections(self, instance_name: str) -> Optional[Dict]:
        """兼容性方法 - 返回None表示使用文件存储"""
        return None
    
    async def get_database_by_name(self, target_instance_name: str, instance_id: str, database_name: str) -> Optional[Dict[str, Any]]:
        """根据名称获取数据库信息"""
        databases = await self.get_databases_by_instance(target_instance_name, instance_id)
        for db in databases:
            if db.get("database_name") == database_name:
                return db
        return None
    
    async def get_collection_by_name(self, target_instance_name: str, instance_id: str, 
                                   database_name: str, collection_name: str) -> Optional[Dict[str, Any]]:
        """根据名称获取集合信息"""
        collections = await self.get_collections_by_database(target_instance_name, instance_id, database_name)
        for collection in collections:
            if collection.get("collection_name") == collection_name:
                return collection
        return None