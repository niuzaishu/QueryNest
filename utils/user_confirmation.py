# -*- coding: utf-8 -*-
"""用户确认机制 - 为关键决策点提供智能推荐和用户确认"""

from typing import Dict, List, Any, Optional, Tuple
import structlog
from mcp.types import TextContent

logger = structlog.get_logger(__name__)


class UserConfirmationHelper:
    """用户确认辅助工具"""
    
    @staticmethod
    def create_instance_selection_prompt(instances: Dict[str, Any], 
                                       context: Dict[str, Any] = None) -> TextContent:
        """创建实例选择确认提示"""
        if len(instances) == 1:
            # 单个实例，推荐自动选择但仍需确认
            instance_id = list(instances.keys())[0]
            instance_config = list(instances.values())[0]
            
            # 兼容字典和对象格式
            name = getattr(instance_config, 'name', None) or instance_config.get('name') if isinstance(instance_config, dict) else getattr(instance_config, 'name', None) or instance_id
            environment = getattr(instance_config, 'environment', None) or instance_config.get('environment') if isinstance(instance_config, dict) else getattr(instance_config, 'environment', None) or 'unknown'
            description = getattr(instance_config, 'description', None) or instance_config.get('description') if isinstance(instance_config, dict) else getattr(instance_config, 'description', None) or '无描述'
            
            text = f"## 🎯 实例选择确认\n\n"
            text += f"**检测到唯一可用实例**，建议选择：\n\n"
            text += f"**推荐实例**: {name}\n"
            text += f"- **实例ID**: `{instance_id}`\n"
            text += f"- **环境**: {environment}\n"
            text += f"- **描述**: {description}\n\n"
            
            text += "### 📋 确认选项\n\n"
            text += f"**A) ✅ 确认选择** `{instance_id}`\n"
            text += "**B) 🔄 查看所有实例详情**\n"
            text += "**C) ❌ 取消选择**\n\n"
            
            text += f"💡 **建议**: 选择 A 继续，使用实例 `{instance_id}`"
            
        else:
            # 多个实例，需要用户选择
            text = f"## 🤔 实例选择确认\n\n"
            text += f"**检测到 {len(instances)} 个可用实例**，请选择一个：\n\n"
            
            # 推荐逻辑：优先推荐dev环境，其次是健康状态好的
            recommended_id = UserConfirmationHelper._recommend_instance(instances)
            
            for i, (instance_id, instance_config) in enumerate(instances.items(), 1):
                is_recommended = instance_id == recommended_id
                marker = "⭐ **推荐** " if is_recommended else ""
                
                # 兼容字典和对象格式
                name = getattr(instance_config, 'name', None) or instance_config.get('name') if isinstance(instance_config, dict) else getattr(instance_config, 'name', None) or instance_id
                environment = getattr(instance_config, 'environment', None) or instance_config.get('environment') if isinstance(instance_config, dict) else getattr(instance_config, 'environment', None) or 'unknown'
                status = getattr(instance_config, 'status', None) or instance_config.get('status') if isinstance(instance_config, dict) else getattr(instance_config, 'status', None) or 'unknown'
                description = getattr(instance_config, 'description', None) or instance_config.get('description') if isinstance(instance_config, dict) else getattr(instance_config, 'description', None)
                
                text += f"**{chr(64+i)}) {marker}{name}**\n"
                text += f"   - 实例ID: `{instance_id}`\n"
                text += f"   - 环境: {environment}\n"
                text += f"   - 状态: {status}\n"
                if description:
                    text += f"   - 描述: {description}\n"
                text += "\n"
            
            text += "### 📋 选择选项\n\n"
            for i, (instance_id, _) in enumerate(instances.items(), 1):
                text += f"**{chr(64+i)}) 选择** `{instance_id}`\n"
            
            text += "**Z) ❌ 取消选择**\n\n"
            
            if recommended_id:
                text += f"💡 **推荐**: 选择 A，使用 `{recommended_id}` (开发环境，便于测试)"
        
        return TextContent(type="text", text=text)
    
    @staticmethod
    def create_database_selection_prompt(databases: List[Dict[str, Any]], 
                                       instance_id: str,
                                       context: Dict[str, Any] = None) -> TextContent:
        """创建数据库选择确认提示"""
        if len(databases) == 1:
            # 单个数据库，推荐自动选择但仍需确认
            db_info = databases[0]
            db_name = db_info["database_name"]
            
            text = f"## 🎯 数据库选择确认\n\n"
            text += f"**在实例 `{instance_id}` 中检测到唯一数据库**，建议选择：\n\n"
            text += f"**推荐数据库**: {db_name}\n"
            if db_info.get("collection_count"):
                text += f"- **集合数量**: {db_info['collection_count']}\n"
            if db_info.get("description"):
                text += f"- **描述**: {db_info['description']}\n"
            text += "\n"
            
            text += "### 📋 确认选项\n\n"
            text += f"**A) ✅ 确认选择** `{db_name}`\n"
            text += "**B) 🔄 查看数据库详情**\n"
            text += "**C) ❌ 取消选择**\n\n"
            
            text += f"💡 **建议**: 选择 A 继续，使用数据库 `{db_name}`"
            
        else:
            # 多个数据库，需要用户选择
            text = f"## 🤔 数据库选择确认\n\n"
            text += f"**在实例 `{instance_id}` 中检测到 {len(databases)} 个数据库**，请选择一个：\n\n"
            
            # 推荐逻辑：优先推荐数据量大的，活跃的数据库
            recommended_db = UserConfirmationHelper._recommend_database(databases)
            
            for i, db_info in enumerate(databases, 1):
                db_name = db_info["database_name"]
                is_recommended = db_name == recommended_db
                marker = "⭐ **推荐** " if is_recommended else ""
                
                text += f"**{chr(64+i)}) {marker}{db_name}**\n"
                if db_info.get("collection_count"):
                    text += f"   - 集合数量: {db_info['collection_count']}\n"
                if db_info.get("description"):
                    text += f"   - 描述: {db_info['description']}\n"
                text += "\n"
            
            text += "### 📋 选择选项\n\n"
            for i, db_info in enumerate(databases, 1):
                db_name = db_info["database_name"]
                text += f"**{chr(64+i)}) 选择** `{db_name}`\n"
            
            text += "**Z) ❌ 取消选择**\n\n"
            
            if recommended_db:
                text += f"💡 **推荐**: 选择 A，使用 `{recommended_db}` (数据量最大，可能最活跃)"
        
        return TextContent(type="text", text=text)
    
    @staticmethod
    def create_collection_selection_prompt(collections: List[Dict[str, Any]], 
                                         database_name: str,
                                         context: Dict[str, Any] = None) -> TextContent:
        """创建集合选择确认提示"""
        if len(collections) == 1:
            # 单个集合，推荐自动选择但仍需确认
            coll_info = collections[0]
            coll_name = coll_info["collection_name"]
            
            text = f"## 🎯 集合选择确认\n\n"
            text += f"**在数据库 `{database_name}` 中检测到唯一集合**，建议选择：\n\n"
            text += f"**推荐集合**: {coll_name}\n"
            if coll_info.get("document_count"):
                text += f"- **文档数量**: {coll_info['document_count']}\n"
            if coll_info.get("description"):
                text += f"- **描述**: {coll_info['description']}\n"
            text += "\n"
            
            text += "### 📋 确认选项\n\n"
            text += f"**A) ✅ 确认选择** `{coll_name}`\n"
            text += "**B) 🔄 查看集合详情**\n"
            text += "**C) ❌ 取消选择**\n\n"
            
            text += f"💡 **建议**: 选择 A 继续，分析集合 `{coll_name}`"
            
        else:
            # 多个集合，需要用户选择
            text = f"## 🤔 集合选择确认\n\n"
            text += f"**在数据库 `{database_name}` 中检测到 {len(collections)} 个集合**，请选择一个：\n\n"
            
            # 推荐逻辑：优先推荐文档数量适中的集合（不要太少也不要太多）
            recommended_coll = UserConfirmationHelper._recommend_collection(collections)
            
            # 显示前10个集合
            display_collections = collections[:10]
            for i, coll_info in enumerate(display_collections, 1):
                coll_name = coll_info["collection_name"]
                is_recommended = coll_name == recommended_coll
                marker = "⭐ **推荐** " if is_recommended else ""
                
                text += f"**{chr(64+i)}) {marker}{coll_name}**\n"
                if coll_info.get("document_count"):
                    text += f"   - 文档数量: {coll_info['document_count']}\n"
                if coll_info.get("description"):
                    text += f"   - 描述: {coll_info['description']}\n"
                text += "\n"
            
            if len(collections) > 10:
                text += f"   ... 还有 {len(collections) - 10} 个集合\n\n"
            
            text += "### 📋 选择选项\n\n"
            for i, coll_info in enumerate(display_collections, 1):
                coll_name = coll_info["collection_name"]
                text += f"**{chr(64+i)}) 选择** `{coll_name}`\n"
            
            if len(collections) > 10:
                text += "**M) 🔍 查看更多集合**\n"
            text += "**Z) ❌ 取消选择**\n\n"
            
            if recommended_coll:
                text += f"💡 **推荐**: 选择 A，使用 `{recommended_coll}` (文档数量适中，便于分析)"
        
        return TextContent(type="text", text=text)
    
    @staticmethod  
    def create_query_confirmation_prompt(query_info: Dict[str, Any],
                                       context: Dict[str, Any] = None) -> TextContent:
        """创建查询确认提示"""
        text = f"## 🔍 查询语句确认\n\n"
        text += f"**已生成以下MongoDB查询语句**，请确认后执行：\n\n"
        
        # 显示查询信息
        if query_info.get("description"):
            text += f"**查询描述**: {query_info['description']}\n"
        if query_info.get("query_type"):
            text += f"**查询类型**: {query_info['query_type']}\n"
        if query_info.get("collection_name"):
            text += f"**目标集合**: {query_info['collection_name']}\n"
        
        text += "\n### 📄 生成的查询语句\n\n"
        text += "```javascript\n"
        
        # 格式化显示查询语句
        if query_info.get("mongodb_query"):
            import json
            query_str = json.dumps(query_info["mongodb_query"], indent=2, ensure_ascii=False)
            text += query_str
        
        text += "\n```\n\n"
        
        # 显示预期结果
        if query_info.get("expected_result_count"):
            text += f"**预期结果数量**: 约 {query_info['expected_result_count']} 条\n"
        if query_info.get("limit"):
            text += f"**结果限制**: 最多返回 {query_info['limit']} 条\n"
        
        text += "\n### 📋 确认选项\n\n"
        text += "**A) ✅ 确认执行** 查询语句\n"
        text += "**B) 🔧 修改查询** (重新生成)\n"
        text += "**C) 📊 仅查看执行计划** (不获取数据)\n"
        text += "**D) ❌ 取消执行**\n\n"
        
        text += "💡 **建议**: 选择 A 执行查询，或选择 C 先查看执行计划"
        
        return TextContent(type="text", text=text)
    
    @staticmethod
    def _recommend_instance(instances: Dict[str, Any]) -> Optional[str]:
        """推荐最佳实例"""
        # 推荐逻辑：优先dev环境，其次看状态
        dev_instances = []
        active_instances = []
        
        for instance_id, config in instances.items():
            # 兼容字典和对象两种格式
            environment = getattr(config, 'environment', None) or config.get('environment') if isinstance(config, dict) else getattr(config, 'environment', None)
            status = getattr(config, 'status', None) or config.get('status') if isinstance(config, dict) else getattr(config, 'status', None)
            
            if environment == "dev":
                dev_instances.append(instance_id)
            if status == "active":
                active_instances.append(instance_id)
        
        if dev_instances:
            return dev_instances[0]
        elif active_instances:
            return active_instances[0]
        else:
            return list(instances.keys())[0]
    
    @staticmethod
    def _recommend_database(databases: List[Dict[str, Any]]) -> Optional[str]:
        """推荐最佳数据库"""
        # 推荐逻辑：优先数据量大的数据库
        if not databases:
            return None
        
        # 按集合数量排序，选择最多的
        sorted_dbs = sorted(databases, 
                          key=lambda x: x.get("collection_count", 0), 
                          reverse=True)
        return sorted_dbs[0]["database_name"]
    
    @staticmethod
    def _recommend_collection(collections: List[Dict[str, Any]]) -> Optional[str]:
        """推荐最佳集合"""
        # 推荐逻辑：选择文档数量适中的集合（100-10000之间）
        if not collections:
            return None
        
        suitable_collections = []
        for coll in collections:
            doc_count = coll.get("document_count", 0)
            if isinstance(doc_count, int) and 100 <= doc_count <= 10000:
                suitable_collections.append(coll)
        
        if suitable_collections:
            # 在合适范围内选择文档数最多的
            best = max(suitable_collections, key=lambda x: x.get("document_count", 0))
            return best["collection_name"]
        else:
            # 没有合适的，选择第一个
            return collections[0]["collection_name"]


class ConfirmationParser:
    """解析用户确认输入"""
    
    @staticmethod
    def parse_selection(user_input: str, options: List[str]) -> Tuple[bool, Optional[str], str]:
        """
        解析用户选择
        返回: (是否有效, 选择的选项, 错误信息)
        """
        if not user_input:
            return False, None, "请提供选择"
        
        user_input = user_input.strip().upper()
        
        # 处理字母选择 (A, B, C, ...)
        if len(user_input) == 1 and user_input.isalpha():
            option_index = ord(user_input) - ord('A')
            if 0 <= option_index < len(options):
                return True, options[option_index], ""
            else:
                return False, None, f"无效选择：{user_input}。可选范围：A-{chr(ord('A') + len(options) - 1)}"
        
        # 处理数字选择 (1, 2, 3, ...)
        if user_input.isdigit():
            option_index = int(user_input) - 1
            if 0 <= option_index < len(options):
                return True, options[option_index], ""
            else:
                return False, None, f"无效选择：{user_input}。可选范围：1-{len(options)}"
        
        # 处理直接输入选项名称
        for option in options:
            if user_input == option.upper():
                return True, option, ""
        
        return False, None, f"无法识别的选择：{user_input}"