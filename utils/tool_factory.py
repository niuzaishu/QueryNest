# -*- coding: utf-8 -*-
"""
工具工厂模块

提供创建和管理MCP工具的工厂类
"""

from typing import Dict, Any, List, Optional, Union, Type
import importlib
import inspect
import os
from pathlib import Path
import structlog

from mcp_tools.interfaces import MCPToolInterface
from mcp_tools.base_tool import BaseTool, CompleteTool

logger = structlog.get_logger(__name__)


class ToolFactory:
    """工具工厂类，负责创建和管理MCP工具"""
    
    def __init__(self):
        """初始化工具工厂"""
        self._tool_registry = {}  # 工具注册表：{名称: 类}
        self._tool_instances = {}  # 工具实例表：{名称: 实例}
        self._discover_tools()
        
    def _discover_tools(self):
        """发现和注册所有工具类"""
        try:
            # 查找mcp_tools模块中的所有工具类
            tools_dir = Path(__file__).parent.parent / 'mcp_tools'
            
            # 确保目录存在
            if not tools_dir.exists() or not tools_dir.is_dir():
                logger.warning("找不到MCP工具目录", path=str(tools_dir))
                return
            
            # 扫描工具目录下的所有Python文件
            for file_path in tools_dir.glob('*.py'):
                # 跳过特殊文件
                if file_path.name in ['__init__.py', 'interfaces.py', 'base_tool.py']:
                    continue
                
                try:
                    # 计算模块名
                    module_name = f"mcp_tools.{file_path.stem}"
                    
                    # 导入模块
                    module = importlib.import_module(module_name)
                    
                    # 查找模块中的工具类
                    for name, obj in inspect.getmembers(module):
                        # 检查是否是可实例化的类且是MCPToolInterface的子类
                        if (inspect.isclass(obj) and issubclass(obj, MCPToolInterface) and 
                            obj not in [MCPToolInterface, BaseTool, CompleteTool]):
                            
                            # 推断工具名称
                            tool_name = self._infer_tool_name(obj, file_path.stem)
                            
                            # 注册工具类
                            self._tool_registry[tool_name] = obj
                            
                            logger.debug(f"已注册工具: {tool_name}", class_name=name, module=module_name)
                    
                except Exception as e:
                    logger.warning(f"导入工具模块失败: {file_path.name}", error=str(e))
            
            logger.info(f"发现了 {len(self._tool_registry)} 个工具")
            
        except Exception as e:
            logger.error("工具发现过程失败", error=str(e))
    
    def _infer_tool_name(self, tool_class, module_name) -> str:
        """推断工具名称"""
        # 首先尝试从类属性中获取
        if hasattr(tool_class, 'TOOL_NAME') and tool_class.TOOL_NAME:
            return tool_class.TOOL_NAME
            
        # 从类名中推断（去掉Tool后缀，转为蛇形命名法）
        class_name = tool_class.__name__
        if class_name.endswith('Tool'):
            class_name = class_name[:-4]
            
        # 转为蛇形命名法
        import re
        name = re.sub(r'(?<!^)(?=[A-Z])', '_', class_name).lower()
        
        # 如果模块名是单词，且不是工具名的一部分，则添加前缀
        if module_name not in ['tools', 'base', 'utils', 'core'] and module_name not in name:
            if module_name.endswith('_tool') or module_name.endswith('_tools'):
                module_prefix = module_name[:-5] if module_name.endswith('_tool') else module_name[:-6]
            else:
                module_prefix = module_name
                
            name = f"{module_prefix}_{name}"
        
        return name
    
    def create_tool(self, name: str, **kwargs) -> Optional[MCPToolInterface]:
        """创建工具实例"""
        # 如果已有实例，直接返回
        if name in self._tool_instances:
            return self._tool_instances[name]
            
        # 查找工具类
        if name not in self._tool_registry:
            logger.warning(f"找不到工具: {name}")
            return None
            
        tool_class = self._tool_registry[name]
        
        try:
            # 创建工具实例
            tool_instance = tool_class(**kwargs)
            
            # 缓存实例
            self._tool_instances[name] = tool_instance
            
            return tool_instance
            
        except Exception as e:
            logger.error(f"创建工具实例失败: {name}", error=str(e))
            return None
    
    def get_all_tools(self) -> Dict[str, MCPToolInterface]:
        """获取所有工具实例"""
        # 确保所有工具类都已实例化
        for name, cls in self._tool_registry.items():
            if name not in self._tool_instances:
                self.create_tool(name)
                
        # 返回所有工具实例的副本
        return self._tool_instances.copy()
    
    def reload_tool(self, name: str) -> bool:
        """重新加载工具"""
        if name not in self._tool_registry:
            logger.warning(f"找不到工具: {name}")
            return False
            
        # 删除现有实例
        if name in self._tool_instances:
            del self._tool_instances[name]
            
        # 重新导入模块
        try:
            tool_class = self._tool_registry[name]
            module_name = tool_class.__module__
            module = importlib.import_module(module_name)
            importlib.reload(module)
            
            # 更新工具类
            for cls_name, cls in inspect.getmembers(module, inspect.isclass):
                if cls.__name__ == tool_class.__name__:
                    self._tool_registry[name] = cls
                    break
                    
            logger.info(f"工具已重新加载: {name}")
            return True
            
        except Exception as e:
            logger.error(f"重新加载工具失败: {name}", error=str(e))
            return False
    
    def register_tool(self, name: str, tool_class: Type[MCPToolInterface]) -> bool:
        """手动注册工具类"""
        if not issubclass(tool_class, MCPToolInterface):
            logger.error(f"无效的工具类: {tool_class.__name__}，必须是MCPToolInterface的子类")
            return False
            
        self._tool_registry[name] = tool_class
        
        # 清除现有实例
        if name in self._tool_instances:
            del self._tool_instances[name]
            
        logger.info(f"已手动注册工具: {name}", class_name=tool_class.__name__)
        return True


# 全局工具工厂实例
_tool_factory = None


def get_tool_factory() -> ToolFactory:
    """获取全局工具工厂实例"""
    global _tool_factory
    if _tool_factory is None:
        _tool_factory = ToolFactory()
    return _tool_factory