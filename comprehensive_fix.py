# -*- coding: utf-8 -*-
"""
修复QueryNest启动问题的完整解决方案
"""

import os
import sys
import asyncio
import logging
from pathlib import Path

# 设置环境变量确保UTF-8编码
os.environ['PYTHONIOENCODING'] = 'utf-8'

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 配置日志系统
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def fix_system_encoding():
    """修复系统编码设置"""
    logger.info("修复系统编码设置...")
    
    # 设置标准输入输出编码
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
    except Exception as e:
        logger.warning(f"无法重新配置标准输出编码: {e}")
    
    # 设置默认编码
    try:
        import locale
        locale.setlocale(locale.LC_ALL, 'zh_CN.UTF-8')
    except Exception as e:
        logger.warning(f"无法设置本地化: {e}")
    
    logger.info(f"当前系统编码: stdout={sys.stdout.encoding}, stderr={sys.stderr.encoding}")

def check_and_create_directories():
    """检查并创建必要的目录"""
    logger.info("检查必要目录...")
    
    directories = [
        "logs",
        "data",
        "data/metadata",
        "semantic_data",
        "semantic_data/instances",
        "semantic_data/indexes"
    ]
    
    for dir_name in directories:
        dir_path = project_root / dir_name
        if not dir_path.exists():
            dir_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"创建目录: {dir_name}")

def validate_config_file():
    """验证配置文件"""
    logger.info("验证配置文件...")
    
    config_file = project_root / "config.yaml"
    if not config_file.exists():
        logger.error("配置文件不存在")
        return False
    
    try:
        import yaml
        with open(config_file, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
        
        # 检查必要的配置项
        if 'mongodb' not in config_data or 'instances' not in config_data['mongodb']:
            logger.error("配置文件缺少MongoDB实例配置")
            return False
        
        logger.info("配置文件验证通过")
        return True
    except Exception as e:
        logger.error(f"配置文件验证失败: {e}")
        return False

async def test_mongodb_connections():
    """测试MongoDB连接"""
    logger.info("测试MongoDB连接...")
    
    try:
        # 导入必要的模块
        from config import QueryNestConfig
        from database.connection_manager import ConnectionManager
        
        # 加载配置
        config_path = os.environ.get('QUERYNEST_CONFIG_PATH', 'config.yaml')
        config = QueryNestConfig.from_yaml(config_path)
        logger.info(f"配置加载成功，实例数量: {len(config.mongo_instances)}")
        
        # 初始化连接管理器
        connection_manager = ConnectionManager(config)
        success = await connection_manager.initialize()
        
        if success:
            logger.info("MongoDB连接测试成功")
            # 显示连接的实例信息
            for instance_name, connection in connection_manager.connections.items():
                logger.info(f"实例 {instance_name} 连接状态: {connection.is_healthy}")
            
            # 关闭连接
            await connection_manager.shutdown()
            return True
        else:
            logger.error("MongoDB连接测试失败")
            return False
            
    except Exception as e:
        logger.error(f"MongoDB连接测试异常: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def fix_file_permissions():
    """修复文件权限"""
    logger.info("修复文件权限...")
    
    try:
        # 确保日志目录可写
        logs_dir = project_root / "logs"
        if logs_dir.exists():
            # 在Windows上不需要特殊权限设置
            pass
        
        logger.info("文件权限检查完成")
    except Exception as e:
        logger.warning(f"文件权限修复失败: {e}")

async def main():
    """主函数"""
    logger.info("开始修复QueryNest启动问题...")
    
    # 1. 修复系统编码
    fix_system_encoding()
    
    # 2. 检查并创建必要目录
    check_and_create_directories()
    
    # 3. 验证配置文件
    if not validate_config_file():
        return False
    
    # 4. 修复文件权限
    fix_file_permissions()
    
    # 5. 测试MongoDB连接
    connection_success = await test_mongodb_connections()
    
    if connection_success:
        logger.info("QueryNest启动问题修复完成！")
        logger.info("请使用以下命令启动服务:")
        logger.info("  uvx --from . --no-cache querynest-mcp")
        logger.info("或者:")
        logger.info("  python mcp_server.py")
        return True
    else:
        logger.error("QueryNest启动问题修复失败，请检查MongoDB连接配置")
        return False

if __name__ == "__main__":
    # 设置事件循环策略以支持Windows
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    success = asyncio.run(main())
    sys.exit(0 if success else 1)