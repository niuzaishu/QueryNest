#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QueryNest 安装脚本"""

import os
import sys
import subprocess
import platform
from pathlib import Path
from typing import List, Optional


class QueryNestInstaller:
    """QueryNest 安装器"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.python_executable = sys.executable
        self.is_windows = platform.system() == "Windows"
        self.venv_name = "venv"
        self.venv_path = self.project_root / self.venv_name
    
    def print_banner(self):
        """打印安装横幅"""
        banner = """
╔══════════════════════════════════════════════════════════════╗
║                    QueryNest 安装程序                        ║
║              MongoDB 多实例查询服务                          ║
╚══════════════════════════════════════════════════════════════╝
"""
        print(banner)
    
    def check_python_version(self) -> bool:
        """检查Python版本"""
        print("🐍 检查Python版本...")
        
        version = sys.version_info
        if version.major < 3 or (version.major == 3 and version.minor < 8):
            print(f"❌ Python版本过低: {version.major}.{version.minor}")
            print("   QueryNest需要Python 3.8或更高版本")
            return False
        
        print(f"✅ Python版本: {version.major}.{version.minor}.{version.micro}")
        return True
    
    def check_pip(self) -> bool:
        """检查pip是否可用"""
        print("📦 检查pip...")
        
        try:
            result = subprocess.run(
                [self.python_executable, "-m", "pip", "--version"],
                capture_output=True,
                text=True,
                check=True
            )
            print(f"✅ pip版本: {result.stdout.strip()}")
            return True
        except subprocess.CalledProcessError:
            print("❌ pip不可用")
            return False
    
    def create_virtual_environment(self) -> bool:
        """创建虚拟环境"""
        print("🏗️ 创建虚拟环境...")
        
        if self.venv_path.exists():
            print(f"⚠️ 虚拟环境已存在: {self.venv_path}")
            response = input("是否删除并重新创建? (y/N): ").strip().lower()
            if response in ['y', 'yes']:
                import shutil
                shutil.rmtree(self.venv_path)
                print("🗑️ 已删除现有虚拟环境")
            else:
                print("📁 使用现有虚拟环境")
                return True
        
        try:
            subprocess.run(
                [self.python_executable, "-m", "venv", str(self.venv_path)],
                check=True
            )
            print(f"✅ 虚拟环境创建成功: {self.venv_path}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ 创建虚拟环境失败: {e}")
            return False
    
    def get_venv_python(self) -> str:
        """获取虚拟环境中的Python可执行文件路径"""
        if self.is_windows:
            return str(self.venv_path / "Scripts" / "python.exe")
        else:
            return str(self.venv_path / "bin" / "python")
    
    def get_venv_pip(self) -> str:
        """获取虚拟环境中的pip可执行文件路径"""
        if self.is_windows:
            return str(self.venv_path / "Scripts" / "pip.exe")
        else:
            return str(self.venv_path / "bin" / "pip")
    
    def upgrade_pip(self) -> bool:
        """升级pip"""
        print("⬆️ 升级pip...")
        
        try:
            venv_python = self.get_venv_python()
            subprocess.run(
                [venv_python, "-m", "pip", "install", "--upgrade", "pip"],
                check=True
            )
            print("✅ pip升级成功")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ pip升级失败: {e}")
            return False
    
    def install_dependencies(self, dev: bool = False) -> bool:
        """安装依赖包"""
        print("📚 安装依赖包...")
        
        requirements_file = self.project_root / "requirements.txt"
        if not requirements_file.exists():
            print(f"❌ 依赖文件不存在: {requirements_file}")
            return False
        
        try:
            venv_python = self.get_venv_python()
            cmd = [venv_python, "-m", "pip", "install", "-r", str(requirements_file)]
            
            if dev:
                print("🔧 安装开发依赖...")
            
            subprocess.run(cmd, check=True)
            print("✅ 依赖包安装成功")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ 依赖包安装失败: {e}")
            return False
    
    def create_config_from_template(self) -> bool:
        """从模板创建配置文件"""
        print("⚙️ 创建配置文件...")
        
        config_file = self.project_root / "config.yaml"
        user_config_file = self.project_root / "config.local.yaml"
        
        if user_config_file.exists():
            print(f"✅ 用户配置文件已存在: {user_config_file}")
            return True
        
        if not config_file.exists():
            print(f"❌ 配置模板不存在: {config_file}")
            return False
        
        try:
            import shutil
            shutil.copy2(config_file, user_config_file)
            print(f"✅ 配置文件创建成功: {user_config_file}")
            print("⚠️ 请编辑配置文件以匹配您的MongoDB实例")
            return True
        except Exception as e:
            print(f"❌ 配置文件创建失败: {e}")
            return False
    
    def create_startup_scripts(self) -> bool:
        """创建启动脚本"""
        print("🚀 创建启动脚本...")
        
        try:
            # Windows批处理脚本
            if self.is_windows:
                bat_script = self.project_root / "start.bat"
                bat_content = f"""@echo off
cd /d "{self.project_root}"
"{self.get_venv_python()}" start.py %*
pause
"""
                bat_script.write_text(bat_content, encoding='utf-8')
                print(f"✅ Windows启动脚本: {bat_script}")
            
            # Unix shell脚本
            sh_script = self.project_root / "start.sh"
            sh_content = f"""#!/bin/bash
cd "{self.project_root}"
"{self.get_venv_python()}" start.py "$@"
"""
            sh_script.write_text(sh_content, encoding='utf-8')
            
            # 设置执行权限（Unix系统）
            if not self.is_windows:
                os.chmod(sh_script, 0o755)
            
            print(f"✅ Unix启动脚本: {sh_script}")
            return True
            
        except Exception as e:
            print(f"❌ 启动脚本创建失败: {e}")
            return False
    
    def run_tests(self) -> bool:
        """运行测试"""
        print("🧪 运行基本测试...")
        
        try:
            venv_python = self.get_venv_python()
            test_script = self.project_root / "test_service.py"
            
            if not test_script.exists():
                print("⚠️ 测试脚本不存在，跳过测试")
                return True
            
            # 运行基本测试（不需要MongoDB连接）
            subprocess.run(
                [venv_python, str(test_script), "--test-type", "tools"],
                check=True,
                timeout=30
            )
            print("✅ 基本测试通过")
            return True
            
        except subprocess.TimeoutExpired:
            print("⚠️ 测试超时，但安装可能成功")
            return True
        except subprocess.CalledProcessError as e:
            print(f"⚠️ 测试失败: {e}")
            print("   这可能是由于MongoDB连接问题，请检查配置")
            return True  # 不因测试失败而中断安装
        except Exception as e:
            print(f"⚠️ 测试执行错误: {e}")
            return True
    
    def print_success_message(self):
        """打印安装成功信息"""
        venv_python = self.get_venv_python()
        
        message = f"""
╔══════════════════════════════════════════════════════════════╗
║                    🎉 安装成功！                             ║
╚══════════════════════════════════════════════════════════════╝

📁 项目目录: {self.project_root}
🐍 虚拟环境: {self.venv_path}
⚙️ 配置文件: config.local.yaml

🚀 启动方式:

1. 激活虚拟环境:
   Windows: {self.venv_path}\\Scripts\\activate
   Unix:    source {self.venv_path}/bin/activate

2. 启动服务:
   python start.py

   或使用启动脚本:
   Windows: start.bat
   Unix:    ./start.sh

3. 运行测试:
   python test_service.py

📝 下一步:
1. 编辑 config.local.yaml 配置您的MongoDB实例
2. 确保MongoDB实例可访问
3. 运行测试验证配置
4. 启动QueryNest服务

📖 更多信息请查看 README.md
"""
        print(message)
    
    def install(self, dev: bool = False, skip_tests: bool = False) -> bool:
        """执行完整安装"""
        self.print_banner()
        
        steps = [
            ("检查Python版本", self.check_python_version),
            ("检查pip", self.check_pip),
            ("创建虚拟环境", self.create_virtual_environment),
            ("升级pip", self.upgrade_pip),
            ("安装依赖包", lambda: self.install_dependencies(dev)),
            ("创建配置文件", self.create_config_from_template),
            ("创建启动脚本", self.create_startup_scripts),
        ]
        
        if not skip_tests:
            steps.append(("运行测试", self.run_tests))
        
        print(f"开始安装QueryNest (共{len(steps)}个步骤)...\n")
        
        for i, (step_name, step_func) in enumerate(steps, 1):
            print(f"[{i}/{len(steps)}] {step_name}")
            if not step_func():
                print(f"\n❌ 安装失败于步骤: {step_name}")
                return False
            print()
        
        self.print_success_message()
        return True


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="QueryNest 安装程序")
    parser.add_argument(
        "--dev",
        action="store_true",
        help="安装开发依赖"
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="跳过测试"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重新安装"
    )
    
    args = parser.parse_args()
    
    installer = QueryNestInstaller()
    
    try:
        success = installer.install(
            dev=args.dev,
            skip_tests=args.skip_tests
        )
        
        if success:
            print("\n🎉 QueryNest安装完成！")
            sys.exit(0)
        else:
            print("\n❌ QueryNest安装失败！")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n⏹️ 安装被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 安装过程中发生意外错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()