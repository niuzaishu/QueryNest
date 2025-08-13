# -*- coding: utf-8 -*-
"""
MCP工具工厂 - 解决循环依赖问题的依赖注入容器
"""

from typing import Dict, Any, Optional, Type, TypeVar
import structlog
from abc import ABC, abstractmethod

from database.connection_manager import ConnectionManager
from database.metadata_manager import MetadataManager
from scanner.semantic_analyzer import SemanticAnalyzer

logger = structlog.get_logger(__name__)

T = TypeVar('T')


class DependencyContainer:
    """轻量级依赖注入容器"""
    
    def __init__(self):
        self._instances: Dict[str, Any] = {}
        self._factories: Dict[str, callable] = {}
        self._singletons: Dict[str, Any] = {}
    
    def register_instance(self, name: str, instance: Any):
        """注册实例"""
        self._instances[name] = instance
    
    def register_factory(self, name: str, factory: callable):
        """注册工厂函数"""
        self._factories[name] = factory
    
    def register_singleton(self, name: str, factory: callable):
        """注册单例工厂"""
        if name not in self._singletons:
            self._singletons[name] = factory()
        return self._singletons[name]
    
    def get(self, name: str) -> Any:
        """获取依赖"""
        # 先检查实例
        if name in self._instances:
            return self._instances[name]
        
        # 再检查单例
        if name in self._singletons:
            return self._singletons[name]
        
        # 最后检查工厂
        if name in self._factories:
            return self._factories[name]()
        
        raise ValueError(f"Dependency '{name}' not found")
    
    def has(self, name: str) -> bool:
        """检查依赖是否存在"""
        return (name in self._instances or 
                name in self._factories or 
                name in self._singletons)


class ToolFactory:
    """MCP工具工厂"""
    
    def __init__(self, container: DependencyContainer):
        self.container = container
        self._tool_registry: Dict[str, Type] = {}
    
    def register_tool(self, tool_name: str, tool_class: Type):
        """注册工具类"""
        self._tool_registry[tool_name] = tool_class
    
    def create_tool(self, tool_name: str, **kwargs) -> Any:
        """创建工具实例"""
        if tool_name not in self._tool_registry:
            raise ValueError(f"Tool '{tool_name}' not registered")
        
        tool_class = self._tool_registry[tool_name]
        
        # 自动注入依赖
        dependencies = self._resolve_dependencies(tool_class, **kwargs)
        
        try:
            return tool_class(**dependencies)
        except Exception as e:
            logger.error(f"Failed to create tool '{tool_name}'", error=str(e))
            raise
    
    def _resolve_dependencies(self, tool_class: Type, **overrides) -> Dict[str, Any]:
        """解析工具类的依赖"""
        import inspect
        
        # 获取构造函数签名
        sig = inspect.signature(tool_class.__init__)
        dependencies = {}
        
        for param_name, param in sig.parameters.items():
            if param_name == 'self':
                continue
            
            # 优先使用覆盖参数
            if param_name in overrides:
                dependencies[param_name] = overrides[param_name]
                continue
            
            # 尝试从容器获取依赖
            if self.container.has(param_name):
                dependencies[param_name] = self.container.get(param_name)
                continue
            
            # 检查是否有默认值
            if param.default != inspect.Parameter.empty:
                dependencies[param_name] = param.default
                continue
            
            # 如果是可选参数，设为None
            if param.annotation:
                from typing import Union, get_origin, get_args
                if get_origin(param.annotation) is Union:
                    if type(None) in get_args(param.annotation):
                        dependencies[param_name] = None
                        continue
            
            logger.warning(f"Cannot resolve dependency '{param_name}' for {tool_class.__name__}")
        
        return dependencies
    
    def get_registered_tools(self) -> Dict[str, Type]:
        """获取已注册的工具"""
        return self._tool_registry.copy()


class ToolConfigurationBuilder:
    """工具配置构建器"""
    
    def __init__(self):
        self.container = DependencyContainer()
        self.factory = ToolFactory(self.container)
    
    def with_connection_manager(self, connection_manager: ConnectionManager):
        """注入连接管理器"""
        self.container.register_instance('connection_manager', connection_manager)
        return self
    
    def with_metadata_manager(self, metadata_manager: MetadataManager):
        """注入元数据管理器"""
        self.container.register_instance('metadata_manager', metadata_manager)
        return self
    
    def with_semantic_analyzer(self, semantic_analyzer: SemanticAnalyzer):
        """注入语义分析器"""
        self.container.register_instance('semantic_analyzer', semantic_analyzer)
        return self
    
    def with_workflow_manager(self, workflow_manager):
        """注入工作流管理器"""
        self.container.register_instance('workflow_manager', workflow_manager)
        return self
    
    def register_tools(self):
        """注册所有工具类"""
        # 延迟导入避免循环依赖
        from mcp_tools.instance_discovery import InstanceDiscoveryTool
        from mcp_tools.instance_selection import InstanceSelectionTool
        from mcp_tools.database_discovery import DatabaseDiscoveryTool
        from mcp_tools.database_selection import DatabaseSelectionTool
        from mcp_tools.collection_analysis import CollectionAnalysisTool
        from mcp_tools.query_generation import QueryGenerationTool
        from mcp_tools.query_confirmation import QueryConfirmationTool
        from mcp_tools.unified_semantic_tool import UnifiedSemanticTool
        from mcp_tools.workflow_management import WorkflowStatusTool, WorkflowResetTool
        
        # 注册工具类
        tools = {
            'discover_instances': InstanceDiscoveryTool,
            'select_instance': InstanceSelectionTool,
            'discover_databases': DatabaseDiscoveryTool,
            'select_database': DatabaseSelectionTool,
            'analyze_collection': CollectionAnalysisTool,
            'generate_query': QueryGenerationTool,
            'confirm_query': QueryConfirmationTool,
            'unified_semantic_operations': UnifiedSemanticTool,
            'workflow_status': WorkflowStatusTool,
            'workflow_reset': WorkflowResetTool,
        }
        
        for tool_name, tool_class in tools.items():
            self.factory.register_tool(tool_name, tool_class)
        
        return self
    
    def build(self) -> ToolFactory:
        """构建工具工厂"""
        return self.factory


# 全局工具工厂实例（单例模式）
_tool_factory: Optional[ToolFactory] = None


def get_tool_factory() -> ToolFactory:
    """获取全局工具工厂实例"""
    global _tool_factory
    if _tool_factory is None:
        raise RuntimeError("Tool factory not initialized. Call setup_tool_factory() first.")
    return _tool_factory


def setup_tool_factory(connection_manager: ConnectionManager,
                      metadata_manager: MetadataManager,
                      semantic_analyzer: SemanticAnalyzer,
                      workflow_manager=None) -> ToolFactory:
    """设置全局工具工厂"""
    global _tool_factory
    
    builder = ToolConfigurationBuilder()
    builder.with_connection_manager(connection_manager)
    builder.with_metadata_manager(metadata_manager)
    builder.with_semantic_analyzer(semantic_analyzer)
    
    if workflow_manager:
        builder.with_workflow_manager(workflow_manager)
    
    builder.register_tools()
    _tool_factory = builder.build()
    
    logger.info("Tool factory initialized successfully")
    return _tool_factory


def reset_tool_factory():
    """重置工具工厂（主要用于测试）"""
    global _tool_factory
    _tool_factory = None