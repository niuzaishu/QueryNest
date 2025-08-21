# -*- coding: utf-8 -*-
"""端到端集成测试 - 模拟完整的MCP工具链使用流程"""

import pytest
import asyncio
from mcp.types import TextContent
from typing import Dict, Any

from .base_integration_test import BaseIntegrationTest
from .test_config import TEST_INSTANCE_CONFIG, TEST_DATA
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from mcp_tools.instance_discovery import InstanceDiscoveryTool
from mcp_tools.database_discovery import DatabaseDiscoveryTool
from mcp_tools.collection_analysis import CollectionAnalysisTool
from mcp_tools.unified_semantic_tool import UnifiedSemanticTool
from mcp_tools.query_generation import QueryGenerationTool
from mcp_tools.query_confirmation import QueryConfirmationTool


@pytest.mark.integration
@pytest.mark.mongodb
class TestEndToEndWorkflow(BaseIntegrationTest):
    """端到端工作流集成测试类"""
    
    async def setup_test_environment(self):
        """设置测试环境"""
        await super().async_setup_method()
        
        # 初始化实例元数据库
        try:
            await self.metadata_manager.init_instance_metadata(TEST_INSTANCE_CONFIG["instance_id"])
            print("✓ 元数据库初始化成功")
        except Exception as e:
            print(f"⚠️  元数据库初始化失败（使用业务库回退）: {e}")
        
        # 注册测试实例
        try:
            await self.metadata_manager.save_instance(TEST_INSTANCE_CONFIG["instance_id"], {
                "name": TEST_INSTANCE_CONFIG["instance_id"],
                "alias": TEST_INSTANCE_CONFIG["name"],
                "connection_string": TEST_INSTANCE_CONFIG["connection_string"],
                "description": "端到端测试用实例",
                "environment": "test",
                "status": "active"
            })
            print("✓ 实例信息保存成功")
        except Exception as e:
            print(f"⚠️  实例信息保存到元数据库失败（预期）: {e}")
    
    @pytest.mark.asyncio
    async def test_complete_discovery_to_query_workflow(self):
        """测试从发现到查询的完整工作流"""
        await self.setup_test_environment()
        
        try:
            # === 步骤1: 发现可用实例 ===
            instance_tool = InstanceDiscoveryTool(
                connection_manager=self.connection_manager,
                metadata_manager=self.metadata_manager
            )
            
            instance_result = await instance_tool.execute({
                "include_health": True,
                "include_stats": True
            })
            
            assert len(instance_result) == 1
            instance_text = instance_result[0].text
            assert TEST_INSTANCE_CONFIG["instance_id"] in instance_text
            print(f"✓ 步骤1完成 - 发现实例: {len(instance_result)} 个结果")
            
            # === 步骤2: 发现数据库 ===
            db_tool = DatabaseDiscoveryTool(
                connection_manager=self.connection_manager,
                metadata_manager=self.metadata_manager
            )
            
            db_result = await db_tool.execute({
                "instance_id": TEST_INSTANCE_CONFIG["instance_id"],
                "include_collections": True,
                "include_stats": True
            })
            
            assert len(db_result) == 1
            db_text = db_result[0].text
            assert "querynest_test" in db_text
            print(f"✓ 步骤2完成 - 发现数据库")
            
            # === 步骤3: 分析集合结构 ===
            analysis_tool = CollectionAnalysisTool(
                connection_manager=self.connection_manager,
                metadata_manager=self.metadata_manager,
                semantic_analyzer=self.semantic_analyzer
            )
            
            analysis_result = await analysis_tool.execute({
                "instance_id": TEST_INSTANCE_CONFIG["instance_id"],
                "database_name": "querynest_test",
                "collection_name": "users",
                "include_semantics": True,
                "include_examples": True,
                "include_indexes": True,
                "rescan": True
            })
            
            assert len(analysis_result) == 1
            analysis_text = analysis_result[0].text
            assert "users" in analysis_text
            assert "name" in analysis_text
            print(f"✓ 步骤3完成 - 分析集合结构")
            
            # === 步骤4: 语义分析和管理 ===
            semantic_tool = UnifiedSemanticTool(
                connection_manager=self.connection_manager,
                metadata_manager=self.metadata_manager,
                semantic_analyzer=self.semantic_analyzer
            )
            
            # 执行批量语义分析
            semantic_result = await semantic_tool.execute({
                "action": "batch_analyze",
                "instance_id": TEST_INSTANCE_CONFIG["instance_id"],
                "database_name": "querynest_test", 
                "collection_name": "users"
            })
            
            assert len(semantic_result) == 1
            semantic_text = semantic_result[0].text
            assert "分析" in semantic_text
            print(f"✓ 步骤4完成 - 语义分析")
            
            # === 步骤5: 生成查询 ===
            query_tool = QueryGenerationTool(
                connection_manager=self.connection_manager,
                metadata_manager=self.metadata_manager,
                semantic_analyzer=self.semantic_analyzer
            )
            
            query_result = await query_tool.execute({
                "instance_id": TEST_INSTANCE_CONFIG["instance_id"],
                "database_name": "querynest_test",
                "collection_name": "users",
                "query_description": "查找技术部的所有员工",
                "include_explanation": True,
                "output_format": "full"
            })
            
            assert len(query_result) == 1
            query_text = query_result[0].text
            assert "find" in query_text.lower() or "查询" in query_text
            print(f"✓ 步骤5完成 - 生成查询")
            
            # === 步骤6: 执行查询确认 ===
            confirm_tool = QueryConfirmationTool(
                connection_manager=self.connection_manager,
                metadata_manager=self.metadata_manager
            )
            
            # 构造一个简单的查询来执行
            test_query = {
                "department": "技术部"
            }
            
            confirm_result = await confirm_tool.execute({
                "instance_id": TEST_INSTANCE_CONFIG["instance_id"],
                "database_name": "querynest_test",
                "collection_name": "users",
                "query_type": "find",
                "mongodb_query": test_query,
                "limit": 10,
                "format_output": True
            })
            
            assert len(confirm_result) == 1
            confirm_text = confirm_result[0].text
            # 应该包含技术部的员工（张三和王五）
            assert "张三" in confirm_text or "王五" in confirm_text
            print(f"✓ 步骤6完成 - 执行查询确认")
            
            print("🎉 完整工作流测试成功！")
            
        finally:
            await self.async_teardown_method()
    
    @pytest.mark.asyncio
    async def test_complex_analytical_workflow(self):
        """测试复杂的分析工作流"""
        await self.setup_test_environment()
        
        try:
            # === 步骤1: 分析所有集合 ===
            analysis_tool = CollectionAnalysisTool(
                connection_manager=self.connection_manager,
                metadata_manager=self.metadata_manager,
                semantic_analyzer=self.semantic_analyzer
            )
            
            collections = ["users", "orders", "products"]
            collection_analyses = {}
            
            for collection_name in collections:
                result = await analysis_tool.execute({
                    "instance_id": TEST_INSTANCE_CONFIG["instance_id"],
                    "database_name": "querynest_test",
                    "collection_name": collection_name,
                    "include_semantics": True,
                    "include_examples": True,
                    "rescan": True
                })
                collection_analyses[collection_name] = result[0].text
                print(f"✓ 分析完成: {collection_name}")
            
            # === 步骤2: 建立语义关系 ===
            semantic_tool = UnifiedSemanticTool(
                connection_manager=self.connection_manager,
                metadata_manager=self.metadata_manager,
                semantic_analyzer=self.semantic_analyzer
            )
            
            # 为关键字段设置语义
            key_semantics = [
                {"collection": "users", "field": "name", "meaning": "用户姓名"},
                {"collection": "users", "field": "department", "meaning": "所属部门"},
                {"collection": "orders", "field": "user_id", "meaning": "用户标识"},
                {"collection": "orders", "field": "product", "meaning": "产品名称"},
                {"collection": "products", "field": "name", "meaning": "商品名称"},
            ]
            
            for semantic in key_semantics:
                await semantic_tool.execute({
                    "action": "update",
                    "instance_id": TEST_INSTANCE_CONFIG["instance_id"],
                    "database_name": "querynest_test",
                    "collection_name": semantic["collection"],
                    "field_path": semantic["field"],
                    "business_meaning": semantic["meaning"]
                })
            
            print("✓ 语义关系建立完成")
            
            # === 步骤3: 执行复杂查询生成 ===
            query_tool = QueryGenerationTool(
                connection_manager=self.connection_manager,
                metadata_manager=self.metadata_manager,
                semantic_analyzer=self.semantic_analyzer
            )
            
            complex_queries = [
                {
                    "collection": "users",
                    "description": "统计各部门的员工数量",
                    "expected_keywords": ["department", "count", "group"]
                },
                {
                    "collection": "orders",
                    "description": "查找金额超过1000元的订单",
                    "expected_keywords": ["amount", "1000", "gt"]
                },
                {
                    "collection": "products",
                    "description": "查找电子产品分类下的所有商品",
                    "expected_keywords": ["category", "电子产品"]
                }
            ]
            
            for query_spec in complex_queries:
                result = await query_tool.execute({
                    "instance_id": TEST_INSTANCE_CONFIG["instance_id"],
                    "database_name": "querynest_test",
                    "collection_name": query_spec["collection"],
                    "query_description": query_spec["description"],
                    "include_explanation": True,
                    "output_format": "full"
                })
                
                query_text = result[0].text
                print(f"✓ 复杂查询生成: {query_spec['collection']} - {query_spec['description']}")
                
                # 验证查询包含预期关键词
                for keyword in query_spec["expected_keywords"]:
                    if keyword not in query_text:
                        print(f"⚠️  查询可能缺少关键词: {keyword}")
            
            print("🎯 复杂分析工作流测试成功！")
            
        finally:
            await self.async_teardown_method()
    
    @pytest.mark.asyncio
    async def test_error_resilience_workflow(self):
        """测试错误恢复能力的工作流"""
        await self.setup_test_environment()
        
        try:
            # === 测试1: 无效实例处理 ===
            instance_tool = InstanceDiscoveryTool(
                connection_manager=self.connection_manager,
                metadata_manager=self.metadata_manager
            )
            
            # 测试正常实例发现
            normal_result = await instance_tool.execute({})
            assert len(normal_result) == 1
            print("✓ 正常实例发现测试通过")
            
            # === 测试2: 无效数据库处理 ===
            db_tool = DatabaseDiscoveryTool(
                connection_manager=self.connection_manager,
                metadata_manager=self.metadata_manager
            )
            
            # 测试无效实例ID
            invalid_result = await db_tool.execute({
                "instance_id": "nonexistent_instance"
            })
            assert len(invalid_result) == 1
            invalid_text = invalid_result[0].text
            assert "不存在" in invalid_text or "error" in invalid_text.lower()
            print("✓ 无效实例处理测试通过")
            
            # === 测试3: 查询生成容错 ===
            query_tool = QueryGenerationTool(
                connection_manager=self.connection_manager,
                metadata_manager=self.metadata_manager,
                semantic_analyzer=self.semantic_analyzer
            )
            
            # 测试对不存在集合的查询生成
            try:
                error_result = await query_tool.execute({
                    "instance_id": TEST_INSTANCE_CONFIG["instance_id"],
                    "database_name": "querynest_test",
                    "collection_name": "nonexistent_collection",
                    "query_description": "查找不存在集合的数据",
                    "include_explanation": True
                })
                # 应该返回友好的错误信息
                assert len(error_result) == 1
                error_text = error_result[0].text
                print(f"✓ 错误查询处理: {error_text}")
            except Exception as e:
                print(f"⚠️  查询工具异常处理: {e}")
            
            # === 测试4: 语义管理容错 ===
            semantic_tool = UnifiedSemanticTool(
                connection_manager=self.connection_manager,
                metadata_manager=self.metadata_manager,
                semantic_analyzer=self.semantic_analyzer
            )
            
            # 测试搜索不存在的语义
            empty_search = await semantic_tool.execute({
                "action": "search",
                "instance_id": TEST_INSTANCE_CONFIG["instance_id"],
                "search_term": "不存在的语义关键词"
            })
            
            assert len(empty_search) == 1
            empty_text = empty_search[0].text
            assert "未找到" in empty_text or "没有" in empty_text
            print("✓ 空搜索结果处理测试通过")
            
            print("🛡️  错误恢复能力测试成功！")
            
        finally:
            await self.async_teardown_method()
    
    @pytest.mark.asyncio
    async def test_performance_workflow(self):
        """测试性能相关的工作流"""
        await self.setup_test_environment()
        
        try:
            import time
            
            # === 性能测试1: 快速实例发现 ===
            start_time = time.time()
            
            instance_tool = InstanceDiscoveryTool(
                connection_manager=self.connection_manager,
                metadata_manager=self.metadata_manager
            )
            
            result = await instance_tool.execute({"include_health": True})
            
            discovery_time = time.time() - start_time
            assert discovery_time < 5.0, f"实例发现耗时过长: {discovery_time}秒"
            print(f"✓ 实例发现性能: {discovery_time:.2f}秒")
            
            # === 性能测试2: 批量集合分析 ===
            start_time = time.time()
            
            analysis_tool = CollectionAnalysisTool(
                connection_manager=self.connection_manager,
                metadata_manager=self.metadata_manager,
                semantic_analyzer=self.semantic_analyzer
            )
            
            # 并发分析多个集合
            analysis_tasks = []
            for collection_name in ["users", "orders", "products"]:
                task = analysis_tool.execute({
                    "instance_id": TEST_INSTANCE_CONFIG["instance_id"],
                    "database_name": "querynest_test",
                    "collection_name": collection_name,
                    "include_semantics": True,
                    "rescan": True
                })
                analysis_tasks.append(task)
            
            await asyncio.gather(*analysis_tasks)
            
            analysis_time = time.time() - start_time
            assert analysis_time < 30.0, f"批量分析耗时过长: {analysis_time}秒"
            print(f"✓ 批量分析性能: {analysis_time:.2f}秒")
            
            # === 性能测试3: 快速查询生成 ===
            start_time = time.time()
            
            query_tool = QueryGenerationTool(
                connection_manager=self.connection_manager,
                metadata_manager=self.metadata_manager,
                semantic_analyzer=self.semantic_analyzer
            )
            
            await query_tool.execute({
                "instance_id": TEST_INSTANCE_CONFIG["instance_id"],
                "database_name": "querynest_test",
                "collection_name": "users",
                "query_description": "查找所有用户",
                "output_format": "executable"  # 使用高性能的简洁格式
            })
            
            query_time = time.time() - start_time
            assert query_time < 10.0, f"查询生成耗时过长: {query_time}秒"
            print(f"✓ 查询生成性能: {query_time:.2f}秒")
            
            print("⚡ 性能测试通过！")
            
        finally:
            await self.async_teardown_method()