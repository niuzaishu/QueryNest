# -*- coding: utf-8 -*-
"""双重语义存储策略集成测试"""

import pytest
import asyncio
from mcp.types import TextContent
from bson import ObjectId

from .base_integration_test import BaseIntegrationTest
from .test_config import TEST_INSTANCE_CONFIG, TEST_DATA
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from mcp_tools.semantic_management import SemanticManagementTool
from mcp_tools.collection_analysis import CollectionAnalysisTool


@pytest.mark.integration
@pytest.mark.mongodb
class TestDualSemanticStorage(BaseIntegrationTest):
    """双重语义存储策略集成测试类"""
    
    async def setup_test_environment(self):
        """设置测试环境"""
        await super().async_setup_method()
        
        # 初始化实例元数据库（可能失败，这是正常的）
        try:
            await self.metadata_manager.init_instance_metadata(TEST_INSTANCE_CONFIG["instance_id"])
            print("✓ 元数据库初始化成功")
        except Exception as e:
            print(f"⚠️  元数据库初始化失败（预期）: {e}")
        
        # 注册测试实例
        try:
            await self.metadata_manager.save_instance(TEST_INSTANCE_CONFIG["instance_id"], {
                "name": TEST_INSTANCE_CONFIG["instance_id"],
                "alias": TEST_INSTANCE_CONFIG["name"],
                "connection_string": TEST_INSTANCE_CONFIG["connection_string"],
                "description": "双重存储测试用实例",
                "environment": "test",
                "status": "active"
            })
            print("✓ 实例信息保存成功")
        except Exception as e:
            print(f"⚠️  实例信息保存失败（可能因为元数据库权限）: {e}")
    
    @pytest.mark.asyncio
    async def test_metadata_fallback_to_business_db(self):
        """测试元数据库失败时回退到业务库存储"""
        # 设置测试环境
        await self.setup_test_environment()
        
        try:
            # 创建语义管理工具
            semantic_tool = SemanticManagementTool(
                connection_manager=self.connection_manager,
                metadata_manager=self.metadata_manager,
                semantic_analyzer=self.semantic_analyzer
            )
            
            # 测试更新字段语义
            result = await semantic_tool.execute({
                "action": "update",
                "instance_id": TEST_INSTANCE_CONFIG["instance_id"],
                "database_name": "querynest_test",
                "collection_name": "users",
                "field_path": "email",
                "business_meaning": "用户电子邮箱地址"
            })
            
            # 验证结果
            assert len(result) == 1
            assert isinstance(result[0], TextContent)
            result_text = result[0].text
            
            # 验证存储成功
            assert "成功" in result_text or "SUCCESS" in result_text.upper()
            print(f"语义更新结果: {result_text}")
            
            # 验证业务库中确实存储了语义信息
            business_db = self.connection_manager.get_instance_database(TEST_INSTANCE_CONFIG["instance_id"], "querynest_test")
            if business_db is not None:
                collection_names = await business_db.list_collection_names()
                assert '_querynest_semantics' in collection_names, "业务库中应该创建了语义集合"
                
                semantics_collection = business_db['_querynest_semantics']
                semantic_record = await semantics_collection.find_one({
                    "collection_name": "users",
                    "field_path": "email"
                })
                assert semantic_record is not None, "业务库中应该有语义记录"
                assert semantic_record["business_meaning"] == "用户电子邮箱地址"
                print("✓ 业务库语义存储验证通过")
        
        finally:
            await self.async_teardown_method()
    
    @pytest.mark.asyncio 
    async def test_semantic_search_across_sources(self):
        """测试跨数据源的语义搜索功能"""
        await self.setup_test_environment()
        
        try:
            # 先存储一些语义信息到业务库
            semantic_tool = SemanticManagementTool(
                connection_manager=self.connection_manager,
                metadata_manager=self.metadata_manager, 
                semantic_analyzer=self.semantic_analyzer
            )
            
            # 存储多个字段的语义信息
            test_semantics = [
                {"field_path": "name", "meaning": "用户姓名"},
                {"field_path": "email", "meaning": "用户邮箱地址"}, 
                {"field_path": "department", "meaning": "所属部门"}
            ]
            
            for semantic in test_semantics:
                await semantic_tool.execute({
                    "action": "update",
                    "instance_id": TEST_INSTANCE_CONFIG["instance_id"],
                    "database_name": "querynest_test",
                    "collection_name": "users",
                    "field_path": semantic["field_path"],
                    "business_meaning": semantic["meaning"]
                })
            
            # 执行语义搜索
            search_result = await semantic_tool.execute({
                "action": "search",
                "instance_id": TEST_INSTANCE_CONFIG["instance_id"],
                "search_term": "用户"
            })
            
            # 验证搜索结果
            assert len(search_result) == 1
            assert isinstance(search_result[0], TextContent)
            search_text = search_result[0].text
            
            # 验证搜索到了多个相关字段
            assert "name" in search_text or "姓名" in search_text
            assert "email" in search_text or "邮箱" in search_text
            assert "department" in search_text or "部门" in search_text
            
            # 验证搜索统计信息
            assert "匹配字段数" in search_text or "字段" in search_text
            print(f"语义搜索结果: {search_text}")
            
        finally:
            await self.async_teardown_method()
    
    @pytest.mark.asyncio
    async def test_batch_semantic_analysis_with_fallback(self):
        """测试批量语义分析使用回退存储"""
        await self.setup_test_environment()
        
        try:
            # 先确保有字段结构数据
            analysis_tool = CollectionAnalysisTool(
                connection_manager=self.connection_manager,
                metadata_manager=self.metadata_manager,
                semantic_analyzer=self.semantic_analyzer
            )
            
            # 分析集合结构
            await analysis_tool.execute({
                "instance_id": TEST_INSTANCE_CONFIG["instance_id"],
                "database_name": "querynest_test",
                "collection_name": "users",
                "include_semantics": True,
                "include_examples": True,
                "rescan": True
            })
            
            # 执行批量语义分析
            semantic_tool = SemanticManagementTool(
                connection_manager=self.connection_manager,
                metadata_manager=self.metadata_manager,
                semantic_analyzer=self.semantic_analyzer
            )
            
            batch_result = await semantic_tool.execute({
                "action": "batch_analyze", 
                "instance_id": TEST_INSTANCE_CONFIG["instance_id"],
                "database_name": "querynest_test",
                "collection_name": "users"
            })
            
            # 验证批量分析结果
            assert len(batch_result) == 1
            assert isinstance(batch_result[0], TextContent)
            batch_text = batch_result[0].text
            
            # 验证包含分析统计
            assert "分析统计" in batch_text or "字段" in batch_text
            assert "总数" in batch_text or "分析" in batch_text
            print(f"批量分析结果: {batch_text}")
            
            # 验证业务库中有自动更新的语义信息
            business_db = self.connection_manager.get_instance_database(TEST_INSTANCE_CONFIG["instance_id"], "querynest_test")
            if business_db is not None and '_querynest_semantics' in await business_db.list_collection_names():
                semantics_collection = business_db['_querynest_semantics']
                semantic_count = await semantics_collection.count_documents({})
                print(f"✓ 业务库中有 {semantic_count} 条自动生成的语义记录")
                
        finally:
            await self.async_teardown_method()
    
    @pytest.mark.asyncio
    async def test_semantic_source_identification(self):
        """测试语义来源标识功能"""
        await self.setup_test_environment()
        
        try:
            # 存储语义信息（会存储到业务库）
            semantic_tool = SemanticManagementTool(
                connection_manager=self.connection_manager,
                metadata_manager=self.metadata_manager,
                semantic_analyzer=self.semantic_analyzer
            )
            
            await semantic_tool.execute({
                "action": "update",
                "instance_id": TEST_INSTANCE_CONFIG["instance_id"],
                "database_name": "querynest_test",
                "collection_name": "users",
                "field_path": "age",
                "business_meaning": "用户年龄"
            })
            
            # 搜索语义信息，验证来源标识
            search_results = await self.metadata_manager.search_fields_by_meaning(
                TEST_INSTANCE_CONFIG["instance_id"], "年龄"
            )
            
            # 验证搜索结果包含来源标识
            assert len(search_results) > 0, "应该找到语义记录"
            
            found_business_source = False
            for result in search_results:
                if result.get("semantic_source") == "business_db":
                    found_business_source = True
                    assert result.get("field_path") == "age"
                    assert result.get("business_meaning") == "用户年龄"
                    print(f"✓ 找到业务库来源的语义记录: {result}")
                    
            assert found_business_source, "应该找到标记为business_db来源的记录"
            
        finally:
            await self.async_teardown_method()
    
    @pytest.mark.asyncio
    async def test_semantic_storage_resilience(self):
        """测试语义存储的容灾能力"""
        await self.setup_test_environment()
        
        try:
            # 验证即使元数据库不可用，语义功能仍能正常工作
            
            # 1. 更新语义信息
            result1 = await self.metadata_manager.update_field_semantics(
                TEST_INSTANCE_CONFIG["instance_id"], 
                ObjectId(),  # 使用假的ObjectId
                "querynest_test", 
                "users",
                "email",
                "联系邮箱",
                ["test@example.com"]
            )
            assert result1, "语义更新应该成功（通过业务库回退）"
            
            # 2. 搜索语义信息
            search_results = await self.metadata_manager.search_fields_by_meaning(
                TEST_INSTANCE_CONFIG["instance_id"], "邮箱"
            )
            assert len(search_results) > 0, "应该能够搜索到语义信息"
            
            # 3. 验证数据完整性
            business_db = self.connection_manager.get_instance_database(TEST_INSTANCE_CONFIG["instance_id"], "querynest_test")
            if business_db is not None:
                semantics_collection = business_db['_querynest_semantics']
                record = await semantics_collection.find_one({
                    "collection_name": "users",
                    "field_path": "email"
                })
                assert record is not None
                assert record["business_meaning"] == "联系邮箱"
                assert "source" in record
                assert record["source"] == "querynest_analyzer"
                print("✓ 语义存储容灾验证通过")
                
        finally:
            await self.async_teardown_method()
    
    @pytest.mark.asyncio
    async def test_cross_database_semantic_consistency(self):
        """测试跨数据库语义一致性"""
        await self.setup_test_environment()
        
        try:
            # 在不同的集合中存储类似的语义信息
            semantic_tool = SemanticManagementTool(
                connection_manager=self.connection_manager,
                metadata_manager=self.metadata_manager,
                semantic_analyzer=self.semantic_analyzer
            )
            
            # 在users集合中存储
            await semantic_tool.execute({
                "action": "update",
                "instance_id": TEST_INSTANCE_CONFIG["instance_id"],
                "database_name": "querynest_test", 
                "collection_name": "users",
                "field_path": "name",
                "business_meaning": "姓名"
            })
            
            # 在orders集合中存储
            await semantic_tool.execute({
                "action": "update",
                "instance_id": TEST_INSTANCE_CONFIG["instance_id"],
                "database_name": "querynest_test",
                "collection_name": "orders", 
                "field_path": "product",
                "business_meaning": "产品名称"
            })
            
            # 搜索包含"名称"的语义信息
            search_result = await semantic_tool.execute({
                "action": "search",
                "instance_id": TEST_INSTANCE_CONFIG["instance_id"],
                "search_term": "名称"
            })
            
            # 验证搜索结果
            assert len(search_result) == 1
            search_text = search_result[0].text
            
            # 应该能找到两个不同集合的记录
            assert "users" in search_text
            assert "orders" in search_text
            assert "姓名" in search_text
            assert "产品名称" in search_text
            
            print(f"跨集合语义搜索结果: {search_text}")
            
        finally:
            await self.async_teardown_method()