# -*- coding: utf-8 -*-
"""
Pytest配置文件
"""

import pytest
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环供异步测试使用"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_config():
    """模拟配置"""
    return {
        "mongodb": {
            "instances": {
                "test_instance": {
                    "name": "test_instance",
                    "connection_string": "mongodb://localhost:27017/test",
                    "environment": "test"
                }
            }
        },
        "metadata": {
            "database_name": "querynest_test_metadata"
        },
        "security": {
            "query_timeout": 30,
            "max_result_size": 1000,
            "allowed_operations": ["find", "aggregate", "count", "distinct"]
        }
    }


# 标记异步测试
pytest_plugins = ("pytest_asyncio",)