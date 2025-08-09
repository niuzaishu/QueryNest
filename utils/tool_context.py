# -*- coding: utf-8 -*-
"""工具执行上下文管理器"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass


@dataclass
class ToolExecutionContext:
    """工具执行上下文"""
    instance_id: Optional[str] = None
    database_name: Optional[str] = None
    collection_name: Optional[str] = None
    connection_manager: Any = None
    metadata_manager: Any = None
    query_engine: Any = None
    semantic_analyzer: Any = None
    user_session_id: Optional[str] = None
    tool_chain: list = None  # 工具调用链，用于上下文推断
    
    def __post_init__(self):
        if self.tool_chain is None:
            self.tool_chain = []
    
    def clone_with_updates(self, **updates) -> "ToolExecutionContext":
        """克隆上下文并更新指定字段"""
        data = {
            'instance_id': self.instance_id,
            'database_name': self.database_name,
            'collection_name': self.collection_name,
            'connection_manager': self.connection_manager,
            'metadata_manager': self.metadata_manager,
            'query_engine': self.query_engine,
            'semantic_analyzer': self.semantic_analyzer,
            'user_session_id': self.user_session_id,
            'tool_chain': self.tool_chain.copy()
        }
        data.update(updates)
        return ToolExecutionContext(**data)
    
    def add_to_chain(self, tool_name: str, arguments: Dict[str, Any]):
        """添加工具调用到链中"""
        self.tool_chain.append({
            'tool_name': tool_name,
            'arguments': arguments
        })
    
    def get_last_tool_call(self) -> Optional[Dict[str, Any]]:
        """获取最后一次工具调用"""
        return self.tool_chain[-1] if self.tool_chain else None
    
    def infer_missing_parameters(self) -> Dict[str, Any]:
        """从工具链推断可能缺失的参数"""
        inferred = {}
        
        # 从最近的工具调用中推断参数
        for call in reversed(self.tool_chain):
            arguments = call.get('arguments', {})
            
            # 推断实例ID
            if not inferred.get('instance_id') and arguments.get('instance_id'):
                inferred['instance_id'] = arguments['instance_id']
            
            # 推断数据库名称
            if not inferred.get('database_name') and arguments.get('database_name'):
                inferred['database_name'] = arguments['database_name']
            
            # 推断集合名称
            if not inferred.get('collection_name') and arguments.get('collection_name'):
                inferred['collection_name'] = arguments['collection_name']
        
        # 也从当前上下文中推断
        if self.instance_id and not inferred.get('instance_id'):
            inferred['instance_id'] = self.instance_id
        if self.database_name and not inferred.get('database_name'):
            inferred['database_name'] = self.database_name
        if self.collection_name and not inferred.get('collection_name'):
            inferred['collection_name'] = self.collection_name
        
        return inferred
    
    def smart_infer_parameters(self, required_params: List[str]) -> Dict[str, Any]:
        """基于需求智能推断参数"""
        inferred = {}
        
        for param in required_params:
            if param == 'instance_id' and not inferred.get('instance_id'):
                inferred['instance_id'] = self._infer_instance_id()
            elif param == 'database_name' and not inferred.get('database_name'):
                inferred['database_name'] = self._infer_database_name()
            elif param == 'collection_name' and not inferred.get('collection_name'):
                inferred['collection_name'] = self._infer_collection_name()
        
        return inferred
    
    def _infer_instance_id(self) -> Optional[str]:
        """推断实例ID"""
        # 优先从当前上下文
        if self.instance_id:
            return self.instance_id
        
        # 从工具链历史推断
        for call in reversed(self.tool_chain):
            instance_id = call.get('arguments', {}).get('instance_id')
            if instance_id:
                return instance_id
        
        return None
    
    def _infer_database_name(self) -> Optional[str]:
        """推断数据库名称"""
        # 优先从当前上下文
        if self.database_name:
            return self.database_name
        
        # 从工具链历史推断
        for call in reversed(self.tool_chain):
            database_name = call.get('arguments', {}).get('database_name')
            if database_name:
                return database_name
        
        return None
    
    def _infer_collection_name(self) -> Optional[str]:
        """推断集合名称"""
        # 优先从当前上下文
        if self.collection_name:
            return self.collection_name
        
        # 从工具链历史推断
        for call in reversed(self.tool_chain):
            collection_name = call.get('arguments', {}).get('collection_name')
            if collection_name:
                return collection_name
        
        return None
    
    def is_instance_context_available(self) -> bool:
        """检查是否有实例上下文"""
        return bool(self.instance_id and self.connection_manager)
    
    def is_database_context_available(self) -> bool:
        """检查是否有数据库上下文"""
        return bool(self.is_instance_context_available() and self.database_name)
    
    def is_collection_context_available(self) -> bool:
        """检查是否有集合上下文"""
        return bool(self.is_database_context_available() and self.collection_name)


class ToolContextManager:
    """工具上下文管理器"""
    
    def __init__(self):
        self._contexts: Dict[str, ToolExecutionContext] = {}
    
    def get_or_create_context(self, session_id: str = "default") -> ToolExecutionContext:
        """获取或创建工具上下文"""
        if session_id not in self._contexts:
            self._contexts[session_id] = ToolExecutionContext(user_session_id=session_id)
        return self._contexts[session_id]
    
    def update_context(self, session_id: str = "default", **updates) -> ToolExecutionContext:
        """更新工具上下文"""
        context = self.get_or_create_context(session_id)
        updated_context = context.clone_with_updates(**updates)
        self._contexts[session_id] = updated_context
        return updated_context
    
    def clear_context(self, session_id: str = "default"):
        """清除工具上下文"""
        if session_id in self._contexts:
            del self._contexts[session_id]
    
    def get_smart_suggestions(self, session_id: str = "default") -> Dict[str, Any]:
        """基于上下文提供智能建议"""
        context = self.get_or_create_context(session_id)
        suggestions = {}
        
        # 基于工具链历史提供建议
        last_call = context.get_last_tool_call()
        if last_call:
            tool_name = last_call['tool_name']
            
            # 根据上一次工具调用提供相关建议
            if tool_name == "discover_instances":
                suggestions['next_actions'] = [
                    "使用 discover_databases 探索特定实例的数据库",
                    "使用 analyze_collection 分析集合结构"
                ]
            elif tool_name == "discover_databases":
                suggestions['next_actions'] = [
                    "使用 analyze_collection 分析感兴趣的集合",
                    "使用 generate_query 生成查询语句"
                ]
            elif tool_name == "analyze_collection":
                suggestions['next_actions'] = [
                    "使用 generate_query 基于字段结构生成查询",
                    "使用 manage_semantics 管理字段的业务含义"
                ]
            elif tool_name == "generate_query":
                suggestions['next_actions'] = [
                    "使用 confirm_query 执行生成的查询",
                    "如果查询不符合预期，可以重新生成"
                ]
        
        # 提供参数建议
        inferred_params = context.infer_missing_parameters()
        if inferred_params:
            suggestions['inferred_parameters'] = inferred_params
        
        return suggestions


# 全局上下文管理器实例
global_context_manager = ToolContextManager()


def get_context_manager() -> ToolContextManager:
    """获取全局上下文管理器"""
    return global_context_manager