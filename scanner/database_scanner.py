#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库扫描器
用于扫描MongoDB实例、数据库和集合的结构信息
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Set
from datetime import datetime
from bson import ObjectId
from pymongo.errors import PyMongoError

from database.connection_manager import ConnectionManager
from database.metadata_manager import MetadataManager
from config import ScannerConfig

logger = logging.getLogger(__name__)


class DatabaseScanner:
    """
    数据库扫描器
    负责扫描MongoDB实例的结构信息，包括数据库、集合和字段
    """
    
    def __init__(self, connection_manager: ConnectionManager, 
                 metadata_manager: MetadataManager, 
                 config: ScannerConfig):
        """
        初始化数据库扫描器
        
        Args:
            connection_manager: 连接管理器
            metadata_manager: 元数据管理器
            config: 扫描器配置
        """
        self.connection_manager = connection_manager
        self.metadata_manager = metadata_manager
        self.config = config
        self.scan_progress = {}
        
        # 系统数据库，通常不需要扫描
        self.system_databases = {'admin', 'config', 'local'}
    
    async def scan_instance(self, instance_id: str) -> bool:
        """
        扫描指定实例的所有数据库
        
        Args:
            instance_id: 实例ID
            
        Returns:
            bool: 扫描是否成功
        """
        try:
            logger.info(f"开始扫描实例: {instance_id}")
            
            # 获取实例连接
            instance_conn = self.connection_manager.get_instance_connection(instance_id)
            if not instance_conn:
                logger.error(f"无法连接到实例: {instance_id}")
                return False
            
            # 获取数据库列表
            database_names = await instance_conn.client.list_database_names()
            
            # 过滤系统数据库
            user_databases = [db for db in database_names if db not in self.system_databases]
            
            logger.info(f"实例 {instance_id} 包含 {len(user_databases)} 个用户数据库")
            
            # 扫描每个数据库
            success_count = 0
            for db_name in user_databases:
                try:
                    if await self._scan_database(instance_id, db_name):
                        success_count += 1
                except Exception as e:
                    logger.error(f"扫描数据库 {db_name} 失败: {e}")
            
            logger.info(f"实例 {instance_id} 扫描完成，成功扫描 {success_count}/{len(user_databases)} 个数据库")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"扫描实例 {instance_id} 失败: {e}")
            return False
    
    async def _scan_database(self, instance_id: str, database_name: str) -> bool:
        """
        扫描指定数据库的所有集合
        
        Args:
            instance_id: 实例ID
            database_name: 数据库名称
            
        Returns:
            bool: 扫描是否成功
        """
        try:
            logger.info(f"扫描数据库: {instance_id}.{database_name}")
            
            # 获取数据库连接
            instance_conn = self.connection_manager.get_instance_connection(instance_id)
            database = instance_conn.get_database(database_name)
            
            # 获取集合列表
            collection_names = await database.list_collection_names()
            
            logger.info(f"数据库 {database_name} 包含 {len(collection_names)} 个集合")
            
            # 保存数据库信息
            database_info = {
                'instance_id': instance_id,
                'name': database_name,
                'collection_count': len(collection_names),
                'collections': collection_names,
                'scanned_at': datetime.utcnow()
            }
            
            # 获取实例的 ObjectId
            instance_obj = await self.metadata_manager.get_instance_by_name(instance_id, instance_id)
            if not instance_obj:
                logger.error(f"无法找到实例 {instance_id}")
                return False
            instance_obj_id = instance_obj["_id"]
            
            # 保存数据库信息
            db_info = {
                "name": database_name,
                "description": f"扫描发现的数据库，包含 {len(collection_names)} 个集合"
            }
            await self.metadata_manager.save_database(instance_id, instance_obj_id, db_info)
            
            # 扫描每个集合
            success_count = 0
            for collection_name in collection_names:
                try:
                    if await self._scan_collection(instance_id, database_name, collection_name):
                        success_count += 1
                except Exception as e:
                    logger.error(f"扫描集合 {collection_name} 失败: {e}")
            
            logger.info(f"数据库 {database_name} 扫描完成，成功扫描 {success_count}/{len(collection_names)} 个集合")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"扫描数据库 {instance_id}.{database_name} 失败: {e}")
            return False
    
    async def _scan_collection(self, instance_id: str, database_name: str, collection_name: str) -> bool:
        """
        扫描指定集合的结构信息
        
        Args:
            instance_id: 实例ID
            database_name: 数据库名称
            collection_name: 集合名称
            
        Returns:
            bool: 扫描是否成功
        """
        try:
            logger.debug(f"扫描集合: {instance_id}.{database_name}.{collection_name}")
            
            # 获取集合连接
            instance_conn = self.connection_manager.get_instance_connection(instance_id)
            database = instance_conn.get_database(database_name)
            collection = database[collection_name]
            
            # 获取集合基本信息
            document_count = await collection.estimated_document_count()
            
            # 获取样本文档进行结构分析
            sample_size = min(self.config.max_sample_documents, document_count)
            
            if sample_size > 0:
                # 使用聚合管道随机采样
                pipeline = [{'$sample': {'size': sample_size}}]
                sample_docs = await collection.aggregate(pipeline).to_list(length=sample_size)
            else:
                sample_docs = []
            
            # 分析文档结构
            field_info = self._analyze_document_structure(sample_docs)
            
            # 保存集合信息
            collection_info = {
                'instance_id': instance_id,
                'database_name': database_name,
                'name': collection_name,
                'document_count': document_count,
                'sample_size': len(sample_docs),
                'field_count': len(field_info),
                'scanned_at': datetime.utcnow()
            }
            
            # 获取实例的 ObjectId
            instance_obj = await self.metadata_manager.get_instance_by_name(instance_id, instance_id)
            if not instance_obj:
                logger.error(f"无法找到实例 {instance_id}")
                return False
            instance_obj_id = instance_obj["_id"]
            
            # 保存集合信息
            collection_data = {
                "name": collection_name,
                "database": database_name,
                "description": f"扫描发现的集合，包含 {document_count} 个文档",
                "document_count": document_count
            }
            await self.metadata_manager.save_collection(instance_id, instance_obj_id, collection_data)
            
            # 保存字段信息
            for field_name, field_data in field_info.items():
                # 获取实例的 ObjectId
                instance_obj = await self.metadata_manager.get_instance_by_name(instance_id, instance_id)
                if not instance_obj:
                    logger.error(f"无法找到实例 {instance_id}")
                    continue
                instance_obj_id = instance_obj["_id"]
                
                # 生成字段语义信息
                semantics = None
                if self.config.semantic_analysis:
                    semantics = await self._generate_field_semantics(field_name, field_data)
                
                # 保存字段信息
                field_save_data = {
                    "database": database_name,
                    "collection": collection_name,
                    "path": field_name,
                    "type": field_data["type"],
                    "examples": list(field_data.get("examples", [])),
                    "is_indexed": field_data.get("is_indexed", False),
                    "is_required": field_data.get("is_required", False)
                }
                
                if semantics:
                    field_save_data["semantics"] = semantics
                await self.metadata_manager.save_field(instance_id, instance_obj_id, field_save_data)
            
            logger.debug(f"集合 {collection_name} 扫描完成，发现 {len(field_info)} 个字段")
            return True
            
        except Exception as e:
            logger.error(f"扫描集合 {instance_id}.{database_name}.{collection_name} 失败: {e}")
            return False
    
    def _analyze_document_structure(self, documents: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        分析文档结构，提取字段信息
        
        Args:
            documents: 文档列表
            
        Returns:
            Dict: 字段信息字典
        """
        field_info = {}
        total_docs = len(documents)
        
        if total_docs == 0:
            return field_info
        
        for doc in documents:
            # 提取所有字段（包括嵌套字段）
            flat_fields = self._extract_nested_fields(doc)
            
            for field_path, value in flat_fields.items():
                if field_path not in field_info:
                    field_info[field_path] = {
                        'type': self._get_field_type(value),
                        'frequency': 0,
                        'examples': set(),
                        'null_count': 0,
                        'unique_values': set()
                    }
                
                field_data = field_info[field_path]
                field_data['frequency'] += 1
                
                if value is None:
                    field_data['null_count'] += 1
                else:
                    # 添加示例值（限制数量）
                    if len(field_data['examples']) < 5:
                        if isinstance(value, (str, int, float, bool)):
                            field_data['examples'].add(str(value))
                    
                    # 记录唯一值（限制数量）
                    if len(field_data['unique_values']) < 100:
                        if isinstance(value, (str, int, float, bool)):
                            field_data['unique_values'].add(value)
        
        # 转换集合为列表，计算统计信息
        for field_path, field_data in field_info.items():
            field_data['examples'] = list(field_data['examples'])
            field_data['unique_values'] = list(field_data['unique_values'])
            field_data['coverage'] = field_data['frequency'] / total_docs
            field_data['null_rate'] = field_data['null_count'] / field_data['frequency'] if field_data['frequency'] > 0 else 0
            field_data['unique_count'] = len(field_data['unique_values'])
        
        return field_info
    
    def _extract_nested_fields(self, document: Dict[str, Any], prefix: str = '', max_depth: int = None) -> Dict[str, Any]:
        """
        提取嵌套字段，将嵌套结构展平
        
        Args:
            document: 文档
            prefix: 字段前缀
            max_depth: 最大深度
            
        Returns:
            Dict: 展平的字段字典
        """
        if max_depth is None:
            max_depth = self.config.field_analysis_depth
        
        fields = {}
        current_depth = len(prefix.split('.')) if prefix else 0
        
        for key, value in document.items():
            field_path = f"{prefix}.{key}" if prefix else key
            
            if isinstance(value, dict) and current_depth < max_depth:
                # 递归处理嵌套对象
                nested_fields = self._extract_nested_fields(value, field_path, max_depth)
                fields.update(nested_fields)
            else:
                # 添加当前字段
                fields[field_path] = value
        
        return fields
    
    def _get_field_type(self, value: Any) -> str:
        """
        获取字段类型
        
        Args:
            value: 字段值
            
        Returns:
            str: 字段类型
        """
        if value is None:
            return 'null'
        elif isinstance(value, bool):
            return 'bool'
        elif isinstance(value, int):
            return 'int'
        elif isinstance(value, float):
            return 'float'
        elif isinstance(value, str):
            return 'string'
        elif isinstance(value, list):
            return 'array'
        elif isinstance(value, dict):
            return 'object'
        elif isinstance(value, datetime):
            return 'date'
        elif isinstance(value, ObjectId):
            return 'objectid'
        else:
            return 'unknown'
    
    async def _generate_field_semantics(self, field_name: str, field_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成字段语义信息
        
        Args:
            field_name: 字段名称
            field_data: 字段数据
            
        Returns:
            Dict: 语义信息
        """
        semantics = {
            'category': 'unknown',
            'meaning': '',
            'confidence': 0.0
        }
        
        # 基于字段名推断语义
        name_meaning = self._infer_field_meaning_by_name(field_name)
        if name_meaning:
            semantics.update(name_meaning)
        
        # 基于示例值推断语义
        if field_data.get('examples'):
            example_meaning = self._infer_field_meaning_by_examples(field_data['examples'], field_data['type'])
            if example_meaning and example_meaning.get('confidence', 0) > semantics.get('confidence', 0):
                semantics.update(example_meaning)
        
        return semantics
    
    def _infer_field_meaning_by_name(self, field_name: str) -> Optional[Dict[str, Any]]:
        """
        基于字段名推断语义
        
        Args:
            field_name: 字段名称
            
        Returns:
            Dict: 语义信息
        """
        field_name_lower = field_name.lower()
        
        # 常见字段模式
        patterns = {
            'id': {'category': 'identifier', 'meaning': '标识符', 'confidence': 0.9},
            'name': {'category': 'personal', 'meaning': '姓名', 'confidence': 0.8},
            'email': {'category': 'contact', 'meaning': '电子邮箱', 'confidence': 0.9},
            'phone': {'category': 'contact', 'meaning': '电话号码', 'confidence': 0.9},
            'address': {'category': 'location', 'meaning': '地址', 'confidence': 0.8},
            'age': {'category': 'personal', 'meaning': '年龄', 'confidence': 0.8},
            'price': {'category': 'financial', 'meaning': '价格', 'confidence': 0.8},
            'amount': {'category': 'financial', 'meaning': '金额', 'confidence': 0.8},
            'date': {'category': 'temporal', 'meaning': '日期', 'confidence': 0.7},
            'time': {'category': 'temporal', 'meaning': '时间', 'confidence': 0.7},
            'status': {'category': 'state', 'meaning': '状态', 'confidence': 0.7},
            'type': {'category': 'classification', 'meaning': '类型', 'confidence': 0.7}
        }
        
        for pattern, meaning in patterns.items():
            if pattern in field_name_lower:
                return meaning
        
        return None
    
    def _infer_field_meaning_by_examples(self, examples: List[str], field_type: str) -> Optional[Dict[str, Any]]:
        """
        基于示例值推断语义
        
        Args:
            examples: 示例值列表
            field_type: 字段类型
            
        Returns:
            Dict: 语义信息
        """
        if not examples:
            return None
        
        import re
        
        # 邮箱模式
        email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
        if all(email_pattern.match(str(ex)) for ex in examples[:3]):
            return {'category': 'contact', 'meaning': '电子邮箱', 'confidence': 0.95}
        
        # 电话号码模式
        phone_pattern = re.compile(r'^[\d\s\-\+\(\)]{7,}$')
        if field_type == 'string' and all(phone_pattern.match(str(ex)) for ex in examples[:3]):
            return {'category': 'contact', 'meaning': '电话号码', 'confidence': 0.8}
        
        # URL模式
        url_pattern = re.compile(r'^https?://')
        if all(url_pattern.match(str(ex)) for ex in examples[:3]):
            return {'category': 'reference', 'meaning': 'URL链接', 'confidence': 0.9}
        
        return None
    
    async def scan_all_instances(self) -> Dict[str, bool]:
        """
        扫描所有配置的实例
        
        Returns:
            Dict: 实例扫描结果
        """
        results = {}
        instance_ids = await self.connection_manager.get_all_instance_ids()
        
        for instance_id in instance_ids:
            try:
                results[instance_id] = await self.scan_instance(instance_id)
            except Exception as e:
                logger.error(f"扫描实例 {instance_id} 失败: {e}")
                results[instance_id] = False
        
        return results
    
    async def get_scan_progress(self, instance_id: str) -> Dict[str, Any]:
        """
        获取扫描进度
        
        Args:
            instance_id: 实例ID
            
        Returns:
            Dict: 扫描进度信息
        """
        return self.scan_progress.get(instance_id, {
            'status': 'not_started',
            'progress': 0.0,
            'current_database': '',
            'current_collection': '',
            'start_time': None,
            'estimated_completion': None
        })