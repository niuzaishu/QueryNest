import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

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

async def insert_test_data():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client['querynest_test']
    
    try:
        # 清理现有数据
        for collection_name in TEST_DATA.keys():
            await db[collection_name].drop()
            print(f"已清理 {collection_name} 集合")
        
        # 插入测试数据
        for collection_name, documents in TEST_DATA.items():
            collection = db[collection_name]
            if documents:
                await collection.insert_many(documents)
                print(f"已插入 {len(documents)} 条数据到 {collection_name} 集合")
        
        # 验证数据插入
        for collection_name in TEST_DATA.keys():
            count = await db[collection_name].count_documents({})
            print(f"{collection_name} 集合文档数量: {count}")
            
    except Exception as e:
        print(f"插入测试数据时出错: {e}")
        raise
    finally:
        client.close()

if __name__ == '__main__':
    asyncio.run(insert_test_data())