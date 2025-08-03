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
    
    async def connect(self) -> bool:
        """连接到MongoDB实例"""
        async with self._lock:
            try:
                if self.client is None:
                    self.client = AsyncIOMotorClient(
                        self.config.connection_string,
                        serverSelectionTimeoutMS=5000,
                        connectTimeoutMS=5000,
                        maxPoolSize=10,
                        minPoolSize=1
                    )
                
                # 测试连接
                await self.client.admin.command('ping')
                self.is_healthy = True
                self.last_health_check = datetime.now()
                
                logger.info(
                    "MongoDB实例连接成功",
                    instance_name=self.config.name,
                    environment=self.config.environment
                )
                return True
                
            except (ConnectionFailure, ServerSelectionTimeoutError) as e:
                self.is_healthy = False
                logger.error(
                    "MongoDB实例连接失败",
                    instance_name=self.config.name,
                    error=str(e)
                )
                return False
            except Exception as e:
                self.is_healthy = False
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
        """获取数据库连接"""
        if not self.is_healthy or self.client is None:
            return None
        return self.client[db_name]
    
    def needs_health_check(self, interval_minutes: int = 5) -> bool:
        """检查是否需要健康检查"""
        if self.last_health_check is None:
            return True
        return datetime.now() - self.last_health_check > timedelta(minutes=interval_minutes)


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
        for instance_config in self.config.get_active_instances():
            connection = InstanceConnection(instance_config)
            if await connection.connect():
                self.connections[instance_config.name] = connection
                success_count += 1
            else:
                logger.warning(
                    "实例连接失败，将跳过",
                    instance_name=instance_config.name
                )
        
        if success_count == 0:
            logger.error("没有成功连接的MongoDB实例")
            return False
        
        # 启动健康检查任务
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        
        logger.info(
            "MongoDB连接管理器初始化完成",
            total_instances=len(self.config.get_active_instances()),
            connected_instances=success_count
        )
        return True
    
    async def init_instance_metadata_on_demand(self, instance_name: str) -> bool:
        """按需为指定实例初始化元数据库（用户确认实例后调用）"""
        connection = self.get_instance_connection(instance_name)
        if connection is None:
            logger.error("实例连接不存在", instance=instance_name)
            return False
        
        try:
            metadata_db = connection.get_database(self.config.metadata.database)
            if metadata_db is None:
                return False
            
            # 测试元数据库访问
            await metadata_db.command('ping')
            
            # 创建基础集合（如果不存在）
            collections = ['instances', 'databases', 'collections', 'fields', 'query_history']
            existing_collections = await metadata_db.list_collection_names()
            for collection_name in collections:
                if collection_name not in existing_collections:
                    await metadata_db.create_collection(collection_name)
            
            logger.info("实例元数据库按需初始化成功", instance=instance_name)
            return True
            
        except Exception as e:
            logger.error("实例元数据库按需初始化失败", 
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
    
    def get_instance_database(self, instance_name: str, db_name: str) -> Optional[AsyncIOMotorDatabase]:
        """获取实例数据库连接"""
        connection = self.get_instance_connection(instance_name)
        if connection:
            return connection.get_database(db_name)
        return None
    
    def get_metadata_database(self, instance_name: str) -> Optional[AsyncIOMotorDatabase]:
        """获取指定实例的元数据库连接"""
        connection = self.get_instance_connection(instance_name)
        if connection is None:
            return None
        return connection.get_database(self.config.metadata.database)
    
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
                await asyncio.sleep(60)  # 每分钟检查一次
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("健康检查循环异常", error=str(e))
                await asyncio.sleep(60)
    
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