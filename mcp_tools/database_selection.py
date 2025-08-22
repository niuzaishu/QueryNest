# -*- coding: utf-8 -*-
"""数据库选择工具 - 支持智能推荐+用户确认"""

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


class DatabaseSelectionTool:
    """数据库选择工具 - 支持推荐+确认模式"""
    
    def __init__(self, connection_manager: ConnectionManager, metadata_manager: MetadataManager):
        self.connection_manager = connection_manager
        self.metadata_manager = metadata_manager
        self.context_manager = get_context_manager()
        self.workflow_manager = get_workflow_manager()
    
    def get_tool_definition(self) -> Tool:
        """获取工具定义"""
        return Tool(
            name="select_database",
            description="智能数据库选择工具：自动发现数据库并提供推荐选项，需要用户确认后执行",
            inputSchema={
                "type": "object",
                "properties": {
                    "instance_id": {
                        "type": "string",
                        "description": "MongoDB实例ID（可选，会从工作流上下文自动获取）"
                    },
                    "database_name": {
                        "type": "string",
                        "description": "要选择的数据库名称（可选，如果不提供则显示推荐选项）"
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
    
    @with_error_handling("数据库选择")
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """执行数据库选择"""
        session_id = arguments.get("session_id", "default")
        instance_id = arguments.get("instance_id")
        database_name = arguments.get("database_name")
        user_choice = arguments.get("user_choice")
        show_recommendations = arguments.get("show_recommendations", False)
        
        # 从工作流上下文获取instance_id（如果没有提供）
        if not instance_id:
            workflow_data = await self.workflow_manager.get_workflow_data(session_id)
            instance_id = workflow_data.get("instance_id")
            
            if not instance_id:
                return [TextContent(
                    type="text",
                    text="## ❌ 缺少实例信息\n\n请先选择MongoDB实例，或在参数中提供 `instance_id`。"
                )]
        
        # 验证实例存在
        if not self.connection_manager.has_instance(instance_id):
            return [TextContent(
                type="text",
                text=f"## ❌ 实例不存在\n\n实例 `{instance_id}` 不存在。请先使用 `select_instance()` 选择有效实例。"
            )]
        
        # 获取数据库列表
        try:
            databases = await self._get_databases(instance_id)
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"## ❌ 获取数据库列表失败\n\n错误: {str(e)}"
            )]
        
        if not databases:
            return [TextContent(
                type="text",
                text=f"## ❌ 未发现数据库\n\n实例 `{instance_id}` 中没有可用的数据库。"
            )]
        
        # 情况1：直接指定了database_name，进行选择
        if database_name and not show_recommendations:
            return await self._execute_selection(database_name, instance_id, session_id, databases)
        
        # 情况2：需要显示推荐选项
        if not user_choice:
            return await self._show_recommendations(databases, instance_id, session_id)
        
        # 情况3：用户已做出选择，处理选择
        return await self._handle_user_choice(user_choice, databases, instance_id, session_id)
    
    async def _get_databases(self, instance_id: str, filter_system: bool = True) -> List[Dict[str, Any]]:
        """获取数据库列表"""
        connection = self.connection_manager.get_instance_connection(instance_id)
        if not connection or not connection.client:
            raise ValueError(f"实例 {instance_id} 连接不可用")
        
        client = connection.client
        db_names = await client.list_database_names()
        
        # 过滤系统数据库
        if filter_system:
            system_dbs = {'admin', 'local', 'config'}
            db_names = [name for name in db_names if name not in system_dbs]
        
        databases = []
        for db_name in db_names:
            db_info = {
                "database_name": db_name,
                "description": f"数据库 {db_name}"
            }
            
            # 获取集合数量
            try:
                db = client[db_name]
                collections = await db.list_collection_names()
                db_info["collection_count"] = len(collections)
                
                # 计算总文档数（采样前几个集合）
                total_docs = 0
                for coll_name in collections[:5]:  # 只统计前5个集合，避免耗时过长
                    try:
                        doc_count = await db[coll_name].count_documents({})
                        total_docs += doc_count
                    except Exception:
                        pass
                
                db_info["estimated_document_count"] = total_docs
                
            except Exception as e:
                logger.warning(f"获取数据库 {db_name} 信息失败", error=str(e))
                db_info["collection_count"] = 0
                db_info["estimated_document_count"] = 0
            
            databases.append(db_info)
        
        # 按集合数量和文档数量排序，活跃的数据库排在前面
        databases.sort(
            key=lambda x: (x.get("collection_count", 0), x.get("estimated_document_count", 0)), 
            reverse=True
        )
        
        return databases
    
    async def _show_recommendations(self, databases: List[Dict[str, Any]], 
                                  instance_id: str, session_id: str) -> List[TextContent]:
        """显示推荐选项"""
        logger.info("显示数据库推荐选项", 
                   session_id=session_id, 
                   instance_id=instance_id, 
                   database_count=len(databases))
        
        return [UserConfirmationHelper.create_database_selection_prompt(databases, instance_id)]
    
    async def _handle_user_choice(self, user_choice: str, databases: List[Dict[str, Any]], 
                                instance_id: str, session_id: str) -> List[TextContent]:
        """处理用户选择"""
        database_names = [db["database_name"] for db in databases]
        
        # 处理特殊选择
        choice_upper = user_choice.upper()
        
        if choice_upper in ['Z', 'CANCEL']:
            return [TextContent(type="text", text="## ❌ 已取消数据库选择")]
        
        if choice_upper in ['B', 'VIEW', 'DETAILS']:
            # 显示详细信息后再次显示推荐
            return await self._show_detailed_databases(databases, instance_id, session_id)
        
        # 解析用户选择
        is_valid, selected_database, error_msg = ConfirmationParser.parse_selection(
            user_choice, database_names
        )
        
        if not is_valid:
            error_text = f"## ❌ 选择无效\n\n{error_msg}\n\n"
            error_text += "请重新选择或使用 `select_database(show_recommendations=True)` 查看选项。"
            return [TextContent(type="text", text=error_text)]
        
        # 执行选择
        return await self._execute_selection(selected_database, instance_id, session_id, databases)
    
    async def _show_detailed_databases(self, databases: List[Dict[str, Any]], 
                                     instance_id: str, session_id: str) -> List[TextContent]:
        """显示详细数据库信息"""
        text = f"## 📋 实例 `{instance_id}` 的详细数据库信息\n\n"
        
        for i, db_info in enumerate(databases, 1):
            db_name = db_info["database_name"]
            
            text += f"### {chr(64+i)}) {db_name}\n"
            text += f"- **数据库名**: `{db_name}`\n"
            text += f"- **集合数量**: {db_info.get('collection_count', '未知')}\n"
            text += f"- **估计文档数**: {db_info.get('estimated_document_count', '未知')}\n"
            
            if db_info.get("description"):
                text += f"- **描述**: {db_info['description']}\n"
            
            text += "\n"
        
        text += "### 📋 请选择数据库\n\n"
        for i, db_info in enumerate(databases, 1):
            db_name = db_info["database_name"]
            text += f"**{chr(64+i)}) 选择** `{db_name}`\n"
        
        text += "**Z) ❌ 取消选择**\n\n"
        text += "💡 **提示**: 输入字母（如A、B）来选择对应的数据库"
        
        return [TextContent(type="text", text=text)]
    
    async def _execute_selection(self, database_name: str, instance_id: str, 
                               session_id: str, databases: List[Dict[str, Any]]) -> List[TextContent]:
        """执行数据库选择"""
        logger.info("执行数据库选择", 
                   database_name=database_name, 
                   instance_id=instance_id, 
                   session_id=session_id)
        
        # 验证数据库存在
        db_names = [db["database_name"] for db in databases]
        if database_name not in db_names:
            available = ', '.join(db_names)
            return [TextContent(
                type="text",
                text=f"## ❌ 数据库不存在\n\n数据库 `{database_name}` 在实例 `{instance_id}` 中不存在。\n\n**可用数据库**: {available}"
            )]
        
        # 获取数据库详细信息
        selected_db = next((db for db in databases if db["database_name"] == database_name), None)
        
        # 更新工作流状态
        update_data = {
            "instance_id": instance_id,
            "database_name": database_name
        }
        
        success, message = await self.workflow_manager.transition_to(
            session_id, 
            WorkflowStage.DATABASE_SELECTION, 
            update_data
        )
        
        if not success:
            return [TextContent(
                type="text",
                text=f"## ❌ 工作流更新失败\n\n{message}"
            )]
        
        # 构建成功响应
        result_text = f"## ✅ 数据库选择成功\n\n"
        result_text += f"**选择的数据库**: `{database_name}`\n"
        result_text += f"**所属实例**: `{instance_id}`\n"
        
        if selected_db:
            result_text += f"**集合数量**: {selected_db.get('collection_count', '未知')}\n"
            result_text += f"**估计文档数**: {selected_db.get('estimated_document_count', '未知')}\n"
        
        result_text += f"\n**工作流状态**: {message}\n\n"
        
        # 下一步建议
        result_text += "## 🎯 下一步操作\n\n"
        result_text += "现在可以继续以下操作：\n"
        result_text += f"- `analyze_collection(instance_id=\"{instance_id}\", database_name=\"{database_name}\", collection_name=\"...\")` - 分析特定集合\n"
        result_text += f"- `select_collection()` - 智能集合选择\n"
        result_text += "- `workflow_status()` - 查看工作流状态\n"
        
        logger.info("数据库选择完成", 
                   database_name=database_name, 
                   instance_id=instance_id, 
                   session_id=session_id)
        
        return [TextContent(type="text", text=result_text)]