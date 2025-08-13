# -*- coding: utf-8 -*-
"""MCP工具单元测试 - 验证工具逻辑正确性"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from mcp.types import TextContent

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from mcp_tools.semantic_management import SemanticManagementTool
from mcp_tools.instance_discovery import InstanceDiscoveryTool
from mcp_tools.database_discovery import DatabaseDiscoveryTool
from mcp_tools.query_generation import QueryGenerationTool
from mcp_tools.collection_analysis import CollectionAnalysisTool


class TestMCPToolsUnit:
    """MCP工具单元测试类"""
    
    @pytest.fixture
    def setup_base_mocks(self):
        """设置基础模拟对象"""
        mock_cm = MagicMock()
        mock_mm = AsyncMock()
        mock_sa = MagicMock()
        
        return {
            'connection_manager': mock_cm,
            'metadata_manager': mock_mm,
            'semantic_analyzer': mock_sa
        }
    
    @pytest.mark.asyncio
    async def test_semantic_management_tool_update_action(self, setup_base_mocks):
        """测试语义管理工具的更新操作"""
        mocks = setup_base_mocks
        
        # 模拟实例存在检查
        mocks['connection_manager'].has_instance.return_value = True
        
        # 模拟语义更新成功
        mocks['metadata_manager'].update_field_semantics = AsyncMock(return_value=True)
        
        # 创建工具实例
        tool = SemanticManagementTool(
            connection_manager=mocks['connection_manager'],
            metadata_manager=mocks['metadata_manager'],
            semantic_analyzer=mocks['semantic_analyzer']
        )
        
        # 执行更新操作
        result = await tool.execute({
            "action": "update",
            "instance_id": "test_instance",
            "database_name": "test_db",
            "collection_name": "test_collection",
            "field_path": "test_field",
            "business_meaning": "测试业务含义"
        })
        
        # 验证结果
        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        result_text = result[0].text
        assert "成功" in result_text or "SUCCESS" in result_text.upper()
        
        # 验证调用
        mocks['metadata_manager'].update_field_semantics.assert_called_once()
    
    @pytest.mark.asyncio 
    async def test_semantic_management_tool_search_action(self, setup_base_mocks):
        """测试语义管理工具的搜索操作"""
        mocks = setup_base_mocks
        
        # 模拟实例存在检查
        mocks['connection_manager'].has_instance.return_value = True
        
        # 模拟搜索结果
        search_results = [
            {
                "database_name": "test_db",
                "collection_name": "test_collection", 
                "field_path": "test_field",
                "business_meaning": "测试含义",
                "field_type": "string"
            }
        ]
        mocks['metadata_manager'].search_fields_by_meaning = AsyncMock(return_value=search_results)
        
        # 创建工具实例
        tool = SemanticManagementTool(
            connection_manager=mocks['connection_manager'],
            metadata_manager=mocks['metadata_manager'],
            semantic_analyzer=mocks['semantic_analyzer']
        )
        
        # 执行搜索操作
        result = await tool.execute({
            "action": "search",
            "instance_id": "test_instance",
            "search_term": "测试"
        })
        
        # 验证结果
        assert len(result) == 1
        result_text = result[0].text
        assert "test_field" in result_text
        assert "测试含义" in result_text
        assert "匹配字段数" in result_text or "字段" in result_text
    
    @pytest.mark.asyncio
    async def test_semantic_management_tool_batch_analyze(self, setup_base_mocks):
        """测试语义管理工具的批量分析"""
        mocks = setup_base_mocks
        
        # 模拟实例存在检查
        mocks['connection_manager'].has_instance.return_value = True
        
        # 模拟批量分析结果
        analysis_result = {
            "total_fields": 10,
            "analyzed_fields": 8,
            "updated_fields": 5,
            "analysis_results": {
                "name": {
                    "suggested_meaning": "姓名",
                    "confidence": 0.8,
                    "reasoning": ["字段名称匹配"],
                    "suggestions": ["建议添加索引"]
                }
            }
        }
        mocks['semantic_analyzer'].batch_analyze_collection = AsyncMock(return_value=analysis_result)
        
        # 创建工具实例
        tool = SemanticManagementTool(
            connection_manager=mocks['connection_manager'],
            metadata_manager=mocks['metadata_manager'],
            semantic_analyzer=mocks['semantic_analyzer']
        )
        
        # 执行批量分析
        result = await tool.execute({
            "action": "batch_analyze",
            "instance_id": "test_instance",
            "database_name": "test_db",
            "collection_name": "test_collection"
        })
        
        # 验证结果
        assert len(result) == 1
        result_text = result[0].text
        assert "字段总数" in result_text
        assert "10" in result_text
        assert "分析字段数" in result_text
        assert "8" in result_text
        assert "自动更新数" in result_text
        assert "5" in result_text
    
    @pytest.mark.asyncio
    async def test_instance_discovery_tool(self, setup_base_mocks):
        """测试实例发现工具"""
        mocks = setup_base_mocks
        
        # 模拟实例信息
        mock_instances = {
            "test_instance": {
                "name": "测试实例",
                "environment": "test",
                "description": "测试用实例",
                "is_healthy": True,
                "last_health_check": None
            }
        }
        mocks['connection_manager'].get_all_instances_info = AsyncMock(return_value=list(mock_instances.values()))
        
        # 创建工具实例
        tool = InstanceDiscoveryTool(
            connection_manager=mocks['connection_manager'],
            metadata_manager=mocks['metadata_manager']
        )
        
        # 执行实例发现
        result = await tool.execute({
            "include_health": True,
            "include_stats": False
        })
        
        # 验证结果
        assert len(result) == 1
        result_text = result[0].text
        assert "测试实例" in result_text
        assert "test" in result_text
        assert "健康状态" in result_text or "状态" in result_text
    
    @pytest.mark.asyncio
    async def test_database_discovery_tool(self, setup_base_mocks):
        """测试数据库发现工具"""
        mocks = setup_base_mocks
        
        # 模拟实例检查
        mocks['connection_manager'].has_instance.return_value = True
        
        # 模拟数据库连接
        mock_instance_connection = MagicMock()
        mock_client = MagicMock()
        mock_client.list_database_names = AsyncMock(return_value=['test_db', 'admin', 'config'])
        mock_instance_connection.client = mock_client
        mocks['connection_manager'].get_instance_connection.return_value = mock_instance_connection
        
        # 创建工具实例
        tool = DatabaseDiscoveryTool(
            connection_manager=mocks['connection_manager'],
            metadata_manager=mocks['metadata_manager']
        )
        
        # 执行数据库发现
        result = await tool.execute({
            "instance_id": "test_instance",
            "filter_system": True,
            "include_collections": False
        })
        
        # 验证结果
        assert len(result) == 1
        result_text = result[0].text
        assert "test_db" in result_text
        # 系统数据库应该被过滤
        assert "admin" not in result_text
        assert "config" not in result_text
    
    @pytest.mark.asyncio
    async def test_query_generation_tool_executable_format(self, setup_base_mocks):
        """测试查询生成工具的可执行格式输出"""
        mocks = setup_base_mocks
        
        # 模拟实例和连接检查
        mocks['connection_manager'].has_instance.return_value = True
        mock_db = MagicMock()
        mocks['connection_manager'].get_instance_database.return_value = mock_db
        
        # 模拟字段信息
        mock_fields = [
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
        mocks['metadata_manager'].get_fields_by_collection = AsyncMock(return_value=mock_fields)
        
        # 创建工具实例
        tool = QueryGenerationTool(
            connection_manager=mocks['connection_manager'],
            metadata_manager=mocks['metadata_manager'],
            semantic_analyzer=mocks['semantic_analyzer']
        )
        
        # 执行查询生成（可执行格式）
        result = await tool.execute({
            "instance_id": "test_instance",
            "database_name": "test_db", 
            "collection_name": "users",
            "query_description": "查找年龄大于25的用户",
            "output_format": "executable",
            "limit": 10
        })
        
        # 验证结果
        assert len(result) == 1
        result_text = result[0].text
        
        # 验证包含可执行的MongoDB语句
        assert "db." in result_text
        assert "users" in result_text
        assert "find" in result_text or "aggregate" in result_text
        
        # 验证不包含详细解释（executable格式应该简洁）
        assert "解释" not in result_text or len(result_text) < 200
    
    @pytest.mark.asyncio
    async def test_collection_analysis_tool(self, setup_base_mocks):
        """测试集合分析工具"""
        mocks = setup_base_mocks
        
        # 模拟实例和数据库检查
        mocks['connection_manager'].has_instance.return_value = True
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__.return_value = mock_collection
        mocks['connection_manager'].get_instance_database.return_value = mock_db
        
        # 模拟集合统计
        mock_collection.count_documents = AsyncMock(return_value=100)
        
        # 模拟样本文档
        sample_docs = [
            {"name": "张三", "age": 25, "email": "zhangsan@example.com"},
            {"name": "李四", "age": 30, "email": "lisi@example.com"}
        ]
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=sample_docs)
        mock_collection.aggregate = MagicMock(return_value=mock_cursor)
        
        # 模拟索引信息
        mock_collection.list_indexes = AsyncMock(return_value=[
            {"key": {"_id": 1}, "name": "_id_"},
            {"key": {"email": 1}, "name": "email_1", "unique": True}
        ])
        
        # 模拟字段信息保存
        mocks['metadata_manager'].save_field = AsyncMock(return_value=ObjectId())
        
        # 创建工具实例
        tool = CollectionAnalysisTool(
            connection_manager=mocks['connection_manager'],
            metadata_manager=mocks['metadata_manager'],
            semantic_analyzer=mocks['semantic_analyzer']
        )
        
        # 执行集合分析
        result = await tool.execute({
            "instance_id": "test_instance",
            "database_name": "test_db",
            "collection_name": "users",
            "include_semantics": True,
            "include_examples": True,
            "include_indexes": True,
            "rescan": True
        })
        
        # 验证结果
        assert len(result) == 1
        result_text = result[0].text
        assert "users" in result_text
        assert "100" in result_text  # 文档数量
        assert "name" in result_text
        assert "age" in result_text
        assert "email" in result_text
        assert "索引" in result_text
    
    @pytest.mark.asyncio
    async def test_error_handling_invalid_instance(self, setup_base_mocks):
        """测试无效实例的错误处理"""
        mocks = setup_base_mocks
        
        # 模拟实例不存在
        mocks['connection_manager'].has_instance.return_value = False
        
        # 创建语义管理工具
        tool = SemanticManagementTool(
            connection_manager=mocks['connection_manager'],
            metadata_manager=mocks['metadata_manager'],
            semantic_analyzer=mocks['semantic_analyzer']
        )
        
        # 执行操作
        result = await tool.execute({
            "action": "update",
            "instance_id": "nonexistent_instance",
            "database_name": "test_db",
            "collection_name": "test_collection",
            "field_path": "test_field",
            "business_meaning": "测试"
        })
        
        # 验证错误处理
        assert len(result) == 1
        result_text = result[0].text
        assert "不存在" in result_text
        assert "discover_instances" in result_text
    
    @pytest.mark.asyncio
    async def test_parameter_validation(self, setup_base_mocks):
        """测试参数验证"""
        mocks = setup_base_mocks
        mocks['connection_manager'].has_instance.return_value = True
        
        # 创建语义管理工具
        tool = SemanticManagementTool(
            connection_manager=mocks['connection_manager'],
            metadata_manager=mocks['metadata_manager'],
            semantic_analyzer=mocks['semantic_analyzer']
        )
        
        # 测试缺少必需参数的更新操作
        result = await tool.execute({
            "action": "update",
            "instance_id": "test_instance",
            # 缺少 database_name, collection_name, field_path, business_meaning
        })
        
        # 验证参数验证
        assert len(result) == 1
        result_text = result[0].text
        assert "需要提供" in result_text or "参数" in result_text
        assert "database_name" in result_text
        assert "collection_name" in result_text
        assert "field_path" in result_text
        assert "business_meaning" in result_text
    
    @pytest.mark.asyncio
    async def test_async_exception_handling(self, setup_base_mocks):
        """测试异步异常处理"""
        mocks = setup_base_mocks
        
        # 模拟实例存在但操作失败
        mocks['connection_manager'].has_instance.return_value = True
        mocks['metadata_manager'].update_field_semantics = AsyncMock(side_effect=Exception("数据库连接失败"))
        
        # 创建工具
        tool = SemanticManagementTool(
            connection_manager=mocks['connection_manager'],
            metadata_manager=mocks['metadata_manager'],
            semantic_analyzer=mocks['semantic_analyzer']
        )
        
        # 执行操作
        result = await tool.execute({
            "action": "update",
            "instance_id": "test_instance",
            "database_name": "test_db",
            "collection_name": "test_collection",
            "field_path": "test_field",
            "business_meaning": "测试"
        })
        
        # 验证异常处理
        assert len(result) == 1
        result_text = result[0].text
        assert "错误" in result_text or "失败" in result_text