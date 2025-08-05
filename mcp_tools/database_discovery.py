# -*- coding: utf-8 -*-
"""数据库发现工具"""

from typing import Dict, List, Any, Optional
import structlog
from mcp.types import Tool, TextContent

from database.connection_manager import ConnectionManager
from database.metadata_manager import MetadataManager
from utils.parameter_validator import (
    ParameterValidator, MCPParameterHelper, ValidationResult,
    is_non_empty_string, is_boolean, is_valid_instance_id, validate_instance_exists
)
from utils.tool_context import get_context_manager, ToolExecutionContext


logger = structlog.get_logger(__name__)


class DatabaseDiscoveryTool:
    """数据库发现工具"""
    
    def __init__(self, connection_manager: ConnectionManager, metadata_manager: MetadataManager):
        self.connection_manager = connection_manager
        self.metadata_manager = metadata_manager
        self.context_manager = get_context_manager()
        self.validator = self._setup_validator()
    
    def get_tool_definition(self) -> Tool:
        """获取工具定义"""
        return Tool(
            name="discover_databases",
            description="发现指定MongoDB实例中的所有数据库",
            inputSchema={
                "type": "object",
                "properties": {
                    "instance_id": {
                        "type": "string",
                        "description": "MongoDB实例ID"
                    },
                    "include_collections": {
                        "type": "boolean",
                        "description": "是否包含每个数据库的集合列表",
                        "default": False
                    },
                    "include_stats": {
                        "type": "boolean",
                        "description": "是否包含数据库统计信息",
                        "default": False
                    },
                    "filter_system": {
                        "type": "boolean",
                        "description": "是否过滤系统数据库",
                        "default": True
                    }
                },
                "required": ["instance_id"]
            }
        )
    
    def _setup_validator(self) -> ParameterValidator:
        """设置参数验证器"""
        validator = ParameterValidator()
        
        async def get_instance_options():
            """获取可用实例选项"""
            try:
                instances = await self.connection_manager.get_all_instances()
                options = []
                for instance_id, instance_config in instances.items():
                    options.append({
                        'value': instance_id,
                        'display_name': instance_id,
                        'description': f"{instance_config.environment} 环境 - {instance_config.description or '无描述'}",
                        'extra_info': f"状态: {instance_config.status}"
                    })
                return options
            except Exception as e:
                logger.warning("获取实例选项失败", error=str(e))
                return []
        
        validator.add_required_parameter(
            name="instance_id",
            type_check=lambda x: is_non_empty_string(x) and is_valid_instance_id(x),
            validator=lambda x, ctx: validate_instance_exists(x, ctx.connection_manager),
            options_provider=get_instance_options,
            description="要探索的MongoDB实例名称（注意：参数名为instance_id但实际使用实例名称）",
            user_friendly_name="MongoDB实例"
        )
        
        validator.add_optional_parameter(
            name="include_collections",
            type_check=is_boolean,
            description="是否包含每个数据库的集合列表",
            user_friendly_name="包含集合列表"
        )
        
        validator.add_optional_parameter(
            name="include_stats",
            type_check=is_boolean,
            description="是否包含数据库统计信息",
            user_friendly_name="包含统计信息"
        )
        
        validator.add_optional_parameter(
            name="filter_system",
            type_check=is_boolean,
            description="是否过滤系统数据库（admin, local, config）",
            user_friendly_name="过滤系统数据库"
        )
        
        return validator

    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """执行数据库发现"""
        # 参数验证和智能补全
        context = self.context_manager.get_or_create_context()
        context.connection_manager = self.connection_manager
        
        # 尝试从上下文推断缺失参数
        if not arguments.get("instance_id"):
            inferred_params = context.infer_missing_parameters()
            if inferred_params.get("instance_id"):
                arguments["instance_id"] = inferred_params["instance_id"]
                logger.info("从上下文推断实例ID", instance_id=arguments["instance_id"])
        
        validation_result, errors = await self.validator.validate_parameters(arguments, context)
        
        if validation_result != ValidationResult.VALID:
            return MCPParameterHelper.create_error_response(errors)
        
        # 记录工具调用到上下文并更新上下文
        context.add_to_chain("discover_databases", arguments)
        self.context_manager.update_context(instance_id=arguments["instance_id"])
        
        instance_id = arguments["instance_id"]
        include_collections = arguments.get("include_collections", False)
        include_stats = arguments.get("include_stats", False)
        filter_system = arguments.get("filter_system", True)
        
        logger.info(
            "开始发现数据库",
            instance_id=instance_id,
            include_collections=include_collections,
            include_stats=include_stats
        )
        
        try:
            # 验证实例是否存在
            if not self.connection_manager.has_instance(instance_id):
                return [TextContent(
                    type="text",
                    text=f"实例 '{instance_id}' 不存在。请使用 discover_instances 工具查看可用实例。"
                )]
            
            # 检查实例健康状态
            health_status = await self.connection_manager.check_instance_health(instance_id)
            if not health_status["healthy"]:
                return [TextContent(
                    type="text",
                    text=f"实例 '{instance_id}' 不健康: {health_status.get('error', 'Unknown error')}"
                )]
            
            # 获取数据库列表
            databases = await self._get_databases(instance_id, filter_system)
            
            if not databases:
                return [TextContent(
                    type="text",
                    text=f"实例 '{instance_id}' 中未发现任何数据库。"
                )]
            
            result_text = f"## 实例 '{instance_id}' 中的数据库\n\n"
            
            for db_info in databases:
                db_name = db_info["database_name"]
                result_text += f"### 数据库: {db_name}\n"
                
                # 添加数据库描述（如果有）
                if db_info.get("description"):
                    result_text += f"- **描述**: {db_info['description']}\n"
                
                if include_stats:
                    # 获取数据库统计信息
                    stats = await self._get_database_stats(instance_id, db_name)
                    if stats:
                        result_text += f"- **集合数量**: {stats.get('collection_count', 0)}\n"
                        result_text += f"- **文档数量**: {stats.get('document_count', 0)}\n"
                        result_text += f"- **数据大小**: {self._format_size(stats.get('data_size', 0))}\n"
                        result_text += f"- **索引大小**: {self._format_size(stats.get('index_size', 0))}\n"
                
                if include_collections:
                    # 获取集合列表
                    collections = await self._get_collections(instance_id, db_name)
                    if collections:
                        result_text += f"- **集合列表**:\n"
                        for coll in collections[:10]:  # 限制显示前10个集合
                            coll_name = coll["collection_name"]
                            doc_count = coll.get("document_count", "未知")
                            result_text += f"  - {coll_name} ({doc_count} 文档)\n"
                        
                        if len(collections) > 10:
                            result_text += f"  - ... 还有 {len(collections) - 10} 个集合\n"
                    else:
                        result_text += f"- **集合列表**: 无集合\n"
                
                # 添加业务领域建议（如果有）
                business_domains = db_info.get("business_domains", [])
                if business_domains:
                    result_text += f"- **业务领域**: {', '.join(business_domains)}\n"
                
                result_text += "\n"
            
            # 添加使用提示
            result_text += "## 使用提示\n\n"
            result_text += "- 使用 `analyze_collection` 工具来分析特定集合的结构\n"
            result_text += "- 使用 `generate_query` 工具来生成查询语句\n"
            result_text += "- 使用 `manage_semantics` 工具来管理字段的业务含义\n"
            
            logger.info("数据库发现完成", instance_id=instance_id, database_count=len(databases))
            
            return [TextContent(type="text", text=result_text)]
            
        except Exception as e:
            error_msg = f"发现数据库时发生错误: {str(e)}"
            logger.error("数据库发现失败", instance_id=instance_id, error=str(e))
            return [TextContent(type="text", text=error_msg)]
    
    async def _get_databases(self, instance_id: str, filter_system: bool = True) -> List[Dict[str, Any]]:
        """获取数据库列表"""
        try:
            # 首先尝试从元数据管理器获取
            # 注意：MetadataManager需要target_instance_name和instance_id两个参数
            # 这里我们先尝试直接从MongoDB获取，因为元数据管理器的设计比较复杂
            databases = []
            
            if not databases:
                # 如果元数据中没有，直接从MongoDB获取
                instance_connection = self.connection_manager.get_instance_connection(instance_id)
                if instance_connection is not None and instance_connection.client is not None:
                    db_names = await instance_connection.client.list_database_names()
                    
                    if filter_system:
                        # 过滤系统数据库
                        system_dbs = {'admin', 'local', 'config'}
                        db_names = [name for name in db_names if name not in system_dbs]
                    
                    databases = [{"database_name": name} for name in db_names]
            
            return databases
            
        except Exception as e:
            logger.error("获取数据库列表失败", instance_id=instance_id, error=str(e))
            return []
    
    async def _get_collections(self, instance_id: str, database_name: str) -> List[Dict[str, Any]]:
        """获取集合列表"""
        try:
            # 直接从MongoDB获取集合信息
            instance_connection = self.connection_manager.get_instance_connection(instance_id)
            if instance_connection is None or instance_connection.client is None:
                return []
            
            db = instance_connection.client[database_name]
            collection_names = await db.list_collection_names()
            
            collections = []
            for coll_name in collection_names:
                # 获取集合的文档数量
                try:
                    doc_count = await db[coll_name].count_documents({})
                    collections.append({
                        "collection_name": coll_name,
                        "document_count": doc_count
                    })
                except Exception as e:
                    logger.warning("获取集合文档数量失败", collection=coll_name, error=str(e))
                    collections.append({
                        "collection_name": coll_name,
                        "document_count": "未知"
                    })
            
            return collections
            
        except Exception as e:
            logger.error(
                "获取集合列表失败",
                instance_id=instance_id,
                database=database_name,
                error=str(e)
            )
            return []
    
    async def _get_database_stats(self, instance_id: str, database_name: str) -> Optional[Dict[str, Any]]:
        """获取数据库统计信息"""
        try:
            instance_connection = self.connection_manager.get_instance_connection(instance_id)
            if not instance_connection or not instance_connection.client:
                return None
            
            db = instance_connection.client[database_name]
            stats = await db.command("dbStats")
            
            return {
                "collection_count": stats.get("collections", 0),
                "document_count": stats.get("objects", 0),
                "data_size": stats.get("dataSize", 0),
                "index_size": stats.get("indexSize", 0),
                "storage_size": stats.get("storageSize", 0)
            }
            
        except Exception as e:
            logger.warning(
                "获取数据库统计信息失败",
                instance_id=instance_id,
                database=database_name,
                error=str(e)
            )
            return None
    
    def _format_size(self, size_bytes: int) -> str:
        """格式化字节大小"""
        if size_bytes == 0:
            return "0 B"
        
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        unit_index = 0
        size = float(size_bytes)
        
        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1
        
        return f"{size:.1f} {units[unit_index]}"
    
    async def search_databases(self, instance_id: str, search_term: str) -> List[Dict[str, Any]]:
        """搜索数据库"""
        try:
            databases = await self._get_databases(instance_id, filter_system=True)
            
            # 简单的名称匹配搜索
            search_term_lower = search_term.lower()
            matching_databases = []
            
            for db in databases:
                db_name = db["database_name"].lower()
                description = db.get("description", "").lower()
                business_domains = [domain.lower() for domain in db.get("business_domains", [])]
                
                # 检查名称、描述或业务领域是否匹配
                if (search_term_lower in db_name or 
                    search_term_lower in description or 
                    any(search_term_lower in domain for domain in business_domains)):
                    matching_databases.append(db)
            
            return matching_databases
            
        except Exception as e:
            logger.error(
                "搜索数据库失败",
                instance_id=instance_id,
                search_term=search_term,
                error=str(e)
            )
            return []
    
    async def get_database_recommendations(self, instance_id: str, query_context: str) -> List[Dict[str, Any]]:
        """根据查询上下文推荐数据库"""
        try:
            databases = await self._get_databases(instance_id, filter_system=True)
            recommendations = []
            
            query_context_lower = query_context.lower()
            
            for db in databases:
                relevance_score = 0.0
                
                # 基于数据库名称计算相关性
                db_name = db["database_name"].lower()
                if any(word in db_name for word in query_context_lower.split()):
                    relevance_score += 0.5
                
                # 基于业务领域计算相关性
                business_domains = db.get("business_domains", [])
                for domain in business_domains:
                    if any(word in domain.lower() for word in query_context_lower.split()):
                        relevance_score += 0.3
                
                # 基于描述计算相关性
                description = db.get("description", "")
                if description and any(word in description.lower() for word in query_context_lower.split()):
                    relevance_score += 0.2
                
                if relevance_score > 0:
                    recommendations.append({
                        **db,
                        "relevance_score": relevance_score
                    })
            
            # 按相关性排序
            recommendations.sort(key=lambda x: x["relevance_score"], reverse=True)
            
            return recommendations[:5]  # 返回前5个推荐
            
        except Exception as e:
            logger.error(
                "获取数据库推荐失败",
                instance_id=instance_id,
                query_context=query_context,
                error=str(e)
            )
            return []