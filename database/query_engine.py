# -*- coding: utf-8 -*-
"""查询引擎"""

import asyncio
from typing import Dict, List, Optional, Any, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import PyMongoError
import structlog
from datetime import datetime
import re
from bson import ObjectId

from database.connection_manager import ConnectionManager
from database.metadata_manager import MetadataManager
from config import QueryNestConfig


logger = structlog.get_logger(__name__)


class QuerySafetyValidator:
    """查询安全验证器"""
    
    # 禁止的操作关键词
    FORBIDDEN_OPERATIONS = [
        'insert', 'update', 'delete', 'drop', 'create', 'remove',
        'save', 'replace', 'modify', 'rename', 'index'
    ]
    
    # 禁止的MongoDB方法
    FORBIDDEN_METHODS = [
        'insertOne', 'insertMany', 'updateOne', 'updateMany',
        'deleteOne', 'deleteMany', 'replaceOne', 'drop',
        'createIndex', 'dropIndex', 'renameCollection'
    ]
    
    @classmethod
    def validate_query(cls, query: Dict[str, Any]) -> Tuple[bool, str]:
        """验证查询安全性"""
        try:
            # 检查查询字符串中是否包含禁止的操作
            query_str = str(query).lower()
            
            for forbidden in cls.FORBIDDEN_OPERATIONS:
                if forbidden in query_str:
                    return False, f"查询包含禁止的操作: {forbidden}"
            
            # 检查是否包含禁止的方法调用
            for method in cls.FORBIDDEN_METHODS:
                if method.lower() in query_str:
                    return False, f"查询包含禁止的方法: {method}"
            
            # 检查是否包含$eval或JavaScript代码执行
            if '$eval' in query_str or '$where' in query_str:
                return False, "查询包含代码执行操作"
            
            # 检查是否包含管理命令
            admin_commands = ['shutdown', 'fsync', 'compact', 'reindex']
            for cmd in admin_commands:
                if cmd in query_str:
                    return False, f"查询包含管理命令: {cmd}"
            
            return True, "查询安全"
            
        except Exception as e:
            return False, f"查询验证异常: {str(e)}"
    
    @classmethod
    def validate_aggregation_pipeline(cls, pipeline: List[Dict[str, Any]]) -> Tuple[bool, str]:
        """验证聚合管道安全性"""
        try:
            for stage in pipeline:
                # 检查是否包含$out或$merge阶段（会写入数据）
                if '$out' in stage or '$merge' in stage:
                    return False, "聚合管道包含写入操作"
                
                # 检查$lookup阶段的安全性
                if '$lookup' in stage:
                    lookup = stage['$lookup']
                    if isinstance(lookup, dict) and 'pipeline' in lookup:
                        # 递归检查子管道
                        is_safe, msg = cls.validate_aggregation_pipeline(lookup['pipeline'])
                        if not is_safe:
                            return False, f"$lookup子管道不安全: {msg}"
            
            return True, "聚合管道安全"
            
        except Exception as e:
            return False, f"聚合管道验证异常: {str(e)}"


class QueryEngine:
    """查询引擎"""
    
    def __init__(self, connection_manager: ConnectionManager, 
                 metadata_manager: MetadataManager, config: QueryNestConfig):
        self.connection_manager = connection_manager
        self.metadata_manager = metadata_manager
        self.config = config
        self.safety_validator = QuerySafetyValidator()
    
    async def execute_find_query(self, instance_name: str, database_name: str, 
                               collection_name: str, query: Dict[str, Any],
                               projection: Optional[Dict[str, Any]] = None,
                               limit: int = None, sort: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """执行查找查询"""
        try:
            # 安全验证
            if not await self.connection_manager.validate_query_permissions(instance_name, "find"):
                return {
                    "success": False,
                    "error": "权限验证失败",
                    "data": None
                }
            
            # 查询安全验证
            is_safe, safety_msg = self.safety_validator.validate_query(query)
            if not is_safe:
                logger.warning("不安全的查询被拒绝", instance=instance_name, reason=safety_msg)
                return {
                    "success": False,
                    "error": f"查询安全验证失败: {safety_msg}",
                    "data": None
                }
            
            # 获取数据库连接
            db = self.connection_manager.get_instance_database(instance_name, database_name)
            if db is None:
                return {
                    "success": False,
                    "error": "无法连接到指定数据库",
                    "data": None
                }
            
            collection = db[collection_name]
            
            # 应用限制
            if limit is None:
                limit = self.config.security.max_result_size
            else:
                limit = min(limit, self.config.security.max_result_size)
            
            # 构建查询
            cursor = collection.find(query, projection)
            
            if sort:
                cursor = cursor.sort(list(sort.items()))
            
            cursor = cursor.limit(limit)
            
            # 执行查询（带超时）
            start_time = datetime.now()
            documents = await asyncio.wait_for(
                cursor.to_list(length=None),
                timeout=self.config.security.query_timeout
            )
            execution_time = (datetime.now() - start_time).total_seconds()
            
            # 数据脱敏
            sanitized_documents = await self._sanitize_documents(documents)
            
            logger.info(
                "查询执行成功",
                instance=instance_name,
                database=database_name,
                collection=collection_name,
                result_count=len(documents),
                execution_time=execution_time
            )
            
            return {
                "success": True,
                "error": None,
                "data": {
                    "documents": sanitized_documents,
                    "count": len(documents),
                    "execution_time": execution_time,
                    "limited": len(documents) >= limit
                }
            }
            
        except asyncio.TimeoutError:
            logger.warning("查询超时", instance=instance_name, timeout=self.config.security.query_timeout)
            return {
                "success": False,
                "error": f"查询超时（{self.config.security.query_timeout}秒）",
                "data": None
            }
        except PyMongoError as e:
            logger.error("MongoDB查询错误", instance=instance_name, error=str(e))
            return {
                "success": False,
                "error": f"数据库查询错误: {str(e)}",
                "data": None
            }
        except Exception as e:
            logger.error("查询执行异常", instance=instance_name, error=str(e))
            return {
                "success": False,
                "error": f"查询执行异常: {str(e)}",
                "data": None
            }
    
    async def execute_aggregation(self, instance_name: str, database_name: str,
                                collection_name: str, pipeline: List[Dict[str, Any]]) -> Dict[str, Any]:
        """执行聚合查询"""
        try:
            # 权限验证
            if not await self.connection_manager.validate_query_permissions(instance_name, "aggregate"):
                return {
                    "success": False,
                    "error": "权限验证失败",
                    "data": None
                }
            
            # 聚合管道安全验证
            is_safe, safety_msg = self.safety_validator.validate_aggregation_pipeline(pipeline)
            if not is_safe:
                logger.warning("不安全的聚合管道被拒绝", instance=instance_name, reason=safety_msg)
                return {
                    "success": False,
                    "error": f"聚合管道安全验证失败: {safety_msg}",
                    "data": None
                }
            
            # 获取数据库连接
            db = self.connection_manager.get_instance_database(instance_name, database_name)
            if not db:
                return {
                    "success": False,
                    "error": "无法连接到指定数据库",
                    "data": None
                }
            
            collection = db[collection_name]
            
            # 添加限制阶段
            pipeline_with_limit = pipeline.copy()
            pipeline_with_limit.append({"$limit": self.config.security.max_result_size})
            
            # 执行聚合（带超时）
            start_time = datetime.now()
            cursor = collection.aggregate(pipeline_with_limit)
            documents = await asyncio.wait_for(
                cursor.to_list(length=None),
                timeout=self.config.security.query_timeout
            )
            execution_time = (datetime.now() - start_time).total_seconds()
            
            # 数据脱敏
            sanitized_documents = await self._sanitize_documents(documents)
            
            logger.info(
                "聚合查询执行成功",
                instance=instance_name,
                database=database_name,
                collection=collection_name,
                result_count=len(documents),
                execution_time=execution_time
            )
            
            return {
                "success": True,
                "error": None,
                "data": {
                    "documents": sanitized_documents,
                    "count": len(documents),
                    "execution_time": execution_time,
                    "limited": len(documents) >= self.config.security.max_result_size
                }
            }
            
        except asyncio.TimeoutError:
            logger.warning("聚合查询超时", instance=instance_name)
            return {
                "success": False,
                "error": f"聚合查询超时（{self.config.security.query_timeout}秒）",
                "data": None
            }
        except PyMongoError as e:
            logger.error("MongoDB聚合查询错误", instance=instance_name, error=str(e))
            return {
                "success": False,
                "error": f"聚合查询错误: {str(e)}",
                "data": None
            }
        except Exception as e:
            logger.error("聚合查询执行异常", instance=instance_name, error=str(e))
            return {
                "success": False,
                "error": f"聚合查询执行异常: {str(e)}",
                "data": None
            }
    
    async def count_documents(self, instance_name: str, database_name: str,
                            collection_name: str, query: Dict[str, Any]) -> Dict[str, Any]:
        """统计文档数量"""
        try:
            # 权限验证
            if not await self.connection_manager.validate_query_permissions(instance_name, "count"):
                return {
                    "success": False,
                    "error": "权限验证失败",
                    "data": None
                }
            
            # 查询安全验证
            is_safe, safety_msg = self.safety_validator.validate_query(query)
            if not is_safe:
                return {
                    "success": False,
                    "error": f"查询安全验证失败: {safety_msg}",
                    "data": None
                }
            
            # 获取数据库连接
            db = self.connection_manager.get_instance_database(instance_name, database_name)
            if not db:
                return {
                    "success": False,
                    "error": "无法连接到指定数据库",
                    "data": None
                }
            
            collection = db[collection_name]
            
            # 执行计数（带超时）
            start_time = datetime.now()
            count = await asyncio.wait_for(
                collection.count_documents(query),
                timeout=self.config.security.query_timeout
            )
            execution_time = (datetime.now() - start_time).total_seconds()
            
            logger.info(
                "文档计数成功",
                instance=instance_name,
                database=database_name,
                collection=collection_name,
                count=count,
                execution_time=execution_time
            )
            
            return {
                "success": True,
                "error": None,
                "data": {
                    "count": count,
                    "execution_time": execution_time
                }
            }
            
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"计数操作超时（{self.config.security.query_timeout}秒）",
                "data": None
            }
        except PyMongoError as e:
            logger.error("MongoDB计数错误", instance=instance_name, error=str(e))
            return {
                "success": False,
                "error": f"计数操作错误: {str(e)}",
                "data": None
            }
        except Exception as e:
            logger.error("计数操作异常", instance=instance_name, error=str(e))
            return {
                "success": False,
                "error": f"计数操作异常: {str(e)}",
                "data": None
            }
    
    async def get_distinct_values(self, instance_name: str, database_name: str,
                                collection_name: str, field: str, 
                                query: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """获取字段的不重复值"""
        try:
            # 权限验证
            if not await self.connection_manager.validate_query_permissions(instance_name, "distinct"):
                return {
                    "success": False,
                    "error": "权限验证失败",
                    "data": None
                }
            
            if query:
                # 查询安全验证
                is_safe, safety_msg = self.safety_validator.validate_query(query)
                if not is_safe:
                    return {
                        "success": False,
                        "error": f"查询安全验证失败: {safety_msg}",
                        "data": None
                    }
            
            # 获取数据库连接
            db = self.connection_manager.get_instance_database(instance_name, database_name)
            if not db:
                return {
                    "success": False,
                    "error": "无法连接到指定数据库",
                    "data": None
                }
            
            collection = db[collection_name]
            
            # 执行distinct查询（带超时）
            start_time = datetime.now()
            distinct_values = await asyncio.wait_for(
                collection.distinct(field, query or {}),
                timeout=self.config.security.query_timeout
            )
            execution_time = (datetime.now() - start_time).total_seconds()
            
            # 限制返回数量
            if len(distinct_values) > self.config.security.max_result_size:
                distinct_values = distinct_values[:self.config.security.max_result_size]
                limited = True
            else:
                limited = False
            
            logger.info(
                "distinct查询成功",
                instance=instance_name,
                database=database_name,
                collection=collection_name,
                field=field,
                distinct_count=len(distinct_values),
                execution_time=execution_time
            )
            
            return {
                "success": True,
                "error": None,
                "data": {
                    "distinct_values": distinct_values,
                    "count": len(distinct_values),
                    "execution_time": execution_time,
                    "limited": limited
                }
            }
            
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"distinct查询超时（{self.config.security.query_timeout}秒）",
                "data": None
            }
        except PyMongoError as e:
            logger.error("MongoDB distinct查询错误", instance=instance_name, error=str(e))
            return {
                "success": False,
                "error": f"distinct查询错误: {str(e)}",
                "data": None
            }
        except Exception as e:
            logger.error("distinct查询异常", instance=instance_name, error=str(e))
            return {
                "success": False,
                "error": f"distinct查询异常: {str(e)}",
                "data": None
            }
    
    async def _sanitize_documents(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """数据脱敏处理"""
        if not documents:
            return documents
        
        sanitized = []
        for doc in documents:
            sanitized_doc = await self._sanitize_document(doc)
            sanitized.append(sanitized_doc)
        
        return sanitized
    
    async def _sanitize_document(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """单个文档脱敏处理"""
        if not isinstance(doc, dict):
            return doc
        
        sanitized = {}
        for key, value in doc.items():
            # 检查是否为敏感字段
            if self._is_sensitive_field(key):
                sanitized[key] = "***"
            elif isinstance(value, dict):
                sanitized[key] = await self._sanitize_document(value)
            elif isinstance(value, list):
                sanitized[key] = [await self._sanitize_document(item) if isinstance(item, dict) else item for item in value]
            else:
                sanitized[key] = value
        
        return sanitized
    
    def _is_sensitive_field(self, field_name: str) -> bool:
        """检查是否为敏感字段"""
        field_lower = field_name.lower()
        for sensitive_keyword in self.config.security.sensitive_fields:
            if sensitive_keyword.lower() in field_lower:
                return True
        return False
    
    async def explain_query(self, instance_name: str, database_name: str,
                          collection_name: str, query: Dict[str, Any]) -> Dict[str, Any]:
        """解释查询执行计划"""
        try:
            # 权限验证
            if not await self.connection_manager.validate_query_permissions(instance_name, "find"):
                return {
                    "success": False,
                    "error": "权限验证失败",
                    "data": None
                }
            
            # 查询安全验证
            is_safe, safety_msg = self.safety_validator.validate_query(query)
            if not is_safe:
                return {
                    "success": False,
                    "error": f"查询安全验证失败: {safety_msg}",
                    "data": None
                }
            
            # 获取数据库连接
            db = self.connection_manager.get_instance_database(instance_name, database_name)
            if not db:
                return {
                    "success": False,
                    "error": "无法连接到指定数据库",
                    "data": None
                }
            
            collection = db[collection_name]
            
            # 获取执行计划
            explain_result = await collection.find(query).explain()
            
            return {
                "success": True,
                "error": None,
                "data": explain_result
            }
            
        except Exception as e:
            logger.error("查询解释异常", instance=instance_name, error=str(e))
            return {
                "success": False,
                "error": f"查询解释异常: {str(e)}",
                "data": None
            }