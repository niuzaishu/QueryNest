# -*- coding: utf-8 -*-
"""
增强版本地语义存储

基于SemanticStorageInterface的增强文件存储实现，
支持版本控制、冲突检测、批量操作等高级功能
"""

import os
import json
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Tuple
from datetime import datetime, timedelta
import structlog
import hashlib
import shutil
from concurrent.futures import ThreadPoolExecutor
import tempfile

from storage.semantic_storage_interface import (
    SemanticStorageInterface,
    SemanticField, 
    SemanticSearchQuery,
    SemanticConflictInfo
)
from storage.semantic_file_manager import SemanticFileManager

logger = structlog.get_logger(__name__)


class EnhancedLocalSemanticStorage(SemanticStorageInterface):
    """增强版本地语义存储"""
    
    def __init__(self, base_path: str = "data/semantics", 
                 enable_compression: bool = False,
                 enable_cache: bool = True,
                 cache_ttl: int = 3600,
                 cache_size: int = 1000,
                 enable_versioning: bool = True,
                 max_versions: int = 10):
        """
        初始化增强版本地语义存储
        
        Args:
            base_path: 基础存储路径
            enable_compression: 是否启用压缩
            enable_cache: 是否启用缓存
            cache_ttl: 缓存TTL（秒）
            cache_size: 缓存大小
            enable_versioning: 是否启用版本控制
            max_versions: 最大版本数
        """
        self.base_path = Path(base_path)
        self.enable_compression = enable_compression
        self.enable_versioning = enable_versioning
        self.max_versions = max_versions
        
        # 创建目录结构
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.versions_path = self.base_path / "versions"
        self.snapshots_path = self.base_path / "snapshots"
        self.conflicts_path = self.base_path / "conflicts"
        
        if enable_versioning:
            self.versions_path.mkdir(exist_ok=True)
        self.snapshots_path.mkdir(exist_ok=True)
        self.conflicts_path.mkdir(exist_ok=True)
        
        # 初始化文件管理器
        self.file_manager = SemanticFileManager(
            self, 
            enable_cache=enable_cache,
            cache_ttl=cache_ttl,
            cache_size=cache_size
        )
        
        # 线程池用于异步文件操作
        self.thread_pool = ThreadPoolExecutor(max_workers=4)
        
        logger.info("增强版本地语义存储初始化完成",
                   base_path=str(self.base_path),
                   enable_versioning=enable_versioning,
                   enable_cache=enable_cache)
    
    def _get_field_path(self, instance_name: str, database_name: str, 
                       collection_name: str, field_path: str) -> Path:
        """获取字段存储路径"""
        # 对字段路径进行安全化处理
        safe_field_path = field_path.replace('/', '_').replace('\\', '_')
        safe_field_path = safe_field_path.replace('..', '_')
        
        return (self.base_path / "instances" / instance_name / 
                "databases" / database_name / "collections" / 
                collection_name / f"{safe_field_path}.json")
    
    def _get_version_path(self, instance_name: str, database_name: str,
                         collection_name: str, field_path: str) -> Path:
        """获取版本存储路径"""
        safe_field_path = field_path.replace('/', '_').replace('\\', '_')
        safe_field_path = safe_field_path.replace('..', '_')
        
        return (self.versions_path / instance_name / database_name / 
                collection_name / safe_field_path)
    
    def _generate_version_id(self, semantic_field: SemanticField) -> str:
        """生成版本ID"""
        content = json.dumps(semantic_field.to_dict(), sort_keys=True)
        return hashlib.md5(content.encode()).hexdigest()[:12]
    
    async def save_field_semantic(self, instance_name: str, database_name: str,
                                collection_name: str, field_path: str,
                                semantic_field: SemanticField) -> bool:
        """保存字段语义信息"""
        try:
            file_path = self._get_field_path(instance_name, database_name, 
                                           collection_name, field_path)
            
            # 检查冲突
            conflicts = await self.detect_conflicts(
                instance_name, database_name, collection_name, 
                field_path, semantic_field
            )
            
            if conflicts:
                logger.warning("检测到语义冲突", conflicts=len(conflicts))
                # 记录冲突信息
                await self._record_conflicts(conflicts)
            
            # 保存版本历史（如果启用）
            if self.enable_versioning:
                await self._save_version(instance_name, database_name, 
                                       collection_name, field_path, semantic_field)
            
            # 更新时间戳
            semantic_field.updated_at = datetime.now()
            
            # 保存到主文件
            success = await self._save_file_async(file_path, semantic_field.to_dict())
            
            if success:
                logger.debug("字段语义保存成功",
                           instance=instance_name,
                           database=database_name,
                           collection=collection_name,
                           field=field_path)
            
            return success
            
        except Exception as e:
            logger.error("保存字段语义失败",
                        instance=instance_name,
                        database=database_name,
                        collection=collection_name,
                        field=field_path,
                        error=str(e))
            return False
    
    async def get_field_semantic(self, instance_name: str, database_name: str,
                               collection_name: str, field_path: str) -> Optional[SemanticField]:
        """获取字段语义信息"""
        try:
            file_path = self._get_field_path(instance_name, database_name,
                                           collection_name, field_path)
            
            data = await self._load_file_async(file_path)
            if data:
                return SemanticField.from_dict(data)
            
            return None
            
        except Exception as e:
            logger.error("获取字段语义失败",
                        instance=instance_name,
                        database=database_name,
                        collection=collection_name,
                        field=field_path,
                        error=str(e))
            return None
    
    async def batch_save_semantics(self, instance_name: str, database_name: str,
                                 collection_name: str, 
                                 semantic_data: Dict[str, SemanticField]) -> Dict[str, bool]:
        """批量保存字段语义信息"""
        results = {}
        
        # 使用文件管理器的批量操作上下文
        async with self.file_manager.batch_operation():
            # 并发执行保存操作
            tasks = []
            for field_path, semantic_field in semantic_data.items():
                task = self.save_field_semantic(
                    instance_name, database_name, collection_name,
                    field_path, semantic_field
                )
                tasks.append((field_path, task))
            
            # 等待所有任务完成
            for field_path, task in tasks:
                try:
                    success = await task
                    results[field_path] = success
                except Exception as e:
                    logger.error(f"批量保存字段{field_path}失败", error=str(e))
                    results[field_path] = False
        
        logger.info("批量保存语义完成",
                   instance=instance_name,
                   database=database_name,
                   collection=collection_name,
                   total=len(semantic_data),
                   success=sum(1 for r in results.values() if r))
        
        return results
    
    async def batch_get_semantics(self, instance_name: str, database_name: str,
                                collection_name: str, 
                                field_paths: List[str]) -> Dict[str, Optional[SemanticField]]:
        """批量获取字段语义信息"""
        results = {}
        
        # 并发执行获取操作
        tasks = []
        for field_path in field_paths:
            task = self.get_field_semantic(
                instance_name, database_name, collection_name, field_path
            )
            tasks.append((field_path, task))
        
        # 等待所有任务完成
        for field_path, task in tasks:
            try:
                semantic_field = await task
                results[field_path] = semantic_field
            except Exception as e:
                logger.error(f"批量获取字段{field_path}失败", error=str(e))
                results[field_path] = None
        
        return results
    
    async def search_semantics(self, query: SemanticSearchQuery) -> List[Tuple[str, SemanticField]]:
        """搜索语义信息"""
        results = []
        
        try:
            # 构建搜索路径
            search_paths = []
            
            if query.instance_name and query.database_name and query.collection_name:
                # 精确集合搜索
                collection_path = (self.base_path / "instances" / query.instance_name /
                                 "databases" / query.database_name / "collections" /
                                 query.collection_name)
                if collection_path.exists():
                    search_paths.append(collection_path)
            elif query.instance_name and query.database_name:
                # 数据库级搜索
                database_path = (self.base_path / "instances" / query.instance_name /
                               "databases" / query.database_name / "collections")
                if database_path.exists():
                    search_paths.extend(database_path.iterdir())
            elif query.instance_name:
                # 实例级搜索
                instance_path = (self.base_path / "instances" / query.instance_name /
                               "databases")
                if instance_path.exists():
                    for db_path in instance_path.iterdir():
                        collections_path = db_path / "collections"
                        if collections_path.exists():
                            search_paths.extend(collections_path.iterdir())
            else:
                # 全局搜索
                instances_path = self.base_path / "instances"
                if instances_path.exists():
                    for instance_path in instances_path.iterdir():
                        databases_path = instance_path / "databases"
                        if databases_path.exists():
                            for db_path in databases_path.iterdir():
                                collections_path = db_path / "collections"
                                if collections_path.exists():
                                    search_paths.extend(collections_path.iterdir())
            
            # 在找到的路径中搜索
            for search_path in search_paths:
                if not search_path.is_dir():
                    continue
                
                for field_file in search_path.glob("*.json"):
                    try:
                        data = await self._load_file_async(field_file)
                        if not data:
                            continue
                        
                        semantic_field = SemanticField.from_dict(data)
                        
                        # 应用查询过滤器
                        if self._matches_query(semantic_field, field_file, query):
                            field_path = field_file.stem.replace('_', '/')
                            results.append((field_path, semantic_field))
                    
                    except Exception as e:
                        logger.warning(f"搜索文件{field_file}时出错", error=str(e))
            
            # 排序和限制结果
            results.sort(key=lambda x: x[1].confidence, reverse=True)
            results = results[:query.limit]
            
        except Exception as e:
            logger.error("语义搜索失败", error=str(e))
        
        return results
    
    def _matches_query(self, semantic_field: SemanticField, 
                      file_path: Path, query: SemanticSearchQuery) -> bool:
        """检查语义字段是否匹配查询条件"""
        # 搜索词匹配
        if query.search_term:
            search_term = query.search_term.lower()
            if (search_term not in semantic_field.business_meaning.lower() and
                search_term not in str(semantic_field.examples).lower() and
                search_term not in file_path.stem.lower()):
                return False
        
        # 置信度范围
        if query.confidence_min is not None and semantic_field.confidence < query.confidence_min:
            return False
        if query.confidence_max is not None and semantic_field.confidence > query.confidence_max:
            return False
        
        # 来源匹配
        if query.source and semantic_field.source != query.source:
            return False
        
        # 标签匹配
        if query.tags:
            if not any(tag in semantic_field.tags for tag in query.tags):
                return False
        
        return True
    
    async def delete_field_semantic(self, instance_name: str, database_name: str,
                                  collection_name: str, field_path: str) -> bool:
        """删除字段语义信息"""
        try:
            file_path = self._get_field_path(instance_name, database_name,
                                           collection_name, field_path)
            
            if file_path.exists():
                # 备份到删除记录
                backup_path = self.base_path / "deleted" / f"{datetime.now().isoformat()}"
                backup_path.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, backup_path / file_path.name)
                
                # 删除主文件
                file_path.unlink()
                
                # 删除版本历史
                if self.enable_versioning:
                    version_path = self._get_version_path(
                        instance_name, database_name, collection_name, field_path
                    )
                    if version_path.exists():
                        shutil.rmtree(version_path)
                
                return True
            
            return False
            
        except Exception as e:
            logger.error("删除字段语义失败",
                        instance=instance_name,
                        database=database_name,
                        collection=collection_name,
                        field=field_path,
                        error=str(e))
            return False
    
    async def get_collection_semantics(self, instance_name: str, database_name: str,
                                     collection_name: str) -> Dict[str, SemanticField]:
        """获取集合的所有字段语义信息"""
        results = {}
        
        try:
            collection_path = (self.base_path / "instances" / instance_name /
                             "databases" / database_name / "collections" / collection_name)
            
            if not collection_path.exists():
                return results
            
            # 并发加载所有字段文件
            tasks = []
            for field_file in collection_path.glob("*.json"):
                field_path = field_file.stem.replace('_', '/')
                task = self.get_field_semantic(
                    instance_name, database_name, collection_name, field_path
                )
                tasks.append((field_path, task))
            
            # 等待所有任务完成
            for field_path, task in tasks:
                try:
                    semantic_field = await task
                    if semantic_field:
                        results[field_path] = semantic_field
                except Exception as e:
                    logger.warning(f"获取字段{field_path}语义失败", error=str(e))
        
        except Exception as e:
            logger.error("获取集合语义失败",
                        instance=instance_name,
                        database=database_name,
                        collection=collection_name,
                        error=str(e))
        
        return results
    
    async def detect_conflicts(self, instance_name: str, database_name: str,
                             collection_name: str, field_path: str,
                             new_semantic: SemanticField) -> List[SemanticConflictInfo]:
        """检测语义冲突"""
        conflicts = []
        
        try:
            # 获取现有语义
            existing_semantic = await self.get_field_semantic(
                instance_name, database_name, collection_name, field_path
            )
            
            if existing_semantic:
                # 检查业务含义冲突
                if (existing_semantic.business_meaning != new_semantic.business_meaning and
                    existing_semantic.business_meaning and new_semantic.business_meaning):
                    
                    confidence_diff = abs(existing_semantic.confidence - new_semantic.confidence)
                    
                    conflict = SemanticConflictInfo(
                        field_path=field_path,
                        existing_meaning=existing_semantic.business_meaning,
                        new_meaning=new_semantic.business_meaning,
                        confidence_diff=confidence_diff,
                        # 自动解决策略
                        resolution_strategy="prefer_higher_confidence" if confidence_diff > 0.2 else "manual"
                    )
                    conflicts.append(conflict)
        
        except Exception as e:
            logger.error("检测语义冲突失败", error=str(e))
        
        return conflicts
    
    async def resolve_conflict(self, conflict: SemanticConflictInfo,
                             resolution_strategy: str) -> bool:
        """解决语义冲突"""
        # 这里是基础实现，实际项目中可能需要更复杂的冲突解决逻辑
        try:
            logger.info("解决语义冲突",
                       field_path=conflict.field_path,
                       strategy=resolution_strategy)
            
            # 记录冲突解决历史
            resolution_record = {
                "timestamp": datetime.now().isoformat(),
                "conflict": conflict.__dict__,
                "resolution_strategy": resolution_strategy,
                "resolved": True
            }
            
            resolution_file = (self.conflicts_path / 
                             f"resolved_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            await self._save_file_async(resolution_file, resolution_record)
            
            return True
            
        except Exception as e:
            logger.error("解决语义冲突失败", error=str(e))
            return False
    
    async def get_semantic_history(self, instance_name: str, database_name: str,
                                 collection_name: str, field_path: str,
                                 limit: int = 10) -> List[SemanticField]:
        """获取字段语义变更历史"""
        if not self.enable_versioning:
            return []
        
        history = []
        
        try:
            version_path = self._get_version_path(
                instance_name, database_name, collection_name, field_path
            )
            
            if not version_path.exists():
                return history
            
            # 获取所有版本文件，按时间排序
            version_files = sorted(version_path.glob("*.json"), 
                                 key=lambda f: f.stat().st_mtime, reverse=True)
            
            for version_file in version_files[:limit]:
                try:
                    data = await self._load_file_async(version_file)
                    if data:
                        semantic_field = SemanticField.from_dict(data)
                        history.append(semantic_field)
                except Exception as e:
                    logger.warning(f"加载版本文件{version_file}失败", error=str(e))
        
        except Exception as e:
            logger.error("获取语义历史失败", error=str(e))
        
        return history
    
    async def create_semantic_snapshot(self, instance_name: str, database_name: str,
                                     collection_name: str, snapshot_name: str) -> bool:
        """创建语义快照"""
        try:
            # 获取集合的所有语义数据
            semantics = await self.get_collection_semantics(
                instance_name, database_name, collection_name
            )
            
            # 创建快照数据
            snapshot_data = {
                "timestamp": datetime.now().isoformat(),
                "instance_name": instance_name,
                "database_name": database_name,
                "collection_name": collection_name,
                "semantics": {path: field.to_dict() for path, field in semantics.items()}
            }
            
            # 保存快照
            snapshot_file = (self.snapshots_path / 
                           f"{instance_name}_{database_name}_{collection_name}_{snapshot_name}.json")
            success = await self._save_file_async(snapshot_file, snapshot_data)
            
            if success:
                logger.info("语义快照创建成功",
                           instance=instance_name,
                           database=database_name,
                           collection=collection_name,
                           snapshot=snapshot_name)
            
            return success
            
        except Exception as e:
            logger.error("创建语义快照失败", error=str(e))
            return False
    
    async def restore_from_snapshot(self, instance_name: str, database_name: str,
                                  collection_name: str, snapshot_name: str) -> bool:
        """从快照恢复"""
        try:
            # 查找快照文件
            snapshot_file = (self.snapshots_path / 
                           f"{instance_name}_{database_name}_{collection_name}_{snapshot_name}.json")
            
            if not snapshot_file.exists():
                logger.error("快照文件不存在", snapshot_file=str(snapshot_file))
                return False
            
            # 加载快照数据
            snapshot_data = await self._load_file_async(snapshot_file)
            if not snapshot_data:
                return False
            
            # 恢复语义数据
            semantics = snapshot_data.get("semantics", {})
            semantic_fields = {path: SemanticField.from_dict(data) 
                             for path, data in semantics.items()}
            
            # 批量保存
            results = await self.batch_save_semantics(
                instance_name, database_name, collection_name, semantic_fields
            )
            
            success_count = sum(1 for r in results.values() if r)
            logger.info("从快照恢复完成",
                       instance=instance_name,
                       database=database_name,
                       collection=collection_name,
                       snapshot=snapshot_name,
                       restored=success_count,
                       total=len(semantics))
            
            return success_count > 0
            
        except Exception as e:
            logger.error("从快照恢复失败", error=str(e))
            return False
    
    async def cleanup_old_versions(self, days: int = 30) -> int:
        """清理旧版本数据"""
        if not self.enable_versioning:
            return 0
        
        cleaned_count = 0
        cutoff_time = datetime.now() - timedelta(days=days)
        
        try:
            if not self.versions_path.exists():
                return 0
            
            # 遍历所有版本文件
            for version_file in self.versions_path.rglob("*.json"):
                try:
                    # 检查文件修改时间
                    mtime = datetime.fromtimestamp(version_file.stat().st_mtime)
                    if mtime < cutoff_time:
                        version_file.unlink()
                        cleaned_count += 1
                except Exception as e:
                    logger.warning(f"清理版本文件{version_file}失败", error=str(e))
            
            logger.info("版本清理完成", cleaned_count=cleaned_count, days=days)
            
        except Exception as e:
            logger.error("版本清理失败", error=str(e))
        
        return cleaned_count
    
    async def get_storage_stats(self) -> Dict[str, Any]:
        """获取存储统计信息"""
        stats = {
            "total_instances": 0,
            "total_databases": 0,
            "total_collections": 0,
            "total_fields": 0,
            "total_versions": 0,
            "total_snapshots": 0,
            "storage_size_bytes": 0,
            "last_updated": None
        }
        
        try:
            instances_path = self.base_path / "instances"
            if instances_path.exists():
                for instance_path in instances_path.iterdir():
                    if instance_path.is_dir():
                        stats["total_instances"] += 1
                        
                        databases_path = instance_path / "databases"
                        if databases_path.exists():
                            for db_path in databases_path.iterdir():
                                if db_path.is_dir():
                                    stats["total_databases"] += 1
                                    
                                    collections_path = db_path / "collections"
                                    if collections_path.exists():
                                        for collection_path in collections_path.iterdir():
                                            if collection_path.is_dir():
                                                stats["total_collections"] += 1
                                                
                                                field_count = len(list(collection_path.glob("*.json")))
                                                stats["total_fields"] += field_count
            
            # 统计版本文件
            if self.versions_path.exists():
                stats["total_versions"] = len(list(self.versions_path.rglob("*.json")))
            
            # 统计快照文件
            if self.snapshots_path.exists():
                stats["total_snapshots"] = len(list(self.snapshots_path.glob("*.json")))
            
            # 计算存储大小
            stats["storage_size_bytes"] = sum(
                f.stat().st_size for f in self.base_path.rglob("*") if f.is_file()
            )
            
            stats["last_updated"] = datetime.now().isoformat()
            
        except Exception as e:
            logger.error("获取存储统计失败", error=str(e))
        
        return stats
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        health = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "checks": {}
        }
        
        try:
            # 检查基础路径
            health["checks"]["base_path_exists"] = self.base_path.exists()
            health["checks"]["base_path_writable"] = os.access(self.base_path, os.W_OK)
            
            # 检查缓存状态
            if hasattr(self.file_manager, 'cache'):
                cache_info = self.file_manager.cache.get_stats()
                health["checks"]["cache_status"] = cache_info
            
            # 检查线程池
            health["checks"]["thread_pool_active"] = not self.thread_pool._shutdown
            
            # 整体状态
            all_checks_passed = all(
                check for check in health["checks"].values() 
                if isinstance(check, bool)
            )
            
            if not all_checks_passed:
                health["status"] = "degraded"
                
        except Exception as e:
            health["status"] = "unhealthy"
            health["error"] = str(e)
            logger.error("健康检查失败", error=str(e))
        
        return health
    
    # 辅助方法
    async def _save_file_async(self, file_path: Path, data: Dict[str, Any]) -> bool:
        """异步保存文件"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.thread_pool, self._save_file_sync, file_path, data)
    
    async def _load_file_async(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """异步加载文件"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.thread_pool, self._load_file_sync, file_path)
    
    def _save_file_sync(self, file_path: Path, data: Dict[str, Any]) -> bool:
        """同步保存文件"""
        try:
            # 创建目录
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 原子写入
            with tempfile.NamedTemporaryFile(
                mode='w', 
                dir=file_path.parent, 
                delete=False,
                encoding='utf-8'
            ) as temp_file:
                json.dump(data, temp_file, ensure_ascii=False, indent=2)
                temp_file.flush()
                
                # 原子重命名
                temp_path = Path(temp_file.name)
                temp_path.replace(file_path)
            
            return True
            
        except Exception as e:
            logger.error(f"保存文件{file_path}失败", error=str(e))
            return False
    
    def _load_file_sync(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """同步加载文件"""
        try:
            if not file_path.exists():
                return None
            
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
                
        except Exception as e:
            logger.error(f"加载文件{file_path}失败", error=str(e))
            return None
    
    async def _save_version(self, instance_name: str, database_name: str,
                          collection_name: str, field_path: str,
                          semantic_field: SemanticField):
        """保存版本历史"""
        try:
            version_dir = self._get_version_path(
                instance_name, database_name, collection_name, field_path
            )
            version_dir.mkdir(parents=True, exist_ok=True)
            
            # 生成版本文件名
            version_id = self._generate_version_id(semantic_field)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            version_file = version_dir / f"{timestamp}_{version_id}.json"
            
            # 保存版本数据
            await self._save_file_async(version_file, semantic_field.to_dict())
            
            # 清理旧版本（保持最大版本数限制）
            await self._cleanup_old_versions_for_field(version_dir, self.max_versions)
            
        except Exception as e:
            logger.error("保存版本历史失败", error=str(e))
    
    async def _cleanup_old_versions_for_field(self, version_dir: Path, max_versions: int):
        """清理单个字段的旧版本"""
        try:
            version_files = sorted(version_dir.glob("*.json"), 
                                 key=lambda f: f.stat().st_mtime, reverse=True)
            
            # 删除超过限制的旧版本
            for old_version in version_files[max_versions:]:
                old_version.unlink()
                
        except Exception as e:
            logger.error("清理字段旧版本失败", error=str(e))
    
    async def _record_conflicts(self, conflicts: List[SemanticConflictInfo]):
        """记录冲突信息"""
        try:
            conflict_record = {
                "timestamp": datetime.now().isoformat(),
                "conflicts": [conflict.__dict__ for conflict in conflicts]
            }
            
            conflict_file = (self.conflicts_path / 
                           f"conflict_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            await self._save_file_async(conflict_file, conflict_record)
            
        except Exception as e:
            logger.error("记录冲突信息失败", error=str(e))
    
    def __del__(self):
        """析构函数，清理资源"""
        if hasattr(self, 'thread_pool'):
            self.thread_pool.shutdown(wait=False)