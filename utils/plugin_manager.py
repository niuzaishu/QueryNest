# -*- coding: utf-8 -*-
"""
插件管理器

提供插件发现、加载和管理功能
"""

from typing import Dict, Any, List, Optional, Union, Type, Callable
import importlib
import inspect
import os
from pathlib import Path
import structlog
import json
import sys

logger = structlog.get_logger(__name__)


class Plugin:
    """插件基类"""
    
    def __init__(self, id: str, name: str, version: str, description: str):
        self.id = id
        self.name = name
        self.version = version
        self.description = description
        self.enabled = True
    
    def activate(self):
        """激活插件"""
        pass
    
    def deactivate(self):
        """停用插件"""
        pass


class PluginManager:
    """插件管理器"""
    
    def __init__(self, plugin_dirs: List[str] = None):
        """
        初始化插件管理器
        
        Args:
            plugin_dirs: 插件目录列表，默认为项目根目录下的plugins目录
        """
        self.plugins: Dict[str, Plugin] = {}
        self.plugin_dirs = plugin_dirs or []
        
        # 默认查找plugins目录
        default_dir = Path(__file__).parent.parent / 'plugins'
        if default_dir.exists() and default_dir.is_dir() and str(default_dir) not in self.plugin_dirs:
            self.plugin_dirs.append(str(default_dir))
            
        # 查找环境变量中定义的插件目录
        if 'QUERYNEST_PLUGIN_PATH' in os.environ:
            env_paths = os.environ['QUERYNEST_PLUGIN_PATH'].split(os.pathsep)
            for path in env_paths:
                if path and path not in self.plugin_dirs:
                    self.plugin_dirs.append(path)
    
    def discover_plugins(self):
        """发现所有可用插件"""
        logger.info(f"开始发现插件，搜索目录: {self.plugin_dirs}")
        
        for plugin_dir in self.plugin_dirs:
            path = Path(plugin_dir)
            
            if not path.exists() or not path.is_dir():
                logger.warning(f"插件目录不存在或不是目录: {plugin_dir}")
                continue
                
            logger.debug(f"搜索插件目录: {plugin_dir}")
            
            # 遍历目录下的子目录
            for item in path.iterdir():
                if not item.is_dir():
                    continue
                    
                # 查找manifest.json
                manifest_path = item / 'manifest.json'
                if not manifest_path.exists():
                    continue
                    
                try:
                    # 加载清单文件
                    with open(manifest_path, 'r', encoding='utf-8') as f:
                        manifest = json.load(f)
                        
                    # 验证清单
                    if not self._validate_manifest(manifest):
                        logger.warning(f"无效的插件清单: {manifest_path}")
                        continue
                        
                    # 加载插件
                    plugin_id = manifest['id']
                    if plugin_id in self.plugins:
                        logger.warning(f"插件ID冲突: {plugin_id}，跳过加载")
                        continue
                        
                    # 插入模块路径
                    if str(item) not in sys.path:
                        sys.path.insert(0, str(item))
                        
                    # 导入插件模块
                    main_module = manifest.get('main', 'main')
                    if not main_module.endswith('.py'):
                        main_module += '.py'
                        
                    module_path = item / main_module
                    if not module_path.exists():
                        logger.warning(f"找不到插件主模块: {module_path}")
                        continue
                        
                    # 计算模块名
                    module_name = f"plugin_{plugin_id}"
                    
                    try:
                        # 直接导入文件
                        spec = importlib.util.spec_from_file_location(module_name, module_path)
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        
                        # 查找插件类
                        plugin_class = None
                        for name, obj in inspect.getmembers(module):
                            if inspect.isclass(obj) and issubclass(obj, Plugin) and obj != Plugin:
                                plugin_class = obj
                                break
                                
                        if plugin_class is None:
                            logger.warning(f"插件模块中没有发现Plugin的子类: {module_path}")
                            continue
                            
                        # 创建插件实例
                        plugin = plugin_class(
                            id=plugin_id,
                            name=manifest.get('name', plugin_id),
                            version=manifest.get('version', '0.1.0'),
                            description=manifest.get('description', '')
                        )
                        
                        # 注册插件
                        self.plugins[plugin_id] = plugin
                        logger.info(f"已加载插件: {plugin_id} ({plugin.name} v{plugin.version})")
                        
                    except Exception as e:
                        logger.error(f"加载插件失败: {plugin_id}", error=str(e))
                    
                except Exception as e:
                    logger.warning(f"解析插件清单失败: {manifest_path}", error=str(e))
        
        logger.info(f"插件发现完成，共找到 {len(self.plugins)} 个插件")
    
    def _validate_manifest(self, manifest: Dict[str, Any]) -> bool:
        """验证插件清单"""
        required_fields = ['id', 'name', 'version']
        for field in required_fields:
            if field not in manifest:
                logger.warning(f"插件清单缺少必需字段: {field}")
                return False
                
        return True
    
    def activate_plugin(self, plugin_id: str) -> bool:
        """激活插件"""
        if plugin_id not in self.plugins:
            logger.warning(f"未找到插件: {plugin_id}")
            return False
            
        plugin = self.plugins[plugin_id]
        
        try:
            plugin.activate()
            plugin.enabled = True
            logger.info(f"已激活插件: {plugin_id}")
            return True
        except Exception as e:
            logger.error(f"激活插件失败: {plugin_id}", error=str(e))
            return False
    
    def deactivate_plugin(self, plugin_id: str) -> bool:
        """停用插件"""
        if plugin_id not in self.plugins:
            logger.warning(f"未找到插件: {plugin_id}")
            return False
            
        plugin = self.plugins[plugin_id]
        
        try:
            plugin.deactivate()
            plugin.enabled = False
            logger.info(f"已停用插件: {plugin_id}")
            return True
        except Exception as e:
            logger.error(f"停用插件失败: {plugin_id}", error=str(e))
            return False
    
    def get_plugin(self, plugin_id: str) -> Optional[Plugin]:
        """获取插件实例"""
        return self.plugins.get(plugin_id)
    
    def get_active_plugins(self) -> Dict[str, Plugin]:
        """获取所有已激活的插件"""
        return {id: plugin for id, plugin in self.plugins.items() if plugin.enabled}
    
    def activate_all(self):
        """激活所有插件"""
        for plugin_id in self.plugins:
            self.activate_plugin(plugin_id)
    
    def deactivate_all(self):
        """停用所有插件"""
        for plugin_id in self.plugins:
            self.deactivate_plugin(plugin_id)


# 全局插件管理器实例
_plugin_manager = None


def get_plugin_manager() -> PluginManager:
    """获取全局插件管理器实例"""
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager