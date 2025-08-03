#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QueryNest MCP 服务器启动脚本
"""

import asyncio
import logging
import signal
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from mcp_server import QueryNestMCPServer
from config import ConfigLoader
from utils.logger import setup_logging
from utils.startup_validator import validate_startup_environment
from utils import error_handler

# 设置基本日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


async def main():
    """主函数"""
    # 环境验证
    print("🔍 验证启动环境...")
    is_valid, messages = validate_startup_environment()
    
    for message in messages:
        print(message)
    
    if not is_valid:
        print("❌ 环境验证失败，请修复上述问题后重试")
        sys.exit(1)
    
    print("✅ 环境验证通过")
    
    # 设置日志
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        # 加载配置
        config_loader = ConfigLoader()
        config = config_loader.load_config()
        
        logger.info("QueryNest 服务启动中...")
        print("🚀 启动 QueryNest 服务...")
        
        # 初始化错误处理器
        error_handling_config = getattr(config, 'error_handling', {}) if hasattr(config, 'error_handling') else {}
        error_handler.initialize(error_handling_config)
        
        # 创建并启动MCP服务器
        config_path = os.getenv('QUERYNEST_CONFIG_PATH', 'config.yaml')
        server = QueryNestMCPServer(config_path)
        await server.initialize()
        await server.run()
        
        logger.info("QueryNest 服务已启动")
        print("✅ QueryNest 服务已成功启动")
        print("🔧 MCP工具已就绪")
        print("\n按 Ctrl+C 停止服务")
        
        # 等待中断信号
        stop_event = asyncio.Event()
        
        def signal_handler(signum, frame):
            logger.info(f"收到信号 {signum}，正在关闭服务...")
            print("\n🛑 正在关闭服务...")
            stop_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        await stop_event.wait()
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"服务启动失败: {e}")
        logger.error(f"详细错误信息: {error_details}")
        print(f"❌ 服务启动失败: {e}")
        print(f"详细错误信息:\n{error_details}")
        error_handler.handle_error(e, {"context": "service_startup"})
        raise
    finally:
        logger.info("QueryNest 服务已停止")
        print("✅ QueryNest 服务已停止")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n服务器已停止")
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"服务器启动失败: {e}")
        print(f"详细错误信息:\n{error_details}")
        sys.exit(1)