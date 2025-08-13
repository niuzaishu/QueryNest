# -*- coding: utf-8 -*-
"""
元数据扫描器 - 负责扫描数据库结构信息
"""

from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import asyncio
import structlog
from abc import ABC, abstractmethod

from database.connection_manager import ConnectionManager

logger = structlog.get_logger(__name__)


class ScanResult:
    """扫描结果封装"""
    
    def __init__(self, instance_name: str, success: bool, error: Optional[str] = None):
        self.instance_name = instance_name
        self.success = success
        self.error = error
        self.scan_time = datetime.now()
        self.databases: List[Dict[str, Any]] = []
        self.collections: List[Dict[str, Any]] = []
        self.metadata_count = 0
    
    def add_database(self, database_info: Dict[str, Any]):
        """添加数据库信息"""
        self.databases.append(database_info)
    
    def add_collection(self, collection_info: Dict[str, Any]):
        """添加集合信息"""
        self.collections.append(collection_info)
        self.metadata_count += 1


class ScanStrategy(ABC):
    """扫描策略抽象基类"""
    
    @abstractmethod
    async def scan_instance(self, instance_name: str, connection_manager: ConnectionManager) -> ScanResult:
        """扫描实例"""
        pass
    
    @abstractmethod
    def get_strategy_name(self) -> str:
        """获取策略名称"""
        pass


class FullScanStrategy(ScanStrategy):
    """全量扫描策略"""
    
    def __init__(self, sample_size: int = 100, max_field_depth: int = 5):
        self.sample_size = sample_size
        self.max_field_depth = max_field_depth
    
    async def scan_instance(self, instance_name: str, connection_manager: ConnectionManager) -> ScanResult:
        """执行全量扫描"""
        result = ScanResult(instance_name, False)
        
        try:
            # 获取实例连接
            instance_connection = connection_manager.get_instance_connection(instance_name)
            if not instance_connection or not instance_connection.client:
                result.error = f"无法获取实例 {instance_name} 的连接"
                return result
            
            client = instance_connection.client
            
            # 扫描所有数据库
            database_names = await client.list_database_names()
            
            for db_name in database_names:
                # 跳过系统数据库
                if self._should_skip_database(db_name):
                    continue
                
                try:
                    db_info = await self._scan_database(client[db_name], db_name)
                    result.add_database(db_info)
                    
                    # 扫描数据库中的集合
                    collection_results = await self._scan_database_collections(client[db_name], db_name)
                    for collection_info in collection_results:
                        result.add_collection(collection_info)
                
                except Exception as e:
                    logger.warning(f"扫描数据库 {db_name} 失败: {e}")
                    continue
            
            result.success = True
            logger.info(f"全量扫描完成: {instance_name}, 发现 {len(result.databases)} 个数据库, {len(result.collections)} 个集合")
            
        except Exception as e:
            result.error = str(e)
            logger.error(f"全量扫描实例 {instance_name} 失败: {e}")
        
        return result
    
    async def _scan_database(self, db, db_name: str) -> Dict[str, Any]:
        """扫描数据库信息"""
        try:
            stats = await db.command("dbStats")
            return {
                "name": db_name,
                "size_on_disk": stats.get("dataSize", 0),
                "collection_count": stats.get("collections", 0),
                "index_count": stats.get("indexes", 0),
                "scanned_at": datetime.now()
            }
        except Exception as e:
            logger.warning(f"获取数据库 {db_name} 统计信息失败: {e}")
            return {
                "name": db_name,
                "size_on_disk": 0,
                "collection_count": 0,
                "index_count": 0,
                "scanned_at": datetime.now(),
                "error": str(e)
            }
    
    async def _scan_database_collections(self, db, db_name: str) -> List[Dict[str, Any]]:
        """扫描数据库中的所有集合"""
        collections = []
        
        try:
            collection_names = await db.list_collection_names()
            
            for coll_name in collection_names:
                if self._should_skip_collection(coll_name):
                    continue
                
                try:
                    collection_info = await self._scan_collection(db[coll_name], db_name, coll_name)
                    collections.append(collection_info)
                except Exception as e:
                    logger.warning(f"扫描集合 {coll_name} 失败: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"获取数据库 {db_name} 的集合列表失败: {e}")
        
        return collections
    
    async def _scan_collection(self, collection, db_name: str, coll_name: str) -> Dict[str, Any]:
        """扫描集合信息和结构"""
        try:
            # 获取集合统计信息
            stats = await collection.stats()
            document_count = stats.get("count", 0)
            
            # 获取索引信息
            indexes = []
            try:
                async for index in collection.list_indexes():
                    indexes.append({
                        "name": index.get("name"),
                        "key": index.get("key"),
                        "unique": index.get("unique", False)
                    })
            except Exception as e:
                logger.warning(f"获取集合 {coll_name} 索引信息失败: {e}")
            
            # 采样文档分析字段结构
            field_analysis = await self._analyze_collection_fields(collection, coll_name)
            
            return {
                "database": db_name,
                "name": coll_name,
                "document_count": document_count,
                "average_size": stats.get("avgObjSize", 0),
                "total_size": stats.get("size", 0),
                "indexes": indexes,
                "fields": field_analysis,
                "scanned_at": datetime.now()
            }
            
        except Exception as e:
            logger.error(f"扫描集合 {db_name}.{coll_name} 失败: {e}")
            return {
                "database": db_name,
                "name": coll_name,
                "document_count": 0,
                "error": str(e),
                "scanned_at": datetime.now()
            }
    
    async def _analyze_collection_fields(self, collection, coll_name: str) -> Dict[str, Any]:
        """分析集合字段结构"""
        field_stats = {}
        sample_count = 0
        
        try:
            # 采样文档
            pipeline = [{"$sample": {"size": self.sample_size}}]
            
            async for doc in collection.aggregate(pipeline):
                sample_count += 1
                self._analyze_document_fields(doc, field_stats, "", 0)
            
            # 计算字段出现频率和类型分布
            total_samples = max(sample_count, 1)
            for field_path, field_info in field_stats.items():
                field_info["frequency"] = field_info["count"] / total_samples
                # 确定主要类型（出现最多的类型）
                if field_info["types"]:
                    field_info["primary_type"] = max(field_info["types"], key=field_info["types"].get)
        
        except Exception as e:
            logger.warning(f"分析集合 {coll_name} 字段结构失败: {e}")
        
        return {
            "sample_count": sample_count,
            "fields": field_stats
        }
    
    def _analyze_document_fields(self, doc: Dict[str, Any], field_stats: Dict[str, Any], 
                                prefix: str, depth: int):
        """递归分析文档字段"""
        if depth >= self.max_field_depth:
            return
        
        for key, value in doc.items():
            if isinstance(key, str):  # 确保键是字符串
                field_path = f"{prefix}.{key}" if prefix else key
                
                # 初始化字段统计
                if field_path not in field_stats:
                    field_stats[field_path] = {
                        "count": 0,
                        "types": {},
                        "examples": []
                    }
                
                field_info = field_stats[field_path]
                field_info["count"] += 1
                
                # 记录类型
                value_type = type(value).__name__
                if value_type not in field_info["types"]:
                    field_info["types"][value_type] = 0
                field_info["types"][value_type] += 1
                
                # 记录示例值（最多5个）
                if len(field_info["examples"]) < 5:
                    if value_type in ['str', 'int', 'float', 'bool']:
                        field_info["examples"].append(value)
                    elif value_type == 'ObjectId':
                        field_info["examples"].append(str(value))
                
                # 递归处理嵌套文档
                if isinstance(value, dict) and depth < self.max_field_depth - 1:
                    self._analyze_document_fields(value, field_stats, field_path, depth + 1)
    
    def _should_skip_database(self, db_name: str) -> bool:
        """判断是否应该跳过数据库"""
        skip_patterns = ["admin", "local", "config", "test"]
        return db_name.lower() in skip_patterns
    
    def _should_skip_collection(self, coll_name: str) -> bool:
        """判断是否应该跳过集合"""
        return coll_name.startswith("system.") or coll_name.startswith("__")
    
    def get_strategy_name(self) -> str:
        return "full_scan"


class IncrementalScanStrategy(ScanStrategy):
    """增量扫描策略"""
    
    def __init__(self, last_scan_times: Optional[Dict[str, datetime]] = None):
        self.last_scan_times = last_scan_times or {}
    
    async def scan_instance(self, instance_name: str, connection_manager: ConnectionManager) -> ScanResult:
        """执行增量扫描"""
        result = ScanResult(instance_name, False)
        
        try:
            # 获取上次扫描时间
            last_scan_time = self.last_scan_times.get(instance_name)
            if not last_scan_time:
                # 如果没有上次扫描记录，回退到全量扫描
                logger.info(f"实例 {instance_name} 无上次扫描记录，执行全量扫描")
                full_strategy = FullScanStrategy()
                return await full_strategy.scan_instance(instance_name, connection_manager)
            
            # 获取实例连接
            instance_connection = connection_manager.get_instance_connection(instance_name)
            if not instance_connection or not instance_connection.client:
                result.error = f"无法获取实例 {instance_name} 的连接"
                return result
            
            client = instance_connection.client
            
            # 检查是否有新的数据库或集合
            current_databases = await client.list_database_names()
            changes_detected = False
            
            for db_name in current_databases:
                if self._should_skip_database(db_name):
                    continue
                
                try:
                    # 检查数据库是否有变化
                    db_changed = await self._check_database_changes(client[db_name], db_name, last_scan_time)
                    if db_changed:
                        changes_detected = True
                        # 重新扫描变化的数据库
                        db_info = await self._scan_database_quick(client[db_name], db_name)
                        result.add_database(db_info)
                
                except Exception as e:
                    logger.warning(f"增量扫描数据库 {db_name} 失败: {e}")
                    continue
            
            result.success = True
            if changes_detected:
                logger.info(f"增量扫描完成: {instance_name}, 检测到变化")
            else:
                logger.info(f"增量扫描完成: {instance_name}, 无变化")
            
        except Exception as e:
            result.error = str(e)
            logger.error(f"增量扫描实例 {instance_name} 失败: {e}")
        
        return result
    
    async def _check_database_changes(self, db, db_name: str, since: datetime) -> bool:
        """检查数据库自指定时间以来是否有变化"""
        try:
            # 简单的启发式检查：比较集合数量
            current_collections = await db.list_collection_names()
            # 在实际实现中，可以维护一个集合变更时间戳的索引
            # 这里简化为检查集合数量变化
            return True  # 简化实现，总是认为有变化
            
        except Exception as e:
            logger.warning(f"检查数据库 {db_name} 变化失败: {e}")
            return True  # 出错时假设有变化
    
    async def _scan_database_quick(self, db, db_name: str) -> Dict[str, Any]:
        """快速扫描数据库信息（增量扫描用）"""
        try:
            stats = await db.command("dbStats")
            return {
                "name": db_name,
                "collection_count": stats.get("collections", 0),
                "scanned_at": datetime.now(),
                "scan_type": "incremental"
            }
        except Exception as e:
            return {
                "name": db_name,
                "error": str(e),
                "scanned_at": datetime.now(),
                "scan_type": "incremental"
            }
    
    def _should_skip_database(self, db_name: str) -> bool:
        """判断是否应该跳过数据库"""
        skip_patterns = ["admin", "local", "config", "test"]
        return db_name.lower() in skip_patterns
    
    def get_strategy_name(self) -> str:
        return "incremental_scan"


class MetadataScanner:
    """元数据扫描器 - 统一管理不同扫描策略"""
    
    def __init__(self, connection_manager: ConnectionManager):
        self.connection_manager = connection_manager
        self.last_scan_times: Dict[str, datetime] = {}
        self._scan_stats = {
            'total_scans': 0,
            'full_scans': 0,
            'incremental_scans': 0,
            'successful_scans': 0,
            'failed_scans': 0
        }
        self._lock = asyncio.Lock()
    
    async def scan_all_instances(self, force_full_scan: bool = False) -> List[ScanResult]:
        """扫描所有实例的元数据"""
        async with self._lock:
            instance_names = self.connection_manager.get_instance_names()
            scan_tasks = []
            
            for instance_name in instance_names:
                strategy = self._select_scan_strategy(instance_name, force_full_scan)
                task = self._scan_instance_with_strategy(instance_name, strategy)
                scan_tasks.append(task)
            
            # 并发执行扫描
            results = await asyncio.gather(*scan_tasks, return_exceptions=True)
            
            # 处理结果
            scan_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    instance_name = instance_names[i]
                    error_result = ScanResult(instance_name, False, str(result))
                    scan_results.append(error_result)
                    self._scan_stats['failed_scans'] += 1
                else:
                    scan_results.append(result)
                    if result.success:
                        self._scan_stats['successful_scans'] += 1
                        # 更新最后扫描时间
                        self.last_scan_times[result.instance_name] = result.scan_time
                    else:
                        self._scan_stats['failed_scans'] += 1
            
            self._scan_stats['total_scans'] += len(scan_results)
            
            logger.info(f"批量扫描完成: {len(scan_results)} 个实例, " +
                       f"{self._scan_stats['successful_scans']} 成功, " +
                       f"{self._scan_stats['failed_scans']} 失败")
            
            return scan_results
    
    async def scan_instance(self, instance_name: str, force_full_scan: bool = False) -> ScanResult:
        """扫描指定实例"""
        async with self._lock:
            strategy = self._select_scan_strategy(instance_name, force_full_scan)
            result = await self._scan_instance_with_strategy(instance_name, strategy)
            
            self._scan_stats['total_scans'] += 1
            if result.success:
                self._scan_stats['successful_scans'] += 1
                self.last_scan_times[instance_name] = result.scan_time
            else:
                self._scan_stats['failed_scans'] += 1
            
            return result
    
    def _select_scan_strategy(self, instance_name: str, force_full_scan: bool) -> ScanStrategy:
        """选择扫描策略"""
        if force_full_scan or self._should_perform_full_scan(instance_name):
            self._scan_stats['full_scans'] += 1
            return FullScanStrategy()
        else:
            self._scan_stats['incremental_scans'] += 1
            return IncrementalScanStrategy(self.last_scan_times)
    
    def _should_perform_full_scan(self, instance_name: str) -> bool:
        """判断是否应该执行全量扫描"""
        last_scan = self.last_scan_times.get(instance_name)
        if not last_scan:
            return True
        
        # 如果距离上次扫描超过24小时，执行全量扫描
        time_diff = datetime.now() - last_scan
        return time_diff.total_seconds() > 86400  # 24小时
    
    async def _scan_instance_with_strategy(self, instance_name: str, strategy: ScanStrategy) -> ScanResult:
        """使用指定策略扫描实例"""
        logger.info(f"开始扫描实例 {instance_name}, 策略: {strategy.get_strategy_name()}")
        result = await strategy.scan_instance(instance_name, self.connection_manager)
        
        if result.success:
            logger.info(f"扫描实例 {instance_name} 成功: {result.metadata_count} 项元数据")
        else:
            logger.error(f"扫描实例 {instance_name} 失败: {result.error}")
        
        return result
    
    def get_scan_statistics(self) -> Dict[str, Any]:
        """获取扫描统计信息"""
        return {
            **self._scan_stats,
            "last_scan_times": {
                instance: scan_time.isoformat() 
                for instance, scan_time in self.last_scan_times.items()
            }
        }
    
    def reset_statistics(self):
        """重置扫描统计"""
        self._scan_stats = {
            'total_scans': 0,
            'full_scans': 0,
            'incremental_scans': 0,
            'successful_scans': 0,
            'failed_scans': 0
        }