#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP查询工具
提供MongoDB查询相关的MCP工具实现
"""

import logging
from typing import Dict, Any, List, Optional
from pymongo.errors import PyMongoError

from database.connection_manager import ConnectionManager
from database.query_engine import QueryEngine
from database.metadata_manager import MetadataManager

logger = logging.getLogger(__name__)


class QueryTools:
    """
    查询工具类
    提供MCP服务器使用的查询相关工具
    """
    
    def __init__(self, connection_manager: ConnectionManager, 
                 query_engine: QueryEngine, 
                 metadata_manager: MetadataManager):
        """
        初始化查询工具
        
        Args:
            connection_manager: 连接管理器
            query_engine: 查询引擎
            metadata_manager: 元数据管理器
        """
        self.connection_manager = connection_manager
        self.query_engine = query_engine
        self.metadata_manager = metadata_manager
    
    async def execute_query(self, instance_id: str, database_name: str, 
                          collection_name: str, query: Dict[str, Any], 
                          limit: int = 100) -> Dict[str, Any]:
        """
        执行MongoDB查询
        
        Args:
            instance_id: 实例ID
            database_name: 数据库名称
            collection_name: 集合名称
            query: 查询条件
            limit: 结果限制
            
        Returns:
            Dict: 查询结果
        """
        try:
            result = await self.query_engine.execute_query(
                instance_id, database_name, collection_name, query, limit
            )
            return {
                'success': True,
                'data': result,
                'count': len(result) if isinstance(result, list) else 1
            }
        except Exception as e:
            logger.error(f"查询执行失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'data': []
            }
    
    async def get_collection_schema(self, instance_id: str, database_name: str, 
                                  collection_name: str) -> Dict[str, Any]:
        """
        获取集合架构信息
        
        Args:
            instance_id: 实例ID
            database_name: 数据库名称
            collection_name: 集合名称
            
        Returns:
            Dict: 架构信息
        """
        try:
            schema = await self.metadata_manager.get_collection_schema(
                instance_id, database_name, collection_name
            )
            return {
                'success': True,
                'schema': schema
            }
        except Exception as e:
            logger.error(f"获取架构失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'schema': {}
            }
    
    async def list_collections(self, instance_id: str, database_name: str) -> Dict[str, Any]:
        """
        列出数据库中的所有集合
        
        Args:
            instance_id: 实例ID
            database_name: 数据库名称
            
        Returns:
            Dict: 集合列表
        """
        try:
            connection = await self.connection_manager.get_instance_connection(instance_id)
            if not connection:
                raise Exception(f"无法连接到实例: {instance_id}")
            
            database = connection[database_name]
            collections = await database.list_collection_names()
            
            return {
                'success': True,
                'collections': collections,
                'count': len(collections)
            }
        except Exception as e:
            logger.error(f"列出集合失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'collections': []
            }
    
    async def get_indexes(self, instance_id: str, database_name: str, 
                         collection_name: str) -> Dict[str, Any]:
        """
        获取集合的索引信息
        
        Args:
            instance_id: 实例ID
            database_name: 数据库名称
            collection_name: 集合名称
            
        Returns:
            Dict: 索引信息
        """
        try:
            connection = await self.connection_manager.get_instance_connection(instance_id)
            if not connection:
                raise Exception(f"无法连接到实例: {instance_id}")
            
            database = connection[database_name]
            collection = database[collection_name]
            indexes = await collection.list_indexes().to_list(length=None)
            
            return {
                'success': True,
                'indexes': indexes,
                'count': len(indexes)
            }
        except Exception as e:
            logger.error(f"获取索引失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'indexes': []
            }
    
    async def analyze_performance(self, instance_id: str, database_name: str, 
                                collection_name: str, query: Dict[str, Any]) -> Dict[str, Any]:
        """
        分析查询性能
        
        Args:
            instance_id: 实例ID
            database_name: 数据库名称
            collection_name: 集合名称
            query: 查询条件
            
        Returns:
            Dict: 性能分析结果
        """
        try:
            analysis = await self.query_engine.analyze_query_performance(
                instance_id, database_name, collection_name, query
            )
            return {
                'success': True,
                'analysis': analysis
            }
        except Exception as e:
            logger.error(f"性能分析失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'analysis': {}
            }
    
    async def suggest_indexes(self, instance_id: str, database_name: str, 
                            collection_name: str, queries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        建议索引优化
        
        Args:
            instance_id: 实例ID
            database_name: 数据库名称
            collection_name: 集合名称
            queries: 查询列表
            
        Returns:
            Dict: 索引建议
        """
        try:
            suggestions = await self.query_engine.suggest_indexes(
                instance_id, database_name, collection_name, queries
            )
            return {
                'success': True,
                'suggestions': suggestions
            }
        except Exception as e:
            logger.error(f"索引建议失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'suggestions': []
            }