# -*- coding: utf-8 -*-
"""查询生成工具 v2 - 支持用户确认机制"""

from typing import Dict, List, Any, Optional
import structlog
from mcp.types import Tool, TextContent

from database.connection_manager import ConnectionManager
from database.metadata_manager import MetadataManager
from scanner.semantic_analyzer import SemanticAnalyzer
from utils.parameter_validator import ParameterValidator, MCPParameterHelper, ValidationResult
from utils.tool_context import get_context_manager
from utils.error_handler import with_error_handling, with_retry, RetryConfig
from utils.workflow_manager import get_workflow_manager, WorkflowStage
from utils.user_confirmation import UserConfirmationHelper, ConfirmationParser

logger = structlog.get_logger(__name__)


class QueryGenerationTool:
    """查询生成工具 v2 - 支持用户确认机制"""
    
    def __init__(self, connection_manager: ConnectionManager, 
                 metadata_manager: MetadataManager,
                 semantic_analyzer: SemanticAnalyzer):
        self.connection_manager = connection_manager
        self.metadata_manager = metadata_manager
        self.semantic_analyzer = semantic_analyzer
        self.context_manager = get_context_manager()
        self.workflow_manager = get_workflow_manager()
    
    def get_tool_definition(self) -> Tool:
        """获取工具定义"""
        return Tool(
            name="generate_query",
            description="智能查询生成工具：生成MongoDB查询语句并要求用户确认后执行",
            inputSchema={
                "type": "object",
                "properties": {
                    "instance_id": {
                        "type": "string",
                        "description": "MongoDB实例ID（可选，会从工作流上下文自动获取）"
                    },
                    "database_name": {
                        "type": "string",
                        "description": "数据库名称（可选，会从工作流上下文自动获取）"
                    },
                    "collection_name": {
                        "type": "string",
                        "description": "集合名称（可选，会从工作流上下文自动获取）"
                    },
                    "query_description": {
                        "type": "string",
                        "description": "查询需求的自然语言描述"
                    },
                    "query_type": {
                        "type": "string",
                        "description": "查询类型",
                        "enum": ["auto", "find", "count", "aggregate", "distinct"],
                        "default": "auto"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "结果限制数量",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 1000
                    },
                    "session_id": {
                        "type": "string",
                        "description": "会话标识符，默认为'default'",
                        "default": "default"
                    },
                    "user_confirmation": {
                        "type": "string",
                        "description": "用户对生成查询的确认选择（A=执行, B=修改, C=查看计划, D=取消）"
                    },
                    "skip_confirmation": {
                        "type": "boolean",
                        "description": "跳过用户确认，直接生成查询语句（不执行）",
                        "default": False
                    }
                },
                "required": ["query_description"]
            }
        )
    
    @with_error_handling("查询生成")
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """执行查询生成"""
        session_id = arguments.get("session_id", "default")
        query_description = arguments["query_description"]
        query_type = arguments.get("query_type", "auto")
        limit = arguments.get("limit", 10)
        user_confirmation = arguments.get("user_confirmation")
        skip_confirmation = arguments.get("skip_confirmation", False)
        
        # 从工作流上下文获取缺失参数
        workflow_data = await self.workflow_manager.get_workflow_data(session_id)
        
        instance_id = arguments.get("instance_id") or workflow_data.get("instance_id")
        database_name = arguments.get("database_name") or workflow_data.get("database_name")
        collection_name = arguments.get("collection_name") or workflow_data.get("collection_name")
        
        # 验证必需参数
        if not instance_id:
            return [TextContent(
                type="text",
                text="## ❌ 缺少实例信息\n\n请先选择MongoDB实例。"
            )]
            
        if not database_name:
            return [TextContent(
                type="text",
                text="## ❌ 缺少数据库信息\n\n请先选择数据库。"
            )]
            
        if not collection_name:
            return [TextContent(
                type="text",
                text="## ❌ 缺少集合信息\n\n请先选择集合。"
            )]
        
        # 验证连接
        if not self.connection_manager.has_instance(instance_id):
            return [TextContent(
                type="text",
                text=f"## ❌ 实例不存在\n\n实例 `{instance_id}` 不存在。"
            )]
        
        # 生成查询语句
        try:
            query_info = await self._generate_query(
                instance_id, database_name, collection_name, 
                query_description, query_type, limit, session_id
            )
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"## ❌ 查询生成失败\n\n错误: {str(e)}\n\n请检查查询描述是否清晰，或尝试更简单的查询。"
            )]
        
        # 如果跳过确认，直接返回查询语句
        if skip_confirmation:
            return await self._show_query_only(query_info)
        
        # 如果没有用户确认，显示确认提示
        if not user_confirmation:
            return await self._show_confirmation_prompt(query_info)
        
        # 处理用户确认
        return await self._handle_user_confirmation(user_confirmation, query_info, session_id)
    
    async def _generate_query(self, instance_id: str, database_name: str, collection_name: str,
                            query_description: str, query_type: str, limit: int, session_id: str) -> Dict[str, Any]:
        """生成MongoDB查询语句"""
        logger.info("生成查询语句", 
                   instance_id=instance_id,
                   database_name=database_name,
                   collection_name=collection_name,
                   query_description=query_description,
                   query_type=query_type)
        
        # 获取集合结构信息
        collection_info = await self._get_collection_info(instance_id, database_name, collection_name)
        
        # 使用语义分析器来理解查询意图
        semantic_info = await self._analyze_query_semantics(
            instance_id, database_name, collection_name, query_description
        )
        
        # 基于结构和语义信息生成查询
        mongodb_query = await self._build_mongodb_query(
            collection_info, semantic_info, query_description, query_type, limit
        )
        
        # 估算结果数量
        estimated_count = await self._estimate_result_count(
            instance_id, database_name, collection_name, mongodb_query
        )
        
        return {
            "instance_id": instance_id,
            "database_name": database_name,
            "collection_name": collection_name,
            "query_description": query_description,
            "query_type": mongodb_query.get("operation", query_type),
            "mongodb_query": mongodb_query,
            "limit": limit,
            "estimated_result_count": estimated_count,
            "collection_info": collection_info,
            "semantic_info": semantic_info
        }
    
    async def _get_collection_info(self, instance_id: str, database_name: str, collection_name: str) -> Dict[str, Any]:
        """获取集合结构信息"""
        try:
            connection = self.connection_manager.get_instance_connection(instance_id)
            if not connection or not connection.client:
                raise ValueError(f"实例 {instance_id} 连接不可用")
            
            db = connection.client[database_name]
            collection = db[collection_name]
            
            # 获取样本文档来分析结构
            sample_docs = []
            async for doc in collection.find().limit(5):
                sample_docs.append(doc)
            
            # 分析字段结构
            field_info = {}
            if sample_docs:
                for doc in sample_docs:
                    if isinstance(doc, dict):
                        for field, value in doc.items():
                            if field not in field_info:
                                field_info[field] = {
                                    "name": field,
                                    "types": set(),
                                    "sample_values": []
                                }
                            
                            # 记录字段类型
                            field_info[field]["types"].add(type(value).__name__)
                            
                            # 记录样本值（避免太长）
                            if len(field_info[field]["sample_values"]) < 3:
                                sample_value = str(value)[:50] if len(str(value)) > 50 else str(value)
                                field_info[field]["sample_values"].append(sample_value)
            
            # 转换为列表格式
            fields = []
            for field_name, info in field_info.items():
                fields.append({
                    "name": field_name,
                    "types": list(info["types"]),
                    "sample_values": info["sample_values"]
                })
            
            return {
                "collection_name": collection_name,
                "document_count": await collection.count_documents({}),
                "fields": fields,
                "sample_documents": sample_docs[:2]  # 保留2个样本文档
            }
            
        except Exception as e:
            logger.error("获取集合信息失败", error=str(e))
            raise
    
    async def _analyze_query_semantics(self, instance_id: str, database_name: str, 
                                     collection_name: str, query_description: str) -> Dict[str, Any]:
        """分析查询的语义意图"""
        try:
            # 使用语义分析器分析查询意图
            return await self.semantic_analyzer.analyze_query_intent(
                query_description, instance_id, database_name, collection_name
            )
        except Exception as e:
            logger.warning("语义分析失败，使用基础分析", error=str(e))
            # 基础的关键词分析
            return self._basic_query_analysis(query_description)
    
    def _basic_query_analysis(self, query_description: str) -> Dict[str, Any]:
        """基础查询意图分析"""
        description_lower = query_description.lower()
        
        # 检测查询类型
        if any(keyword in description_lower for keyword in ["count", "数量", "多少", "统计"]):
            operation = "count"
        elif any(keyword in description_lower for keyword in ["distinct", "唯一", "去重", "不同"]):
            operation = "distinct"
        elif any(keyword in description_lower for keyword in ["sum", "average", "max", "min", "group", "聚合", "分组", "求和", "平均"]):
            operation = "aggregate"
        else:
            operation = "find"
        
        # 提取可能的字段名和条件
        potential_fields = []
        conditions = []
        
        # 简单的字段提取（基于常见模式）
        import re
        
        # 查找类似 "field = value" 的模式
        equals_patterns = re.findall(r'(\w+)\s*[=等于是]\s*["\']?([^"\'，,]+)["\']?', description_lower)
        for field, value in equals_patterns:
            potential_fields.append(field)
            conditions.append({"field": field, "operator": "equals", "value": value.strip()})
        
        # 查找类似 "field > value" 的模式
        comparison_patterns = re.findall(r'(\w+)\s*([>大于<小于>=<=])\s*(\d+)', description_lower)
        for field, operator, value in comparison_patterns:
            potential_fields.append(field)
            op_map = {">": "gt", "大于": "gt", "<": "lt", "小于": "lt", ">=": "gte", "<=": "lte"}
            conditions.append({"field": field, "operator": op_map.get(operator, "gt"), "value": int(value)})
        
        return {
            "operation": operation,
            "potential_fields": potential_fields,
            "conditions": conditions,
            "confidence": 0.6  # 基础分析的置信度较低
        }
    
    async def _build_mongodb_query(self, collection_info: Dict[str, Any], semantic_info: Dict[str, Any],
                                 query_description: str, query_type: str, limit: int) -> Dict[str, Any]:
        """构建MongoDB查询语句"""
        operation = semantic_info.get("operation", query_type)
        if operation == "auto":
            operation = "find"
        
        # 构建查询条件
        query_filter = {}
        
        # 根据语义信息构建过滤条件
        conditions = semantic_info.get("conditions", [])
        for condition in conditions:
            field = condition["field"]
            operator = condition["operator"]
            value = condition["value"]
            
            # 验证字段是否存在
            field_names = [f["name"] for f in collection_info.get("fields", [])]
            if field in field_names:
                if operator == "equals":
                    query_filter[field] = value
                elif operator == "gt":
                    query_filter[field] = {"$gt": value}
                elif operator == "lt":
                    query_filter[field] = {"$lt": value}
                elif operator == "gte":
                    query_filter[field] = {"$gte": value}
                elif operator == "lte":
                    query_filter[field] = {"$lte": value}
        
        # 如果没有明确条件，尝试智能匹配
        if not query_filter:
            query_filter = await self._smart_field_matching(collection_info, query_description)
        
        # 构建完整查询
        mongodb_query = {
            "operation": operation,
            "filter": query_filter
        }
        
        if operation == "find":
            mongodb_query["limit"] = limit
            # 选择要返回的字段（限制返回字段以提高性能）
            important_fields = self._select_important_fields(collection_info, semantic_info)
            if important_fields:
                mongodb_query["projection"] = {field: 1 for field in important_fields}
        
        elif operation == "count":
            # count 查询不需要 limit 和 projection
            pass
        
        elif operation == "distinct":
            # 为 distinct 查询选择字段
            distinct_field = self._select_distinct_field(collection_info, semantic_info)
            mongodb_query["field"] = distinct_field
        
        elif operation == "aggregate":
            # 构建聚合管道
            mongodb_query["pipeline"] = self._build_aggregation_pipeline(collection_info, semantic_info, query_description)
        
        return mongodb_query
    
    async def _smart_field_matching(self, collection_info: Dict[str, Any], query_description: str) -> Dict[str, Any]:
        """智能字段匹配"""
        query_filter = {}
        description_lower = query_description.lower()
        
        # 遍历字段，寻找可能的匹配
        for field_info in collection_info.get("fields", []):
            field_name = field_info["name"]
            field_name_lower = field_name.lower()
            
            # 如果查询描述中包含字段名
            if field_name_lower in description_lower:
                # 尝试提取值
                import re
                # 查找字段名后面的值
                pattern = f"{field_name_lower}\\s*[=:是为]\\s*[\"']?([^\"'，,\\s]+)[\"']?"
                match = re.search(pattern, description_lower)
                if match:
                    value = match.group(1)
                    # 尝试转换类型
                    if value.isdigit():
                        query_filter[field_name] = int(value)
                    elif value.replace('.', '').isdigit():
                        query_filter[field_name] = float(value)
                    else:
                        query_filter[field_name] = value
        
        return query_filter
    
    def _select_important_fields(self, collection_info: Dict[str, Any], semantic_info: Dict[str, Any]) -> List[str]:
        """选择重要字段"""
        all_fields = [f["name"] for f in collection_info.get("fields", [])]
        
        # 优先选择语义分析中涉及的字段
        important_fields = semantic_info.get("potential_fields", [])
        
        # 添加一些常见的重要字段
        common_important = ["_id", "id", "name", "title", "status", "created_at", "updated_at"]
        for field in all_fields:
            if field.lower() in [f.lower() for f in common_important]:
                if field not in important_fields:
                    important_fields.append(field)
        
        # 限制字段数量，避免返回过多数据
        return important_fields[:10]
    
    def _select_distinct_field(self, collection_info: Dict[str, Any], semantic_info: Dict[str, Any]) -> str:
        """选择distinct查询的字段"""
        potential_fields = semantic_info.get("potential_fields", [])
        if potential_fields:
            return potential_fields[0]
        
        # 默认选择第一个非_id字段
        for field_info in collection_info.get("fields", []):
            if field_info["name"] != "_id":
                return field_info["name"]
        
        return "_id"
    
    def _build_aggregation_pipeline(self, collection_info: Dict[str, Any], 
                                  semantic_info: Dict[str, Any], query_description: str) -> List[Dict[str, Any]]:
        """构建聚合管道"""
        pipeline = []
        
        # 基础的聚合管道
        description_lower = query_description.lower()
        
        if "group" in description_lower or "分组" in description_lower:
            # 添加分组阶段
            group_stage = {"$group": {"_id": None, "count": {"$sum": 1}}}
            pipeline.append(group_stage)
        
        if "sum" in description_lower or "求和" in description_lower:
            # 查找数值字段进行求和
            numeric_fields = []
            for field_info in collection_info.get("fields", []):
                if any(t in ["int", "float", "Decimal128"] for t in field_info.get("types", [])):
                    numeric_fields.append(field_info["name"])
            
            if numeric_fields:
                group_stage = {
                    "$group": {
                        "_id": None,
                        "total": {"$sum": f"${numeric_fields[0]}"}
                    }
                }
                pipeline.append(group_stage)
        
        # 如果没有特殊聚合，返回基础统计
        if not pipeline:
            pipeline = [
                {"$group": {"_id": None, "count": {"$sum": 1}}},
                {"$project": {"_id": 0, "total_documents": "$count"}}
            ]
        
        return pipeline
    
    async def _estimate_result_count(self, instance_id: str, database_name: str, 
                                   collection_name: str, mongodb_query: Dict[str, Any]) -> int:
        """估算查询结果数量"""
        try:
            connection = self.connection_manager.get_instance_connection(instance_id)
            if not connection or not connection.client:
                return -1
            
            db = connection.client[database_name]
            collection = db[collection_name]
            
            # 对于简单查询，直接统计
            if mongodb_query.get("operation") == "count":
                return await collection.count_documents(mongodb_query.get("filter", {}))
            elif mongodb_query.get("operation") == "find":
                # 限制统计时间，如果超过1000条就返回估算值
                filter_query = mongodb_query.get("filter", {})
                if not filter_query:
                    # 无过滤条件，返回总文档数
                    return await collection.count_documents({})
                else:
                    # 有过滤条件，统计匹配数量
                    return await collection.count_documents(filter_query)
            else:
                # 其他类型查询，返回未知
                return -1
                
        except Exception as e:
            logger.warning("估算结果数量失败", error=str(e))
            return -1
    
    async def _show_query_only(self, query_info: Dict[str, Any]) -> List[TextContent]:
        """仅显示生成的查询语句"""
        text = f"## 🔍 生成的MongoDB查询语句\n\n"
        text += f"**查询描述**: {query_info['query_description']}\n"
        text += f"**目标集合**: `{query_info['instance_id']}.{query_info['database_name']}.{query_info['collection_name']}`\n"
        text += f"**查询类型**: {query_info['query_type']}\n\n"
        
        text += "### 📄 MongoDB查询语句\n\n"
        text += "```javascript\n"
        
        # 格式化显示查询语句
        mongodb_query = query_info["mongodb_query"]
        operation = mongodb_query.get("operation", "find")
        
        if operation == "find":
            filter_part = mongodb_query.get("filter", {})
            projection_part = mongodb_query.get("projection", {})
            limit_part = mongodb_query.get("limit", 10)
            
            text += f"db.{query_info['collection_name']}.find("
            if filter_part:
                import json
                text += json.dumps(filter_part, indent=2, ensure_ascii=False)
            else:
                text += "{}"
            
            if projection_part:
                text += ",\n  "
                text += json.dumps(projection_part, indent=2, ensure_ascii=False)
            
            text += f").limit({limit_part})"
            
        elif operation == "count":
            filter_part = mongodb_query.get("filter", {})
            text += f"db.{query_info['collection_name']}.countDocuments("
            if filter_part:
                import json
                text += json.dumps(filter_part, indent=2, ensure_ascii=False)
            else:
                text += "{}"
            text += ")"
            
        elif operation == "distinct":
            field = mongodb_query.get("field", "_id")
            filter_part = mongodb_query.get("filter", {})
            text += f'db.{query_info["collection_name"]}.distinct("{field}"'
            if filter_part:
                text += ", "
                import json
                text += json.dumps(filter_part, indent=2, ensure_ascii=False)
            text += ")"
            
        elif operation == "aggregate":
            pipeline = mongodb_query.get("pipeline", [])
            text += f"db.{query_info['collection_name']}.aggregate("
            import json
            text += json.dumps(pipeline, indent=2, ensure_ascii=False)
            text += ")"
        
        text += "\n```\n\n"
        
        # 显示预期结果
        if query_info.get("estimated_result_count", -1) >= 0:
            text += f"**预期结果数量**: 约 {query_info['estimated_result_count']} 条\n"
        
        text += f"**结果限制**: 最多返回 {query_info.get('limit', 10)} 条\n\n"
        text += "💡 **提示**: 使用 `generate_query()` 并提供 `user_confirmation` 参数来执行查询"
        
        return [TextContent(type="text", text=text)]
    
    async def _show_confirmation_prompt(self, query_info: Dict[str, Any]) -> List[TextContent]:
        """显示确认提示"""
        return [UserConfirmationHelper.create_query_confirmation_prompt(query_info)]
    
    async def _handle_user_confirmation(self, user_confirmation: str, 
                                      query_info: Dict[str, Any], session_id: str) -> List[TextContent]:
        """处理用户确认"""
        choice_upper = user_confirmation.upper()
        
        if choice_upper in ['A', 'CONFIRM', 'EXECUTE']:
            # 确认执行查询
            return await self._execute_query(query_info, session_id)
            
        elif choice_upper in ['B', 'MODIFY', 'REGENERATE']:
            # 重新生成查询
            return [TextContent(
                type="text",
                text="## 🔧 重新生成查询\n\n请使用不同的查询描述重新调用 `generate_query(query_description=\"新的查询描述\")`"
            )]
            
        elif choice_upper in ['C', 'PLAN', 'EXPLAIN']:
            # 查看执行计划
            return await self._show_execution_plan(query_info)
            
        elif choice_upper in ['D', 'CANCEL']:
            # 取消执行
            return [TextContent(
                type="text",
                text="## ❌ 已取消查询执行"
            )]
        else:
            # 无效选择
            return [TextContent(
                type="text",
                text=f"## ❌ 无效选择\n\n选择 '{user_confirmation}' 无效。请选择 A（执行）、B（修改）、C（查看计划）或 D（取消）。"
            )]
    
    async def _execute_query(self, query_info: Dict[str, Any], session_id: str) -> List[TextContent]:
        """执行查询"""
        logger.info("执行确认的查询", 
                   instance_id=query_info["instance_id"],
                   database_name=query_info["database_name"],
                   collection_name=query_info["collection_name"])
        
        try:
            # 更新工作流状态
            update_data = {
                "instance_id": query_info["instance_id"],
                "database_name": query_info["database_name"],
                "collection_name": query_info["collection_name"],
                "generated_query": query_info["mongodb_query"]
            }
            
            await self.workflow_manager.update_workflow_data(session_id, update_data)
            
            # 执行查询
            results = await self._run_mongodb_query(query_info)
            
            # 格式化结果
            return await self._format_query_results(query_info, results)
            
        except Exception as e:
            logger.error("查询执行失败", error=str(e))
            return [TextContent(
                type="text",
                text=f"## ❌ 查询执行失败\n\n错误: {str(e)}\n\n请检查查询语句或数据库连接。"
            )]
    
    async def _run_mongodb_query(self, query_info: Dict[str, Any]) -> Any:
        """运行MongoDB查询"""
        connection = self.connection_manager.get_instance_connection(query_info["instance_id"])
        if not connection or not connection.client:
            raise ValueError("数据库连接不可用")
        
        db = connection.client[query_info["database_name"]]
        collection = db[query_info["collection_name"]]
        mongodb_query = query_info["mongodb_query"]
        operation = mongodb_query.get("operation", "find")
        
        if operation == "find":
            filter_query = mongodb_query.get("filter", {})
            projection = mongodb_query.get("projection", {})
            limit = mongodb_query.get("limit", 10)
            
            cursor = collection.find(filter_query, projection).limit(limit)
            results = []
            async for doc in cursor:
                results.append(doc)
            return results
            
        elif operation == "count":
            filter_query = mongodb_query.get("filter", {})
            return await collection.count_documents(filter_query)
            
        elif operation == "distinct":
            field = mongodb_query.get("field", "_id")
            filter_query = mongodb_query.get("filter", {})
            return await collection.distinct(field, filter_query)
            
        elif operation == "aggregate":
            pipeline = mongodb_query.get("pipeline", [])
            cursor = collection.aggregate(pipeline)
            results = []
            async for doc in cursor:
                results.append(doc)
            return results
        
        else:
            raise ValueError(f"不支持的查询操作: {operation}")
    
    async def _format_query_results(self, query_info: Dict[str, Any], results: Any) -> List[TextContent]:
        """格式化查询结果"""
        operation = query_info["mongodb_query"].get("operation", "find")
        
        text = f"## ✅ 查询执行成功\n\n"
        text += f"**查询描述**: {query_info['query_description']}\n"
        text += f"**目标集合**: `{query_info['collection_name']}`\n"
        text += f"**查询类型**: {operation}\n\n"
        
        if operation == "count":
            text += f"### 📊 统计结果\n\n"
            text += f"**文档数量**: {results}\n"
            
        elif operation == "distinct":
            text += f"### 📋 唯一值列表\n\n"
            if isinstance(results, list):
                for i, value in enumerate(results[:20], 1):  # 最多显示20个
                    text += f"{i}. {value}\n"
                if len(results) > 20:
                    text += f"... 还有 {len(results) - 20} 个值\n"
                text += f"\n**总计**: {len(results)} 个唯一值\n"
            else:
                text += f"结果: {results}\n"
                
        elif operation in ["find", "aggregate"]:
            text += f"### 📄 查询结果\n\n"
            if isinstance(results, list):
                text += f"**返回记录数**: {len(results)}\n\n"
                
                for i, doc in enumerate(results[:5], 1):  # 最多显示5条记录
                    text += f"#### 记录 {i}\n"
                    text += "```json\n"
                    import json
                    text += json.dumps(doc, indent=2, ensure_ascii=False, default=str)
                    text += "\n```\n\n"
                
                if len(results) > 5:
                    text += f"*... 还有 {len(results) - 5} 条记录*\n\n"
            else:
                text += f"结果: {results}\n"
        
        # 添加下一步建议
        text += "## 🎯 下一步操作\n\n"
        text += "可以继续以下操作：\n"
        text += "- `generate_query(query_description=\"新的查询需求\")` - 生成新查询\n"
        text += "- `workflow_status()` - 查看工作流状态\n"
        text += "- 分析查询结果，根据需要调整查询条件\n"
        
        return [TextContent(type="text", text=text)]
    
    async def _show_execution_plan(self, query_info: Dict[str, Any]) -> List[TextContent]:
        """显示执行计划"""
        try:
            connection = self.connection_manager.get_instance_connection(query_info["instance_id"])
            if not connection or not connection.client:
                raise ValueError("数据库连接不可用")
            
            db = connection.client[query_info["database_name"]]
            collection = db[query_info["collection_name"]]
            mongodb_query = query_info["mongodb_query"]
            
            # 获取执行计划
            if mongodb_query.get("operation") == "find":
                filter_query = mongodb_query.get("filter", {})
                explain_result = await collection.find(filter_query).explain()
            else:
                explain_result = {"message": "只有find查询支持执行计划分析"}
            
            text = f"## 📊 查询执行计划\n\n"
            text += f"**查询类型**: {mongodb_query.get('operation', 'find')}\n"
            text += f"**集合**: `{query_info['collection_name']}`\n\n"
            
            text += "### 📄 执行计划详情\n\n"
            text += "```json\n"
            import json
            text += json.dumps(explain_result, indent=2, ensure_ascii=False, default=str)
            text += "\n```\n\n"
            
            text += "### 📋 确认选项\n\n"
            text += "查看执行计划后，请选择下一步操作：\n"
            text += "- `generate_query(..., user_confirmation=\"A\")` - 确认执行查询\n"
            text += "- `generate_query(..., user_confirmation=\"B\")` - 修改查询\n"
            text += "- `generate_query(..., user_confirmation=\"D\")` - 取消查询\n"
            
            return [TextContent(type="text", text=text)]
            
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"## ❌ 获取执行计划失败\n\n错误: {str(e)}"
            )]