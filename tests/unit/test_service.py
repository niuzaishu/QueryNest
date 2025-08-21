#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QueryNest服务测试脚本"""

import asyncio
import sys
import json
from pathlib import Path
from typing import Dict, Any

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config import QueryNestConfig
from database.connection_manager import ConnectionManager
from database.metadata_manager_file import FileBasedMetadataManager
from database.query_engine import QueryEngine
from scanner.structure_scanner import StructureScanner
from scanner.semantic_analyzer import SemanticAnalyzer
from mcp_tools import (
    InstanceDiscoveryTool,
    DatabaseDiscoveryTool,
    CollectionAnalysisTool,
    UnifiedSemanticTool,
    QueryGenerationTool,
    QueryConfirmationTool,
)


class QueryNestTester:
    """QueryNest服务测试器"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.config = None
        self.connection_manager = None
        self.metadata_manager = None
        self.query_engine = None
        self.structure_scanner = None
        self.semantic_analyzer = None
        self.tools = {}
    
    async def initialize(self):
        """初始化测试环境"""
        print("🚀 初始化QueryNest测试环境...")
        
        try:
            # 加载配置
            self.config = QueryNestConfig.from_yaml(self.config_path)
            print(f"✅ 配置加载完成，发现 {len(self.config.mongo_instances)} 个实例")
            
            # 初始化连接管理器
            self.connection_manager = ConnectionManager(self.config)
            await self.connection_manager.initialize()
            print("✅ 连接管理器初始化完成")
            
            # 初始化元数据管理器
            self.metadata_manager = FileBasedMetadataManager(self.connection_manager)
            await self.metadata_manager.initialize()
            print("✅ 元数据管理器初始化完成")
            
            # 初始化查询引擎
            self.query_engine = QueryEngine(self.connection_manager, self.metadata_manager, self.config)
            print("✅ 查询引擎初始化完成")
            
            # 初始化结构扫描器
            self.structure_scanner = StructureScanner(self.connection_manager, self.metadata_manager, self.config)
            print("✅ 结构扫描器初始化完成")
            
            # 初始化语义分析器
            self.semantic_analyzer = SemanticAnalyzer(self.metadata_manager)
            print("✅ 语义分析器初始化完成")
            
            # 初始化MCP工具
            await self._initialize_tools()
            print(f"✅ MCP工具初始化完成，共 {len(self.tools)} 个工具")
            
            print("🎉 初始化完成！\n")
            
        except Exception as e:
            print(f"❌ 初始化失败: {e}")
            raise
    
    async def _initialize_tools(self):
        """初始化MCP工具"""
        # 实例发现工具
        self.tools["discover_instances"] = InstanceDiscoveryTool(self.connection_manager, self.metadata_manager)
        
        # 数据库发现工具
        self.tools["discover_databases"] = DatabaseDiscoveryTool(self.connection_manager, self.metadata_manager)
        
        # 集合分析工具
        self.tools["analyze_collection"] = CollectionAnalysisTool(
            self.connection_manager, self.metadata_manager, self.semantic_analyzer
        )
        
        # 语义管理工具
        self.tools["manage_semantics"] = UnifiedSemanticTool(
            self.connection_manager, self.metadata_manager, self.semantic_analyzer
        )
        
        # 查询生成工具
        self.tools["generate_query"] = QueryGenerationTool(
            self.connection_manager, self.metadata_manager, self.semantic_analyzer
        )
        
        # 查询确认工具
        self.tools["confirm_query"] = QueryConfirmationTool(
            self.connection_manager, self.metadata_manager, self.query_engine
        )
    
    async def test_basic_functionality(self):
        """测试基本功能"""
        print("🧪 开始基本功能测试...\n")
        
        # 测试1: 实例发现
        await self._test_instance_discovery()
        
        # 测试2: 数据库发现
        await self._test_database_discovery()
        
        # 测试3: 连接健康检查
        await self._test_health_check()
        
        print("✅ 基本功能测试完成\n")
    
    async def _test_instance_discovery(self):
        """测试实例发现"""
        print("📋 测试实例发现...")
        
        try:
            tool = self.tools["discover_instances"]
            result = await tool.execute({
                "include_health": True,
                "include_stats": True
            })
            
            if result and len(result) > 0:
                print(f"✅ 实例发现成功，返回 {len(result)} 条结果")
                # 打印第一个结果的前200个字符
                content = result[0].text[:200] + "..." if len(result[0].text) > 200 else result[0].text
                print(f"   结果预览: {content}")
            else:
                print("⚠️ 实例发现返回空结果")
                
        except Exception as e:
            print(f"❌ 实例发现测试失败: {e}")
    
    async def _test_database_discovery(self):
        """测试数据库发现"""
        print("📋 测试数据库发现...")
        
        try:
            # 获取第一个实例ID
            instance_ids = list(self.connection_manager.connections.keys())
            if not instance_ids:
                print("⚠️ 没有可用的实例进行测试")
                return
            
            instance_id = instance_ids[0]
            tool = self.tools["discover_databases"]
            result = await tool.execute({
                "instance_id": instance_id,
                "include_collections": True,
                "exclude_system": True
            })
            
            if result and len(result) > 0:
                print(f"✅ 数据库发现成功，实例 {instance_id}")
                content = result[0].text[:200] + "..." if len(result[0].text) > 200 else result[0].text
                print(f"   结果预览: {content}")
            else:
                print(f"⚠️ 实例 {instance_id} 数据库发现返回空结果")
                
        except Exception as e:
            print(f"❌ 数据库发现测试失败: {e}")
    
    async def _test_health_check(self):
        """测试健康检查"""
        print("🏥 测试连接健康检查...")
        
        try:
            for instance_id in self.connection_manager.connections.keys():
                connection = self.connection_manager.get_instance_connection(instance_id)
                if connection:
                    health = await connection.health_check()
                    status = "✅ 健康" if health else "❌ 不健康"
                    print(f"   实例 {instance_id}: {status}")
                    
        except Exception as e:
            print(f"❌ 健康检查测试失败: {e}")
    
    async def test_advanced_functionality(self):
        """测试高级功能"""
        print("🔬 开始高级功能测试...\n")
        
        # 获取第一个可用实例
        instance_ids = list(self.connection_manager.connections.keys())
        if not instance_ids:
            print("⚠️ 没有可用的实例进行高级测试")
            return
        
        instance_id = instance_ids[0]
        
        # 测试集合分析（如果有可用的集合）
        await self._test_collection_analysis(instance_id)
        
        # 测试查询生成
        await self._test_query_generation(instance_id)
        
        print("✅ 高级功能测试完成\n")
    
    async def _test_collection_analysis(self, instance_id: str):
        """测试集合分析"""
        print(f"🔍 测试集合分析 (实例: {instance_id})...")
        
        try:
            # 首先获取数据库列表
            connection = self.connection_manager.get_instance_connection(instance_id)
            if not connection or not connection.client:
                print(f"⚠️ 无法连接到实例 {instance_id}")
                return
            
            # 获取数据库列表
            databases = await connection.client.list_database_names()
            # 过滤系统数据库
            user_dbs = [db for db in db_names if not db.startswith(("admin", "local", "config"))]
            
            if not user_dbs:
                print("⚠️ 没有找到用户数据库进行测试")
                return
            
            # 选择第一个用户数据库
            database_name = user_dbs[0]
            db = connection[database_name]
            collection_names = await db.list_collection_names()
            
            if not collection_names:
                print(f"⚠️ 数据库 {database_name} 中没有集合")
                return
            
            # 选择第一个集合进行分析
            collection_name = collection_names[0]
            
            tool = self.tools["analyze_collection"]
            result = await tool.execute({
                "instance_id": instance_id,
                "database_name": database_name,
                "collection_name": collection_name,
                "include_semantics": True,
                "include_examples": True,
                "rescan": True
            })
            
            if result and len(result) > 0:
                print(f"✅ 集合分析成功: {database_name}.{collection_name}")
                content = result[0].text[:300] + "..." if len(result[0].text) > 300 else result[0].text
                print(f"   结果预览: {content}")
            else:
                print(f"⚠️ 集合分析返回空结果")
                
        except Exception as e:
            print(f"❌ 集合分析测试失败: {e}")
    
    async def _test_query_generation(self, instance_id: str):
        """测试查询生成"""
        print(f"🤖 测试查询生成 (实例: {instance_id})...")
        
        try:
            # 使用一个通用的查询描述进行测试
            tool = self.tools["generate_query"]
            
            # 首先尝试获取一个可用的集合
            connection = self.connection_manager.get_instance_connection(instance_id)
            if not connection or not connection.client:
                print(f"⚠️ 无法连接到实例 {instance_id}")
                return
            
            # 获取数据库列表
            databases = await connection.client.list_database_names()
            user_dbs = [db for db in db_names if not db.startswith(("admin", "local", "config"))]
            
            if not user_dbs:
                print("⚠️ 没有找到用户数据库进行测试")
                return
            
            database_name = user_dbs[0]
            db = connection[database_name]
            collection_names = await db.list_collection_names()
            
            if not collection_names:
                print(f"⚠️ 数据库 {database_name} 中没有集合")
                return
            
            collection_name = collection_names[0]
            
            # 生成一个简单的查询
            result = await tool.execute({
                "instance_id": instance_id,
                "database_name": database_name,
                "collection_name": collection_name,
                "query_description": "查找所有文档，限制返回10条记录",
                "query_type": "find",
                "limit": 10
            })
            
            if result and len(result) > 0:
                print(f"✅ 查询生成成功: {database_name}.{collection_name}")
                content = result[0].text[:300] + "..." if len(result[0].text) > 300 else result[0].text
                print(f"   结果预览: {content}")
            else:
                print(f"⚠️ 查询生成返回空结果")
                
        except Exception as e:
            print(f"❌ 查询生成测试失败: {e}")
    
    async def test_tool_definitions(self):
        """测试工具定义"""
        print("📋 测试工具定义...\n")
        
        for tool_name, tool_instance in self.tools.items():
            try:
                definition = tool_instance.get_tool_definition()
                print(f"✅ {tool_name}: {definition.description}")
            except Exception as e:
                print(f"❌ {tool_name}: 获取定义失败 - {e}")
        
        print("\n✅ 工具定义测试完成\n")
    
    async def cleanup(self):
        """清理资源"""
        print("🧹 清理测试资源...")
        
        try:
            if self.connection_manager:
                await self.connection_manager.shutdown()
                print("✅ 连接已关闭")
        except Exception as e:
            print(f"⚠️ 清理资源时发生错误: {e}")
    
    async def run_all_tests(self):
        """运行所有测试"""
        print("🎯 开始QueryNest服务完整测试\n")
        print("=" * 50)
        
        try:
            # 初始化
            await self.initialize()
            
            # 测试工具定义
            await self.test_tool_definitions()
            
            # 基本功能测试
            await self.test_basic_functionality()
            
            # 高级功能测试
            await self.test_advanced_functionality()
            
            print("=" * 50)
            print("🎉 所有测试完成！")
            
        except Exception as e:
            print(f"❌ 测试过程中发生错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await self.cleanup()


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="QueryNest服务测试")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="配置文件路径 (默认: config.yaml)"
    )
    parser.add_argument(
        "--test-type",
        choices=["all", "basic", "advanced", "tools"],
        default="all",
        help="测试类型 (默认: all)"
    )
    
    args = parser.parse_args()
    
    # 检查配置文件是否存在
    if not Path(args.config).exists():
        print(f"❌ 配置文件不存在: {args.config}")
        print("请确保配置文件存在并且配置正确")
        sys.exit(1)
    
    # 创建测试器
    tester = QueryNestTester(args.config)
    
    try:
        if args.test_type == "all":
            await tester.run_all_tests()
        else:
            await tester.initialize()
            
            if args.test_type == "basic":
                await tester.test_basic_functionality()
            elif args.test_type == "advanced":
                await tester.test_advanced_functionality()
            elif args.test_type == "tools":
                await tester.test_tool_definitions()
            
            await tester.cleanup()
            
    except KeyboardInterrupt:
        print("\n⏹️ 测试被用户中断")
        await tester.cleanup()
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        await tester.cleanup()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())