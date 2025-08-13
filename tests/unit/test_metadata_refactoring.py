# -*- coding: utf-8 -*-
"""
元数据管理器重构测试
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timedelta

from database.metadata_scanner import MetadataScanner, FullScanStrategy, IncrementalScanStrategy, ScanResult
from database.metadata_storage import MongoMetadataStorage, FileMetadataStorage
from database.metadata_cache import MetadataCache, LRUCacheStrategy, MultiLevelMetadataCache
from database.metadata_manager_refactored import MetadataManagerRefactored, MetadataManagerFactory


class TestMetadataScanner:
    """元数据扫描器测试"""
    
    def setup_method(self):
        """测试前准备"""
        self.mock_connection_manager = MagicMock()
        self.scanner = MetadataScanner(self.mock_connection_manager)
    
    def test_scanner_initialization(self):
        """测试扫描器初始化"""
        assert self.scanner.connection_manager is self.mock_connection_manager
        assert len(self.scanner.last_scan_times) == 0
        assert self.scanner._scan_stats['total_scans'] == 0
    
    def test_should_perform_full_scan(self):
        """测试全量扫描判断逻辑"""
        instance_name = "test_instance"
        
        # 没有扫描记录时应该执行全量扫描
        assert self.scanner._should_perform_full_scan(instance_name) is True
        
        # 最近扫描过的不需要全量扫描
        self.scanner.last_scan_times[instance_name] = datetime.now()
        assert self.scanner._should_perform_full_scan(instance_name) is False
        
        # 超过24小时的需要全量扫描
        self.scanner.last_scan_times[instance_name] = datetime.now() - timedelta(hours=25)
        assert self.scanner._should_perform_full_scan(instance_name) is True
    
    def test_scan_statistics(self):
        """测试扫描统计功能"""
        stats = self.scanner.get_scan_statistics()
        
        assert "total_scans" in stats
        assert "full_scans" in stats
        assert "incremental_scans" in stats
        assert "successful_scans" in stats
        assert "last_scan_times" in stats
        
        # 重置统计
        self.scanner.reset_statistics()
        stats = self.scanner.get_scan_statistics()
        assert stats["total_scans"] == 0


class TestScanStrategies:
    """扫描策略测试"""
    
    def test_full_scan_strategy(self):
        """测试全量扫描策略"""
        strategy = FullScanStrategy(sample_size=10, max_field_depth=3)
        
        assert strategy.get_strategy_name() == "full_scan"
        assert strategy.sample_size == 10
        assert strategy.max_field_depth == 3
        
        # 测试数据库跳过逻辑
        assert strategy._should_skip_database("admin") is True
        assert strategy._should_skip_database("test") is True
        assert strategy._should_skip_database("myapp") is False
        
        # 测试集合跳过逻辑
        assert strategy._should_skip_collection("system.users") is True
        assert strategy._should_skip_collection("__temp") is True
        assert strategy._should_skip_collection("users") is False
    
    def test_incremental_scan_strategy(self):
        """测试增量扫描策略"""
        last_scan_times = {"instance1": datetime.now()}
        strategy = IncrementalScanStrategy(last_scan_times)
        
        assert strategy.get_strategy_name() == "incremental_scan"
        assert "instance1" in strategy.last_scan_times


class TestMetadataCache:
    """元数据缓存测试"""
    
    def setup_method(self):
        """测试前准备"""
        self.cache = MetadataCache(max_size=5, default_ttl=10)
    
    def test_cache_basic_operations(self):
        """测试缓存基本操作"""
        # 存储和获取
        key = self.cache.put("test", "value1", None, "key1")
        assert key is not None
        
        value = self.cache.get("test", "key1")
        assert value == "value1"
        
        # 获取不存在的键
        value = self.cache.get("test", "nonexistent")
        assert value is None
        
        # 删除
        success = self.cache.delete("test", "key1")
        assert success is True
        
        value = self.cache.get("test", "key1")
        assert value is None
    
    def test_cache_ttl(self):
        """测试缓存TTL功能"""
        # 短TTL缓存
        cache = MetadataCache(max_size=10, default_ttl=1)
        cache.put("test", "value1", None, "key1")
        
        # 立即获取应该成功
        value = cache.get("test", "key1")
        assert value == "value1"
        
        # 等待过期后获取应该失败
        import time
        time.sleep(1.1)
        value = cache.get("test", "key1")
        assert value is None
    
    def test_cache_eviction(self):
        """测试缓存淘汰策略"""
        # 填满缓存
        for i in range(5):
            self.cache.put("test", f"value{i}", None, f"key{i}")
        
        # 添加第6个条目，应该触发淘汰
        self.cache.put("test", "value5", None, "key5")
        
        stats = self.cache.get_stats()
        assert stats["cache_size"] == 5  # 应该保持最大大小
        assert stats["evictions"] > 0   # 应该有淘汰发生
    
    def test_cache_statistics(self):
        """测试缓存统计功能"""
        # 添加一些数据
        self.cache.put("test", "value1", None, "key1")
        self.cache.get("test", "key1")  # 命中
        self.cache.get("test", "nonexistent")  # 未命中
        
        stats = self.cache.get_stats()
        
        assert stats["hits"] >= 1
        assert stats["misses"] >= 1
        assert stats["total_requests"] >= 2
        assert stats["hit_rate"] > 0
        assert stats["cache_size"] >= 1
    
    def test_cache_namespaces(self):
        """测试缓存命名空间"""
        # 添加不同命名空间的数据
        self.cache.put("namespace1", "value1", None, "key1")
        self.cache.put("namespace2", "value2", None, "key1")
        
        # 获取数据
        value1 = self.cache.get("namespace1", "key1")
        value2 = self.cache.get("namespace2", "key1")
        
        assert value1 == "value1"
        assert value2 == "value2"
        
        # 清空一个命名空间
        self.cache.clear_namespace("namespace1")
        
        value1 = self.cache.get("namespace1", "key1")
        value2 = self.cache.get("namespace2", "key1")
        
        assert value1 is None
        assert value2 == "value2"
    
    def test_namespace_statistics(self):
        """测试命名空间统计功能"""
        # 添加不同命名空间的数据
        self.cache.put("ns1", "value1", None, "key1")
        self.cache.put("ns1", "value2", None, "key2")
        self.cache.put("ns2", "value3", None, "key1")
        
        # 访问一些数据增加访问计数
        self.cache.get("ns1", "key1")
        self.cache.get("ns1", "key1")
        self.cache.get("ns2", "key1")
        
        # 获取命名空间统计
        ns_stats = self.cache.get_namespace_stats()
        
        assert "ns1" in ns_stats
        assert "ns2" in ns_stats
        assert ns_stats["ns1"]["count"] == 2
        assert ns_stats["ns2"]["count"] == 1
        assert ns_stats["ns1"]["total_access"] >= 2  # key1被访问了2次
        assert ns_stats["ns2"]["total_access"] >= 1


class TestMultiLevelCache:
    """多级缓存测试"""
    
    def setup_method(self):
        """测试前准备"""
        self.cache = MultiLevelMetadataCache()
    
    def test_multilevel_cache_structure(self):
        """测试多级缓存结构"""
        l1 = self.cache.get_instance_cache()
        l2 = self.cache.get_database_cache()
        l3 = self.cache.get_collection_cache()
        
        assert l1.max_size == 100
        assert l2.max_size == 500
        assert l3.max_size == 2000
        
        assert l1.default_ttl == 300   # 5分钟
        assert l2.default_ttl == 1800  # 30分钟
        assert l3.default_ttl == 3600  # 1小时
    
    def test_multilevel_cache_operations(self):
        """测试多级缓存操作"""
        # 在不同级别存储数据（使用包含实例信息的数据结构）
        inst_data = {"name": "inst1", "type": "instance"}
        db_data = {"instance_name": "inst1", "name": "db1", "type": "database"}
        coll_data = {"instance_name": "inst1", "database": "db1", "name": "coll1", "type": "collection"}
        
        self.cache.get_instance_cache().put("instance", inst_data, None, "inst1")
        self.cache.get_database_cache().put("database", db_data, None, "inst1", "db1")
        self.cache.get_collection_cache().put("collection", coll_data, None, "inst1", "db1", "coll1")
        
        # 验证数据存在
        assert self.cache.get_instance_cache().get("instance", "inst1") == inst_data
        assert self.cache.get_database_cache().get("database", "inst1", "db1") == db_data
        assert self.cache.get_collection_cache().get("collection", "inst1", "db1", "coll1") == coll_data
        
        # 清理实例缓存
        self.cache.clear_instance_cache("inst1")
        
        # 验证相关缓存被清理
        assert self.cache.get_instance_cache().get("instance", "inst1") is None
        assert self.cache.get_database_cache().get("database", "inst1", "db1") is None
        assert self.cache.get_collection_cache().get("collection", "inst1", "db1", "coll1") is None
    
    def test_overall_statistics(self):
        """测试整体统计功能"""
        # 添加一些操作
        self.cache.get_instance_cache().put("instance", "data", None, "key")
        self.cache.get_instance_cache().get("instance", "key")
        
        stats = self.cache.get_overall_stats()
        
        assert "l1_cache" in stats
        assert "l2_cache" in stats
        assert "l3_cache" in stats
        assert "total_hits" in stats
        assert "total_misses" in stats
        assert "overall_hit_rate" in stats


class TestMetadataStorage:
    """元数据存储测试"""
    
    def setup_method(self):
        """测试前准备"""
        self.mock_connection_manager = MagicMock()
    
    def test_file_storage_initialization(self):
        """测试文件存储初始化"""
        storage = FileMetadataStorage("./test_storage")
        assert storage.storage_path == "./test_storage"
    
    @pytest.mark.asyncio
    async def test_file_storage_operations(self):
        """测试文件存储操作"""
        import tempfile
        import os
        
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = FileMetadataStorage(temp_dir)
            
            # 创建测试扫描结果
            scan_result = ScanResult("test_instance", True)
            scan_result.add_database({"name": "test_db", "collection_count": 5})
            scan_result.add_collection({"database": "test_db", "name": "test_coll", "document_count": 100})
            
            # 存储和获取
            success = await storage.store_scan_result(scan_result)
            assert success is True
            
            metadata = await storage.get_instance_metadata("test_instance")
            assert metadata is not None
            assert metadata["instance_name"] == "test_instance"
            assert metadata["success"] is True
            
            # 验证文件存在
            instance_dir = os.path.join(temp_dir, "test_instance")
            assert os.path.exists(instance_dir)
            assert os.path.exists(os.path.join(instance_dir, "latest.json"))


class TestMetadataManagerRefactored:
    """重构后的元数据管理器测试"""
    
    def setup_method(self):
        """测试前准备"""
        self.mock_connection_manager = MagicMock()
        self.mock_storage = AsyncMock()
        self.manager = MetadataManagerRefactored(
            self.mock_connection_manager, 
            self.mock_storage
        )
    
    def test_manager_initialization(self):
        """测试管理器初始化"""
        assert self.manager.connection_manager is self.mock_connection_manager
        assert self.manager.storage is self.mock_storage
        assert self.manager.scanner is not None
        assert self.manager.cache is not None
    
    @pytest.mark.asyncio
    async def test_get_instance_metadata_with_cache(self):
        """测试带缓存的实例元数据获取"""
        # 模拟存储返回数据
        test_metadata = {"name": "test_instance", "database_count": 5}
        self.mock_storage.get_instance_metadata.return_value = test_metadata
        
        # 第一次调用应该从存储获取并缓存
        result1 = await self.manager.get_instance_metadata("test_instance")
        assert result1 == test_metadata
        assert self.mock_storage.get_instance_metadata.call_count == 1
        
        # 第二次调用应该从缓存获取
        result2 = await self.manager.get_instance_metadata("test_instance")
        assert result2 == test_metadata
        # 存储不应该被再次调用
        assert self.mock_storage.get_instance_metadata.call_count == 1
    
    @pytest.mark.asyncio
    async def test_scan_instance(self):
        """测试实例扫描"""
        # 模拟扫描成功
        with patch.object(self.manager.scanner, 'scan_instance') as mock_scan:
            mock_result = ScanResult("test_instance", True)
            mock_scan.return_value = mock_result
            self.mock_storage.store_scan_result.return_value = True
            
            result = await self.manager.scan_instance("test_instance")
            
            assert result is True
            mock_scan.assert_called_once()
            self.mock_storage.store_scan_result.assert_called_once_with(mock_result)
    
    @pytest.mark.asyncio
    async def test_health_check(self):
        """测试健康检查"""
        self.mock_storage.list_instances.return_value = ["instance1", "instance2"]
        
        health = await self.manager.health_check()
        
        assert "status" in health
        assert "components" in health
        assert "timestamp" in health
        assert "scanner" in health["components"]
        assert "cache" in health["components"]
        assert "storage" in health["components"]
    
    def test_get_manager_statistics(self):
        """测试管理器统计"""
        stats = self.manager.get_manager_statistics()
        
        assert "total_operations" in stats
        assert "cache_hits" in stats
        assert "storage_hits" in stats
        assert "scanner_stats" in stats
        assert "cache_stats" in stats


class TestMetadataManagerFactory:
    """元数据管理器工厂测试"""
    
    def setup_method(self):
        """测试前准备"""
        self.mock_connection_manager = MagicMock()
    
    def test_create_mongo_manager(self):
        """测试创建MongoDB管理器"""
        manager = MetadataManagerFactory.create_manager(
            self.mock_connection_manager, "mongo"
        )
        
        assert isinstance(manager, MetadataManagerRefactored)
        assert isinstance(manager.storage, MongoMetadataStorage)
    
    def test_create_file_manager(self):
        """测试创建文件管理器"""
        manager = MetadataManagerFactory.create_manager(
            self.mock_connection_manager, "file"
        )
        
        assert isinstance(manager, MetadataManagerRefactored)
        assert isinstance(manager.storage, FileMetadataStorage)
    
    def test_create_test_manager(self):
        """测试创建测试管理器"""
        manager = MetadataManagerFactory.create_test_manager(self.mock_connection_manager)
        
        assert isinstance(manager, MetadataManagerRefactored)
        assert isinstance(manager.storage, FileMetadataStorage)
    
    def test_invalid_storage_type(self):
        """测试无效存储类型"""
        with pytest.raises(ValueError, match="不支持的存储类型"):
            MetadataManagerFactory.create_manager(
                self.mock_connection_manager, "invalid"
            )