# -*- coding: utf-8 -*-
"""查询确认工具"""

from typing import Dict, List, Any, Optional
import json
from datetime import datetime
import structlog
from mcp.types import Tool, TextContent

from database.connection_manager import ConnectionManager
from database.metadata_manager import MetadataManager
from database.query_engine import QueryEngine


logger = structlog.get_logger(__name__)


class QueryConfirmationTool:
    """查询确认工具"""
    
    def __init__(self, connection_manager: ConnectionManager, 
                 metadata_manager: MetadataManager,
                 query_engine: QueryEngine):
        self.connection_manager = connection_manager
        self.metadata_manager = metadata_manager
        self.query_engine = query_engine
    
    def get_tool_definition(self) -> Tool:
        """获取工具定义"""
        return Tool(
            name="confirm_query",
            description="执行生成的MongoDB查询并返回结果",
            inputSchema={
                "type": "object",
                "properties": {
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
                    "query_type": {
                        "type": "string",
                        "enum": ["find", "count", "aggregate", "distinct"],
                        "description": "查询类型"
                    },
                    "mongodb_query": {
                        "type": "object",
                        "description": "MongoDB查询对象"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "结果限制数量（仅用于find和aggregate查询）",
                        "default": 100,
                        "minimum": 1,
                        "maximum": 1000
                    },
                    "explain": {
                        "type": "boolean",
                        "description": "是否返回查询执行计划",
                        "default": False
                    },
                    "format_output": {
                        "type": "boolean",
                        "description": "是否格式化输出结果",
                        "default": True
                    },
                    "include_metadata": {
                        "type": "boolean",
                        "description": "是否包含查询元数据信息",
                        "default": True
                    }
                },
                "required": ["instance_id", "database_name", "collection_name", "query_type", "mongodb_query"]
            }
        )
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """执行查询确认"""
        instance_id = arguments["instance_id"]
        database_name = arguments["database_name"]
        collection_name = arguments["collection_name"]
        query_type = arguments["query_type"]
        mongodb_query = arguments["mongodb_query"]
        limit = arguments.get("limit", 100)
        explain = arguments.get("explain", False)
        format_output = arguments.get("format_output", True)
        include_metadata = arguments.get("include_metadata", True)
        
        logger.info(
            "开始执行查询",
            instance_id=instance_id,
            database=database_name,
            collection=collection_name,
            query_type=query_type
        )
        
        try:
            # 验证实例和集合
            validation_result = await self._validate_target(instance_id, database_name, collection_name)
            if validation_result:
                return [TextContent(type="text", text=validation_result)]
            
            # 执行查询
            start_time = datetime.now()
            
            if query_type == "find":
                result = await self._execute_find_query(
                    instance_id, database_name, collection_name, mongodb_query, limit, explain
                )
            elif query_type == "count":
                result = await self._execute_count_query(
                    instance_id, database_name, collection_name, mongodb_query
                )
            elif query_type == "aggregate":
                result = await self._execute_aggregate_query(
                    instance_id, database_name, collection_name, mongodb_query, limit, explain
                )
            elif query_type == "distinct":
                result = await self._execute_distinct_query(
                    instance_id, database_name, collection_name, mongodb_query
                )
            else:
                return [TextContent(type="text", text=f"不支持的查询类型: {query_type}")]
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            if "error" in result:
                return [TextContent(type="text", text=f"查询执行失败: {result['error']}")]
            
            # 构建结果文本
            result_text = await self._build_result_text(
                result, query_type, mongodb_query, execution_time,
                format_output, include_metadata, explain
            )
            
            # 更新查询历史
            await self._update_query_history(
                instance_id, database_name, collection_name,
                query_type, mongodb_query, result, execution_time
            )
            
            logger.info(
                "查询执行完成",
                instance_id=instance_id,
                database=database_name,
                collection=collection_name,
                query_type=query_type,
                execution_time=execution_time,
                result_count=result.get("count", 0)
            )
            
            return [TextContent(type="text", text=result_text)]
            
        except Exception as e:
            error_msg = f"执行查询时发生错误: {str(e)}"
            logger.error(
                "查询执行失败",
                instance_id=instance_id,
                database=database_name,
                collection=collection_name,
                query_type=query_type,
                error=str(e)
            )
            return [TextContent(type="text", text=error_msg)]
    
    async def _validate_target(self, instance_id: str, database_name: str, collection_name: str) -> Optional[str]:
        """验证目标实例和集合"""
        # 验证实例
        if not self.connection_manager.has_instance(instance_id):
            return f"实例 '{instance_id}' 不存在。请使用 discover_instances 工具查看可用实例。"
        
        # 检查实例健康状态
        health_status = await self.connection_manager.check_instance_health(instance_id)
        if not health_status["healthy"]:
            return f"实例 '{instance_id}' 不健康: {health_status.get('error', 'Unknown error')}"
        
        # 验证集合是否存在
        try:
            connection = self.connection_manager.get_instance_connection(instance_id)
            if connection:
                db = connection.get_database(database_name)
                collection_names = await db.list_collection_names()
                if collection_name not in collection_names:
                    return f"集合 '{database_name}.{collection_name}' 不存在。"
        except Exception as e:
            return f"验证集合时发生错误: {str(e)}"
        
        return None
    
    async def _execute_find_query(self, instance_id: str, database_name: str, collection_name: str,
                                mongodb_query: Dict[str, Any], limit: int, explain: bool) -> Dict[str, Any]:
        """执行查找查询"""
        try:
            filter_query = mongodb_query.get("filter", {})
            sort_query = mongodb_query.get("sort")
            projection = mongodb_query.get("projection")
            
            # 执行查询
            result = await self.query_engine.execute_find_query(
                instance_id=instance_id,
                database_name=database_name,
                collection_name=collection_name,
                filter_query=filter_query,
                projection=projection,
                sort=sort_query,
                limit=limit
            )
            
            if explain and "documents" in result:
                # 获取查询执行计划
                explain_result = await self.query_engine.explain_query(
                    instance_id=instance_id,
                    database_name=database_name,
                    collection_name=collection_name,
                    filter_query=filter_query,
                    sort=sort_query
                )
                result["explain"] = explain_result
            
            return result
            
        except Exception as e:
            return {"error": str(e)}
    
    async def _execute_count_query(self, instance_id: str, database_name: str, collection_name: str,
                                 mongodb_query: Dict[str, Any]) -> Dict[str, Any]:
        """执行计数查询"""
        try:
            filter_query = mongodb_query.get("filter", {})
            
            # 执行计数查询
            result = await self.query_engine.count_documents(
                instance_id=instance_id,
                database_name=database_name,
                collection_name=collection_name,
                filter_query=filter_query
            )
            
            return result
            
        except Exception as e:
            return {"error": str(e)}
    
    async def _execute_aggregate_query(self, instance_id: str, database_name: str, collection_name: str,
                                     mongodb_query: Dict[str, Any], limit: int, explain: bool) -> Dict[str, Any]:
        """执行聚合查询"""
        try:
            pipeline = mongodb_query.get("pipeline", [])
            
            # 确保pipeline中有limit阶段
            has_limit = any("$limit" in stage for stage in pipeline)
            if not has_limit:
                pipeline.append({"$limit": limit})
            
            # 执行聚合查询
            result = await self.query_engine.execute_aggregation(
                instance_id=instance_id,
                database_name=database_name,
                collection_name=collection_name,
                pipeline=pipeline
            )
            
            if explain and "documents" in result:
                # 聚合查询的执行计划
                try:
                    connection = self.connection_manager.get_instance_connection(instance_id)
                    if connection:
                        db = connection.get_database(database_name)
                        collection = db[collection_name]
                        
                        # 添加explain阶段
                        explain_pipeline = [{"$explain": {"verbosity": "executionStats"}}] + pipeline
                        explain_cursor = collection.aggregate(explain_pipeline)
                        explain_result = await explain_cursor.to_list(length=1)
                        
                        if explain_result:
                            result["explain"] = explain_result[0]
                except Exception as explain_error:
                    logger.warning("获取聚合查询执行计划失败", error=str(explain_error))
            
            return result
            
        except Exception as e:
            return {"error": str(e)}
    
    async def _execute_distinct_query(self, instance_id: str, database_name: str, collection_name: str,
                                    mongodb_query: Dict[str, Any]) -> Dict[str, Any]:
        """执行去重查询"""
        try:
            field = mongodb_query.get("field")
            filter_query = mongodb_query.get("filter", {})
            
            if not field:
                return {"error": "去重查询缺少字段参数"}
            
            # 执行去重查询
            result = await self.query_engine.get_distinct_values(
                instance_id=instance_id,
                database_name=database_name,
                collection_name=collection_name,
                field=field,
                filter_query=filter_query
            )
            
            return result
            
        except Exception as e:
            return {"error": str(e)}
    
    async def _build_result_text(self, result: Dict[str, Any], query_type: str, 
                               mongodb_query: Dict[str, Any], execution_time: float,
                               format_output: bool, include_metadata: bool, explain: bool) -> str:
        """构建结果文本"""
        result_text = f"## 查询执行结果\n\n"
        
        # 查询信息
        if include_metadata:
            result_text += f"### 查询信息\n\n"
            result_text += f"- **查询类型**: {query_type.upper()}\n"
            result_text += f"- **执行时间**: {execution_time:.3f} 秒\n"
            
            if query_type in ["find", "aggregate"]:
                result_text += f"- **返回记录数**: {result.get('count', 0)}\n"
            elif query_type == "count":
                result_text += f"- **文档总数**: {result.get('count', 0)}\n"
            elif query_type == "distinct":
                result_text += f"- **唯一值数量**: {len(result.get('values', []))}\n"
            
            result_text += "\n"
        
        # 查询结果
        result_text += f"### 查询结果\n\n"
        
        if query_type == "count":
            count = result.get("count", 0)
            result_text += f"**文档数量**: {count:,}\n\n"
            
        elif query_type == "distinct":
            values = result.get("values", [])
            field = mongodb_query.get("field", "unknown")
            
            result_text += f"**字段 '{field}' 的唯一值** ({len(values)} 个):\n\n"
            
            if format_output:
                # 格式化显示唯一值
                if len(values) <= 50:
                    for i, value in enumerate(values, 1):
                        result_text += f"{i}. {self._format_value(value)}\n"
                else:
                    # 显示前50个值
                    for i, value in enumerate(values[:50], 1):
                        result_text += f"{i}. {self._format_value(value)}\n"
                    result_text += f"\n... 还有 {len(values) - 50} 个值\n"
            else:
                result_text += f"```json\n{json.dumps(values, indent=2, ensure_ascii=False, default=str)}\n```\n"
            
            result_text += "\n"
            
        elif query_type in ["find", "aggregate"]:
            documents = result.get("documents", [])
            count = result.get("count", len(documents))
            
            if count == 0:
                result_text += "**没有找到匹配的文档**\n\n"
            else:
                result_text += f"**找到 {count} 条记录**:\n\n"
                
                if format_output:
                    # 格式化显示文档
                    result_text += await self._format_documents(documents)
                else:
                    # JSON格式显示
                    result_text += f"```json\n{json.dumps(documents, indent=2, ensure_ascii=False, default=str)}\n```\n"
        
        # 执行计划
        if explain and "explain" in result:
            result_text += await self._format_explain_result(result["explain"])
        
        # 性能建议
        if include_metadata:
            result_text += await self._generate_performance_suggestions(
                query_type, mongodb_query, result, execution_time
            )
        
        return result_text
    
    async def _format_documents(self, documents: List[Dict[str, Any]]) -> str:
        """格式化文档显示"""
        if not documents:
            return "无文档\n\n"
        
        formatted_text = ""
        
        # 显示前10个文档的详细信息
        display_count = min(len(documents), 10)
        
        for i, doc in enumerate(documents[:display_count], 1):
            formatted_text += f"#### 文档 {i}\n\n"
            
            # 格式化文档字段
            for key, value in doc.items():
                formatted_value = self._format_value(value)
                formatted_text += f"- **{key}**: {formatted_value}\n"
            
            formatted_text += "\n"
        
        # 如果有更多文档，显示摘要
        if len(documents) > display_count:
            formatted_text += f"... 还有 {len(documents) - display_count} 条记录\n\n"
            
            # 显示字段摘要
            if documents:
                all_fields = set()
                for doc in documents:
                    all_fields.update(doc.keys())
                
                formatted_text += f"**所有文档包含的字段**: {', '.join(sorted(all_fields))}\n\n"
        
        return formatted_text
    
    def _format_value(self, value: Any) -> str:
        """格式化值显示"""
        if value is None:
            return "null"
        elif isinstance(value, str):
            # 限制字符串长度
            if len(value) > 100:
                return f"\"{value[:97]}...\""
            return f"\"{value}\""
        elif isinstance(value, (list, dict)):
            # 复杂对象显示为JSON
            json_str = json.dumps(value, ensure_ascii=False, default=str)
            if len(json_str) > 200:
                return f"{json_str[:197]}..."
            return json_str
        elif isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        else:
            return str(value)
    
    async def _format_explain_result(self, explain_result: Dict[str, Any]) -> str:
        """格式化执行计划结果"""
        explain_text = f"### 查询执行计划\n\n"
        
        # 提取关键信息
        if "executionStats" in explain_result:
            stats = explain_result["executionStats"]
            
            explain_text += f"**执行统计**:\n"
            explain_text += f"- 总执行时间: {stats.get('executionTimeMillis', 0)} ms\n"
            explain_text += f"- 检查文档数: {stats.get('totalDocsExamined', 0):,}\n"
            explain_text += f"- 返回文档数: {stats.get('totalDocsReturned', 0):,}\n"
            
            if "indexesUsed" in stats:
                indexes = stats["indexesUsed"]
                if indexes:
                    explain_text += f"- 使用的索引: {', '.join(indexes)}\n"
                else:
                    explain_text += f"- 使用的索引: 无 (全表扫描)\n"
            
            explain_text += "\n"
        
        # 显示完整执行计划（折叠格式）
        explain_text += f"<details>\n<summary>完整执行计划</summary>\n\n"
        explain_text += f"```json\n{json.dumps(explain_result, indent=2, ensure_ascii=False, default=str)}\n```\n\n"
        explain_text += f"</details>\n\n"
        
        return explain_text
    
    async def _generate_performance_suggestions(self, query_type: str, mongodb_query: Dict[str, Any],
                                              result: Dict[str, Any], execution_time: float) -> str:
        """生成性能建议"""
        suggestions_text = f"### 性能建议\n\n"
        suggestions = []
        
        # 执行时间建议
        if execution_time > 5.0:
            suggestions.append("⚠️ 查询执行时间较长，建议优化查询条件或添加索引")
        elif execution_time > 1.0:
            suggestions.append("💡 查询执行时间适中，可考虑进一步优化")
        else:
            suggestions.append("✅ 查询执行时间良好")
        
        # 结果数量建议
        if query_type in ["find", "aggregate"]:
            count = result.get("count", 0)
            if count > 1000:
                suggestions.append("⚠️ 返回结果较多，建议添加更精确的筛选条件")
            elif count > 100:
                suggestions.append("💡 返回结果适中，可考虑分页处理")
        
        # 索引建议
        if "explain" in result:
            explain_result = result["explain"]
            if "executionStats" in explain_result:
                stats = explain_result["executionStats"]
                docs_examined = stats.get("totalDocsExamined", 0)
                docs_returned = stats.get("totalDocsReturned", 0)
                
                if docs_examined > docs_returned * 10:
                    suggestions.append("⚠️ 扫描文档数远大于返回文档数，强烈建议添加索引")
                elif docs_examined > docs_returned * 2:
                    suggestions.append("💡 建议为查询字段添加索引以提高性能")
        
        # 查询优化建议
        if query_type == "find":
            filter_query = mongodb_query.get("filter", {})
            if not filter_query:
                suggestions.append("💡 无筛选条件的查询可能返回大量数据，建议添加筛选条件")
            
            # 检查是否使用了正则表达式
            if self._has_regex_query(filter_query):
                suggestions.append("💡 正则表达式查询性能较低，建议使用文本索引或精确匹配")
        
        elif query_type == "aggregate":
            pipeline = mongodb_query.get("pipeline", [])
            
            # 检查$match阶段位置
            match_stages = [i for i, stage in enumerate(pipeline) if "$match" in stage]
            if match_stages and match_stages[0] > 0:
                suggestions.append("💡 建议将$match阶段移到聚合管道的开始位置以提高性能")
            
            # 检查是否有$sort但没有索引支持
            sort_stages = [stage for stage in pipeline if "$sort" in stage]
            if sort_stages:
                suggestions.append("💡 聚合管道中的排序操作建议有索引支持")
        
        # 输出建议
        if suggestions:
            for suggestion in suggestions:
                suggestions_text += f"- {suggestion}\n"
        else:
            suggestions_text += "- ✅ 查询性能良好，无特殊建议\n"
        
        suggestions_text += "\n"
        return suggestions_text
    
    def _has_regex_query(self, query: Dict[str, Any]) -> bool:
        """检查查询是否包含正则表达式"""
        if isinstance(query, dict):
            for key, value in query.items():
                if key == "$regex" or (isinstance(value, dict) and "$regex" in value):
                    return True
                elif isinstance(value, dict):
                    if self._has_regex_query(value):
                        return True
        return False
    
    async def _update_query_history(self, instance_id: str, database_name: str, collection_name: str,
                                  query_type: str, mongodb_query: Dict[str, Any], 
                                  result: Dict[str, Any], execution_time: float):
        """更新查询历史"""
        try:
            # 查找最近的查询历史记录并更新执行结果
            recent_queries = await self.metadata_manager.get_query_history(
                instance_id=instance_id,
                database_name=database_name,
                collection_name=collection_name,
                limit=10
            )
            
            # 查找匹配的查询记录
            for query_record in recent_queries:
                if (query_record.get("query_type") == query_type and 
                    query_record.get("mongodb_query") == mongodb_query):
                    
                    # 更新执行结果
                    execution_result = {
                        "executed_at": datetime.now(),
                        "execution_time": execution_time,
                        "result_count": result.get("count", 0),
                        "success": "error" not in result
                    }
                    
                    if "error" in result:
                        execution_result["error"] = result["error"]
                    
                    # 这里可以扩展metadata_manager来支持更新查询历史
                    # await self.metadata_manager.update_query_execution_result(...)
                    break
            
        except Exception as e:
            logger.warning("更新查询历史失败", error=str(e))