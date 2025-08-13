# -*- coding: utf-8 -*-
"""
示例插件

展示QueryNest插件系统的基本用法
"""

from utils.plugin_manager import Plugin
from mcp_tools.interfaces import MCPToolInterface
from mcp.types import Tool, TextContent
from typing import Dict, Any, List


class ExampleTool(MCPToolInterface):
    """示例工具"""
    
    TOOL_NAME = "example_tool"  # 工具名称，会被自动注册
    
    def get_tool_definition(self) -> Tool:
        """获取工具定义"""
        return Tool(
            name="example_tool",
            description="示例插件提供的工具，展示插件系统功能",
            parameters={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "要显示的消息"
                    }
                },
                "required": ["message"]
            }
        )
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """执行工具"""
        message = arguments.get("message", "未提供消息")
        
        return [TextContent(
            type="text",
            text=f"示例插件响应: {message}\n\n"
                 f"这是通过插件系统动态加载的工具。"
        )]


class ExamplePlugin(Plugin):
    """示例插件类"""
    
    def activate(self):
        """激活插件"""
        print(f"示例插件已激活: {self.name} v{self.version}")
        
        # 注册工具
        from utils.tool_factory import get_tool_factory
        tool_factory = get_tool_factory()
        tool_factory.register_tool(ExampleTool.TOOL_NAME, ExampleTool)
        
    def deactivate(self):
        """停用插件"""
        print(f"示例插件已停用: {self.name}")