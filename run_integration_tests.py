#!/usr/bin/env python3
"""运行集成测试脚本"""
import asyncio
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from motor.motor_asyncio import AsyncIOMotorClient
from tests.integration.test_config import TEST_DB_CONFIG


async def check_mongodb_connection():
    """检查MongoDB连接"""
    try:
        client = AsyncIOMotorClient(
            host=TEST_DB_CONFIG["host"],
            port=TEST_DB_CONFIG["port"],
            serverSelectionTimeoutMS=5000  # 5秒超时
        )
        
        # 测试连接
        await client.admin.command('ping')
        print(f"✓ MongoDB连接成功: {TEST_DB_CONFIG['host']}:{TEST_DB_CONFIG['port']}")
        
        # 检查测试数据库
        db_names = await client.list_database_names()
        print(f"✓ 可用数据库: {', '.join(db_names)}")
        
        client.close()
        return True
        
    except Exception as e:
        print(f"✗ MongoDB连接失败: {e}")
        print("请确保MongoDB服务正在运行")
        print(f"连接地址: {TEST_DB_CONFIG['host']}:{TEST_DB_CONFIG['port']}")
        return False


def run_tests(test_type="all"):
    """运行测试"""
    import subprocess
    
    if test_type == "unit":
        cmd = ["python", "-m", "pytest", "tests/unit/", "-v", "-m", "not integration"]
    elif test_type == "integration":
        cmd = ["python", "-m", "pytest", "tests/integration/", "-v", "-m", "integration"]
    elif test_type == "all":
        cmd = ["python", "-m", "pytest", "tests/", "-v"]
    else:
        print(f"未知的测试类型: {test_type}")
        return False
    
    print(f"运行命令: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=project_root)
    return result.returncode == 0


async def main():
    """主函数"""
    print("QueryNest 集成测试运行器")
    print("=" * 50)
    
    # 检查命令行参数
    test_type = "integration"
    if len(sys.argv) > 1:
        test_type = sys.argv[1]
    
    if test_type in ["integration", "all"]:
        print("1. 检查MongoDB连接...")
        if not await check_mongodb_connection():
            print("\n请先启动MongoDB服务，然后重新运行测试")
            print("启动命令示例:")
            print("  Windows: net start MongoDB")
            print("  Linux/Mac: sudo systemctl start mongod")
            print("  Docker: docker run -d -p 27017:27017 mongo:latest")
            return False
    
    print(f"\n2. 运行{test_type}测试...")
    success = run_tests(test_type)
    
    if success:
        print("\n✓ 所有测试通过!")
    else:
        print("\n✗ 部分测试失败")
    
    return success


if __name__ == "__main__":
    print("使用方法:")
    print("  python run_integration_tests.py [test_type]")
    print("  test_type: unit | integration | all (默认: integration)")
    print()
    
    success = asyncio.run(main())
    sys.exit(0 if success else 1)