# -*- coding: utf-8 -*-
"""实例发现工具"""

from typing import Dict, List, Any, Optional
import structlog
from mcp.types import Tool, TextContent

from database.connection_manager import ConnectionManager
from database.metadata_manager import MetadataManager


logger = structlog.get_logger(__name__)


class InstanceDiscoveryTool:
    """实例发现工具"""
    
    def __init__(self, connection_manager: ConnectionManager, metadata_manager: MetadataManager):
        self.connection_manager = connection_manager
        self.metadata_manager = metadata_manager
    
    def get_tool_definition(self) -> Tool:
        """获取工具定义"""
        return Tool(
            name="discover_instances",
            description="发现和列出所有可用的MongoDB实例",
            inputSchema={
                "type": "object",
                "properties": {
                    "include_health": {
                        "type": "boolean",
                        "description": "是否包含实例健康状态信息",
                        "default": True
                    },
                    "include_stats": {
                        "type": "boolean",
                        "description": "是否包含实例统计信息",
                        "default": False
                    }
                },
                "required": []
            }
        )
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """执行实例发现"""
        include_health = arguments.get("include_health", True)
        include_stats = arguments.get("include_stats", False)
        
        logger.info("开始发现MongoDB实例", include_health=include_health, include_stats=include_stats)
        
        try:
            # 获取所有配置的实例
            instances = await self.connection_manager.get_all_instances()
            
            if not instances:
                return [TextContent(
                    type="text",
                    text="未发现任何MongoDB实例。请检查配置文件中的实例配置。"
                )]
            
            result_text = "## 发现的MongoDB实例\n\n"
            
            for instance_id, instance_config in instances.items():
                result_text += f"### 实例: {instance_id}\n"
                result_text += f"- **连接字符串**: {instance_config.connection_string}\n"
                result_text += f"- **环境**: {instance_config.environment}\n"
                result_text += f"- **状态**: {instance_config.status}\n"
                if instance_config.description:
                    result_text += f"- **描述**: {instance_config.description}\n"
                
                if include_health:
                    # 检查实例健康状态
                    health_status = await self.connection_manager.check_instance_health(instance_id)
                    if health_status["healthy"]:
                        result_text += f"- **状态**: ✅ 健康\n"
                        result_text += f"- **延迟**: {health_status.get('latency_ms', 'N/A')}ms\n"
                    else:
                        result_text += f"- **状态**: ❌ 不健康\n"
                        result_text += f"- **错误**: {health_status.get('error', 'Unknown')}\n"
                
                if include_stats:
                    # 获取实例统计信息
                    try:
                        stats = await self._get_instance_stats(instance_id)
                        if stats:
                            result_text += f"- **数据库数量**: {stats.get('database_count', 0)}\n"
                            result_text += f"- **集合数量**: {stats.get('collection_count', 0)}\n"
                            result_text += f"- **文档数量**: {stats.get('document_count', 0)}\n"
                    except Exception as e:
                        result_text += f"- **统计信息**: 获取失败 ({str(e)})\n"
                
                result_text += "\n"
            
            # 添加使用提示
            result_text += "## 使用提示\n\n"
            result_text += "- 使用 `discover_databases` 工具来探索特定实例的数据库\n"
            result_text += "- 使用 `analyze_collection` 工具来分析集合结构\n"
            result_text += "- 在查询时需要指定 `instance_id` 参数\n"
            
            logger.info("实例发现完成", instance_count=len(instances))
            
            return [TextContent(type="text", text=result_text)]
            
        except Exception as e:
            error_msg = f"发现实例时发生错误: {str(e)}"
            logger.error("实例发现失败", error=str(e))
            return [TextContent(type="text", text=error_msg)]
    
    async def _get_instance_stats(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """获取实例统计信息"""
        try:
            # 检查实例的元数据是否已初始化
            if instance_id not in self.metadata_manager._instance_collections:
                # 元数据未初始化，返回基本信息
                return {
                    "database_count": "未扫描",
                    "collection_count": "未扫描",
                    "document_count": "未扫描",
                    "metadata_initialized": False
                }
            
            # 从元数据管理器获取统计信息
            stats = await self.metadata_manager.get_statistics(instance_id)
            stats["metadata_initialized"] = True
            return stats
        except Exception as e:
            logger.warning("获取实例统计信息失败", instance_id=instance_id, error=str(e))
            return None
    
    async def get_instance_selection_prompt(self, available_instances: List[str]) -> str:
        """生成实例选择提示"""
        if len(available_instances) == 1:
            return f"将使用实例: {available_instances[0]}"
        
        prompt = "请选择要使用的MongoDB实例:\n\n"
        
        for i, instance_id in enumerate(available_instances, 1):
            try:
                # 获取实例基本信息
                instance_config = self.connection_manager.get_instance_config(instance_id)
                if instance_config:
                    prompt += f"{i}. **{instance_id}** - {instance_config.host}:{instance_config.port}\n"
                else:
                    prompt += f"{i}. **{instance_id}** - 配置信息不可用\n"
            except Exception:
                prompt += f"{i}. **{instance_id}** - 状态未知\n"
        
        prompt += "\n请回复实例名称或编号来选择实例。"
        return prompt
    
    def validate_instance_id(self, instance_id: str) -> bool:
        """验证实例ID是否有效"""
        try:
            return self.connection_manager.has_instance(instance_id)
        except Exception:
            return False
    
    async def get_instance_info(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """获取实例详细信息"""
        try:
            if not self.validate_instance_id(instance_id):
                return None
            
            instance_config = self.connection_manager.get_instance_config(instance_id)
            if not instance_config:
                return None
            
            # 获取健康状态
            health_status = await self.connection_manager.check_instance_health(instance_id)
            
            # 获取统计信息
            stats = await self._get_instance_stats(instance_id)
            
            return {
                "instance_id": instance_id,
                "host": instance_config.host,
                "port": instance_config.port,
                "database": instance_config.database,
                "has_auth": bool(instance_config.username),
                "health": health_status,
                "stats": stats or {}
            }
            
        except Exception as e:
            logger.error("获取实例信息失败", instance_id=instance_id, error=str(e))
            return None