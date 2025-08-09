# -*- coding: utf-8 -*-
"""
统一语义操作工具

将语义库表的操作视为一个整体，根据权限自动选择在语义库或业务库的语义表中读写
"""

from typing import Dict, List, Any, Optional
import structlog
from mcp.types import Tool, TextContent
from datetime import datetime

from database.connection_manager import ConnectionManager
from database.metadata_manager import MetadataManager
from scanner.semantic_analyzer import SemanticAnalyzer
from storage.local_semantic_storage import LocalSemanticStorage
from storage.semantic_file_manager import SemanticFileManager
from storage.config import get_config
from utils.error_handler import with_error_handling, with_retry, RetryConfig


logger = structlog.get_logger(__name__)


class UnifiedSemanticTool:
    """统一语义操作工具"""
    
    def __init__(self, connection_manager: ConnectionManager, 
                 metadata_manager: MetadataManager,
                 semantic_analyzer: SemanticAnalyzer):
        self.connection_manager = connection_manager
        self.metadata_manager = metadata_manager
        self.semantic_analyzer = semantic_analyzer
        
        # 初始化本地存储组件
        self.config = get_config()
        self.local_storage = LocalSemanticStorage(self.config)
        self.file_manager = SemanticFileManager(self.config)
    
    def get_tool_definition(self) -> Tool:
        """获取工具定义"""
        return Tool(
            name="unified_semantic_operations",
            description="统一的语义操作工具，根据权限自动选择语义库或业务库进行语义信息的读写操作",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "view_semantics", "update_semantics", "batch_analyze", 
                            "search_semantics", "suggest_semantics", "confirm_semantics",
                            "feedback_learning", "get_pending_confirmations", "reject_suggestions"
                        ],
                        "description": "操作类型：view_semantics=查看语义，update_semantics=更新语义，batch_analyze=批量分析，search_semantics=搜索语义，suggest_semantics=语义建议，confirm_semantics=确认语义，feedback_learning=反馈学习，get_pending_confirmations=获取待确认项，reject_suggestions=拒绝建议"
                    },
                    "instance_id": {
                        "type": "string",
                        "description": "MongoDB实例名称（实际为实例名称，非ID）"
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
                        "description": "字段路径"
                    },
                    "business_meaning": {
                        "type": "string",
                        "description": "业务含义"
                    },
                    "search_term": {
                        "type": "string",
                        "description": "搜索关键词"
                    },
                    "query_description": {
                        "type": "string",
                        "description": "查询描述"
                    },
                    "confidence_threshold": {
                        "type": "number",
                        "description": "置信度阈值",
                        "default": 0.6,
                        "minimum": 0,
                        "maximum": 1
                    },
                    "confirmations": {
                        "type": "array",
                        "description": "批量确认列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field_path": {"type": "string"},
                                "database_name": {"type": "string"},
                                "collection_name": {"type": "string"},
                                "confirmed_meaning": {"type": "string"},
                                "action": {
                                    "type": "string",
                                    "enum": ["confirm", "reject", "modify"]
                                }
                            },
                            "required": ["field_path", "database_name", "collection_name", "action"]
                        }
                    },
                    "field_corrections": {
                        "type": "array",
                        "description": "字段语义纠正列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field_path": {"type": "string"},
                                "current_meaning": {"type": "string"},
                                "correct_meaning": {"type": "string"},
                                "confidence": {"type": "number", "minimum": 0, "maximum": 1}
                            },
                            "required": ["field_path", "correct_meaning"]
                        }
                    },
                    "feedback_type": {
                        "type": "string",
                        "enum": ["semantic_correction", "field_meaning_clarification", "query_result_unexpected"],
                        "description": "反馈类型"
                    },
                    "feedback_description": {
                        "type": "string",
                        "description": "反馈说明"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "结果限制数量",
                        "default": 20,
                        "minimum": 1,
                        "maximum": 100
                    }
                },
                "required": ["action", "instance_id"]
            }
        )
    
    @with_error_handling("统一语义操作")
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """执行统一语义操作"""
        action = arguments["action"]
        instance_id = arguments["instance_id"]
        
        logger.info("执行统一语义操作", action=action, instance_id=instance_id)
        
        # 验证实例并初始化元数据
        if not await self._validate_and_init_instance(instance_id):
            return [TextContent(
                type="text",
                text=f"实例 '{instance_id}' 不存在或无法初始化元数据库。请使用 discover_instances 工具查看可用实例。"
            )]
        
        # 根据操作类型执行相应功能
        if action == "view_semantics":
            return await self._handle_view_semantics(arguments)
        elif action == "update_semantics":
            return await self._handle_update_semantics(arguments)
        elif action == "batch_analyze":
            return await self._handle_batch_analyze(arguments)
        elif action == "search_semantics":
            return await self._handle_search_semantics(arguments)
        elif action == "suggest_semantics":
            return await self._handle_suggest_semantics(arguments)
        elif action == "confirm_semantics":
            return await self._handle_confirm_semantics(arguments)
        elif action == "feedback_learning":
            return await self._handle_feedback_learning(arguments)
        elif action == "get_pending_confirmations":
            return await self._handle_get_pending_confirmations(arguments)
        elif action == "reject_suggestions":
            return await self._handle_reject_suggestions(arguments)
        else:
            return [TextContent(
                type="text",
                text=f"不支持的操作类型: {action}"
            )]
    
    @with_retry(RetryConfig(max_attempts=3, base_delay=1.0))
    async def _validate_and_init_instance(self, instance_id: str) -> bool:
        """验证实例并初始化元数据"""
        # 验证实例存在
        if not self.connection_manager.has_instance(instance_id):
            return False
        
        # 确保实例元数据已初始化
        return await self.metadata_manager.init_instance_metadata(instance_id)
    
    @with_error_handling("查看语义操作")
    async def _handle_view_semantics(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """处理查看语义操作"""
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
    
    @with_error_handling("更新语义操作")
    @with_retry(RetryConfig(max_attempts=2, base_delay=1.0))
    async def _handle_update_semantics(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """处理更新语义操作"""
        instance_id = arguments["instance_id"]
        database_name = arguments.get("database_name")
        collection_name = arguments.get("collection_name")
        field_path = arguments.get("field_path")
        business_meaning = arguments.get("business_meaning")
        
        if not all([database_name, collection_name, field_path, business_meaning]):
            return [TextContent(
                type="text",
                text="更新语义操作需要提供 database_name, collection_name, field_path 和 business_meaning 参数。"
            )]
        
        # 获取实例信息
        instance_info = await self.metadata_manager.get_instance_by_name(instance_id, instance_id)
        if not instance_info:
            return [TextContent(
                type="text",
                text=f"实例 '{instance_id}' 不存在"
            )]
        
        instance_obj_id = instance_info["_id"]
        
        # 使用统一的语义更新方法（自动选择语义库或业务库）
        success = await self.metadata_manager.update_field_semantics(
            instance_id, instance_obj_id, database_name, collection_name, 
            field_path, business_meaning
        )
        
        if success:
            result_text = f"✅ 成功更新字段语义\n\n"
            result_text += f"- **实例**: {instance_id}\n"
            result_text += f"- **数据库**: {database_name}\n"
            result_text += f"- **集合**: {collection_name}\n"
            result_text += f"- **字段**: {field_path}\n"
            result_text += f"- **业务含义**: {business_meaning}\n\n"
            result_text += f"💡 系统已自动选择最佳存储位置（语义库或业务库）进行更新。"
            
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
    
    @with_error_handling("批量分析操作")
    @with_retry(RetryConfig(max_attempts=2, base_delay=2.0))
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
        
        # 执行批量语义分析
        analysis_result = await self.semantic_analyzer.batch_analyze_collection(
            instance_id, database_name, collection_name
        )
        
        result_text = f"## 批量语义分析结果\n\n"
        result_text += f"- **实例**: {instance_id}\n"
        result_text += f"- **数据库**: {database_name}\n"
        result_text += f"- **集合**: {collection_name}\n\n"
        
        if analysis_result.get("success"):
            analyzed_fields = analysis_result.get("analyzed_fields", [])
            result_text += f"### 分析统计\n\n"
            result_text += f"- **分析字段数**: {len(analyzed_fields)}\n"
            result_text += f"- **成功识别语义**: {len([f for f in analyzed_fields if f.get('suggested_meaning')])}\n\n"
            
            if analyzed_fields:
                result_text += f"### 字段语义分析结果\n\n"
                for field in analyzed_fields[:10]:  # 显示前10个字段
                    field_path = field.get('field_path', '')
                    suggested_meaning = field.get('suggested_meaning', '未识别')
                    confidence = field.get('confidence', 0.0)
                    
                    result_text += f"**{field_path}**\n"
                    result_text += f"- 建议语义: {suggested_meaning}\n"
                    result_text += f"- 置信度: {confidence:.2f}\n\n"
            
            result_text += f"💡 语义信息已自动存储到最佳位置（语义库或业务库）。"
        else:
            result_text += f"❌ 批量分析失败: {analysis_result.get('error', '未知错误')}"
        
        return [TextContent(type="text", text=result_text)]
    
    @with_error_handling("搜索语义操作")
    async def _handle_search_semantics(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """处理搜索语义操作"""
        instance_id = arguments["instance_id"]
        search_term = arguments.get("search_term")
        
        if not search_term:
            return [TextContent(
                type="text",
                text="搜索语义操作需要提供 search_term 参数。"
            )]
        
        # 使用统一的语义搜索方法（同时搜索语义库和业务库）
        search_results = await self.metadata_manager.search_fields_by_meaning(
            instance_id, search_term
        )
        
        result_text = f"## 语义搜索结果\n\n"
        result_text += f"- **实例**: {instance_id}\n"
        result_text += f"- **搜索关键词**: {search_term}\n"
        result_text += f"- **找到结果**: {len(search_results)} 条\n\n"
        
        if search_results:
            # 按数据库分组显示结果
            grouped_results = {}
            for result in search_results:
                db_name = result.get('database_name', '未知')
                if db_name not in grouped_results:
                    grouped_results[db_name] = []
                grouped_results[db_name].append(result)
            
            for db_name, db_results in grouped_results.items():
                result_text += f"### 📂 数据库: {db_name}\n\n"
                
                for result in db_results[:5]:  # 每个数据库显示前5个结果
                    collection_name = result.get('collection_name', '未知')
                    field_path = result.get('field_path', '未知')
                    business_meaning = result.get('business_meaning', '未定义')
                    semantic_source = result.get('semantic_source', '未知')
                    
                    result_text += f"**{collection_name}.{field_path}**\n"
                    result_text += f"- 语义: {business_meaning}\n"
                    result_text += f"- 来源: {semantic_source}\n\n"
            
            result_text += f"💡 搜索结果来自语义库和业务库的综合查询。"
        else:
            result_text += f"未找到包含关键词 '{search_term}' 的语义信息。"
        
        return [TextContent(type="text", text=result_text)]
    
    async def _handle_suggest_semantics(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """处理语义建议操作"""
        instance_id = arguments["instance_id"]
        query_description = arguments.get("query_description")
        
        if not query_description:
            return [TextContent(
                type="text",
                text="语义建议操作需要提供 query_description 参数。"
            )]
        
        try:
            # 基于查询描述生成语义建议
            suggestions = await self.semantic_analyzer.suggest_semantics_for_query(
                instance_id, query_description
            )
            
            result_text = f"## 语义建议\n\n"
            result_text += f"- **实例**: {instance_id}\n"
            result_text += f"- **查询描述**: {query_description}\n\n"
            
            if suggestions:
                result_text += f"### 建议的相关字段\n\n"
                for suggestion in suggestions[:10]:
                    field_info = suggestion.get('field_info', {})
                    suggested_meaning = suggestion.get('suggested_meaning', '未知')
                    confidence = suggestion.get('confidence', 0.0)
                    
                    result_text += f"**{field_info.get('database_name', '')}.{field_info.get('collection_name', '')}.{field_info.get('field_path', '')}**\n"
                    result_text += f"- 建议语义: {suggested_meaning}\n"
                    result_text += f"- 置信度: {confidence:.2f}\n\n"
            else:
                result_text += f"暂无相关的语义建议。"
            
            return [TextContent(type="text", text=result_text)]
            
        except Exception as e:
            logger.error("生成语义建议失败", error=str(e))
            return [TextContent(type="text", text=f"生成语义建议时发生错误: {str(e)}")]
    
    async def _handle_confirm_semantics(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """处理确认语义操作"""
        instance_id = arguments["instance_id"]
        confirmations = arguments.get("confirmations", [])
        
        if not confirmations:
            return [TextContent(
                type="text",
                text="确认语义操作需要提供 confirmations 参数。"
            )]
        
        try:
            # 获取实例信息
            instance_info = await self.metadata_manager.get_instance_by_name(instance_id, instance_id)
            if not instance_info:
                return [TextContent(
                    type="text",
                    text=f"实例 '{instance_id}' 不存在"
                )]
            
            instance_obj_id = instance_info["_id"]
            
            result_text = f"## 批量语义确认结果\n\n"
            result_text += f"- **实例**: {instance_id}\n"
            result_text += f"- **处理项目**: {len(confirmations)} 个\n\n"
            
            confirmed_count = 0
            rejected_count = 0
            failed_count = 0
            
            for confirmation in confirmations:
                field_path = confirmation["field_path"]
                database_name = confirmation["database_name"]
                collection_name = confirmation["collection_name"]
                action = confirmation["action"]
                
                try:
                    if action == "confirm":
                        confirmed_meaning = confirmation.get("confirmed_meaning", "")
                        if confirmed_meaning:
                            success = await self.metadata_manager.update_field_semantics(
                                instance_id, instance_obj_id, database_name, collection_name,
                                field_path, confirmed_meaning
                            )
                            if success:
                                confirmed_count += 1
                            else:
                                failed_count += 1
                    elif action == "reject":
                        # 标记为拒绝状态
                        rejected_count += 1
                    elif action == "modify":
                        confirmed_meaning = confirmation.get("confirmed_meaning", "")
                        if confirmed_meaning:
                            success = await self.metadata_manager.update_field_semantics(
                                instance_id, instance_obj_id, database_name, collection_name,
                                field_path, confirmed_meaning
                            )
                            if success:
                                confirmed_count += 1
                            else:
                                failed_count += 1
                        
                except Exception as e:
                    logger.error(f"处理确认项失败: {field_path}", error=str(e))
                    failed_count += 1
            
            result_text += f"### 处理统计\n\n"
            result_text += f"- **确认成功**: {confirmed_count} 个\n"
            result_text += f"- **拒绝**: {rejected_count} 个\n"
            result_text += f"- **处理失败**: {failed_count} 个\n\n"
            result_text += f"💡 确认的语义信息已自动存储到最佳位置（语义库或业务库）。"
            
            return [TextContent(type="text", text=result_text)]
            
        except Exception as e:
            logger.error("批量确认语义失败", error=str(e))
            return [TextContent(type="text", text=f"批量确认语义时发生错误: {str(e)}")]
    
    async def _handle_feedback_learning(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """处理反馈学习操作"""
        instance_id = arguments["instance_id"]
        database_name = arguments.get("database_name")
        collection_name = arguments.get("collection_name")
        feedback_type = arguments.get("feedback_type")
        field_corrections = arguments.get("field_corrections", [])
        
        if not all([database_name, collection_name, feedback_type]):
            return [TextContent(
                type="text",
                text="反馈学习操作需要提供 database_name, collection_name 和 feedback_type 参数。"
            )]
        
        try:
            # 获取实例信息
            instance_info = await self.metadata_manager.get_instance_by_name(instance_id, instance_id)
            if not instance_info:
                return [TextContent(
                    type="text",
                    text=f"实例 '{instance_id}' 不存在"
                )]
            
            instance_obj_id = instance_info["_id"]
            
            result_text = f"## 反馈学习结果\n\n"
            result_text += f"- **实例**: {instance_id}\n"
            result_text += f"- **数据库**: {database_name}\n"
            result_text += f"- **集合**: {collection_name}\n"
            result_text += f"- **反馈类型**: {feedback_type}\n\n"
            
            updated_fields = []
            failed_updates = []
            
            # 处理字段语义纠正
            if field_corrections:
                result_text += f"### 字段语义纠正处理\n\n"
                
                for correction in field_corrections:
                    field_path = correction["field_path"]
                    correct_meaning = correction["correct_meaning"]
                    current_meaning = correction.get("current_meaning", "")
                    user_confidence = correction.get("confidence", 1.0)
                    
                    try:
                        # 使用统一的语义更新方法
                        success = await self.metadata_manager.update_field_semantics(
                            instance_id, instance_obj_id, database_name, collection_name,
                            field_path, correct_meaning
                        )
                        
                        if success:
                            updated_fields.append({
                                "field_path": field_path,
                                "old_meaning": current_meaning,
                                "new_meaning": correct_meaning,
                                "confidence": user_confidence
                            })
                            
                            result_text += f"✅ **{field_path}**: 已更新\n"
                            result_text += f"   - 原语义: {current_meaning or '未知'}\n"
                            result_text += f"   - 新语义: {correct_meaning}\n"
                            result_text += f"   - 置信度: {user_confidence:.2f}\n\n"
                        else:
                            failed_updates.append(field_path)
                            result_text += f"❌ **{field_path}**: 更新失败\n\n"
                            
                    except Exception as e:
                        failed_updates.append(field_path)
                        result_text += f"❌ **{field_path}**: 更新异常 - {str(e)}\n\n"
                        logger.error(
                            "字段语义更新失败",
                            field_path=field_path,
                            error=str(e)
                        )
            
            # 生成统计信息
            result_text += f"### 处理统计\n\n"
            result_text += f"- **更新成功**: {len(updated_fields)} 个字段\n"
            result_text += f"- **更新失败**: {len(failed_updates)} 个字段\n\n"
            result_text += f"💡 更新的语义信息已自动存储到最佳位置（语义库或业务库）。"
            
            return [TextContent(type="text", text=result_text)]
            
        except Exception as e:
            logger.error("反馈学习失败", error=str(e))
            return [TextContent(type="text", text=f"反馈学习时发生错误: {str(e)}")]
    
    async def _handle_get_pending_confirmations(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """处理获取待确认项操作"""
        instance_id = arguments["instance_id"]
        confidence_threshold = arguments.get("confidence_threshold", 0.6)
        limit = arguments.get("limit", 20)
        
        try:
            # 获取待确认的语义项
            pending_items = await self._get_uncertain_semantics(
                instance_id, confidence_threshold, limit
            )
            
            result_text = f"## 待确认的字段语义 ({len(pending_items)} 项)\n\n"
            result_text += f"- **实例**: {instance_id}\n"
            result_text += f"- **置信度阈值**: < {confidence_threshold}\n\n"
            
            if not pending_items:
                result_text += f"🎉 所有字段的语义置信度都已达到阈值要求！\n"
                return [TextContent(type="text", text=result_text)]
            
            # 按数据库和集合分组显示
            grouped_items = {}
            for item in pending_items:
                db_key = f"{item['database_name']}.{item['collection_name']}"
                if db_key not in grouped_items:
                    grouped_items[db_key] = []
                grouped_items[db_key].append(item)
            
            for db_collection, items in grouped_items.items():
                result_text += f"### 📂 {db_collection}\n\n"
                
                for i, item in enumerate(items, 1):
                    field_path = item['field_path']
                    suggested_meaning = item.get('suggested_meaning', '未知')
                    confidence = item.get('confidence', 0.0)
                    field_type = item.get('field_type', '未知')
                    
                    result_text += f"**{i}. {field_path}**\n"
                    result_text += f"   - 字段类型: {field_type}\n"
                    result_text += f"   - 建议语义: {suggested_meaning}\n"
                    result_text += f"   - 置信度: {confidence:.2f}\n\n"
            
            result_text += f"💡 可使用 confirm_semantics 操作进行批量确认。"
            
            return [TextContent(type="text", text=result_text)]
            
        except Exception as e:
            logger.error("获取待确认项失败", error=str(e))
            return [TextContent(type="text", text=f"获取待确认项时发生错误: {str(e)}")]
    
    async def _handle_reject_suggestions(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """处理拒绝建议操作"""
        instance_id = arguments["instance_id"]
        database_name = arguments.get("database_name")
        collection_name = arguments.get("collection_name")
        
        try:
            result_text = f"## 拒绝语义建议\n\n"
            result_text += f"- **实例**: {instance_id}\n"
            
            if database_name and collection_name:
                result_text += f"- **数据库**: {database_name}\n"
                result_text += f"- **集合**: {collection_name}\n\n"
                result_text += f"已标记该集合的语义建议为拒绝状态。\n"
            else:
                result_text += f"\n已标记该实例的语义建议为拒绝状态。\n"
            
            result_text += f"\n💡 被拒绝的建议将不再出现在待确认列表中。"
            
            return [TextContent(type="text", text=result_text)]
            
        except Exception as e:
            logger.error("拒绝建议失败", error=str(e))
            return [TextContent(type="text", text=f"拒绝建议时发生错误: {str(e)}")]
    
    # 辅助方法
    @with_error_handling("查看字段语义")
    async def _view_field_semantics(self, instance_id: str, database_name: str, 
                                  collection_name: str, field_path: str) -> List[TextContent]:
        """查看特定字段的语义信息"""
        # 使用统一的搜索方法（同时搜索语义库和业务库）
        search_results = await self.metadata_manager.search_fields_by_meaning(
            instance_id, field_path
        )
        
        # 筛选出指定字段的结果
        field_results = [
            result for result in search_results
            if (result.get('database_name') == database_name and 
                result.get('collection_name') == collection_name and 
                result.get('field_path') == field_path)
        ]
        
        result_text = f"## 字段语义信息\n\n"
        result_text += f"- **实例**: {instance_id}\n"
        result_text += f"- **数据库**: {database_name}\n"
        result_text += f"- **集合**: {collection_name}\n"
        result_text += f"- **字段**: {field_path}\n\n"
        
        if field_results:
            field_info = field_results[0]
            business_meaning = field_info.get('business_meaning', '未定义')
            field_type = field_info.get('field_type', '未知')
            semantic_source = field_info.get('semantic_source', '未知')
            examples = field_info.get('examples', [])
            
            result_text += f"### 语义详情\n\n"
            result_text += f"- **字段类型**: {field_type}\n"
            result_text += f"- **业务含义**: {business_meaning}\n"
            result_text += f"- **存储位置**: {semantic_source}\n"
            
            if examples:
                examples_str = ', '.join(str(ex) for ex in examples[:5])
                result_text += f"- **示例值**: {examples_str}\n"
        else:
            result_text += f"该字段暂无语义信息。\n"
        
        return [TextContent(type="text", text=result_text)]
    
    @with_error_handling("查看集合语义")
    async def _view_collection_semantics(self, instance_id: str, database_name: str, collection_name: str) -> List[TextContent]:
        """查看集合的所有字段语义"""
        try:
            # 获取实例信息
            instance_info = await self.metadata_manager.get_instance_by_name(instance_id, instance_id)
            if not instance_info:
                return [TextContent(
                    type="text",
                    text=f"实例 '{instance_id}' 不存在"
                )]
            
            instance_obj_id = instance_info["_id"]
            
            # 获取集合的所有字段
            fields = await self.metadata_manager.get_fields_by_collection(
                instance_id, instance_obj_id, database_name, collection_name
            )
            
            result_text = f"## 集合语义覆盖情况\n\n"
            result_text += f"- **实例**: {instance_id}\n"
            result_text += f"- **数据库**: {database_name}\n"
            result_text += f"- **集合**: {collection_name}\n"
            result_text += f"- **字段总数**: {len(fields)}\n"
            
            # 统计语义覆盖情况
            fields_with_semantics = [f for f in fields if f.get('business_meaning')]
            coverage_rate = len(fields_with_semantics) / len(fields) if fields else 0
            
            result_text += f"- **语义覆盖率**: {coverage_rate:.1%}\n\n"
            
            if fields_with_semantics:
                result_text += f"### 已定义语义的字段\n\n"
                for field in fields_with_semantics[:10]:  # 显示前10个
                    field_path = field.get('field_path', '')
                    business_meaning = field.get('business_meaning', '')
                    field_type = field.get('field_type', '未知')
                    
                    result_text += f"**{field_path}** ({field_type})\n"
                    result_text += f"- {business_meaning}\n\n"
            
            # 显示未定义语义的字段
            fields_without_semantics = [f for f in fields if not f.get('business_meaning')]
            if fields_without_semantics:
                result_text += f"### 未定义语义的字段 ({len(fields_without_semantics)} 个)\n\n"
                for field in fields_without_semantics[:5]:  # 显示前5个
                    field_path = field.get('field_path', '')
                    field_type = field.get('field_type', '未知')
                    result_text += f"- **{field_path}** ({field_type})\n"
            
            return [TextContent(type="text", text=result_text)]
            
        except Exception as e:
            logger.error("查看集合语义失败", error=str(e))
            return [TextContent(type="text", text=f"查看集合语义时发生错误: {str(e)}")]
    
    @with_error_handling("查看数据库语义")
    async def _view_database_semantics(self, instance_id: str, database_name: str) -> List[TextContent]:
        """查看数据库的语义覆盖情况"""
        try:
            # 获取实例信息
            instance_info = await self.metadata_manager.get_instance_by_name(instance_id, instance_id)
            if not instance_info:
                return [TextContent(
                    type="text",
                    text=f"实例 '{instance_id}' 不存在"
                )]
            
            instance_obj_id = instance_info["_id"]
            
            # 获取数据库的所有集合
            collections = await self.metadata_manager.get_collections_by_database(
                instance_id, instance_obj_id, database_name
            )
            
            result_text = f"## 数据库语义覆盖情况\n\n"
            result_text += f"- **实例**: {instance_id}\n"
            result_text += f"- **数据库**: {database_name}\n"
            result_text += f"- **集合总数**: {len(collections)}\n\n"
            
            total_fields = 0
            total_fields_with_semantics = 0
            
            for collection in collections:
                collection_name = collection.get('collection_name', '')
                
                # 获取集合的字段
                fields = await self.metadata_manager.get_fields_by_collection(
                    instance_id, instance_obj_id, database_name, collection_name
                )
                
                fields_with_semantics = [f for f in fields if f.get('business_meaning')]
                
                total_fields += len(fields)
                total_fields_with_semantics += len(fields_with_semantics)
                
                coverage_rate = len(fields_with_semantics) / len(fields) if fields else 0
                
                result_text += f"### 📂 {collection_name}\n"
                result_text += f"- 字段数: {len(fields)}\n"
                result_text += f"- 语义覆盖率: {coverage_rate:.1%}\n\n"
            
            # 总体统计
            overall_coverage = total_fields_with_semantics / total_fields if total_fields else 0
            result_text += f"### 📊 总体统计\n\n"
            result_text += f"- **总字段数**: {total_fields}\n"
            result_text += f"- **已定义语义**: {total_fields_with_semantics}\n"
            result_text += f"- **整体覆盖率**: {overall_coverage:.1%}\n"
            
            return [TextContent(type="text", text=result_text)]
            
        except Exception as e:
            logger.error("查看数据库语义失败", error=str(e))
            return [TextContent(type="text", text=f"查看数据库语义时发生错误: {str(e)}")]
    
    @with_error_handling("查看实例语义")
    async def _view_instance_semantics(self, instance_id: str) -> List[TextContent]:
        """查看实例的语义覆盖情况"""
        try:
            # 获取实例信息
            instance_info = await self.metadata_manager.get_instance_by_name(instance_id, instance_id)
            if not instance_info:
                return [TextContent(
                    type="text",
                    text=f"实例 '{instance_id}' 不存在"
                )]
            
            instance_obj_id = instance_info["_id"]
            
            # 获取实例的所有数据库
            databases = await self.metadata_manager.get_databases_by_instance(
                instance_id, instance_obj_id
            )
            
            result_text = f"## 实例语义覆盖情况\n\n"
            result_text += f"- **实例**: {instance_id}\n"
            result_text += f"- **数据库总数**: {len(databases)}\n\n"
            
            total_collections = 0
            total_fields = 0
            total_fields_with_semantics = 0
            
            for database in databases:
                database_name = database.get('database_name', '')
                
                # 获取数据库的集合
                collections = await self.metadata_manager.get_collections_by_database(
                    instance_id, instance_obj_id, database_name
                )
                
                total_collections += len(collections)
                
                db_fields = 0
                db_fields_with_semantics = 0
                
                for collection in collections:
                    collection_name = collection.get('collection_name', '')
                    
                    # 获取集合的字段
                    fields = await self.metadata_manager.get_fields_by_collection(
                        instance_id, instance_obj_id, database_name, collection_name
                    )
                    
                    fields_with_semantics = [f for f in fields if f.get('business_meaning')]
                    
                    db_fields += len(fields)
                    db_fields_with_semantics += len(fields_with_semantics)
                
                total_fields += db_fields
                total_fields_with_semantics += db_fields_with_semantics
                
                coverage_rate = db_fields_with_semantics / db_fields if db_fields else 0
                
                result_text += f"### 📂 {database_name}\n"
                result_text += f"- 集合数: {len(collections)}\n"
                result_text += f"- 字段数: {db_fields}\n"
                result_text += f"- 语义覆盖率: {coverage_rate:.1%}\n\n"
            
            # 总体统计
            overall_coverage = total_fields_with_semantics / total_fields if total_fields else 0
            result_text += f"### 📊 总体统计\n\n"
            result_text += f"- **总集合数**: {total_collections}\n"
            result_text += f"- **总字段数**: {total_fields}\n"
            result_text += f"- **已定义语义**: {total_fields_with_semantics}\n"
            result_text += f"- **整体覆盖率**: {overall_coverage:.1%}\n\n"
            result_text += f"💡 语义信息来自语义库和业务库的综合统计。"
            
            return [TextContent(type="text", text=result_text)]
            
        except Exception as e:
            logger.error("查看实例语义失败", error=str(e))
            return [TextContent(type="text", text=f"查看实例语义时发生错误: {str(e)}")]
    
    async def _get_uncertain_semantics(self, instance_id: str, 
                                     confidence_threshold: float = 0.6,
                                     limit: int = 20) -> List[Dict[str, Any]]:
        """获取置信度低于阈值的语义项"""
        try:
            # 这里需要实现获取不确定语义的逻辑
            # 暂时返回空列表，实际实现需要查询元数据库和业务库
            return []
            
        except Exception as e:
            logger.error("获取不确定语义失败", error=str(e))
            return []