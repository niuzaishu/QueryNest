# -*- coding: utf-8 -*-
"""
MCP工具接口定义

提供统一的工具接口规范和抽象基类
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass
import structlog
from mcp.types import Tool, TextContent

logger = structlog.get_logger(__name__)


class MCPToolInterface(ABC):
    """MCP工具接口"""
    
    @abstractmethod
    def get_tool_definition(self) -> Tool:
        """获取工具定义"""
        pass
    
    @abstractmethod
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """执行工具"""
        pass


class WorkflowAwareTool(MCPToolInterface):
    """支持工作流的工具接口"""
    
    @abstractmethod
    async def validate_workflow(self, session_id: str) -> Dict[str, Any]:
        """验证工作流状态"""
        pass
    
    @abstractmethod
    async def update_workflow(self, session_id: str, arguments: Dict[str, Any], 
                           result: List[TextContent]) -> bool:
        """更新工作流状态"""
        pass


@dataclass
class ToolValidationResult:
    """工具验证结果"""
    valid: bool
    message: str
    data: Dict[str, Any] = None
    suggestions: List[str] = None
    
    def __post_init__(self):
        if self.data is None:
            self.data = {}
        if self.suggestions is None:
            self.suggestions = []


class ValidationAwareTool(MCPToolInterface):
    """支持参数验证的工具接口"""
    
    @abstractmethod
    async def validate_arguments(self, arguments: Dict[str, Any]) -> ToolValidationResult:
        """验证工具参数"""
        pass
    
    @abstractmethod
    async def enhance_arguments(self, arguments: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        """增强工具参数"""
        pass


class ContextAwareTool(MCPToolInterface):
    """支持上下文的工具接口"""
    
    @abstractmethod
    async def get_context_dependencies(self) -> List[str]:
        """获取上下文依赖"""
        pass
    
    @abstractmethod
    async def process_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理上下文"""
        pass


class ErrorHandlingTool(MCPToolInterface):
    """支持错误处理的工具接口"""
    
    @abstractmethod
    async def handle_error(self, error: Exception, arguments: Dict[str, Any]) -> List[TextContent]:
        """处理错误"""
        pass
    
    @abstractmethod
    async def should_retry(self, error: Exception, attempt: int) -> bool:
        """是否应该重试"""
        pass
    
    @abstractmethod
    async def get_retry_delay(self, attempt: int) -> float:
        """获取重试延迟（秒）"""
        pass


class DocumentableTool(MCPToolInterface):
    """支持文档的工具接口"""
    
    @abstractmethod
    def get_documentation(self) -> str:
        """获取工具文档"""
        pass
    
    @abstractmethod
    def get_examples(self) -> List[Dict[str, Any]]:
        """获取工具示例"""
        pass


class CompositeTool(MCPToolInterface):
    """组合工具接口"""
    
    @abstractmethod
    async def get_subtool_ids(self) -> List[str]:
        """获取子工具ID列表"""
        pass
    
    @abstractmethod
    async def select_subtool(self, arguments: Dict[str, Any]) -> str:
        """选择子工具"""
        pass
    
    @abstractmethod
    async def execute_subtool(self, subtool_id: str, arguments: Dict[str, Any]) -> List[TextContent]:
        """执行子工具"""
        pass