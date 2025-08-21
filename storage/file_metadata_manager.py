# -*- coding: utf-8 -*-
"""
基于文件的元数据管理器

提供基于JSON文件的元数据存储和管理功能，替代MongoDB存储
"""

import json
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
import aiofiles
import structlog
from dataclasses import dataclass, asdict
import uuid
import copy

logger = structlog.get_logger(__name__)


@dataclass
class InstanceMetadata:
    """实例元数据"""
    id: str
    instance_name: str
    instance_alias: Optional[str]
    connection_string: str
    description: str
    environment: str
    status: str
    created_at: str
    updated_at: str


@dataclass
class DatabaseMetadata:
    """数据库元数据"""
    id: str
    instance_id: str
    database_name: str
    collection_count: int
    estimated_size: int
    description: str
    created_at: str
    updated_at: str


@dataclass
class CollectionMetadata:
    """集合元数据"""
    id: str
    instance_id: str
    database_name: str
    collection_name: str
    document_count: int
    estimated_size: int
    has_index: bool
    field_count: int
    sample_document: Optional[Dict[str, Any]]
    created_at: str
    updated_at: str


@dataclass
class FieldMetadata:
    """字段元数据"""
    id: str
    instance_id: str
    database_name: str
    collection_name: str
    field_path: str
    field_type: str
    is_required: bool
    unique_values_count: int
    examples: List[str]
    business_meaning: Optional[str]
    confidence: float
    created_at: str
    updated_at: str


@dataclass
class QueryHistory:
    """查询历史"""
    id: str
    instance_name: str
    database_name: str
    collection_name: str
    query_type: str
    query_content: Dict[str, Any]
    result_count: int
    execution_time_ms: float
    user_description: str
    created_at: str


class FileMetadataManager:
    """基于文件的元数据管理器"""
    
    def __init__(self, base_path: str = "data/metadata"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        # 创建子目录
        (self.base_path / "instances").mkdir(exist_ok=True)
        (self.base_path / "databases").mkdir(exist_ok=True)
        (self.base_path / "collections").mkdir(exist_ok=True)
        (self.base_path / "fields").mkdir(exist_ok=True)
        (self.base_path / "queries").mkdir(exist_ok=True)
        
        # 内存缓存
        self.metadata_cache: Dict[str, Dict] = {}
        self.last_scan_time: Dict[str, datetime] = {}
        self._lock = asyncio.Lock()
        
        # 统计信息
        self._scan_stats = {
            'total_scans': 0,
            'incremental_scans': 0,
            'full_scans': 0,
            'cache_hits': 0,
            'cache_misses': 0
        }
    
    async def initialize(self) -> bool:
        """初始化元数据管理器"""
        try:
            # 创建全局配置文件
            config_file = self.base_path / "config.json"
            if not config_file.exists():
                config = {
                    "version": "1.0.0",
                    "created_at": datetime.now().isoformat(),
                    "storage_type": "file",
                    "compression_enabled": False
                }
                await self._write_json_file(config_file, config)
            
            logger.info("文件元数据管理器初始化完成", base_path=str(self.base_path))
            return True
        except Exception as e:
            logger.error("元数据管理器初始化失败", error=str(e))
            return False
    
    async def _write_json_file(self, file_path: Path, data: Any) -> None:
        """写入JSON文件"""
        async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2))
    
    async def _read_json_file(self, file_path: Path) -> Optional[Any]:
        """读取JSON文件"""
        try:
            if not file_path.exists():
                return None
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content)
        except Exception as e:
            logger.error(f"读取文件失败: {file_path}", error=str(e))
            return None
    
    def _generate_id(self) -> str:
        """生成唯一ID"""
        return str(uuid.uuid4())
    
    # ==================== 实例管理 ====================
    
    async def save_instance(self, target_instance_name: str, instance_config: Dict[str, Any]) -> str:
        """保存实例配置"""
        instance_id = self._generate_id()
        
        instance_metadata = InstanceMetadata(
            id=instance_id,
            instance_name=instance_config.get("name", target_instance_name),
            instance_alias=instance_config.get("alias"),
            connection_string=instance_config.get("connection_string", ""),
            description=instance_config.get("description", ""),
            environment=instance_config.get("environment", "dev"),
            status=instance_config.get("status", "active"),
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        
        # 保存到文件
        instance_file = self.base_path / "instances" / f"{target_instance_name}.json"
        await self._write_json_file(instance_file, asdict(instance_metadata))
        
        logger.info("实例配置已保存", instance_name=target_instance_name)
        return instance_id
    
    async def get_instance_by_name(self, target_instance_name: str, instance_name: str) -> Optional[Dict[str, Any]]:
        """根据名称获取实例信息"""
        instance_file = self.base_path / "instances" / f"{instance_name}.json"
        data = await self._read_json_file(instance_file)
        
        if data and data.get("instance_name") == instance_name:
            return data
        
        # 如果按实例名找不到，搜索所有实例文件
        instances_dir = self.base_path / "instances"
        for file_path in instances_dir.glob("*.json"):
            data = await self._read_json_file(file_path)
            if data and data.get("instance_name") == instance_name:
                return data
        
        return None
    
    async def get_all_instances(self, target_instance_name: str, environment: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取所有实例"""
        instances = []
        instances_dir = self.base_path / "instances"
        
        for file_path in instances_dir.glob("*.json"):
            data = await self._read_json_file(file_path)
            if data:
                if environment is None or data.get("environment") == environment:
                    instances.append(data)
        
        return instances
    
    # ==================== 数据库管理 ====================
    
    async def save_database(self, target_instance_name: str, instance_id: str, db_info: Dict[str, Any]) -> str:
        """保存数据库信息"""
        db_id = self._generate_id()
        
        database_metadata = DatabaseMetadata(
            id=db_id,
            instance_id=instance_id,
            database_name=db_info.get("name", ""),
            collection_count=db_info.get("collection_count", 0),
            estimated_size=db_info.get("size_bytes", 0),
            description=db_info.get("description", ""),
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        
        # 保存到文件
        db_file = self.base_path / "databases" / f"{target_instance_name}_{db_info['name']}.json"
        await self._write_json_file(db_file, asdict(database_metadata))
        
        logger.info("数据库信息已保存", instance=target_instance_name, database=db_info['name'])
        return db_id
    
    async def get_databases_by_instance(self, target_instance_name: str, instance_id: str) -> List[Dict[str, Any]]:
        """获取实例的所有数据库"""
        databases = []
        databases_dir = self.base_path / "databases"
        
        for file_path in databases_dir.glob(f"{target_instance_name}_*.json"):
            data = await self._read_json_file(file_path)
            if data and data.get("instance_id") == instance_id:
                databases.append(data)
        
        return databases
    
    # ==================== 集合管理 ====================
    
    async def save_collection(self, target_instance_name: str, instance_id: str, collection_info: Dict[str, Any]) -> str:
        """保存集合信息"""
        collection_id = self._generate_id()
        
        collection_metadata = CollectionMetadata(
            id=collection_id,
            instance_id=instance_id,
            database_name=collection_info.get("database_name", ""),
            collection_name=collection_info.get("name", ""),
            document_count=collection_info.get("document_count", 0),
            estimated_size=collection_info.get("size_bytes", 0),
            has_index=collection_info.get("has_index", False),
            field_count=collection_info.get("field_count", 0),
            sample_document=collection_info.get("sample_document"),
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        
        # 保存到文件
        collection_file = self.base_path / "collections" / f"{target_instance_name}_{collection_info['database_name']}_{collection_info['name']}.json"
        await self._write_json_file(collection_file, asdict(collection_metadata))
        
        logger.info("集合信息已保存", 
                   instance=target_instance_name,
                   database=collection_info['database_name'],
                   collection=collection_info['name'])
        return collection_id
    
    async def get_collections_by_database(self, target_instance_name: str, instance_id: str, database_name: str) -> List[Dict[str, Any]]:
        """获取数据库的所有集合"""
        collections = []
        collections_dir = self.base_path / "collections"
        
        for file_path in collections_dir.glob(f"{target_instance_name}_{database_name}_*.json"):
            data = await self._read_json_file(file_path)
            if data and data.get("instance_id") == instance_id:
                collections.append(data)
        
        return collections
    
    # ==================== 字段管理 ====================
    
    async def save_field(self, target_instance_name: str, instance_id: str, field_info: Dict[str, Any]) -> str:
        """保存字段信息"""
        field_id = self._generate_id()
        
        field_metadata = FieldMetadata(
            id=field_id,
            instance_id=instance_id,
            database_name=field_info.get("database_name", ""),
            collection_name=field_info.get("collection_name", ""),
            field_path=field_info.get("field_path", ""),
            field_type=field_info.get("field_type", ""),
            is_required=field_info.get("is_required", False),
            unique_values_count=field_info.get("unique_values_count", 0),
            examples=field_info.get("examples", []),
            business_meaning=field_info.get("business_meaning"),
            confidence=field_info.get("confidence", 0.0),
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        
        # 保存到文件
        field_file = self.base_path / "fields" / f"{target_instance_name}_{field_info['database_name']}_{field_info['collection_name']}_{field_info['field_path']}.json"
        await self._write_json_file(field_file, asdict(field_metadata))
        
        logger.info("字段信息已保存",
                   instance=target_instance_name,
                   database=field_info['database_name'],
                   collection=field_info['collection_name'],
                   field=field_info['field_path'])
        return field_id
    
    async def get_fields_by_collection(self, target_instance_name: str, instance_id: str, 
                                     database_name: str, collection_name: str) -> List[Dict[str, Any]]:
        """获取集合的所有字段"""
        fields = []
        fields_dir = self.base_path / "fields"
        
        for file_path in fields_dir.glob(f"{target_instance_name}_{database_name}_{collection_name}_*.json"):
            data = await self._read_json_file(file_path)
            if data and data.get("instance_id") == instance_id:
                fields.append(data)
        
        return fields
    
    # ==================== 查询历史管理 ====================
    
    async def save_query_history(self, target_instance_name: str, query_info: Dict[str, Any]) -> str:
        """保存查询历史"""
        query_id = self._generate_id()
        
        query_history = QueryHistory(
            id=query_id,
            instance_name=target_instance_name,
            database_name=query_info.get("database_name", ""),
            collection_name=query_info.get("collection_name", ""),
            query_type=query_info.get("query_type", ""),
            query_content=query_info.get("query_content", {}),
            result_count=query_info.get("result_count", 0),
            execution_time_ms=query_info.get("execution_time_ms", 0.0),
            user_description=query_info.get("user_description", ""),
            created_at=datetime.now().isoformat()
        )
        
        # 按日期组织查询历史文件
        date_str = datetime.now().strftime("%Y-%m-%d")
        query_file = self.base_path / "queries" / f"{target_instance_name}_{date_str}.json"
        
        # 读取现有查询历史
        existing_queries = await self._read_json_file(query_file) or []
        existing_queries.append(asdict(query_history))
        
        # 保存更新后的查询历史
        await self._write_json_file(query_file, existing_queries)
        
        logger.info("查询历史已保存", instance=target_instance_name, query_id=query_id)
        return query_id
    
    async def get_query_history(self, target_instance_name: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取查询历史"""
        queries = []
        queries_dir = self.base_path / "queries"
        
        # 按日期倒序读取查询历史文件
        query_files = sorted(queries_dir.glob(f"{target_instance_name}_*.json"), reverse=True)
        
        for file_path in query_files:
            data = await self._read_json_file(file_path)
            if data:
                queries.extend(data)
                if len(queries) >= limit:
                    break
        
        return queries[:limit]
    
    # ==================== 扫描管理 ====================
    
    async def scan_instance_metadata(self, instance_name: str, full_scan: bool = False) -> bool:
        """扫描指定实例的元数据"""
        try:
            self.last_scan_time[instance_name] = datetime.now()
            
            if full_scan:
                self._scan_stats['full_scans'] += 1
            else:
                self._scan_stats['incremental_scans'] += 1
            
            self._scan_stats['total_scans'] += 1
            
            logger.info(f"实例 {instance_name} 元数据扫描完成", full_scan=full_scan)
            return True
            
        except Exception as e:
            logger.error(f"扫描实例 {instance_name} 元数据失败", error=str(e))
            return False
    
    async def get_scan_stats(self) -> Dict[str, Any]:
        """获取扫描统计信息"""
        return copy.deepcopy(self._scan_stats)
    
    async def init_instance_metadata(self, instance_name: str) -> bool:
        """初始化实例元数据"""
        try:
            # 为基于文件的存储，这里主要是确保目录结构存在
            instance_dir = self.base_path / "instances"
            instance_dir.mkdir(exist_ok=True)
            
            logger.info(f"实例 {instance_name} 元数据初始化完成")
            return True
        except Exception as e:
            logger.error(f"初始化实例 {instance_name} 元数据失败", error=str(e))
            return False
    
    # ==================== 统计信息 ====================
    
    async def get_statistics(self) -> Dict[str, Any]:
        """获取存储统计信息"""
        try:
            stats = {
                "total_instances": len(list((self.base_path / "instances").glob("*.json"))),
                "total_databases": len(list((self.base_path / "databases").glob("*.json"))),
                "total_collections": len(list((self.base_path / "collections").glob("*.json"))),
                "total_fields": len(list((self.base_path / "fields").glob("*.json"))),
                "storage_path": str(self.base_path),
                "scan_stats": self._scan_stats.copy()
            }
            return stats
        except Exception as e:
            logger.error("获取统计信息失败", error=str(e))
            return {}