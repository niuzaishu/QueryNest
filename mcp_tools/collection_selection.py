# -*- coding: utf-8 -*-
"""集合选择工具 - 支持智能推荐+用户确认"""

from typing import Dict, List, Any, Optional
import structlog
from mcp.types import Tool, TextContent

from database.connection_manager import ConnectionManager
from database.metadata_manager import MetadataManager
from utils.parameter_validator import ParameterValidator, MCPParameterHelper, ValidationResult
from utils.tool_context import get_context_manager
from utils.error_handler import with_error_handling, with_retry, RetryConfig
from utils.workflow_manager import get_workflow_manager, WorkflowStage
from utils.user_confirmation import UserConfirmationHelper, ConfirmationParser

logger = structlog.get_logger(__name__)


class CollectionSelectionTool:
    """集合选择工具 - 支持推荐+确认模式"""
    
    def __init__(self, connection_manager: ConnectionManager, metadata_manager: MetadataManager):
        self.connection_manager = connection_manager
        self.metadata_manager = metadata_manager
        self.context_manager = get_context_manager()
        self.workflow_manager = get_workflow_manager()
    
    def get_tool_definition(self) -> Tool:
        """获取工具定义"""
        return Tool(
            name="select_collection",
            description="智能集合选择工具：自动发现集合并提供推荐选项，需要用户确认后执行",
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
                        "description": "要选择的集合名称（可选，如果不提供则显示推荐选项）"
                    },
                    "session_id": {
                        "type": "string",
                        "description": "会话标识符，默认为'default'",
                        "default": "default"
                    },
                    "user_choice": {
                        "type": "string",
                        "description": "用户选择（A, B, C等），用于确认推荐选项"
                    },
                    "show_recommendations": {
                        "type": "boolean",
                        "description": "强制显示推荐选项",
                        "default": False
                    }
                },
                "required": []
            }
        )
    
    @with_error_handling("集合选择")
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """执行集合选择"""
        session_id = arguments.get("session_id", "default")
        instance_id = arguments.get("instance_id")
        database_name = arguments.get("database_name") 
        collection_name = arguments.get("collection_name")
        user_choice = arguments.get("user_choice")
        show_recommendations = arguments.get("show_recommendations", False)
        
        # 从工作流上下文获取缺失参数
        workflow_data = await self.workflow_manager.get_workflow_data(session_id)
        
        if not instance_id:
            instance_id = workflow_data.get("instance_id")
            
        if not database_name:
            database_name = workflow_data.get("database_name")
            
        # 验证必需参数
        if not instance_id:
            return [TextContent(
                type="text",
                text="## ❌ 缺少实例信息\n\n请先选择MongoDB实例，或在参数中提供 `instance_id`。"
            )]
            
        if not database_name:
            return [TextContent(
                type="text",
                text="## ❌ 缺少数据库信息\n\n请先选择数据库，或在参数中提供 `database_name`。"
            )]
        
        # 验证实例和数据库存在
        if not self.connection_manager.has_instance(instance_id):
            return [TextContent(
                type="text",
                text=f"## ❌ 实例不存在\n\n实例 `{instance_id}` 不存在。"
            )]
        
        # 获取集合列表
        try:
            collections = await self._get_collections(instance_id, database_name)
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"## ❌ 获取集合列表失败\n\n错误: {str(e)}"
            )]
        
        if not collections:
            return [TextContent(
                type="text",
                text=f"## ❌ 未发现集合\n\n数据库 `{database_name}` 中没有可用的集合。"
            )]
        
        # 情况1：直接指定了collection_name，进行选择
        if collection_name and not show_recommendations:
            return await self._execute_selection(collection_name, instance_id, database_name, session_id, collections)
        
        # 情况2：需要显示推荐选项
        if not user_choice:
            return await self._show_recommendations(collections, database_name, session_id)
        
        # 情况3：用户已做出选择，处理选择
        return await self._handle_user_choice(user_choice, collections, instance_id, database_name, session_id)
    
    async def _get_collections(self, instance_id: str, database_name: str) -> List[Dict[str, Any]]:
        """获取集合列表"""
        connection = self.connection_manager.get_instance_connection(instance_id)
        if not connection or not connection.client:
            raise ValueError(f"实例 {instance_id} 连接不可用")
        
        client = connection.client
        db = client[database_name]
        collection_names = await db.list_collection_names()
        
        collections = []
        for coll_name in collection_names:
            coll_info = {
                "collection_name": coll_name,
                "description": f"集合 {coll_name}"
            }
            
            # 获取集合的文档数量和基本信息
            try:
                collection = db[coll_name]
                doc_count = await collection.count_documents({})
                coll_info["document_count"] = doc_count
                
                # 获取一个示例文档来推测数据类型
                sample_doc = await collection.find_one()
                if sample_doc:
                    # 统计字段数量
                    field_count = len(sample_doc.keys()) if isinstance(sample_doc, dict) else 0
                    coll_info["estimated_field_count"] = field_count
                    
                    # 检查一些常见的业务字段来推测集合类型
                    business_indicators = []
                    if isinstance(sample_doc, dict):
                        keys_lower = [k.lower() for k in sample_doc.keys()]
                        
                        if any(k in keys_lower for k in ['user', 'account', 'customer']):
                            business_indicators.append("用户相关")
                        if any(k in keys_lower for k in ['order', 'transaction', 'payment']):
                            business_indicators.append("交易相关")
                        if any(k in keys_lower for k in ['log', 'event', 'audit']):
                            business_indicators.append("日志相关")
                        if any(k in keys_lower for k in ['config', 'setting', 'param']):
                            business_indicators.append("配置相关")
                    
                    coll_info["business_indicators"] = business_indicators
                else:
                    coll_info["estimated_field_count"] = 0
                    coll_info["business_indicators"] = []
                
            except Exception as e:
                logger.warning(f"获取集合 {coll_name} 信息失败", error=str(e))
                coll_info["document_count"] = "未知"
                coll_info["estimated_field_count"] = 0
                coll_info["business_indicators"] = []
            
            collections.append(coll_info)
        
        # 按文档数量排序，但优先考虑适中的数量（便于分析）
        def collection_priority(coll):
            doc_count = coll.get("document_count", 0)
            if isinstance(doc_count, str):
                return 0
            
            # 优先级：100-10000文档的集合最好，其次是更多文档的，最后是很少文档的
            if 100 <= doc_count <= 10000:
                return 10000 + doc_count  # 最高优先级
            elif doc_count > 10000:
                return doc_count  # 中等优先级
            else:
                return doc_count / 10  # 低优先级
        
        collections.sort(key=collection_priority, reverse=True)
        
        return collections
    
    async def _show_recommendations(self, collections: List[Dict[str, Any]], 
                                  database_name: str, session_id: str) -> List[TextContent]:
        """显示推荐选项"""
        logger.info("显示集合推荐选项", 
                   session_id=session_id, 
                   database_name=database_name, 
                   collection_count=len(collections))
        
        return [UserConfirmationHelper.create_collection_selection_prompt(collections, database_name)]
    
    async def _handle_user_choice(self, user_choice: str, collections: List[Dict[str, Any]], 
                                instance_id: str, database_name: str, session_id: str) -> List[TextContent]:
        """处理用户选择"""
        collection_names = [coll["collection_name"] for coll in collections]
        
        # 处理特殊选择
        choice_upper = user_choice.upper()
        
        if choice_upper in ['Z', 'CANCEL']:
            return [TextContent(type="text", text="## ❌ 已取消集合选择")]
        
        if choice_upper in ['B', 'VIEW', 'DETAILS']:
            return await self._show_detailed_collections(collections, database_name, session_id)
        
        if choice_upper in ['M', 'MORE']:
            return await self._show_more_collections(collections, database_name, session_id)
        
        # 解析用户选择
        display_collections = collections[:10]  # 只显示前10个
        display_names = [coll["collection_name"] for coll in display_collections]
        
        is_valid, selected_collection, error_msg = ConfirmationParser.parse_selection(
            user_choice, display_names
        )
        
        if not is_valid:
            error_text = f"## ❌ 选择无效\n\n{error_msg}\n\n"
            error_text += "请重新选择或使用 `select_collection(show_recommendations=True)` 查看选项。"
            return [TextContent(type="text", text=error_text)]
        
        # 执行选择
        return await self._execute_selection(selected_collection, instance_id, database_name, session_id, collections)
    
    async def _show_detailed_collections(self, collections: List[Dict[str, Any]], 
                                       database_name: str, session_id: str) -> List[TextContent]:
        """显示详细集合信息"""
        text = f"## 📋 数据库 `{database_name}` 的详细集合信息\n\n"
        
        display_collections = collections[:10]
        for i, coll_info in enumerate(display_collections, 1):
            coll_name = coll_info["collection_name"]
            
            text += f"### {chr(64+i)}) {coll_name}\n"
            text += f"- **集合名**: `{coll_name}`\n"
            text += f"- **文档数量**: {coll_info.get('document_count', '未知')}\n"
            text += f"- **估计字段数**: {coll_info.get('estimated_field_count', '未知')}\n"
            
            business_indicators = coll_info.get('business_indicators', [])
            if business_indicators:
                text += f"- **业务类型**: {', '.join(business_indicators)}\n"
            
            if coll_info.get("description"):
                text += f"- **描述**: {coll_info['description']}\n"
            
            text += "\n"
        
        if len(collections) > 10:
            text += f"*... 还有 {len(collections) - 10} 个集合*\n\n"
        
        text += "### 📋 请选择集合\n\n"
        for i, coll_info in enumerate(display_collections, 1):
            coll_name = coll_info["collection_name"]
            text += f"**{chr(64+i)}) 选择** `{coll_name}`\n"
        
        if len(collections) > 10:
            text += "**M) 🔍 查看更多集合**\n"
        text += "**Z) ❌ 取消选择**\n\n"
        text += "💡 **提示**: 输入字母（如A、B）来选择对应的集合"
        
        return [TextContent(type="text", text=text)]
    
    async def _show_more_collections(self, collections: List[Dict[str, Any]], 
                                   database_name: str, session_id: str) -> List[TextContent]:
        """显示更多集合"""
        text = f"## 📋 数据库 `{database_name}` 的完整集合列表\n\n"
        
        for i, coll_info in enumerate(collections, 1):
            coll_name = coll_info["collection_name"]
            doc_count = coll_info.get('document_count', '未知')
            text += f"{i:2d}. **{coll_name}** ({doc_count} 文档)\n"
        
        text += "\n### 📋 请选择集合\n\n"
        text += "**输入集合的序号或名称**，例如：\n"
        text += "- `select_collection(collection_name=\"集合名称\")`\n"
        text += "- 或重新使用 `select_collection()` 进入推荐模式\n"
        
        return [TextContent(type="text", text=text)]
    
    async def _execute_selection(self, collection_name: str, instance_id: str, database_name: str,
                               session_id: str, collections: List[Dict[str, Any]]) -> List[TextContent]:
        """执行集合选择"""
        logger.info("执行集合选择", 
                   collection_name=collection_name, 
                   database_name=database_name,
                   instance_id=instance_id, 
                   session_id=session_id)
        
        # 验证集合存在
        coll_names = [coll["collection_name"] for coll in collections]
        if collection_name not in coll_names:
            available = ', '.join(coll_names[:5])  # 显示前5个
            return [TextContent(
                type="text",
                text=f"## ❌ 集合不存在\n\n集合 `{collection_name}` 在数据库 `{database_name}` 中不存在。\n\n**可用集合** (前5个): {available}"
            )]
        
        # 获取集合详细信息
        selected_coll = next((coll for coll in collections if coll["collection_name"] == collection_name), None)
        
        # 更新工作流状态
        update_data = {
            "instance_id": instance_id,
            "database_name": database_name,
            "collection_name": collection_name
        }
        
        success, message = await self.workflow_manager.transition_to(
            session_id, 
            WorkflowStage.COLLECTION_SELECTION, 
            update_data
        )
        
        if not success:
            return [TextContent(
                type="text",
                text=f"## ❌ 工作流更新失败\n\n{message}"
            )]
        
        # 构建成功响应
        result_text = f"## ✅ 集合选择成功\n\n"
        result_text += f"**选择的集合**: `{collection_name}`\n"
        result_text += f"**所属数据库**: `{database_name}`\n"
        result_text += f"**所属实例**: `{instance_id}`\n"
        
        if selected_coll:
            result_text += f"**文档数量**: {selected_coll.get('document_count', '未知')}\n"
            result_text += f"**估计字段数**: {selected_coll.get('estimated_field_count', '未知')}\n"
            
            business_indicators = selected_coll.get('business_indicators', [])
            if business_indicators:
                result_text += f"**业务类型**: {', '.join(business_indicators)}\n"
        
        result_text += f"\n**工作流状态**: {message}\n\n"
        
        # 下一步建议
        result_text += "## 🎯 下一步操作\n\n"
        result_text += "现在可以继续以下操作：\n"
        result_text += f"- `analyze_collection(instance_id=\"{instance_id}\", database_name=\"{database_name}\", collection_name=\"{collection_name}\")` - 分析集合结构\n"
        result_text += f"- `generate_query()` - 智能查询生成\n"
        result_text += "- `workflow_status()` - 查看工作流状态\n"
        
        logger.info("集合选择完成", 
                   collection_name=collection_name,
                   database_name=database_name, 
                   instance_id=instance_id, 
                   session_id=session_id)
        
        return [TextContent(type="text", text=result_text)]