# -*- coding: utf-8 -*-
"""元数据管理器"""

from typing import Dict, List, Optional, Any
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorCollection
from datetime import datetime
import structlog
from bson import ObjectId

from database.connection_manager import ConnectionManager


logger = structlog.get_logger(__name__)


class MetadataManager:
    """元数据管理器"""
    
    def __init__(self, connection_manager: ConnectionManager):
        self.connection_manager = connection_manager
        # 每个实例都有自己的元数据库，不再使用单一的_db
        self._instance_collections: Dict[str, Dict[str, AsyncIOMotorCollection]] = {}
    
    async def initialize(self) -> bool:
        """初始化元数据管理器（不预先初始化实例元数据）"""
        try:
            # 元数据管理器初始化完成，实例元数据将按需初始化
            logger.info("元数据管理器初始化完成（按需模式）")
            return True
            
        except Exception as e:
            logger.error("元数据管理器初始化失败", error=str(e))
            return False
    
    async def _create_indexes_for_instance(self, instance_name: str):
        """为指定实例创建必要的索引"""
        try:
            collections = self._instance_collections[instance_name]
            
            # instances集合索引
            await collections['instances'].create_index("instance_name", unique=True)
            await collections['instances'].create_index("environment")
            
            # databases集合索引
            await collections['databases'].create_index(
                [("instance_id", 1), ("database_name", 1)], unique=True
            )
            
            # collections集合索引
            await collections['collections'].create_index(
                [("instance_id", 1), ("database_name", 1), ("collection_name", 1)], unique=True
            )
            
            # fields集合索引
            await collections['fields'].create_index(
                [("instance_id", 1), ("database_name", 1), ("collection_name", 1), ("field_path", 1)],
                unique=True
            )
            
            # query_history集合索引
            await collections['query_history'].create_index("session_id")
            await collections['query_history'].create_index("created_at")
            
            logger.info("实例元数据索引创建完成", instance=instance_name)
            
        except Exception as e:
            logger.warning("创建实例索引时出现警告", instance=instance_name, error=str(e))
    
    async def init_instance_metadata(self, instance_name: str) -> bool:
        """按需初始化指定实例的元数据集合"""
        try:
            # 先确保连接管理器中的元数据库已初始化
            if not await self.connection_manager.init_instance_metadata_on_demand(instance_name):
                return False
            
            # 获取元数据库连接
            metadata_db = self.connection_manager.get_metadata_database(instance_name)
            if metadata_db is None:
                logger.error("无法获取实例元数据库连接", instance=instance_name)
                return False
            
            # 初始化该实例的集合引用
            self._instance_collections[instance_name] = {
                'instances': metadata_db['instances'],
                'databases': metadata_db['databases'],
                'collections': metadata_db['collections'],
                'fields': metadata_db['fields'],
                'query_history': metadata_db['query_history']
            }
            
            # 为该实例创建索引
            await self._create_indexes_for_instance(instance_name)
            
            logger.info("实例元数据按需初始化成功", instance=instance_name)
            return True
            
        except Exception as e:
            logger.error("实例元数据按需初始化失败", instance=instance_name, error=str(e))
            return False
    
    def _get_instance_collections(self, instance_name: str) -> Optional[Dict[str, AsyncIOMotorCollection]]:
        """获取指定实例的集合引用"""
        return self._instance_collections.get(instance_name)
    
    # ==================== 实例管理 ====================
    
    async def save_instance(self, target_instance_name: str, instance_config: Dict[str, Any]) -> ObjectId:
        """在指定实例的元数据库中保存实例配置"""
        collections = self._get_instance_collections(target_instance_name)
        if collections is None:
            raise ValueError(f"实例 {target_instance_name} 的元数据库不可用")
        
        instance_doc = {
            "instance_name": instance_config["name"],
            "instance_alias": instance_config["alias"],
            "connection_string": instance_config["connection_string"],
            "description": instance_config.get("description", ""),
            "environment": instance_config.get("environment", "dev"),
            "status": instance_config.get("status", "active"),
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
        
        # 使用upsert更新或插入
        result = await collections['instances'].replace_one(
            {"instance_name": instance_config["name"]},
            instance_doc,
            upsert=True
        )
        
        if result.upserted_id:
            logger.info("实例配置已保存", target_instance=target_instance_name, instance_name=instance_config["name"])
            return result.upserted_id
        else:
            # 获取现有文档的ID
            existing = await collections['instances'].find_one(
                {"instance_name": instance_config["name"]}
            )
            logger.info("实例配置已更新", target_instance=target_instance_name, instance_name=instance_config["name"])
            return existing["_id"]
    
    async def get_instance_by_name(self, target_instance_name: str, instance_name: str) -> Optional[Dict[str, Any]]:
        """根据名称获取实例信息"""
        collections = self._get_instance_collections(target_instance_name)
        if not collections:
            raise ValueError(f"实例 {target_instance_name} 的元数据库不可用")
        
        return await collections['instances'].find_one(
            {"instance_name": instance_name}
        )
    
    async def get_all_instances(self, target_instance_name: str, environment: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取所有实例"""
        collections = self._get_instance_collections(target_instance_name)
        if not collections:
            raise ValueError(f"实例 {target_instance_name} 的元数据库不可用")
        
        filter_query = {}
        if environment:
            filter_query["environment"] = environment
        
        cursor = collections['instances'].find(filter_query)
        return await cursor.to_list(length=None)
    
    # ==================== 数据库管理 ====================
    
    async def save_database(self, target_instance_name: str, instance_id: ObjectId, db_info: Dict[str, Any]) -> ObjectId:
        """保存数据库信息"""
        collections = self._get_instance_collections(target_instance_name)
        if not collections:
            raise ValueError(f"实例 {target_instance_name} 的元数据库不可用")
        
        db_doc = {
            "instance_id": instance_id,
            "database_name": db_info["name"],
            "description": db_info.get("description", ""),
            "business_domain": db_info.get("business_domain", ""),
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "status": "active"
        }
        
        result = await collections['databases'].replace_one(
            {"instance_id": instance_id, "database_name": db_info["name"]},
            db_doc,
            upsert=True
        )
        
        if result.upserted_id:
            return result.upserted_id
        else:
            existing = await collections['databases'].find_one(
                {"instance_id": instance_id, "database_name": db_info["name"]}
            )
            return existing["_id"]
    
    async def get_databases_by_instance(self, target_instance_name: str, instance_id: ObjectId) -> List[Dict[str, Any]]:
        """获取实例的所有数据库"""
        collections = self._get_instance_collections(target_instance_name)
        if collections is None:
            raise ValueError(f"实例 {target_instance_name} 的元数据库不可用")
        
        cursor = collections['databases'].find({"instance_id": instance_id})
        return await cursor.to_list(length=None)
    
    async def search_databases(self, target_instance_name: str, query: str, instance_id: Optional[ObjectId] = None) -> List[Dict[str, Any]]:
        """搜索数据库"""
        collections = self._get_instance_collections(target_instance_name)
        if not collections:
            raise ValueError(f"实例 {target_instance_name} 的元数据库不可用")
        
        filter_query = {
            "$or": [
                {"database_name": {"$regex": query, "$options": "i"}},
                {"description": {"$regex": query, "$options": "i"}},
                {"business_domain": {"$regex": query, "$options": "i"}}
            ]
        }
        
        if instance_id:
            filter_query["instance_id"] = instance_id
        
        cursor = collections['databases'].find(filter_query)
        return await cursor.to_list(length=None)
    
    # ==================== 集合管理 ====================
    
    async def save_collection(self, target_instance_name: str, instance_id: ObjectId, collection_info: Dict[str, Any]) -> ObjectId:
        """保存集合信息"""
        collections = self._get_instance_collections(target_instance_name)
        if not collections:
            raise ValueError(f"实例 {target_instance_name} 的元数据库不可用")
        
        collection_doc = {
            "instance_id": instance_id,
            "database_name": collection_info["database"],
            "collection_name": collection_info["name"],
            "description": collection_info.get("description", ""),
            "business_purpose": collection_info.get("business_purpose", ""),
            "sample_documents": collection_info.get("sample_documents", []),
            "document_count": collection_info.get("document_count", 0),
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
        
        result = await collections['collections'].replace_one(
            {
                "instance_id": instance_id,
                "database_name": collection_info["database"],
                "collection_name": collection_info["name"]
            },
            collection_doc,
            upsert=True
        )
        
        if result.upserted_id:
            return result.upserted_id
        else:
            existing = await collections['collections'].find_one({
                "instance_id": instance_id,
                "database_name": collection_info["database"],
                "collection_name": collection_info["name"]
            })
            return existing["_id"]
    
    async def get_collections_by_database(self, target_instance_name: str, instance_id: ObjectId, database_name: str) -> List[Dict[str, Any]]:
        """获取数据库的所有集合"""
        collections = self._get_instance_collections(target_instance_name)
        if collections is None:
            raise ValueError(f"实例 {target_instance_name} 的元数据库不可用")
        
        cursor = collections['collections'].find({
            "instance_id": instance_id,
            "database_name": database_name
        })
        return await cursor.to_list(length=None)
    
    # ==================== 字段管理 ====================
    
    async def save_field(self, target_instance_name: str, instance_id: ObjectId, field_info: Dict[str, Any]) -> ObjectId:
        """保存字段信息"""
        collections = self._get_instance_collections(target_instance_name)
        if not collections:
            raise ValueError(f"实例 {target_instance_name} 的元数据库不可用")
        
        field_doc = {
            "instance_id": instance_id,
            "database_name": field_info["database"],
            "collection_name": field_info["collection"],
            "field_path": field_info["path"],
            "field_type": field_info.get("type", "unknown"),
            "business_meaning": field_info.get("business_meaning", ""),
            "examples": field_info.get("examples", []),
            "is_indexed": field_info.get("is_indexed", False),
            "is_required": field_info.get("is_required", False),
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
        
        result = await collections['fields'].replace_one(
            {
                "instance_id": instance_id,
                "database_name": field_info["database"],
                "collection_name": field_info["collection"],
                "field_path": field_info["path"]
            },
            field_doc,
            upsert=True
        )
        
        if result.upserted_id:
            return result.upserted_id
        else:
            existing = await collections['fields'].find_one({
                "instance_id": instance_id,
                "database_name": field_info["database"],
                "collection_name": field_info["collection"],
                "field_path": field_info["path"]
            })
            return existing["_id"]
    
    async def get_fields_by_collection(self, target_instance_name: str, instance_id: ObjectId, database_name: str, collection_name: str) -> List[Dict[str, Any]]:
        """获取集合的所有字段"""
        collections = self._get_instance_collections(target_instance_name)
        if collections is None:
            raise ValueError(f"实例 {target_instance_name} 的元数据库不可用")
        
        cursor = collections['fields'].find({
            "instance_id": instance_id,
            "database_name": database_name,
            "collection_name": collection_name
        })
        return await cursor.to_list(length=None)
    
    async def update_field_semantics(self, target_instance_name: str, instance_id: ObjectId, database_name: str, 
                                   collection_name: str, field_path: str, 
                                   business_meaning: str, examples: List[str] = None) -> bool:
        """更新字段业务语义"""
        collections = self._get_instance_collections(target_instance_name)
        if not collections:
            raise ValueError(f"实例 {target_instance_name} 的元数据库不可用")
        
        update_doc = {
            "business_meaning": business_meaning,
            "updated_at": datetime.now()
        }
        
        if examples:
            update_doc["examples"] = examples
        
        result = await collections['fields'].update_one(
            {
                "instance_id": instance_id,
                "database_name": database_name,
                "collection_name": collection_name,
                "field_path": field_path
            },
            {"$set": update_doc}
        )
        
        if result.modified_count > 0:
            logger.info(
                "字段语义已更新",
                instance_id=str(instance_id),
                database=database_name,
                collection=collection_name,
                field=field_path
            )
            return True
        return False
    
    # ==================== 查询历史管理 ====================
    
    async def save_query_history(self, target_instance_name: str, query_info: Dict[str, Any]) -> ObjectId:
        """保存查询历史"""
        collections = self._get_instance_collections(target_instance_name)
        if not collections:
            raise ValueError(f"实例 {target_instance_name} 的元数据库不可用")
        
        query_doc = {
            "session_id": query_info["session_id"],
            "instance_id": query_info["instance_id"],
            "user_intent": query_info["user_intent"],
            "selected_database": query_info.get("selected_database"),
            "selected_collection": query_info.get("selected_collection"),
            "generated_query": query_info.get("generated_query"),
            "execution_result": query_info.get("execution_result"),
            "user_feedback": query_info.get("user_feedback", ""),
            "created_at": datetime.now()
        }
        
        result = await collections['query_history'].insert_one(query_doc)
        return result.inserted_id
    
    async def get_query_history(self, target_instance_name: str, session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取查询历史"""
        collections = self._get_instance_collections(target_instance_name)
        if not collections:
            raise ValueError(f"实例 {target_instance_name} 的元数据库不可用")
        
        cursor = collections['query_history'].find(
            {"session_id": session_id}
        ).sort("created_at", -1).limit(limit)
        
        return await cursor.to_list(length=None)
    
    # ==================== 搜索和推荐 ====================
    
    async def search_by_business_meaning(self, target_instance_name: str, query: str, instance_id: Optional[ObjectId] = None) -> Dict[str, List[Dict[str, Any]]]:
        """根据业务含义搜索"""
        collections = self._get_instance_collections(target_instance_name)
        if not collections:
            raise ValueError(f"实例 {target_instance_name} 的元数据库不可用")
        
        results = {
            "databases": [],
            "collections": [],
            "fields": []
        }
        
        search_filter = {
            "$or": [
                {"business_meaning": {"$regex": query, "$options": "i"}},
                {"description": {"$regex": query, "$options": "i"}}
            ]
        }
        
        if instance_id:
            search_filter["instance_id"] = instance_id
        
        # 搜索数据库
        db_cursor = collections['databases'].find(search_filter)
        results["databases"] = await db_cursor.to_list(length=None)
        
        # 搜索集合
        collection_filter = search_filter.copy()
        collection_filter["$or"].append({"business_purpose": {"$regex": query, "$options": "i"}})
        collection_cursor = collections['collections'].find(collection_filter)
        results["collections"] = await collection_cursor.to_list(length=None)
        
        # 搜索字段
        field_cursor = collections['fields'].find(search_filter)
        results["fields"] = await field_cursor.to_list(length=None)
        
        return results
    
    async def get_statistics(self, target_instance_name: str) -> Dict[str, Any]:
        """获取统计信息"""
        collections = self._get_instance_collections(target_instance_name)
        if not collections:
            raise ValueError(f"实例 {target_instance_name} 的元数据库不可用")
        
        stats = {}
        
        # 实例统计
        stats["instances_count"] = await collections['instances'].count_documents({})
        stats["active_instances_count"] = await collections['instances'].count_documents({"status": "active"})
        
        # 数据库统计
        stats["databases_count"] = await collections['databases'].count_documents({})
        
        # 集合统计
        stats["collections_count"] = await collections['collections'].count_documents({})
        
        # 字段统计
        stats["fields_count"] = await collections['fields'].count_documents({})
        stats["fields_with_semantics_count"] = await collections['fields'].count_documents({
            "business_meaning": {"$ne": ""}
        })
        
        # 查询历史统计
        stats["query_history_count"] = await collections['query_history'].count_documents({})
        
        return stats