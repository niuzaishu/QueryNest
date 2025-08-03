#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置验证和环境检查工具
"""

import os
import re
import yaml
import logging
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from urllib.parse import urlparse
import socket
from dataclasses import dataclass


@dataclass
class ValidationResult:
    """验证结果"""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    suggestions: List[str]


class ConfigValidator:
    """配置验证器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def validate_config_file(self, config_path: str) -> ValidationResult:
        """验证配置文件"""
        errors = []
        warnings = []
        suggestions = []
        
        try:
            # 检查文件是否存在
            if not os.path.exists(config_path):
                errors.append(f"配置文件不存在: {config_path}")
                suggestions.append("请确保配置文件路径正确")
                return ValidationResult(False, errors, warnings, suggestions)
            
            # 检查文件权限
            if not os.access(config_path, os.R_OK):
                errors.append(f"无法读取配置文件: {config_path}")
                suggestions.append("请检查文件权限")
                return ValidationResult(False, errors, warnings, suggestions)
            
            # 加载并验证YAML格式
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
            except yaml.YAMLError as e:
                errors.append(f"YAML格式错误: {e}")
                suggestions.append("请检查YAML语法")
                return ValidationResult(False, errors, warnings, suggestions)
            
            # 验证配置结构
            structure_result = self._validate_config_structure(config)
            errors.extend(structure_result.errors)
            warnings.extend(structure_result.warnings)
            suggestions.extend(structure_result.suggestions)
            
            # 验证MongoDB配置
            if 'mongodb' in config:
                mongo_result = self._validate_mongodb_config(config['mongodb'])
                errors.extend(mongo_result.errors)
                warnings.extend(mongo_result.warnings)
                suggestions.extend(mongo_result.suggestions)
            
            # 验证安全配置
            if 'security' in config:
                security_result = self._validate_security_config(config['security'])
                errors.extend(security_result.errors)
                warnings.extend(security_result.warnings)
                suggestions.extend(security_result.suggestions)
            
            # 验证MCP配置
            if 'mcp' in config:
                mcp_result = self._validate_mcp_config(config['mcp'])
                errors.extend(mcp_result.errors)
                warnings.extend(mcp_result.warnings)
                suggestions.extend(mcp_result.suggestions)
            
            return ValidationResult(len(errors) == 0, errors, warnings, suggestions)
            
        except Exception as e:
            errors.append(f"验证配置文件时发生错误: {e}")
            return ValidationResult(False, errors, warnings, suggestions)
    
    def _validate_config_structure(self, config: Dict[str, Any]) -> ValidationResult:
        """验证配置结构"""
        errors = []
        warnings = []
        suggestions = []
        
        # 必需的顶级配置项
        required_sections = ['mongodb', 'metadata', 'security', 'mcp']
        for section in required_sections:
            if section not in config:
                errors.append(f"缺少必需的配置节: {section}")
                suggestions.append(f"请添加 {section} 配置节")
        
        # 可选但推荐的配置项
        recommended_sections = ['logging', 'performance', 'monitoring']
        for section in recommended_sections:
            if section not in config:
                warnings.append(f"建议添加配置节: {section}")
                suggestions.append(f"添加 {section} 配置可以提供更好的功能")
        
        return ValidationResult(len(errors) == 0, errors, warnings, suggestions)
    
    def _validate_mongodb_config(self, mongodb_config: Dict[str, Any]) -> ValidationResult:
        """验证MongoDB配置"""
        errors = []
        warnings = []
        suggestions = []
        
        # 检查实例配置
        if 'instances' not in mongodb_config:
            errors.append("MongoDB配置中缺少 instances 节")
            suggestions.append("请配置至少一个MongoDB实例")
            return ValidationResult(False, errors, warnings, suggestions)
        
        instances = mongodb_config['instances']
        if not isinstance(instances, dict) or len(instances) == 0:
            errors.append("MongoDB实例配置为空")
            suggestions.append("请配置至少一个MongoDB实例")
            return ValidationResult(False, errors, warnings, suggestions)
        
        # 验证每个实例
        for instance_name, instance_config in instances.items():
            instance_result = self._validate_mongodb_instance(instance_name, instance_config)
            errors.extend(instance_result.errors)
            warnings.extend(instance_result.warnings)
            suggestions.extend(instance_result.suggestions)
        
        return ValidationResult(len(errors) == 0, errors, warnings, suggestions)
    
    def _validate_mongodb_instance(self, instance_name: str, instance_config: Dict[str, Any]) -> ValidationResult:
        """验证MongoDB实例配置"""
        errors = []
        warnings = []
        suggestions = []
        
        # 必需字段
        required_fields = ['connection_string']
        for field in required_fields:
            if field not in instance_config:
                errors.append(f"实例 {instance_name} 缺少必需字段: {field}")
        
        # 验证连接字符串
        if 'connection_string' in instance_config:
            connection_string = instance_config['connection_string']
            if not isinstance(connection_string, str) or not connection_string.strip():
                errors.append(f"实例 {instance_name} 的连接字符串无效: {connection_string}")
                suggestions.append("请提供有效的MongoDB连接字符串")
            elif not connection_string.startswith('mongodb://'):
                warnings.append(f"实例 {instance_name} 的连接字符串格式可能不正确")
                suggestions.append("建议使用标准的MongoDB连接字符串格式: mongodb://...")
        
        # 验证主机名（可选，用于向后兼容）
        if 'host' in instance_config:
            host = instance_config['host']
            if not self._is_valid_hostname(host):
                warnings.append(f"实例 {instance_name} 的主机名无效: {host}")
                suggestions.append("建议使用connection_string替代host和port配置")
        
        # 验证端口（可选，用于向后兼容）
        if 'port' in instance_config:
            port = instance_config['port']
            if not isinstance(port, int) or port < 1 or port > 65535:
                warnings.append(f"实例 {instance_name} 的端口号无效: {port}")
                suggestions.append("建议使用connection_string替代host和port配置")
        
        # 验证认证配置
        if 'username' in instance_config and 'password' not in instance_config:
            warnings.append(f"实例 {instance_name} 配置了用户名但没有密码")
            suggestions.append("建议同时配置用户名和密码")
        
        # 验证SSL配置
        if 'ssl' in instance_config:
            ssl_config = instance_config['ssl']
            if ssl_config.get('enabled', False):
                if 'ca_file' in ssl_config and not os.path.exists(ssl_config['ca_file']):
                    errors.append(f"实例 {instance_name} 的SSL CA文件不存在: {ssl_config['ca_file']}")
                if 'cert_file' in ssl_config and not os.path.exists(ssl_config['cert_file']):
                    errors.append(f"实例 {instance_name} 的SSL证书文件不存在: {ssl_config['cert_file']}")
        
        # 验证连接池配置
        if 'connection_pool' in instance_config:
            pool_config = instance_config['connection_pool']
            max_size = pool_config.get('max_size', 10)
            min_size = pool_config.get('min_size', 1)
            
            if max_size < min_size:
                errors.append(f"实例 {instance_name} 的连接池最大值小于最小值")
            
            if max_size > 100:
                warnings.append(f"实例 {instance_name} 的连接池大小过大: {max_size}")
                suggestions.append("建议连接池大小不超过100")
        
        return ValidationResult(len(errors) == 0, errors, warnings, suggestions)
    
    def _validate_security_config(self, security_config: Dict[str, Any]) -> ValidationResult:
        """验证安全配置"""
        errors = []
        warnings = []
        suggestions = []
        
        # 验证查询权限
        if 'query_permissions' in security_config:
            perms = security_config['query_permissions']
            
            if not perms.get('read_only', True):
                warnings.append("已禁用只读模式，这可能带来安全风险")
                suggestions.append("建议启用只读模式以确保数据安全")
            
            # 验证查询限制
            if 'query_limits' in perms:
                limits = perms['query_limits']
                
                max_docs = limits.get('max_documents_returned', 1000)
                if max_docs > 10000:
                    warnings.append(f"最大返回文档数过大: {max_docs}")
                    suggestions.append("建议限制返回文档数以提高性能")
                
                timeout = limits.get('query_timeout_seconds', 30)
                if timeout > 300:  # 5分钟
                    warnings.append(f"查询超时时间过长: {timeout}秒")
                    suggestions.append("建议设置合理的查询超时时间")
        
        # 验证数据脱敏配置
        if 'data_masking' in security_config:
            masking = security_config['data_masking']
            
            if not masking.get('enabled', False):
                warnings.append("数据脱敏功能未启用")
                suggestions.append("建议启用数据脱敏以保护敏感信息")
            
            # 验证敏感字段配置
            if 'sensitive_fields' in masking:
                sensitive_fields = masking['sensitive_fields']
                if not sensitive_fields:
                    warnings.append("未配置敏感字段")
                    suggestions.append("请配置需要脱敏的敏感字段")
        
        return ValidationResult(len(errors) == 0, errors, warnings, suggestions)
    
    def _validate_mcp_config(self, mcp_config: Dict[str, Any]) -> ValidationResult:
        """验证MCP配置"""
        errors = []
        warnings = []
        suggestions = []
        
        # 验证服务配置
        if 'server' in mcp_config:
            server_config = mcp_config['server']
            
            # 验证端口
            if 'port' in server_config:
                port = server_config['port']
                if not isinstance(port, int) or port < 1024 or port > 65535:
                    warnings.append(f"MCP服务端口可能不合适: {port}")
                    suggestions.append("建议使用1024-65535之间的端口")
        
        # 验证工具配置
        if 'tools' in mcp_config:
            tools_config = mcp_config['tools']
            
            # 检查是否启用了基本工具
            basic_tools = ['query_tools', 'discovery_tools']
            for tool in basic_tools:
                if not tools_config.get(tool, {}).get('enabled', True):
                    warnings.append(f"基本工具 {tool} 未启用")
                    suggestions.append(f"建议启用 {tool} 以获得完整功能")
        
        return ValidationResult(len(errors) == 0, errors, warnings, suggestions)
    
    def _is_valid_hostname(self, hostname: str) -> bool:
        """验证主机名是否有效"""
        if not hostname:
            return False
        
        # 检查是否为IP地址
        try:
            socket.inet_aton(hostname)
            return True
        except socket.error:
            pass
        
        # 检查是否为有效的主机名
        if len(hostname) > 255:
            return False
        
        # 主机名规则
        hostname_pattern = re.compile(
            r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?'
            r'(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$'
        )
        
        return bool(hostname_pattern.match(hostname))


class EnvironmentChecker:
    """环境检查器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def check_environment(self) -> ValidationResult:
        """检查运行环境"""
        errors = []
        warnings = []
        suggestions = []
        
        # 检查Python版本
        python_result = self._check_python_version()
        errors.extend(python_result.errors)
        warnings.extend(python_result.warnings)
        suggestions.extend(python_result.suggestions)
        
        # 检查依赖包
        deps_result = self._check_dependencies()
        errors.extend(deps_result.errors)
        warnings.extend(deps_result.warnings)
        suggestions.extend(deps_result.suggestions)
        
        # 检查环境变量
        env_result = self._check_environment_variables()
        errors.extend(env_result.errors)
        warnings.extend(env_result.warnings)
        suggestions.extend(env_result.suggestions)
        
        # 检查文件权限
        perms_result = self._check_file_permissions()
        errors.extend(perms_result.errors)
        warnings.extend(perms_result.warnings)
        suggestions.extend(perms_result.suggestions)
        
        # 检查网络连接
        network_result = self._check_network_connectivity()
        errors.extend(network_result.errors)
        warnings.extend(network_result.warnings)
        suggestions.extend(network_result.suggestions)
        
        return ValidationResult(len(errors) == 0, errors, warnings, suggestions)
    
    def _check_python_version(self) -> ValidationResult:
        """检查Python版本"""
        import sys
        
        errors = []
        warnings = []
        suggestions = []
        
        version = sys.version_info
        
        if version.major < 3:
            errors.append(f"Python版本过低: {version.major}.{version.minor}")
            suggestions.append("请升级到Python 3.8或更高版本")
        elif version.minor < 8:
            warnings.append(f"Python版本较低: {version.major}.{version.minor}")
            suggestions.append("建议升级到Python 3.8或更高版本")
        
        return ValidationResult(len(errors) == 0, errors, warnings, suggestions)
    
    def _check_dependencies(self) -> ValidationResult:
        """检查依赖包"""
        errors = []
        warnings = []
        suggestions = []
        
        required_packages = {
            'pymongo': '4.0.0',
            'yaml': '5.0.0',  # pyyaml包的导入名是yaml
            'asyncio': None  # 内置包
        }
        
        # 包名映射（导入名 -> 包名）
        package_name_mapping = {
            'yaml': 'pyyaml'
        }
        
        for package, min_version in required_packages.items():
            try:
                if package == 'asyncio':
                    import asyncio
                    continue
                
                __import__(package)
                
                if min_version:
                    try:
                        import pkg_resources
                        # 使用真实包名检查版本
                        real_package_name = package_name_mapping.get(package, package)
                        installed_version = pkg_resources.get_distribution(real_package_name).version
                        if pkg_resources.parse_version(installed_version) < pkg_resources.parse_version(min_version):
                            warnings.append(f"包 {real_package_name} 版本过低: {installed_version} < {min_version}")
                            suggestions.append(f"请升级 {real_package_name} 到 {min_version} 或更高版本")
                    except Exception:
                        real_package_name = package_name_mapping.get(package, package)
                        warnings.append(f"无法检查包 {real_package_name} 的版本")
                
            except ImportError:
                real_package_name = package_name_mapping.get(package, package)
                errors.append(f"缺少必需的包: {real_package_name}")
                suggestions.append(f"请安装 {real_package_name}: pip install {real_package_name}")
        
        return ValidationResult(len(errors) == 0, errors, warnings, suggestions)
    
    def _check_environment_variables(self) -> ValidationResult:
        """检查环境变量"""
        errors = []
        warnings = []
        suggestions = []
        
        # 检查重要的环境变量
        important_vars = [
            'QUERYNEST_CONFIG_PATH',
            'QUERYNEST_LOG_LEVEL'
        ]
        
        for var in important_vars:
            if var not in os.environ:
                warnings.append(f"环境变量 {var} 未设置")
                suggestions.append(f"建议设置环境变量 {var}")
        
        # 检查配置文件路径
        config_path = os.environ.get('QUERYNEST_CONFIG_PATH')
        if config_path and not os.path.exists(config_path):
            errors.append(f"配置文件路径不存在: {config_path}")
            suggestions.append("请检查 QUERYNEST_CONFIG_PATH 环境变量")
        
        return ValidationResult(len(errors) == 0, errors, warnings, suggestions)
    
    def _check_file_permissions(self) -> ValidationResult:
        """检查文件权限"""
        errors = []
        warnings = []
        suggestions = []
        
        # 检查当前目录权限
        current_dir = os.getcwd()
        
        if not os.access(current_dir, os.R_OK):
            errors.append(f"无法读取当前目录: {current_dir}")
        
        if not os.access(current_dir, os.W_OK):
            warnings.append(f"无法写入当前目录: {current_dir}")
            suggestions.append("某些功能可能需要写入权限")
        
        # 检查日志目录
        log_dir = os.path.join(current_dir, 'logs')
        if not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir, exist_ok=True)
            except PermissionError:
                warnings.append(f"无法创建日志目录: {log_dir}")
                suggestions.append("请手动创建日志目录或检查权限")
        
        return ValidationResult(len(errors) == 0, errors, warnings, suggestions)
    
    def _check_network_connectivity(self) -> ValidationResult:
        """检查网络连接"""
        errors = []
        warnings = []
        suggestions = []
        
        # 检查基本网络连接
        try:
            socket.create_connection(('8.8.8.8', 53), timeout=5)
        except (socket.timeout, socket.error):
            warnings.append("网络连接可能存在问题")
            suggestions.append("请检查网络连接")
        
        return ValidationResult(len(errors) == 0, errors, warnings, suggestions)
    
    def check_mongodb_connectivity(self, instances_config: Dict[str, Any]) -> ValidationResult:
        """检查MongoDB连接"""
        errors = []
        warnings = []
        suggestions = []
        
        for instance_name, config in instances_config.items():
            try:
                host = config.get('host', 'localhost')
                port = config.get('port', 27017)
                
                # 尝试TCP连接
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                result = sock.connect_ex((host, port))
                sock.close()
                
                if result != 0:
                    errors.append(f"无法连接到MongoDB实例 {instance_name} ({host}:{port})")
                    suggestions.append(f"请检查实例 {instance_name} 的网络连接和配置")
                
            except Exception as e:
                errors.append(f"检查MongoDB实例 {instance_name} 连接时发生错误: {e}")
        
        return ValidationResult(len(errors) == 0, errors, warnings, suggestions)


def validate_startup_environment() -> Tuple[bool, List[str]]:
    """验证启动环境"""
    validator = ConfigValidator()
    env_checker = EnvironmentChecker()
    
    all_errors = []
    all_warnings = []
    all_suggestions = []
    
    # 检查环境
    env_result = env_checker.check_environment()
    all_errors.extend(env_result.errors)
    all_warnings.extend(env_result.warnings)
    all_suggestions.extend(env_result.suggestions)
    
    # 检查配置文件
    config_path = os.environ.get('QUERYNEST_CONFIG_PATH', 'config.yaml')
    if os.path.exists(config_path):
        config_result = validator.validate_config_file(config_path)
        all_errors.extend(config_result.errors)
        all_warnings.extend(config_result.warnings)
        all_suggestions.extend(config_result.suggestions)
    
    # 生成报告
    messages = []
    
    if all_errors:
        messages.append("❌ 发现以下错误:")
        for error in all_errors:
            messages.append(f"  • {error}")
    
    if all_warnings:
        messages.append("⚠️  发现以下警告:")
        for warning in all_warnings:
            messages.append(f"  • {warning}")
    
    if all_suggestions:
        messages.append("💡 建议:")
        for suggestion in all_suggestions:
            messages.append(f"  • {suggestion}")
    
    if not all_errors and not all_warnings:
        messages.append("✅ 环境检查通过")
    
    return len(all_errors) == 0, messages