# -*- coding: utf-8 -*-
"""元数据管理器"""

from typing import Dict, List, Optional, Any
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorCollection
from datetime import datetime
import structlog
import asyncio
from bson import ObjectId

from database.connection_manager import ConnectionManager
from storage.local_semantic_storage import LocalSemanticStorage
from storage.semantic_file_manager import SemanticFileManager
from storage.config import get_config


logger = structlog.get_logger(__name__)


class MetadataManager:
    """元数据管理器"""
    
    def __init__(self, connection_manager: ConnectionManager):
        self.connection_manager = connection_manager
        # 每个实例都有自己的元数据库，不再使用单一的_db
        self._instance_collections: Dict[str, Dict[str, AsyncIOMotorCollection]] = {}
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
        self._collection_timestamps: Dict[str, Dict[str, datetime]] = {}  # instance -> {collection: last_modified}
        
        # 初始化本地存储组件
        self.config = get_config()
        self.local_storage = LocalSemanticStorage()
        self.file_manager = SemanticFileManager()
    
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
            
            # 获取实例信息
            instance_doc = await self.get_instance_by_name(instance_name, instance_name)
            if not instance_doc:
                # 创建实例记录
                instance_config = {
                    "name": instance_name,
                    "alias": instance_name,
                    "connection_string": "auto_discovered",
                    "description": "自动发现的实例",
                    "environment": "unknown"
                }
                instance_id = await self.save_instance(instance_name, instance_config)
            else:
                instance_id = instance_doc["_id"]
            
            # 获取数据库列表
            database_names = await instance_connection.client.list_database_names()
            
            scan_count = 0
            for db_name in database_names:
                # 跳过系统数据库
                if db_name in ['admin', 'config', 'local']:
                    continue
                
                try:
                    # 扫描数据库
                    if await self._scan_database_metadata(instance_name, instance_id, db_name, full_scan):
                        scan_count += 1
                except Exception as e:
                    logger.warning(f"扫描数据库 {db_name} 失败", error=str(e))
                    continue
            
            # 更新扫描时间
            self.last_scan_time[instance_name] = datetime.now()
            
            logger.info(f"实例 {instance_name} 元数据扫描完成，处理了 {scan_count} 个数据库")
            return True
            
        except Exception as e:
            logger.error(f"扫描实例 {instance_name} 元数据失败", error=str(e))
            return False
    
    async def scan_instance_metadata_incremental(self, instance_name: str) -> bool:
        """增量扫描实例元数据"""
        try:
            # 检查缓存
            cache_key = f"metadata_{instance_name}"
            if cache_key in self.metadata_cache:
                self._scan_stats['cache_hits'] += 1
                logger.debug(f"使用缓存的元数据: {instance_name}")
                return True
            
            self._scan_stats['cache_misses'] += 1
            
            # 执行增量扫描（只扫描变更的集合）
            return await self.scan_instance_metadata(instance_name, full_scan=False)
            
        except Exception as e:
            logger.error(f"增量扫描实例 {instance_name} 失败", error=str(e))
            return False
    
    async def _scan_database_metadata(self, instance_name: str, instance_id: ObjectId, 
                                    database_name: str, full_scan: bool = False) -> bool:
        """扫描数据库元数据"""
        try:
            # 保存数据库信息
            db_info = {
                "name": database_name,
                "description": f"自动发现的数据库: {database_name}"
            }
            await self.save_database(instance_name, instance_id, db_info)
            
            # 获取数据库连接
            database = self.connection_manager.get_instance_database(instance_name, database_name)
            if not database:
                return False
            
            # 获取集合列表
            collection_names = await database.list_collection_names()
            
            for collection_name in collection_names:
                # 跳过系统集合
                if collection_name.startswith('system.') or collection_name.startswith('_querynest'):
                    continue
                
                try:
                    await self._scan_collection_metadata(
                        instance_name, instance_id, database_name, 
                        collection_name, database, full_scan
                    )
                except Exception as e:
                    logger.warning(f"扫描集合 {collection_name} 失败", error=str(e))
                    continue
            
            return True
            
        except Exception as e:
            logger.error(f"扫描数据库 {database_name} 失败", error=str(e))
            return False
    
    async def _scan_collection_metadata(self, instance_name: str, instance_id: ObjectId,
                                      database_name: str, collection_name: str,
                                      database, full_scan: bool = False) -> bool:
        """扫描集合元数据"""
        try:
            collection = database[collection_name]
            
            # 获取文档数量
            doc_count = await collection.count_documents({})
            
            # 获取样本文档
            sample_docs = []
            if doc_count > 0:
                cursor = collection.find().limit(3)
                async for doc in cursor:
                    # 转换ObjectId为字符串以便序列化
                    sample_doc = self._serialize_document(doc)
                    sample_docs.append(sample_doc)
            
            # 保存集合信息
            collection_info = {
                "database": database_name,
                "name": collection_name,
                "description": f"自动发现的集合: {collection_name}",
                "document_count": doc_count,
                "sample_documents": sample_docs
            }
            await self.save_collection(instance_name, instance_id, collection_info)
            
            # 分析字段结构
            if full_scan or doc_count <= 1000:  # 小集合或全量扫描时分析字段
                await self._analyze_collection_fields(
                    instance_name, instance_id, database_name, 
                    collection_name, collection
                )
            
            return True
            
        except Exception as e:
            logger.error(f"扫描集合 {collection_name} 失败", error=str(e))
            return False
    
    async def _analyze_collection_fields(self, instance_name: str, instance_id: ObjectId,
                                       database_name: str, collection_name: str, collection) -> bool:
        """分析集合字段结构"""
        try:
            # 使用聚合管道分析字段
            pipeline = [
                {"$sample": {"size": 100}},  # 采样100个文档
                {"$project": {"arrayofkeyvalue": {"$objectToArray": "$$ROOT"}}},
                {"$unwind": "$arrayofkeyvalue"},
                {"$group": {
                    "_id": {
                        "field": "$arrayofkeyvalue.k",
                        "type": {"$type": "$arrayofkeyvalue.v"}
                    },
                    "count": {"$sum": 1},
                    "examples": {"$addToSet": "$arrayofkeyvalue.v"}
                }},
                {"$sort": {"count": -1}}
            ]
            
            field_stats = {}
            async for result in collection.aggregate(pipeline):
                field_name = result["_id"]["field"]
                field_type = result["_id"]["type"]
                count = result["count"]
                examples = result["examples"][:5]  # 只保留前5个示例
                
                if field_name not in field_stats:
                    field_stats[field_name] = {
                        "types": {},
                        "total_count": 0,
                        "examples": []
                    }
                
                field_stats[field_name]["types"][field_type] = count
                field_stats[field_name]["total_count"] += count
                field_stats[field_name]["examples"].extend(examples)
            
            # 保存字段信息
            for field_name, stats in field_stats.items():
                # 确定主要类型
                main_type = max(stats["types"], key=stats["types"].get)
                
                field_info = {
                    "database": database_name,
                    "collection": collection_name,
                    "path": field_name,
                    "type": main_type,
                    "examples": list(set(str(ex) for ex in stats["examples"][:5])),
                    "is_indexed": False,  # 需要额外查询索引信息
                    "is_required": stats["total_count"] > 0
                }
                
                await self.save_field(instance_name, instance_id, field_info)
            
            return True
            
        except Exception as e:
            logger.error(f"分析集合 {collection_name} 字段失败", error=str(e))
            return False
    
    def _serialize_document(self, doc: Dict) -> Dict:
        """序列化文档，处理特殊类型"""
        if isinstance(doc, dict):
            result = {}
            for key, value in doc.items():
                if isinstance(value, ObjectId):
                    result[key] = str(value)
                elif isinstance(value, datetime):
                    result[key] = value.isoformat()
                elif isinstance(value, (dict, list)):
                    result[key] = self._serialize_document(value)
                else:
                    result[key] = value
            return result
        elif isinstance(doc, list):
            return [self._serialize_document(item) for item in doc]
        else:
            return doc
    
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
            
            # semantic_learning集合索引（用于语义学习历史）
            await collections['semantic_learning'].create_index("instance_id")
            await collections['semantic_learning'].create_index("created_at")
            await collections['semantic_learning'].create_index([
                ("instance_id", 1), 
                ("database_name", 1), 
                ("collection_name", 1)
            ])
            
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
                'query_history': metadata_db['query_history'],
                'semantic_learning': metadata_db['semantic_learning']
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
        """更新字段业务语义，使用本地文件存储"""
        
        try:
            success = await self.local_storage.save_field_semantics(
                target_instance_name, database_name, collection_name, 
                field_path, business_meaning, examples or []
            )
            if success:
                logger.info(
                    "字段语义已保存到本地文件",
                    instance=target_instance_name,
                    database=database_name,
                    collection=collection_name,
                    field=field_path,
                    meaning=business_meaning
                )
            return success
        except Exception as e:
            logger.error("本地文件语义保存失败", error=str(e))
            return False
    
    async def _update_metadata_semantics(self, target_instance_name: str, instance_id: ObjectId, 
                                       database_name: str, collection_name: str, field_path: str, 
                                       business_meaning: str, examples: List[str] = None) -> bool:
        """在元数据库中更新字段语义"""
        try:
            collections = self._get_instance_collections(target_instance_name)
            if not collections:
                logger.warning("元数据库集合不可用", instance=target_instance_name)
                return False
            
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
            
            return result.modified_count > 0
            
        except Exception as e:
            logger.warning(
                "元数据库语义更新失败，将尝试业务库存储",
                instance=target_instance_name,
                error=str(e)
            )
            return False
    
    async def _update_business_semantics(self, target_instance_name: str, database_name: str, 
                                       collection_name: str, field_path: str, 
                                       business_meaning: str, examples: List[str] = None) -> bool:
        """在业务库中存储字段语义"""
        try:
            # 获取业务数据库连接
            business_db = self.connection_manager.get_instance_database(target_instance_name, database_name)
            if business_db is None:
                logger.error("无法获取业务数据库连接", instance=target_instance_name, database=database_name)
                return False
            
            # 在业务库中创建或更新语义集合
            semantics_collection = business_db['_querynest_semantics']
            
            semantic_doc = {
                "collection_name": collection_name,
                "field_path": field_path,
                "business_meaning": business_meaning,
                "updated_at": datetime.now(),
                "source": "querynest_analyzer"
            }
            
            if examples:
                semantic_doc["examples"] = examples
            
            # 使用 upsert 更新或插入语义信息
            result = await semantics_collection.replace_one(
                {
                    "collection_name": collection_name,
                    "field_path": field_path
                },
                semantic_doc,
                upsert=True
            )
            
            logger.info(
                "字段语义已存储至业务库",
                instance=target_instance_name,
                database=database_name,
                collection=collection_name,
                field=field_path,
                business_collection="_querynest_semantics"
            )
            
            return True
            
        except Exception as e:
            logger.error(
                "业务库语义存储失败",
                instance=target_instance_name,
                database=database_name,
                error=str(e)
            )
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
    
    async def search_fields_by_meaning(self, target_instance_name: str, search_term: str) -> List[Dict[str, Any]]:
        """根据业务含义搜索字段，使用本地文件存储"""
        try:
            results = await self.local_storage.search_semantics(target_instance_name, search_term)
            logger.info(
                "本地文件语义搜索完成",
                target_instance=target_instance_name,
                search_term=search_term,
                total_results=len(results)
            )
            return results
        except Exception as e:
            logger.error("本地文件语义搜索失败", error=str(e))
            return []
    
    async def _search_metadata_semantics(self, target_instance_name: str, search_term: str) -> List[Dict[str, Any]]:
        """在元数据库中搜索语义信息"""
        collections = self._get_instance_collections(target_instance_name)
        if not collections:
            return []
        
        # 构建搜索条件：在字段路径、业务含义、示例中搜索
        search_filter = {
            "$or": [
                {"field_path": {"$regex": search_term, "$options": "i"}},
                {"business_meaning": {"$regex": search_term, "$options": "i"}},
                {"examples": {"$elemMatch": {"$regex": search_term, "$options": "i"}}}
            ]
        }
        
        field_cursor = collections['fields'].find(search_filter)
        results = await field_cursor.to_list(length=None)
        
        # 为结果添加来源标记
        for result in results:
            result["semantic_source"] = "metadata_db"
        
        return results
    
    async def _search_business_semantics(self, target_instance_name: str, search_term: str) -> List[Dict[str, Any]]:
        """在业务库中搜索语义信息"""
        results = []
        
        # 获取实例的所有数据库
        try:
            # 这里需要从配置或连接管理器获取数据库列表
            # 暂时使用一个简化的方式
            instance_connection = self.connection_manager.get_instance_connection(target_instance_name)
            if not instance_connection or not instance_connection.client:
                return []
            
            # 获取所有数据库名称
            database_names = await instance_connection.client.list_database_names()
            
            # 搜索每个数据库的语义集合
            for db_name in database_names:
                # 跳过系统数据库
                if db_name in ['admin', 'config', 'local', 'querynest_metadata']:
                    continue
                
                try:
                    business_db = instance_connection.get_database(db_name)
                    if business_db is None:
                        continue
                    
                    # 检查是否存在语义集合
                    collection_names = await business_db.list_collection_names()
                    if '_querynest_semantics' not in collection_names:
                        continue
                    
                    semantics_collection = business_db['_querynest_semantics']
                    
                    # 构建搜索条件 - 修复examples字段的搜索语法
                    search_filter = {
                        "$or": [
                            {"field_path": {"$regex": search_term, "$options": "i"}},
                            {"business_meaning": {"$regex": search_term, "$options": "i"}},
                            {"examples": {"$elemMatch": {"$regex": search_term, "$options": "i"}}}
                        ]
                    }
                    
                    cursor = semantics_collection.find(search_filter)
                    db_results = await cursor.to_list(length=None)
                    
                    # 为结果添加数据库信息和来源标记
                    for result in db_results:
                        result["database_name"] = db_name
                        result["semantic_source"] = "business_db"
                        # 确保有实例ID字段（兼容性）
                        if "instance_id" not in result:
                            result["instance_id"] = target_instance_name
                        results.append(result)
                        
                except Exception as e:
                    logger.debug(f"搜索业务库 {db_name} 语义信息时出错", error=str(e))
                    continue
        
        except Exception as e:
            logger.warning("获取业务库列表失败", error=str(e))
        
        return results
    
    def _deduplicate_semantic_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """去重语义搜索结果，优先级：本地文件 > 元数据库 > 业务库"""
        seen = set()
        unique_results = []
        
        # 优先级1：本地文件的结果
        for result in results:
            if result.get("semantic_source") == "local_file":
                key = (result.get("database_name", ""), result.get("collection_name", ""), result.get("field_path", ""))
                if key not in seen:
                    seen.add(key)
                    unique_results.append(result)
        
        # 优先级2：元数据库的结果
        for result in results:
            if result.get("semantic_source") == "metadata_db":
                key = (result.get("database_name", ""), result.get("collection_name", ""), result.get("field_path", ""))
                if key not in seen:
                    seen.add(key)
                    unique_results.append(result)
        
        # 优先级3：业务库的结果
        for result in results:
            if result.get("semantic_source") == "business_db":
                key = (result.get("database_name", ""), result.get("collection_name", ""), result.get("field_path", ""))
                if key not in seen:
                    seen.add(key)
                    unique_results.append(result)
        
        return unique_results
    
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
        
        # 扫描统计
        stats["scan_stats"] = self._scan_stats.copy()
        
        return stats