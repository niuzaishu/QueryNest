# -*- coding: utf-8 -*-
"""
查询反馈语义学习工具
"""

from typing import Dict, Any, List, Optional
from mcp import types
from mcp.types import TextContent, Tool
from database.metadata_manager import MetadataManager
from database.connection_manager import ConnectionManager
from scanner.semantic_analyzer import SemanticAnalyzer
# 移除不存在的基类导入
from datetime import datetime
import structlog

logger = structlog.get_logger()


class QueryFeedbackSemanticTool:
    """查询反馈语义学习工具"""
    
    def __init__(self, connection_manager: ConnectionManager, 
                 metadata_manager: MetadataManager, 
                 semantic_analyzer: SemanticAnalyzer):
        self.connection_manager = connection_manager
        self.metadata_manager = metadata_manager
        self.semantic_analyzer = semantic_analyzer
        self.logger = logger.bind(component="QueryFeedbackSemanticTool")
    
    def get_tool_definition(self) -> Tool:
        return Tool(
            name="query_feedback_semantic",
            description="根据用户查询反馈更新字段语义信息",
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
                    "query_id": {
                        "type": "string",
                        "description": "相关查询ID（可选）"
                    },
                    "feedback_type": {
                        "type": "string",
                        "enum": ["semantic_correction", "field_meaning_clarification", "query_result_unexpected"],
                        "description": "反馈类型：semantic_correction=语义纠正，field_meaning_clarification=字段含义澄清，query_result_unexpected=查询结果异常"
                    },
                    "field_corrections": {
                        "type": "array",
                        "description": "字段语义纠正列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field_path": {
                                    "type": "string",
                                    "description": "字段路径"
                                },
                                "current_meaning": {
                                    "type": "string",
                                    "description": "当前理解的含义"
                                },
                                "correct_meaning": {
                                    "type": "string",
                                    "description": "正确的含义"
                                },
                                "confidence": {
                                    "type": "number",
                                    "description": "用户确信度(0-1)",
                                    "minimum": 0,
                                    "maximum": 1
                                }
                            },
                            "required": ["field_path", "correct_meaning"]
                        }
                    },
                    "feedback_description": {
                        "type": "string",
                        "description": "反馈说明"
                    }
                },
                "required": ["instance_id", "database_name", "collection_name", "feedback_type"]
            }
        )
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """执行查询反馈语义学习"""
        instance_id = arguments["instance_id"]
        database_name = arguments["database_name"]
        collection_name = arguments["collection_name"]
        query_id = arguments.get("query_id")
        feedback_type = arguments["feedback_type"]
        field_corrections = arguments.get("field_corrections", [])
        feedback_description = arguments.get("feedback_description", "")
        
        try:
            # 验证实例存在
            instance_info = await self.metadata_manager.get_instance_by_name(instance_id, instance_id)
            if not instance_info:
                return [TextContent(
                    type="text",
                    text=f"未找到实例 {instance_id}"
                )]
            
            result_text = f"## 查询反馈语义学习结果\n\n"
            result_text += f"- **实例**: {instance_info.get('name', instance_id)}\n"
            result_text += f"- **数据库**: {database_name}\n"
            result_text += f"- **集合**: {collection_name}\n"
            result_text += f"- **反馈类型**: {self._get_feedback_type_desc(feedback_type)}\n\n"
            
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
                        # 更新字段语义
                        success = await self.metadata_manager.update_field_semantics(
                            instance_id, 
                            database_name,
                            collection_name, 
                            field_path,
                            correct_meaning
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
                        self.logger.error(
                            "字段语义更新失败",
                            field_path=field_path,
                            error=str(e)
                        )
            
            # 记录反馈学习历史
            feedback_record = {
                "query_id": query_id,
                "instance_id": instance_id,
                "database_name": database_name,
                "collection_name": collection_name,
                "feedback_type": feedback_type,
                "field_corrections": field_corrections,
                "feedback_description": feedback_description,
                "updated_fields": updated_fields,
                "failed_updates": failed_updates,
                "created_at": datetime.now(),
                "learning_source": "user_feedback"
            }
            
            await self._record_semantic_learning(feedback_record)
            
            # 生成统计信息
            result_text += f"### 处理统计\n\n"
            result_text += f"- **更新成功**: {len(updated_fields)} 个字段\n"
            result_text += f"- **更新失败**: {len(failed_updates)} 个字段\n"
            
            if updated_fields:
                result_text += f"\n### 后续建议\n\n"
                result_text += f"1. 建议重新扫描相关集合以验证语义更新效果\n"
                result_text += f"2. 可以使用 `collection_analysis` 工具查看更新后的语义信息\n"
                result_text += f"3. 类似字段的语义可能也需要检查更新\n"
            
            # 触发相关字段的语义关联分析
            if updated_fields:
                await self._trigger_semantic_correlation_analysis(
                    instance_id, database_name, collection_name, updated_fields
                )
            
            self.logger.info(
                "查询反馈语义学习完成",
                instance_id=instance_id,
                database=database_name,
                collection=collection_name,
                updated_count=len(updated_fields),
                failed_count=len(failed_updates)
            )
            
            return [TextContent(type="text", text=result_text)]
            
        except Exception as e:
            error_msg = f"查询反馈语义学习失败: {str(e)}"
            self.logger.error(error_msg, error=str(e))
            return [TextContent(type="text", text=f"❌ {error_msg}")]
    
    def _get_feedback_type_desc(self, feedback_type: str) -> str:
        """获取反馈类型描述"""
        descriptions = {
            "semantic_correction": "语义纠正",
            "field_meaning_clarification": "字段含义澄清", 
            "query_result_unexpected": "查询结果异常"
        }
        return descriptions.get(feedback_type, feedback_type)
    
    async def _record_semantic_learning(self, feedback_record: Dict[str, Any]):
        """记录语义学习历史"""
        try:
            # 获取元数据库集合
            collections = self.metadata_manager._get_instance_collections(
                feedback_record["instance_id"]
            )
            
            if collections and 'semantic_learning' in collections:
                await collections['semantic_learning'].insert_one(feedback_record)
            else:
                # 如果集合不存在，创建它
                instance_info = await self.metadata_manager.get_instance_by_name(
                    feedback_record["instance_id"], feedback_record["instance_id"]
                )
                if instance_info:
                    metadata_db = self.metadata_manager._get_metadata_db(
                        instance_info['name']
                    )
                    if metadata_db:
                        semantic_learning_collection = metadata_db['semantic_learning']
                        await semantic_learning_collection.insert_one(feedback_record)
                        
        except Exception as e:
            self.logger.warning(f"记录语义学习历史失败: {e}")
    
    async def _trigger_semantic_correlation_analysis(self, instance_id: str, 
                                                   database_name: str, 
                                                   collection_name: str,
                                                   updated_fields: List[Dict]):
        """触发语义关联分析"""
        try:
            # 寻找相似字段并建议语义关联
            for field_update in updated_fields:
                field_path = field_update["field_path"]
                new_meaning = field_update["new_meaning"]
                
                # 查找相似字段
                similar_fields = await self.metadata_manager.search_fields_by_meaning(
                    instance_id, new_meaning
                )
                
                # 如果找到相似但语义为空的字段，建议更新
                for similar_field in similar_fields:
                    if (not similar_field.get("business_meaning") or 
                        similar_field.get("business_meaning") == "未知"):
                        
                        self.logger.info(
                            "发现可能需要语义关联的字段",
                            similar_field_path=similar_field["field_path"],
                            database=similar_field["database_name"],
                            collection=similar_field["collection_name"],
                            suggested_meaning=new_meaning
                        )
                
        except Exception as e:
            self.logger.warning(f"语义关联分析失败: {e}")