# -*- coding: utf-8 -*-
"""
元数据缓存管理器 - 负责元数据的智能缓存
"""

from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import asyncio
import structlog
from abc import ABC, abstractmethod
import hashlib
from collections import OrderedDict
import threading

logger = structlog.get_logger(__name__)


class CacheEntry:
    """缓存条目"""
    
    def __init__(self, key: str, value: Any, ttl: int = 3600, namespace: str = ""):
        self.key = key
        self.value = value
        self.namespace = namespace  # 存储命名空间信息
        self.created_at = datetime.now()
        self.expires_at = self.created_at + timedelta(seconds=ttl)
        self.access_count = 0
        self.last_accessed = datetime.now()
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        return datetime.now() > self.expires_at
    
    def access(self) -> Any:
        """访问缓存条目"""
        self.access_count += 1
        self.last_accessed = datetime.now()
        return self.value
    
    def extend_ttl(self, seconds: int):
        """延长TTL"""
        self.expires_at = datetime.now() + timedelta(seconds=seconds)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "key": self.key,
            "namespace": self.namespace,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "access_count": self.access_count,
            "last_accessed": self.last_accessed.isoformat(),
            "value_size": len(str(self.value)) if self.value else 0
        }


class CacheStrategy(ABC):
    """缓存策略抽象基类"""
    
    @abstractmethod
    def should_evict(self, entry: CacheEntry, cache_size: int, max_size: int) -> bool:
        """判断是否应该淘汰该条目"""
        pass
    
    @abstractmethod
    def get_priority(self, entry: CacheEntry) -> float:
        """获取条目优先级（用于排序，值越小优先级越高，越容易被淘汰）"""
        pass


class LRUCacheStrategy(CacheStrategy):
    """LRU (Least Recently Used) 缓存策略"""
    
    def should_evict(self, entry: CacheEntry, cache_size: int, max_size: int) -> bool:
        """缓存满时需要淘汰"""
        return cache_size >= max_size
    
    def get_priority(self, entry: CacheEntry) -> float:
        """按最后访问时间排序"""
        return entry.last_accessed.timestamp()


class LFUCacheStrategy(CacheStrategy):
    """LFU (Least Frequently Used) 缓存策略"""
    
    def should_evict(self, entry: CacheEntry, cache_size: int, max_size: int) -> bool:
        return cache_size >= max_size
    
    def get_priority(self, entry: CacheEntry) -> float:
        """按访问次数排序"""
        return entry.access_count


class TTLCacheStrategy(CacheStrategy):
    """TTL (Time To Live) 缓存策略"""
    
    def should_evict(self, entry: CacheEntry, cache_size: int, max_size: int) -> bool:
        """过期的条目需要淘汰"""
        return entry.is_expired()
    
    def get_priority(self, entry: CacheEntry) -> float:
        """按过期时间排序"""
        return entry.expires_at.timestamp()


class HybridCacheStrategy(CacheStrategy):
    """混合缓存策略（结合TTL、LRU和访问频率）"""
    
    def __init__(self, ttl_weight: float = 0.5, lru_weight: float = 0.3, lfu_weight: float = 0.2):
        self.ttl_weight = ttl_weight
        self.lru_weight = lru_weight
        self.lfu_weight = lfu_weight
    
    def should_evict(self, entry: CacheEntry, cache_size: int, max_size: int) -> bool:
        # 过期的条目立即淘汰
        if entry.is_expired():
            return True
        # 缓存满时需要淘汰
        return cache_size >= max_size
    
    def get_priority(self, entry: CacheEntry) -> float:
        """综合考虑多个因素的优先级"""
        now = datetime.now()
        
        # TTL因子（越接近过期，优先级越高/越容易被淘汰）
        ttl_factor = (entry.expires_at - now).total_seconds() / 3600.0  # 转换为小时
        
        # LRU因子（越久未访问，优先级越高）
        lru_factor = (now - entry.last_accessed).total_seconds() / 3600.0
        
        # LFU因子（访问次数越少，优先级越高）
        lfu_factor = 1.0 / (entry.access_count + 1)  # 避免除零
        
        # 综合计算优先级（值越小越容易被淘汰）
        priority = (
            self.ttl_weight * (-ttl_factor) +  # TTL越小（越接近过期）越容易被淘汰
            self.lru_weight * lru_factor +     # 越久未访问越容易被淘汰
            self.lfu_weight * lfu_factor       # 访问次数越少越容易被淘汰
        )
        
        return priority


class MetadataCache:
    """智能元数据缓存管理器"""
    
    def __init__(self, max_size: int = 1000, default_ttl: int = 3600, 
                 strategy: Optional[CacheStrategy] = None):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.strategy = strategy or HybridCacheStrategy()
        
        # 使用OrderedDict来保持插入顺序
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()  # 使用递归锁
        
        # 统计信息
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "expirations": 0,
            "total_requests": 0
        }
    
    def _generate_key(self, namespace: str, *args: Any) -> str:
        """生成缓存键"""
        key_parts = [namespace] + [str(arg) for arg in args]
        key_string = ":".join(key_parts)
        # 使用hash确保键的长度合理
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def put(self, namespace: str, value: Any, ttl: Optional[int] = None, *args: Any) -> str:
        """存储缓存条目"""
        key = self._generate_key(namespace, *args)
        ttl = ttl or self.default_ttl
        
        with self._lock:
            # 如果键已存在，更新值
            if key in self._cache:
                entry = self._cache[key]
                entry.value = value
                entry.extend_ttl(ttl)
                # 移动到末尾（最近使用）
                self._cache.move_to_end(key)
            else:
                # 创建新条目
                entry = CacheEntry(key, value, ttl, namespace)
                self._cache[key] = entry
            
            # 检查是否需要清理
            self._cleanup_if_needed()
            
            return key
    
    def get(self, namespace: str, *args: Any) -> Optional[Any]:
        """获取缓存条目"""
        key = self._generate_key(namespace, *args)
        
        with self._lock:
            self._stats["total_requests"] += 1
            
            if key not in self._cache:
                self._stats["misses"] += 1
                return None
            
            entry = self._cache[key]
            
            # 检查是否过期
            if entry.is_expired():
                del self._cache[key]
                self._stats["expirations"] += 1
                self._stats["misses"] += 1
                return None
            
            # 命中，更新统计和访问信息
            self._stats["hits"] += 1
            value = entry.access()
            
            # 移动到末尾（最近使用）
            self._cache.move_to_end(key)
            
            return value
    
    def delete(self, namespace: str, *args: Any) -> bool:
        """删除缓存条目"""
        key = self._generate_key(namespace, *args)
        
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def clear_namespace(self, namespace: str):
        """清空指定命名空间的所有缓存"""
        with self._lock:
            keys_to_delete = []
            
            # 直接使用缓存条目中存储的命名空间信息
            for key, entry in list(self._cache.items()):
                if entry.namespace == namespace:
                    keys_to_delete.append(key)
            
            # 删除匹配的条目
            deleted_count = 0
            for key in keys_to_delete:
                if key in self._cache:
                    del self._cache[key]
                    deleted_count += 1
            
            logger.debug(f"清空命名空间 '{namespace}' 的缓存: {deleted_count} 个条目")
    
    
    def clear_all(self):
        """清空所有缓存"""
        with self._lock:
            self._cache.clear()
            self._reset_stats()
    
    def _cleanup_if_needed(self):
        """必要时清理缓存"""
        # 清理过期条目
        expired_keys = []
        for key, entry in list(self._cache.items()):
            if entry.is_expired():
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._cache[key]
            self._stats["expirations"] += 1
        
        # 如果仍然超过最大大小，使用策略淘汰
        while len(self._cache) > self.max_size:
            self._evict_one()
    
    def _evict_one(self):
        """淘汰一个缓存条目"""
        if not self._cache:
            return
        
        # 根据策略计算优先级并排序
        entries_with_priority = []
        for key, entry in self._cache.items():
            priority = self.strategy.get_priority(entry)
            entries_with_priority.append((priority, key, entry))
        
        # 按优先级排序（优先级小的先淘汰）
        entries_with_priority.sort(key=lambda x: x[0])
        
        # 淘汰优先级最低的条目
        if entries_with_priority:
            _, key_to_evict, _ = entries_with_priority[0]
            del self._cache[key_to_evict]
            self._stats["evictions"] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self._lock:
            hit_rate = 0.0
            if self._stats["total_requests"] > 0:
                hit_rate = self._stats["hits"] / self._stats["total_requests"]
            
            return {
                **self._stats,
                "hit_rate": hit_rate,
                "cache_size": len(self._cache),
                "max_size": self.max_size,
                "utilization": len(self._cache) / self.max_size if self.max_size > 0 else 0.0
            }
    
    def get_cache_info(self) -> List[Dict[str, Any]]:
        """获取缓存条目信息"""
        with self._lock:
            return [entry.to_dict() for entry in self._cache.values()]
    
    def get_namespace_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取各命名空间的缓存统计"""
        with self._lock:
            namespace_stats = {}
            
            for entry in self._cache.values():
                namespace = entry.namespace or "default"
                
                if namespace not in namespace_stats:
                    namespace_stats[namespace] = {
                        "count": 0,
                        "total_access": 0,
                        "expired_count": 0,
                        "latest_access": None
                    }
                
                stats = namespace_stats[namespace]
                stats["count"] += 1
                stats["total_access"] += entry.access_count
                
                if entry.is_expired():
                    stats["expired_count"] += 1
                
                if (stats["latest_access"] is None or 
                    entry.last_accessed > stats["latest_access"]):
                    stats["latest_access"] = entry.last_accessed
            
            # 转换datetime为字符串
            for stats in namespace_stats.values():
                if stats["latest_access"]:
                    stats["latest_access"] = stats["latest_access"].isoformat()
            
            return namespace_stats
    
    def _reset_stats(self):
        """重置统计信息"""
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "expirations": 0,
            "total_requests": 0
        }
    
    def optimize(self):
        """优化缓存（清理过期条目，整理内存）"""
        with self._lock:
            # 清理过期条目
            self._cleanup_if_needed()
            
            # 重新整理缓存（按访问时间排序）
            sorted_items = sorted(
                self._cache.items(),
                key=lambda x: x[1].last_accessed,
                reverse=True
            )
            
            # 重建缓存
            self._cache.clear()
            for key, entry in sorted_items:
                self._cache[key] = entry


class MultiLevelMetadataCache:
    """多级元数据缓存"""
    
    def __init__(self):
        # L1: 实例级缓存（小容量，低TTL，快速访问）
        self.l1_cache = MetadataCache(
            max_size=100,
            default_ttl=300,  # 5分钟
            strategy=LRUCacheStrategy()
        )
        
        # L2: 数据库级缓存（中等容量，中等TTL）
        self.l2_cache = MetadataCache(
            max_size=500,
            default_ttl=1800,  # 30分钟
            strategy=HybridCacheStrategy()
        )
        
        # L3: 集合级缓存（大容量，长TTL）
        self.l3_cache = MetadataCache(
            max_size=2000,
            default_ttl=3600,  # 1小时
            strategy=HybridCacheStrategy()
        )
    
    def get_instance_cache(self) -> MetadataCache:
        """获取实例级缓存"""
        return self.l1_cache
    
    def get_database_cache(self) -> MetadataCache:
        """获取数据库级缓存"""
        return self.l2_cache
    
    def get_collection_cache(self) -> MetadataCache:
        """获取集合级缓存"""
        return self.l3_cache
    
    def clear_instance_cache(self, instance_name: str):
        """清理指定实例的所有缓存"""
        # 清理实例级缓存
        self.l1_cache.clear_namespace("instance")
        
        # 清理包含该实例的数据库级和集合级缓存
        self._clear_instance_related_cache(self.l2_cache, instance_name)
        self._clear_instance_related_cache(self.l3_cache, instance_name)
    
    def _clear_instance_related_cache(self, cache: MetadataCache, instance_name: str):
        """清理与指定实例相关的缓存条目"""
        with cache._lock:
            keys_to_delete = []
            
            for key, entry in list(cache._cache.items()):
                # 检查缓存条目的值是否包含该实例
                if self._cache_belongs_to_instance(entry.value, instance_name):
                    keys_to_delete.append(key)
            
            # 删除相关条目
            for key in keys_to_delete:
                if key in cache._cache:
                    del cache._cache[key]
    
    def _cache_belongs_to_instance(self, cache_value: Any, instance_name: str) -> bool:
        """检查缓存值是否属于指定实例"""
        if isinstance(cache_value, dict):
            # 检查常见的实例名称字段
            instance_fields = ["instance_name", "instance", "name"]
            for field in instance_fields:
                if cache_value.get(field) == instance_name:
                    return True
        return False
    
    def get_overall_stats(self) -> Dict[str, Any]:
        """获取整体缓存统计"""
        l1_stats = self.l1_cache.get_stats()
        l2_stats = self.l2_cache.get_stats()
        l3_stats = self.l3_cache.get_stats()
        
        return {
            "l1_cache": l1_stats,
            "l2_cache": l2_stats,
            "l3_cache": l3_stats,
            "total_hits": l1_stats["hits"] + l2_stats["hits"] + l3_stats["hits"],
            "total_misses": l1_stats["misses"] + l2_stats["misses"] + l3_stats["misses"],
            "total_size": l1_stats["cache_size"] + l2_stats["cache_size"] + l3_stats["cache_size"],
            "overall_hit_rate": (
                (l1_stats["hits"] + l2_stats["hits"] + l3_stats["hits"]) /
                max(1, l1_stats["total_requests"] + l2_stats["total_requests"] + l3_stats["total_requests"])
            )
        }
    
    def optimize_all(self):
        """优化所有级别的缓存"""
        self.l1_cache.optimize()
        self.l2_cache.optimize()
        self.l3_cache.optimize()


# 全局缓存实例
_global_cache_instance = None


def get_metadata_cache() -> MultiLevelMetadataCache:
    """获取全局元数据缓存实例"""
    global _global_cache_instance
    if _global_cache_instance is None:
        _global_cache_instance = MultiLevelMetadataCache()
    return _global_cache_instance


def reset_metadata_cache():
    """重置全局缓存（主要用于测试）"""
    global _global_cache_instance
    _global_cache_instance = None