#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""插入测试数据脚本"""

import asyncio
import sys
import logging
from pathlib import Path
from datetime import datetime, timedelta
import random
from typing import List, Dict, Any

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from motor.motor_asyncio import AsyncIOMotorClient
from config import load_config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TestDataInserter:
    """测试数据插入器"""
    
    def __init__(self):
        self.config = load_config()
        self.clients = {}
    
    async def connect_to_instances(self):
        """连接到所有活跃的MongoDB实例"""
        for instance_key, instance_config in self.config.mongo_instances.items():
            if instance_config.status == "active":
                try:
                    client = AsyncIOMotorClient(
                        instance_config.connection_string,
                        serverSelectionTimeoutMS=5000
                    )
                    # 测试连接
                    await client.admin.command('ping')
                    self.clients[instance_key] = {
                        'client': client,
                        'config': instance_config
                    }
                    logger.info(f"连接到实例: {instance_config.name}")
                except Exception as e:
                    logger.error(f"连接实例失败: {instance_config.name}, 错误: {e}")
    
    async def generate_user_data(self, count: int = 100) -> List[Dict[str, Any]]:
        """生成用户测试数据"""
        users = []
        for i in range(count):
            user = {
                "user_id": f"user_{i+1:04d}",
                "username": f"testuser{i+1}",
                "email": f"user{i+1}@example.com",
                "age": random.randint(18, 65),
                "gender": random.choice(["male", "female", "other"]),
                "city": random.choice(["北京", "上海", "广州", "深圳", "杭州", "成都"]),
                "registration_date": datetime.now() - timedelta(days=random.randint(1, 365)),
                "is_active": random.choice([True, False]),
                "profile": {
                    "bio": f"这是用户{i+1}的个人简介",
                    "interests": random.sample(["编程", "音乐", "电影", "旅行", "读书", "运动"], k=random.randint(1, 3)),
                    "score": random.randint(0, 100)
                },
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            }
            users.append(user)
        return users
    
    async def generate_product_data(self, count: int = 50) -> List[Dict[str, Any]]:
        """生成产品测试数据"""
        products = []
        categories = ["电子产品", "服装", "家居", "图书", "运动", "美妆"]
        
        for i in range(count):
            product = {
                "product_id": f"prod_{i+1:04d}",
                "name": f"测试产品{i+1}",
                "category": random.choice(categories),
                "price": round(random.uniform(10.0, 1000.0), 2),
                "stock": random.randint(0, 100),
                "description": f"这是测试产品{i+1}的详细描述",
                "tags": random.sample(["热销", "新品", "推荐", "限时", "特价"], k=random.randint(1, 3)),
                "rating": round(random.uniform(1.0, 5.0), 1),
                "reviews_count": random.randint(0, 500),
                "is_available": random.choice([True, False]),
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            }
            products.append(product)
        return products
    
    async def generate_order_data(self, count: int = 200) -> List[Dict[str, Any]]:
        """生成订单测试数据"""
        orders = []
        statuses = ["pending", "processing", "shipped", "delivered", "cancelled"]
        
        for i in range(count):
            order = {
                "order_id": f"order_{i+1:06d}",
                "user_id": f"user_{random.randint(1, 100):04d}",
                "product_ids": [f"prod_{random.randint(1, 50):04d}" for _ in range(random.randint(1, 5))],
                "total_amount": round(random.uniform(20.0, 2000.0), 2),
                "status": random.choice(statuses),
                "shipping_address": {
                    "street": f"测试街道{random.randint(1, 100)}号",
                    "city": random.choice(["北京", "上海", "广州", "深圳"]),
                    "postal_code": f"{random.randint(100000, 999999)}"
                },
                "order_date": datetime.now() - timedelta(days=random.randint(1, 30)),
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            }
            orders.append(order)
        return orders
    
    async def insert_test_data(self):
        """插入测试数据到所有实例"""
        for instance_key, instance_info in self.clients.items():
            client = instance_info['client']
            config = instance_info['config']
            
            # 获取数据库
            db_name = config.connection_string.split('/')[-1] or "test_db"
            db = client[db_name]
            
            logger.info(f"开始向实例 {config.name} 的数据库 {db_name} 插入测试数据")
            
            try:
                # 生成并插入用户数据
                users = await self.generate_user_data(100)
                await db.users.insert_many(users)
                logger.info(f"插入了 {len(users)} 条用户数据")
                
                # 生成并插入产品数据
                products = await self.generate_product_data(50)
                await db.products.insert_many(products)
                logger.info(f"插入了 {len(products)} 条产品数据")
                
                # 生成并插入订单数据
                orders = await self.generate_order_data(200)
                await db.orders.insert_many(orders)
                logger.info(f"插入了 {len(orders)} 条订单数据")
                
                # 创建索引以提高查询性能
                await db.users.create_index("user_id")
                await db.users.create_index("email")
                await db.products.create_index("product_id")
                await db.products.create_index("category")
                await db.orders.create_index("order_id")
                await db.orders.create_index("user_id")
                
                logger.info(f"实例 {config.name} 测试数据插入完成")
                
            except Exception as e:
                logger.error(f"向实例 {config.name} 插入数据失败: {e}")
    
    async def close_connections(self):
        """关闭所有连接"""
        for instance_key, instance_info in self.clients.items():
            instance_info['client'].close()
        logger.info("所有连接已关闭")


async def main():
    """主函数"""
    inserter = TestDataInserter()
    
    try:
        # 连接到实例
        await inserter.connect_to_instances()
        
        if not inserter.clients:
            logger.error("没有可用的MongoDB实例连接")
            return
        
        # 插入测试数据
        await inserter.insert_test_data()
        
        logger.info("测试数据插入完成！")
        
    except Exception as e:
        logger.error(f"插入测试数据时发生错误: {e}")
    finally:
        # 关闭连接
        await inserter.close_connections()


if __name__ == "__main__":
    # 运行主函数
    asyncio.run(main())