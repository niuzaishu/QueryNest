#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QueryNest MCP 启动脚本
解决 uvx 运行时的工作目录问题
"""

import os
import sys
from pathlib import Path

def main():
    """启动 MCP 服务器"""
    # 获取脚本所在目录（项目根目录）
    project_root = Path(__file__).parent.absolute()
    
    # 更改当前工作目录到项目根目录
    os.chdir(project_root)
    
    # 确保项目根目录在 Python 路径中
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    
    # 设置配置文件环境变量
    config_path = project_root / "config.yaml"
    if config_path.exists():
        os.environ['QUERYNEST_CONFIG_PATH'] = str(config_path)
        print(f"INFO: 设置配置文件路径: {config_path}")
    else:
        print(f"WARNING: 配置文件不存在: {config_path}")
        
    # 显示调试信息
    print(f"INFO: 项目根目录: {project_root}")
    print(f"INFO: 当前工作目录: {os.getcwd()}")
    
    # 导入并运行 MCP 服务器
    try:
        from mcp_server import cli_main
        cli_main()
    except ImportError as e:
        print(f"导入错误: {e}")
        print(f"当前工作目录: {os.getcwd()}")
        print(f"Python 路径: {sys.path[:3]}")  # 只显示前3个路径
        sys.exit(1)
    except Exception as e:
        print(f"启动错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()