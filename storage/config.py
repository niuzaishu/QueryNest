# -*- coding: utf-8 -*-
"""
本地语义存储配置管理

提供配置参数管理和验证功能
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
import structlog


logger = structlog.get_logger(__name__)


@dataclass
class LocalStorageConfig:
    """本地存储配置类"""
    
    # 基础路径配置
    base_path: Path = field(default_factory=lambda: Path("./semantic_data"))
    
    # 缓存配置
    cache_enabled: bool = True
    cache_size: int = 1000
    cache_ttl: int = 300  # 5分钟
    
    # 性能配置
    max_concurrent_operations: int = 10
    batch_size: int = 100
    
    # 文件配置
    use_compression: bool = False
    backup_enabled: bool = True
    backup_retention_days: int = 30
    
    # 索引配置
    enable_search_index: bool = True
    index_update_interval: int = 60  # 秒
    
    # 安全配置
    enable_file_locking: bool = True
    atomic_writes: bool = True
    
    # 日志配置
    log_level: str = "INFO"
    log_file_operations: bool = False
    
    def __post_init__(self):
        """配置验证和初始化"""
        # 确保路径是Path对象
        if isinstance(self.base_path, str):
            self.base_path = Path(self.base_path)
        
        # 验证配置参数
        self._validate_config()
        
        # 创建基础目录
        self._ensure_directories()
    
    def _validate_config(self):
        """验证配置参数"""
        if self.cache_size <= 0:
            raise ValueError("cache_size must be positive")
        
        if self.cache_ttl <= 0:
            raise ValueError("cache_ttl must be positive")
        
        if self.max_concurrent_operations <= 0:
            raise ValueError("max_concurrent_operations must be positive")
        
        if self.batch_size <= 0:
            raise ValueError("batch_size must be positive")
        
        if self.backup_retention_days < 0:
            raise ValueError("backup_retention_days cannot be negative")
        
        if self.index_update_interval <= 0:
            raise ValueError("index_update_interval must be positive")
        
        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.log_level not in valid_log_levels:
            raise ValueError(f"log_level must be one of {valid_log_levels}")
    
    def _ensure_directories(self):
        """确保必要的目录存在"""
        try:
            # 创建基础目录
            self.base_path.mkdir(parents=True, exist_ok=True)
            
            # 创建子目录
            (self.base_path / "instances").mkdir(exist_ok=True)
            (self.base_path / "indexes").mkdir(exist_ok=True)
            
            if self.backup_enabled:
                (self.base_path / "backups").mkdir(exist_ok=True)
            
            logger.info("存储目录初始化完成", base_path=str(self.base_path))
            
        except Exception as e:
            logger.error("创建存储目录失败", base_path=str(self.base_path), error=str(e))
            raise
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'LocalStorageConfig':
        """从字典创建配置"""
        # 处理路径字段
        if 'base_path' in config_dict:
            config_dict['base_path'] = Path(config_dict['base_path'])
        
        return cls(**config_dict)
    

    
    @classmethod
    def from_env(cls, prefix: str = "SEMANTIC_STORAGE_") -> 'LocalStorageConfig':
        """从环境变量创建配置"""
        config_dict = {}
        
        # 定义环境变量映射
        env_mappings = {
            f"{prefix}BASE_PATH": ("base_path", str),
            f"{prefix}CACHE_ENABLED": ("cache_enabled", lambda x: x.lower() == 'true'),
            f"{prefix}CACHE_SIZE": ("cache_size", int),
            f"{prefix}CACHE_TTL": ("cache_ttl", int),
            f"{prefix}MAX_CONCURRENT_OPERATIONS": ("max_concurrent_operations", int),
            f"{prefix}BATCH_SIZE": ("batch_size", int),
            f"{prefix}USE_COMPRESSION": ("use_compression", lambda x: x.lower() == 'true'),
            f"{prefix}BACKUP_ENABLED": ("backup_enabled", lambda x: x.lower() == 'true'),
            f"{prefix}BACKUP_RETENTION_DAYS": ("backup_retention_days", int),
            f"{prefix}ENABLE_SEARCH_INDEX": ("enable_search_index", lambda x: x.lower() == 'true'),
            f"{prefix}INDEX_UPDATE_INTERVAL": ("index_update_interval", int),
            f"{prefix}ENABLE_FILE_LOCKING": ("enable_file_locking", lambda x: x.lower() == 'true'),
            f"{prefix}ATOMIC_WRITES": ("atomic_writes", lambda x: x.lower() == 'true'),
            f"{prefix}LOG_LEVEL": ("log_level", str),
            f"{prefix}LOG_FILE_OPERATIONS": ("log_file_operations", lambda x: x.lower() == 'true'),
        }
        
        # 从环境变量读取配置
        for env_key, (config_key, converter) in env_mappings.items():
            env_value = os.getenv(env_key)
            if env_value is not None:
                try:
                    config_dict[config_key] = converter(env_value)
                except (ValueError, TypeError) as e:
                    logger.warning(
                        "环境变量转换失败",
                        env_key=env_key,
                        env_value=env_value,
                        error=str(e)
                    )
        
        return cls.from_dict(config_dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {}
        for key, value in self.__dict__.items():
            if isinstance(value, Path):
                result[key] = str(value)
            else:
                result[key] = value
        return result
    
    def get_instance_path(self, instance_name: str) -> Path:
        """获取实例路径"""
        return self.base_path / "instances" / instance_name
    
    def get_index_path(self) -> Path:
        """获取索引路径"""
        return self.base_path / "indexes"
    
    def get_backup_path(self) -> Path:
        """获取备份路径"""
        return self.base_path / "backups"
    
    def update_from_dict(self, updates: Dict[str, Any]):
        """从字典更新配置"""
        for key, value in updates.items():
            if hasattr(self, key):
                if key == 'base_path' and isinstance(value, str):
                    value = Path(value)
                setattr(self, key, value)
            else:
                logger.warning("未知配置项", key=key, value=value)
        
        # 重新验证配置
        self._validate_config()
        
        # 确保目录存在
        self._ensure_directories()
    
    def get_performance_config(self) -> Dict[str, Any]:
        """获取性能相关配置"""
        return {
            "cache_enabled": self.cache_enabled,
            "cache_size": self.cache_size,
            "cache_ttl": self.cache_ttl,
            "max_concurrent_operations": self.max_concurrent_operations,
            "batch_size": self.batch_size,
            "use_compression": self.use_compression,
            "enable_search_index": self.enable_search_index,
            "index_update_interval": self.index_update_interval,
        }
    
    def get_security_config(self) -> Dict[str, Any]:
        """获取安全相关配置"""
        return {
            "enable_file_locking": self.enable_file_locking,
            "atomic_writes": self.atomic_writes,
        }
    
    def get_backup_config(self) -> Dict[str, Any]:
        """获取备份相关配置"""
        return {
            "backup_enabled": self.backup_enabled,
            "backup_retention_days": self.backup_retention_days,
            "backup_path": str(self.get_backup_path()),
        }


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_file: Optional[Path] = None):
        self.config_file = config_file or Path("semantic_storage_config.json")
        self._config: Optional[LocalStorageConfig] = None
    
    def load_config(self) -> LocalStorageConfig:
        """加载配置"""
        if self._config is not None:
            return self._config
        
        # 优先级：配置文件 > 环境变量 > 默认值
        if self.config_file.exists():
            self._config = self._load_from_file()
        else:
            # 尝试从环境变量加载
            self._config = LocalStorageConfig.from_env()
        
        logger.info(
            "配置加载完成",
            config_source="file" if self.config_file.exists() else "env/default",
            base_path=str(self._config.base_path)
        )
        
        return self._config
    
    def _load_from_file(self) -> LocalStorageConfig:
        """从文件加载配置"""
        # 尝试从环境变量加载
        try:
            return LocalStorageConfig.from_env()
        except Exception as e:
            logger.warning(
                "环境变量配置加载失败，使用默认配置",
                error=str(e)
            )
        
        # 返回默认配置
        return LocalStorageConfig()
    

    
    def get_config(self) -> LocalStorageConfig:
        """获取当前配置"""
        if self._config is None:
            return self.load_config()
        return self._config
    
    def update_config(self, updates: Dict[str, Any]):
        """更新配置"""
        config = self.get_config()
        config.update_from_dict(updates)
        self.save_config(config)
    
    def reset_config(self):
        """重置为默认配置"""
        self._config = LocalStorageConfig()
        self.save_config(self._config)


# 全局配置管理器实例
_config_manager = ConfigManager()


def get_config() -> LocalStorageConfig:
    """获取全局配置"""
    # 优先尝试加载YAML配置文件
    yaml_config_path = os.path.join(os.path.dirname(__file__), 'local_storage.yaml')
    if os.path.exists(yaml_config_path):
        return LocalStorageConfig.load_from_file(yaml_config_path)
    else:
        return _config_manager.get_config()


def update_config(updates: Dict[str, Any]):
    """更新全局配置"""
    _config_manager.update_config(updates)


def reset_config():
    """重置全局配置"""
    _config_manager.reset_config()