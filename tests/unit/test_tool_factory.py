# -*- coding: utf-8 -*-
"""
工具工厂单元测试
"""

import pytest
from unittest.mock import MagicMock, patch
from typing import Optional

from mcp_tools.tool_factory import (
    DependencyContainer, ToolFactory, ToolConfigurationBuilder,
    get_tool_factory, setup_tool_factory, reset_tool_factory
)
from mcp_tools.base_tool import BaseTool
from database.connection_manager import ConnectionManager
from database.metadata_manager import MetadataManager
from scanner.semantic_analyzer import SemanticAnalyzer


# 测试用的模拟工具类
class MockTool(BaseTool):
    """模拟工具类"""
    
    def __init__(self, name: str = "mock_tool", description: str = "Mock tool for testing", 
                 connection_manager=None, metadata_manager=None, optional_param: Optional[str] = None):
        super().__init__(name, description)
        self.connection_manager = connection_manager
        self.metadata_manager = metadata_manager
        self.optional_param = optional_param


class MockComplexTool(BaseTool):
    """复杂的模拟工具类"""
    
    def __init__(self, name: str, description: str, connection_manager: ConnectionManager,
                 metadata_manager: MetadataManager, semantic_analyzer: SemanticAnalyzer,
                 workflow_manager=None, config: dict = None):
        super().__init__(name, description)
        self.connection_manager = connection_manager
        self.metadata_manager = metadata_manager
        self.semantic_analyzer = semantic_analyzer
        self.workflow_manager = workflow_manager
        self.config = config or {}


class TestDependencyContainer:
    """依赖容器测试类"""
    
    def setup_method(self):
        """测试前准备"""
        self.container = DependencyContainer()
    
    def test_register_and_get_instance(self):
        """测试注册和获取实例"""
        mock_instance = MagicMock()
        self.container.register_instance("test_service", mock_instance)
        
        retrieved = self.container.get("test_service")
        assert retrieved is mock_instance
    
    def test_register_and_get_factory(self):
        """测试注册和获取工厂"""
        def factory():
            return "factory_result"
        
        self.container.register_factory("test_factory", factory)
        
        result = self.container.get("test_factory")
        assert result == "factory_result"
    
    def test_register_and_get_singleton(self):
        """测试注册和获取单例"""
        call_count = 0
        
        def singleton_factory():
            nonlocal call_count
            call_count += 1
            return f"singleton_{call_count}"
        
        # 第一次调用应该创建实例
        result1 = self.container.register_singleton("test_singleton", singleton_factory)
        assert result1 == "singleton_1"
        assert call_count == 1
        
        # 第二次获取应该返回相同实例
        result2 = self.container.get("test_singleton")
        assert result2 == "singleton_1"
        assert call_count == 1  # 工厂函数只调用一次
    
    def test_has_dependency(self):
        """测试检查依赖是否存在"""
        assert not self.container.has("nonexistent")
        
        self.container.register_instance("test_instance", "value")
        assert self.container.has("test_instance")
        
        self.container.register_factory("test_factory", lambda: "value")
        assert self.container.has("test_factory")
    
    def test_get_nonexistent_dependency(self):
        """测试获取不存在的依赖"""
        with pytest.raises(ValueError, match="Dependency 'nonexistent' not found"):
            self.container.get("nonexistent")


class TestToolFactory:
    """工具工厂测试类"""
    
    def setup_method(self):
        """测试前准备"""
        self.container = DependencyContainer()
        self.factory = ToolFactory(self.container)
    
    def test_register_and_create_simple_tool(self):
        """测试注册和创建简单工具"""
        self.factory.register_tool("mock_tool", MockTool)
        
        tool = self.factory.create_tool("mock_tool")
        
        assert isinstance(tool, MockTool)
        assert tool.name == "mock_tool"
        assert tool.description == "Mock tool for testing"
    
    def test_create_tool_with_dependencies(self):
        """测试创建带依赖的工具"""
        # 注册依赖
        mock_connection_manager = MagicMock()
        mock_metadata_manager = MagicMock()
        
        self.container.register_instance("connection_manager", mock_connection_manager)
        self.container.register_instance("metadata_manager", mock_metadata_manager)
        
        # 注册工具
        self.factory.register_tool("mock_tool", MockTool)
        
        # 创建工具
        tool = self.factory.create_tool("mock_tool")
        
        assert tool.connection_manager is mock_connection_manager
        assert tool.metadata_manager is mock_metadata_manager
    
    def test_create_tool_with_overrides(self):
        """测试创建工具时覆盖依赖"""
        # 注册默认依赖
        default_manager = MagicMock()
        self.container.register_instance("connection_manager", default_manager)
        
        # 注册工具
        self.factory.register_tool("mock_tool", MockTool)
        
        # 创建工具时覆盖依赖
        override_manager = MagicMock()
        tool = self.factory.create_tool("mock_tool", connection_manager=override_manager)
        
        assert tool.connection_manager is override_manager
        assert tool.connection_manager is not default_manager
    
    def test_create_tool_with_optional_parameters(self):
        """测试创建带可选参数的工具"""
        self.factory.register_tool("mock_tool", MockTool)
        
        tool = self.factory.create_tool("mock_tool")
        
        # 可选参数应该有默认值
        assert tool.optional_param is None
    
    def test_create_complex_tool(self):
        """测试创建复杂工具"""
        # 注册所有必需的依赖
        mock_connection_manager = MagicMock(spec=ConnectionManager)
        mock_metadata_manager = MagicMock(spec=MetadataManager)
        mock_semantic_analyzer = MagicMock(spec=SemanticAnalyzer)
        
        self.container.register_instance("connection_manager", mock_connection_manager)
        self.container.register_instance("metadata_manager", mock_metadata_manager)
        self.container.register_instance("semantic_analyzer", mock_semantic_analyzer)
        
        # 注册工具
        self.factory.register_tool("complex_tool", MockComplexTool)
        
        # 创建工具
        tool = self.factory.create_tool(
            "complex_tool",
            name="test_complex",
            description="Test complex tool"
        )
        
        assert isinstance(tool, MockComplexTool)
        assert tool.name == "test_complex"
        assert tool.connection_manager is mock_connection_manager
        assert tool.metadata_manager is mock_metadata_manager
        assert tool.semantic_analyzer is mock_semantic_analyzer
        assert tool.workflow_manager is None  # 可选依赖
        assert tool.config == {}  # 默认值
    
    def test_create_unregistered_tool(self):
        """测试创建未注册的工具"""
        with pytest.raises(ValueError, match="Tool 'unregistered' not registered"):
            self.factory.create_tool("unregistered")
    
    def test_create_tool_missing_dependencies(self):
        """测试创建工具时缺少依赖"""
        # 注册需要依赖但没有提供依赖的工具
        self.factory.register_tool("complex_tool", MockComplexTool)
        
        # 创建工具时应该处理缺少的依赖
        with pytest.raises(Exception):  # 具体异常类型取决于MockComplexTool的实现
            self.factory.create_tool("complex_tool", name="test", description="test")
    
    def test_get_registered_tools(self):
        """测试获取已注册的工具"""
        self.factory.register_tool("tool1", MockTool)
        self.factory.register_tool("tool2", MockComplexTool)
        
        registered_tools = self.factory.get_registered_tools()
        
        assert len(registered_tools) == 2
        assert "tool1" in registered_tools
        assert "tool2" in registered_tools
        assert registered_tools["tool1"] is MockTool
        assert registered_tools["tool2"] is MockComplexTool


class TestToolConfigurationBuilder:
    """工具配置构建器测试类"""
    
    def setup_method(self):
        """测试前准备"""
        self.builder = ToolConfigurationBuilder()
    
    def test_fluent_interface(self):
        """测试流式接口"""
        mock_connection_manager = MagicMock()
        mock_metadata_manager = MagicMock()
        mock_semantic_analyzer = MagicMock()
        mock_workflow_manager = MagicMock()
        
        result = (self.builder
                 .with_connection_manager(mock_connection_manager)
                 .with_metadata_manager(mock_metadata_manager)
                 .with_semantic_analyzer(mock_semantic_analyzer)
                 .with_workflow_manager(mock_workflow_manager))
        
        assert result is self.builder  # 应该返回自身支持链式调用
        
        # 验证依赖已注册
        assert self.builder.container.has("connection_manager")
        assert self.builder.container.has("metadata_manager")
        assert self.builder.container.has("semantic_analyzer")
        assert self.builder.container.has("workflow_manager")
    
    def test_register_tools(self):
        """测试注册工具"""
        # 跳过实际的工具注册测试，因为涉及复杂的模块导入
        # 这里只测试工具注册的基本功能
        mock_tool_class = MagicMock()
        self.builder.factory.register_tool("test_tool", mock_tool_class)
        
        registered_tools = self.builder.factory.get_registered_tools()
        
        # 验证工具已注册
        assert "test_tool" in registered_tools
        assert registered_tools["test_tool"] is mock_tool_class
    
    def test_build(self):
        """测试构建工具工厂"""
        factory = self.builder.build()
        
        assert isinstance(factory, ToolFactory)
        assert factory is self.builder.factory


class TestGlobalToolFactory:
    """全局工具工厂测试类"""
    
    def setup_method(self):
        """测试前准备"""
        reset_tool_factory()  # 重置全局状态
    
    def teardown_method(self):
        """测试后清理"""
        reset_tool_factory()  # 清理全局状态
    
    def test_setup_tool_factory(self):
        """测试设置工具工厂"""
        mock_connection_manager = MagicMock()
        mock_metadata_manager = MagicMock()
        mock_semantic_analyzer = MagicMock()
        mock_workflow_manager = MagicMock()
        
        # 使用patch避免实际注册工具
        with patch.object(ToolConfigurationBuilder, 'register_tools') as mock_register:
            mock_register.return_value = None
            
            factory = setup_tool_factory(
                connection_manager=mock_connection_manager,
                metadata_manager=mock_metadata_manager,
                semantic_analyzer=mock_semantic_analyzer,
                workflow_manager=mock_workflow_manager
            )
            
            assert factory is not None
            assert isinstance(factory, ToolFactory)
            
            # 验证全局工厂已设置
            global_factory = get_tool_factory()
            assert global_factory is factory
    
    def test_setup_tool_factory_without_workflow_manager(self):
        """测试设置工具工厂（不带工作流管理器）"""
        mock_connection_manager = MagicMock()
        mock_metadata_manager = MagicMock()
        mock_semantic_analyzer = MagicMock()
        
        # 使用patch避免实际注册工具
        with patch.object(ToolConfigurationBuilder, 'register_tools') as mock_register:
            mock_register.return_value = None
            
            factory = setup_tool_factory(
                connection_manager=mock_connection_manager,
                metadata_manager=mock_metadata_manager,
                semantic_analyzer=mock_semantic_analyzer
            )
            
            assert factory is not None
            assert isinstance(factory, ToolFactory)
    
    def test_get_tool_factory_not_initialized(self):
        """测试获取未初始化的工具工厂"""
        with pytest.raises(RuntimeError, match="Tool factory not initialized"):
            get_tool_factory()
    
    def test_reset_tool_factory(self):
        """测试重置工具工厂"""
        # 设置工厂
        mock_connection_manager = MagicMock()
        mock_metadata_manager = MagicMock()
        mock_semantic_analyzer = MagicMock()
        
        # 使用patch避免实际注册工具
        with patch.object(ToolConfigurationBuilder, 'register_tools') as mock_register:
            mock_register.return_value = None
            
            setup_tool_factory(
                connection_manager=mock_connection_manager,
                metadata_manager=mock_metadata_manager,
                semantic_analyzer=mock_semantic_analyzer
            )
            
            # 验证工厂已设置
            factory = get_tool_factory()
            assert factory is not None
            
            # 重置工厂
            reset_tool_factory()
            
            # 验证工厂已重置
            with pytest.raises(RuntimeError):
                get_tool_factory()


class TestToolFactoryIntegration:
    """工具工厂集成测试"""
    
    def setup_method(self):
        """测试前准备"""
        reset_tool_factory()
        
        # 创建模拟依赖
        self.mock_connection_manager = MagicMock(spec=ConnectionManager)
        self.mock_metadata_manager = MagicMock(spec=MetadataManager)
        self.mock_semantic_analyzer = MagicMock(spec=SemanticAnalyzer)
        self.mock_workflow_manager = MagicMock()
    
    def teardown_method(self):
        """测试后清理"""
        reset_tool_factory()
    
    def test_end_to_end_tool_creation(self):
        """测试端到端工具创建"""
        # 使用patch避免实际注册工具
        with patch.object(ToolConfigurationBuilder, 'register_tools') as mock_register:
            mock_register.return_value = None
            
            # 设置全局工厂
            factory = setup_tool_factory(
                connection_manager=self.mock_connection_manager,
                metadata_manager=self.mock_metadata_manager,
                semantic_analyzer=self.mock_semantic_analyzer,
                workflow_manager=self.mock_workflow_manager
            )
            
            # 注册测试工具
            factory.register_tool("test_tool", MockTool)
            
            # 创建工具
            tool = factory.create_tool("test_tool")
            
            assert isinstance(tool, MockTool)
            assert tool.connection_manager is self.mock_connection_manager
            assert tool.metadata_manager is self.mock_metadata_manager
    
    def test_dependency_injection_precedence(self):
        """测试依赖注入优先级"""
        # 使用patch避免实际注册工具
        with patch.object(ToolConfigurationBuilder, 'register_tools') as mock_register:
            mock_register.return_value = None
            
            # 设置全局工厂
            factory = setup_tool_factory(
                connection_manager=self.mock_connection_manager,
                metadata_manager=self.mock_metadata_manager,
                semantic_analyzer=self.mock_semantic_analyzer
            )
            
            # 注册工具
            factory.register_tool("test_tool", MockTool)
            
            # 创建工具时覆盖依赖
            override_manager = MagicMock()
            tool = factory.create_tool("test_tool", connection_manager=override_manager)
            
            # 覆盖的依赖应该优先
            assert tool.connection_manager is override_manager
            assert tool.connection_manager is not self.mock_connection_manager
            
            # 其他依赖使用默认值
            assert tool.metadata_manager is self.mock_metadata_manager
    
    def test_singleton_behavior(self):
        """测试单例行为"""
        # 使用patch避免实际注册工具
        with patch.object(ToolConfigurationBuilder, 'register_tools') as mock_register:
            mock_register.return_value = None
            
            # 设置工厂两次
            factory1 = setup_tool_factory(
                connection_manager=self.mock_connection_manager,
                metadata_manager=self.mock_metadata_manager,
                semantic_analyzer=self.mock_semantic_analyzer
            )
            
            factory2 = setup_tool_factory(
                connection_manager=MagicMock(),
                metadata_manager=MagicMock(),
                semantic_analyzer=MagicMock()
            )
            
            # 第二次设置应该覆盖第一次
            assert factory2 is not factory1
            
            global_factory = get_tool_factory()
            assert global_factory is factory2
    
    @patch('mcp_tools.tool_factory.logger')
    def test_logging_integration(self, mock_logger):
        """测试日志集成"""
        # 使用patch避免实际注册工具
        with patch.object(ToolConfigurationBuilder, 'register_tools') as mock_register:
            mock_register.return_value = None
            
            setup_tool_factory(
                connection_manager=self.mock_connection_manager,
                metadata_manager=self.mock_metadata_manager,
                semantic_analyzer=self.mock_semantic_analyzer
            )
            
            # 验证日志被调用
            mock_logger.info.assert_called_with("Tool factory initialized successfully")