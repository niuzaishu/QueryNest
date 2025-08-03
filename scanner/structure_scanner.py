# -*- coding: utf-8 -*-
"""数据库结构扫描器"""

import asyncio
from typing import Dict, List, Optional, Any, Set
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import PyMongoError
import structlog
from datetime import datetime
from bson import ObjectId
import random

from database.connection_manager import ConnectionManager
from database.metadata_manager import MetadataManager
from config import QueryNestConfig


logger = structlog.get_logger(__name__)


class StructureScanner:
    """数据库结构扫描器"""
    
    def __init__(self, connection_manager: ConnectionManager, 
                 metadata_manager: MetadataManager, config: QueryNestConfig):
        self.connection_manager = connection_manager
        self.metadata_manager = metadata_manager
        self.config = config
        self.sample_size = 100  # 每个集合的采样文档数量
        self.max_field_depth = 5  # 最大字段嵌套深度
    
    async def scan_instance_on_demand(self, instance_name: str) -> Dict[str, Any]:
        """按需扫描指定实例的数据库结构（用户确认实例后调用）"""
        logger.info("开始按需扫描MongoDB实例结构", instance_name=instance_name)
        
        scan_results = {
            "instance_name": instance_name,
            "databases_count": 0,
            "collections_count": 0,
            "fields_count": 0,
            "errors": []
        }
        
        try:
            # 确保元数据管理器已为该实例初始化
            if not await self.metadata_manager.init_instance_metadata(instance_name):
                raise Exception("无法初始化实例元数据库")
            
            # 获取或创建实例记录
            instance_info = self.connection_manager.get_instance_info(instance_name)
            if not instance_info:
                raise Exception("无法获取实例信息")
            
            instance_id = await self._ensure_instance_record(instance_name, instance_info)
            
            # 扫描实例结构
            instance_result = await self.scan_instance_structure(instance_name, instance_id)
            
            scan_results["databases_count"] = instance_result["databases_count"]
            scan_results["collections_count"] = instance_result["collections_count"]
            scan_results["fields_count"] = instance_result["fields_count"]
            
            if instance_result["errors"]:
                scan_results["errors"].extend(instance_result["errors"])
            
            logger.info(
                "实例按需扫描完成",
                instance_name=instance_name,
                databases=scan_results["databases_count"],
                collections=scan_results["collections_count"],
                fields=scan_results["fields_count"]
            )
                
        except Exception as e:
            error_msg = f"扫描实例 {instance_name} 时发生异常: {str(e)}"
            logger.error(error_msg)
            scan_results["errors"].append(error_msg)
        
        return scan_results
    
    async def scan_instance_structure(self, instance_name: str, instance_id: ObjectId) -> Dict[str, Any]:
        """扫描单个实例的结构"""
        result = {
            "databases_count": 0,
            "collections_count": 0,
            "fields_count": 0,
            "errors": []
        }
        
        try:
            # 获取实例连接
            connection = self.connection_manager.get_instance_connection(instance_name)
            if not connection or not connection.client:
                raise Exception("无法获取实例连接")
            
            # 获取所有数据库
            databases = await connection.client.list_database_names()
            
            # 过滤系统数据库
            user_databases = [db for db in databases if not self._is_system_database(db)]
            
            for db_name in user_databases:
                try:
                    db_result = await self.scan_database_structure(instance_name, instance_id, db_name)
                    result["databases_count"] += 1
                    result["collections_count"] += db_result["collections_count"]
                    result["fields_count"] += db_result["fields_count"]
                    
                    if db_result["errors"]:
                        result["errors"].extend(db_result["errors"])
                        
                except Exception as e:
                    error_msg = f"扫描数据库 {db_name} 时发生异常: {str(e)}"
                    logger.error(error_msg, instance_name=instance_name)
                    result["errors"].append(error_msg)
        
        except Exception as e:
            error_msg = f"扫描实例结构时发生异常: {str(e)}"
            logger.error(error_msg, instance_name=instance_name)
            result["errors"].append(error_msg)
        
        return result
    
    async def scan_database_structure(self, instance_name: str, instance_id: ObjectId, database_name: str) -> Dict[str, Any]:
        """扫描数据库结构"""
        result = {
            "collections_count": 0,
            "fields_count": 0,
            "errors": []
        }
        
        try:
            # 获取数据库连接
            db = self.connection_manager.get_instance_database(instance_name, database_name)
            if not db:
                raise Exception("无法获取数据库连接")
            
            # 保存数据库信息
            await self.metadata_manager.save_database(instance_name, {
                "name": database_name,
                "instance_id": instance_id,
                "description": "",
                "business_domain": ""
            })
            
            # 获取所有集合
            collections = await db.list_collection_names()
            
            # 过滤系统集合
            user_collections = [coll for coll in collections if not self._is_system_collection(coll)]
            
            for collection_name in user_collections:
                try:
                    collection_result = await self.scan_collection_structure(
                        instance_name, instance_id, database_name, collection_name
                    )
                    result["collections_count"] += 1
                    result["fields_count"] += collection_result["fields_count"]
                    
                    if collection_result["errors"]:
                        result["errors"].extend(collection_result["errors"])
                        
                except Exception as e:
                    error_msg = f"扫描集合 {collection_name} 时发生异常: {str(e)}"
                    logger.error(error_msg, instance_name=instance_name, database=database_name)
                    result["errors"].append(error_msg)
        
        except Exception as e:
            error_msg = f"扫描数据库结构时发生异常: {str(e)}"
            logger.error(error_msg, instance_name=instance_name, database=database_name)
            result["errors"].append(error_msg)
        
        return result
    
    async def scan_collection_structure(self, instance_name: str, instance_id: ObjectId, 
                                      database_name: str, collection_name: str) -> Dict[str, Any]:
        """扫描集合结构"""
        result = {
            "fields_count": 0,
            "errors": []
        }
        
        try:
            # 获取集合连接
            db = self.connection_manager.get_instance_database(instance_name, database_name)
            if db is None:
                raise Exception("无法获取数据库连接")
            
            collection = db[collection_name]
            
            # 获取集合统计信息
            try:
                stats = await db.command("collStats", collection_name)
                document_count = stats.get("count", 0)
            except:
                # 如果collStats失败，使用count_documents
                document_count = await collection.count_documents({})
            
            # 获取索引信息
            indexes = await collection.list_indexes().to_list(length=None)
            indexed_fields = set()
            for index in indexes:
                if "key" in index:
                    for field_name in index["key"].keys():
                        indexed_fields.add(field_name)
            
            # 采样文档分析字段结构
            sample_documents = await self._sample_documents(collection, min(self.sample_size, document_count))
            
            # 分析字段结构
            field_analysis = self._analyze_document_fields(sample_documents)
            
            # 保存集合信息
            await self.metadata_manager.save_collection(instance_name, instance_id, {
                "database": database_name,
                "name": collection_name,
                "description": "",
                "business_purpose": "",
                "sample_documents": sample_documents[:5],  # 只保存前5个样本
                "document_count": document_count
            })
            
            # 保存字段信息
            for field_path, field_info in field_analysis.items():
                await self.metadata_manager.save_field(instance_name, instance_id, {
                    "database": database_name,
                    "collection": collection_name,
                    "path": field_path,
                    "type": field_info["type"],
                    "business_meaning": "",
                    "examples": field_info["examples"][:10],  # 最多保存10个示例
                    "is_indexed": field_path in indexed_fields,
                    "is_required": field_info["occurrence_rate"] > 0.9  # 出现率>90%认为是必需字段
                })
                
                result["fields_count"] += 1
            
            logger.info(
                "集合扫描完成",
                instance_name=instance_name,
                database=database_name,
                collection=collection_name,
                document_count=document_count,
                fields_count=result["fields_count"]
            )
        
        except Exception as e:
            error_msg = f"扫描集合结构时发生异常: {str(e)}"
            logger.error(error_msg, instance_name=instance_name, database=database_name, collection=collection_name)
            result["errors"].append(error_msg)
        
        return result
    
    async def _sample_documents(self, collection, sample_size: int) -> List[Dict[str, Any]]:
        """采样文档"""
        if sample_size <= 0:
            return []
        
        try:
            # 使用聚合管道进行随机采样
            pipeline = [{"$sample": {"size": sample_size}}]
            cursor = collection.aggregate(pipeline)
            documents = await cursor.to_list(length=None)
            
            # 转换ObjectId为字符串以便序列化
            for doc in documents:
                self._convert_objectids_to_strings(doc)
            
            return documents
            
        except Exception as e:
            logger.warning("随机采样失败，使用顺序采样", error=str(e))
            
            # 如果随机采样失败，使用顺序采样
            try:
                cursor = collection.find().limit(sample_size)
                documents = await cursor.to_list(length=None)
                
                for doc in documents:
                    self._convert_objectids_to_strings(doc)
                
                return documents
            except Exception as e2:
                logger.error("文档采样失败", error=str(e2))
                return []
    
    def _convert_objectids_to_strings(self, obj):
        """递归转换ObjectId为字符串"""
        if isinstance(obj, ObjectId):
            return str(obj)
        elif isinstance(obj, dict):
            for key, value in obj.items():
                obj[key] = self._convert_objectids_to_strings(value)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                obj[i] = self._convert_objectids_to_strings(item)
        return obj
    
    def _analyze_document_fields(self, documents: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """分析文档字段结构"""
        field_analysis = {}
        total_docs = len(documents)
        
        if total_docs == 0:
            return field_analysis
        
        for doc in documents:
            self._extract_fields_from_document(doc, field_analysis, total_docs)
        
        # 计算字段统计信息
        for field_path, field_info in field_analysis.items():
            field_info["occurrence_rate"] = field_info["count"] / total_docs
            
            # 确定主要类型
            if field_info["types"]:
                main_type = max(field_info["types"], key=field_info["types"].get)
                field_info["type"] = main_type
            else:
                field_info["type"] = "unknown"
        
        return field_analysis
    
    def _extract_fields_from_document(self, doc: Dict[str, Any], field_analysis: Dict[str, Dict[str, Any]], 
                                    total_docs: int, prefix: str = "", depth: int = 0):
        """从文档中提取字段信息"""
        if depth > self.max_field_depth:
            return
        
        for key, value in doc.items():
            field_path = f"{prefix}.{key}" if prefix else key
            
            # 初始化字段信息
            if field_path not in field_analysis:
                field_analysis[field_path] = {
                    "count": 0,
                    "types": {},
                    "examples": [],
                    "occurrence_rate": 0.0
                }
            
            field_info = field_analysis[field_path]
            field_info["count"] += 1
            
            # 确定值类型
            value_type = self._get_value_type(value)
            if value_type in field_info["types"]:
                field_info["types"][value_type] += 1
            else:
                field_info["types"][value_type] = 1
            
            # 收集示例值
            if len(field_info["examples"]) < 10:  # 最多保存10个示例
                example_value = self._get_example_value(value)
                if example_value not in field_info["examples"]:
                    field_info["examples"].append(example_value)
            
            # 递归处理嵌套对象
            if isinstance(value, dict) and depth < self.max_field_depth:
                self._extract_fields_from_document(value, field_analysis, total_docs, field_path, depth + 1)
            elif isinstance(value, list) and value and isinstance(value[0], dict) and depth < self.max_field_depth:
                # 处理对象数组的第一个元素
                self._extract_fields_from_document(value[0], field_analysis, total_docs, field_path, depth + 1)
    
    def _get_value_type(self, value) -> str:
        """获取值的类型"""
        if value is None:
            return "null"
        elif isinstance(value, bool):
            return "boolean"
        elif isinstance(value, int):
            return "integer"
        elif isinstance(value, float):
            return "double"
        elif isinstance(value, str):
            return "string"
        elif isinstance(value, datetime):
            return "date"
        elif isinstance(value, ObjectId):
            return "objectId"
        elif isinstance(value, dict):
            return "object"
        elif isinstance(value, list):
            return "array"
        else:
            return "unknown"
    
    def _get_example_value(self, value) -> Any:
        """获取示例值（简化版本）"""
        if isinstance(value, (dict, list)):
            return str(type(value).__name__)
        elif isinstance(value, str) and len(value) > 50:
            return value[:50] + "..."
        else:
            return value
    
    def _is_system_database(self, db_name: str) -> bool:
        """判断是否为系统数据库"""
        system_dbs = {"admin", "local", "config"}
        return db_name in system_dbs
    
    def _is_system_collection(self, collection_name: str) -> bool:
        """判断是否为系统集合"""
        return collection_name.startswith("system.")
    
    async def _ensure_instance_record(self, instance_name: str, instance_info: Dict[str, Any]) -> ObjectId:
        """确保实例记录存在"""
        existing = await self.metadata_manager.get_instance_by_name(instance_name, instance_info["name"])
        if existing:
            return existing["_id"]
        
        instance_id = await self.metadata_manager.save_instance(instance_name, instance_info)
        return instance_id
    
    async def incremental_scan(self, instance_name: str) -> Dict[str, Any]:
        """增量扫描指定实例"""
        logger.info("开始增量扫描", instance_name=instance_name)
        
        try:
            # 获取实例信息
            instance_info = self.connection_manager.get_instance_info(instance_name)
            if not instance_info:
                raise Exception("无法获取实例信息")
            
            instance_id = await self._ensure_instance_record(instance_name, instance_info)
            
            # 获取已扫描的数据库列表
            scanned_databases = await self.metadata_manager.get_databases_by_instance(instance_name, instance_name)
            scanned_db_names = {db["name"] for db in scanned_databases}
            
            # 获取当前实例的所有数据库
            connection = self.connection_manager.get_instance_connection(instance_name)
            if not connection or not connection.client:
                raise Exception("无法获取实例连接")
            
            databases = await connection.client.list_database_names()
            current_db_names = {db for db in databases if not self._is_system_database(db)}
            
            # 找出新增的数据库
            new_databases = current_db_names - scanned_db_names
            
            scan_result = {
                "instance_name": instance_name,
                "new_databases": list(new_databases),
                "databases_count": 0,
                "collections_count": 0,
                "fields_count": 0,
                "errors": []
            }
            
            # 扫描新增的数据库
            for db_name in new_databases:
                try:
                    db_result = await self.scan_database_structure(instance_name, instance_id, db_name)
                    scan_result["databases_count"] += 1
                    scan_result["collections_count"] += db_result["collections_count"]
                    scan_result["fields_count"] += db_result["fields_count"]
                    
                    if db_result["errors"]:
                        scan_result["errors"].extend(db_result["errors"])
                    
                    logger.info("扫描新数据库完成", database=db_name)
                except Exception as e:
                    error_msg = f"扫描数据库 {db_name} 失败: {str(e)}"
                    logger.error(error_msg, database=db_name)
                    scan_result["errors"].append(error_msg)
            
            logger.info(
                "增量扫描完成",
                instance_name=instance_name,
                databases=scan_result["databases_count"],
                collections=scan_result["collections_count"],
                fields=scan_result["fields_count"]
            )
            
            return scan_result
            
        except Exception as e:
            logger.error("增量扫描失败", instance_name=instance_name, error=str(e))
            return {
                "databases_count": 0,
                "collections_count": 0,
                "fields_count": 0,
                "errors": [str(e)]
            }
       