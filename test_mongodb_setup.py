#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MongoDB测试设置脚本
用于验证MongoDB连接并插入测试数据
"""

import sys
import os
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
import time

def test_mongodb_connection(host='localhost', port=27017, timeout=5):
    """
    测试MongoDB连接
    """
    try:
        client = MongoClient(host, port, serverSelectionTimeoutMS=timeout*1000)
        # 测试连接
        client.admin.command('ping')
        print(f"✓ MongoDB连接成功: {host}:{port}")
        return client
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        print(f"✗ MongoDB连接失败: {e}")
        return None

def insert_test_data(client):
    """
    插入测试数据
    """
    try:
        # 创建测试数据库和集合
        db = client['querynest_test']
        
        # 用户集合测试数据
        users_collection = db['users']
        users_data = [
            {"_id": 1, "name": "张三", "age": 25, "email": "zhangsan@example.com", "department": "技术部"},
            {"_id": 2, "name": "李四", "age": 30, "email": "lisi@example.com", "department": "产品部"},
            {"_id": 3, "name": "王五", "age": 28, "email": "wangwu@example.com", "department": "技术部"},
            {"_id": 4, "name": "赵六", "age": 35, "email": "zhaoliu@example.com", "department": "运营部"},
            {"_id": 5, "name": "钱七", "age": 27, "email": "qianqi@example.com", "department": "技术部"}
        ]
        
        # 清空现有数据
        users_collection.delete_many({})
        # 插入测试数据
        users_collection.insert_many(users_data)
        print(f"✓ 插入用户测试数据: {len(users_data)} 条记录")
        
        # 产品集合测试数据
        products_collection = db['products']
        products_data = [
            {"_id": 1, "name": "笔记本电脑", "price": 5999.99, "category": "电子产品", "stock": 50},
            {"_id": 2, "name": "无线鼠标", "price": 99.99, "category": "电子产品", "stock": 200},
            {"_id": 3, "name": "机械键盘", "price": 299.99, "category": "电子产品", "stock": 80},
            {"_id": 4, "name": "显示器", "price": 1299.99, "category": "电子产品", "stock": 30},
            {"_id": 5, "name": "耳机", "price": 199.99, "category": "电子产品", "stock": 120}
        ]
        
        products_collection.delete_many({})
        products_collection.insert_many(products_data)
        print(f"✓ 插入产品测试数据: {len(products_data)} 条记录")
        
        # 订单集合测试数据
        orders_collection = db['orders']
        orders_data = [
            {"_id": 1, "user_id": 1, "product_id": 1, "quantity": 1, "total": 5999.99, "status": "已完成"},
            {"_id": 2, "user_id": 2, "product_id": 2, "quantity": 2, "total": 199.98, "status": "处理中"},
            {"_id": 3, "user_id": 3, "product_id": 3, "quantity": 1, "total": 299.99, "status": "已完成"},
            {"_id": 4, "user_id": 1, "product_id": 4, "quantity": 1, "total": 1299.99, "status": "已发货"},
            {"_id": 5, "user_id": 4, "product_id": 5, "quantity": 3, "total": 599.97, "status": "已完成"}
        ]
        
        orders_collection.delete_many({})
        orders_collection.insert_many(orders_data)
        print(f"✓ 插入订单测试数据: {len(orders_data)} 条记录")
        
        # 创建索引
        users_collection.create_index("email", unique=True)
        users_collection.create_index("department")
        products_collection.create_index("category")
        products_collection.create_index("price")
        orders_collection.create_index("user_id")
        orders_collection.create_index("status")
        print("✓ 创建索引完成")
        
        # 验证数据
        user_count = users_collection.count_documents({})
        product_count = products_collection.count_documents({})
        order_count = orders_collection.count_documents({})
        
        print(f"\n数据验证:")
        print(f"  用户数量: {user_count}")
        print(f"  产品数量: {product_count}")
        print(f"  订单数量: {order_count}")
        
        return True
        
    except Exception as e:
        print(f"✗ 插入测试数据失败: {e}")
        return False

def main():
    print("MongoDB测试设置开始...")
    print("=" * 50)
    
    # 等待MongoDB启动
    print("等待MongoDB服务启动...")
    max_retries = 10
    retry_count = 0
    client = None
    
    while retry_count < max_retries:
        client = test_mongodb_connection()
        if client:
            break
        retry_count += 1
        print(f"重试 {retry_count}/{max_retries}...")
        time.sleep(2)
    
    if not client:
        print("✗ 无法连接到MongoDB，请确保MongoDB服务正在运行")
        sys.exit(1)
    
    # 插入测试数据
    if insert_test_data(client):
        print("\n✓ MongoDB测试设置完成！")
        print("\n可用的测试数据库: querynest_test")
        print("可用的集合: users, products, orders")
    else:
        print("\n✗ 测试数据插入失败")
        sys.exit(1)
    
    client.close()

if __name__ == "__main__":
    main()