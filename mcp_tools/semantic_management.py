# -*- coding: utf-8 -*-
"""语义管理工具"""

from typing import Dict, List, Any, Optional
import structlog
from mcp.types import Tool, TextContent

from database.connection_manager import ConnectionManager
from database.metadata_manager import MetadataManager
from scanner.semantic_analyzer import SemanticAnalyzer


logger = structlog.get_logger(__name__)


class SemanticManagementTool:
    """语义管理工具"""
    
    def __init__(self, connection_manager: ConnectionManager, 
                 metadata_manager: MetadataManager,
                 semantic_analyzer: SemanticAnalyzer):
        self.connection_manager = connection_manager
        self.metadata_manager = metadata_manager
        self.semantic_analyzer = semantic_analyzer
    
    def get_tool_definition(self) -> Tool:
        """获取工具定义"""
        return Tool(
            name="manage_semantics",
            description="管理字段的业务语义信息，包括查看、更新和批量分析",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["view", "update", "batch_analyze", "search", "suggest"],
                        "description": "操作类型：view(查看), update(更新), batch_analyze(批量分析), search(搜索), suggest(建议)"
                    },
                    "instance_id": {
                        "type": "string",
                        "description": "MongoDB实例ID"
                    },
                    "database_name": {
                        "type": "string",
                        "description": "数据库名称"
                    },
                    "collection_name": {
                        "type": "string",
                        "description": "集合名称"
                    },
                    "field_path": {
                        "type": "string",
                        "description": "字段路径（用于view和update操作）"
                    },
                    "business_meaning": {
                        "type": "string",
                        "description": "业务含义（用于update操作）"
                    },
                    "search_term": {
                        "type": "string",
                        "description": "搜索关键词（用于search操作）"
                    },
                    "query_description": {
                        "type": "string",
                        "description": "查询描述（用于suggest操作）"
                    }
                },
                "required": ["action", "instance_id"]
            }
        )
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """执行语义管理操作"""
        action = arguments["action"]
        instance_id = arguments["instance_id"]
        
        logger.info("执行语义管理操作", action=action, instance_id=instance_id)
        
        try:
            # 验证实例
            if not self.connection_manager.has_instance(instance_id):
                return [TextContent(
                    type="text",
                    text=f"实例 '{instance_id}' 不存在。请使用 discover_instances 工具查看可用实例。"
                )]
            
            # 根据操作类型执行相应功能
            if action == "view":
                return await self._handle_view(arguments)
            elif action == "update":
                return await self._handle_update(arguments)
            elif action == "batch_analyze":
                return await self._handle_batch_analyze(arguments)
            elif action == "search":
                return await self._handle_search(arguments)
            elif action == "suggest":
                return await self._handle_suggest(arguments)
            else:
                return [TextContent(
                    type="text",
                    text=f"不支持的操作类型: {action}"
                )]
                
        except Exception as e:
            error_msg = f"执行语义管理操作时发生错误: {str(e)}"
            logger.error("语义管理操作失败", action=action, instance_id=instance_id, error=str(e))
            return [TextContent(type="text", text=error_msg)]
    
    async def _handle_view(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """处理查看操作"""
        instance_id = arguments["instance_id"]
        database_name = arguments.get("database_name")
        collection_name = arguments.get("collection_name")
        field_path = arguments.get("field_path")
        
        if field_path and database_name and collection_name:
            # 查看特定字段的语义信息
            return await self._view_field_semantics(instance_id, database_name, collection_name, field_path)
        elif database_name and collection_name:
            # 查看集合的所有字段语义
            return await self._view_collection_semantics(instance_id, database_name, collection_name)
        elif database_name:
            # 查看数据库的语义覆盖情况
            return await self._view_database_semantics(instance_id, database_name)
        else:
            # 查看实例的语义覆盖情况
            return await self._view_instance_semantics(instance_id)
    
    async def _handle_update(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """处理更新操作"""
        instance_id = arguments["instance_id"]
        database_name = arguments.get("database_name")
        collection_name = arguments.get("collection_name")
        field_path = arguments.get("field_path")
        business_meaning = arguments.get("business_meaning")
        
        if not all([database_name, collection_name, field_path, business_meaning]):
            return [TextContent(
                type="text",
                text="更新操作需要提供 database_name, collection_name, field_path 和 business_meaning 参数。"
            )]
        
        try:
            # 更新字段语义 - 需要传入正确的参数
            # 由于新的双重存储策略，需要提供instance_id作为ObjectId
            from bson import ObjectId
            try:
                # 如果instance_id是字符串，需要转换或使用实例名称
                success = await self.metadata_manager.update_field_semantics(
                    instance_id, ObjectId(), database_name, collection_name, field_path, business_meaning
                )
            except:
                # 如果ObjectId转换失败，使用实例名称的方式调用新版本方法
                success = await self._update_field_semantics_by_instance_name(
                    instance_id, database_name, collection_name, field_path, business_meaning
                )
            
            if success:
                result_text = f"✅ 成功更新字段语义\n\n"
                result_text += f"- **实例**: {instance_id}\n"
                result_text += f"- **数据库**: {database_name}\n"
                result_text += f"- **集合**: {collection_name}\n"
                result_text += f"- **字段**: {field_path}\n"
                result_text += f"- **业务含义**: {business_meaning}\n"
                
                logger.info(
                    "字段语义更新成功",
                    instance_id=instance_id,
                    database=database_name,
                    collection=collection_name,
                    field_path=field_path
                )
            else:
                result_text = f"❌ 更新字段语义失败\n\n"
                result_text += f"请检查字段路径是否正确，或字段是否存在于集合中。"
            
            return [TextContent(type="text", text=result_text)]
            
        except Exception as e:
            logger.error("更新字段语义失败", error=str(e))
            return [TextContent(type="text", text=f"更新字段语义时发生错误: {str(e)}")]
    
    async def _handle_batch_analyze(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """处理批量分析操作"""
        instance_id = arguments["instance_id"]
        database_name = arguments.get("database_name")
        collection_name = arguments.get("collection_name")
        
        if not all([database_name, collection_name]):
            return [TextContent(
                type="text",
                text="批量分析操作需要提供 database_name 和 collection_name 参数。"
            )]
        
        try:
            # 执行批量语义分析
            analysis_result = await self.semantic_analyzer.batch_analyze_collection(
                instance_id, database_name, collection_name
            )
            
            result_text = f"## 批量语义分析结果: {database_name}.{collection_name}\n\n"
            
            if "error" in analysis_result:
                result_text += f"❌ 分析失败: {analysis_result['error']}\n"
                return [TextContent(type="text", text=result_text)]
            
            total_fields = analysis_result["total_fields"]
            analyzed_fields = analysis_result["analyzed_fields"]
            updated_fields = analysis_result["updated_fields"]
            
            result_text += f"### 分析统计\n\n"
            result_text += f"- **字段总数**: {total_fields}\n"
            result_text += f"- **分析字段数**: {analyzed_fields}\n"
            result_text += f"- **自动更新数**: {updated_fields}\n"
            
            if analyzed_fields > 0:
                auto_update_rate = updated_fields / analyzed_fields
                result_text += f"- **自动更新率**: {auto_update_rate:.1%}\n"
            
            result_text += "\n"
            
            # 显示分析结果详情
            analysis_results = analysis_result.get("analysis_results", {})
            if analysis_results:
                result_text += "### 分析详情\n\n"
                
                for field_path, analysis in analysis_results.items():
                    suggested_meaning = analysis["suggested_meaning"]
                    confidence = analysis["confidence"]
                    
                    result_text += f"#### {field_path}\n"
                    result_text += f"- **建议含义**: {suggested_meaning}\n"
                    result_text += f"- **置信度**: {confidence:.1%}\n"
                    
                    if analysis["reasoning"]:
                        result_text += f"- **推理依据**: {', '.join(analysis['reasoning'])}\n"
                    
                    if analysis["suggestions"]:
                        result_text += f"- **改进建议**: {'; '.join(analysis['suggestions'])}\n"
                    
                    result_text += "\n"
            
            # 添加后续操作建议
            result_text += "### 后续操作建议\n\n"
            if updated_fields < analyzed_fields:
                result_text += "- 对于置信度较低的字段，建议手动确认和更新语义信息\n"
            result_text += "- 使用 `manage_semantics` 的 view 操作查看更新后的语义信息\n"
            result_text += "- 使用 `generate_query` 工具测试语义理解效果\n"
            
            logger.info(
                "批量语义分析完成",
                instance_id=instance_id,
                database=database_name,
                collection=collection_name,
                total_fields=total_fields,
                updated_fields=updated_fields
            )
            
            return [TextContent(type="text", text=result_text)]
            
        except Exception as e:
            logger.error("批量语义分析失败", error=str(e))
            return [TextContent(type="text", text=f"批量语义分析时发生错误: {str(e)}")]
    
    async def _handle_search(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """处理搜索操作"""
        instance_id = arguments["instance_id"]
        search_term = arguments.get("search_term")
        
        if not search_term:
            return [TextContent(
                type="text",
                text="搜索操作需要提供 search_term 参数。"
            )]
        
        try:
            # 搜索相关字段
            search_results = await self.metadata_manager.search_fields_by_meaning(
                instance_id, search_term
            )
            
            if not search_results:
                return [TextContent(
                    type="text",
                    text=f"未找到与 '{search_term}' 相关的字段。"
                )]
            
            result_text = f"## 语义搜索结果: '{search_term}'\n\n"
            
            # 按数据库和集合分组显示结果
            grouped_results = {}
            for field in search_results:
                db_name = field["database_name"]
                coll_name = field["collection_name"]
                key = f"{db_name}.{coll_name}"
                
                if key not in grouped_results:
                    grouped_results[key] = []
                grouped_results[key].append(field)
            
            for collection_key, fields in grouped_results.items():
                result_text += f"### {collection_key}\n\n"
                
                for field in fields:
                    field_path = field["field_path"]
                    business_meaning = field.get("business_meaning", "未定义")
                    field_type = field.get("field_type", "unknown")
                    
                    result_text += f"- **{field_path}** ({field_type})\n"
                    result_text += f"  - 业务含义: {business_meaning}\n"
                    
                    if field.get("examples"):
                        examples = field["examples"][:2]
                        examples_str = ", ".join([str(ex) for ex in examples])
                        result_text += f"  - 示例值: {examples_str}\n"
                
                result_text += "\n"
            
            result_text += f"### 搜索统计\n\n"
            result_text += f"- **匹配字段数**: {len(search_results)}\n"
            result_text += f"- **涉及集合数**: {len(grouped_results)}\n"
            
            return [TextContent(type="text", text=result_text)]
            
        except Exception as e:
            logger.error("语义搜索失败", error=str(e))
            return [TextContent(type="text", text=f"语义搜索时发生错误: {str(e)}")]
    
    async def _handle_suggest(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """处理建议操作"""
        instance_id = arguments["instance_id"]
        database_name = arguments.get("database_name")
        collection_name = arguments.get("collection_name")
        query_description = arguments.get("query_description")
        
        if not all([database_name, collection_name, query_description]):
            return [TextContent(
                type="text",
                text="建议操作需要提供 database_name, collection_name 和 query_description 参数。"
            )]
        
        try:
            # 获取字段建议
            from .collection_analysis import CollectionAnalysisTool
            
            analysis_tool = CollectionAnalysisTool(
                self.connection_manager, self.metadata_manager, self.semantic_analyzer
            )
            
            suggestions = await analysis_tool.get_field_suggestions(
                instance_id, database_name, collection_name, query_description
            )
            
            if not suggestions:
                return [TextContent(
                    type="text",
                    text=f"未找到与查询描述 '{query_description}' 相关的字段建议。"
                )]
            
            result_text = f"## 字段建议: '{query_description}'\n\n"
            result_text += f"基于查询描述，为集合 `{database_name}.{collection_name}` 推荐以下字段:\n\n"
            
            for i, suggestion in enumerate(suggestions[:10], 1):
                field_path = suggestion["field_path"]
                business_meaning = suggestion["business_meaning"] or "未定义"
                relevance_score = suggestion["relevance_score"]
                field_type = suggestion["field_type"]
                
                result_text += f"{i}. **{field_path}** ({field_type})\n"
                result_text += f"   - 业务含义: {business_meaning}\n"
                result_text += f"   - 相关性: {relevance_score:.1%}\n\n"
            
            result_text += "### 使用建议\n\n"
            result_text += "- 选择相关性高的字段构建查询条件\n"
            result_text += "- 使用 `generate_query` 工具生成具体的查询语句\n"
            result_text += "- 如果字段含义不明确，使用 `manage_semantics` 工具更新语义信息\n"
            
            return [TextContent(type="text", text=result_text)]
            
        except Exception as e:
            logger.error("获取字段建议失败", error=str(e))
            return [TextContent(type="text", text=f"获取字段建议时发生错误: {str(e)}")]
    
    async def _view_field_semantics(self, instance_id: str, database_name: str, 
                                  collection_name: str, field_path: str) -> List[TextContent]:
        """查看特定字段的语义信息"""
        try:
            field_info = await self.metadata_manager.get_field_info(
                instance_id, database_name, collection_name, field_path
            )
            
            if not field_info:
                return [TextContent(
                    type="text",
                    text=f"字段 '{field_path}' 不存在于集合 '{database_name}.{collection_name}' 中。"
                )]
            
            result_text = f"## 字段语义信息: {field_path}\n\n"
            result_text += f"- **实例**: {instance_id}\n"
            result_text += f"- **数据库**: {database_name}\n"
            result_text += f"- **集合**: {collection_name}\n"
            result_text += f"- **字段路径**: {field_path}\n"
            result_text += f"- **数据类型**: {field_info.get('field_type', 'unknown')}\n"
            result_text += f"- **出现率**: {field_info.get('occurrence_rate', 0):.1%}\n"
            
            business_meaning = field_info.get("business_meaning")
            if business_meaning:
                result_text += f"- **业务含义**: {business_meaning}\n"
            else:
                result_text += f"- **业务含义**: 未定义\n"
                
                # 提供语义建议
                analysis = await self.semantic_analyzer.analyze_field_semantics(
                    instance_id, database_name, collection_name, field_path, field_info
                )
                if analysis["suggested_meaning"]:
                    result_text += f"- **建议含义**: {analysis['suggested_meaning']} (置信度: {analysis['confidence']:.1%})\n"
            
            if field_info.get("examples"):
                examples = field_info["examples"][:5]
                examples_str = ", ".join([str(ex) for ex in examples])
                result_text += f"- **示例值**: {examples_str}\n"
            
            if field_info.get("is_indexed"):
                result_text += f"- **索引状态**: ✅ 已索引\n"
            
            if field_info.get("is_required"):
                result_text += f"- **必需字段**: ✅ 是\n"
            
            return [TextContent(type="text", text=result_text)]
            
        except Exception as e:
            logger.error("查看字段语义失败", error=str(e))
            return [TextContent(type="text", text=f"查看字段语义时发生错误: {str(e)}")]
    
    async def _view_collection_semantics(self, instance_id: str, database_name: str, collection_name: str) -> List[TextContent]:
        """查看集合的语义覆盖情况"""
        try:
            fields = await self.metadata_manager.get_fields_by_collection(
                instance_id, instance_id, database_name, collection_name
            )
            
            if not fields:
                return [TextContent(
                    type="text",
                    text=f"集合 '{database_name}.{collection_name}' 中没有字段信息。请先使用 analyze_collection 工具扫描集合结构。"
                )]
            
            total_fields = len(fields)
            fields_with_meaning = sum(1 for field in fields if field.get("business_meaning"))
            coverage_rate = fields_with_meaning / total_fields if total_fields > 0 else 0
            
            result_text = f"## 集合语义覆盖: {database_name}.{collection_name}\n\n"
            result_text += f"### 统计信息\n\n"
            result_text += f"- **字段总数**: {total_fields}\n"
            result_text += f"- **已定义语义**: {fields_with_meaning}\n"
            result_text += f"- **覆盖率**: {coverage_rate:.1%}\n\n"
            
            # 显示已定义语义的字段
            fields_with_semantics = [f for f in fields if f.get("business_meaning")]
            if fields_with_semantics:
                result_text += f"### 已定义语义的字段\n\n"
                for field in fields_with_semantics:
                    field_path = field["field_path"]
                    business_meaning = field["business_meaning"]
                    result_text += f"- **{field_path}**: {business_meaning}\n"
                result_text += "\n"
            
            # 显示未定义语义的字段
            fields_without_semantics = [f for f in fields if not f.get("business_meaning")]
            if fields_without_semantics:
                result_text += f"### 未定义语义的字段\n\n"
                for field in fields_without_semantics[:10]:  # 只显示前10个
                    field_path = field["field_path"]
                    field_type = field.get("field_type", "unknown")
                    result_text += f"- **{field_path}** ({field_type})\n"
                
                if len(fields_without_semantics) > 10:
                    result_text += f"- ... 还有 {len(fields_without_semantics) - 10} 个字段\n"
                
                result_text += "\n"
                result_text += "💡 **建议**: 使用 `manage_semantics` 的 batch_analyze 操作自动分析这些字段的语义\n\n"
            
            return [TextContent(type="text", text=result_text)]
            
        except Exception as e:
            logger.error("查看集合语义失败", error=str(e))
            return [TextContent(type="text", text=f"查看集合语义时发生错误: {str(e)}")]
    
    async def _view_database_semantics(self, instance_id: str, database_name: str) -> List[TextContent]:
        """查看数据库的语义覆盖情况"""
        try:
            # 获取数据库中的所有集合
            collections = await self.metadata_manager.get_collections_by_database(instance_id, database_name)
            
            if not collections:
                return [TextContent(
                    type="text",
                    text=f"数据库 '{database_name}' 中没有集合信息。请先使用相关工具扫描数据库结构。"
                )]
            
            result_text = f"## 数据库语义覆盖: {database_name}\n\n"
            
            total_collections = len(collections)
            total_fields = 0
            total_fields_with_meaning = 0
            
            collection_stats = []
            
            for collection in collections:
                collection_name = collection["collection_name"]
                fields = await self.metadata_manager.get_fields_by_collection(
                    instance_id, database_name, collection_name
                )
                
                field_count = len(fields)
                fields_with_meaning = sum(1 for field in fields if field.get("business_meaning"))
                coverage_rate = fields_with_meaning / field_count if field_count > 0 else 0
                
                collection_stats.append({
                    "collection_name": collection_name,
                    "field_count": field_count,
                    "fields_with_meaning": fields_with_meaning,
                    "coverage_rate": coverage_rate
                })
                
                total_fields += field_count
                total_fields_with_meaning += fields_with_meaning
            
            overall_coverage = total_fields_with_meaning / total_fields if total_fields > 0 else 0
            
            result_text += f"### 总体统计\n\n"
            result_text += f"- **集合数量**: {total_collections}\n"
            result_text += f"- **字段总数**: {total_fields}\n"
            result_text += f"- **已定义语义**: {total_fields_with_meaning}\n"
            result_text += f"- **整体覆盖率**: {overall_coverage:.1%}\n\n"
            
            result_text += f"### 各集合覆盖情况\n\n"
            for stats in collection_stats:
                collection_name = stats["collection_name"]
                field_count = stats["field_count"]
                fields_with_meaning = stats["fields_with_meaning"]
                coverage_rate = stats["coverage_rate"]
                
                status_icon = "✅" if coverage_rate > 0.8 else "⚠️" if coverage_rate > 0.5 else "❌"
                
                result_text += f"- {status_icon} **{collection_name}**: {fields_with_meaning}/{field_count} ({coverage_rate:.1%})\n"
            
            result_text += "\n"
            
            # 提供改进建议
            low_coverage_collections = [s for s in collection_stats if s["coverage_rate"] < 0.5]
            if low_coverage_collections:
                result_text += f"### 改进建议\n\n"
                result_text += f"以下集合的语义覆盖率较低，建议优先处理:\n\n"
                for stats in low_coverage_collections[:5]:
                    result_text += f"- {stats['collection_name']} ({stats['coverage_rate']:.1%})\n"
                result_text += "\n使用 `manage_semantics` 的 batch_analyze 操作可以自动分析这些集合的字段语义。\n\n"
            
            return [TextContent(type="text", text=result_text)]
            
        except Exception as e:
            logger.error("查看数据库语义失败", error=str(e))
            return [TextContent(type="text", text=f"查看数据库语义时发生错误: {str(e)}")]
    
    async def _view_instance_semantics(self, instance_id: str) -> List[TextContent]:
        """查看实例的语义覆盖情况"""
        try:
            # 获取实例统计信息
            stats = await self.metadata_manager.get_instance_stats(instance_id)
            
            if not stats:
                return [TextContent(
                    type="text",
                    text=f"实例 '{instance_id}' 没有统计信息。请先扫描实例结构。"
                )]
            
            result_text = f"## 实例语义覆盖: {instance_id}\n\n"
            result_text += f"### 统计信息\n\n"
            result_text += f"- **数据库数量**: {stats.get('database_count', 0)}\n"
            result_text += f"- **集合数量**: {stats.get('collection_count', 0)}\n"
            result_text += f"- **字段总数**: {stats.get('field_count', 0)}\n"
            result_text += f"- **已定义语义**: {stats.get('fields_with_meaning', 0)}\n"
            
            field_count = stats.get('field_count', 0)
            fields_with_meaning = stats.get('fields_with_meaning', 0)
            if field_count > 0:
                coverage_rate = fields_with_meaning / field_count
                result_text += f"- **整体覆盖率**: {coverage_rate:.1%}\n"
            
            result_text += "\n"
            result_text += "💡 **提示**: 使用 `manage_semantics` 的 view 操作查看特定数据库或集合的详细语义信息。\n"
            
            return [TextContent(type="text", text=result_text)]
            
        except Exception as e:
            logger.error("查看实例语义失败", error=str(e))
            return [TextContent(type="text", text=f"查看实例语义时发生错误: {str(e)}")]
    
    async def _update_field_semantics_by_instance_name(self, instance_name: str, database_name: str, 
                                                     collection_name: str, field_path: str, 
                                                     business_meaning: str) -> bool:
        """使用实例名称更新字段语义的辅助方法"""
        try:
            # 直接调用新的双重存储策略方法
            # 这里我们需要一个假的ObjectId，因为新方法需要它作为参数但会在失败时回退到业务库存储
            from bson import ObjectId
            fake_instance_id = ObjectId()
            
            # 调用元数据管理器的双重存储方法
            success = await self.metadata_manager.update_field_semantics(
                instance_name, fake_instance_id, database_name, collection_name, 
                field_path, business_meaning
            )
            
            return success
            
        except Exception as e:
            logger.error("使用实例名称更新字段语义失败", error=str(e))
            return False