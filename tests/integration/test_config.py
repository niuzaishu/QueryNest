"""集成测试配置"""
import os
from typing import Dict, Any

# 测试数据库配置
TEST_DB_CONFIG = {
    "host": "localhost",
    "port": 27017,
    "database": "querynest_test",
    "username": None,
    "password": None
}

# 测试实例配置
TEST_INSTANCE_CONFIG = {
    "instance_id": "test_instance",
    "name": "测试实例",
    "host": "localhost",
    "port": 27017,
    "database_type": "mongodb",
    "status": "active",
    "connection_string": "mongodb://localhost:27017"
}

# 测试数据
TEST_DATA = {
    "users": [
        {"_id": 1, "name": "张三", "age": 25, "email": "zhangsan@example.com", "department": "技术部"},
        {"_id": 2, "name": "李四", "age": 30, "email": "lisi@example.com", "department": "产品部"},
        {"_id": 3, "name": "王五", "age": 28, "email": "wangwu@example.com", "department": "技术部"},
        {"_id": 4, "name": "赵六", "age": 32, "email": "zhaoliu@example.com", "department": "市场部"}
    ],
    "orders": [
        {"_id": 1, "user_id": 1, "product": "笔记本电脑", "amount": 5999.99, "status": "completed", "created_at": "2024-01-15"},
        {"_id": 2, "user_id": 2, "product": "手机", "amount": 3999.99, "status": "pending", "created_at": "2024-01-16"},
        {"_id": 3, "user_id": 1, "product": "键盘", "amount": 299.99, "status": "completed", "created_at": "2024-01-17"},
        {"_id": 4, "user_id": 3, "product": "鼠标", "amount": 199.99, "status": "shipped", "created_at": "2024-01-18"}
    ],
    "products": [
        {"_id": 1, "name": "笔记本电脑", "category": "电子产品", "price": 5999.99, "stock": 50},
        {"_id": 2, "name": "手机", "category": "电子产品", "price": 3999.99, "stock": 100},
        {"_id": 3, "name": "键盘", "category": "配件", "price": 299.99, "stock": 200},
        {"_id": 4, "name": "鼠标", "category": "配件", "price": 199.99, "stock": 150}
    ]
}

# 测试索引配置
TEST_INDEXES = {
    "users": [
        {"keys": {"email": 1}, "unique": True},
        {"keys": {"department": 1, "age": -1}}
    ],
    "orders": [
        {"keys": {"user_id": 1}},
        {"keys": {"status": 1, "created_at": -1}}
    ],
    "products": [
        {"keys": {"category": 1}},
        {"keys": {"name": "text"}}
    ]
}