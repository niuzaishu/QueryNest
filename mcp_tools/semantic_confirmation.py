# -*- coding: utf-8 -*-
"""
交互式语义确认工具
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


class SemanticConfirmationTool:
    """交互式语义确认工具"""
    
    def __init__(self, connection_manager: ConnectionManager, 
                 metadata_manager: MetadataManager, 
                 semantic_analyzer: SemanticAnalyzer):
        self.connection_manager = connection_manager
        self.metadata_manager = metadata_manager
        self.semantic_analyzer = semantic_analyzer
        self.logger = logger.bind(component="SemanticConfirmationTool")
    
    def get_tool_definition(self) -> Tool:
        return Tool(
            name="semantic_confirmation",
            description="获取和确认待定的字段语义信息",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["get_pending", "confirm_batch", "reject_suggestions"],
                        "description": "操作类型：get_pending=获取待确认项，confirm_batch=批量确认，reject_suggestions=拒绝建议"
                    },
                    "instance_id": {
                        "type": "string",
                        "description": "MongoDB实例ID"
                    },
                    "database_name": {
                        "type": "string",
                        "description": "数据库名称（可选，用于筛选）"
                    },
                    "collection_name": {
                        "type": "string",
                        "description": "集合名称（可选，用于筛选）"
                    },
                    "confidence_threshold": {
                        "type": "number",
                        "description": "置信度阈值，获取低于此值的待确认项",
                        "minimum": 0,
                        "maximum": 1,
                        "default": 0.6
                    },
                    "confirmations": {
                        "type": "array",
                        "description": "批量确认列表（用于confirm_batch操作）",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field_id": {
                                    "type": "string",
                                    "description": "字段ID"
                                },
                                "field_path": {
                                    "type": "string",
                                    "description": "字段路径"
                                },
                                "database_name": {
                                    "type": "string",
                                    "description": "数据库名称"
                                },
                                "collection_name": {
                                    "type": "string",
                                    "description": "集合名称"
                                },
                                "confirmed_meaning": {
                                    "type": "string",
                                    "description": "确认的语义含义"
                                },
                                "action": {
                                    "type": "string",
                                    "enum": ["confirm", "reject", "modify"],
                                    "description": "确认动作：confirm=确认建议，reject=拒绝建议，modify=修改为自定义含义"
                                }
                            },
                            "required": ["field_path", "database_name", "collection_name", "action"]
                        }
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
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """执行语义确认操作"""
        action = arguments["action"]
        instance_id = arguments["instance_id"]
        
        try:
            if action == "get_pending":
                return await self._get_pending_confirmations(arguments)
            elif action == "confirm_batch":
                return await self._confirm_batch(arguments)
            elif action == "reject_suggestions":
                return await self._reject_suggestions(arguments)
            else:
                return [TextContent(
                    type="text",
                    text=f"❌ 不支持的操作: {action}"
                )]
                
        except Exception as e:
            error_msg = f"语义确认操作失败: {str(e)}"
            self.logger.error(error_msg, action=action, error=str(e))
            return [TextContent(type="text", text=f"❌ {error_msg}")]
    
    async def _get_pending_confirmations(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """获取待确认的语义项"""
        instance_id = arguments["instance_id"]
        database_name = arguments.get("database_name")
        collection_name = arguments.get("collection_name")
        confidence_threshold = arguments.get("confidence_threshold", 0.6)
        limit = arguments.get("limit", 20)
        
        # 验证实例存在
        instance_info = await self.metadata_manager.get_instance_by_name(instance_id, instance_id)
        if not instance_info:
            return [TextContent(
                type="text",
                text=f"❌ 未找到实例 {instance_id}"
            )]
        
        # 获取待确认的字段
        pending_items = await self._get_uncertain_semantics(
            instance_id, database_name, collection_name, confidence_threshold, limit
        )
        
        if not pending_items:
            result_text = f"## 语义确认状态\n\n"
            result_text += f"- **实例**: {instance_info.get('name', instance_id)}\n"
            result_text += f"- **置信度阈值**: < {confidence_threshold}\n"
            result_text += f"- **待确认项**: 暂无\n\n"
            result_text += f"🎉 所有字段的语义置信度都已达到阈值要求！\n"
            
            return [TextContent(type="text", text=result_text)]
        
        # 格式化显示待确认项
        result_text = f"## 待确认的字段语义 ({len(pending_items)} 项)\n\n"
        result_text += f"- **实例**: {instance_info.get('name', instance_id)}\n"
        result_text += f"- **置信度阈值**: < {confidence_threshold}\n\n"
        
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
                result_text += f"   - 置信度: {confidence:.2f}\n"
                
                # 显示示例值（如果有）
                examples = item.get('examples', [])
                if examples:
                    examples_str = ', '.join(str(ex) for ex in examples[:3])
                    result_text += f"   - 示例值: {examples_str}\n"
                
                result_text += f"\n"
        
        # 提供批量确认示例
        result_text += f"### 📝 批量确认示例\n\n"
        result_text += f"使用 `semantic_confirmation` 工具进行批量确认：\n\n"
        result_text += f"```json\n"
        result_text += f"{{\n"
        result_text += f'  "action": "confirm_batch",\n'
        result_text += f'  "instance_id": "{instance_id}",\n'
        result_text += f'  "confirmations": [\n'
        
        # 生成前3个项目的确认示例
        sample_items = pending_items[:3]
        for i, item in enumerate(sample_items):
            result_text += f"    {{\n"
            result_text += f'      "field_path": "{item["field_path"]}",\n'
            result_text += f'      "database_name": "{item["database_name"]}",\n'
            result_text += f'      "collection_name": "{item["collection_name"]}",\n'
            result_text += f'      "action": "confirm",\n'
            result_text += f'      "confirmed_meaning": "{item.get("suggested_meaning", "自定义含义")}"\n'
            result_text += f"    }}{',' if i < len(sample_items) - 1 else ''}\n"
        
        result_text += f"  ]\n"
        result_text += f"}}\n"
        result_text += f"```\n"
        
        return [TextContent(type="text", text=result_text)]
    
    async def _confirm_batch(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """批量确认语义"""
        instance_id = arguments["instance_id"]
        confirmations = arguments.get("confirmations", [])
        
        if not confirmations:
            return [TextContent(
                type="text",
                text="❌ 未提供确认列表"
            )]
        
        # 验证实例存在
        instance_info = await self.metadata_manager.get_instance_by_name(instance_id, instance_id)
        if not instance_info:
            return [TextContent(
                type="text",
                text=f"❌ 未找到实例 {instance_id}"
            )]
        
        result_text = f"## 批量语义确认结果\n\n"
        result_text += f"- **实例**: {instance_info.get('name', instance_id)}\n"
        result_text += f"- **处理项目**: {len(confirmations)} 项\n\n"
        
        confirmed_count = 0
        rejected_count = 0
        modified_count = 0
        failed_count = 0
        
        for i, confirmation in enumerate(confirmations, 1):
            field_path = confirmation["field_path"]
            database_name = confirmation["database_name"]
            collection_name = confirmation["collection_name"]
            action = confirmation["action"]
            confirmed_meaning = confirmation.get("confirmed_meaning", "")
            
            try:
                result_text += f"### {i}. {database_name}.{collection_name}.{field_path}\n\n"
                
                if action == "confirm":
                    if confirmed_meaning:
                        success = await self.metadata_manager.update_field_semantics(
                            instance_id, database_name, collection_name, 
                            field_path, confirmed_meaning
                        )
                        if success:
                            confirmed_count += 1
                            result_text += f"✅ **已确认**: {confirmed_meaning}\n\n"
                        else:
                            failed_count += 1
                            result_text += f"❌ **确认失败**: 更新操作失败\n\n"
                    else:
                        failed_count += 1
                        result_text += f"❌ **确认失败**: 未提供确认含义\n\n"
                
                elif action == "modify":
                    if confirmed_meaning:
                        success = await self.metadata_manager.update_field_semantics(
                            instance_id, database_name, collection_name, 
                            field_path, confirmed_meaning
                        )
                        if success:
                            modified_count += 1
                            result_text += f"✏️ **已修改**: {confirmed_meaning}\n\n"
                        else:
                            failed_count += 1
                            result_text += f"❌ **修改失败**: 更新操作失败\n\n"
                    else:
                        failed_count += 1
                        result_text += f"❌ **修改失败**: 未提供新含义\n\n"
                
                elif action == "reject":
                    rejected_count += 1
                    result_text += f"⛔ **已拒绝**: 不更新此字段语义\n\n"
                    
                    # 可选：标记为已拒绝，避免重复出现在待确认列表中
                    await self._mark_semantic_rejected(
                        instance_id, database_name, collection_name, field_path
                    )
                
            except Exception as e:
                failed_count += 1
                result_text += f"❌ **处理异常**: {str(e)}\n\n"
                self.logger.error(
                    "语义确认处理失败",
                    field_path=field_path,
                    action=action,
                    error=str(e)
                )
        
        # 生成统计信息
        result_text += f"### 📊 处理统计\n\n"
        result_text += f"- **确认成功**: {confirmed_count} 项\n"
        result_text += f"- **修改成功**: {modified_count} 项\n"
        result_text += f"- **拒绝**: {rejected_count} 项\n"
        result_text += f"- **失败**: {failed_count} 项\n"
        
        total_updated = confirmed_count + modified_count
        if total_updated > 0:
            result_text += f"\n### 🎯 后续建议\n\n"
            result_text += f"语义更新完成后，建议：\n"
            result_text += f"1. 使用 `collection_analysis` 验证更新后的语义信息\n"
            result_text += f"2. 重新生成查询测试语义准确性\n"
            result_text += f"3. 检查相似字段是否也需要更新语义\n"
        
        self.logger.info(
            "批量语义确认完成",
            instance_id=instance_id,
            total_items=len(confirmations),
            confirmed=confirmed_count,
            modified=modified_count,
            rejected=rejected_count,
            failed=failed_count
        )
        
        return [TextContent(type="text", text=result_text)]
    
    async def _reject_suggestions(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """拒绝语义建议"""
        instance_id = arguments["instance_id"]
        database_name = arguments.get("database_name")
        collection_name = arguments.get("collection_name")
        
        # TODO: 实现批量拒绝逻辑
        result_text = f"## 语义建议拒绝\n\n"
        result_text += f"- **实例ID**: {instance_id}\n"
        
        if database_name:
            result_text += f"- **数据库**: {database_name}\n"
        if collection_name:
            result_text += f"- **集合**: {collection_name}\n"
        
        result_text += f"\n⚠️ 拒绝功能正在开发中...\n"
        
        return [TextContent(type="text", text=result_text)]
    
    async def _get_uncertain_semantics(self, instance_id: str, 
                                     database_name: Optional[str] = None,
                                     collection_name: Optional[str] = None,
                                     confidence_threshold: float = 0.6,
                                     limit: int = 20) -> List[Dict[str, Any]]:
        """获取置信度不够的字段语义"""
        try:
            collections = self.metadata_manager._get_instance_collections(instance_id)
            if not collections:
                return []
            
            # 构建查询条件
            query_filter = {
                "instance_id": instance_id,
                "$or": [
                    {"confidence": {"$lt": confidence_threshold}},
                    {"business_meaning": {"$in": [None, "", "未知"]}},
                    {"business_meaning": {"$exists": False}}
                ]
            }
            
            if database_name:
                query_filter["database_name"] = database_name
            if collection_name:
                query_filter["collection_name"] = collection_name
            
            cursor = collections['fields'].find(query_filter).limit(limit)
            uncertain_fields = await cursor.to_list(length=None)
            
            return uncertain_fields
            
        except Exception as e:
            self.logger.error(f"获取不确定语义字段失败: {e}")
            return []
    
    async def _mark_semantic_rejected(self, instance_id: str, database_name: str, 
                                    collection_name: str, field_path: str):
        """标记语义为已拒绝"""
        try:
            collections = self.metadata_manager._get_instance_collections(instance_id)
            if collections:
                await collections['fields'].update_one(
                    {
                        "instance_id": instance_id,
                        "database_name": database_name,
                        "collection_name": collection_name,
                        "field_path": field_path
                    },
                    {
                        "$set": {
                            "semantic_status": "rejected",
                            "rejected_at": datetime.now()
                        }
                    }
                )
        except Exception as e:
            self.logger.warning(f"标记语义拒绝状态失败: {e}")