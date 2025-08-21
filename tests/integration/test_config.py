# -*- coding: utf-8 -*-
"""集成测试配置"""

# 测试实例配置
TEST_INSTANCE_CONFIG = {
    "instance_name": "local_test",
    "connection_string": "mongodb://localhost:27017/querynest_test",
    "database_name": "querynest_test"
}

# 测试数据
TEST_DATA = {
    "collections": [
        {
            "name": "test_collection",
            "documents": [
                {"_id": 1, "name": "测试文档1", "type": "test", "status": "active"},
                {"_id": 2, "name": "测试文档2", "type": "example", "status": "inactive"},
                {"_id": 3, "name": "测试文档3", "type": "demo", "status": "active"}
            ]
        }
    ]
}