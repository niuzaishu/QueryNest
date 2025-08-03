# -*- coding: utf-8 -*-
"""语义补全工具

当元数据库找不到语义时，尝试解读其他库表进行语义补全和用户确认
"""

from typing import Dict, List, Any, Optional, Tuple
import structlog
from mcp.types import Tool, TextContent
import re
from datetime import datetime

from database.connection_manager import ConnectionManager
from database.metadata_manager import MetadataManager
from scanner.semantic_analyzer import SemanticAnalyzer


logger = structlog.get_logger(__name__)


class SemanticCompletionTool:
    """语义补全工具"""
    
    def __init__(self, connection_manager: ConnectionManager, 
                 metadata_manager: MetadataManager,
                 semantic_analyzer: SemanticAnalyzer):
        self.connection_manager = connection_manager
        self.metadata_manager = metadata_manager
        self.semantic_analyzer = semantic_analyzer
    
    def get_tool_definition(self) -> Tool:
        """获取工具定义"""
        return Tool(
            name="semantic_completion",
            description="当元数据库找不到语义时，尝试解读其他库表进行语义补全和用户确认",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["analyze_unknown_field", "cross_reference_analysis", "suggest_semantics", "confirm_semantics"],
                        "description": "操作类型：analyze_unknown_field=分析未知字段，cross_reference_analysis=跨库表分析，suggest_semantics=语义建议，confirm_semantics=确认语义"
                    },
                    "instance_name": {
                        "type": "string",
                        "description": "实例名称"
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
                        "description": "字段路径（用于analyze_unknown_field和confirm_semantics）"
                    },
                    "query_description": {
                        "type": "string",
                        "description": "用户查询描述（用于cross_reference_analysis）"
                    },
                    "suggested_meaning": {
                        "type": "string",
                        "description": "建议的语义含义（用于confirm_semantics）"
                    },
                    "confidence_threshold": {
                        "type": "number",
                        "default": 0.6,
                        "description": "置信度阈值，低于此值的建议需要用户确认"
                    }
                },
                "required": ["action", "instance_name"]
            }
        )
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """执行语义补全操作"""
        try:
            action = arguments["action"]
            instance_name = arguments["instance_name"]
            
            # 确保实例元数据已初始化
            if not await self.metadata_manager.init_instance_metadata(instance_name):
                return [TextContent(
                    type="text",
                    text=f"无法初始化实例 '{instance_name}' 的元数据库"
                )]
            
            if action == "analyze_unknown_field":
                return await self._analyze_unknown_field(arguments)
            elif action == "cross_reference_analysis":
                return await self._cross_reference_analysis(arguments)
            elif action == "suggest_semantics":
                return await self._suggest_semantics(arguments)
            elif action == "confirm_semantics":
                return await self._confirm_semantics(arguments)
            else:
                return [TextContent(
                    type="text",
                    text=f"不支持的操作类型: {action}"
                )]
                
        except Exception as e:
            logger.error("语义补全操作失败", error=str(e))
            return [TextContent(
                type="text",
                text=f"语义补全操作失败: {str(e)}"
            )]
    
    async def _analyze_unknown_field(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """分析未知字段的语义"""
        instance_name = arguments["instance_name"]
        database_name = arguments["database_name"]
        collection_name = arguments["collection_name"]
        field_path = arguments["field_path"]
        confidence_threshold = arguments.get("confidence_threshold", 0.6)
        
        try:
            # 获取实例信息
            instance_info = await self.metadata_manager.get_instance_by_name(instance_name, instance_name)
            if not instance_info:
                return [TextContent(
                    type="text",
                    text=f"实例 '{instance_name}' 不存在"
                )]
            
            instance_id = instance_info["_id"]
            
            # 获取字段信息
            fields = await self.metadata_manager.get_fields_by_collection(
                instance_name, instance_id, database_name, collection_name
            )
            
            target_field = None
            for field in fields:
                if field["field_path"] == field_path:
                    target_field = field
                    break
            
            if not target_field:
                return [TextContent(
                    type="text",
                    text=f"字段 '{field_path}' 在集合 '{database_name}.{collection_name}' 中不存在"
                )]
            
            # 检查是否已有语义定义
            if target_field.get("business_meaning"):
                return [TextContent(
                    type="text",
                    text=f"字段 '{field_path}' 已有语义定义: {target_field['business_meaning']}"
                )]
            
            result_text = f"## 未知字段语义分析: {field_path}\n\n"
            
            # 1. 基础语义分析
            analysis = await self.semantic_analyzer.analyze_field_semantics(
                instance_name, database_name, collection_name, field_path, target_field
            )
            
            result_text += f"### 基础分析结果\n\n"
            result_text += f"- **建议含义**: {analysis['suggested_meaning']}\n"
            result_text += f"- **置信度**: {analysis['confidence']:.1%}\n"
            result_text += f"- **分析依据**: {', '.join(analysis['reasoning'])}\n\n"
            
            # 2. 跨库表相似字段分析
            similar_fields = await self._find_similar_fields_across_collections(
                instance_name, instance_id, field_path, database_name, collection_name
            )
            
            if similar_fields:
                result_text += f"### 跨库表相似字段\n\n"
                for similar in similar_fields[:5]:  # 显示前5个最相似的
                    similarity = similar['similarity']
                    db_name = similar['database_name']
                    coll_name = similar['collection_name']
                    similar_path = similar['field_path']
                    meaning = similar.get('business_meaning', '未定义')
                    
                    result_text += f"- **{db_name}.{coll_name}.{similar_path}** (相似度: {similarity:.1%})\n"
                    result_text += f"  语义: {meaning}\n\n"
            
            # 3. 值模式分析
            value_patterns = await self._analyze_value_patterns(
                instance_name, instance_id, target_field
            )
            
            if value_patterns:
                result_text += f"### 值模式分析\n\n"
                for pattern in value_patterns:
                    result_text += f"- **{pattern['pattern']}**: {pattern['meaning']} (匹配度: {pattern['match_rate']:.1%})\n"
                result_text += "\n"
            
            # 4. 生成最终建议
            final_suggestions = await self._generate_final_suggestions(
                analysis, similar_fields, value_patterns, confidence_threshold
            )
            
            result_text += f"### 语义建议\n\n"
            
            if analysis['confidence'] >= confidence_threshold:
                result_text += f"✅ **高置信度建议**: {analysis['suggested_meaning']}\n\n"
                result_text += f"建议直接采用此语义定义。\n\n"
            else:
                result_text += f"⚠️ **需要确认的建议**:\n\n"
                for i, suggestion in enumerate(final_suggestions, 1):
                    result_text += f"{i}. **{suggestion['meaning']}** (置信度: {suggestion['confidence']:.1%})\n"
                    result_text += f"   依据: {suggestion['reasoning']}\n\n"
                
                result_text += f"💡 **下一步操作**:\n"
                result_text += f"使用 `semantic_completion` 工具的 `confirm_semantics` 操作确认语义定义。\n\n"
            
            return [TextContent(type="text", text=result_text)]
            
        except Exception as e:
            logger.error("分析未知字段失败", error=str(e))
            return [TextContent(
                type="text",
                text=f"分析未知字段时发生错误: {str(e)}"
            )]
    
    async def _cross_reference_analysis(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """跨库表分析，根据查询描述推断可能的字段语义"""
        instance_name = arguments["instance_name"]
        database_name = arguments["database_name"]
        collection_name = arguments["collection_name"]
        query_description = arguments["query_description"]
        
        try:
            # 获取实例信息
            instance_info = await self.metadata_manager.get_instance_by_name(instance_name, instance_name)
            if not instance_info:
                return [TextContent(
                    type="text",
                    text=f"实例 '{instance_name}' 不存在"
                )]
            
            instance_id = instance_info["_id"]
            
            result_text = f"## 跨库表语义分析\n\n"
            result_text += f"**查询描述**: {query_description}\n\n"
            
            # 1. 提取查询中的关键词
            keywords = self._extract_query_keywords(query_description)
            result_text += f"### 提取的关键词\n\n"
            result_text += f"{', '.join(keywords)}\n\n"
            
            # 2. 在当前集合中查找相关字段
            current_fields = await self.metadata_manager.get_fields_by_collection(
                instance_name, instance_id, database_name, collection_name
            )
            
            relevant_fields = self._match_fields_to_keywords(current_fields, keywords)
            
            if relevant_fields:
                result_text += f"### 当前集合相关字段\n\n"
                for field in relevant_fields:
                    field_path = field['field_path']
                    meaning = field.get('business_meaning', '未定义')
                    relevance = field['relevance_score']
                    
                    result_text += f"- **{field_path}** (相关度: {relevance:.1%})\n"
                    result_text += f"  当前语义: {meaning}\n\n"
            
            # 3. 跨库表查找相似语义
            cross_references = await self._find_cross_references(
                instance_name, instance_id, keywords, database_name, collection_name
            )
            
            if cross_references:
                result_text += f"### 跨库表参考\n\n"
                for ref in cross_references[:10]:  # 显示前10个
                    db_name = ref['database_name']
                    coll_name = ref['collection_name']
                    field_path = ref['field_path']
                    meaning = ref['business_meaning']
                    relevance = ref['relevance_score']
                    
                    result_text += f"- **{db_name}.{coll_name}.{field_path}** (相关度: {relevance:.1%})\n"
                    result_text += f"  语义: {meaning}\n\n"
            
            # 4. 生成语义补全建议
            completion_suggestions = await self._generate_completion_suggestions(
                relevant_fields, cross_references, keywords
            )
            
            if completion_suggestions:
                result_text += f"### 语义补全建议\n\n"
                for i, suggestion in enumerate(completion_suggestions, 1):
                    field_path = suggestion['field_path']
                    suggested_meaning = suggestion['suggested_meaning']
                    confidence = suggestion['confidence']
                    reasoning = suggestion['reasoning']
                    
                    result_text += f"{i}. **字段**: {field_path}\n"
                    result_text += f"   **建议语义**: {suggested_meaning}\n"
                    result_text += f"   **置信度**: {confidence:.1%}\n"
                    result_text += f"   **依据**: {reasoning}\n\n"
                
                result_text += f"💡 **下一步操作**:\n"
                result_text += f"使用 `semantic_completion` 工具的 `confirm_semantics` 操作确认这些语义定义。\n\n"
            else:
                result_text += f"### 未找到相关的语义参考\n\n"
                result_text += f"建议：\n"
                result_text += f"1. 检查查询描述是否准确\n"
                result_text += f"2. 尝试使用更具体的关键词\n"
                result_text += f"3. 手动定义字段语义\n\n"
            
            return [TextContent(type="text", text=result_text)]
            
        except Exception as e:
            logger.error("跨库表分析失败", error=str(e))
            return [TextContent(
                type="text",
                text=f"跨库表分析时发生错误: {str(e)}"
            )]
    
    async def _suggest_semantics(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """为指定集合的所有未定义语义字段提供建议"""
        instance_name = arguments["instance_name"]
        database_name = arguments["database_name"]
        collection_name = arguments["collection_name"]
        confidence_threshold = arguments.get("confidence_threshold", 0.6)
        
        try:
            # 获取实例信息
            instance_info = await self.metadata_manager.get_instance_by_name(instance_name, instance_name)
            if not instance_info:
                return [TextContent(
                    type="text",
                    text=f"实例 '{instance_name}' 不存在"
                )]
            
            instance_id = instance_info["_id"]
            
            # 获取集合中的所有字段
            fields = await self.metadata_manager.get_fields_by_collection(
                instance_name, instance_id, database_name, collection_name
            )
            
            # 筛选出未定义语义的字段
            undefined_fields = [f for f in fields if not f.get("business_meaning")]
            
            if not undefined_fields:
                return [TextContent(
                    type="text",
                    text=f"集合 '{database_name}.{collection_name}' 中的所有字段都已定义语义"
                )]
            
            result_text = f"## 语义建议: {database_name}.{collection_name}\n\n"
            result_text += f"发现 {len(undefined_fields)} 个未定义语义的字段\n\n"
            
            high_confidence_suggestions = []
            low_confidence_suggestions = []
            
            for field in undefined_fields:
                field_path = field["field_path"]
                
                # 分析字段语义
                analysis = await self.semantic_analyzer.analyze_field_semantics(
                    instance_name, database_name, collection_name, field_path, field
                )
                
                suggestion = {
                    "field_path": field_path,
                    "suggested_meaning": analysis["suggested_meaning"],
                    "confidence": analysis["confidence"],
                    "reasoning": analysis["reasoning"]
                }
                
                if analysis["confidence"] >= confidence_threshold:
                    high_confidence_suggestions.append(suggestion)
                else:
                    low_confidence_suggestions.append(suggestion)
            
            # 显示高置信度建议
            if high_confidence_suggestions:
                result_text += f"### 🎯 高置信度建议 (≥{confidence_threshold:.0%})\n\n"
                for suggestion in high_confidence_suggestions:
                    field_path = suggestion["field_path"]
                    meaning = suggestion["suggested_meaning"]
                    confidence = suggestion["confidence"]
                    
                    result_text += f"- **{field_path}**: {meaning} (置信度: {confidence:.1%})\n"
                
                result_text += f"\n这些建议可以直接采用。\n\n"
            
            # 显示低置信度建议
            if low_confidence_suggestions:
                result_text += f"### ⚠️ 需要确认的建议 (<{confidence_threshold:.0%})\n\n"
                for suggestion in low_confidence_suggestions:
                    field_path = suggestion["field_path"]
                    meaning = suggestion["suggested_meaning"]
                    confidence = suggestion["confidence"]
                    reasoning = ", ".join(suggestion["reasoning"])
                    
                    result_text += f"- **{field_path}**: {meaning}\n"
                    result_text += f"  置信度: {confidence:.1%} | 依据: {reasoning}\n\n"
            
            # 操作建议
            result_text += f"### 💡 操作建议\n\n"
            
            if high_confidence_suggestions:
                result_text += f"1. **批量确认高置信度建议**:\n"
                for suggestion in high_confidence_suggestions:
                    field_path = suggestion["field_path"]
                    meaning = suggestion["suggested_meaning"]
                    result_text += f"   - 确认 `{field_path}` 为 \"{meaning}\"\n"
                result_text += "\n"
            
            if low_confidence_suggestions:
                result_text += f"2. **逐个确认低置信度建议**:\n"
                result_text += f"   使用 `semantic_completion` 工具的 `confirm_semantics` 操作\n\n"
            
            return [TextContent(type="text", text=result_text)]
            
        except Exception as e:
            logger.error("生成语义建议失败", error=str(e))
            return [TextContent(
                type="text",
                text=f"生成语义建议时发生错误: {str(e)}"
            )]
    
    async def _confirm_semantics(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """确认并保存字段语义"""
        instance_name = arguments["instance_name"]
        database_name = arguments["database_name"]
        collection_name = arguments["collection_name"]
        field_path = arguments["field_path"]
        suggested_meaning = arguments["suggested_meaning"]
        
        try:
            # 获取实例信息
            instance_info = await self.metadata_manager.get_instance_by_name(instance_name, instance_name)
            if not instance_info:
                return [TextContent(
                    type="text",
                    text=f"实例 '{instance_name}' 不存在"
                )]
            
            instance_id = instance_info["_id"]
            
            # 更新字段语义
            success = await self.metadata_manager.update_field_semantics(
                instance_name, instance_id, database_name, collection_name, 
                field_path, suggested_meaning
            )
            
            if success:
                result_text = f"✅ **语义确认成功**\n\n"
                result_text += f"- **字段**: {database_name}.{collection_name}.{field_path}\n"
                result_text += f"- **语义**: {suggested_meaning}\n"
                result_text += f"- **更新时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                result_text += f"语义定义已保存到元数据库中。\n"
                
                return [TextContent(type="text", text=result_text)]
            else:
                return [TextContent(
                    type="text",
                    text=f"❌ 语义确认失败：无法更新字段 '{field_path}' 的语义信息"
                )]
                
        except Exception as e:
            logger.error("确认语义失败", error=str(e))
            return [TextContent(
                type="text",
                text=f"确认语义时发生错误: {str(e)}"
            )]
    
    async def _find_similar_fields_across_collections(
        self, instance_name: str, instance_id: str, field_path: str, 
        exclude_db: str, exclude_collection: str
    ) -> List[Dict[str, Any]]:
        """在其他集合中查找相似的字段"""
        try:
            # 获取所有数据库
            databases = await self.metadata_manager.get_databases_by_instance(instance_name, instance_id)
            
            similar_fields = []
            
            for db in databases:
                db_name = db["database_name"]
                
                # 获取数据库中的所有集合
                collections = await self.metadata_manager.get_collections_by_database(
                    instance_name, instance_id, db_name
                )
                
                for collection in collections:
                    collection_name = collection["collection_name"]
                    
                    # 跳过当前集合
                    if db_name == exclude_db and collection_name == exclude_collection:
                        continue
                    
                    # 获取集合中的字段
                    fields = await self.metadata_manager.get_fields_by_collection(
                        instance_name, instance_id, db_name, collection_name
                    )
                    
                    for field in fields:
                        # 计算字段名称相似度
                        similarity = self._calculate_field_similarity(field_path, field["field_path"])
                        
                        if similarity > 0.5:  # 相似度阈值
                            similar_fields.append({
                                "database_name": db_name,
                                "collection_name": collection_name,
                                "field_path": field["field_path"],
                                "business_meaning": field.get("business_meaning"),
                                "similarity": similarity,
                                "field_type": field.get("field_type")
                            })
            
            # 按相似度排序
            similar_fields.sort(key=lambda x: x["similarity"], reverse=True)
            
            return similar_fields
            
        except Exception as e:
            logger.error("查找相似字段失败", error=str(e))
            return []
    
    def _calculate_field_similarity(self, field1: str, field2: str) -> float:
        """计算两个字段名称的相似度"""
        # 简单的字符串相似度计算
        field1_clean = field1.lower().replace('_', '').replace('-', '')
        field2_clean = field2.lower().replace('_', '').replace('-', '')
        
        # 完全匹配
        if field1_clean == field2_clean:
            return 1.0
        
        # 包含关系
        if field1_clean in field2_clean or field2_clean in field1_clean:
            return 0.8
        
        # 编辑距离相似度
        max_len = max(len(field1_clean), len(field2_clean))
        if max_len == 0:
            return 0.0
        
        edit_distance = self._levenshtein_distance(field1_clean, field2_clean)
        similarity = 1.0 - (edit_distance / max_len)
        
        return max(0.0, similarity)
    
    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """计算编辑距离"""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)
        
        if len(s2) == 0:
            return len(s1)
        
        previous_row = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
    
    async def _analyze_value_patterns(self, instance_name: str, instance_id: str, field_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """分析字段值的模式"""
        patterns = []
        examples = field_info.get("examples", [])
        
        if not examples:
            return patterns
        
        # 常见模式检测
        pattern_checks = [
            (r'^\d{11}$', '手机号码'),
            (r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', '邮箱地址'),
            (r'^https?://', 'URL地址'),
            (r'^\d{4}-\d{2}-\d{2}', '日期格式'),
            (r'^[0-9a-fA-F]{24}$', 'MongoDB ObjectId'),
            (r'^\d{13}$', '时间戳（毫秒）'),
            (r'^\d{10}$', '时间戳（秒）'),
            (r'^[0-9]{6}$', '验证码/邮政编码'),
        ]
        
        for pattern_regex, meaning in pattern_checks:
            matches = 0
            for example in examples:
                if example is not None and re.match(pattern_regex, str(example)):
                    matches += 1
            
            if matches > 0:
                match_rate = matches / len(examples)
                patterns.append({
                    "pattern": pattern_regex,
                    "meaning": meaning,
                    "match_rate": match_rate,
                    "matches": matches,
                    "total": len(examples)
                })
        
        # 按匹配率排序
        patterns.sort(key=lambda x: x["match_rate"], reverse=True)
        
        return patterns
    
    async def _generate_final_suggestions(
        self, analysis: Dict[str, Any], similar_fields: List[Dict[str, Any]], 
        value_patterns: List[Dict[str, Any]], confidence_threshold: float
    ) -> List[Dict[str, Any]]:
        """生成最终的语义建议"""
        suggestions = []
        
        # 基础分析建议
        if analysis["suggested_meaning"]:
            suggestions.append({
                "meaning": analysis["suggested_meaning"],
                "confidence": analysis["confidence"],
                "reasoning": "基于字段名称和类型分析"
            })
        
        # 相似字段建议
        for similar in similar_fields[:3]:  # 取前3个最相似的
            if similar.get("business_meaning"):
                confidence = similar["similarity"] * 0.8  # 相似度折扣
                suggestions.append({
                    "meaning": similar["business_meaning"],
                    "confidence": confidence,
                    "reasoning": f"参考相似字段 {similar['database_name']}.{similar['collection_name']}.{similar['field_path']}"
                })
        
        # 值模式建议
        for pattern in value_patterns[:2]:  # 取前2个最匹配的模式
            if pattern["match_rate"] > 0.7:  # 高匹配率
                confidence = pattern["match_rate"] * 0.9
                suggestions.append({
                    "meaning": pattern["meaning"],
                    "confidence": confidence,
                    "reasoning": f"基于值模式分析（匹配率: {pattern['match_rate']:.1%}）"
                })
        
        # 去重并排序
        unique_suggestions = []
        seen_meanings = set()
        
        for suggestion in suggestions:
            meaning = suggestion["meaning"]
            if meaning not in seen_meanings:
                unique_suggestions.append(suggestion)
                seen_meanings.add(meaning)
        
        # 按置信度排序
        unique_suggestions.sort(key=lambda x: x["confidence"], reverse=True)
        
        return unique_suggestions[:5]  # 返回前5个建议
    
    def _extract_query_keywords(self, query_description: str) -> List[str]:
        """从查询描述中提取关键词"""
        # 简单的关键词提取
        import jieba
        
        # 中文分词
        words = list(jieba.cut(query_description))
        
        # 过滤停用词和短词
        stop_words = {'的', '是', '在', '有', '和', '与', '或', '但', '而', '了', '着', '过', '要', '会', '能', '可以', '应该'}
        keywords = [word.strip() for word in words if len(word.strip()) > 1 and word.strip() not in stop_words]
        
        # 英文单词提取
        english_words = re.findall(r'\b[a-zA-Z]+\b', query_description)
        keywords.extend([word.lower() for word in english_words if len(word) > 2])
        
        return list(set(keywords))  # 去重
    
    def _match_fields_to_keywords(self, fields: List[Dict[str, Any]], keywords: List[str]) -> List[Dict[str, Any]]:
        """将字段与关键词匹配"""
        relevant_fields = []
        
        for field in fields:
            field_path = field["field_path"].lower()
            business_meaning = field.get("business_meaning", "").lower()
            
            relevance_score = 0.0
            
            for keyword in keywords:
                keyword_lower = keyword.lower()
                
                # 字段名匹配
                if keyword_lower in field_path:
                    relevance_score += 0.8
                
                # 语义匹配
                if keyword_lower in business_meaning:
                    relevance_score += 1.0
                
                # 部分匹配
                if any(keyword_lower in part for part in field_path.split('_')):
                    relevance_score += 0.5
            
            if relevance_score > 0:
                field_copy = field.copy()
                field_copy["relevance_score"] = min(relevance_score, 1.0)
                relevant_fields.append(field_copy)
        
        # 按相关度排序
        relevant_fields.sort(key=lambda x: x["relevance_score"], reverse=True)
        
        return relevant_fields
    
    async def _find_cross_references(
        self, instance_name: str, instance_id: str, keywords: List[str], 
        exclude_db: str, exclude_collection: str
    ) -> List[Dict[str, Any]]:
        """查找跨库表的语义参考"""
        try:
            cross_references = []
            
            # 获取所有数据库
            databases = await self.metadata_manager.get_databases_by_instance(instance_name, instance_id)
            
            for db in databases:
                db_name = db["database_name"]
                
                # 获取数据库中的所有集合
                collections = await self.metadata_manager.get_collections_by_database(
                    instance_name, instance_id, db_name
                )
                
                for collection in collections:
                    collection_name = collection["collection_name"]
                    
                    # 跳过当前集合
                    if db_name == exclude_db and collection_name == exclude_collection:
                        continue
                    
                    # 获取集合中的字段
                    fields = await self.metadata_manager.get_fields_by_collection(
                        instance_name, instance_id, db_name, collection_name
                    )
                    
                    # 匹配字段
                    relevant_fields = self._match_fields_to_keywords(fields, keywords)
                    
                    for field in relevant_fields:
                        if field.get("business_meaning"):  # 只考虑已定义语义的字段
                            cross_references.append({
                                "database_name": db_name,
                                "collection_name": collection_name,
                                "field_path": field["field_path"],
                                "business_meaning": field["business_meaning"],
                                "relevance_score": field["relevance_score"]
                            })
            
            # 按相关度排序
            cross_references.sort(key=lambda x: x["relevance_score"], reverse=True)
            
            return cross_references
            
        except Exception as e:
            logger.error("查找跨库表参考失败", error=str(e))
            return []
    
    async def _generate_completion_suggestions(
        self, relevant_fields: List[Dict[str, Any]], cross_references: List[Dict[str, Any]], 
        keywords: List[str]
    ) -> List[Dict[str, Any]]:
        """生成语义补全建议"""
        suggestions = []
        
        # 为未定义语义的相关字段生成建议
        for field in relevant_fields:
            if not field.get("business_meaning"):
                field_path = field["field_path"]
                
                # 从跨库表参考中寻找最相似的语义
                best_match = None
                best_score = 0.0
                
                for ref in cross_references:
                    # 计算字段名相似度
                    similarity = self._calculate_field_similarity(field_path, ref["field_path"])
                    combined_score = (similarity + ref["relevance_score"]) / 2
                    
                    if combined_score > best_score:
                        best_score = combined_score
                        best_match = ref
                
                if best_match and best_score > 0.5:
                    suggestions.append({
                        "field_path": field_path,
                        "suggested_meaning": best_match["business_meaning"],
                        "confidence": best_score,
                        "reasoning": f"参考 {best_match['database_name']}.{best_match['collection_name']}.{best_match['field_path']}"
                    })
        
        # 按置信度排序
        suggestions.sort(key=lambda x: x["confidence"], reverse=True)
        
        return suggestions