#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
启动环境验证模块
"""

import os
import sys
from pathlib import Path
from typing import Tuple, List
import importlib.util


def validate_startup_environment() -> Tuple[bool, List[str]]:
    """
    验证启动环境
    
    Returns:
        Tuple[bool, List[str]]: (是否验证通过, 验证消息列表)
    """
    messages = []
    is_valid = True
    
    # 检查Python版本
    python_version = sys.version_info
    if python_version < (3, 8):
        messages.append("❌ Python版本过低，需要Python 3.8或更高版本")
        is_valid = False
    else:
        messages.append(f"✅ Python版本: {python_version.major}.{python_version.minor}.{python_version.micro}")
    
    # 检查必要的依赖包
    required_packages = [
        'motor',
        'pymongo', 
        'pydantic',
        'yaml',
        'mcp'
    ]
    
    for package in required_packages:
        try:
            importlib.import_module(package)
            messages.append(f"✅ 依赖包 {package} 已安装")
        except ImportError:
            messages.append(f"❌ 缺少依赖包: {package}")
            is_valid = False
    
    # 检查配置文件
    config_file = Path("config.yaml")
    if config_file.exists():
        messages.append("✅ 配置文件 config.yaml 存在")
    else:
        messages.append("⚠️  配置文件 config.yaml 不存在，将使用默认配置")
    
    # 检查数据目录
    data_dir = Path("data")
    if not data_dir.exists():
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
            messages.append("✅ 创建数据目录")
        except Exception as e:
            messages.append(f"❌ 无法创建数据目录: {e}")
            is_valid = False
    else:
        messages.append("✅ 数据目录存在")
    
    # 检查日志目录
    log_dir = Path("logs")
    if not log_dir.exists():
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            messages.append("✅ 创建日志目录")
        except Exception as e:
            messages.append(f"⚠️  无法创建日志目录: {e}")
    else:
        messages.append("✅ 日志目录存在")
    
    # 检查环境变量
    env_vars = [
        'PYTHONPATH'
    ]
    
    for var in env_vars:
        if os.getenv(var):
            messages.append(f"✅ 环境变量 {var} 已设置")
        else:
            messages.append(f"ℹ️  环境变量 {var} 未设置（可选）")
    
    # 检查文件权限
    try:
        test_file = Path("test_write_permission.tmp")
        test_file.write_text("test")
        test_file.unlink()
        messages.append("✅ 文件写入权限正常")
    except Exception as e:
        messages.append(f"❌ 文件写入权限异常: {e}")
        is_valid = False
    
    return is_valid, messages


def check_mongodb_connection(connection_string: str) -> Tuple[bool, str]:
    """
    检查MongoDB连接
    
    Args:
        connection_string: MongoDB连接字符串
        
    Returns:
        Tuple[bool, str]: (连接是否成功, 消息)
    """
    try:
        from pymongo import MongoClient
        
        client = MongoClient(connection_string, serverSelectionTimeoutMS=5000)
        client.server_info()  # 触发连接
        client.close()
        
        return True, "MongoDB连接成功"
    except Exception as e:
        return False, f"MongoDB连接失败: {e}"


def validate_config_file(config_path: str) -> Tuple[bool, List[str]]:
    """
    验证配置文件
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        Tuple[bool, List[str]]: (验证是否通过, 验证消息列表)
    """
    messages = []
    is_valid = True
    
    config_file = Path(config_path)
    if not config_file.exists():
        messages.append(f"❌ 配置文件不存在: {config_path}")
        return False, messages
    
    try:
        import yaml
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 检查必要的配置项
        required_sections = ['mongodb']
        for section in required_sections:
            if section not in config:
                messages.append(f"❌ 配置文件缺少必要部分: {section}")
                is_valid = False
            else:
                messages.append(f"✅ 配置部分 {section} 存在")
        
        # 检查MongoDB实例配置
        if 'mongodb' in config and 'instances' in config['mongodb'] and config['mongodb']['instances']:
            instances = config['mongodb']['instances']
            messages.append(f"✅ 配置了 {len(instances)} 个MongoDB实例")
            
            # 检查是否有活跃实例
            active_instances = [inst for inst in instances.values() if inst.get('status', 'active') == 'active']
            if active_instances:
                messages.append(f"✅ 发现 {len(active_instances)} 个活跃的MongoDB实例")
            else:
                messages.append("⚠️  没有活跃的MongoDB实例")
        else:
            messages.append("⚠️  未配置MongoDB实例")
        
    except yaml.YAMLError as e:
        messages.append(f"❌ 配置文件格式错误: {e}")
        is_valid = False
    except Exception as e:
        messages.append(f"❌ 读取配置文件失败: {e}")
        is_valid = False
    
    return is_valid, messages