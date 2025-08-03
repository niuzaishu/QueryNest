"""集成测试基础类"""
import asyncio
import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Dict, Any, List

from .test_config import TEST_DB_CONFIG, TEST_DATA, TEST_INDEXES, TEST_INSTANCE_CONFIG
from src.database.connection_manager import ConnectionManager
from src.database.metadata_manager import MetadataManager
from src.scanner.semantic_analyzer import SemanticAnalyzer
from src.config import QueryNestConfig


class BaseIntegrationTest:
    """集成测试基础类"""
    
    @classmethod
    def setup_class(cls):
        """类级别的设置"""
        # 这个方法会在pytest中自动调用
        pass
    
    @classmethod
    def teardown_class(cls):
        """类级别的清理"""
        # 这个方法会在pytest中自动调用
        pass
    
    async def setup_integration_test(self):
        """设置集成测试环境"""
        # 创建数据库连接
        self.client = AsyncIOMotorClient(
            host=TEST_DB_CONFIG["host"],
            port=TEST_DB_CONFIG["port"]
        )
        self.db = self.client[TEST_DB_CONFIG["database"]]
        
        # 初始化组件
        from src.config import MongoInstanceConfig, MetadataConfig
        self.config = QueryNestConfig(
            mongo_instances={
                TEST_INSTANCE_CONFIG["instance_id"]: MongoInstanceConfig(
                    name=TEST_INSTANCE_CONFIG["instance_id"],
                    connection_string=f"mongodb://{TEST_INSTANCE_CONFIG['host']}:{TEST_INSTANCE_CONFIG['port']}",
                    environment="test",
                    description="测试实例",
                    status="active"
                )
            },
            metadata=MetadataConfig(database="querynest_test_metadata")
        )
        self.connection_manager = ConnectionManager(self.config)
        self.metadata_manager = MetadataManager(self.connection_manager)
        self.semantic_analyzer = SemanticAnalyzer(self.metadata_manager)
        
        # 初始化连接管理器
        await self.connection_manager.initialize()
    
    async def teardown_integration_test(self):
        """清理集成测试环境"""
        # 清理
        await self.cleanup_database()
        await self.connection_manager.shutdown()
        self.client.close()
    
    async def async_setup_method(self):
        """异步方法级别的设置"""
        # 设置集成测试环境
        await self.setup_integration_test()
        # 清理并重新插入测试数据
        await self.cleanup_database()
        await self.insert_test_data()
        await self.create_test_indexes()

    async def async_teardown_method(self):
        """异步方法级别的清理"""
        # 方法执行后清理
        await self.cleanup_database()
        await self.teardown_integration_test()
    
    async def cleanup_database(self):
        """清理测试数据库"""
        try:
            # 删除所有集合
            collections = await self.db.list_collection_names()
            for collection_name in collections:
                await self.db.drop_collection(collection_name)
        except Exception as e:
            print(f"清理数据库时出错: {e}")
    
    async def insert_test_data(self):
        """插入测试数据"""
        try:
            for collection_name, documents in TEST_DATA.items():
                collection = self.db[collection_name]
                if documents:
                    await collection.insert_many(documents)
                    print(f"已插入 {len(documents)} 条数据到 {collection_name} 集合")
        except Exception as e:
            print(f"插入测试数据时出错: {e}")
            raise
    
    async def create_test_indexes(self):
        """创建测试索引"""
        try:
            for collection_name, indexes in TEST_INDEXES.items():
                collection = self.db[collection_name]
                for index_spec in indexes:
                    await collection.create_index(
                        index_spec["keys"],
                        unique=index_spec.get("unique", False)
                    )
                print(f"已为 {collection_name} 集合创建 {len(indexes)} 个索引")
        except Exception as e:
            print(f"创建测试索引时出错: {e}")
            raise
    
    async def get_collection_count(self, collection_name: str) -> int:
        """获取集合文档数量"""
        return await self.db[collection_name].count_documents({})
    
    async def verify_data_exists(self) -> bool:
        """验证测试数据是否存在"""
        try:
            for collection_name, expected_data in TEST_DATA.items():
                count = await self.get_collection_count(collection_name)
                if count != len(expected_data):
                    return False
            return True
        except Exception:
            return False