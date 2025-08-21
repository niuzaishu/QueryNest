# -*- coding: utf-8 -*-
"""集成测试基类"""

import pytest
import asyncio
from typing import Dict, Any, Optional
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config import QueryNestConfig
from database.connection_manager import ConnectionManager
from database.metadata_manager_file import FileBasedMetadataManager
from scanner.semantic_analyzer import SemanticAnalyzer


class BaseIntegrationTest:
    """集成测试基类"""
    
    def setup_method(self):
        """设置方法"""
        self.config = None
        self.connection_manager = None
        self.metadata_manager = None
        self.semantic_analyzer = None
        
    async def async_setup_method(self):
        """异步设置方法"""
        try:
            # 加载配置
            self.config = QueryNestConfig.from_yaml('config.yaml')
            
            # 初始化连接管理器
            self.connection_manager = ConnectionManager(self.config)
            
            # 初始化元数据管理器
            self.metadata_manager = FileBasedMetadataManager(self.connection_manager)
            
            # 初始化语义分析器
            self.semantic_analyzer = SemanticAnalyzer(self.metadata_manager, self.connection_manager)
            
        except Exception as e:
            pytest.skip(f"Integration test setup failed: {e}")
            
    async def async_teardown_method(self):
        """异步清理方法"""
        if self.connection_manager:
            await self.connection_manager.shutdown()