# -*- coding: utf-8 -*-
"""本地语义存储策略单元测试 - 适配新架构"""

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


class TestLocalSemanticStorageUnit:
    """本地语义存储策略单元测试类"""
    
    @pytest.fixture
    def setup_mocks(self):
        """设置模拟对象"""
        # 模拟连接管理器
        mock_cm = MagicMock(spec=ConnectionManager)
        
        # 创建元数据管理器
        metadata_manager = MetadataManager(mock_cm)
        
        # 模拟本地存储组件
        mock_local_storage = AsyncMock()
        mock_file_manager = MagicMock()
        
        # 替换MetadataManager中的本地存储组件
        metadata_manager.local_storage = mock_local_storage
        metadata_manager.file_manager = mock_file_manager
        
        return {
            'metadata_manager': metadata_manager,
            'mock_cm': mock_cm,
            'mock_local_storage': mock_local_storage,
            'mock_file_manager': mock_file_manager
        }
    
    @pytest.mark.asyncio
    async def test_local_storage_success(self, setup_mocks):
        """测试本地文件存储成功"""
        mm = setup_mocks['metadata_manager']
        mock_local_storage = setup_mocks['mock_local_storage']
        
        # 模拟本地存储操作成功
        mock_local_storage.save_field_semantics = AsyncMock(return_value=True)
        
        # 执行更新操作
        result = await mm.update_field_semantics(
            "test_instance", ObjectId(), "test_db", "test_collection", 
            "test_field", "测试业务含义"
        )
        
        # 验证结果
        assert result is True, "应该返回成功"
        
        # 验证本地存储被调用
        mock_local_storage.save_field_semantics.assert_called_once_with(
            "test_instance", "test_db", "test_collection", "test_field", "测试业务含义", []
        )
    
    @pytest.mark.asyncio
    async def test_local_storage_with_examples(self, setup_mocks):
        """测试本地存储包含示例值"""
        mm = setup_mocks['metadata_manager']
        mock_local_storage = setup_mocks['mock_local_storage']
        
        # 模拟本地存储操作成功
        mock_local_storage.save_field_semantics = AsyncMock(return_value=True)
        
        # 执行更新操作，包含示例值
        result = await mm.update_field_semantics(
            "test_instance", ObjectId(), "test_db", "test_collection", 
            "test_field", "测试业务含义", ["example1", "example2"]
        )
        
        # 验证结果
        assert result is True, "应该返回成功"
        
        # 验证本地存储被调用，包含示例值
        mock_local_storage.save_field_semantics.assert_called_once_with(
            "test_instance", "test_db", "test_collection", "test_field", "测试业务含义", ["example1", "example2"]
        )
    
    @pytest.mark.asyncio
    async def test_local_storage_failure(self, setup_mocks):
        """测试本地存储失败"""
        mm = setup_mocks['metadata_manager']
        mock_local_storage = setup_mocks['mock_local_storage']
        
        # 模拟本地存储操作失败
        mock_local_storage.save_field_semantics = AsyncMock(return_value=False)
        
        # 执行更新操作
        result = await mm.update_field_semantics(
            "test_instance", ObjectId(), "test_db", "test_collection", 
            "test_field", "测试业务含义"
        )
        
        # 验证结果
        assert result is False, "应该返回失败"
        
        # 验证本地存储被调用
        mock_local_storage.save_field_semantics.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_local_storage_exception(self, setup_mocks):
        """测试本地存储异常处理"""
        mm = setup_mocks['metadata_manager']
        mock_local_storage = setup_mocks['mock_local_storage']
        
        # 模拟本地存储操作异常
        mock_local_storage.save_field_semantics = AsyncMock(side_effect=Exception("文件系统错误"))
        
        # 执行更新操作
        result = await mm.update_field_semantics(
            "test_instance", ObjectId(), "test_db", "test_collection", 
            "test_field", "测试业务含义"
        )
        
        # 验证结果
        assert result is False, "应该返回失败"
        
        # 验证本地存储被调用
        mock_local_storage.save_field_semantics.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_search_fields_by_meaning(self, setup_mocks):
        """测试按语义搜索字段"""
        mm = setup_mocks['metadata_manager']
        mock_local_storage = setup_mocks['mock_local_storage']
        
        # 模拟搜索结果
        search_results = [
            {
                "instance_name": "test_instance",
                "database_name": "test_db",
                "collection_name": "test_collection",
                "field_path": "test_field",
                "business_meaning": "测试含义",
                "examples": ["example1", "example2"],
                "semantic_source": "local_file"
            }
        ]
        
        mock_local_storage.search_semantics = AsyncMock(return_value=search_results)
        
        # 执行搜索
        results = await mm.search_fields_by_meaning("test_instance", "测试")
        
        # 验证结果
        assert len(results) == 1
        result = results[0]
        assert result["semantic_source"] == "local_file"
        assert result["business_meaning"] == "测试含义"
        assert result["database_name"] == "test_db"
        
        # 验证本地存储搜索被调用
        mock_local_storage.search_semantics.assert_called_once_with("test_instance", "测试")
    
    @pytest.mark.asyncio
    async def test_get_fields_by_collection(self, setup_mocks):
        """测试获取集合字段信息"""
        mm = setup_mocks['metadata_manager']
        
        # 模拟元数据库collections
        mock_fields_collection = AsyncMock()
        mock_collections = {'fields': mock_fields_collection}
        mm._get_instance_collections = MagicMock(return_value=mock_collections)
        
        # 模拟字段数据
        fields_data = [
            {
                "field_path": "name",
                "business_meaning": "姓名",
                "field_type": "string",
                "examples": ["张三", "李四"]
            },
            {
                "field_path": "age",
                "business_meaning": "年龄", 
                "field_type": "number",
                "examples": [25, 30]
            }
        ]
        
        # 模拟cursor
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=fields_data)
        mock_fields_collection.find = MagicMock(return_value=mock_cursor)
        
        # 执行获取操作
        fields = await mm.get_fields_by_collection("test_instance", ObjectId(), "test_db", "test_collection")
        
        # 验证结果
        assert len(fields) == 2
        assert fields[0]["field_path"] == "name"
        assert fields[0]["business_meaning"] == "姓名"
        assert fields[1]["field_path"] == "age"
        assert fields[1]["business_meaning"] == "年龄"
        
        # 验证调用
        mock_fields_collection.find.assert_called_once()
        mock_cursor.to_list.assert_called_once_with(length=None)