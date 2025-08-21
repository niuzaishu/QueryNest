# -*- coding: utf-8 -*-
"""配置管理模块"""

import os
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator, ConfigDict
from pydantic_settings import BaseSettings
import yaml
from pathlib import Path


class MongoInstanceConfig(BaseModel):
    """MongoDB实例配置"""
    name: str = Field(..., description="实例名称")
    alias: Optional[str] = Field(default=None, description="实例别名")
    connection_string: str = Field(..., description="连接字符串")
    environment: str = Field(default="dev", description="环境类型")
    description: str = Field(default="", description="实例描述")
    status: str = Field(default="active", description="实例状态")
    
    @field_validator('environment')
    @classmethod
    def validate_environment(cls, v):
        # 移除硬编码的环境限制，支持任意环境命名
        # 只进行基本的字符串验证
        if not isinstance(v, str) or not v.strip():
            raise ValueError('环境类型必须是非空字符串')
        return v.strip()
    
    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        if v not in ['active', 'inactive']:
            raise ValueError('状态必须是 active 或 inactive')
        return v


class StorageConfig(BaseModel):
    """存储配置"""
    metadata_path: str = Field(default="data/metadata", description="元数据存储路径")
    semantic_path: str = Field(default="data/semantics", description="语义数据存储路径")
    retention: Optional[Dict[str, int]] = Field(default=None, description="数据保留策略")
    

class SecurityConfig(BaseModel):
    """安全配置"""
    query_timeout: int = Field(default=30, description="查询超时时间（秒）")
    max_result_size: int = Field(default=1000, description="最大结果集大小")
    allowed_operations: List[str] = Field(
        default=["find", "aggregate", "count", "distinct"],
        description="允许的操作类型"
    )
    sensitive_fields: List[str] = Field(
        default=["password", "token", "secret", "key"],
        description="敏感字段关键词"
    )


class ScannerConfig(BaseModel):
    """
    数据库扫描器配置
    """
    enabled: bool = True
    scan_interval: int = 3600  # 扫描间隔（秒）
    max_sample_documents: int = 100  # 最大样本文档数
    field_analysis_depth: int = 3  # 字段分析深度
    semantic_analysis: bool = True  # 是否启用语义分析
    
    class Config:
        """Pydantic配置"""
        arbitrary_types_allowed = True


class MCPConfig(BaseModel):
    """MCP服务配置"""
    name: str = Field(default="QueryNest", description="MCP服务名称")
    version: str = Field(default="1.0.0", description="服务版本")
    description: str = Field(
        default="MongoDB多实例查询服务",
        description="服务描述"
    )


class LoggingFileConfig(BaseModel):
    """日志文件配置"""
    enabled: bool = Field(default=True, description="是否启用文件日志")
    path: str = Field(default="logs/querynest.log", description="日志文件路径")
    max_size: str = Field(default="100MB", description="日志文件最大大小")
    backup_count: int = Field(default=5, description="日志文件备份数量")


class LoggingConfig(BaseModel):
    """日志配置"""
    level: str = Field(default="INFO", description="日志级别")
    format: str = Field(default="json", description="日志格式")
    file: LoggingFileConfig = Field(default_factory=LoggingFileConfig, description="文件日志配置")


class ConnectionPoolConfig(BaseModel):
    """连接池配置"""
    health_check_interval: int = Field(default=30, description="健康检查间隔（秒）")
    max_retries: int = Field(default=3, description="连接重试次数")
    retry_interval: int = Field(default=5, description="重试间隔（秒）")


class ToolsConfig(BaseModel):
    """工具配置"""
    max_retries: int = Field(default=3, description="最大重试次数")
    retry_delay: float = Field(default=1.0, description="重试延迟（秒）")
    backoff_factor: float = Field(default=2.0, description="退避因子")


class QueryNestConfig(BaseSettings):
    """QueryNest主配置"""
    mongo_instances: Dict[str, MongoInstanceConfig] = Field(default={}, description="MongoDB实例字典")
    storage: StorageConfig = Field(default_factory=StorageConfig, description="存储配置")
    security: SecurityConfig = Field(default_factory=SecurityConfig, description="安全配置")
    mcp: MCPConfig = Field(default_factory=MCPConfig, description="MCP服务配置")
    logging: LoggingConfig = Field(default_factory=LoggingConfig, description="日志配置")
    connection_pool: ConnectionPoolConfig = Field(default_factory=ConnectionPoolConfig, description="连接池配置")
    tools: ToolsConfig = Field(default_factory=ToolsConfig, description="工具配置")
    
    model_config = ConfigDict(
        env_prefix="QUERYNEST_",
        env_file=".env",
        extra="allow"
    )
        
    @classmethod
    def from_yaml(cls, config_path: str) -> "QueryNestConfig":
        """从YAML文件加载配置"""
        config_file = Path(config_path)
        
        # 如果是相对路径，使用多种策略查找配置文件
        if not config_file.is_absolute():
            search_paths = [
                # 1. 当前工作目录
                Path.cwd() / config_path,
                # 2. 项目根目录（config.py 所在目录）
                Path(__file__).parent / config_path,
                # 3. 环境变量指定的配置目录
                Path(os.environ.get('QUERYNEST_CONFIG_DIR', '.')) / config_path,
                # 4. 用户主目录下的 .querynest 目录
                Path.home() / '.querynest' / config_path,
                # 5. /etc/querynest/ 目录（Linux/Unix 系统）
                Path('/etc/querynest') / config_path,
            ]
            
            # 尝试每个路径
            config_file = None
            for search_path in search_paths:
                if search_path.exists():
                    config_file = search_path
                    break
            
            if config_file is None:
                # 生成详细的错误信息，显示所有搜索的路径
                searched_paths = '\n  - '.join([str(p) for p in search_paths])
                raise FileNotFoundError(
                    f"Configuration file not found: {config_path}\n"
                    f"Searched in:\n  - {searched_paths}"
                )
        else:
            # 绝对路径直接检查
            if not config_file.exists():
                raise FileNotFoundError(f"Configuration file not found: {config_path}")
            
            
        with open(config_file, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
        
        # 处理mongodb.instances格式，转换为mongo_instances格式
        if 'mongodb' in config_data and 'instances' in config_data['mongodb']:
            config_data['mongo_instances'] = config_data['mongodb']['instances']
            
        return cls(**config_data)
    
    def to_yaml(self, config_path: str) -> None:
        """保存配置到YAML文件"""
        config_file = Path(config_path)
        config_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(config_file, 'w', encoding='utf-8') as f:
            yaml.dump(
                self.dict(),
                f,
                default_flow_style=False,
                allow_unicode=True,
                indent=2
            )
    
    def get_instance_by_name(self, name: str) -> Optional[MongoInstanceConfig]:
        """根据名称获取实例配置"""
        for instance in self.mongo_instances.values():
            if instance.name == name:
                return instance
        return None
    
    def get_active_instances(self) -> List[MongoInstanceConfig]:
        """获取所有活跃的实例配置"""
        return [instance for instance in self.mongo_instances.values() if instance.status == "active"]
    
    def validate_config(self) -> List[str]:
        """验证配置有效性"""
        errors = []
        
        # 检查实例名称唯一性
        instance_names = [instance.name for instance in self.mongo_instances.values()]
        if len(instance_names) != len(set(instance_names)):
            errors.append("实例名称必须唯一")
        
        # 检查至少有一个活跃实例
        active_instances = self.get_active_instances()
        if not active_instances:
            errors.append("至少需要一个活跃的MongoDB实例")
        
        return errors


# 全局配置实例
config: Optional[QueryNestConfig] = None


def load_config(config_path: str = None) -> QueryNestConfig:
    """加载配置"""
    global config
     
    if config_path is None:
        import os
        config_path = os.getenv('QUERYNEST_CONFIG_PATH', 'config.yaml')
     
    config = QueryNestConfig.from_yaml(config_path)
    
    # 验证配置
    errors = config.validate_config()
    if errors:
        raise ValueError(f"配置验证失败: {', '.join(errors)}")
    
    return config


def get_config() -> QueryNestConfig:
    """获取当前配置"""
    if config is None:
        raise RuntimeError("配置未加载，请先调用 load_config()")
    return config


class ConfigLoader:
    """配置加载器"""
    
    def __init__(self, config_path: str = None):
        if config_path is None:
            import os
            config_path = os.getenv('QUERYNEST_CONFIG_PATH', 'config.yaml')
        
        self.config_path = config_path
    
    def load_config(self) -> QueryNestConfig:
        """加载配置文件"""
        return load_config(self.config_path)