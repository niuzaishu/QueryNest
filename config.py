# -*- coding: utf-8 -*-
"""配置管理模块"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, validator, ConfigDict
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
    
    @validator('environment')
    def validate_environment(cls, v):
        # 移除硬编码的环境限制，支持任意环境命名
        # 只进行基本的字符串验证
        if not isinstance(v, str) or not v.strip():
            raise ValueError('环境类型必须是非空字符串')
        return v.strip()
    
    @validator('status')
    def validate_status(cls, v):
        if v not in ['active', 'inactive']:
            raise ValueError('状态必须是 active 或 inactive')
        return v


class MetadataConfig(BaseModel):
    """元数据库配置"""
    database: str = Field(default="querynest_metadata", description="元数据库名称")
    # 注意：每个实例都会创建独立的querynest_metadata库，不再需要单独的连接字符串
    

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
    name: str = Field(default="querynest", description="MCP服务名称")
    version: str = Field(default="0.1.0", description="服务版本")
    description: str = Field(
        default="QueryNest MCP MongoDB查询服务",
        description="服务描述"
    )
    transport: str = Field(default="stdio", description="传输方式")
    host: Optional[str] = Field(default=None, description="HTTP服务主机")
    port: Optional[int] = Field(default=None, description="HTTP服务端口")


class LoggingConfig(BaseModel):
    """日志配置"""
    level: str = Field(default="INFO", description="日志级别")
    format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="日志格式"
    )
    file_path: Optional[str] = Field(default=None, description="日志文件路径")
    max_size: int = Field(default=10485760, description="日志文件最大大小（字节）")
    backup_count: int = Field(default=5, description="日志文件备份数量")


class QueryNestConfig(BaseSettings):
    """QueryNest主配置"""
    mongo_instances: Dict[str, MongoInstanceConfig] = Field(default={}, description="MongoDB实例字典")
    security: SecurityConfig = Field(default_factory=SecurityConfig, description="安全配置")
    mcp: MCPConfig = Field(default_factory=MCPConfig, description="MCP服务配置")
    cache: Optional[Dict[str, Any]] = Field(default=None, description="缓存配置")
    connection_pool: Optional[Dict[str, Any]] = Field(default=None, description="连接池配置")
    logging: Optional[Dict[str, Any]] = Field(default=None, description="日志配置")
    monitoring: Optional[Dict[str, Any]] = Field(default=None, description="监控配置")
    performance: Optional[Dict[str, Any]] = Field(default=None, description="性能配置")
    development: Optional[Dict[str, Any]] = Field(default=None, description="开发配置")
    
    model_config = ConfigDict(
        env_prefix="QUERYNEST_",
        env_file=".env",
        extra="allow"
    )
        
    @classmethod
    def from_yaml(cls, config_path: str) -> "QueryNestConfig":
        """从YAML文件加载配置"""
        config_file = Path(config_path)
        
        # 如果是相对路径，优先相对于当前工作目录解析
        if not config_file.is_absolute():
            # 首先尝试相对于当前工作目录
            cwd_config = Path.cwd() / config_path
            if cwd_config.exists():
                config_file = cwd_config
            else:
                # 如果当前工作目录没有找到，则相对于当前文件所在目录解析
                current_dir = Path(__file__).parent
                config_file = current_dir / config_path
        
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