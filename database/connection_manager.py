# -*- coding: utf-8 -*-
"""多实例MongoDB连接管理器"""

import asyncio
from typing import Dict, List, Optional, Any
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
import structlog
from datetime import datetime, timedelta

from config import QueryNestConfig, MongoInstanceConfig


logger = structlog.get_logger(__name__)


class InstanceConnection:
    """单个MongoDB实例连接"""
    
    def __init__(self, config: MongoInstanceConfig):
        self.config = config
        self.client: Optional[AsyncIOMotorClient] = None
        self.last_health_check: Optional[datetime] = None
        self.is_healthy = False
        self._lock = asyncio.Lock()
        self._connection_stats = {
            'total_connections': 0,
            'active_connections': 0,
            'failed_connections': 0,
            'last_connection_time': None
        }
    
    def _get_optimal_pool_config(self) -> dict:
        """获取最优连接池配置"""
        # 根据环境和负载动态调整连接池大小
        if self.config.environment == "production":
            return {
                "maxPoolSize": 20,
                "minPoolSize": 5,
                "maxIdleTimeMS": 30000,
                "waitQueueTimeoutMS": 10000
            }
        elif self.config.environment == "staging":
            return {
                "maxPoolSize": 10,
                "minPoolSize": 2,
                "maxIdleTimeMS": 60000,
                "waitQueueTimeoutMS": 5000
            }
        else:  # development
            return {
                "maxPoolSize": 5,
                "minPoolSize": 1,
                "maxIdleTimeMS": 120000,
                "waitQueueTimeoutMS": 3000
            }
    
    async def connect(self) -> bool:
        """连接到MongoDB实例"""
        async with self._lock:
            if self.client is not None:
                return True
            
            try:
                # 动态连接池配置
                pool_config = self._get_optimal_pool_config()
                
                self.client = AsyncIOMotorClient(
                    self.config.connection_string,
                    serverSelectionTimeoutMS=5000,
                    connectTimeoutMS=5000,
                    **pool_config
                )
                
                # 测试连接
                await self.client.admin.command('ping')
                self.is_healthy = True
                self.last_health_check = datetime.now()
                
                # 更新连接统计
                self._connection_stats['total_connections'] += 1
                self._connection_stats['active_connections'] += 1
                self._connection_stats['last_connection_time'] = datetime.now()
                
                logger.info(
                    "MongoDB实例连接成功",
                    instance_name=self.config.name,
                    environment=self.config.environment,
                    pool_config=pool_config
                )
                return True
                
            except (ConnectionFailure, ServerSelectionTimeoutError) as e:
                self.is_healthy = False
                self._connection_stats['failed_connections'] += 1
                logger.error(
                    "MongoDB实例连接失败",
                    instance_name=self.config.name,
                    error=str(e)
                )
                return False
            except Exception as e:
                self.is_healthy = False
                self._connection_stats['failed_connections'] += 1
                logger.error(
                    "MongoDB实例连接异常",
                    instance_name=self.config.name,
                    error=str(e)
                )
                return False
    
    async def disconnect(self):
        """断开连接"""
        async with self._lock:
            if self.client:
                self.client.close()
                self.client = None
                self.is_healthy = False
                
                # 更新连接统计
                if self._connection_stats['active_connections'] > 0:
                    self._connection_stats['active_connections'] -= 1
                
                logger.info("MongoDB实例连接已断开", instance_name=self.config.name)
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            if self.client is None:
                return False
            
            await self.client.admin.command('ping')
            self.is_healthy = True
            self.last_health_check = datetime.now()
            return True
            
        except Exception as e:
            self.is_healthy = False
            logger.warning(
                "MongoDB实例健康检查失败",
                instance_name=self.config.name,
                error=str(e)
            )
            return False
    
    def get_database(self, db_name: str) -> Optional[AsyncIOMotorDatabase]:
        """获取数据库连接（支持连接复用）"""
        if not self.is_healthy or self.client is None:
            return None
        
        # 连接复用：直接返回已存在的客户端数据库引用
        database = self.client[db_name]
        
        # 记录数据库访问（可用于后续优化）
        if not hasattr(self, '_db_access_count'):
            self._db_access_count = {}
        self._db_access_count[db_name] = self._db_access_count.get(db_name, 0) + 1
        
        return database
    
    def needs_health_check(self, interval_minutes: int = 5) -> bool:
        """检查是否需要健康检查"""
        if self.last_health_check is None:
            return True
        return datetime.now() - self.last_health_check > timedelta(minutes=interval_minutes)
    
    def get_connection_stats(self) -> dict:
        """获取连接统计信息"""
        stats = self._connection_stats.copy()
        stats['db_access_count'] = getattr(self, '_db_access_count', {})
        stats['pool_config'] = self._get_optimal_pool_config()
        return stats


class ConnectionManager:
    """多实例MongoDB连接管理器"""
    
    def __init__(self, config: QueryNestConfig):
        self.config = config
        self.connections: Dict[str, InstanceConnection] = {}
        # 移除单独的元数据客户端，每个实例都管理自己的元数据库
        self._health_check_task: Optional[asyncio.Task] = None
        self._shutdown = False
    
    async def initialize(self) -> bool:
        """初始化所有连接"""
        logger.info("开始初始化MongoDB连接管理器")
        
        # 初始化业务实例连接（不立即初始化元数据库）
        success_count = 0
        for instance_key, instance_config in self.config.mongo_instances.items():
            if instance_config.status != "active":
                continue
                
            connection = InstanceConnection(instance_config)
            if await connection.connect():
                self.connections[instance_key] = connection  # 使用配置键名而非name字段
                success_count += 1
            else:
                logger.warning(
                    "实例连接失败，将跳过",
                    instance_name=instance_config.name,
                    instance_key=instance_key
                )
        
        if success_count == 0:
            logger.error("没有成功连接的MongoDB实例")
            return False
        
        # 启动健康检查任务
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        
        logger.info(
            "MongoDB连接管理器初始化完成",
            total_instances=len([i for i in self.config.mongo_instances.values() if i.status == "active"]),
            connected_instances=success_count
        )
        return True
    
    async def init_instance_metadata_on_demand(self, instance_name: str) -> bool:
        """按需初始化实例元数据（基于文件存储）"""
        connection = self.get_instance_connection(instance_name)
        if connection is None:
            logger.error("实例连接不存在", instance=instance_name)
            return False
        
        try:
            # 基于文件存储，元数据初始化由FileMetadataManager处理
            # 这里只需要确认实例连接正常即可
            logger.info("实例元数据初始化成功（使用文件存储）", instance=instance_name)
            return True
            
        except Exception as e:
            logger.error("实例元数据初始化失败", 
                        instance=instance_name, error=str(e))
            return False
    
    async def shutdown(self):
        """关闭所有连接"""
        logger.info("开始关闭MongoDB连接管理器")
        self._shutdown = True
        
        # 停止健康检查任务
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        # 关闭所有实例连接
        for connection in self.connections.values():
            await connection.disconnect()
        self.connections.clear()
        
        # 元数据库连接已随各实例连接一起关闭
        
        logger.info("MongoDB连接管理器已关闭")
    
    def get_instance_connection(self, instance_name: str) -> Optional[InstanceConnection]:
        """获取实例连接"""
        return self.connections.get(instance_name)
    
    def get_client(self, instance_name: str) -> Optional[AsyncIOMotorClient]:
        """获取MongoDB客户端
        
        此方法作为兼容层，直接返回实例连接的client属性。
        用于与期望直接获取client的代码兼容。
        """
        connection = self.get_instance_connection(instance_name)
        if connection:
            return connection.client
        return None
    
    def get_instance_database(self, instance_name: str, db_name: str) -> Optional[AsyncIOMotorDatabase]:
        """获取实例数据库连接"""
        connection = self.get_instance_connection(instance_name)
        if connection:
            return connection.get_database(db_name)
        return None
    
    def get_metadata_database(self, instance_name: str) -> Optional[str]:
        """获取指定实例的元数据存储路径（文件存储）"""
        # 返回实例名称，用于文件存储路径生成
        connection = self.get_instance_connection(instance_name)
        if connection is None:
            return None
        return instance_name
    
    def get_available_instances(self) -> List[str]:
        """获取可用实例列表"""
        return [
            name for name, connection in self.connections.items()
            if connection.is_healthy
        ]
    
    def get_instance_info(self, instance_name: str) -> Optional[Dict[str, Any]]:
        """获取实例信息"""
        connection = self.get_instance_connection(instance_name)
        if connection:
            return {
                "name": connection.config.name,
                "alias": connection.config.alias,
                "environment": connection.config.environment,
                "description": connection.config.description,
                "is_healthy": connection.is_healthy,
                "last_health_check": connection.last_health_check
            }
        return None
    
    def get_all_instances_info(self) -> List[Dict[str, Any]]:
        """获取所有实例信息"""
        instances_info = []
        for instance_name in self.connections.keys():
            info = self.get_instance_info(instance_name)
            if info:
                instances_info.append(info)
        return instances_info
    
    async def get_all_instances(self) -> Dict[str, Any]:
        """获取所有实例配置（用于MCP工具）"""
        instances = {}
        for instance_name, connection in self.connections.items():
            instances[instance_name] = connection.config
        return instances
    
    def has_instance(self, instance_name: str) -> bool:
        """检查实例是否存在"""
        return instance_name in self.connections
    
    async def check_instance_health(self, instance_name: str) -> Dict[str, Any]:
        """检查实例健康状态"""
        connection = self.get_instance_connection(instance_name)
        if not connection:
            return {
                "healthy": False,
                "error": "实例连接不存在",
                "last_check": None
            }
        
        is_healthy = await connection.health_check()
        return {
            "healthy": is_healthy,
            "last_check": connection.last_health_check,
            "error": None if is_healthy else "连接检查失败"
        }
    
    async def _health_check_loop(self):
        """健康检查循环"""
        while not self._shutdown:
            try:
                # 检查所有实例连接
                for connection in self.connections.values():
                    if connection.needs_health_check():
                        await connection.health_check()
                
                # 元数据库连接已随各实例连接一起管理，无需单独检查
                
                # 等待下次检查
                health_check_interval = self.config.connection_pool.health_check_interval
                await asyncio.sleep(health_check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("健康检查循环异常", error=str(e))
                health_check_interval = self.config.connection_pool.health_check_interval
                await asyncio.sleep(health_check_interval)
    
    async def validate_query_permissions(self, instance_name: str, operation: str) -> bool:
        """验证查询权限"""
        # 检查操作是否在允许列表中
        if operation not in self.config.security.allowed_operations:
            logger.warning(
                "不允许的操作类型",
                instance_name=instance_name,
                operation=operation
            )
            return False
        
        # 检查实例是否可用
        connection = self.get_instance_connection(instance_name)
        if not connection or not connection.is_healthy:
            logger.warning(
                "实例不可用",
                instance_name=instance_name
            )
            return False
        
        return True