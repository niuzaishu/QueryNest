# -*- coding: utf-8 -*-
"""
语义文件管理器

提供高级的文件操作功能，包括缓存、锁机制和性能优化
"""

import asyncio
import time
try:
    import fcntl
except ImportError:
    fcntl = None  # Windows doesn't have fcntl
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import OrderedDict
import structlog
from contextlib import asynccontextmanager

from .local_semantic_storage import LocalSemanticStorage


logger = structlog.get_logger(__name__)


class TimedLRUCache:
    """带TTL的LRU缓存"""
    
    def __init__(self, maxsize: int = 128, ttl: int = 300):
        self.maxsize = maxsize
        self.ttl = ttl
        self.cache = OrderedDict()
        self.timestamps = {}
        self._lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        async with self._lock:
            if key in self.cache:
                # 检查是否过期
                if time.time() - self.timestamps[key] < self.ttl:
                    # 移动到末尾（最近使用）
                    value = self.cache.pop(key)
                    self.cache[key] = value
                    return value
                else:
                    # 过期，删除
                    del self.cache[key]
                    del self.timestamps[key]
            return None
    
    async def set(self, key: str, value: Any):
        """设置缓存值"""
        async with self._lock:
            # 如果已存在，先删除
            if key in self.cache:
                del self.cache[key]
                del self.timestamps[key]
            
            # 如果缓存满了，删除最旧的条目
            while len(self.cache) >= self.maxsize:
                oldest_key = next(iter(self.cache))
                del self.cache[oldest_key]
                del self.timestamps[oldest_key]
            
            # 添加新条目
            self.cache[key] = value
            self.timestamps[key] = time.time()
    
    async def invalidate(self, pattern: str = None):
        """缓存失效"""
        async with self._lock:
            if pattern is None:
                # 清空所有缓存
                self.cache.clear()
                self.timestamps.clear()
            else:
                # 按模式删除
                keys_to_remove = [key for key in self.cache.keys() if pattern in key]
                for key in keys_to_remove:
                    del self.cache[key]
                    del self.timestamps[key]
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        async with self._lock:
            current_time = time.time()
            expired_count = sum(1 for ts in self.timestamps.values() if current_time - ts >= self.ttl)
            
            return {
                "total_entries": len(self.cache),
                "expired_entries": expired_count,
                "max_size": self.maxsize,
                "ttl": self.ttl
            }


class FileLocker:
    """文件锁管理器"""
    
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.lock_file = None
        self.lock_path = file_path.with_suffix('.lock')
    
    async def __aenter__(self):
        """获取文件锁"""
        try:
            # 确保锁文件目录存在
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 创建锁文件
            self.lock_file = open(self.lock_path, 'w')
            
            # 尝试获取排他锁
            if fcntl is not None:
                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            
            logger.debug("文件锁获取成功", file_path=str(self.file_path))
            return self
            
        except (IOError, OSError) as e:
            if self.lock_file:
                self.lock_file.close()
                self.lock_file = None
            logger.warning("文件锁获取失败", file_path=str(self.file_path), error=str(e))
            raise
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """释放文件锁"""
        if self.lock_file:
            try:
                if fcntl is not None:
                    fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
                self.lock_file.close()
                
                # 删除锁文件
                if self.lock_path.exists():
                    self.lock_path.unlink()
                    
                logger.debug("文件锁释放成功", file_path=str(self.file_path))
                
            except Exception as e:
                logger.error("文件锁释放失败", file_path=str(self.file_path), error=str(e))
            finally:
                self.lock_file = None


class SemanticFileManager:
    """语义文件管理器"""
    
    def __init__(self, storage: LocalSemanticStorage, cache_size: int = 1000, cache_ttl: int = 300):
        self.storage = storage
        self.cache = TimedLRUCache(maxsize=cache_size, ttl=cache_ttl)
        self._operation_semaphore = asyncio.Semaphore(10)  # 限制并发操作数
        
    async def load_file_with_cache(self, file_path: Path, cache_key: str = None) -> Optional[Dict[str, Any]]:
        """带缓存的文件加载"""
        if cache_key is None:
            cache_key = str(file_path)
        
        # 尝试从缓存获取
        cached_data = await self.cache.get(cache_key)
        if cached_data is not None:
            logger.debug("缓存命中", cache_key=cache_key)
            return cached_data
        
        # 从文件加载
        async with self._operation_semaphore:
            data = await self.storage._read_json_file(file_path)
            
            if data is not None:
                # 存入缓存
                await self.cache.set(cache_key, data)
                logger.debug("文件加载并缓存", file_path=str(file_path))
            
            return data
    
    async def save_file_atomic(self, file_path: Path, data: Dict[str, Any], cache_key: str = None) -> bool:
        """原子性文件保存"""
        async with self._operation_semaphore:
            # 使用文件锁确保原子性
            async with FileLocker(file_path):
                success = await self.storage._atomic_write(file_path, data)
                
                if success:
                    # 更新缓存
                    if cache_key is None:
                        cache_key = str(file_path)
                    await self.cache.set(cache_key, data)
                    logger.debug("文件保存并更新缓存", file_path=str(file_path))
                
                return success
    
    async def invalidate_cache(self, pattern: str = None):
        """缓存失效"""
        await self.cache.invalidate(pattern)
        logger.info("缓存失效", pattern=pattern)
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        return await self.cache.get_stats()
    
    @asynccontextmanager
    async def batch_operation(self):
        """批量操作上下文管理器"""
        logger.info("开始批量操作")
        start_time = time.time()
        
        try:
            yield self
        finally:
            end_time = time.time()
            logger.info("批量操作完成", duration=f"{end_time - start_time:.2f}s")
    
    async def preload_instance_data(self, instance_name: str):
        """预加载实例数据到缓存"""
        logger.info("开始预加载实例数据", instance=instance_name)
        
        try:
            instance_path = self.storage._get_instance_path(instance_name)
            if not instance_path.exists():
                logger.warning("实例路径不存在", instance=instance_name)
                return
            
            # 预加载实例元数据
            metadata_file = instance_path / "metadata.json"
            if metadata_file.exists():
                await self.load_file_with_cache(metadata_file)
            
            # 预加载数据库和集合的字段文件
            databases_path = instance_path / "databases"
            if databases_path.exists():
                for db_path in databases_path.iterdir():
                    if not db_path.is_dir():
                        continue
                    
                    collections_path = db_path / "collections"
                    if collections_path.exists():
                        for collection_path in collections_path.iterdir():
                            if not collection_path.is_dir():
                                continue
                            
                            fields_file = collection_path / "fields.json"
                            if fields_file.exists():
                                await self.load_file_with_cache(fields_file)
            
            logger.info("实例数据预加载完成", instance=instance_name)
            
        except Exception as e:
            logger.error("预加载实例数据失败", instance=instance_name, error=str(e))
    
    async def cleanup_expired_cache(self):
        """清理过期缓存"""
        stats_before = await self.cache.get_stats()
        
        # 触发过期检查（通过尝试获取所有键）
        async with self.cache._lock:
            current_time = time.time()
            expired_keys = [
                key for key, timestamp in self.cache.timestamps.items()
                if current_time - timestamp >= self.cache.ttl
            ]
            
            for key in expired_keys:
                if key in self.cache.cache:
                    del self.cache.cache[key]
                if key in self.cache.timestamps:
                    del self.cache.timestamps[key]
        
        stats_after = await self.cache.get_stats()
        
        logger.info(
            "缓存清理完成",
            expired_count=len(expired_keys),
            before_count=stats_before["total_entries"],
            after_count=stats_after["total_entries"]
        )
    
    async def backup_semantic_data(self, instance_name: str, backup_path: Path) -> bool:
        """备份语义数据"""
        try:
            import shutil
            import tarfile
            from datetime import datetime
            
            instance_path = self.storage._get_instance_path(instance_name)
            if not instance_path.exists():
                logger.error("实例路径不存在", instance=instance_name)
                return False
            
            # 创建备份目录
            backup_path.mkdir(parents=True, exist_ok=True)
            
            # 生成备份文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = backup_path / f"{instance_name}_semantic_backup_{timestamp}.tar.gz"
            
            # 创建压缩备份
            with tarfile.open(backup_file, "w:gz") as tar:
                tar.add(instance_path, arcname=instance_name)
            
            logger.info(
                "语义数据备份完成",
                instance=instance_name,
                backup_file=str(backup_file),
                file_size=backup_file.stat().st_size
            )
            
            return True
            
        except Exception as e:
            logger.error("备份语义数据失败", instance=instance_name, error=str(e))
            return False
    
    async def restore_semantic_data(self, backup_file: Path, instance_name: str) -> bool:
        """恢复语义数据"""
        try:
            import tarfile
            
            if not backup_file.exists():
                logger.error("备份文件不存在", backup_file=str(backup_file))
                return False
            
            instance_path = self.storage._get_instance_path(instance_name)
            
            # 如果实例目录已存在，先备份
            if instance_path.exists():
                backup_existing = instance_path.with_suffix('.backup')
                if backup_existing.exists():
                    shutil.rmtree(backup_existing)
                shutil.move(str(instance_path), str(backup_existing))
            
            # 解压恢复
            with tarfile.open(backup_file, "r:gz") as tar:
                tar.extractall(path=self.storage.base_path / "instances")
            
            # 清理相关缓存
            await self.invalidate_cache(instance_name)
            
            logger.info(
                "语义数据恢复完成",
                instance=instance_name,
                backup_file=str(backup_file)
            )
            
            return True
            
        except Exception as e:
            logger.error("恢复语义数据失败", instance=instance_name, error=str(e))
            return False
    
    async def optimize_storage(self, instance_name: str) -> Dict[str, Any]:
        """优化存储结构"""
        optimization_stats = {
            "files_processed": 0,
            "files_optimized": 0,
            "space_saved": 0,
            "errors": []
        }
        
        try:
            instance_path = self.storage._get_instance_path(instance_name)
            if not instance_path.exists():
                return optimization_stats
            
            # 遍历所有字段文件进行优化
            databases_path = instance_path / "databases"
            if databases_path.exists():
                for db_path in databases_path.iterdir():
                    if not db_path.is_dir():
                        continue
                    
                    collections_path = db_path / "collections"
                    if collections_path.exists():
                        for collection_path in collections_path.iterdir():
                            if not collection_path.is_dir():
                                continue
                            
                            fields_file = collection_path / "fields.json"
                            if fields_file.exists():
                                optimization_stats["files_processed"] += 1
                                
                                # 优化文件（移除空字段、压缩格式等）
                                optimized = await self._optimize_fields_file(fields_file)
                                if optimized:
                                    optimization_stats["files_optimized"] += 1
            
            logger.info(
                "存储优化完成",
                instance=instance_name,
                stats=optimization_stats
            )
            
        except Exception as e:
            optimization_stats["errors"].append(str(e))
            logger.error("存储优化失败", instance=instance_name, error=str(e))
        
        return optimization_stats
    
    async def _optimize_fields_file(self, fields_file: Path) -> bool:
        """优化字段文件"""
        try:
            original_size = fields_file.stat().st_size
            
            # 读取文件
            data = await self.storage._read_json_file(fields_file)
            if not data:
                return False
            
            # 优化数据结构
            optimized = False
            
            # 移除空的分析结果
            if "fields" in data:
                for field_path, field_info in data["fields"].items():
                    if "analysis_result" in field_info:
                        analysis = field_info["analysis_result"]
                        if not analysis or (isinstance(analysis, dict) and not any(analysis.values())):
                            del field_info["analysis_result"]
                            optimized = True
                    
                    # 移除空的示例列表
                    if "examples" in field_info and not field_info["examples"]:
                        del field_info["examples"]
                        optimized = True
            
            # 如果有优化，重新保存
            if optimized:
                success = await self.storage._atomic_write(fields_file, data)
                if success:
                    new_size = fields_file.stat().st_size
                    logger.debug(
                        "字段文件优化完成",
                        file=str(fields_file),
                        original_size=original_size,
                        new_size=new_size,
                        saved=original_size - new_size
                    )
                return success
            
            return False
            
        except Exception as e:
            logger.error("优化字段文件失败", file=str(fields_file), error=str(e))
            return False