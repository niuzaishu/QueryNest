# -*- coding: utf-8 -*-
"""
本地语义存储管理器

提供基于文件系统的语义数据存储和管理功能
"""

import json
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import aiofiles
import structlog
from dataclasses import dataclass, asdict


logger = structlog.get_logger(__name__)


@dataclass
class SemanticInfo:
    """语义信息数据类"""
    business_meaning: str
    confidence: float
    data_type: str
    examples: List[str]
    analysis_result: Dict[str, Any]
    created_at: str
    updated_at: str
    source: str  # manual, auto_analysis, confirmed


class LocalSemanticStorage:
    """本地语义存储管理器"""
    
    def __init__(self, base_path: str = "data/semantics"):
        self.base_path = Path(base_path)
        self.ensure_directory_structure()
        self._file_locks = {}  # 文件锁字典
        
    def ensure_directory_structure(self):
        """确保目录结构存在"""
        self.base_path.mkdir(parents=True, exist_ok=True)
        (self.base_path / "instances").mkdir(exist_ok=True)
        
        # 创建全局配置文件
        global_config_path = self.base_path / "global_config.json"
        if not global_config_path.exists():
            default_config = {
                "storage": {
                    "base_path": str(self.base_path),
                    "backup_enabled": True,
                    "backup_interval": 3600,
                    "max_backups": 10
                },
                "cache": {
                    "enabled": True,
                    "max_size": 1000,
                    "ttl": 300
                },
                "indexing": {
                    "auto_rebuild": True,
                    "rebuild_interval": 1800
                },
                "performance": {
                    "batch_size": 100,
                    "concurrent_operations": 10
                },
                "created_at": datetime.now().isoformat(),
                "version": "1.0.0"
            }
            
            with open(global_config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, ensure_ascii=False, indent=2)
    
    def _get_instance_path(self, instance_name: str) -> Path:
        """获取实例目录路径"""
        return self.base_path / "instances" / instance_name
    
    def _get_database_path(self, instance_name: str, database_name: str) -> Path:
        """获取数据库目录路径"""
        return self._get_instance_path(instance_name) / "databases" / database_name
    
    def _get_collection_path(self, instance_name: str, database_name: str, collection_name: str) -> Path:
        """获取集合目录路径"""
        return self._get_database_path(instance_name, database_name) / "collections" / collection_name
    
    def _get_fields_file_path(self, instance_name: str, database_name: str, collection_name: str) -> Path:
        """获取字段语义文件路径"""
        return self._get_collection_path(instance_name, database_name, collection_name) / "fields.json"
    
    async def _atomic_write(self, file_path: Path, data: Dict[str, Any]) -> bool:
        """原子性写入文件"""
        temp_path = file_path.with_suffix('.tmp')
        try:
            # 确保目录存在
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            async with aiofiles.open(temp_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2))
            
            # 原子性重命名
            temp_path.replace(file_path)
            return True
        except Exception as e:
            logger.error("原子性写入失败", file_path=str(file_path), error=str(e))
            if temp_path.exists():
                temp_path.unlink()
            return False
    
    async def _read_json_file(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """读取JSON文件"""
        try:
            if not file_path.exists():
                return None
                
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content)
        except Exception as e:
            logger.error("读取JSON文件失败", file_path=str(file_path), error=str(e))
            return None
    
    async def save_field_semantics(self, instance_name: str, database_name: str, 
                                 collection_name: str, field_path: str, 
                                 business_meaning: str, confidence: float = 1.0,
                                 data_type: str = "unknown", examples: List[str] = None,
                                 analysis_result: Dict[str, Any] = None,
                                 source: str = "manual") -> bool:
        """保存字段语义信息"""
        try:
            fields_file_path = self._get_fields_file_path(instance_name, database_name, collection_name)
            
            # 读取现有数据
            fields_data = await self._read_json_file(fields_file_path) or {
                "collection_name": collection_name,
                "last_updated": datetime.now().isoformat(),
                "fields": {}
            }
            
            # 创建语义信息
            semantic_info = {
                "business_meaning": business_meaning,
                "confidence": confidence,
                "data_type": data_type,
                "examples": examples or [],
                "analysis_result": analysis_result or {},
                "created_at": fields_data["fields"].get(field_path, {}).get("created_at", datetime.now().isoformat()),
                "updated_at": datetime.now().isoformat(),
                "source": source
            }
            
            # 更新字段信息
            fields_data["fields"][field_path] = semantic_info
            fields_data["last_updated"] = datetime.now().isoformat()
            
            # 原子性保存
            success = await self._atomic_write(fields_file_path, fields_data)
            
            if success:
                logger.info(
                    "字段语义保存成功",
                    instance=instance_name,
                    database=database_name,
                    collection=collection_name,
                    field=field_path
                )
                
                # 更新索引
                await self._update_semantic_index(instance_name, database_name, collection_name, field_path, business_meaning)
            
            return success
            
        except Exception as e:
            logger.error(
                "保存字段语义失败",
                instance=instance_name,
                database=database_name,
                collection=collection_name,
                field=field_path,
                error=str(e)
            )
            return False
    
    async def get_field_semantics(self, instance_name: str, database_name: str,
                                collection_name: str, field_path: str) -> Optional[Dict[str, Any]]:
        """获取字段语义信息"""
        try:
            fields_file_path = self._get_fields_file_path(instance_name, database_name, collection_name)
            fields_data = await self._read_json_file(fields_file_path)
            
            if fields_data and "fields" in fields_data:
                return fields_data["fields"].get(field_path)
            
            return None
            
        except Exception as e:
            logger.error(
                "获取字段语义失败",
                instance=instance_name,
                database=database_name,
                collection=collection_name,
                field=field_path,
                error=str(e)
            )
            return None
    
    async def get_collection_semantics(self, instance_name: str, database_name: str, 
                                     collection_name: str) -> Optional[Dict[str, Any]]:
        """获取集合的所有字段语义"""
        try:
            fields_file_path = self._get_fields_file_path(instance_name, database_name, collection_name)
            return await self._read_json_file(fields_file_path)
            
        except Exception as e:
            logger.error(
                "获取集合语义失败",
                instance=instance_name,
                database=database_name,
                collection=collection_name,
                error=str(e)
            )
            return None
    
    async def search_semantics(self, instance_name: str, search_term: str) -> List[Dict[str, Any]]:
        """搜索语义信息"""
        results = []
        
        try:
            instance_path = self._get_instance_path(instance_name)
            if not instance_path.exists():
                return results
            
            # 遍历所有数据库和集合
            databases_path = instance_path / "databases"
            if not databases_path.exists():
                return results
            
            for db_path in databases_path.iterdir():
                if not db_path.is_dir():
                    continue
                    
                database_name = db_path.name
                collections_path = db_path / "collections"
                
                if not collections_path.exists():
                    continue
                
                for collection_path in collections_path.iterdir():
                    if not collection_path.is_dir():
                        continue
                        
                    collection_name = collection_path.name
                    fields_file = collection_path / "fields.json"
                    
                    fields_data = await self._read_json_file(fields_file)
                    if not fields_data or "fields" not in fields_data:
                        continue
                    
                    # 搜索匹配的字段
                    for field_path, field_info in fields_data["fields"].items():
                        business_meaning = field_info.get("business_meaning", "")
                        
                        if search_term.lower() in business_meaning.lower() or search_term.lower() in field_path.lower():
                            results.append({
                                "instance_name": instance_name,
                                "database_name": database_name,
                                "collection_name": collection_name,
                                "field_path": field_path,
                                "business_meaning": business_meaning,
                                "confidence": field_info.get("confidence", 0.0),
                                "semantic_source": "local_file",
                                "updated_at": field_info.get("updated_at")
                            })
            
            # 按置信度排序
            results.sort(key=lambda x: x["confidence"], reverse=True)
            
            logger.info(
                "语义搜索完成",
                instance=instance_name,
                search_term=search_term,
                results_count=len(results)
            )
            
        except Exception as e:
            logger.error(
                "搜索语义失败",
                instance=instance_name,
                search_term=search_term,
                error=str(e)
            )
        
        return results
    
    async def batch_save_collection_semantics(self, instance_name: str, database_name: str,
                                            collection_name: str, fields_data: Dict[str, Any]) -> bool:
        """批量保存集合的字段语义"""
        try:
            fields_file_path = self._get_fields_file_path(instance_name, database_name, collection_name)
            
            # 准备完整的字段数据
            complete_data = {
                "collection_name": collection_name,
                "last_updated": datetime.now().isoformat(),
                "fields": fields_data
            }
            
            success = await self._atomic_write(fields_file_path, complete_data)
            
            if success:
                logger.info(
                    "批量保存集合语义成功",
                    instance=instance_name,
                    database=database_name,
                    collection=collection_name,
                    fields_count=len(fields_data)
                )
                
                # 批量更新索引
                for field_path, field_info in fields_data.items():
                    business_meaning = field_info.get("business_meaning", "")
                    if business_meaning:
                        await self._update_semantic_index(instance_name, database_name, collection_name, field_path, business_meaning)
            
            return success
            
        except Exception as e:
            logger.error(
                "批量保存集合语义失败",
                instance=instance_name,
                database=database_name,
                collection=collection_name,
                error=str(e)
            )
            return False
    
    async def _update_semantic_index(self, instance_name: str, database_name: str, 
                                   collection_name: str, field_path: str, business_meaning: str):
        """更新语义索引"""
        try:
            index_file_path = self.base_path / "semantic_index.json"
            
            # 读取现有索引
            index_data = await self._read_json_file(index_file_path) or {
                "semantic_index": {},
                "field_index": {},
                "last_updated": datetime.now().isoformat()
            }
            
            # 更新语义索引
            if business_meaning not in index_data["semantic_index"]:
                index_data["semantic_index"][business_meaning] = []
            
            # 检查是否已存在相同条目
            existing_entry = None
            for entry in index_data["semantic_index"][business_meaning]:
                if (entry["instance"] == instance_name and 
                    entry["database"] == database_name and 
                    entry["collection"] == collection_name and 
                    entry["field"] == field_path):
                    existing_entry = entry
                    break
            
            if not existing_entry:
                index_data["semantic_index"][business_meaning].append({
                    "instance": instance_name,
                    "database": database_name,
                    "collection": collection_name,
                    "field": field_path,
                    "meaning": business_meaning
                })
            
            # 更新字段索引
            if field_path not in index_data["field_index"]:
                index_data["field_index"][field_path] = []
            
            # 检查字段索引中是否已存在
            field_existing = None
            for entry in index_data["field_index"][field_path]:
                if (entry["instance"] == instance_name and 
                    entry["database"] == database_name and 
                    entry["collection"] == collection_name):
                    field_existing = entry
                    break
            
            if field_existing:
                field_existing["meaning"] = business_meaning
            else:
                index_data["field_index"][field_path].append({
                    "instance": instance_name,
                    "database": database_name,
                    "collection": collection_name,
                    "meaning": business_meaning
                })
            
            index_data["last_updated"] = datetime.now().isoformat()
            
            # 保存索引
            await self._atomic_write(index_file_path, index_data)
            
        except Exception as e:
            logger.error("更新语义索引失败", error=str(e))
    
    async def get_instance_statistics(self, instance_name: str) -> Dict[str, Any]:
        """获取实例统计信息"""
        stats = {
            "total_databases": 0,
            "total_collections": 0,
            "total_fields": 0,
            "semantic_coverage": 0.0,
            "last_updated": None
        }
        
        try:
            instance_path = self._get_instance_path(instance_name)
            if not instance_path.exists():
                return stats
            
            databases_path = instance_path / "databases"
            if not databases_path.exists():
                return stats
            
            total_fields = 0
            semantic_fields = 0
            latest_update = None
            
            for db_path in databases_path.iterdir():
                if not db_path.is_dir():
                    continue
                    
                stats["total_databases"] += 1
                collections_path = db_path / "collections"
                
                if not collections_path.exists():
                    continue
                
                for collection_path in collections_path.iterdir():
                    if not collection_path.is_dir():
                        continue
                        
                    stats["total_collections"] += 1
                    fields_file = collection_path / "fields.json"
                    
                    fields_data = await self._read_json_file(fields_file)
                    if fields_data and "fields" in fields_data:
                        collection_fields = len(fields_data["fields"])
                        total_fields += collection_fields
                        
                        # 统计有语义的字段
                        for field_info in fields_data["fields"].values():
                            if field_info.get("business_meaning"):
                                semantic_fields += 1
                        
                        # 更新最新时间
                        last_updated = fields_data.get("last_updated")
                        if last_updated and (not latest_update or last_updated > latest_update):
                            latest_update = last_updated
            
            stats["total_fields"] = total_fields
            stats["semantic_coverage"] = semantic_fields / total_fields if total_fields > 0 else 0.0
            stats["last_updated"] = latest_update
            
        except Exception as e:
            logger.error("获取实例统计失败", instance=instance_name, error=str(e))
        
        return stats
    
    async def save_instance_metadata(self, instance_name: str, metadata: Dict[str, Any]) -> bool:
        """保存实例元数据"""
        try:
            instance_path = self._get_instance_path(instance_name)
            instance_path.mkdir(parents=True, exist_ok=True)
            
            metadata_file = instance_path / "metadata.json"
            
            # 添加统计信息
            stats = await self.get_instance_statistics(instance_name)
            metadata["statistics"] = stats
            metadata["last_updated"] = datetime.now().isoformat()
            
            return await self._atomic_write(metadata_file, metadata)
            
        except Exception as e:
            logger.error("保存实例元数据失败", instance=instance_name, error=str(e))
            return False
    
    async def get_instance_metadata(self, instance_name: str) -> Optional[Dict[str, Any]]:
        """获取实例元数据"""
        try:
            instance_path = self._get_instance_path(instance_name)
            metadata_file = instance_path / "metadata.json"
            
            return await self._read_json_file(metadata_file)
            
        except Exception as e:
            logger.error("获取实例元数据失败", instance=instance_name, error=str(e))
            return None