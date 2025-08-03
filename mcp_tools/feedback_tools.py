#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用户反馈和帮助系统MCP工具
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from utils.error_handler import feedback_collector, error_handler
from database.metadata_manager import MetadataManager


class FeedbackTools:
    """用户反馈工具"""
    
    def __init__(self, metadata_manager: MetadataManager):
        self.metadata_manager = metadata_manager
        self.logger = logging.getLogger(__name__)
    
    async def submit_feedback(
        self,
        session_id: str,
        feedback_type: str,
        content: str,
        error_id: Optional[str] = None,
        rating: Optional[int] = None,
        category: str = "general"
    ) -> Dict[str, Any]:
        """
        提交用户反馈
        
        Args:
            session_id: 会话ID
            feedback_type: 反馈类型 (suggestion, bug_report, feature_request, compliment, complaint)
            content: 反馈内容
            error_id: 相关错误ID（可选）
            rating: 评分 1-5（可选）
            category: 反馈分类
        
        Returns:
            反馈提交结果
        """
        try:
            # 验证输入
            if not content or len(content.strip()) < 5:
                return {
                    "success": False,
                    "error": "反馈内容不能为空且至少包含5个字符",
                    "suggestions": ["请提供详细的反馈内容"]
                }
            
            if rating is not None and (rating < 1 or rating > 5):
                return {
                    "success": False,
                    "error": "评分必须在1-5之间",
                    "suggestions": ["请提供1-5的评分"]
                }
            
            # 收集反馈
            feedback = feedback_collector.collect_feedback(
                session_id=session_id,
                error_id=error_id or "none",
                feedback_type=feedback_type,
                rating=rating,
                comment=content
            )
            
            # 保存到元数据库
            feedback_record = {
                "feedback_id": feedback["feedback_id"],
                "session_id": session_id,
                "feedback_type": feedback_type,
                "category": category,
                "content": content,
                "rating": rating,
                "error_id": error_id,
                "status": "submitted",
                "created_at": datetime.now(),
                "metadata": {
                    "user_agent": "QueryNest-MCP",
                    "source": "mcp_tools"
                }
            }
            
            # 尝试保存到数据库
            try:
                await self._save_feedback_to_db(feedback_record)
            except Exception as e:
                self.logger.warning(f"无法保存反馈到数据库: {e}")
            
            # 生成响应消息
            response_message = self._generate_feedback_response(feedback_type, rating)
            
            return {
                "success": True,
                "feedback_id": feedback["feedback_id"],
                "message": response_message,
                "next_steps": self._get_next_steps(feedback_type)
            }
            
        except Exception as e:
            self.logger.error(f"提交反馈失败: {e}")
            return {
                "success": False,
                "error": "提交反馈时发生错误",
                "suggestions": ["请稍后重试", "如果问题持续，请联系技术支持"]
            }
    
    async def get_feedback_status(
        self,
        feedback_id: str
    ) -> Dict[str, Any]:
        """
        获取反馈状态
        
        Args:
            feedback_id: 反馈ID
        
        Returns:
            反馈状态信息
        """
        try:
            # 从数据库查询反馈状态
            feedback_info = await self._get_feedback_from_db(feedback_id)
            
            if not feedback_info:
                return {
                    "success": False,
                    "error": "未找到指定的反馈记录",
                    "suggestions": ["请检查反馈ID是否正确"]
                }
            
            return {
                "success": True,
                "feedback_id": feedback_id,
                "status": feedback_info.get("status", "unknown"),
                "created_at": feedback_info.get("created_at"),
                "updated_at": feedback_info.get("updated_at"),
                "response": feedback_info.get("admin_response"),
                "category": feedback_info.get("category"),
                "type": feedback_info.get("feedback_type")
            }
            
        except Exception as e:
            self.logger.error(f"获取反馈状态失败: {e}")
            return {
                "success": False,
                "error": "获取反馈状态时发生错误",
                "suggestions": ["请稍后重试"]
            }
    
    async def get_help_content(
        self,
        topic: str = "general",
        user_level: str = "beginner"
    ) -> Dict[str, Any]:
        """
        获取帮助内容
        
        Args:
            topic: 帮助主题 (general, query, connection, troubleshooting)
            user_level: 用户级别 (beginner, intermediate, advanced)
        
        Returns:
            帮助内容
        """
        try:
            help_content = self._get_help_by_topic(topic, user_level)
            
            return {
                "success": True,
                "topic": topic,
                "user_level": user_level,
                "content": help_content,
                "related_topics": self._get_related_topics(topic),
                "quick_actions": self._get_quick_actions(topic)
            }
            
        except Exception as e:
            self.logger.error(f"获取帮助内容失败: {e}")
            return {
                "success": False,
                "error": "获取帮助内容时发生错误",
                "suggestions": ["请尝试其他帮助主题"]
            }
    
    async def get_faq(
        self,
        category: str = "all",
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        获取常见问题解答
        
        Args:
            category: FAQ分类 (all, query, connection, error, feature)
            limit: 返回数量限制
        
        Returns:
            FAQ列表
        """
        try:
            faq_list = self._get_faq_by_category(category, limit)
            
            return {
                "success": True,
                "category": category,
                "total_count": len(faq_list),
                "faqs": faq_list,
                "categories": ["query", "connection", "error", "feature", "general"]
            }
            
        except Exception as e:
            self.logger.error(f"获取FAQ失败: {e}")
            return {
                "success": False,
                "error": "获取FAQ时发生错误",
                "suggestions": ["请稍后重试"]
            }
    
    async def search_help(
        self,
        query: str,
        limit: int = 5
    ) -> Dict[str, Any]:
        """
        搜索帮助内容
        
        Args:
            query: 搜索关键词
            limit: 返回数量限制
        
        Returns:
            搜索结果
        """
        try:
            if not query or len(query.strip()) < 2:
                return {
                    "success": False,
                    "error": "搜索关键词至少需要2个字符",
                    "suggestions": ["请提供更具体的搜索关键词"]
                }
            
            search_results = self._search_help_content(query.strip(), limit)
            
            return {
                "success": True,
                "query": query,
                "total_results": len(search_results),
                "results": search_results,
                "suggestions": self._get_search_suggestions(query) if not search_results else []
            }
            
        except Exception as e:
            self.logger.error(f"搜索帮助内容失败: {e}")
            return {
                "success": False,
                "error": "搜索帮助内容时发生错误",
                "suggestions": ["请尝试其他关键词"]
            }
    
    async def get_feedback_summary(
        self,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        获取反馈摘要（管理员功能）
        
        Args:
            days: 统计天数
        
        Returns:
            反馈摘要统计
        """
        try:
            # 获取反馈统计
            feedback_stats = feedback_collector.get_feedback_summary()
            
            # 获取错误统计
            error_stats = error_handler.get_error_statistics()
            
            # 计算趋势
            trends = await self._calculate_feedback_trends(days)
            
            return {
                "success": True,
                "period_days": days,
                "feedback_statistics": feedback_stats,
                "error_statistics": error_stats,
                "trends": trends,
                "recommendations": self._generate_improvement_recommendations(feedback_stats, error_stats)
            }
            
        except Exception as e:
            self.logger.error(f"获取反馈摘要失败: {e}")
            return {
                "success": False,
                "error": "获取反馈摘要时发生错误",
                "suggestions": ["请稍后重试"]
            }
    
    def _generate_feedback_response(self, feedback_type: str, rating: Optional[int]) -> str:
        """生成反馈响应消息"""
        responses = {
            "suggestion": "感谢您的建议！我们会认真考虑您的意见。",
            "bug_report": "感谢您报告这个问题！我们会尽快调查并修复。",
            "feature_request": "感谢您的功能建议！我们会评估并考虑在未来版本中实现。",
            "compliment": "感谢您的肯定！这对我们团队来说意义重大。",
            "complaint": "很抱歉给您带来不便，我们会认真对待您的意见并努力改进。"
        }
        
        base_message = responses.get(feedback_type, "感谢您的反馈！")
        
        if rating is not None:
            if rating >= 4:
                base_message += " 很高兴您对我们的服务满意！"
            elif rating <= 2:
                base_message += " 我们会努力改进以提供更好的服务。"
        
        return base_message
    
    def _get_next_steps(self, feedback_type: str) -> List[str]:
        """获取后续步骤建议"""
        next_steps = {
            "suggestion": [
                "您可以通过反馈ID跟踪处理进度",
                "如有更多建议，欢迎继续反馈"
            ],
            "bug_report": [
                "我们会在24小时内确认问题",
                "修复完成后会通过系统通知您",
                "如需紧急处理，请联系技术支持"
            ],
            "feature_request": [
                "功能评估通常需要1-2周时间",
                "您可以关注产品更新公告",
                "欢迎提供更详细的使用场景"
            ],
            "compliment": [
                "欢迎分享给其他用户",
                "如有更多使用心得，欢迎分享"
            ],
            "complaint": [
                "我们会在48小时内回复处理方案",
                "如需立即协助，请联系客服"
            ]
        }
        
        return next_steps.get(feedback_type, ["感谢您的反馈"])
    
    def _get_help_by_topic(self, topic: str, user_level: str) -> Dict[str, Any]:
        """根据主题获取帮助内容"""
        help_content = {
            "general": {
                "title": "QueryNest 使用指南",
                "description": "QueryNest 是一个强大的MongoDB多实例查询服务",
                "sections": [
                    {
                        "title": "快速开始",
                        "content": "1. 连接到MongoDB实例\n2. 选择数据库和集合\n3. 输入查询条件\n4. 查看结果"
                    },
                    {
                        "title": "主要功能",
                        "content": "• 自然语言查询\n• 多实例管理\n• 数据结构发现\n• 查询优化建议"
                    }
                ]
            },
            "query": {
                "title": "查询使用指南",
                "description": "学习如何使用QueryNest进行数据查询",
                "sections": [
                    {
                        "title": "自然语言查询",
                        "content": "直接用中文描述您的查询需求，例如：\n• 查找年龄大于25的用户\n• 统计订单总数\n• 找出最近一周的活跃用户"
                    },
                    {
                        "title": "MongoDB查询",
                        "content": "支持标准MongoDB查询语法：\n• find查询: {age: {$gt: 25}}\n• 聚合查询: [{$match: {...}}, {$group: {...}}]\n• 投影查询: {name: 1, age: 1}"
                    }
                ]
            },
            "connection": {
                "title": "连接配置指南",
                "description": "了解如何配置和管理MongoDB连接",
                "sections": [
                    {
                        "title": "连接配置",
                        "content": "在config.yaml中配置MongoDB实例：\n• host: 数据库地址\n• port: 端口号\n• username/password: 认证信息\n• ssl: 安全连接设置"
                    },
                    {
                        "title": "故障排除",
                        "content": "常见连接问题：\n• 检查网络连接\n• 验证认证信息\n• 确认防火墙设置\n• 查看错误日志"
                    }
                ]
            },
            "troubleshooting": {
                "title": "故障排除指南",
                "description": "解决常见问题和错误",
                "sections": [
                    {
                        "title": "常见错误",
                        "content": "• 连接超时: 检查网络和配置\n• 权限错误: 确认用户权限\n• 查询失败: 验证语法和字段名\n• 性能问题: 优化查询条件"
                    },
                    {
                        "title": "性能优化",
                        "content": "• 使用索引加速查询\n• 限制返回文档数量\n• 避免复杂的聚合操作\n• 合理使用缓存"
                    }
                ]
            }
        }
        
        return help_content.get(topic, help_content["general"])
    
    def _get_related_topics(self, topic: str) -> List[str]:
        """获取相关主题"""
        related = {
            "general": ["query", "connection"],
            "query": ["troubleshooting", "general"],
            "connection": ["troubleshooting", "general"],
            "troubleshooting": ["query", "connection"]
        }
        
        return related.get(topic, ["general"])
    
    def _get_quick_actions(self, topic: str) -> List[Dict[str, str]]:
        """获取快速操作"""
        actions = {
            "general": [
                {"title": "开始查询", "action": "start_query"},
                {"title": "查看示例", "action": "view_examples"}
            ],
            "query": [
                {"title": "查询示例", "action": "query_examples"},
                {"title": "语法帮助", "action": "syntax_help"}
            ],
            "connection": [
                {"title": "测试连接", "action": "test_connection"},
                {"title": "配置检查", "action": "check_config"}
            ],
            "troubleshooting": [
                {"title": "诊断问题", "action": "diagnose"},
                {"title": "查看日志", "action": "view_logs"}
            ]
        }
        
        return actions.get(topic, [])
    
    def _get_faq_by_category(self, category: str, limit: int) -> List[Dict[str, Any]]:
        """根据分类获取FAQ"""
        all_faqs = [
            {
                "id": "faq_001",
                "category": "query",
                "question": "如何使用自然语言查询？",
                "answer": "直接用中文描述您的查询需求，例如'查找年龄大于25的用户'，系统会自动转换为MongoDB查询。",
                "tags": ["自然语言", "查询", "基础"]
            },
            {
                "id": "faq_002",
                "category": "connection",
                "question": "连接数据库失败怎么办？",
                "answer": "请检查：1) 网络连接是否正常 2) 数据库地址和端口是否正确 3) 用户名密码是否正确 4) 防火墙设置是否允许连接。",
                "tags": ["连接", "故障排除", "网络"]
            },
            {
                "id": "faq_003",
                "category": "error",
                "question": "查询超时是什么原因？",
                "answer": "查询超时通常由以下原因造成：1) 查询条件过于复杂 2) 数据量过大 3) 缺少合适的索引 4) 网络延迟。建议优化查询条件或添加索引。",
                "tags": ["超时", "性能", "优化"]
            },
            {
                "id": "faq_004",
                "category": "feature",
                "question": "支持哪些MongoDB操作？",
                "answer": "目前支持只读操作：find查询、聚合查询、计数查询、去重查询。不支持写入操作（insert、update、delete）以确保数据安全。",
                "tags": ["功能", "操作", "限制"]
            },
            {
                "id": "faq_005",
                "category": "general",
                "question": "如何查看查询历史？",
                "answer": "系统会自动记录您的查询历史，您可以通过分析工具查看历史查询记录，包括查询条件、执行时间和结果统计。",
                "tags": ["历史", "记录", "分析"]
            }
        ]
        
        if category == "all":
            filtered_faqs = all_faqs
        else:
            filtered_faqs = [faq for faq in all_faqs if faq["category"] == category]
        
        return filtered_faqs[:limit]
    
    def _search_help_content(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """搜索帮助内容"""
        # 简单的关键词匹配搜索
        query_lower = query.lower()
        
        search_results = []
        
        # 搜索FAQ
        faqs = self._get_faq_by_category("all", 100)
        for faq in faqs:
            if (query_lower in faq["question"].lower() or 
                query_lower in faq["answer"].lower() or
                any(query_lower in tag.lower() for tag in faq["tags"])):
                search_results.append({
                    "type": "faq",
                    "title": faq["question"],
                    "content": faq["answer"],
                    "category": faq["category"],
                    "relevance": self._calculate_relevance(query_lower, faq)
                })
        
        # 搜索帮助主题
        help_topics = ["general", "query", "connection", "troubleshooting"]
        for topic in help_topics:
            help_content = self._get_help_by_topic(topic, "beginner")
            if query_lower in help_content["title"].lower() or query_lower in help_content["description"].lower():
                search_results.append({
                    "type": "help_topic",
                    "title": help_content["title"],
                    "content": help_content["description"],
                    "category": topic,
                    "relevance": 0.8
                })
        
        # 按相关性排序
        search_results.sort(key=lambda x: x["relevance"], reverse=True)
        
        return search_results[:limit]
    
    def _calculate_relevance(self, query: str, faq: Dict[str, Any]) -> float:
        """计算搜索相关性"""
        relevance = 0.0
        
        # 标题匹配权重更高
        if query in faq["question"].lower():
            relevance += 0.8
        
        # 答案匹配
        if query in faq["answer"].lower():
            relevance += 0.5
        
        # 标签匹配
        for tag in faq["tags"]:
            if query in tag.lower():
                relevance += 0.3
        
        return min(relevance, 1.0)
    
    def _get_search_suggestions(self, query: str) -> List[str]:
        """获取搜索建议"""
        suggestions = [
            "尝试使用更简单的关键词",
            "检查拼写是否正确",
            "尝试使用同义词",
            "查看常见问题解答",
            "联系技术支持获取帮助"
        ]
        
        return suggestions
    
    async def _save_feedback_to_db(self, feedback_record: Dict[str, Any]):
        """保存反馈到数据库"""
        try:
            metadata_db = await self.metadata_manager.get_metadata_database()
            feedback_collection = metadata_db["user_feedback"]
            await feedback_collection.insert_one(feedback_record)
        except Exception as e:
            self.logger.error(f"保存反馈到数据库失败: {e}")
            raise
    
    async def _get_feedback_from_db(self, feedback_id: str) -> Optional[Dict[str, Any]]:
        """从数据库获取反馈"""
        try:
            metadata_db = await self.metadata_manager.get_metadata_database()
            feedback_collection = metadata_db["user_feedback"]
            return await feedback_collection.find_one({"feedback_id": feedback_id})
        except Exception as e:
            self.logger.error(f"从数据库获取反馈失败: {e}")
            return None
    
    async def _calculate_feedback_trends(self, days: int) -> Dict[str, Any]:
        """计算反馈趋势"""
        # 这里可以实现更复杂的趋势分析
        return {
            "feedback_growth": "stable",
            "satisfaction_trend": "improving",
            "common_issues": ["connection_timeout", "query_complexity"]
        }
    
    def _generate_improvement_recommendations(self, feedback_stats: Dict[str, Any], error_stats: Dict[str, Any]) -> List[str]:
        """生成改进建议"""
        recommendations = []
        
        # 基于反馈统计生成建议
        if feedback_stats.get("average_rating", 0) < 3.5:
            recommendations.append("用户满意度较低，需要重点关注用户体验改进")
        
        # 基于错误统计生成建议
        error_types = error_stats.get("error_types", {})
        if error_types.get("connection_error", 0) > 10:
            recommendations.append("连接错误频发，建议检查网络稳定性和连接池配置")
        
        if error_types.get("timeout_error", 0) > 5:
            recommendations.append("查询超时较多，建议优化查询性能和添加索引")
        
        if not recommendations:
            recommendations.append("系统运行良好，继续保持当前服务质量")
        
        return recommendations