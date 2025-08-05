# -*- coding: utf-8 -*-
"""语义分析器"""

import re
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import structlog

from database.metadata_manager import MetadataManager


logger = structlog.get_logger(__name__)


class SemanticAnalyzer:
    """语义分析器"""
    
    def __init__(self, metadata_manager: MetadataManager):
        self.metadata_manager = metadata_manager
        
        # 常见字段名称模式和对应的业务含义
        self.field_patterns = {
            # 用户相关
            r'user.*id|uid|user_id': '用户ID',
            r'user.*name|username': '用户名',
            r'user.*email|email': '用户邮箱',
            r'user.*phone|phone|mobile': '用户手机号',
            r'user.*avatar|avatar': '用户头像',
            r'user.*age|age': '用户年龄',
            r'user.*gender|gender|sex': '用户性别',
            
            # 订单相关
            r'order.*id|order_id': '订单ID',
            r'order.*no|order_no|order_number': '订单号',
            r'order.*status|status': '订单状态',
            r'order.*amount|amount|price|total': '订单金额',
            r'order.*time|order_time|created_time': '订单时间',
            
            # 产品相关
            r'product.*id|prod_id|product_id': '产品ID',
            r'product.*name|prod_name|product_name': '产品名称',
            r'product.*price|price': '产品价格',
            r'product.*desc|description': '产品描述',
            r'product.*category|category': '产品分类',
            
            # 时间相关
            r'create.*time|created.*at|create_time': '创建时间',
            r'update.*time|updated.*at|update_time|modify_time': '更新时间',
            r'delete.*time|deleted.*at|delete_time': '删除时间',
            r'start.*time|start_time|begin_time': '开始时间',
            r'end.*time|end_time|finish_time': '结束时间',
            
            # 状态相关
            r'.*status$|.*state$': '状态',
            r'.*flag$|.*enabled$|.*disabled$': '标志位',
            r'is_.*|has_.*': '布尔标识',
            
            # 地址相关
            r'.*address|addr': '地址',
            r'.*city': '城市',
            r'.*province|.*state': '省份/州',
            r'.*country': '国家',
            r'.*zip.*code|.*postal.*code': '邮政编码',
            
            # 通用ID
            r'.*_id$|.*id$': 'ID标识',
            r'.*_no$|.*no$|.*number$': '编号',
            r'.*_code$|.*code$': '代码',
            r'.*_name$|.*name$': '名称',
            r'.*_type$|.*type$': '类型',
            r'.*_count$|.*count$': '数量',
            r'.*_url$|.*url$': 'URL地址',
        }
        
        # 数据类型对应的业务含义提示
        self.type_hints = {
            'objectId': 'MongoDB文档ID',
            'string': '文本信息',
            'integer': '整数值',
            'double': '浮点数值',
            'boolean': '布尔值（真/假）',
            'date': '日期时间',
            'array': '数组/列表',
            'object': '嵌套对象'
        }
        
        # 常见值模式和对应含义
        self.value_patterns = {
            r'^\d{11}$': '手机号码',
            r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$': '邮箱地址',
            r'^https?://': 'URL地址',
            r'^\d{4}-\d{2}-\d{2}': '日期格式',
            r'^[0-9a-fA-F]{24}$': 'MongoDB ObjectId',
            r'^\d{13}$': '时间戳（毫秒）',
            r'^\d{10}$': '时间戳（秒）',
            r'^[0-9]{6}$': '验证码/邮政编码',
        }
    
    async def analyze_field_semantics(self, instance_id: str, database_name: str, 
                                    collection_name: str, field_path: str, 
                                    field_info: Dict[str, Any]) -> Dict[str, Any]:
        """分析字段语义"""
        analysis_result = {
            "suggested_meaning": "",
            "confidence": 0.0,
            "reasoning": [],
            "suggestions": []
        }
        
        try:
            # 基于字段名称分析
            name_analysis = self._analyze_field_name(field_path)
            if name_analysis["meaning"]:
                analysis_result["suggested_meaning"] = name_analysis["meaning"]
                analysis_result["confidence"] += name_analysis["confidence"]
                analysis_result["reasoning"].append(f"字段名称匹配: {name_analysis['pattern']}")
            
            # 基于数据类型分析
            type_analysis = self._analyze_field_type(field_info.get("type", "unknown"))
            if type_analysis["hint"]:
                analysis_result["reasoning"].append(f"数据类型: {type_analysis['hint']}")
                analysis_result["confidence"] += type_analysis["confidence"]
            
            # 基于示例值分析
            examples = field_info.get("examples", [])
            if examples:
                value_analysis = self._analyze_field_values(examples)
                if value_analysis["meaning"]:
                    if not analysis_result["suggested_meaning"]:
                        analysis_result["suggested_meaning"] = value_analysis["meaning"]
                    analysis_result["confidence"] += value_analysis["confidence"]
                    analysis_result["reasoning"].append(f"值模式匹配: {value_analysis['pattern']}")
            
            # 基于上下文分析（集合名称、数据库名称）
            context_analysis = self._analyze_context(database_name, collection_name, field_path)
            if context_analysis["suggestions"]:
                analysis_result["suggestions"].extend(context_analysis["suggestions"])
                analysis_result["reasoning"].append("基于上下文推断")
            
            # 标准化置信度
            analysis_result["confidence"] = min(analysis_result["confidence"], 1.0)
            
            # 如果没有明确的语义建议，提供通用建议
            if not analysis_result["suggested_meaning"]:
                analysis_result["suggested_meaning"] = self._generate_generic_meaning(field_path, field_info)
                analysis_result["confidence"] = 0.3
                analysis_result["reasoning"].append("通用推断")
            
            # 生成改进建议
            analysis_result["suggestions"].extend(self._generate_improvement_suggestions(field_info))
            
            logger.debug(
                "字段语义分析完成",
                field_path=field_path,
                suggested_meaning=analysis_result["suggested_meaning"],
                confidence=analysis_result["confidence"]
            )
            
        except Exception as e:
            logger.error("字段语义分析异常", field_path=field_path, error=str(e))
            analysis_result["reasoning"].append(f"分析异常: {str(e)}")
        
        return analysis_result
    
    def _analyze_field_name(self, field_path: str) -> Dict[str, Any]:
        """基于字段名称分析语义"""
        field_name = field_path.lower().replace('_', '').replace('-', '')
        
        for pattern, meaning in self.field_patterns.items():
            if re.search(pattern, field_name, re.IGNORECASE):
                return {
                    "meaning": meaning,
                    "confidence": 0.7,
                    "pattern": pattern
                }
        
        return {"meaning": "", "confidence": 0.0, "pattern": ""}
    
    def _analyze_field_type(self, field_type: str) -> Dict[str, Any]:
        """基于数据类型分析"""
        hint = self.type_hints.get(field_type, "")
        confidence = 0.2 if hint else 0.0
        
        return {
            "hint": hint,
            "confidence": confidence
        }
    
    def _analyze_field_values(self, examples: List[Any]) -> Dict[str, Any]:
        """基于示例值分析语义"""
        if not examples:
            return {"meaning": "", "confidence": 0.0, "pattern": ""}
        
        # 统计匹配的模式
        pattern_matches = {}
        
        for example in examples:
            if example is None:
                continue
                
            example_str = str(example)
            for pattern, meaning in self.value_patterns.items():
                if re.match(pattern, example_str):
                    if meaning not in pattern_matches:
                        pattern_matches[meaning] = 0
                    pattern_matches[meaning] += 1
        
        if pattern_matches:
            # 选择匹配最多的模式
            best_meaning = max(pattern_matches, key=pattern_matches.get)
            match_rate = pattern_matches[best_meaning] / len(examples)
            
            return {
                "meaning": best_meaning,
                "confidence": match_rate * 0.8,  # 最高0.8的置信度
                "pattern": best_meaning
            }
        
        return {"meaning": "", "confidence": 0.0, "pattern": ""}
    
    def _analyze_context(self, database_name: str, collection_name: str, field_path: str) -> Dict[str, Any]:
        """基于上下文分析"""
        suggestions = []
        
        # 基于集合名称推断
        collection_lower = collection_name.lower()
        if 'user' in collection_lower:
            if any(keyword in field_path.lower() for keyword in ['name', 'email', 'phone']):
                suggestions.append("用户相关信息")
        elif 'order' in collection_lower:
            if any(keyword in field_path.lower() for keyword in ['amount', 'price', 'total']):
                suggestions.append("订单金额相关")
        elif 'product' in collection_lower:
            if any(keyword in field_path.lower() for keyword in ['name', 'title', 'desc']):
                suggestions.append("产品信息相关")
        
        # 基于数据库名称推断
        db_lower = database_name.lower()
        if 'ecommerce' in db_lower or 'shop' in db_lower:
            suggestions.append("电商业务相关")
        elif 'cms' in db_lower or 'content' in db_lower:
            suggestions.append("内容管理相关")
        elif 'user' in db_lower or 'auth' in db_lower:
            suggestions.append("用户认证相关")
        
        return {"suggestions": suggestions}
    
    def _generate_generic_meaning(self, field_path: str, field_info: Dict[str, Any]) -> str:
        """生成通用语义描述"""
        field_type = field_info.get("type", "unknown")
        
        # 基于字段路径的最后一部分
        field_name = field_path.split('.')[-1]
        
        if field_name.endswith('_id') or field_name.endswith('Id'):
            return f"{field_name[:-3]}的标识符"
        elif field_name.endswith('_name') or field_name.endswith('Name'):
            return f"{field_name[:-5]}的名称"
        elif field_name.endswith('_time') or field_name.endswith('Time'):
            return f"{field_name[:-5]}的时间"
        elif field_name.endswith('_count') or field_name.endswith('Count'):
            return f"{field_name[:-6]}的数量"
        elif field_type == 'boolean':
            return f"{field_name}的状态标识"
        elif field_type in ['integer', 'double']:
            return f"{field_name}的数值"
        elif field_type == 'date':
            return f"{field_name}的日期时间"
        else:
            return f"{field_name}字段"
    
    def _generate_improvement_suggestions(self, field_info: Dict[str, Any]) -> List[str]:
        """生成改进建议"""
        suggestions = []
        
        # 检查是否需要索引
        if not field_info.get("is_indexed", False):
            occurrence_rate = field_info.get("occurrence_rate", 0)
            if occurrence_rate > 0.8:  # 出现率高的字段建议添加索引
                suggestions.append("建议为此字段添加索引以提高查询性能")
        
        # 检查数据一致性
        types = field_info.get("types", {})
        if len(types) > 1:
            suggestions.append("字段存在多种数据类型，建议统一数据格式")
        
        # 检查是否为必需字段
        occurrence_rate = field_info.get("occurrence_rate", 0)
        if occurrence_rate < 0.5:
            suggestions.append("字段出现率较低，考虑是否为可选字段")
        elif occurrence_rate > 0.9 and not field_info.get("is_required", False):
            suggestions.append("字段出现率很高，建议设置为必需字段")
        
        return suggestions
    
    async def batch_analyze_collection(self, instance_id: str, database_name: str, collection_name: str) -> Dict[str, Any]:
        """批量分析集合中的所有字段"""
        logger.info(
            "开始批量分析集合字段语义",
            database=database_name,
            collection=collection_name
        )
        
        try:
            # 获取集合的所有字段
            fields = await self.metadata_manager.get_fields_by_collection(
                instance_id, database_name, collection_name
            )
            
            analysis_results = {}
            updated_count = 0
            
            for field in fields:
                field_path = field["field_path"]
                
                # 如果字段已有业务含义，跳过
                if field.get("business_meaning"):
                    continue
                
                # 分析字段语义
                analysis = await self.analyze_field_semantics(
                    instance_id, database_name, collection_name, field_path, field
                )
                
                analysis_results[field_path] = analysis
                
                # 如果置信度足够高，自动更新字段语义
                if analysis["confidence"] > 0.6 and analysis["suggested_meaning"]:
                    # 使用新的双重存储策略更新字段语义
                    from bson import ObjectId
                    try:
                        # 尝试使用假的ObjectId调用新方法，会自动回退到业务库存储
                        fake_instance_id = ObjectId()
                        success = await self.metadata_manager.update_field_semantics(
                            instance_id, fake_instance_id, database_name, collection_name, 
                            field_path, analysis["suggested_meaning"]
                        )
                        if success:
                            updated_count += 1
                    except Exception as e:
                        logger.warning(
                            "自动更新字段语义失败，跳过该字段",
                            field_path=field_path,
                            error=str(e)
                        )
            
            logger.info(
                "集合字段语义分析完成",
                database=database_name,
                collection=collection_name,
                total_fields=len(fields),
                analyzed_fields=len(analysis_results),
                updated_fields=updated_count
            )
            
            return {
                "total_fields": len(fields),
                "analyzed_fields": len(analysis_results),
                "updated_fields": updated_count,
                "analysis_results": analysis_results
            }
            
        except Exception as e:
            logger.error(
                "批量分析字段语义异常",
                database=database_name,
                collection=collection_name,
                error=str(e)
            )
            return {
                "total_fields": 0,
                "analyzed_fields": 0,
                "updated_fields": 0,
                "analysis_results": {},
                "error": str(e)
            }
    
    async def suggest_business_domain(self, database_name: str, collections: List[Dict[str, Any]]) -> List[str]:
        """基于数据库和集合信息推断业务领域"""
        suggestions = set()
        
        # 基于数据库名称
        db_lower = database_name.lower()
        if any(keyword in db_lower for keyword in ['ecommerce', 'shop', 'store', 'mall']):
            suggestions.add("电子商务")
        elif any(keyword in db_lower for keyword in ['cms', 'content', 'blog', 'news']):
            suggestions.add("内容管理")
        elif any(keyword in db_lower for keyword in ['user', 'auth', 'account']):
            suggestions.add("用户管理")
        elif any(keyword in db_lower for keyword in ['finance', 'payment', 'billing']):
            suggestions.add("金融支付")
        elif any(keyword in db_lower for keyword in ['log', 'analytics', 'stats']):
            suggestions.add("数据分析")
        
        # 基于集合名称
        collection_names = [coll["collection_name"].lower() for coll in collections]
        
        if any('user' in name for name in collection_names):
            suggestions.add("用户管理")
        if any(keyword in ' '.join(collection_names) for keyword in ['order', 'product', 'cart']):
            suggestions.add("电子商务")
        if any(keyword in ' '.join(collection_names) for keyword in ['article', 'post', 'content']):
            suggestions.add("内容管理")
        if any(keyword in ' '.join(collection_names) for keyword in ['payment', 'transaction', 'billing']):
            suggestions.add("金融支付")
        
        return list(suggestions)
    
    def get_semantic_suggestions_for_query(self, query_description: str, 
                                         available_fields: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """为查询描述提供语义建议"""
        suggestions = []
        query_lower = query_description.lower()
        
        for field in available_fields:
            field_path = field["field_path"]
            business_meaning = field.get("business_meaning", "")
            
            # 计算相关性得分
            relevance_score = 0.0
            
            # 基于业务含义匹配
            if business_meaning:
                meaning_lower = business_meaning.lower()
                common_words = set(query_lower.split()) & set(meaning_lower.split())
                if common_words:
                    relevance_score += len(common_words) * 0.3
            
            # 基于字段名称匹配
            field_words = re.split(r'[._]', field_path.lower())
            query_words = query_lower.split()
            field_matches = set(field_words) & set(query_words)
            if field_matches:
                relevance_score += len(field_matches) * 0.2
            
            # 基于示例值匹配
            examples = field.get("examples", [])
            for example in examples:
                if str(example).lower() in query_lower:
                    relevance_score += 0.1
            
            if relevance_score > 0:
                suggestions.append({
                    "field_path": field_path,
                    "business_meaning": business_meaning,
                    "relevance_score": relevance_score,
                    "field_type": field.get("field_type", "unknown")
                })
        
        # 按相关性得分排序
        suggestions.sort(key=lambda x: x["relevance_score"], reverse=True)
        
        return suggestions[:10]  # 返回前10个最相关的字段