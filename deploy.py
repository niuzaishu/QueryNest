#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QueryNest 部署脚本
"""

import os
import sys
import argparse
import subprocess
import shutil
from pathlib import Path
from typing import List, Dict, Any


def check_python_version():
    """检查Python版本"""
    if sys.version_info < (3, 8):
        print("❌ Python版本过低，需要Python 3.8或更高版本")
        print(f"当前版本: {sys.version}")
        sys.exit(1)
    print(f"✅ Python版本检查通过: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")


def install_dependencies():
    """安装依赖包"""
    print("📦 安装依赖包...")
    
    requirements_file = "requirements.txt"
    if not os.path.exists(requirements_file):
        print(f"❌ 找不到 {requirements_file} 文件")
        return False
    
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", requirements_file], 
                      check=True, capture_output=True, text=True)
        print("✅ 依赖包安装完成")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 依赖包安装失败: {e}")
        print(f"错误输出: {e.stderr}")
        return False


def create_directories():
    """创建必要的目录"""
    print("📁 创建目录结构...")
    
    directories = [
        "logs",
        "data",
        "cache",
        "backups",
        "temp"
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        print(f"  ✅ 创建目录: {directory}")


def setup_config():
    """设置配置文件"""
    print("⚙️  设置配置文件...")
    
    config_file = "config.yaml"
    example_config = "config.example.yaml"
    
    if not os.path.exists(config_file):
        if os.path.exists(example_config):
            shutil.copy2(example_config, config_file)
            print(f"  ✅ 从 {example_config} 复制配置文件")
            print(f"  ⚠️  请编辑 {config_file} 以配置您的MongoDB实例")
        else:
            print(f"  ❌ 找不到示例配置文件 {example_config}")
            return False
    else:
        print(f"  ✅ 配置文件 {config_file} 已存在")
    
    # 设置环境变量文件
    env_file = ".env"
    example_env = ".env.example"
    
    if not os.path.exists(env_file):
        if os.path.exists(example_env):
            shutil.copy2(example_env, env_file)
            print(f"  ✅ 从 {example_env} 复制环境变量文件")
            print(f"  ⚠️  请编辑 {env_file} 以配置环境变量")
        else:
            print(f"  ⚠️  找不到示例环境变量文件 {example_env}")
    else:
        print(f"  ✅ 环境变量文件 {env_file} 已存在")
    
    return True


def validate_environment():
    """验证环境"""
    print("🔍 验证环境...")
    
    try:
        from src.utils.config_validator import validate_startup_environment
        
        is_valid, messages = validate_startup_environment()
        
        for message in messages:
            print(f"  {message}")
        
        if not is_valid:
            print("  ❌ 环境验证失败，请修复上述问题后重试")
            return False
        
        print("  ✅ 环境验证通过")
        return True
        
    except ImportError as e:
        print(f"  ⚠️  无法导入验证模块: {e}")
        print("  继续部署，但建议手动检查环境")
        return True


def test_mongodb_connection():
    """测试MongoDB连接"""
    print("🔗 测试MongoDB连接...")
    
    try:
        from src.database.connection_manager import ConnectionManager
        import asyncio
        
        async def test_connections():
            try:
                manager = ConnectionManager()
                await manager.initialize()
                
                available_instances = await manager.get_available_instances()
                if available_instances:
                    print(f"  ✅ 成功连接到 {len(available_instances)} 个MongoDB实例")
                    for instance in available_instances:
                        print(f"    • {instance}")
                    return True
                else:
                    print("  ❌ 没有可用的MongoDB实例")
                    return False
                    
            except Exception as e:
                print(f"  ❌ MongoDB连接测试失败: {e}")
                return False
            finally:
                try:
                    await manager.close_all()
                except:
                    pass
        
        return asyncio.run(test_connections())
        
    except ImportError as e:
        print(f"  ⚠️  无法导入连接管理器: {e}")
        print("  跳过MongoDB连接测试")
        return True
    except Exception as e:
        print(f"  ❌ 连接测试失败: {e}")
        return False


def create_startup_script():
    """创建启动脚本"""
    print("📝 创建启动脚本...")
    
    # Windows批处理脚本
    windows_script = "start.bat"
    with open(windows_script, 'w', encoding='utf-8') as f:
        f.write("@echo off\n")
        f.write("echo Starting QueryNest...\n")
        f.write("python start.py\n")
        f.write("pause\n")
    print(f"  ✅ 创建Windows启动脚本: {windows_script}")
    
    # Unix shell脚本
    unix_script = "start.sh"
    with open(unix_script, 'w', encoding='utf-8') as f:
        f.write("#!/bin/bash\n")
        f.write("echo \"Starting QueryNest...\"\n")
        f.write("python3 start.py\n")
    
    # 设置执行权限
    try:
        os.chmod(unix_script, 0o755)
        print(f"  ✅ 创建Unix启动脚本: {unix_script}")
    except:
        print(f"  ⚠️  创建Unix启动脚本但无法设置权限: {unix_script}")


def create_service_files():
    """创建服务文件"""
    print("🔧 创建服务文件...")
    
    # systemd服务文件
    service_content = f"""[Unit]
Description=QueryNest MongoDB Query Service
After=network.target

[Service]
Type=simple
User=querynest
WorkingDirectory={os.getcwd()}
ExecStart={sys.executable} start.py
Restart=always
RestartSec=10
Environment=PYTHONPATH={os.getcwd()}

[Install]
WantedBy=multi-user.target
"""
    
    service_file = "querynest.service"
    with open(service_file, 'w', encoding='utf-8') as f:
        f.write(service_content)
    
    print(f"  ✅ 创建systemd服务文件: {service_file}")
    print("  💡 要安装服务，请运行:")
    print(f"     sudo cp {service_file} /etc/systemd/system/")
    print("     sudo systemctl enable querynest")
    print("     sudo systemctl start querynest")


def create_docker_files():
    """创建Docker文件"""
    print("🐳 创建Docker文件...")
    
    # Dockerfile
    dockerfile_content = """FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建必要目录
RUN mkdir -p logs data cache temp

# 设置环境变量
    ENV PYTHONPATH=/app
    ENV QUERYNEST_CONFIG_PATH=/app/config.yaml
    ENV QUERYNEST_LOG_LEVEL=INFO
    ENV QUERYNEST_MCP_TRANSPORT=stdio

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["python", "start.py"]
"""
    
    with open("Dockerfile", 'w', encoding='utf-8') as f:
        f.write(dockerfile_content)
    
    # docker-compose.yml
    compose_content = """version: '3.8'

services:
  querynest:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - ./logs:/app/logs
      - ./data:/app/data
    environment:
      - QUERYNEST_CONFIG_PATH=/app/config.yaml
      - QUERYNEST_LOG_LEVEL=INFO
      - QUERYNEST_MCP_TRANSPORT=stdio
    restart: unless-stopped
    depends_on:
      - mongodb

  mongodb:
    image: mongo:5.0
    ports:
      - "27017:27017"
    volumes:
      - mongodb_data:/data/db
    environment:
      - MONGO_INITDB_ROOT_USERNAME=admin
      - MONGO_INITDB_ROOT_PASSWORD=password
    restart: unless-stopped

volumes:
  mongodb_data:
"""
    
    with open("docker-compose.yml", 'w', encoding='utf-8') as f:
        f.write(compose_content)
    
    # .dockerignore
    dockerignore_content = """__pycache__
*.pyc
*.pyo
*.pyd
.Python
env
venv
.venv
pip-log.txt
pip-delete-this-directory.txt
.tox
.coverage
.coverage.*
.cache
nosetests.xml
coverage.xml
*.cover
*.log
.git
.mypy_cache
.pytest_cache
.hypothesis

.DS_Store
.vscode
.idea

logs/*
data/*
cache/*
temp/*
backups/*

*.env
.env.*
"""
    
    with open(".dockerignore", 'w', encoding='utf-8') as f:
        f.write(dockerignore_content)
    
    print("  ✅ 创建Dockerfile")
    print("  ✅ 创建docker-compose.yml")
    print("  ✅ 创建.dockerignore")
    print("  💡 要使用Docker运行，请执行:")
    print("     docker-compose up -d")


def print_deployment_summary():
    """打印部署摘要"""
    print("\n" + "="*60)
    print("🎉 QueryNest 部署完成!")
    print("="*60)
    
    print("\n📋 部署摘要:")
    print("  ✅ Python环境检查")
    print("  ✅ 依赖包安装")
    print("  ✅ 目录结构创建")
    print("  ✅ 配置文件设置")
    print("  ✅ 启动脚本创建")
    print("  ✅ 服务文件创建")
    print("  ✅ Docker文件创建")
    
    print("\n🚀 启动方式:")
    print("  • 直接启动: python start.py")
    print("  • Windows: start.bat")
    print("  • Unix/Linux: ./start.sh")
    print("  • Docker: docker-compose up -d")
    
    print("\n⚙️  下一步:")
    print("  1. 编辑 config.yaml 配置您的MongoDB实例")
    print("  2. 编辑 .env 设置环境变量")
    print("  3. 运行启动脚本测试服务")
    
    print("\n📚 文档和帮助:")
    print("  • README.md - 项目说明")
    print("  • app.md - 技术文档")
    print("  • config.example.yaml - 配置示例")
    print("  • .env.example - 环境变量示例")
    
    print("\n" + "="*60)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="QueryNest 部署脚本")
    parser.add_argument("--skip-deps", action="store_true", help="跳过依赖安装")
    parser.add_argument("--skip-test", action="store_true", help="跳过连接测试")
    parser.add_argument("--docker-only", action="store_true", help="只创建Docker文件")
    
    args = parser.parse_args()
    
    print("🚀 开始部署 QueryNest...")
    print("="*60)
    
    try:
        # 检查Python版本
        check_python_version()
        
        if args.docker_only:
            create_docker_files()
            print("\n✅ Docker文件创建完成")
            return
        
        # 安装依赖
        if not args.skip_deps:
            if not install_dependencies():
                print("❌ 部署失败：依赖安装失败")
                sys.exit(1)
        
        # 创建目录
        create_directories()
        
        # 设置配置
        if not setup_config():
            print("❌ 部署失败：配置设置失败")
            sys.exit(1)
        
        # 验证环境
        if not validate_environment():
            print("❌ 部署失败：环境验证失败")
            sys.exit(1)
        
        # 测试MongoDB连接
        if not args.skip_test:
            if not test_mongodb_connection():
                print("⚠️  MongoDB连接测试失败，但继续部署")
                print("   请检查配置文件中的MongoDB设置")
        
        # 创建启动脚本
        create_startup_script()
        
        # 创建服务文件
        create_service_files()
        
        # 创建Docker文件
        create_docker_files()
        
        # 打印摘要
        print_deployment_summary()
        
    except KeyboardInterrupt:
        print("\n❌ 部署被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 部署失败：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()