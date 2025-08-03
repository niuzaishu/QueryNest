import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def check_database():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client['querynest_test']
    
    # 检查orders集合
    count = await db.orders.count_documents({})
    print(f'orders集合文档数量: {count}')
    
    if count > 0:
        docs = await db.orders.find().limit(2).to_list(length=None)
        print(f'前2个文档: {docs}')
    else:
        print('orders集合为空')
    
    # 检查所有集合
    collections = await db.list_collection_names()
    print(f'数据库中的集合: {collections}')
    
    # 检查每个集合的文档数量
    for coll_name in collections:
        coll_count = await db[coll_name].count_documents({})
        print(f'{coll_name}集合文档数量: {coll_count}')
    
    client.close()

if __name__ == '__main__':
    asyncio.run(check_database())