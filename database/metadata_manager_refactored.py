# -*- coding: utf-8 -*-
"""
重构后的元数据管理器 - 使用分离的组件
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import asyncio
import structlog

from database.connection_manager import ConnectionManager
from database.metadata_scanner import MetadataScanner, ScanResult
from database.metadata_storage import MetadataStorageInterface, MongoMetadataStorage
from database.metadata_cache import MultiLevelMetadataCache, get_metadata_cache

logger = structlog.get_logger(__name__)


class MetadataManagerRefactored:
    """重构后的元数据管理器 - 使用组合模式分离职责"""
    
    def __init__(self, connection_manager: ConnectionManager, 
                 storage: Optional[MetadataStorageInterface] = None):
        self.connection_manager = connection_manager
        
        # 初始化各个组件
        self.scanner = MetadataScanner(connection_manager)
        self.storage = storage or MongoMetadataStorage(connection_manager)
        self.cache = get_metadata_cache()
        
        # 管理器级别的锁
        self._manager_lock = asyncio.Lock()
        
        # 管理器统计
        self._manager_stats = {
            'total_operations': 0,
            'cache_hits': 0,
            'storage_hits': 0,
            'scan_operations': 0,
            'errors': 0
        }
    
    async def scan_all_instances(self, force_full_scan: bool = False) -> Dict[str, bool]:
        """扫描所有实例的元数据"""
        async with self._manager_lock:
            self._manager_stats['scan_operations'] += 1
            
            try:
                # 使用扫描器执行扫描
                scan_results = await self.scanner.scan_all_instances(force_full_scan)
                
                # 存储扫描结果
                storage_results = {}
                for result in scan_results:
                    storage_success = await self.storage.store_scan_result(result)
                    storage_results[result.instance_name] = result.success and storage_success
                    
                    # 如果扫描成功，清理对应实例的缓存
                    if result.success:
                        self.cache.clear_instance_cache(result.instance_name)
                
                logger.info(f"批量扫描完成: {len(scan_results)} 个实例")
                return storage_results
                
            except Exception as e:
                self._manager_stats['errors'] += 1
                logger.error(f"批量扫描失败: {e}")
                return {}
    
    async def scan_instance(self, instance_name: str, force_full_scan: bool = False) -> bool:
        """扫描指定实例"""
        async with self._manager_lock:
            self._manager_stats['scan_operations'] += 1
            
            try:
                # 使用扫描器执行扫描
                result = await self.scanner.scan_instance(instance_name, force_full_scan)
                
                if result.success:
                    # 存储扫描结果
                    storage_success = await self.storage.store_scan_result(result)
                    
                    if storage_success:
                        # 清理缓存
                        self.cache.clear_instance_cache(instance_name)
                        logger.info(f"实例 {instance_name} 扫描和存储成功")
                        return True
                    else:
                        logger.error(f"实例 {instance_name} 扫描成功但存储失败")
                        return False
                else:
                    logger.error(f"实例 {instance_name} 扫描失败: {result.error}")
                    return False
                    
            except Exception as e:
                self._manager_stats['errors'] += 1
                logger.error(f"扫描实例 {instance_name} 失败: {e}")
                return False
    
    async def get_instance_metadata(self, instance_name: str) -> Optional[Dict[str, Any]]:
        """获取实例元数据（带缓存）"""
        self._manager_stats['total_operations'] += 1
        
        try:
            # 先尝试从缓存获取
            cached_data = self.cache.get_instance_cache().get("instance", instance_name)
            if cached_data:
                self._manager_stats['cache_hits'] += 1
                return cached_data
            
            # 从存储获取
            storage_data = await self.storage.get_instance_metadata(instance_name)
            if storage_data:
                self._manager_stats['storage_hits'] += 1
                # 缓存结果
                self.cache.get_instance_cache().put("instance", storage_data, None, instance_name)
                return storage_data
            
            return None
            
        except Exception as e:
            self._manager_stats['errors'] += 1
            logger.error(f"获取实例 {instance_name} 元数据失败: {e}")
            return None
    
    async def get_database_metadata(self, instance_name: str, database_name: str) -> Optional[Dict[str, Any]]:
        """获取数据库元数据（带缓存）"""
        self._manager_stats['total_operations'] += 1
        
        try:
            # 先尝试从缓存获取
            cached_data = self.cache.get_database_cache().get("database", instance_name, database_name)
            if cached_data:
                self._manager_stats['cache_hits'] += 1
                return cached_data
            
            # 从存储获取
            storage_data = await self.storage.get_database_metadata(instance_name, database_name)
            if storage_data:
                self._manager_stats['storage_hits'] += 1
                # 缓存结果
                self.cache.get_database_cache().put("database", storage_data, None, instance_name, database_name)
                return storage_data
            
            return None
            
        except Exception as e:
            self._manager_stats['errors'] += 1
            logger.error(f"获取数据库 {instance_name}.{database_name} 元数据失败: {e}")
            return None
    
    async def get_collection_metadata(self, instance_name: str, database_name: str, 
                                    collection_name: str) -> Optional[Dict[str, Any]]:
        """获取集合元数据（带缓存）"""
        self._manager_stats['total_operations'] += 1
        
        try:
            # 先尝试从缓存获取
            cached_data = self.cache.get_collection_cache().get(
                "collection", instance_name, database_name, collection_name
            )
            if cached_data:
                self._manager_stats['cache_hits'] += 1
                return cached_data
            
            # 从存储获取
            storage_data = await self.storage.get_collection_metadata(
                instance_name, database_name, collection_name
            )
            if storage_data:
                self._manager_stats['storage_hits'] += 1
                # 缓存结果
                self.cache.get_collection_cache().put(
                    "collection", storage_data, None, instance_name, database_name, collection_name
                )
                return storage_data
            
            return None
            
        except Exception as e:
            self._manager_stats['errors'] += 1
            logger.error(f"获取集合 {instance_name}.{database_name}.{collection_name} 元数据失败: {e}")
            return None
    
    async def list_instances(self) -> List[str]:
        """列出所有实例"""
        try:
            return await self.storage.list_instances()
        except Exception as e:
            logger.error(f"列出实例失败: {e}")
            return []
    
    async def list_databases(self, instance_name: str) -> List[str]:
        """列出实例的所有数据库"""
        try:
            return await self.storage.list_databases(instance_name)
        except Exception as e:
            logger.error(f"列出实例 {instance_name} 数据库失败: {e}")
            return []
    
    async def list_collections(self, instance_name: str, database_name: str) -> List[str]:
        """列出数据库的所有集合"""
        try:
            return await self.storage.list_collections(instance_name, database_name)
        except Exception as e:
            logger.error(f"列出数据库 {instance_name}.{database_name} 集合失败: {e}")
            return []
    
    async def delete_instance_metadata(self, instance_name: str) -> bool:
        """删除实例元数据"""
        try:
            success = await self.storage.delete_instance_metadata(instance_name)
            if success:
                # 清理缓存
                self.cache.clear_instance_cache(instance_name)
                logger.info(f"实例 {instance_name} 元数据删除成功")
            return success
        except Exception as e:
            logger.error(f"删除实例 {instance_name} 元数据失败: {e}")
            return False
    
    def get_scan_statistics(self) -> Dict[str, Any]:
        """获取扫描统计信息"""
        return self.scanner.get_scan_statistics()
    
    def get_cache_statistics(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        return self.cache.get_overall_stats()
    
    def get_manager_statistics(self) -> Dict[str, Any]:
        """获取管理器统计信息"""
        return {
            **self._manager_stats,
            "scanner_stats": self.get_scan_statistics(),
            "cache_stats": self.get_cache_statistics()
        }
    
    async def optimize_cache(self):
        """优化缓存"""
        try:
            self.cache.optimize_all()
            logger.info("缓存优化完成")
        except Exception as e:
            logger.error(f"缓存优化失败: {e}")
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        health_status = {
            "status": "healthy",
            "components": {},
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            # 检查扫描器
            scanner_stats = self.get_scan_statistics()
            health_status["components"]["scanner"] = {
                "status": "healthy",
                "total_scans": scanner_stats.get("total_scans", 0)
            }
        except Exception as e:
            health_status["components"]["scanner"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health_status["status"] = "degraded"
        
        try:
            # 检查缓存
            cache_stats = self.get_cache_statistics()
            health_status["components"]["cache"] = {
                "status": "healthy",
                "hit_rate": cache_stats.get("overall_hit_rate", 0.0),
                "total_size": cache_stats.get("total_size", 0)
            }
        except Exception as e:
            health_status["components"]["cache"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health_status["status"] = "degraded"
        
        try:
            # 检查存储（通过列出实例）
            instances = await self.list_instances()
            health_status["components"]["storage"] = {
                "status": "healthy",
                "instance_count": len(instances)
            }
        except Exception as e:
            health_status["components"]["storage"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health_status["status"] = "unhealthy"
        
        return health_status


class MetadataManagerFactory:
    """元数据管理器工厂"""
    
    @staticmethod
    def create_manager(connection_manager: ConnectionManager, 
                      storage_type: str = "mongo") -> MetadataManagerRefactored:
        """创建元数据管理器"""
        if storage_type == "mongo":
            storage = MongoMetadataStorage(connection_manager)
        elif storage_type == "file":
            from database.metadata_storage import FileMetadataStorage
            storage = FileMetadataStorage()
        else:
            raise ValueError(f"不支持的存储类型: {storage_type}")
        
        return MetadataManagerRefactored(connection_manager, storage)
    
    @staticmethod
    def create_test_manager(connection_manager: ConnectionManager) -> MetadataManagerRefactored:
        """创建用于测试的元数据管理器"""
        from database.metadata_storage import FileMetadataStorage
        storage = FileMetadataStorage("./test_metadata_storage")
        return MetadataManagerRefactored(connection_manager, storage)


# 兼容性别名
MetadataManager = MetadataManagerRefactored