#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QueryNest uvx 启动问题修复脚本
"""

import os
import sys
import shutil
from pathlib import Path
import subprocess


def clean_build_artifacts():
    """清理构建产物"""
    print("🧹 清理构建产物...")
    
    artifacts = [
        "build",
        "dist", 
        "*.egg-info",
        "__pycache__",
        ".pytest_cache"
    ]
    
    for pattern in artifacts:
        if "*" in pattern:
            # 处理通配符模式
            import glob
            for path in glob.glob(pattern):
                if os.path.exists(path):
                    if os.path.isdir(path):
                        shutil.rmtree(path, ignore_errors=True)
                    else:
                        os.remove(path)
                    print(f"  ✅ 已删除: {path}")
        else:
            # 处理普通路径
            if os.path.exists(pattern):
                if os.path.isdir(pattern):
                    shutil.rmtree(pattern, ignore_errors=True)
                else:
                    os.remove(pattern)
                print(f"  ✅ 已删除: {pattern}")


def fix_pyproject_toml():
    """修复 pyproject.toml 配置"""
    print("🔧 修复 pyproject.toml 配置...")
    
    pyproject_path = Path("pyproject.toml")
    if not pyproject_path.exists():
        print("  ❌ pyproject.toml 文件不存在")
        return False
    
    # 读取现有内容
    with open(pyproject_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 修复入口点配置
    if 'querynest-mcp = "mcp_server:cli_main"' in content:
        print("  ✅ 入口点配置正确")
    else:
        print("  ⚠️  入口点配置可能有问题")
    
    return True


def create_startup_script():
    """创建启动脚本"""
    print("📝 创建启动脚本...")
    
    # Windows 批处理脚本
    bat_content = '''@echo off
echo Starting QueryNest MCP Server...
cd /d "%~dp0"
set QUERYNEST_CONFIG_PATH=%~dp0config.yaml
python mcp_server.py
if errorlevel 1 (
    echo Failed to start QueryNest MCP Server
    pause
    exit /b 1
)
'''
    
    with open("start_querynest.bat", 'w', encoding='utf-8') as f:
        f.write(bat_content)
    print("  ✅ 已创建 start_querynest.bat")
    
    # PowerShell 脚本
    ps1_content = '''# QueryNest MCP Server 启动脚本
Write-Host "Starting QueryNest MCP Server..." -ForegroundColor Green

# 设置工作目录
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# 设置环境变量
$env:QUERYNEST_CONFIG_PATH = Join-Path $ScriptDir "config.yaml"

# 启动服务
try {
    python mcp_server.py
} catch {
    Write-Host "Failed to start QueryNest MCP Server: $_" -ForegroundColor Red
    Read-Host "Press Enter to continue..."
    exit 1
}
'''
    
    with open("start_querynest.ps1", 'w', encoding='utf-8') as f:
        f.write(ps1_content)
    print("  ✅ 已创建 start_querynest.ps1")


def test_direct_startup():
    """测试直接启动"""
    print("🧪 测试直接启动...")
    
    # 设置环境变量
    os.environ['QUERYNEST_CONFIG_PATH'] = str(Path.cwd() / "config.yaml")
    
    try:
        # 导入测试
        sys.path.insert(0, str(Path.cwd()))
        import mcp_server
        print("  ✅ 模块导入成功")
        
        # 检查入口点函数
        if hasattr(mcp_server, 'cli_main'):
            print("  ✅ cli_main 函数存在")
        else:
            print("  ❌ cli_main 函数不存在")
            return False
            
        return True
        
    except ImportError as e:
        print(f"  ❌ 模块导入失败: {e}")
        return False
    except Exception as e:
        print(f"  ❌ 测试失败: {e}")
        return False


def create_alternative_uvx_config():
    """创建替代的 uvx 配置"""
    print("⚙️  创建替代的 uvx 配置...")
    
    # 创建简化的 setup.py
    setup_content = '''from setuptools import setup, find_packages

setup(
    name="querynest",
    version="1.0.0",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "querynest-mcp=mcp_server:cli_main",
        ],
    },
    install_requires=[
        "mcp>=1.0.0",
        "pymongo>=4.0.0",
        "motor>=3.3.0",
        "pydantic>=2.0.0",
        "pydantic-settings>=2.0.0",
        "pyyaml>=6.0",
        "structlog>=23.0.0",
        "nltk>=3.8",
        "scikit-learn>=1.3.0",
        "numpy>=1.24.0",
        "python-dotenv>=1.0.0",
        "dnspython>=2.0.0",
        "tornado>=5.0"
    ],
    python_requires=">=3.8",
)
'''
    
    with open("setup.py", 'w', encoding='utf-8') as f:
        f.write(setup_content)
    print("  ✅ 已创建简化的 setup.py")


def main():
    """主函数"""
    print("🚀 QueryNest uvx 启动问题修复工具")
    print("=" * 50)
    
    # 1. 清理构建产物
    clean_build_artifacts()
    
    # 2. 修复配置文件
    fix_pyproject_toml()
    
    # 3. 创建启动脚本
    create_startup_script()
    
    # 4. 创建替代配置
    create_alternative_uvx_config()
    
    # 5. 测试直接启动
    if test_direct_startup():
        print("\n✅ 修复完成！")
        print("\n📋 使用方法:")
        print("1. 直接启动: python mcp_server.py")
        print("2. 批处理启动: start_querynest.bat")
        print("3. PowerShell启动: .\\start_querynest.ps1")
        print("4. uvx启动: uvx --from . --no-cache querynest-mcp")
        print("\n⚠️  如果 uvx 仍有问题，建议使用直接启动方式")
    else:
        print("\n❌ 修复过程中发现问题，请检查错误信息")


if __name__ == "__main__":
    main()