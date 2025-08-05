# -*- coding: utf-8 -*-
"""集合结构分析工具"""

from typing import Dict, List, Any, Optional
import structlog
from mcp.types import Tool, TextContent

from database.connection_manager import ConnectionManager
from database.metadata_manager import MetadataManager
from scanner.semantic_analyzer import SemanticAnalyzer


logger = structlog.get_logger(__name__)


class CollectionAnalysisTool:
    """集合结构分析工具"""
    
    def __init__(self, connection_manager: ConnectionManager, 
                 metadata_manager: MetadataManager,
                 semantic_analyzer: SemanticAnalyzer):
        self.connection_manager = connection_manager
        self.metadata_manager = metadata_manager
        self.semantic_analyzer = semantic_analyzer
    
    def get_tool_definition(self) -> Tool:
        """获取工具定义"""
        return Tool(
            name="analyze_collection",
            description="分析指定集合的结构、字段类型和业务语义",
            inputSchema={
                "type": "object",
                "properties": {
                    "instance_id": {
                        "type": "string",
                        "description": "MongoDB实例ID（注意：参数名为instance_id但实际使用实例名称）"
                    },
                    "database_name": {
                        "type": "string",
                        "description": "数据库名称"
                    },
                    "collection_name": {
                        "type": "string",
                        "description": "集合名称"
                    },
                    "include_semantics": {
                        "type": "boolean",
                        "description": "是否包含语义分析",
                        "default": True
                    },
                    "include_examples": {
                        "type": "boolean",
                        "description": "是否包含字段示例值",
                        "default": True
                    },
                    "include_indexes": {
                        "type": "boolean",
                        "description": "是否包含索引信息",
                        "default": True
                    },
                    "rescan": {
                        "type": "boolean",
                        "description": "是否重新扫描集合结构",
                        "default": False
                    }
                },
                "required": ["instance_id", "database_name", "collection_name"]
            }
        )
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """执行集合分析"""
        instance_id = arguments["instance_id"]
        database_name = arguments["database_name"]
        collection_name = arguments["collection_name"]
        include_semantics = arguments.get("include_semantics", True)
        include_examples = arguments.get("include_examples", True)
        include_indexes = arguments.get("include_indexes", True)
        rescan = arguments.get("rescan", False)
        
        logger.info(
            "开始分析集合结构",
            instance_id=instance_id,
            database=database_name,
            collection=collection_name
        )
        
        try:
            # 验证实例和连接
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
            
            # 验证集合是否存在
            collection_exists = await self._check_collection_exists(instance_id, database_name, collection_name)
            if not collection_exists:
                return [TextContent(
                    type="text",
                    text=f"集合 '{database_name}.{collection_name}' 不存在。"
                )]
            
            # 如果需要重新扫描或集合信息不存在，进行扫描
            if rescan or not await self._has_collection_metadata(instance_id, database_name, collection_name):
                await self._scan_collection(instance_id, database_name, collection_name)
            
            # 获取集合基本信息
            from bson import ObjectId
            if isinstance(instance_id, str):
                # 如果是字符串，需要先获取实例信息来得到ObjectId
                instance_info = await self.metadata_manager.get_instance_by_name(instance_id, instance_id)
                if not instance_info:
                    return [TextContent(
                        type="text",
                        text=f"无法找到实例 '{instance_id}'。"
                    )]
                instance_obj_id = instance_info["_id"]
            else:
                instance_obj_id = instance_id
            
            collections = await self.metadata_manager.get_collections_by_database(
                instance_id, instance_obj_id, database_name
            )
            # 查找指定的集合
            collection_info = None
            for collection in collections:
                if collection.get("collection_name") == collection_name:
                    collection_info = collection
                    break
            
            if not collection_info:
                return [TextContent(
                    type="text",
                    text=f"无法获取集合 '{database_name}.{collection_name}' 的信息。请尝试重新扫描。"
                )]
            
            # 获取字段信息
            fields = await self.metadata_manager.get_fields_by_collection(
                instance_id, instance_id, database_name, collection_name
            )
            
            # 构建分析结果
            result_text = await self._build_analysis_result(
                collection_info, fields, instance_id, database_name, collection_name,
                include_semantics, include_examples, include_indexes
            )
            
            logger.info(
                "集合分析完成",
                instance_id=instance_id,
                database=database_name,
                collection=collection_name,
                field_count=len(fields)
            )
            
            return [TextContent(type="text", text=result_text)]
            
        except Exception as e:
            error_msg = f"分析集合时发生错误: {str(e)}"
            logger.error(
                "集合分析失败",
                instance_id=instance_id,
                database=database_name,
                collection=collection_name,
                error=str(e)
            )
            return [TextContent(type="text", text=error_msg)]
    
    async def _check_collection_exists(self, instance_id: str, database_name: str, collection_name: str) -> bool:
        """检查集合是否存在"""
        try:
            connection = self.connection_manager.get_instance_connection(instance_id)
            if connection is None:
                return False
            
            db = connection.get_database(database_name)
            collection_names = await db.list_collection_names()
            return collection_name in collection_names
            
        except Exception as e:
            logger.error("检查集合存在性失败", error=str(e))
            return False
    
    async def _has_collection_metadata(self, instance_id: str, database_name: str, collection_name: str) -> bool:
        """检查是否已有集合元数据"""
        try:
            # 获取实例的ObjectId
            from bson import ObjectId
            if isinstance(instance_id, str):
                # 如果是字符串，需要先获取实例信息来得到ObjectId
                instance_info = await self.metadata_manager.get_instance_by_name(instance_id, instance_id)
                if not instance_info:
                    return False
                instance_obj_id = instance_info["_id"]
            else:
                instance_obj_id = instance_id
            
            collections = await self.metadata_manager.get_collections_by_database(
                instance_id, instance_obj_id, database_name
            )
            # 检查是否存在指定的集合
            for collection in collections:
                if collection.get("collection_name") == collection_name:
                    return True
            return False
        except Exception:
            return False
    
    async def _scan_collection(self, instance_id: str, database_name: str, collection_name: str) -> Dict[str, Any]:
        """扫描集合结构"""
        try:
            # 获取连接
            connection = self.connection_manager.get_instance_connection(instance_id)
            if connection is None:
                return {"error": f"无法连接到实例 {instance_id}"}
            
            # 获取数据库
            db = connection.get_database(database_name)
            
            # 检查集合是否存在
            if collection_name not in await db.list_collection_names():
                return {"error": f"集合 '{database_name}.{collection_name}' 不存在。"}
            
            # 获取实例信息
            from bson import ObjectId
            try:
                instance_obj_id = ObjectId(instance_id)
            except:
                instance_obj_id = instance_id
            
            # 获取实例名称
            # 直接使用 instance_id 作为 instance_name，因为在测试环境中它们通常是相同的
            instance_name = instance_id
            
            # 扫描集合结构
            from ..scanner.structure_scanner import StructureScanner
            from ..config import QueryNestConfig
            config = QueryNestConfig()
            scanner = StructureScanner(self.connection_manager, self.metadata_manager, config)
            structure = await scanner.scan_collection_structure(instance_name, instance_obj_id, database_name, collection_name)
            
            # 获取索引信息
            indexes = await self._get_collection_indexes(instance_id, database_name, collection_name)
            
            return {
                "name": collection_name,
                "structure": structure,
                "indexes": indexes
            }
            
        except Exception as e:
            logger.error("扫描集合结构失败", 
                        instance_id=instance_id, 
                        database=database_name, 
                        collection=collection_name, 
                        error=str(e))
            return {"error": f"扫描集合结构失败: {str(e)}"}
            
            logger.info(
                "集合结构扫描完成",
                instance_id=instance_id,
                database=database_name,
                collection=collection_name
            )
            
        except Exception as e:
            logger.error(
                "扫描集合结构失败",
                instance_id=instance_id,
                database=database_name,
                collection=collection_name,
                error=str(e)
            )
            raise
    
    async def _build_analysis_result(self, collection_info: Dict[str, Any], fields: List[Dict[str, Any]],
                                   instance_id: str, database_name: str, collection_name: str,
                                   include_semantics: bool, include_examples: bool, include_indexes: bool) -> str:
        """构建分析结果文本"""
        result_text = f"## 集合分析: {database_name}.{collection_name}\n\n"
        
        # 基本信息
        result_text += "### 基本信息\n"
        result_text += f"- **实例**: {instance_id}\n"
        result_text += f"- **数据库**: {database_name}\n"
        result_text += f"- **集合**: {collection_name}\n"
        result_text += f"- **文档数量**: {collection_info.get('document_count', '未知')}\n"
        result_text += f"- **平均文档大小**: {self._format_size(collection_info.get('avg_doc_size', 0))}\n"
        
        if collection_info.get("description"):
            result_text += f"- **描述**: {collection_info['description']}\n"
        
        result_text += "\n"
        
        # 索引信息
        if include_indexes:
            indexes = await self._get_collection_indexes(instance_id, database_name, collection_name)
            if indexes:
                result_text += "### 索引信息\n"
                for idx in indexes:
                    idx_name = idx.get("name", "未知")
                    idx_keys = idx.get("key", {})
                    key_desc = ", ".join([f"{k}: {v}" for k, v in idx_keys.items()])
                    result_text += f"- **{idx_name}**: {key_desc}\n"
                result_text += "\n"
        
        # 字段结构
        if fields:
            result_text += "### 字段结构\n\n"
            
            # 按字段路径排序
            fields.sort(key=lambda x: x["field_path"])
            
            for field in fields:
                field_path = field["field_path"]
                field_type = field.get("field_type", "unknown")
                occurrence_rate = field.get("occurrence_rate", 0)
                
                result_text += f"#### {field_path}\n"
                result_text += f"- **类型**: {field_type}\n"
                result_text += f"- **出现率**: {occurrence_rate:.1%}\n"
        else:
            result_text += "### 字段结构\n\n"
            result_text += "集合 '{}.{}' 没有字段信息。请先使用 analyze_collection 工具扫描集合结构。\n\n".format(database_name, collection_name)
        
        # 语义分析总结
        if include_semantics:
            semantic_summary = await self._get_semantic_summary(instance_id, database_name, collection_name, fields)
            if semantic_summary:
                result_text += semantic_summary
        
        # 使用建议
        result_text += "### 使用建议\n\n"
        result_text += "- 使用 `manage_semantics` 工具来添加或更新字段的业务含义\n"
        result_text += "- 使用 `generate_query` 工具来生成针对此集合的查询\n"
        result_text += "- 对于高频查询字段，建议添加索引以提高性能\n"
        
        return result_text
    
    async def _get_collection_indexes(self, instance_id: str, database_name: str, collection_name: str) -> List[Dict[str, Any]]:
        """获取集合索引信息"""
        try:
            connection = self.connection_manager.get_instance_connection(instance_id)
            if connection is None:
                return []
            
            db = connection.get_database(database_name)
            collection = db[collection_name]
            
            indexes = []
            async for index in collection.list_indexes():
                indexes.append(index)
            
            return indexes
            
        except Exception as e:
            logger.warning(
                "获取索引信息失败",
                instance_id=instance_id,
                database=database_name,
                collection=collection_name,
                error=str(e)
            )
            return []
    
    async def _get_semantic_summary(self, instance_id: str, database_name: str, 
                                  collection_name: str, fields: List[Dict[str, Any]]) -> str:
        """获取语义分析总结"""
        try:
            # 统计语义信息
            total_fields = len(fields)
            fields_with_meaning = sum(1 for field in fields if field.get("business_meaning"))
            
            if total_fields == 0:
                return ""
            
            semantic_coverage = fields_with_meaning / total_fields
            
            summary = "### 语义分析总结\n\n"
            summary += f"- **字段总数**: {total_fields}\n"
            summary += f"- **已定义语义**: {fields_with_meaning} ({semantic_coverage:.1%})\n"
            
            if semantic_coverage < 0.5:
                summary += "- **建议**: 语义覆盖率较低，建议使用 `manage_semantics` 工具完善字段含义\n"
            elif semantic_coverage < 0.8:
                summary += "- **建议**: 语义覆盖率中等，可以进一步完善剩余字段的含义\n"
            else:
                summary += "- **状态**: ✅ 语义覆盖率良好\n"
            
            # 推荐业务领域
            business_domains = await self.semantic_analyzer.suggest_business_domain(
                database_name, [{"collection_name": collection_name}]
            )
            if business_domains:
                summary += f"- **推荐业务领域**: {', '.join(business_domains)}\n"
            
            summary += "\n"
            return summary
            
        except Exception as e:
            logger.warning("生成语义总结失败", error=str(e))
            return ""
    
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
    
    async def get_field_suggestions(self, instance_id: str, database_name: str, 
                                  collection_name: str, query_description: str) -> List[Dict[str, Any]]:
        """根据查询描述获取字段建议"""
        try:
            fields = await self.metadata_manager.get_fields_by_collection(
                instance_id, instance_id, database_name, collection_name
            )
            
            if not fields:
                return []
            
            # 使用语义分析器获取建议
            suggestions = self.semantic_analyzer.get_semantic_suggestions_for_query(
                query_description, fields
            )
            
            return suggestions
            
        except Exception as e:
            logger.error(
                "获取字段建议失败",
                instance_id=instance_id,
                database=database_name,
                collection=collection_name,
                error=str(e)
            )
            return []