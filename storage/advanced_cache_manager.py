# -*- coding: utf-8 -*-
"""
高级缓存管理器

提供多层次、智能化的语义数据缓存策略
"""

import asyncio
import time
import threading
from typing import Dict, Any, Optional, Tuple, Set, List
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
import structlog
import weakref
import hashlib

logger = structlog.get_logger(__name__)


@dataclass
class CacheEntry:
    """缓存条目"""
    data: Any
    timestamp: float
    ttl: float
    access_count: int = 0
    last_access: float = 0
    size: int = 0
    
    def __post_init__(self):
        self.last_access = self.timestamp
        # 计算数据大小（简化版）
        import sys
        self.size = sys.getsizeof(self.data)
    
    @property
    def is_expired(self) -> bool:
        """是否已过期"""
        return time.time() > (self.timestamp + self.ttl)
    
    @property
    def age(self) -> float:
        """年龄（秒）"""
        return time.time() - self.timestamp
    
    def touch(self):
        """更新访问时间"""
        self.access_count += 1
        self.last_access = time.time()


class MultiLevelCache:
    """多层级缓存"""
    
    def __init__(self, 
                 l1_size: int = 100, 
                 l1_ttl: float = 300,  # 5分钟
                 l2_size: int = 500,
                 l2_ttl: float = 1800,  # 30分钟
                 l3_size: int = 1000,
                 l3_ttl: float = 3600):  # 1小时
        """
        初始化多层级缓存
        
        L1: 热点数据，高频访问
        L2: 温数据，中频访问  
        L3: 冷数据，低频访问
        """
        self.l1_cache = OrderedDict()  # LRU缓存
        self.l2_cache = OrderedDict()
        self.l3_cache = OrderedDict()
        
        self.l1_size = l1_size
        self.l1_ttl = l1_ttl
        self.l2_size = l2_size
        self.l2_ttl = l2_ttl
        self.l3_size = l3_size
        self.l3_ttl = l3_ttl
        
        # 统计信息
        self.stats = {
            'l1_hits': 0, 'l1_misses': 0,
            'l2_hits': 0, 'l2_misses': 0,
            'l3_hits': 0, 'l3_misses': 0,
            'promotions': 0, 'evictions': 0
        }
        
        # 线程锁
        self.lock = threading.RLock()
        
        logger.info("多层级缓存初始化完成",
                   l1_size=l1_size, l2_size=l2_size, l3_size=l3_size)
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存数据"""
        with self.lock:
            # L1 缓存查找
            if key in self.l1_cache:
                entry = self.l1_cache[key]
                if not entry.is_expired:
                    entry.touch()
                    # 移到末尾（LRU）
                    self.l1_cache.move_to_end(key)
                    self.stats['l1_hits'] += 1
                    return entry.data
                else:
                    del self.l1_cache[key]
            
            self.stats['l1_misses'] += 1
            
            # L2 缓存查找
            if key in self.l2_cache:
                entry = self.l2_cache[key]
                if not entry.is_expired:
                    entry.touch()
                    # 提升到L1
                    self._promote_to_l1(key, entry)
                    del self.l2_cache[key]
                    self.stats['l2_hits'] += 1
                    self.stats['promotions'] += 1
                    return entry.data
                else:
                    del self.l2_cache[key]
            
            self.stats['l2_misses'] += 1
            
            # L3 缓存查找
            if key in self.l3_cache:
                entry = self.l3_cache[key]
                if not entry.is_expired:
                    entry.touch()
                    # 提升到L2
                    self._promote_to_l2(key, entry)
                    del self.l3_cache[key]
                    self.stats['l3_hits'] += 1
                    self.stats['promotions'] += 1
                    return entry.data
                else:
                    del self.l3_cache[key]
            
            self.stats['l3_misses'] += 1
            return None
    
    def put(self, key: str, data: Any, ttl: Optional[float] = None):
        """存储缓存数据"""
        with self.lock:
            # 根据访问频率决定存储层级
            if ttl is None:
                ttl = self.l1_ttl
            
            entry = CacheEntry(data=data, timestamp=time.time(), ttl=ttl)
            
            # 默认存储到L1
            self._put_to_l1(key, entry)
    
    def _put_to_l1(self, key: str, entry: CacheEntry):
        """存储到L1缓存"""
        if key in self.l1_cache:
            del self.l1_cache[key]
        
        self.l1_cache[key] = entry
        
        # 检查容量限制
        while len(self.l1_cache) > self.l1_size:
            # 移除最老的条目到L2
            lru_key, lru_entry = self.l1_cache.popitem(last=False)
            if not lru_entry.is_expired:
                self._demote_to_l2(lru_key, lru_entry)
            self.stats['evictions'] += 1
    
    def _promote_to_l1(self, key: str, entry: CacheEntry):
        """提升到L1缓存"""
        entry.ttl = self.l1_ttl
        self._put_to_l1(key, entry)
    
    def _put_to_l2(self, key: str, entry: CacheEntry):
        """存储到L2缓存"""
        if key in self.l2_cache:
            del self.l2_cache[key]
        
        entry.ttl = self.l2_ttl
        self.l2_cache[key] = entry
        
        # 检查容量限制
        while len(self.l2_cache) > self.l2_size:
            lru_key, lru_entry = self.l2_cache.popitem(last=False)
            if not lru_entry.is_expired:
                self._demote_to_l3(lru_key, lru_entry)
            self.stats['evictions'] += 1
    
    def _promote_to_l2(self, key: str, entry: CacheEntry):
        """提升到L2缓存"""
        self._put_to_l2(key, entry)
    
    def _demote_to_l2(self, key: str, entry: CacheEntry):
        """降级到L2缓存"""
        self._put_to_l2(key, entry)
    
    def _put_to_l3(self, key: str, entry: CacheEntry):
        """存储到L3缓存"""
        if key in self.l3_cache:
            del self.l3_cache[key]
        
        entry.ttl = self.l3_ttl
        self.l3_cache[key] = entry
        
        # 检查容量限制
        while len(self.l3_cache) > self.l3_size:
            self.l3_cache.popitem(last=False)
            self.stats['evictions'] += 1
    
    def _demote_to_l3(self, key: str, entry: CacheEntry):
        """降级到L3缓存"""
        self._put_to_l3(key, entry)
    
    def remove(self, key: str) -> bool:
        """移除缓存条目"""
        with self.lock:
            removed = False
            if key in self.l1_cache:
                del self.l1_cache[key]
                removed = True
            if key in self.l2_cache:
                del self.l2_cache[key]
                removed = True
            if key in self.l3_cache:
                del self.l3_cache[key]
                removed = True
            return removed
    
    def clear(self):
        """清空所有缓存"""
        with self.lock:
            self.l1_cache.clear()
            self.l2_cache.clear()
            self.l3_cache.clear()
    
    def cleanup_expired(self) -> int:
        """清理过期条目"""
        with self.lock:
            cleaned = 0
            
            # 清理L1
            expired_keys = [k for k, v in self.l1_cache.items() if v.is_expired]
            for key in expired_keys:
                del self.l1_cache[key]
                cleaned += 1
            
            # 清理L2
            expired_keys = [k for k, v in self.l2_cache.items() if v.is_expired]
            for key in expired_keys:
                del self.l2_cache[key]
                cleaned += 1
            
            # 清理L3
            expired_keys = [k for k, v in self.l3_cache.items() if v.is_expired]
            for key in expired_keys:
                del self.l3_cache[key]
                cleaned += 1
            
            return cleaned
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        with self.lock:
            total_hits = self.stats['l1_hits'] + self.stats['l2_hits'] + self.stats['l3_hits']
            total_misses = self.stats['l1_misses'] + self.stats['l2_misses'] + self.stats['l3_misses']
            hit_rate = total_hits / (total_hits + total_misses) if (total_hits + total_misses) > 0 else 0
            
            return {
                **self.stats,
                'total_hits': total_hits,
                'total_misses': total_misses,
                'hit_rate': hit_rate,
                'l1_size': len(self.l1_cache),
                'l2_size': len(self.l2_cache), 
                'l3_size': len(self.l3_cache),
                'total_size': len(self.l1_cache) + len(self.l2_cache) + len(self.l3_cache)
            }


class SmartSemanticCache:
    """智能语义缓存管理器"""
    
    def __init__(self, 
                 enable_multilevel: bool = True,
                 enable_query_cache: bool = True,
                 enable_result_prefetch: bool = True,
                 cache_size: int = 2000,
                 cache_ttl: int = 3600):
        """
        初始化智能语义缓存
        
        Args:
            enable_multilevel: 启用多层级缓存
            enable_query_cache: 启用查询结果缓存
            enable_result_prefetch: 启用结果预取
            cache_size: 缓存大小
            cache_ttl: 缓存TTL
        """
        self.enable_multilevel = enable_multilevel
        self.enable_query_cache = enable_query_cache
        self.enable_result_prefetch = enable_result_prefetch
        
        # 主缓存
        if enable_multilevel:
            self.main_cache = MultiLevelCache(
                l1_size=cache_size // 10,
                l2_size=cache_size // 5,
                l3_size=cache_size
            )
        else:
            self.main_cache = OrderedDict()
            self.cache_size = cache_size
            self.cache_ttl = cache_ttl
        
        # 查询缓存
        self.query_cache = OrderedDict() if enable_query_cache else None
        self.query_cache_size = 500
        
        # 预取缓存
        self.prefetch_cache = OrderedDict() if enable_result_prefetch else None
        self.prefetch_patterns = defaultdict(int)  # 访问模式统计
        
        # 缓存依赖关系图
        self.dependency_graph = defaultdict(set)
        self.reverse_deps = defaultdict(set)
        
        # 统计信息
        self.cache_stats = {
            'hits': 0, 'misses': 0, 'prefetch_hits': 0,
            'invalidations': 0, 'dependency_invalidations': 0
        }
        
        # 清理任务
        self.cleanup_task = None
        self.start_cleanup_task()
        
        logger.info("智能语义缓存初始化完成",
                   multilevel=enable_multilevel,
                   query_cache=enable_query_cache,
                   prefetch=enable_result_prefetch)
    
    def get_field_semantic(self, instance: str, database: str, collection: str, field: str) -> Optional[Any]:
        """获取字段语义缓存"""
        cache_key = self._make_field_key(instance, database, collection, field)
        
        # 记录访问模式
        if self.enable_result_prefetch:
            self._record_access_pattern(instance, database, collection, field)
        
        # 多层级缓存查找
        if self.enable_multilevel:
            result = self.main_cache.get(cache_key)
        else:
            entry = self.main_cache.get(cache_key)
            if entry and not entry.is_expired:
                entry.touch()
                self.main_cache.move_to_end(cache_key)
                result = entry.data
            else:
                if entry:
                    del self.main_cache[cache_key]
                result = None
        
        if result:
            self.cache_stats['hits'] += 1
        else:
            self.cache_stats['misses'] += 1
            # 触发预取
            if self.enable_result_prefetch:
                asyncio.create_task(self._prefetch_related(instance, database, collection, field))
        
        return result
    
    def put_field_semantic(self, instance: str, database: str, collection: str, 
                          field: str, data: Any, dependencies: Set[str] = None):
        """存储字段语义缓存"""
        cache_key = self._make_field_key(instance, database, collection, field)
        
        # 存储到主缓存
        if self.enable_multilevel:
            self.main_cache.put(cache_key, data)
        else:
            entry = CacheEntry(data=data, timestamp=time.time(), ttl=self.cache_ttl)
            self.main_cache[cache_key] = entry
            
            # 检查容量限制
            while len(self.main_cache) > self.cache_size:
                self.main_cache.popitem(last=False)
        
        # 建立依赖关系
        if dependencies:
            self.dependency_graph[cache_key] = dependencies
            for dep in dependencies:
                self.reverse_deps[dep].add(cache_key)
    
    def get_query_result(self, query_hash: str) -> Optional[Any]:
        """获取查询结果缓存"""
        if not self.enable_query_cache or not self.query_cache:
            return None
        
        entry = self.query_cache.get(query_hash)
        if entry and not entry.is_expired:
            entry.touch()
            self.query_cache.move_to_end(query_hash)
            return entry.data
        elif entry:
            del self.query_cache[query_hash]
        
        return None
    
    def put_query_result(self, query_hash: str, result: Any, ttl: float = 600):
        """存储查询结果缓存"""
        if not self.enable_query_cache or not self.query_cache:
            return
        
        entry = CacheEntry(data=result, timestamp=time.time(), ttl=ttl)
        self.query_cache[query_hash] = entry
        
        # 检查容量限制
        while len(self.query_cache) > self.query_cache_size:
            self.query_cache.popitem(last=False)
    
    def invalidate_field(self, instance: str, database: str, collection: str, field: str):
        """使字段缓存失效"""
        cache_key = self._make_field_key(instance, database, collection, field)
        
        # 主缓存失效
        if self.enable_multilevel:
            self.main_cache.remove(cache_key)
        else:
            self.main_cache.pop(cache_key, None)
        
        # 级联失效依赖项
        self._cascade_invalidate(cache_key)
        
        self.cache_stats['invalidations'] += 1
    
    def invalidate_collection(self, instance: str, database: str, collection: str):
        """使集合相关缓存失效"""
        prefix = f"{instance}:{database}:{collection}:"
        
        # 查找所有相关缓存键
        keys_to_invalidate = []
        
        if self.enable_multilevel:
            # 多层级缓存需要检查所有层级
            with self.main_cache.lock:
                for cache_dict in [self.main_cache.l1_cache, self.main_cache.l2_cache, self.main_cache.l3_cache]:
                    keys_to_invalidate.extend([k for k in cache_dict.keys() if k.startswith(prefix)])
        else:
            keys_to_invalidate = [k for k in self.main_cache.keys() if k.startswith(prefix)]
        
        # 批量失效
        for key in keys_to_invalidate:
            if self.enable_multilevel:
                self.main_cache.remove(key)
            else:
                self.main_cache.pop(key, None)
            
            # 级联失效
            self._cascade_invalidate(key)
        
        self.cache_stats['invalidations'] += len(keys_to_invalidate)
    
    def _make_field_key(self, instance: str, database: str, collection: str, field: str) -> str:
        """生成字段缓存键"""
        return f"{instance}:{database}:{collection}:{field}"
    
    def _make_query_hash(self, query_params: Dict[str, Any]) -> str:
        """生成查询哈希"""
        query_str = json.dumps(query_params, sort_keys=True)
        return hashlib.md5(query_str.encode()).hexdigest()
    
    def _record_access_pattern(self, instance: str, database: str, collection: str, field: str):
        """记录访问模式"""
        pattern_key = f"{instance}:{database}:{collection}"
        self.prefetch_patterns[pattern_key] += 1
    
    async def _prefetch_related(self, instance: str, database: str, collection: str, field: str):
        """预取相关数据"""
        if not self.enable_result_prefetch:
            return
        
        # 基于访问模式预取同集合的其他字段
        pattern_key = f"{instance}:{database}:{collection}"
        if self.prefetch_patterns[pattern_key] > 5:  # 阈值
            # 这里应该调用实际的存储层来预取数据
            # 简化实现，仅作示例
            logger.debug("触发预取", pattern=pattern_key)
    
    def _cascade_invalidate(self, cache_key: str):
        """级联失效依赖缓存"""
        dependent_keys = self.reverse_deps.get(cache_key, set())
        
        for dep_key in dependent_keys:
            if self.enable_multilevel:
                self.main_cache.remove(dep_key)
            else:
                self.main_cache.pop(dep_key, None)
            
            # 递归失效
            self._cascade_invalidate(dep_key)
            self.cache_stats['dependency_invalidations'] += 1
        
        # 清理依赖关系
        if cache_key in self.dependency_graph:
            for dep in self.dependency_graph[cache_key]:
                self.reverse_deps[dep].discard(cache_key)
            del self.dependency_graph[cache_key]
        
        self.reverse_deps.pop(cache_key, None)
    
    def start_cleanup_task(self):
        """启动清理任务"""
        async def cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(300)  # 5分钟清理一次
                    cleaned = self.cleanup_expired()
                    if cleaned > 0:
                        logger.debug("缓存清理完成", cleaned=cleaned)
                except Exception as e:
                    logger.error("缓存清理异常", error=str(e))
        
        self.cleanup_task = asyncio.create_task(cleanup_loop())
    
    def cleanup_expired(self) -> int:
        """清理过期缓存"""
        cleaned = 0
        
        # 清理主缓存
        if self.enable_multilevel:
            cleaned += self.main_cache.cleanup_expired()
        else:
            expired_keys = [k for k, v in self.main_cache.items() if v.is_expired]
            for key in expired_keys:
                del self.main_cache[key]
                cleaned += 1
        
        # 清理查询缓存
        if self.query_cache:
            expired_keys = [k for k, v in self.query_cache.items() if v.is_expired]
            for key in expired_keys:
                del self.query_cache[key]
                cleaned += 1
        
        return cleaned
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        stats = self.cache_stats.copy()
        
        if self.enable_multilevel:
            stats.update(self.main_cache.get_stats())
        else:
            total_requests = stats['hits'] + stats['misses']
            stats['hit_rate'] = stats['hits'] / total_requests if total_requests > 0 else 0
            stats['cache_size'] = len(self.main_cache)
        
        if self.query_cache:
            stats['query_cache_size'] = len(self.query_cache)
        
        stats['prefetch_patterns'] = len(self.prefetch_patterns)
        stats['dependencies'] = len(self.dependency_graph)
        
        return stats
    
    def get_health_status(self) -> Dict[str, Any]:
        """获取缓存健康状态"""
        stats = self.get_stats()
        
        health = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "metrics": stats
        }
        
        # 健康检查规则
        if stats.get('hit_rate', 0) < 0.3:
            health["status"] = "degraded"
            health["warnings"] = ["缓存命中率过低"]
        
        if stats.get('total_size', 0) > self.cache_size * 0.9:
            health["status"] = "degraded" 
            health.setdefault("warnings", []).append("缓存使用率过高")
        
        return health
    
    def shutdown(self):
        """关闭缓存管理器"""
        if self.cleanup_task:
            self.cleanup_task.cancel()
        
        # 清理所有缓存
        if self.enable_multilevel:
            self.main_cache.clear()
        else:
            self.main_cache.clear()
        
        if self.query_cache:
            self.query_cache.clear()
        
        logger.info("智能语义缓存已关闭")