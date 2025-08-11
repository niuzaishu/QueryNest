#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
创建测试数据脚本
用于在MongoDB中创建测试数据库和集合
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta
import random

async def create_test_data():
    """创建测试数据"""
    # 连接MongoDB
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    
    # 创建querynest_test数据库
    test_db = client.querynest_test
    
    print("正在创建测试数据...")
    
    # 创建用户集合
    users_collection = test_db.users
    users_data = [
        {
            "_id": i,
            "name": f"用户{i}",
            "email": f"user{i}@example.com",
            "age": random.randint(18, 65),
            "city": random.choice(["北京", "上海", "广州", "深圳", "杭州"]),
            "created_at": datetime.now() - timedelta(days=random.randint(1, 365)),
            "status": random.choice(["active", "inactive", "pending"])
        }
        for i in range(1, 101)  # 创建100个用户
    ]
    await users_collection.insert_many(users_data)
    print(f"已创建 {len(users_data)} 个用户记录")
    
    # 创建订单集合
    orders_collection = test_db.orders
    orders_data = [
        {
            "_id": i,
            "user_id": random.randint(1, 100),
            "product_name": f"商品{random.randint(1, 50)}",
            "price": round(random.uniform(10.0, 1000.0), 2),
            "quantity": random.randint(1, 5),
            "order_date": datetime.now() - timedelta(days=random.randint(1, 180)),
            "status": random.choice(["pending", "completed", "cancelled"])
        }
        for i in range(1, 501)  # 创建500个订单
    ]
    await orders_collection.insert_many(orders_data)
    print(f"已创建 {len(orders_data)} 个订单记录")
    
    # 创建产品集合
    products_collection = test_db.products
    products_data = [
        {
            "_id": i,
            "name": f"商品{i}",
            "category": random.choice(["电子产品", "服装", "食品", "书籍", "家居"]),
            "price": round(random.uniform(10.0, 2000.0), 2),
            "stock": random.randint(0, 100),
            "description": f"这是商品{i}的描述",
            "tags": random.sample(["热销", "新品", "促销", "限量", "推荐"], random.randint(1, 3))
        }
        for i in range(1, 51)  # 创建50个产品
    ]
    await products_collection.insert_many(products_data)
    print(f"已创建 {len(products_data)} 个产品记录")
    
    # 创建querynest_dev数据库
    dev_db = client.querynest_dev
    
    # 在开发数据库中创建一些测试集合
    test_collection = dev_db.test_collection
    test_data = [
        {
            "_id": i,
            "field1": f"value{i}",
            "field2": random.randint(1, 100),
            "field3": random.choice([True, False]),
            "timestamp": datetime.now()
        }
        for i in range(1, 21)  # 创建20条测试记录
    ]
    await test_collection.insert_many(test_data)
    print(f"已创建 {len(test_data)} 个测试记录")
    
    # 显示数据库信息
    print("\n数据库创建完成！")
    print("\n可用数据库:")
    databases = await client.list_database_names()
    for db_name in databases:
        if db_name.startswith('querynest'):
            db = client[db_name]
            collections = await db.list_collection_names()
            print(f"  - {db_name}: {collections}")
    
    client.close()
    print("\n测试数据创建完成！")

if __name__ == "__main__":
    asyncio.run(create_test_data())