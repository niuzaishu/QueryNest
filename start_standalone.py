#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QueryNest MCP 服务器独立启动脚本
解决stdio处理导致Windows下立即退出的问题
"""

import asyncio
import logging
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))

# 设置基本日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 设置环境变量
if not os.environ.get('QUERYNEST_CONFIG_PATH'):
    config_path = script_dir / "config.yaml"
    if config_path.exists():
        os.environ['QUERYNEST_CONFIG_PATH'] = str(config_path)
        logger.info(f"Setting config path to: {config_path}")

def create_necessary_directories():
    """创建必要的目录结构"""
    dirs = [
        script_dir / "logs",
        script_dir / "data" / "metadata",
        script_dir / "semantic_data"
    ]
    
    for dir_path in dirs:
        if not dir_path.exists():
            dir_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"创建目录: {dir_path}")

async def keep_server_alive():
    """保持服务器运行"""
    try:
        # 创建一个永不完成的Future
        forever = asyncio.Future()
        await forever
    except asyncio.CancelledError:
        logger.info("服务器关闭请求已接收")
    except Exception as e:
        logger.error(f"保持活动循环中的错误: {e}")

async def main():
    """主函数"""
    # 创建必要的目录
    create_necessary_directories()
    
    # 导入服务器类
    try:
        from mcp_server import QueryNestMCPServer
    except ImportError as e:
        logger.error(f"导入错误: {e}")
        logger.error("请确保所有依赖已安装")
        return 1
    
    # 创建MCP服务器实例
    server = None
    keep_alive_task = None
    
    try:
        logger.info("正在启动QueryNest MCP服务器...")
        print("正在启动QueryNest MCP服务器...")
        
        # 初始化服务器
        config_path = os.environ.get('QUERYNEST_CONFIG_PATH', 'config.yaml')
        server = QueryNestMCPServer(config_path)
        await server.initialize()
        
        logger.info("QueryNest MCP服务器已初始化")
        print("\n========================================")
        print("  QueryNest MCP服务器已启动 (独立模式)  ")
        print("  按Ctrl+C停止服务器                   ")
        print("========================================\n")
        
        # 创建保持活动的任务
        keep_alive_task = asyncio.create_task(keep_server_alive())
        
        # 等待任务完成或取消
        await keep_alive_task
        
    except KeyboardInterrupt:
        print("\n收到键盘中断，正在关闭服务器...")
        logger.info("收到键盘中断，正在关闭服务器...")
    except Exception as e:
        import traceback
        logger.error(f"服务器运行时出错: {e}")
        logger.error(traceback.format_exc())
        return 1
    finally:
        # 取消keep_alive_task（如果存在）
        if keep_alive_task and not keep_alive_task.done():
            keep_alive_task.cancel()
            try:
                await keep_alive_task
            except asyncio.CancelledError:
                pass
        
        # 清理资源
        if server:
            logger.info("正在清理服务器资源...")
            try:
                await server.cleanup()
                logger.info("服务器资源已清理")
            except Exception as e:
                logger.error(f"清理资源时出错: {e}")
    
    logger.info("QueryNest MCP服务器已关闭")
    print("QueryNest MCP服务器已成功关闭")
    return 0

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n服务器已被用户中断")
    except Exception as e:
        print(f"致命错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)