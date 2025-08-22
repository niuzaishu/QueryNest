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

from mcp_tools.unified_semantic_tool import UnifiedSemanticTool
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
        
        # 为连接管理器添加常用的异步方法模拟
        mock_cm.check_instance_health = AsyncMock(return_value={
            "healthy": True,
            "last_check": None,
            "error": None
        })
        mock_cm.get_all_instances = AsyncMock(return_value={})
        mock_cm.has_instance.return_value = True
        
        # 为元数据管理器添加常用方法模拟
        mock_mm.get_instance_by_name = AsyncMock(return_value={
            "_id": ObjectId(),
            "name": "test_instance"
        })
        mock_mm.init_instance_metadata = AsyncMock(return_value=True)
        
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
        tool = UnifiedSemanticTool(
            connection_manager=mocks['connection_manager'],
            metadata_manager=mocks['metadata_manager'],
            semantic_analyzer=mocks['semantic_analyzer']
        )
        
        # 执行更新操作
        result = await tool.execute({
            "action": "update_semantics",
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
        tool = UnifiedSemanticTool(
            connection_manager=mocks['connection_manager'],
            metadata_manager=mocks['metadata_manager'],
            semantic_analyzer=mocks['semantic_analyzer']
        )
        
        # 执行搜索操作
        result = await tool.execute({
            "action": "search_semantics",
            "instance_id": "test_instance",
            "search_term": "测试"
        })
        
        # 验证结果
        assert len(result) == 1
        result_text = result[0].text
        assert "test_field" in result_text
        assert "测试含义" in result_text
        assert "找到结果" in result_text or "字段" in result_text
    
    @pytest.mark.asyncio
    async def test_semantic_management_tool_batch_analyze(self, setup_base_mocks):
        """测试语义管理工具的批量分析"""
        mocks = setup_base_mocks
        
        # 模拟实例存在检查
        mocks['connection_manager'].has_instance.return_value = True
        
        # 模拟批量分析结果
        analysis_result = {
            "success": True,
            "analyzed_fields": [
                {
                    "field_path": "name",
                    "suggested_meaning": "姓名",
                    "confidence": 0.8
                },
                {
                    "field_path": "age", 
                    "suggested_meaning": "年龄",
                    "confidence": 0.7
                }
            ]
        }
        mocks['semantic_analyzer'].batch_analyze_collection = AsyncMock(return_value=analysis_result)
        
        # 创建工具实例
        tool = UnifiedSemanticTool(
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
        assert "分析字段数" in result_text
        assert "2" in result_text
        assert "成功识别语义" in result_text
        assert "姓名" in result_text
        assert "年龄" in result_text
    
    @pytest.mark.asyncio
    async def test_instance_discovery_tool(self, setup_base_mocks):
        """测试实例发现工具"""
        mocks = setup_base_mocks
        
        # 创建模拟的实例配置对象
        from config import MongoInstanceConfig
        mock_instance_config = MongoInstanceConfig(
            name="测试实例",
            connection_string="mongodb://localhost:27017/test",
            environment="test",
            description="测试用实例",
            status="active"
        )
        
        # 模拟get_all_instances方法返回配置字典
        mock_instances = {
            "test_instance": mock_instance_config
        }
        mocks['connection_manager'].get_all_instances = AsyncMock(return_value=mock_instances)
        
        # 模拟健康检查方法
        mocks['connection_manager'].check_instance_health = AsyncMock(return_value={
            "healthy": True,
            "latency_ms": 10,
            "last_check": None,
            "error": None
        })
        
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
        
        # 模拟健康检查
        mocks['connection_manager'].check_instance_health = AsyncMock(return_value={
            "healthy": True,
            "last_check": None,
            "error": None
        })
        
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
        
        # 模拟健康检查
        mocks['connection_manager'].check_instance_health = AsyncMock(return_value={
            "healthy": True,
            "error": None
        })
        
        # 模拟实例连接和数据库
        mock_connection = MagicMock()
        mock_db = MagicMock()
        mock_db.list_collection_names = AsyncMock(return_value=["users", "products", "orders"])
        mock_connection.get_database.return_value = mock_db
        mocks['connection_manager'].get_instance_connection.return_value = mock_connection
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
        
        # Mock workflow manager
        tool.workflow_manager = AsyncMock()
        tool.workflow_manager.get_workflow_data = AsyncMock(return_value={})
        tool.workflow_manager.update_workflow_data = AsyncMock()
        
        # Mock the query generation process
        query_info = {
            "instance_id": "test_instance",
            "database_name": "test_db",
            "collection_name": "users",
            "query_description": "查找年龄大于25的用户",
            "query_type": "find",
            "mongodb_query": {
                "operation": "find",
                "filter": {"age": {"$gt": 25}},
                "limit": 10
            },
            "limit": 10,
            "estimated_result_count": 5
        }
        tool._generate_query = AsyncMock(return_value=query_info)
        
        # Mock the query display method
        from mcp.types import TextContent
        expected_result = [TextContent(
            type="text", 
            text="## 🔍 生成的MongoDB查询语句\n\n**查询描述**: 查找年龄大于25的用户\n**MongoDB查询**: db.users.find({\"age\": {\"$gt\": 25}}).limit(10)"
        )]
        tool._show_query_only = AsyncMock(return_value=expected_result)
        
        # 执行查询生成（跳过确认以获取查询语句）
        result = await tool.execute({
            "instance_id": "test_instance",
            "database_name": "test_db", 
            "collection_name": "users",
            "query_description": "查找年龄大于25的用户",
            "skip_confirmation": True,
            "limit": 10
        })
        
        # 验证结果
        assert len(result) == 1
        result_text = result[0].text
        
        # 验证包含MongoDB查询语句
        assert "生成的MongoDB查询语句" in result_text
        assert "查找年龄大于25的用户" in result_text
        assert "db.users.find" in result_text
        
        # 验证工具被正确调用
        tool._generate_query.assert_called_once()
        tool._show_query_only.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_collection_analysis_tool(self, setup_base_mocks):
        """测试集合分析工具"""
        mocks = setup_base_mocks
        
        # 模拟实例和数据库检查
        mocks['connection_manager'].has_instance.return_value = True
        
        # 模拟实例连接对象
        mock_connection = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__.return_value = mock_collection
        mock_db.list_collection_names = AsyncMock(return_value=['users', 'products', 'orders'])
        mock_connection.get_database.return_value = mock_db
        
        mocks['connection_manager'].get_instance_connection.return_value = mock_connection
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
        
        # 模拟集合相关的方法
        mocks['metadata_manager'].get_collections_by_database = AsyncMock(return_value=[
            {"collection_name": "users", "document_count": 100}
        ])
        mocks['metadata_manager'].get_fields_by_collection = AsyncMock(return_value=[
            {"field_name": "name", "field_type": "string"},
            {"field_name": "age", "field_type": "number"},
            {"field_name": "email", "field_type": "string"}
        ])
        
        # 模拟其他需要的方法
        mocks['metadata_manager']._has_collection_metadata = AsyncMock(return_value=False)
        mocks['metadata_manager']._scan_collection = AsyncMock(return_value=None)
        
        # 模拟分析结果构建方法（这个方法在工具内部调用）
        async def mock_build_analysis_result(*args, **kwargs):
            return "## 集合分析结果\\n\\n集合: users\\n文档数量: 100\\n字段信息:\\n- name (string)\\n- age (number)\\n- email (string)"
        
        # 创建工具实例
        tool = CollectionAnalysisTool(
            connection_manager=mocks['connection_manager'],
            metadata_manager=mocks['metadata_manager'],
            semantic_analyzer=mocks['semantic_analyzer']
        )
        
        # Mock工具内部方法
        tool._has_collection_metadata = AsyncMock(return_value=False)
        tool._scan_collection = AsyncMock(return_value=None)
        tool._build_analysis_result = AsyncMock(return_value="## 集合分析结果\\n\\n集合: users\\n文档数量: 100\\n字段: name, age, email")
        
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
        assert result is not None, "Result should not be None"
        assert len(result) == 1
        result_text = result[0].text
        assert "users" in result_text
        assert "100" in result_text  # 文档数量
        assert "name" in result_text
        assert "age" in result_text
        assert "email" in result_text
    
    @pytest.mark.asyncio
    async def test_error_handling_invalid_instance(self, setup_base_mocks):
        """测试无效实例的错误处理"""
        mocks = setup_base_mocks
        
        # 模拟实例不存在
        mocks['connection_manager'].has_instance.return_value = False
        
        # 创建语义管理工具
        tool = UnifiedSemanticTool(
            connection_manager=mocks['connection_manager'],
            metadata_manager=mocks['metadata_manager'],
            semantic_analyzer=mocks['semantic_analyzer']
        )
        
        # 执行操作
        result = await tool.execute({
            "action": "update_semantics",
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
        tool = UnifiedSemanticTool(
            connection_manager=mocks['connection_manager'],
            metadata_manager=mocks['metadata_manager'],
            semantic_analyzer=mocks['semantic_analyzer']
        )
        
        # 测试缺少必需参数的更新操作
        result = await tool.execute({
            "action": "update_semantics",
            "instance_id": "test_instance",
            # 缺少 database_name, collection_name, field_path, business_meaning
        })
        
        # 验证参数验证
        assert len(result) == 1
        result_text = result[0].text
        assert "需要提供" in result_text or "参数" in result_text or "更新语义操作需要提供" in result_text
    
    @pytest.mark.asyncio
    async def test_async_exception_handling(self, setup_base_mocks):
        """测试异步异常处理"""
        mocks = setup_base_mocks
        
        # 模拟实例存在但操作失败
        mocks['connection_manager'].has_instance.return_value = True
        mocks['metadata_manager'].update_field_semantics = AsyncMock(side_effect=Exception("数据库连接失败"))
        
        # 创建工具
        tool = UnifiedSemanticTool(
            connection_manager=mocks['connection_manager'],
            metadata_manager=mocks['metadata_manager'],
            semantic_analyzer=mocks['semantic_analyzer']
        )
        
        # 执行操作，期望抛出QueryNestError
        from utils.error_handler import QueryNestError
        with pytest.raises(QueryNestError) as exc_info:
            await tool.execute({
                "action": "update_semantics",
                "instance_id": "test_instance",
                "database_name": "test_db",
                "collection_name": "test_collection",
                "field_path": "test_field",
                "business_meaning": "测试"
            })
        
        # 验证异常信息
        assert "数据库连接失败" in str(exc_info.value)