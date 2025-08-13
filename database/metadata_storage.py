# -*- coding: utf-8 -*-
"""
元数据存储器 - 负责元数据的持久化存储
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import asyncio
import structlog
from abc import ABC, abstractmethod
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorCollection

from database.connection_manager import ConnectionManager
from database.metadata_scanner import ScanResult

logger = structlog.get_logger(__name__)


class MetadataStorageInterface(ABC):
    """元数据存储接口"""
    
    @abstractmethod
    async def store_scan_result(self, scan_result: ScanResult) -> bool:
        """存储扫描结果"""
        pass
    
    @abstractmethod
    async def get_instance_metadata(self, instance_name: str) -> Optional[Dict[str, Any]]:
        """获取实例元数据"""
        pass
    
    @abstractmethod
    async def get_database_metadata(self, instance_name: str, database_name: str) -> Optional[Dict[str, Any]]:
        """获取数据库元数据"""
        pass
    
    @abstractmethod
    async def get_collection_metadata(self, instance_name: str, database_name: str, 
                                    collection_name: str) -> Optional[Dict[str, Any]]:
        """获取集合元数据"""
        pass
    
    @abstractmethod
    async def list_instances(self) -> List[str]:
        """列出所有实例"""
        pass
    
    @abstractmethod
    async def list_databases(self, instance_name: str) -> List[str]:
        """列出实例的所有数据库"""
        pass
    
    @abstractmethod
    async def list_collections(self, instance_name: str, database_name: str) -> List[str]:
        """列出数据库的所有集合"""
        pass
    
    @abstractmethod
    async def delete_instance_metadata(self, instance_name: str) -> bool:
        """删除实例元数据"""
        pass


class MongoMetadataStorage(MetadataStorageInterface):
    """MongoDB元数据存储实现"""
    
    def __init__(self, connection_manager: ConnectionManager):
        self.connection_manager = connection_manager
        self._metadata_collections: Dict[str, Dict[str, AsyncIOMotorCollection]] = {}
        self._lock = asyncio.Lock()
    
    async def init_instance_metadata_storage(self, instance_name: str) -> bool:
        """初始化实例的元数据存储"""
        try:
            # 确保实例连接可用
            if not await self.connection_manager.init_instance_metadata_on_demand(instance_name):
                return False
            
            metadata_db = self.connection_manager.get_metadata_database(instance_name)
            if not metadata_db:
                logger.error(f"无法获取实例 {instance_name} 的元数据库")
                return False
            
            # 初始化集合映射
            if instance_name not in self._metadata_collections:
                self._metadata_collections[instance_name] = {
                    'instances': metadata_db['instances'],
                    'databases': metadata_db['databases'],
                    'collections': metadata_db['collections'],
                    'scan_history': metadata_db['scan_history']
                }
            
            # 创建索引
            await self._ensure_indexes(instance_name)
            
            logger.info(f"实例 {instance_name} 元数据存储初始化完成")
            return True
            
        except Exception as e:
            logger.error(f"初始化实例 {instance_name} 元数据存储失败: {e}")
            return False
    
    async def _ensure_indexes(self, instance_name: str):
        """确保必要的索引存在"""
        try:
            collections = self._metadata_collections[instance_name]
            
            # 实例集合索引
            await collections['instances'].create_index("name", unique=True)
            
            # 数据库集合索引
            await collections['databases'].create_index([("instance_name", 1), ("name", 1)], unique=True)
            
            # 集合集合索引
            await collections['collections'].create_index(
                [("instance_name", 1), ("database_name", 1), ("name", 1)], 
                unique=True
            )
            
            # 扫描历史索引
            await collections['scan_history'].create_index([("instance_name", 1), ("scan_time", -1)])
            
        except Exception as e:
            logger.warning(f"创建索引失败: {e}")
    
    async def store_scan_result(self, scan_result: ScanResult) -> bool:
        """存储扫描结果"""
        async with self._lock:
            try:
                # 确保存储初始化
                if not await self.init_instance_metadata_storage(scan_result.instance_name):
                    return False
                
                collections = self._metadata_collections[scan_result.instance_name]
                
                # 存储实例信息
                await self._store_instance_info(collections['instances'], scan_result)
                
                # 存储数据库信息
                for db_info in scan_result.databases:
                    await self._store_database_info(collections['databases'], scan_result.instance_name, db_info)
                
                # 存储集合信息
                for coll_info in scan_result.collections:
                    await self._store_collection_info(collections['collections'], scan_result.instance_name, coll_info)
                
                # 存储扫描历史
                await self._store_scan_history(collections['scan_history'], scan_result)
                
                logger.info(f"扫描结果存储完成: {scan_result.instance_name}")
                return True
                
            except Exception as e:
                logger.error(f"存储扫描结果失败: {e}")
                return False
    
    async def _store_instance_info(self, collection: AsyncIOMotorCollection, scan_result: ScanResult):
        """存储实例信息"""
        instance_doc = {
            "name": scan_result.instance_name,
            "last_scan_time": scan_result.scan_time,
            "scan_success": scan_result.success,
            "database_count": len(scan_result.databases),
            "collection_count": len(scan_result.collections),
            "updated_at": datetime.now()
        }
        
        if scan_result.error:
            instance_doc["last_error"] = scan_result.error
        
        await collection.replace_one(
            {"name": scan_result.instance_name},
            instance_doc,
            upsert=True
        )
    
    async def _store_database_info(self, collection: AsyncIOMotorCollection, 
                                 instance_name: str, db_info: Dict[str, Any]):
        """存储数据库信息"""
        db_doc = {
            "instance_name": instance_name,
            "name": db_info["name"],
            "size_on_disk": db_info.get("size_on_disk", 0),
            "collection_count": db_info.get("collection_count", 0),
            "index_count": db_info.get("index_count", 0),
            "scanned_at": db_info.get("scanned_at", datetime.now()),
            "updated_at": datetime.now()
        }
        
        if "error" in db_info:
            db_doc["error"] = db_info["error"]
        
        await collection.replace_one(
            {"instance_name": instance_name, "name": db_info["name"]},
            db_doc,
            upsert=True
        )
    
    async def _store_collection_info(self, collection: AsyncIOMotorCollection,
                                   instance_name: str, coll_info: Dict[str, Any]):
        """存储集合信息"""
        coll_doc = {
            "instance_name": instance_name,
            "database_name": coll_info["database"],
            "name": coll_info["name"],
            "document_count": coll_info.get("document_count", 0),
            "average_size": coll_info.get("average_size", 0),
            "total_size": coll_info.get("total_size", 0),
            "indexes": coll_info.get("indexes", []),
            "fields": coll_info.get("fields", {}),
            "scanned_at": coll_info.get("scanned_at", datetime.now()),
            "updated_at": datetime.now()
        }
        
        if "error" in coll_info:
            coll_doc["error"] = coll_info["error"]
        
        await collection.replace_one(
            {
                "instance_name": instance_name,
                "database_name": coll_info["database"],
                "name": coll_info["name"]
            },
            coll_doc,
            upsert=True
        )
    
    async def _store_scan_history(self, collection: AsyncIOMotorCollection, scan_result: ScanResult):
        """存储扫描历史"""
        history_doc = {
            "instance_name": scan_result.instance_name,
            "scan_time": scan_result.scan_time,
            "success": scan_result.success,
            "database_count": len(scan_result.databases),
            "collection_count": len(scan_result.collections),
            "metadata_count": scan_result.metadata_count
        }
        
        if scan_result.error:
            history_doc["error"] = scan_result.error
        
        await collection.insert_one(history_doc)
    
    async def get_instance_metadata(self, instance_name: str) -> Optional[Dict[str, Any]]:
        """获取实例元数据"""
        try:
            if not await self.init_instance_metadata_storage(instance_name):
                return None
            
            collection = self._metadata_collections[instance_name]['instances']
            doc = await collection.find_one({"name": instance_name})
            
            if doc:
                # 移除MongoDB的_id字段
                doc.pop('_id', None)
                return doc
            
            return None
            
        except Exception as e:
            logger.error(f"获取实例 {instance_name} 元数据失败: {e}")
            return None
    
    async def get_database_metadata(self, instance_name: str, database_name: str) -> Optional[Dict[str, Any]]:
        """获取数据库元数据"""
        try:
            if not await self.init_instance_metadata_storage(instance_name):
                return None
            
            collection = self._metadata_collections[instance_name]['databases']
            doc = await collection.find_one({"instance_name": instance_name, "name": database_name})
            
            if doc:
                doc.pop('_id', None)
                return doc
            
            return None
            
        except Exception as e:
            logger.error(f"获取数据库 {instance_name}.{database_name} 元数据失败: {e}")
            return None
    
    async def get_collection_metadata(self, instance_name: str, database_name: str, 
                                    collection_name: str) -> Optional[Dict[str, Any]]:
        """获取集合元数据"""
        try:
            if not await self.init_instance_metadata_storage(instance_name):
                return None
            
            collection = self._metadata_collections[instance_name]['collections']
            doc = await collection.find_one({
                "instance_name": instance_name,
                "database_name": database_name,
                "name": collection_name
            })
            
            if doc:
                doc.pop('_id', None)
                return doc
            
            return None
            
        except Exception as e:
            logger.error(f"获取集合 {instance_name}.{database_name}.{collection_name} 元数据失败: {e}")
            return None
    
    async def list_instances(self) -> List[str]:
        """列出所有实例"""
        instances = []
        
        for instance_name in self.connection_manager.get_instance_names():
            try:
                if await self.init_instance_metadata_storage(instance_name):
                    collection = self._metadata_collections[instance_name]['instances']
                    if await collection.find_one({"name": instance_name}):
                        instances.append(instance_name)
            except Exception as e:
                logger.warning(f"检查实例 {instance_name} 失败: {e}")
        
        return instances
    
    async def list_databases(self, instance_name: str) -> List[str]:
        """列出实例的所有数据库"""
        try:
            if not await self.init_instance_metadata_storage(instance_name):
                return []
            
            collection = self._metadata_collections[instance_name]['databases']
            cursor = collection.find({"instance_name": instance_name}, {"name": 1})
            
            databases = []
            async for doc in cursor:
                databases.append(doc["name"])
            
            return databases
            
        except Exception as e:
            logger.error(f"列出实例 {instance_name} 数据库失败: {e}")
            return []
    
    async def list_collections(self, instance_name: str, database_name: str) -> List[str]:
        """列出数据库的所有集合"""
        try:
            if not await self.init_instance_metadata_storage(instance_name):
                return []
            
            collection = self._metadata_collections[instance_name]['collections']
            cursor = collection.find(
                {"instance_name": instance_name, "database_name": database_name},
                {"name": 1}
            )
            
            collections = []
            async for doc in cursor:
                collections.append(doc["name"])
            
            return collections
            
        except Exception as e:
            logger.error(f"列出数据库 {instance_name}.{database_name} 集合失败: {e}")
            return []
    
    async def delete_instance_metadata(self, instance_name: str) -> bool:
        """删除实例元数据"""
        try:
            if not await self.init_instance_metadata_storage(instance_name):
                return False
            
            collections = self._metadata_collections[instance_name]
            
            # 删除所有相关数据
            await collections['instances'].delete_many({"name": instance_name})
            await collections['databases'].delete_many({"instance_name": instance_name})
            await collections['collections'].delete_many({"instance_name": instance_name})
            await collections['scan_history'].delete_many({"instance_name": instance_name})
            
            # 从缓存中移除
            self._metadata_collections.pop(instance_name, None)
            
            logger.info(f"实例 {instance_name} 元数据删除完成")
            return True
            
        except Exception as e:
            logger.error(f"删除实例 {instance_name} 元数据失败: {e}")
            return False
    
    async def get_scan_history(self, instance_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取扫描历史"""
        try:
            if not await self.init_instance_metadata_storage(instance_name):
                return []
            
            collection = self._metadata_collections[instance_name]['scan_history']
            cursor = collection.find(
                {"instance_name": instance_name}
            ).sort("scan_time", -1).limit(limit)
            
            history = []
            async for doc in cursor:
                doc.pop('_id', None)
                history.append(doc)
            
            return history
            
        except Exception as e:
            logger.error(f"获取实例 {instance_name} 扫描历史失败: {e}")
            return []


class FileMetadataStorage(MetadataStorageInterface):
    """文件系统元数据存储实现（用于测试或轻量级部署）"""
    
    def __init__(self, storage_path: str = "./metadata_storage"):
        self.storage_path = storage_path
        self._ensure_storage_directory()
    
    def _ensure_storage_directory(self):
        """确保存储目录存在"""
        import os
        os.makedirs(self.storage_path, exist_ok=True)
    
    async def store_scan_result(self, scan_result: ScanResult) -> bool:
        """存储扫描结果到文件"""
        import json
        import os
        
        try:
            instance_dir = os.path.join(self.storage_path, scan_result.instance_name)
            os.makedirs(instance_dir, exist_ok=True)
            
            # 存储扫描结果
            result_data = {
                "instance_name": scan_result.instance_name,
                "success": scan_result.success,
                "error": scan_result.error,
                "scan_time": scan_result.scan_time.isoformat(),
                "databases": scan_result.databases,
                "collections": scan_result.collections,
                "metadata_count": scan_result.metadata_count
            }
            
            # 将datetime对象转换为字符串
            def serialize_datetime(obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                raise TypeError(f"Object {obj} is not JSON serializable")
            
            result_file = os.path.join(instance_dir, f"scan_{int(scan_result.scan_time.timestamp())}.json")
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(result_data, f, default=serialize_datetime, ensure_ascii=False, indent=2)
            
            # 更新最新结果链接
            latest_file = os.path.join(instance_dir, "latest.json")
            with open(latest_file, 'w', encoding='utf-8') as f:
                json.dump(result_data, f, default=serialize_datetime, ensure_ascii=False, indent=2)
            
            return True
            
        except Exception as e:
            logger.error(f"存储扫描结果到文件失败: {e}")
            return False
    
    # 其他方法的简化实现...
    async def get_instance_metadata(self, instance_name: str) -> Optional[Dict[str, Any]]:
        """从文件获取实例元数据"""
        import json
        import os
        
        try:
            latest_file = os.path.join(self.storage_path, instance_name, "latest.json")
            if os.path.exists(latest_file):
                with open(latest_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return None
            
        except Exception as e:
            logger.error(f"从文件读取实例 {instance_name} 元数据失败: {e}")
            return None
    
    async def get_database_metadata(self, instance_name: str, database_name: str) -> Optional[Dict[str, Any]]:
        instance_data = await self.get_instance_metadata(instance_name)
        if instance_data:
            for db in instance_data.get("databases", []):
                if db.get("name") == database_name:
                    return db
        return None
    
    async def get_collection_metadata(self, instance_name: str, database_name: str, 
                                    collection_name: str) -> Optional[Dict[str, Any]]:
        instance_data = await self.get_instance_metadata(instance_name)
        if instance_data:
            for coll in instance_data.get("collections", []):
                if (coll.get("database") == database_name and 
                    coll.get("name") == collection_name):
                    return coll
        return None
    
    async def list_instances(self) -> List[str]:
        import os
        try:
            return [d for d in os.listdir(self.storage_path) 
                   if os.path.isdir(os.path.join(self.storage_path, d))]
        except Exception:
            return []
    
    async def list_databases(self, instance_name: str) -> List[str]:
        instance_data = await self.get_instance_metadata(instance_name)
        if instance_data:
            return [db["name"] for db in instance_data.get("databases", [])]
        return []
    
    async def list_collections(self, instance_name: str, database_name: str) -> List[str]:
        instance_data = await self.get_instance_metadata(instance_name)
        if instance_data:
            return [coll["name"] for coll in instance_data.get("collections", [])
                   if coll.get("database") == database_name]
        return []
    
    async def delete_instance_metadata(self, instance_name: str) -> bool:
        import shutil
        import os
        
        try:
            instance_dir = os.path.join(self.storage_path, instance_name)
            if os.path.exists(instance_dir):
                shutil.rmtree(instance_dir)
            return True
        except Exception as e:
            logger.error(f"删除实例 {instance_name} 文件元数据失败: {e}")
            return False