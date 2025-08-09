# -*- coding: utf-8 -*-
"""查询生成工具"""

from typing import Dict, List, Any, Optional, Union
import re
import json
from datetime import datetime, timedelta
import structlog
from mcp.types import Tool, TextContent

from database.connection_manager import ConnectionManager
from database.metadata_manager import MetadataManager
from scanner.semantic_analyzer import SemanticAnalyzer
from mcp_tools.unified_semantic_tool import UnifiedSemanticTool
from utils.parameter_validator import (
    ParameterValidator, MCPParameterHelper, ValidationResult,
    is_non_empty_string, is_positive_integer, is_boolean, 
    is_valid_instance_id, is_valid_database_name, is_valid_collection_name,
    validate_instance_exists, validate_database_exists, validate_collection_exists
)
from utils.tool_context import get_context_manager, ToolExecutionContext
from utils.error_handler import with_error_handling, with_retry, RetryConfig


logger = structlog.get_logger(__name__)


class QueryGenerationTool:
    """查询生成工具"""
    
    def __init__(self, connection_manager: ConnectionManager, 
                 metadata_manager: MetadataManager,
                 semantic_analyzer: SemanticAnalyzer):
        self.connection_manager = connection_manager
        self.metadata_manager = metadata_manager
        self.semantic_analyzer = semantic_analyzer
        self.unified_semantic = UnifiedSemanticTool(
            connection_manager, metadata_manager, semantic_analyzer
        )
        self.context_manager = get_context_manager()
        self.validator = self._setup_validator()
        
        # 查询模式映射
        self.query_patterns = {
            # 查找模式
            r'查找|找到|获取|搜索|查询': 'find',
            r'统计|计数|数量|多少': 'count',
            r'聚合|分组|汇总|统计分析': 'aggregate',
            r'去重|唯一|不重复': 'distinct',
            
            # 条件模式
            r'等于|是|为': '$eq',
            r'不等于|不是|不为': '$ne',
            r'大于': '$gt',
            r'大于等于|不小于': '$gte',
            r'小于': '$lt',
            r'小于等于|不大于': '$lte',
            r'包含|含有': '$regex',
            r'在.*之间|范围': '$range',
            r'存在|有': '$exists',
            r'不存在|没有': '$not_exists',
            r'为空|空值': '$null',
            r'不为空|非空': '$not_null',
        }
        
        # 时间关键词
        self.time_keywords = {
            r'今天|当天': 0,
            r'昨天': -1,
            r'前天': -2,
            r'明天': 1,
            r'后天': 2,
            r'本周|这周': 'this_week',
            r'上周|上一周': 'last_week',
            r'本月|这个月': 'this_month',
            r'上月|上个月': 'last_month',
            r'今年|本年': 'this_year',
            r'去年|上年': 'last_year',
        }
    
    def get_tool_definition(self) -> Tool:
        """获取工具定义"""
        return Tool(
            name="generate_query",
            description="根据自然语言描述生成MongoDB查询语句",
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
                    "query_description": {
                        "type": "string",
                        "description": "查询的自然语言描述"
                    },
                    "query_type": {
                        "type": "string",
                        "enum": ["auto", "find", "count", "aggregate", "distinct"],
                        "description": "查询类型，auto表示自动识别",
                        "default": "auto"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "结果限制数量",
                        "default": 100,
                        "minimum": 1,
                        "maximum": 1000
                    },
                    "include_explanation": {
                        "type": "boolean",
                        "description": "是否包含查询解释",
                        "default": True
                    },
                    "output_format": {
                        "type": "string",
                        "enum": ["full", "query_only", "executable"],
                        "description": "输出格式：full=完整解释，query_only=仅查询语句，executable=可直接执行的语句",
                        "default": "full"
                    }
                },
                "required": ["instance_id", "database_name", "collection_name", "query_description"]
            }
        )
    
    def _setup_validator(self) -> ParameterValidator:
        """设置参数验证器"""
        validator = ParameterValidator()
        
        async def get_instance_options():
            """获取可用实例选项"""
            try:
                instances = await self.connection_manager.get_all_instances()
                return [{'value': instance_id, 'display_name': instance_id, 
                        'description': instance_config.description or '无描述'} 
                       for instance_id, instance_config in instances.items()]
            except Exception:
                return []
        
        async def get_database_options(context):
            """获取可用数据库选项"""
            try:
                if not context or not context.instance_id:
                    return []
                
                connection = self.connection_manager.get_instance_connection(context.instance_id)
                if not connection:
                    return []
                
                db_names = await connection.client.list_database_names()
                # 过滤系统数据库
                system_dbs = {'admin', 'local', 'config'}
                user_dbs = [name for name in db_names if name not in system_dbs]
                
                return [{'value': db_name, 'display_name': db_name,
                        'description': f'数据库: {db_name}'} for db_name in user_dbs]
            except Exception:
                return []
        
        async def get_collection_options(context):
            """获取可用集合选项"""
            try:
                if not context or not context.instance_id or not context.database_name:
                    return []
                
                connection = self.connection_manager.get_instance_connection(context.instance_id)
                if not connection:
                    return []
                
                db = connection.client[context.database_name]
                collection_names = await db.list_collection_names()
                
                return [{'value': coll_name, 'display_name': coll_name,
                        'description': f'集合: {coll_name}'} for coll_name in collection_names]
            except Exception:
                return []
        
        # 设置验证规则
        validator.add_required_parameter(
            name="instance_id",
            type_check=lambda x: is_non_empty_string(x) and is_valid_instance_id(x),
            validator=lambda x, ctx: validate_instance_exists(x, ctx.connection_manager),
            options_provider=get_instance_options,
            description="MongoDB实例名称（注意：参数名为instance_id但实际使用实例名称）",
            user_friendly_name="MongoDB实例"
        )
        
        validator.add_required_parameter(
            name="database_name",
            type_check=lambda x: is_non_empty_string(x) and is_valid_database_name(x),
            validator=validate_database_exists,
            options_provider=get_database_options,
            description="数据库名称",
            user_friendly_name="数据库"
        )
        
        validator.add_required_parameter(
            name="collection_name",
            type_check=lambda x: is_non_empty_string(x) and is_valid_collection_name(x),
            validator=validate_collection_exists,
            options_provider=get_collection_options,
            description="集合名称",
            user_friendly_name="集合"
        )
        
        validator.add_required_parameter(
            name="query_description",
            type_check=is_non_empty_string,
            description="查询的自然语言描述，例如：'查找所有状态为激活的用户'",
            user_friendly_name="查询描述"
        )
        
        validator.add_optional_parameter(
            name="query_type",
            type_check=lambda x: x in ["auto", "find", "count", "aggregate", "distinct"],
            description="查询类型，auto表示自动识别",
            user_friendly_name="查询类型"
        )
        
        validator.add_optional_parameter(
            name="limit",
            type_check=lambda x: is_positive_integer(x) and 1 <= x <= 1000,
            description="结果限制数量，范围1-1000",
            user_friendly_name="结果数量限制"
        )
        
        validator.add_optional_parameter(
            name="include_explanation",
            type_check=is_boolean,
            description="是否包含查询解释",
            user_friendly_name="包含解释"
        )
        
        validator.add_optional_parameter(
            name="output_format",
            type_check=lambda x: x in ["full", "query_only", "executable"],
            description="输出格式选择",
            user_friendly_name="输出格式"
        )
        
        return validator

    @with_error_handling({"component": "query_generation", "operation": "execute"})
    @with_retry(RetryConfig(max_attempts=2, base_delay=1.0))
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """执行查询生成"""
        # 参数验证和智能补全
        context = self.context_manager.get_or_create_context()
        context.connection_manager = self.connection_manager
        
        # 尝试从上下文推断缺失参数
        inferred_params = context.infer_missing_parameters()
        for param_name in ["instance_id", "database_name", "collection_name"]:
            if not arguments.get(param_name) and inferred_params.get(param_name):
                arguments[param_name] = inferred_params[param_name]
                logger.info(f"从上下文推断{param_name}", value=arguments[param_name])
        
        # 更新上下文以支持数据库和集合选项的获取
        if arguments.get("instance_id"):
            context = context.clone_with_updates(instance_id=arguments["instance_id"])
        if arguments.get("database_name"):
            context = context.clone_with_updates(database_name=arguments["database_name"])
        
        validation_result, errors = await self.validator.validate_parameters(arguments, context)
        
        if validation_result != ValidationResult.VALID:
            return MCPParameterHelper.create_error_response(errors)
        
        # 记录工具调用到上下文并更新上下文
        context.add_to_chain("generate_query", arguments)
        self.context_manager.update_context(
            instance_id=arguments["instance_id"],
            database_name=arguments["database_name"],
            collection_name=arguments["collection_name"]
        )
        
        instance_id = arguments["instance_id"]
        database_name = arguments["database_name"]
        collection_name = arguments["collection_name"]
        query_description = arguments["query_description"]
        query_type = arguments.get("query_type", "auto")
        limit = arguments.get("limit", 100)
        include_explanation = arguments.get("include_explanation", True)
        output_format = arguments.get("output_format", "full")
        
        logger.info(
            "开始生成查询",
            instance_id=instance_id,
            database=database_name,
            collection=collection_name,
            description=query_description
        )
        
        try:
            # 验证实例和集合
            validation_result = await self._validate_target(instance_id, database_name, collection_name)
            if validation_result:
                return [TextContent(type="text", text=validation_result)]
            
            # 获取集合字段信息
            fields = await self.metadata_manager.get_fields_by_collection(
                instance_id, instance_id, database_name, collection_name
            )
            
            if not fields:
                return [TextContent(
                    type="text",
                    text=f"集合 '{database_name}.{collection_name}' 没有字段信息。请先使用 analyze_collection 工具扫描集合结构。"
                )]
            
            # 分析查询描述
            query_analysis = await self._analyze_query_description(
                query_description, fields, query_type
            )
            
            # 生成查询
            query_result = await self._generate_query(
                query_analysis, fields, limit
            )
            
            if "error" in query_result:
                return [TextContent(type="text", text=f"生成查询失败: {query_result['error']}")]
            
            # 构建结果
            result_text = await self._build_query_result(
                query_result, query_description, instance_id, database_name, 
                collection_name, include_explanation, query_analysis, output_format
            )
            
            # 保存查询历史
            await self._save_query_history(
                instance_id, database_name, collection_name,
                query_description, query_result
            )
            
            logger.info(
                "查询生成完成",
                instance_id=instance_id,
                database=database_name,
                collection=collection_name,
                query_type=query_result.get("query_type")
            )
            
            return [TextContent(type="text", text=result_text)]
            
        except Exception as e:
            error_msg = f"生成查询时发生错误: {str(e)}"
            logger.error(
                "查询生成失败",
                instance_id=instance_id,
                database=database_name,
                collection=collection_name,
                error=str(e)
            )
            return [TextContent(type="text", text=error_msg)]
    
    @with_error_handling({"component": "query_generation", "operation": "validate_target"})
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
    
    @with_error_handling({"component": "query_generation", "operation": "analyze_query"})
    async def _analyze_query_description(self, description: str, fields: List[Dict[str, Any]], 
                                       query_type: str) -> Dict[str, Any]:
        """分析查询描述"""
        analysis = {
            "query_type": query_type,
            "conditions": [],
            "projections": [],
            "sort_fields": [],
            "group_fields": [],
            "time_filters": [],
            "text_searches": [],
            "numeric_ranges": []
        }
        
        description_lower = description.lower()
        
        # 自动识别查询类型
        if query_type == "auto":
            analysis["query_type"] = self._detect_query_type(description_lower)
        
        # 获取字段建议
        field_suggestions = self.semantic_analyzer.get_semantic_suggestions_for_query(
            description, fields
        )
        
        # 检查是否有未知字段需要语义补全
        unknown_fields = self._detect_unknown_fields(description, field_suggestions)
        if unknown_fields:
            # 尝试语义补全
            completion_result = await self._try_semantic_completion(
                description, unknown_fields, fields
            )
            if completion_result.get("suggestions"):
                # 合并补全建议到字段建议中
                field_suggestions.extend(completion_result["suggestions"])
                analysis["semantic_completion"] = completion_result
        
        # 分析条件
        analysis["conditions"] = self._extract_conditions(
            description, field_suggestions
        )
        
        # 分析时间过滤
        analysis["time_filters"] = self._extract_time_filters(
            description, field_suggestions
        )
        
        # 分析文本搜索
        analysis["text_searches"] = self._extract_text_searches(
            description, field_suggestions
        )
        
        # 分析数值范围
        analysis["numeric_ranges"] = self._extract_numeric_ranges(
            description, field_suggestions
        )
        
        # 分析排序
        analysis["sort_fields"] = self._extract_sort_fields(
            description, field_suggestions
        )
        
        # 分析分组（用于聚合查询）
        if analysis["query_type"] == "aggregate":
            analysis["group_fields"] = self._extract_group_fields(
                description, field_suggestions
            )
        
        return analysis
    
    def _detect_unknown_fields(self, description: str, field_suggestions: List[Dict[str, Any]]) -> List[str]:
        """检测查询描述中的未知字段"""
        import jieba
        
        # 分词提取可能的字段名
        words = list(jieba.cut(description))
        
        # 过滤出可能是字段名的词汇
        potential_fields = []
        for word in words:
            if len(word) > 1 and word.isalnum():
                potential_fields.append(word)
        
        # 检查哪些字段在现有建议中找不到
        existing_fields = {suggestion.get("field_path", "").lower() 
                          for suggestion in field_suggestions}
        
        unknown_fields = []
        for field in potential_fields:
            if field.lower() not in existing_fields:
                # 进一步检查是否真的像字段名
                if self._looks_like_field_name(field):
                    unknown_fields.append(field)
        
        return unknown_fields
    
    def _looks_like_field_name(self, word: str) -> bool:
        """判断词汇是否像字段名"""
        # 简单的启发式规则
        if len(word) < 2:
            return False
        
        # 包含常见字段关键词
        field_keywords = ["名称", "姓名", "时间", "日期", "状态", "类型", "编号", "ID", "id", 
                         "name", "time", "date", "status", "type", "code", "number"]
        
        for keyword in field_keywords:
            if keyword in word:
                return True
        
        # 或者是英文字段名模式
        if word.replace("_", "").isalnum() and any(c.islower() for c in word):
            return True
            
        return False
    
    async def _try_semantic_completion(self, description: str, unknown_fields: List[str], 
                                     fields: List[Dict[str, Any]]) -> Dict[str, Any]:
        """尝试语义补全"""
        try:
            # 调用统一语义工具进行语义建议
            completion_args = {
                "action": "suggest_semantics",
                "instance_name": "default",  # 使用默认实例
                "query_description": description,
                "unknown_fields": unknown_fields,
                "available_fields": [field.get("field_path", "") for field in fields],
                "field_types": {field.get("field_path", ""): field.get("field_type", "string") 
                               for field in fields}
            }
            
            result = await self.unified_semantic.execute(completion_args)
            
            # 解析结果
            if result and len(result) > 0:
                content = result[0].text if hasattr(result[0], 'text') else str(result[0])
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    return {"suggestions": [], "message": content}
            
            return {"suggestions": []}
            
        except Exception as e:
            logger.warning("语义补全失败", error=str(e))
            return {"suggestions": [], "error": str(e)}
        
    def _detect_query_type(self, description: str) -> str:
        """检测查询类型"""
        for pattern, query_type in self.query_patterns.items():
            if re.search(pattern, description):
                if query_type in ['find', 'count', 'aggregate', 'distinct']:
                    return query_type
        
        # 默认为查找
        return 'find'
    
    def _extract_conditions(self, description: str, field_suggestions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """提取查询条件"""
        conditions = []
        
        # 简单的条件提取逻辑
        for field_info in field_suggestions[:5]:  # 只考虑前5个最相关的字段
            field_path = field_info["field_path"]
            business_meaning = field_info.get("business_meaning", "")
            
            # 检查是否在描述中提到了这个字段
            field_mentioned = False
            for word in [field_path.lower(), business_meaning.lower()]:
                if word and word in description.lower():
                    field_mentioned = True
                    break
            
            if field_mentioned:
                # 尝试提取条件操作符和值
                condition = self._extract_field_condition(description, field_path, field_info)
                if condition:
                    conditions.append(condition)
        
        return conditions
    
    def _extract_field_condition(self, description: str, field_path: str, 
                               field_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """提取特定字段的条件"""
        field_type = field_info.get("field_type", "string")
        
        # 查找操作符
        operator = "$eq"  # 默认等于
        
        for pattern, op in self.query_patterns.items():
            if op.startswith("$") and re.search(pattern, description):
                operator = op
                break
        
        # 尝试提取值
        value = self._extract_field_value(description, field_path, field_type)
        
        if value is not None:
            condition = {
                "field": field_path,
                "operator": operator,
                "value": value,
                "field_type": field_type
            }
            
            # 处理特殊操作符
            if operator == "$range":
                # 范围查询需要两个值
                range_values = self._extract_range_values(description, field_type)
                if range_values:
                    condition["value"] = range_values
            elif operator == "$regex":
                # 正则表达式查询
                condition["value"] = {"$regex": str(value), "$options": "i"}
            elif operator in ["$exists", "$not_exists"]:
                condition["value"] = operator == "$exists"
                condition["operator"] = "$exists"
            elif operator in ["$null", "$not_null"]:
                if operator == "$null":
                    condition["operator"] = "$eq"
                    condition["value"] = None
                else:
                    condition["operator"] = "$ne"
                    condition["value"] = None
            
            return condition
        
        return None
    
    def _extract_field_value(self, description: str, field_path: str, field_type: str) -> Any:
        """提取字段值"""
        # 这里实现简单的值提取逻辑
        # 在实际应用中，可能需要更复杂的NLP处理
        
        # 提取数字
        if field_type in ["integer", "double", "long"]:
            numbers = re.findall(r'\d+(?:\.\d+)?', description)
            if numbers:
                try:
                    if field_type == "integer":
                        return int(float(numbers[0]))
                    else:
                        return float(numbers[0])
                except ValueError:
                    pass
        
        # 提取布尔值
        if field_type == "boolean":
            if re.search(r'真|是|true|yes|1', description.lower()):
                return True
            elif re.search(r'假|否|false|no|0', description.lower()):
                return False
        
        # 提取字符串（简单实现）
        # 查找引号中的内容
        quoted_strings = re.findall(r'["\']([^"\'\']+)["\']', description)
        if quoted_strings:
            return quoted_strings[0]
        
        # 查找可能的字符串值
        words = description.split()
        for i, word in enumerate(words):
            if field_path.lower() in word.lower() and i + 1 < len(words):
                next_word = words[i + 1]
                # 简单的值提取
                if not re.match(r'^(是|为|等于|大于|小于|包含)$', next_word):
                    return next_word
        
        return None
    
    def _extract_range_values(self, description: str, field_type: str) -> Optional[List[Any]]:
        """提取范围值"""
        # 查找 "X 到 Y" 或 "X - Y" 模式
        range_patterns = [
            r'(\d+(?:\.\d+)?)\s*到\s*(\d+(?:\.\d+)?)',
            r'(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)',
            r'(\d+(?:\.\d+)?)\s*至\s*(\d+(?:\.\d+)?)',
        ]
        
        for pattern in range_patterns:
            match = re.search(pattern, description)
            if match:
                try:
                    start_val = float(match.group(1))
                    end_val = float(match.group(2))
                    
                    if field_type == "integer":
                        return [int(start_val), int(end_val)]
                    else:
                        return [start_val, end_val]
                except ValueError:
                    continue
        
        return None
    
    def _extract_time_filters(self, description: str, field_suggestions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """提取时间过滤条件"""
        time_filters = []
        
        # 查找时间字段
        time_fields = [f for f in field_suggestions if 'time' in f["field_path"].lower() or 
                      'date' in f["field_path"].lower() or f.get("field_type") == "date"]
        
        if not time_fields:
            return time_filters
        
        # 查找时间关键词
        for pattern, time_value in self.time_keywords.items():
            if re.search(pattern, description):
                for time_field in time_fields:
                    time_range = self._calculate_time_range(time_value)
                    if time_range:
                        time_filters.append({
                            "field": time_field["field_path"],
                            "operator": "$gte",
                            "value": time_range["start"]
                        })
                        time_filters.append({
                            "field": time_field["field_path"],
                            "operator": "$lt",
                            "value": time_range["end"]
                        })
                break
        
        return time_filters
    
    def _calculate_time_range(self, time_value: Union[int, str]) -> Optional[Dict[str, datetime]]:
        """计算时间范围"""
        now = datetime.now()
        
        if isinstance(time_value, int):
            # 相对天数
            target_date = now + timedelta(days=time_value)
            return {
                "start": target_date.replace(hour=0, minute=0, second=0, microsecond=0),
                "end": target_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            }
        elif time_value == "this_week":
            # 本周
            start_of_week = now - timedelta(days=now.weekday())
            end_of_week = start_of_week + timedelta(days=6)
            return {
                "start": start_of_week.replace(hour=0, minute=0, second=0, microsecond=0),
                "end": end_of_week.replace(hour=23, minute=59, second=59, microsecond=999999)
            }
        elif time_value == "this_month":
            # 本月
            start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if now.month == 12:
                end_of_month = start_of_month.replace(year=now.year + 1, month=1) - timedelta(days=1)
            else:
                end_of_month = start_of_month.replace(month=now.month + 1) - timedelta(days=1)
            return {
                "start": start_of_month,
                "end": end_of_month.replace(hour=23, minute=59, second=59, microsecond=999999)
            }
        
        return None
    
    def _extract_text_searches(self, description: str, field_suggestions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """提取文本搜索条件"""
        text_searches = []
        
        # 查找文本字段
        text_fields = [f for f in field_suggestions if f.get("field_type") == "string"]
        
        # 查找包含关键词
        if re.search(r'包含|含有', description):
            # 提取要搜索的文本
            search_terms = re.findall(r'包含["\']([^"\'\']+)["\']', description)
            if not search_terms:
                search_terms = re.findall(r'含有["\']([^"\'\']+)["\']', description)
            
            for term in search_terms:
                for field in text_fields[:3]:  # 限制字段数量
                    text_searches.append({
                        "field": field["field_path"],
                        "operator": "$regex",
                        "value": {"$regex": term, "$options": "i"}
                    })
        
        return text_searches
    
    def _extract_numeric_ranges(self, description: str, field_suggestions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """提取数值范围条件"""
        numeric_ranges = []
        
        # 查找数值字段
        numeric_fields = [f for f in field_suggestions if 
                         f.get("field_type") in ["integer", "double", "long"]]
        
        # 查找范围表达式
        range_patterns = [
            r'(\w+)\s*在\s*(\d+(?:\.\d+)?)\s*到\s*(\d+(?:\.\d+)?)\s*之间',
            r'(\w+)\s*范围\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)',
        ]
        
        for pattern in range_patterns:
            matches = re.finditer(pattern, description)
            for match in matches:
                field_name = match.group(1)
                start_val = float(match.group(2))
                end_val = float(match.group(3))
                
                # 查找匹配的字段
                for field in numeric_fields:
                    if (field_name.lower() in field["field_path"].lower() or 
                        field_name.lower() in field.get("business_meaning", "").lower()):
                        
                        field_type = field.get("field_type")
                        if field_type == "integer":
                            start_val = int(start_val)
                            end_val = int(end_val)
                        
                        numeric_ranges.extend([
                            {
                                "field": field["field_path"],
                                "operator": "$gte",
                                "value": start_val
                            },
                            {
                                "field": field["field_path"],
                                "operator": "$lte",
                                "value": end_val
                            }
                        ])
                        break
        
        return numeric_ranges
    
    def _extract_sort_fields(self, description: str, field_suggestions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """提取排序字段"""
        sort_fields = []
        
        # 查找排序关键词
        sort_patterns = [
            (r'按\s*(\w+)\s*升序|按\s*(\w+)\s*正序', 1),
            (r'按\s*(\w+)\s*降序|按\s*(\w+)\s*倒序', -1),
            (r'(\w+)\s*从小到大', 1),
            (r'(\w+)\s*从大到小', -1),
        ]
        
        for pattern, direction in sort_patterns:
            matches = re.finditer(pattern, description)
            for match in matches:
                field_name = match.group(1) or match.group(2)
                if field_name:
                    # 查找匹配的字段
                    for field in field_suggestions:
                        if (field_name.lower() in field["field_path"].lower() or 
                            field_name.lower() in field.get("business_meaning", "").lower()):
                            sort_fields.append({
                                "field": field["field_path"],
                                "direction": direction
                            })
                            break
        
        return sort_fields
    
    def _extract_group_fields(self, description: str, field_suggestions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """提取分组字段"""
        group_fields = []
        
        # 查找分组关键词
        group_patterns = [
            r'按\s*(\w+)\s*分组',
            r'根据\s*(\w+)\s*分组',
            r'以\s*(\w+)\s*为组',
        ]
        
        for pattern in group_patterns:
            matches = re.finditer(pattern, description)
            for match in matches:
                field_name = match.group(1)
                # 查找匹配的字段
                for field in field_suggestions:
                    if (field_name.lower() in field["field_path"].lower() or 
                        field_name.lower() in field.get("business_meaning", "").lower()):
                        group_fields.append({
                            "field": field["field_path"]
                        })
                        break
        
        return group_fields
    
    @with_error_handling({"component": "query_generation", "operation": "generate_query"})
    @with_retry(RetryConfig(max_attempts=2, base_delay=1.0))
    async def _generate_query(self, analysis: Dict[str, Any], fields: List[Dict[str, Any]], 
                            limit: int) -> Dict[str, Any]:
        """生成查询语句"""
        query_type = analysis["query_type"]
        
        try:
            if query_type == "find":
                return self._generate_find_query(analysis, limit)
            elif query_type == "count":
                return self._generate_count_query(analysis)
            elif query_type == "aggregate":
                return self._generate_aggregate_query(analysis, limit)
            elif query_type == "distinct":
                return self._generate_distinct_query(analysis, fields)
            else:
                return {"error": f"不支持的查询类型: {query_type}"}
                
        except Exception as e:
            return {"error": f"生成查询时发生错误: {str(e)}"}
    
    @with_error_handling({"component": "query_generation", "operation": "generate_find_query"})
    def _generate_find_query(self, analysis: Dict[str, Any], limit: int) -> Dict[str, Any]:
        """生成查找查询"""
        query = {}
        
        # 构建查询条件
        all_conditions = (analysis["conditions"] + analysis["time_filters"] + 
                         analysis["text_searches"] + analysis["numeric_ranges"])
        
        for condition in all_conditions:
            field = condition["field"]
            operator = condition["operator"]
            value = condition["value"]
            
            if operator == "$eq":
                query[field] = value
            elif operator in ["$ne", "$gt", "$gte", "$lt", "$lte"]:
                if field not in query:
                    query[field] = {}
                query[field][operator] = value
            elif operator == "$regex":
                query[field] = value
            elif operator == "$exists":
                query[field] = {"$exists": value}
        
        # 构建排序
        sort = []
        for sort_field in analysis["sort_fields"]:
            sort.append((sort_field["field"], sort_field["direction"]))
        
        return {
            "query_type": "find",
            "filter": query,
            "sort": sort,
            "limit": limit,
            "mongodb_query": {
                "filter": query,
                "sort": dict(sort) if sort else None,
                "limit": limit
            }
        }
    
    @with_error_handling({"component": "query_generation", "operation": "generate_count_query"})
    def _generate_count_query(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """生成计数查询"""
        query = {}
        
        # 构建查询条件（与find查询相同）
        all_conditions = (analysis["conditions"] + analysis["time_filters"] + 
                         analysis["text_searches"] + analysis["numeric_ranges"])
        
        for condition in all_conditions:
            field = condition["field"]
            operator = condition["operator"]
            value = condition["value"]
            
            if operator == "$eq":
                query[field] = value
            elif operator in ["$ne", "$gt", "$gte", "$lt", "$lte"]:
                if field not in query:
                    query[field] = {}
                query[field][operator] = value
            elif operator == "$regex":
                query[field] = value
            elif operator == "$exists":
                query[field] = {"$exists": value}
        
        return {
            "query_type": "count",
            "filter": query,
            "mongodb_query": {
                "filter": query
            }
        }
    
    @with_error_handling({"component": "query_generation", "operation": "generate_aggregate_query"})
    def _generate_aggregate_query(self, analysis: Dict[str, Any], limit: int) -> Dict[str, Any]:
        """生成聚合查询"""
        pipeline = []
        
        # 添加匹配阶段
        match_conditions = {}
        all_conditions = (analysis["conditions"] + analysis["time_filters"] + 
                         analysis["text_searches"] + analysis["numeric_ranges"])
        
        for condition in all_conditions:
            field = condition["field"]
            operator = condition["operator"]
            value = condition["value"]
            
            if operator == "$eq":
                match_conditions[field] = value
            elif operator in ["$ne", "$gt", "$gte", "$lt", "$lte"]:
                if field not in match_conditions:
                    match_conditions[field] = {}
                match_conditions[field][operator] = value
            elif operator == "$regex":
                match_conditions[field] = value
            elif operator == "$exists":
                match_conditions[field] = {"$exists": value}
        
        if match_conditions:
            pipeline.append({"$match": match_conditions})
        
        # 添加分组阶段
        if analysis["group_fields"]:
            group_stage = {
                "_id": {}
            }
            
            for group_field in analysis["group_fields"]:
                field_name = group_field["field"].replace(".", "_")
                group_stage["_id"][field_name] = f"${group_field['field']}"
            
            # 添加计数
            group_stage["count"] = {"$sum": 1}
            
            pipeline.append({"$group": group_stage})
        
        # 添加排序阶段
        if analysis["sort_fields"]:
            sort_stage = {}
            for sort_field in analysis["sort_fields"]:
                sort_stage[sort_field["field"]] = sort_field["direction"]
            pipeline.append({"$sort": sort_stage})
        
        # 添加限制阶段
        pipeline.append({"$limit": limit})
        
        return {
            "query_type": "aggregate",
            "pipeline": pipeline,
            "mongodb_query": {
                "pipeline": pipeline
            }
        }
    
    @with_error_handling({"component": "query_generation", "operation": "generate_distinct_query"})
    def _generate_distinct_query(self, analysis: Dict[str, Any], fields: List[Dict[str, Any]]) -> Dict[str, Any]:
        """生成去重查询"""
        # 选择第一个相关字段作为去重字段
        distinct_field = None
        
        if analysis["conditions"]:
            distinct_field = analysis["conditions"][0]["field"]
        elif fields:
            # 选择第一个字段
            distinct_field = fields[0]["field_path"]
        
        if not distinct_field:
            return {"error": "无法确定去重字段"}
        
        # 构建查询条件
        query = {}
        all_conditions = (analysis["conditions"] + analysis["time_filters"] + 
                         analysis["text_searches"] + analysis["numeric_ranges"])
        
        for condition in all_conditions:
            field = condition["field"]
            operator = condition["operator"]
            value = condition["value"]
            
            if operator == "$eq":
                query[field] = value
            elif operator in ["$ne", "$gt", "$gte", "$lt", "$lte"]:
                if field not in query:
                    query[field] = {}
                query[field][operator] = value
            elif operator == "$regex":
                query[field] = value
            elif operator == "$exists":
                query[field] = {"$exists": value}
        
        return {
            "query_type": "distinct",
            "field": distinct_field,
            "filter": query,
            "mongodb_query": {
                "field": distinct_field,
                "filter": query
            }
        }
    
    @with_error_handling({"component": "query_generation", "operation": "build_query_result"})
    async def _build_query_result(self, query_result: Dict[str, Any], query_description: str,
                                instance_id: str, database_name: str, collection_name: str,
                                include_explanation: bool, analysis: Dict[str, Any] = None, 
                                output_format: str = "full") -> str:
        """构建查询结果文本"""
        query_type = query_result["query_type"]
        mongodb_query = query_result["mongodb_query"]
        
        # 生成可执行的MongoDB查询语句
        executable_query = self._generate_executable_query(query_type, collection_name, mongodb_query)
        
        # 根据输出格式返回不同内容
        if output_format == "executable":
            return executable_query
        elif output_format == "query_only":
            result_text = f"**查询类型**: {query_type.upper()}\n\n"
            result_text += f"```javascript\n{executable_query}\n```"
            return result_text
        
        # 默认完整格式
        result_text = f"## 查询生成结果\n\n"
        result_text += f"**查询描述**: {query_description}\n\n"
        
        # 语义补全信息
        if analysis and "semantic_completion" in analysis:
            completion_info = analysis["semantic_completion"]
            if completion_info.get("suggestions"):
                result_text += f"### 🔍 智能字段匹配\n\n"
                result_text += f"系统自动识别并匹配了以下字段：\n\n"
                for suggestion in completion_info["suggestions"]:
                    field_path = suggestion.get("field_path", "")
                    confidence = suggestion.get("confidence", 0)
                    reason = suggestion.get("reason", "")
                    result_text += f"- **{field_path}** (置信度: {confidence:.2f}) - {reason}\n"
                result_text += "\n"
        
        result_text += f"### 生成的MongoDB查询\n\n"
        result_text += f"**查询类型**: {query_type.upper()}\n\n"
        
        # 显示可执行的MongoDB查询语句
        result_text += f"```javascript\n{executable_query}\n```\n\n"
        
        # 查询解释
        if include_explanation:
            result_text += await self._generate_query_explanation(query_result, query_description)
        
        # 使用建议
        result_text += f"### 使用建议\n\n"
        result_text += f"- 可直接复制上述查询语句到MongoDB shell或客户端中执行\n"
        result_text += f"- 使用 `confirm_query` 工具在系统中执行此查询并查看结果\n"
        result_text += f"- 如果查询结果不符合预期，可以调整查询描述重新生成\n"
        result_text += f"- 对于大数据集，建议先使用 count 查询确认结果数量\n"
        
        return result_text
    
    def _generate_executable_query(self, query_type: str, collection_name: str, mongodb_query: Dict[str, Any]) -> str:
        """生成可直接执行的MongoDB查询语句"""
        if query_type == "find":
            filter_query = mongodb_query.get("filter", {})
            sort_query = mongodb_query.get("sort")
            limit_query = mongodb_query.get("limit")
            
            query_str = f"db.{collection_name}.find("
            query_str += json.dumps(filter_query, ensure_ascii=False, default=str, separators=(',', ':'))
            query_str += ")"
            
            if sort_query:
                query_str += f".sort({json.dumps(sort_query, ensure_ascii=False, separators=(',', ':'))})"
            
            if limit_query:
                query_str += f".limit({limit_query})"
            
            return query_str
            
        elif query_type == "count":
            filter_query = mongodb_query.get("filter", {})
            query_str = f"db.{collection_name}.countDocuments("
            query_str += json.dumps(filter_query, ensure_ascii=False, default=str, separators=(',', ':'))
            query_str += ")"
            return query_str
            
        elif query_type == "aggregate":
            pipeline = mongodb_query.get("pipeline", [])
            query_str = f"db.{collection_name}.aggregate("
            query_str += json.dumps(pipeline, ensure_ascii=False, default=str, separators=(',', ':'))
            query_str += ")"
            return query_str
            
        elif query_type == "distinct":
            field = mongodb_query.get("field")
            filter_query = mongodb_query.get("filter", {})
            query_str = f"db.{collection_name}.distinct("
            query_str += f'"{field}", '
            query_str += json.dumps(filter_query, ensure_ascii=False, default=str, separators=(',', ':'))
            query_str += ")"
            return query_str
        
        return f"// 不支持的查询类型: {query_type}"
    
    async def _generate_query_explanation(self, query_result: Dict[str, Any], query_description: str) -> str:
        """生成查询解释"""
        explanation = f"### 查询解释\n\n"
        
        query_type = query_result["query_type"]
        
        if query_type == "find":
            filter_query = query_result.get("filter", {})
            sort_query = query_result.get("sort", [])
            limit_query = query_result.get("limit")
            
            explanation += f"此查询将：\n"
            
            if filter_query:
                explanation += f"1. **筛选条件**: 根据以下条件筛选文档：\n"
                for field, condition in filter_query.items():
                    if isinstance(condition, dict):
                        for op, value in condition.items():
                            op_desc = self._get_operator_description(op)
                            explanation += f"   - {field} {op_desc} {value}\n"
                    else:
                        explanation += f"   - {field} 等于 {condition}\n"
            else:
                explanation += f"1. **筛选条件**: 无筛选条件，返回所有文档\n"
            
            if sort_query:
                explanation += f"2. **排序**: 按以下字段排序：\n"
                for field, direction in sort_query:
                    direction_desc = "升序" if direction == 1 else "降序"
                    explanation += f"   - {field} ({direction_desc})\n"
            
            if limit_query:
                explanation += f"3. **限制**: 最多返回 {limit_query} 条记录\n"
            
        elif query_type == "count":
            explanation += f"此查询将统计满足条件的文档数量\n"
            
        elif query_type == "aggregate":
            explanation += f"此查询使用聚合管道进行复杂数据处理\n"
            
        elif query_type == "distinct":
            field = query_result.get("field")
            explanation += f"此查询将返回字段 '{field}' 的所有唯一值\n"
        
        explanation += "\n"
        return explanation
    
    def _get_operator_description(self, operator: str) -> str:
        """获取操作符描述"""
        descriptions = {
            "$eq": "等于",
            "$ne": "不等于",
            "$gt": "大于",
            "$gte": "大于等于",
            "$lt": "小于",
            "$lte": "小于等于",
            "$regex": "匹配正则表达式",
            "$exists": "存在" if operator == "$exists" else "不存在"
        }
        return descriptions.get(operator, operator)
    
    @with_error_handling({"component": "query_generation", "operation": "save_query_history"})
    async def _save_query_history(self, instance_id: str, database_name: str, collection_name: str,
                                query_description: str, query_result: Dict[str, Any]):
        """保存查询历史"""
        try:
            await self.metadata_manager.save_query_history(
                instance_id=instance_id,
                database_name=database_name,
                collection_name=collection_name,
                query_description=query_description,
                query_type=query_result["query_type"],
                mongodb_query=query_result["mongodb_query"],
                generated_at=datetime.now()
            )
        except Exception as e:
            logger.warning("保存查询历史失败", error=str(e))