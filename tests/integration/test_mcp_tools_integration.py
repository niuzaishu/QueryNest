"""MCP工具集成测试"""
import pytest
import asyncio
from mcp.types import TextContent

from .base_integration_test import BaseIntegrationTest
from .test_config import TEST_INSTANCE_CONFIG, TEST_DATA
import sys
from pathlib import Path
# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from mcp_tools.instance_discovery import InstanceDiscoveryTool
from mcp_tools.database_discovery import DatabaseDiscoveryTool
from mcp_tools.collection_analysis import CollectionAnalysisTool
from mcp_tools.query_generation import QueryGenerationTool
from mcp_tools.semantic_completion import SemanticCompletionTool


@pytest.mark.integration
@pytest.mark.mongodb
class TestMCPToolsIntegration(BaseIntegrationTest):
    """MCP工具集成测试类"""
    
    async def setup_test_environment(self):
        """设置测试环境"""
        await super().async_setup_method()
        
        # 初始化实例元数据库
        await self.metadata_manager.init_instance_metadata(TEST_INSTANCE_CONFIG["instance_id"])
        
        # 注册测试实例
        await self.metadata_manager.save_instance(TEST_INSTANCE_CONFIG["instance_id"], {
            "name": TEST_INSTANCE_CONFIG["instance_id"],
            "alias": TEST_INSTANCE_CONFIG["name"],
            "connection_string": TEST_INSTANCE_CONFIG["connection_string"],
            "description": "集成测试用实例",
            "environment": "test",
            "status": "active"
        })
        
        # 初始化语义分析器
        from scanner.semantic_analyzer import SemanticAnalyzer
        self.semantic_analyzer = SemanticAnalyzer(self.metadata_manager)
        
        # 扫描数据库和集合信息到元数据库
        from scanner.database_scanner import DatabaseScanner  
        from config import ScannerConfig
        
        # 创建扫描器配置
        scanner_config = ScannerConfig(
            max_sample_size=100,
            max_field_depth=5,
            enable_semantic_analysis=True
        )
        
        scanner = DatabaseScanner(self.connection_manager, self.metadata_manager, scanner_config)
        await scanner.scan_instance(TEST_INSTANCE_CONFIG["instance_id"])
    
    @pytest.mark.asyncio
    async def test_instance_discovery_integration(self):
        """测试实例发现工具 - 集成测试"""
        # 设置测试环境
        await self.async_setup_method()
        
        try:
            # 创建工具实例
            tool = InstanceDiscoveryTool(
                connection_manager=self.connection_manager,
                metadata_manager=self.metadata_manager
            )
            
            # 执行实例发现
            result = await tool.execute({})
            
            # 验证结果
            assert len(result) == 1
            assert isinstance(result[0], TextContent)
            
            # 验证返回的实例信息包含测试实例
            result_text = result[0].text
            assert TEST_INSTANCE_CONFIG["instance_id"] in result_text
            assert "active" in result_text.lower() or "活跃" in result_text
            
            print(f"实例发现结果: {result_text}")
        finally:
            # 清理测试环境
            await self.async_teardown_method()
    
    @pytest.mark.asyncio
    async def test_database_discovery_integration(self):
        """测试数据库发现工具 - 集成测试"""
        # 设置测试环境
        await self.async_setup_method()
        
        try:
            # 创建工具实例
            tool = DatabaseDiscoveryTool(
                connection_manager=self.connection_manager,
                metadata_manager=self.metadata_manager
            )
            
            # 执行数据库发现
            result = await tool.execute({
                "instance_id": TEST_INSTANCE_CONFIG["instance_id"]
            })
            
            # 验证结果
            assert len(result) == 1
            assert isinstance(result[0], TextContent)
            
            # 验证返回的数据库信息包含测试数据库
            result_text = result[0].text
            assert "querynest_test" in result_text
            
            print(f"数据库发现结果: {result_text}")
        finally:
            # 清理测试环境
            await self.async_teardown_method()
    
    @pytest.mark.asyncio
    async def test_collection_analysis_integration(self):
        """测试集合分析工具 - 集成测试"""
        # 设置测试环境
        await self.setup_test_environment()
        
        try:
            # 验证测试数据存在
            assert await self.verify_data_exists(), "测试数据不存在"
            
            # 创建工具实例
            tool = CollectionAnalysisTool(
                connection_manager=self.connection_manager,
                metadata_manager=self.metadata_manager,
                semantic_analyzer=self.semantic_analyzer
            )
            
            # 测试分析users集合
            result = await tool.execute({
                "instance_id": TEST_INSTANCE_CONFIG["instance_id"],
                "database_name": "querynest_test",
                "collection_name": "users",
                "include_semantics": True,
                "include_examples": True,
                "include_indexes": True,
                "rescan": True  # 强制重新扫描
            })
            
            # 验证结果
            assert len(result) == 1
            assert isinstance(result[0], TextContent)
            
            result_text = result[0].text
            print(f"\n=== 集合分析完整结果 ===\n{result_text}\n=== 结果结束 ===\n")
            
            # 验证包含集合信息
            assert "users" in result_text
            # 验证包含字段信息
            assert "name" in result_text
            assert "age" in result_text
            assert "email" in result_text
            # 验证包含文档数量
            assert str(len(TEST_DATA["users"])) in result_text
        finally:
            # 清理测试环境
            await self.async_teardown_method()
    
    @pytest.mark.asyncio
    async def test_query_generation_integration(self):
        """测试查询生成工具 - 集成测试"""
        # 设置测试环境
        await self.setup_test_environment()
        
        try:
            # 验证测试数据存在
            assert await self.verify_data_exists(), "测试数据不存在"
            
            # 创建工具实例
            tool = QueryGenerationTool(
                connection_manager=self.connection_manager,
                metadata_manager=self.metadata_manager,
                semantic_analyzer=self.semantic_analyzer
            )
            
            # 测试生成查询
            result = await tool.execute({
                "instance_id": TEST_INSTANCE_CONFIG["instance_id"],
                "database_name": "querynest_test",
                "collection_name": "users",
                "query_description": "查找技术部的所有用户",
                "include_explanation": True
            })
            
            # 验证结果
            assert len(result) == 1
            assert isinstance(result[0], TextContent)
            
            result_text = result[0].text
            # 验证包含查询语句
            assert "find" in result_text.lower() or "查询" in result_text
            assert "技术部" in result_text or "department" in result_text
            
            print(f"查询生成结果: {result_text}")
        finally:
            # 清理测试环境
            await self.async_teardown_method()
    
    @pytest.mark.asyncio
    async def test_semantic_completion_integration(self):
        """测试语义补全工具 - 集成测试"""
        # 设置测试环境
        await self.async_setup_method()
        
        try:
            # 验证测试数据存在
            assert await self.verify_data_exists(), "测试数据不存在"
            
            # 创建工具实例
            tool = SemanticCompletionTool(
                connection_manager=self.connection_manager,
                metadata_manager=self.metadata_manager,
                semantic_analyzer=self.semantic_analyzer
            )
            
            # 测试字段建议
            result = await tool.execute({
                "action": "suggest_semantics",
                "instance_name": TEST_INSTANCE_CONFIG["instance_id"],
                "database_name": "querynest_test",
                "collection_name": "users",
                "field_path": "na",
                "suggestion_type": "field"
            })
            
            # 验证结果
            assert len(result) == 1
            assert isinstance(result[0], TextContent)
            
            result_text = result[0].text
            # 验证包含字段建议
            assert "name" in result_text
            
            print(f"语义补全结果: {result_text}")
        finally:
            # 清理测试环境
            await self.async_teardown_method()
    
    @pytest.mark.asyncio
    async def test_cross_collection_query_integration(self):
        """测试跨集合查询 - 集成测试"""
        # 设置测试环境
        await self.setup_test_environment()
        
        try:
            # 验证测试数据存在
            assert await self.verify_data_exists(), "测试数据不存在"
            
            # 验证数据插入成功
            db = self.connection_manager.get_instance_database("test_instance", "querynest_test")
            orders_collection = db["orders"]
            users_collection = db["users"]
            
            orders_count = await orders_collection.count_documents({})
            users_count = await users_collection.count_documents({})
            
            assert orders_count > 0, "orders集合应该有数据"
            assert users_count > 0, "users集合应该有数据"
            
            # 先分析orders集合以获取字段信息
            analysis_tool = CollectionAnalysisTool(
                connection_manager=self.connection_manager,
                metadata_manager=self.metadata_manager,
                semantic_analyzer=self.semantic_analyzer
            )
            
            # 分析orders集合，强制重新扫描
            analysis_result = await analysis_tool.execute({
                "instance_id": TEST_INSTANCE_CONFIG["instance_id"],
                "database_name": "querynest_test",
                "collection_name": "orders",
                "include_semantics": True,
                "include_examples": True,
                "include_indexes": True,
                "rescan": True  # 强制重新扫描
            })
            
            # 验证分析结果
            assert analysis_result, "分析结果不应为空"
            assert len(analysis_result) > 0, "分析结果应包含内容"
            
            # 创建查询生成工具
            tool = QueryGenerationTool(
                connection_manager=self.connection_manager,
                metadata_manager=self.metadata_manager,
                semantic_analyzer=self.semantic_analyzer
            )
            
            # 测试生成关联查询
            result = await tool.execute({
                "instance_id": TEST_INSTANCE_CONFIG["instance_id"],
                "database_name": "querynest_test",
                "collection_name": "orders",
                "query_description": "查找张三的所有订单",
                "include_explanation": True
            })
            
            # 验证结果
            assert len(result) == 1
            assert isinstance(result[0], TextContent)
            
            result_text = result[0].text
            # 验证包含查询逻辑
            assert "orders" in result_text.lower() or "订单" in result_text
            assert "张三" in result_text or "user" in result_text.lower()
            
            print(f"跨集合查询结果: {result_text}")
        finally:
            # 清理测试环境
            await self.async_teardown_method()
    
    @pytest.mark.asyncio
    async def test_data_consistency_integration(self):
        """测试数据一致性 - 集成测试"""
        # 设置测试环境
        await self.async_setup_method()
        
        try:
            # 验证所有集合的数据数量
            for collection_name, expected_data in TEST_DATA.items():
                actual_count = await self.get_collection_count(collection_name)
                expected_count = len(expected_data)
                assert actual_count == expected_count, f"{collection_name} 集合数据数量不匹配: 期望 {expected_count}, 实际 {actual_count}"
            
            # 验证索引创建
            collections = await self.db.list_collection_names()
            assert "users" in collections
            assert "orders" in collections
            assert "products" in collections
            
            # 验证特定数据存在
            users_collection = self.db["users"]
            zhangsan = await users_collection.find_one({"name": "张三"})
            assert zhangsan is not None, "张三用户数据不存在"
            assert zhangsan["department"] == "技术部"
            
            orders_collection = self.db["orders"]
            zhangsan_orders = await orders_collection.count_documents({"user_id": 1})
            assert zhangsan_orders == 2, f"张三的订单数量不正确: 期望 2, 实际 {zhangsan_orders}"
            
            print("数据一致性验证通过")
        finally:
            # 清理测试环境
            await self.async_teardown_method()
