# -*- coding: utf-8 -*-
"""双重语义存储策略单元测试 - 无需外部MongoDB依赖"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from database.metadata_manager import MetadataManager
from database.connection_manager import ConnectionManager
from config import QueryNestConfig


class TestDualSemanticStorageUnit:
    """双重语义存储策略单元测试类"""
    
    @pytest.fixture
    def setup_mocks(self):
        """设置模拟对象"""
        # 模拟连接管理器
        mock_cm = MagicMock(spec=ConnectionManager)
        
        # 模拟业务数据库连接
        mock_business_db = MagicMock()
        mock_semantics_collection = AsyncMock()
        mock_business_db.__getitem__.return_value = mock_semantics_collection
        
        mock_cm.get_instance_database.return_value = mock_business_db
        
        # 模拟实例连接
        mock_instance_connection = MagicMock()
        mock_instance_connection.client = MagicMock()
        mock_instance_connection.client.list_database_names = AsyncMock(return_value=['test_db', 'admin'])
        mock_instance_connection.get_database.return_value = mock_business_db
        
        mock_cm.get_instance_connection.return_value = mock_instance_connection
        
        # 创建元数据管理器
        metadata_manager = MetadataManager(mock_cm)
        
        return {
            'metadata_manager': metadata_manager,
            'mock_cm': mock_cm,
            'mock_business_db': mock_business_db,
            'mock_semantics_collection': mock_semantics_collection
        }
    
    @pytest.mark.asyncio
    async def test_metadata_fallback_logic(self, setup_mocks):
        """测试元数据库失败时的回退逻辑"""
        mm = setup_mocks['metadata_manager']
        mock_semantics_collection = setup_mocks['mock_semantics_collection']
        
        # 模拟元数据库集合不可用（返回None）
        mm._get_instance_collections = MagicMock(return_value=None)
        
        # 模拟业务库操作成功
        mock_replace_result = MagicMock()
        mock_replace_result.upserted_id = ObjectId()
        mock_semantics_collection.replace_one = AsyncMock(return_value=mock_replace_result)
        
        # 执行更新操作
        result = await mm.update_field_semantics(
            "test_instance", ObjectId(), "test_db", "test_collection", 
            "test_field", "测试业务含义"
        )
        
        # 验证结果
        assert result is True, "应该返回成功"
        
        # 验证业务库存储被调用
        mock_semantics_collection.replace_one.assert_called_once()
        call_args = mock_semantics_collection.replace_one.call_args
        
        # 验证调用参数
        assert call_args[0][0] == {"collection_name": "test_collection", "field_path": "test_field"}
        assert call_args[0][1]["business_meaning"] == "测试业务含义"
        assert call_args[0][1]["source"] == "querynest_analyzer"
        assert call_args[1]["upsert"] is True
    
    @pytest.mark.asyncio
    async def test_metadata_success_no_fallback(self, setup_mocks):
        """测试元数据库成功时不使用回退"""
        mm = setup_mocks['metadata_manager']
        mock_cm = setup_mocks['mock_cm']
        
        # 模拟元数据库集合可用
        mock_fields_collection = AsyncMock()
        mock_update_result = MagicMock()
        mock_update_result.modified_count = 1
        mock_fields_collection.update_one = AsyncMock(return_value=mock_update_result)
        
        mock_collections = {'fields': mock_fields_collection}
        mm._get_instance_collections = MagicMock(return_value=mock_collections)
        
        # 执行更新操作
        result = await mm.update_field_semantics(
            "test_instance", ObjectId(), "test_db", "test_collection", 
            "test_field", "测试业务含义"
        )
        
        # 验证结果
        assert result is True, "应该返回成功"
        
        # 验证元数据库被调用
        mock_fields_collection.update_one.assert_called_once()
        
        # 验证业务库没有被调用
        mock_cm.get_instance_database.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_comprehensive_search_logic(self, setup_mocks):
        """测试综合搜索逻辑"""
        mm = setup_mocks['metadata_manager']
        mock_semantics_collection = setup_mocks['mock_semantics_collection']
        
        # 模拟元数据库搜索结果为空
        mm._get_instance_collections = MagicMock(return_value=None)
        
        # 模拟业务库搜索结果
        business_results = [
            {
                "collection_name": "test_collection",
                "field_path": "test_field",
                "business_meaning": "测试含义",
                "examples": ["example1", "example2"]
            }
        ]
        
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=business_results)
        mock_semantics_collection.find = MagicMock(return_value=mock_cursor)
        
        # 模拟数据库列表
        mock_business_db = setup_mocks['mock_business_db']
        mock_business_db.list_collection_names = AsyncMock(return_value=['_querynest_semantics'])
        
        # 执行搜索
        search_results = await mm.search_fields_by_meaning("test_instance", "测试")
        
        # 验证结果
        assert len(search_results) == 1
        result = search_results[0]
        assert result["semantic_source"] == "business_db"
        assert result["business_meaning"] == "测试含义"
        assert result["database_name"] == "test_db"  # 应该被设置
    
    @pytest.mark.asyncio
    async def test_deduplication_logic(self, setup_mocks):
        """测试去重逻辑"""
        mm = setup_mocks['metadata_manager']
        
        # 创建重复的搜索结果
        results = [
            {
                "database_name": "test_db",
                "collection_name": "test_collection",
                "field_path": "test_field",
                "business_meaning": "元数据库含义",
                "semantic_source": "metadata_db"
            },
            {
                "database_name": "test_db", 
                "collection_name": "test_collection",
                "field_path": "test_field",
                "business_meaning": "业务库含义",
                "semantic_source": "business_db"
            },
            {
                "database_name": "test_db",
                "collection_name": "test_collection", 
                "field_path": "another_field",
                "business_meaning": "另一个字段",
                "semantic_source": "business_db"
            }
        ]
        
        # 执行去重
        unique_results = mm._deduplicate_semantic_results(results)
        
        # 验证结果
        assert len(unique_results) == 2, "应该有2个唯一结果"
        
        # 验证优先保留元数据库记录
        test_field_result = None
        another_field_result = None
        
        for result in unique_results:
            if result["field_path"] == "test_field":
                test_field_result = result
            elif result["field_path"] == "another_field":
                another_field_result = result
        
        assert test_field_result is not None
        assert test_field_result["semantic_source"] == "metadata_db"
        assert test_field_result["business_meaning"] == "元数据库含义"
        
        assert another_field_result is not None
        assert another_field_result["semantic_source"] == "business_db"
    
    @pytest.mark.asyncio
    async def test_business_db_storage_error_handling(self, setup_mocks):
        """测试业务库存储错误处理"""
        mm = setup_mocks['metadata_manager']
        mock_cm = setup_mocks['mock_cm']
        
        # 模拟元数据库不可用
        mm._get_instance_collections = MagicMock(return_value=None)
        
        # 模拟业务库连接失败
        mock_cm.get_instance_database.return_value = None
        
        # 执行更新操作
        result = await mm.update_field_semantics(
            "test_instance", ObjectId(), "test_db", "test_collection", 
            "test_field", "测试业务含义"
        )
        
        # 验证结果
        assert result is False, "应该返回失败"
    
    @pytest.mark.asyncio
    async def test_business_db_update_exception_handling(self, setup_mocks):
        """测试业务库更新异常处理"""
        mm = setup_mocks['metadata_manager']
        mock_semantics_collection = setup_mocks['mock_semantics_collection']
        
        # 模拟元数据库不可用
        mm._get_instance_collections = MagicMock(return_value=None)
        
        # 模拟业务库操作异常
        mock_semantics_collection.replace_one = AsyncMock(side_effect=Exception("数据库操作失败"))
        
        # 执行更新操作
        result = await mm.update_field_semantics(
            "test_instance", ObjectId(), "test_db", "test_collection", 
            "test_field", "测试业务含义"
        )
        
        # 验证结果
        assert result is False, "应该返回失败"
    
    def test_semantic_document_structure(self, setup_mocks):
        """测试语义文档结构"""
        mm = setup_mocks['metadata_manager']
        mock_semantics_collection = setup_mocks['mock_semantics_collection']
        
        # 模拟调用以验证文档结构
        async def capture_document():
            # 模拟元数据库不可用
            mm._get_instance_collections = MagicMock(return_value=None)
            
            # 捕获传递给replace_one的文档
            captured_doc = None
            
            async def capture_replace_one(filter_doc, update_doc, **kwargs):
                nonlocal captured_doc
                captured_doc = update_doc
                mock_result = MagicMock()
                mock_result.upserted_id = ObjectId()
                return mock_result
            
            mock_semantics_collection.replace_one = capture_replace_one
            
            # 执行更新操作
            await mm.update_field_semantics(
                "test_instance", ObjectId(), "test_db", "test_collection", 
                "test_field", "测试业务含义", ["example1", "example2"]
            )
            
            return captured_doc
        
        # 运行异步测试
        captured_doc = asyncio.run(capture_document())
        
        # 验证文档结构
        assert captured_doc is not None
        assert captured_doc["collection_name"] == "test_collection"
        assert captured_doc["field_path"] == "test_field"
        assert captured_doc["business_meaning"] == "测试业务含义"
        assert captured_doc["examples"] == ["example1", "example2"]
        assert captured_doc["source"] == "querynest_analyzer"
        assert "updated_at" in captured_doc
    
    @pytest.mark.asyncio
    async def test_search_query_construction(self, setup_mocks):
        """测试搜索查询构造"""
        mm = setup_mocks['metadata_manager']
        mock_semantics_collection = setup_mocks['mock_semantics_collection']
        
        # 模拟元数据库不可用
        mm._get_instance_collections = MagicMock(return_value=None)
        
        # 捕获传递给find的查询
        captured_query = None
        
        def capture_find(query):
            nonlocal captured_query
            captured_query = query
            mock_cursor = AsyncMock()
            mock_cursor.to_list = AsyncMock(return_value=[])
            return mock_cursor
        
        mock_semantics_collection.find = capture_find
        
        # 模拟数据库列表
        mock_business_db = setup_mocks['mock_business_db']
        mock_business_db.list_collection_names = AsyncMock(return_value=['_querynest_semantics'])
        
        # 执行搜索
        await mm.search_fields_by_meaning("test_instance", "测试关键词")
        
        # 验证查询构造
        assert captured_query is not None
        assert "$or" in captured_query
        or_conditions = captured_query["$or"]
        assert len(or_conditions) == 3
        
        # 验证查询条件
        field_path_condition = or_conditions[0]
        assert field_path_condition["field_path"]["$regex"] == "测试关键词"
        assert field_path_condition["field_path"]["$options"] == "i"
        
        business_meaning_condition = or_conditions[1]
        assert business_meaning_condition["business_meaning"]["$regex"] == "测试关键词"
        
        examples_condition = or_conditions[2]
        assert "examples" in examples_condition
        assert "$elemMatch" in examples_condition["examples"]