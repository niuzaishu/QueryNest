#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
错误处理和用户反馈机制
"""

import logging
import traceback
from typing import Dict, Any, Optional, List
from enum import Enum
from datetime import datetime
import json


class ErrorType(Enum):
    """错误类型枚举"""
    CONNECTION_ERROR = "connection_error"
    QUERY_ERROR = "query_error"
    VALIDATION_ERROR = "validation_error"
    PERMISSION_ERROR = "permission_error"
    TIMEOUT_ERROR = "timeout_error"
    RESOURCE_ERROR = "resource_error"
    CONFIGURATION_ERROR = "configuration_error"
    INTERNAL_ERROR = "internal_error"
    USER_INPUT_ERROR = "user_input_error"
    SEMANTIC_ERROR = "semantic_error"


class ErrorSeverity(Enum):
    """错误严重程度"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class QueryNestError(Exception):
    """QueryNest自定义异常基类"""
    
    def __init__(
        self,
        message: str,
        error_type: ErrorType,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        details: Optional[Dict[str, Any]] = None,
        suggestions: Optional[List[str]] = None,
        user_friendly_message: Optional[str] = None
    ):
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.severity = severity
        self.details = details or {}
        self.suggestions = suggestions or []
        self.user_friendly_message = user_friendly_message or self._generate_user_friendly_message()
        self.timestamp = datetime.now()
        self.error_id = self._generate_error_id()
    
    def _generate_error_id(self) -> str:
        """生成错误ID"""
        import uuid
        return str(uuid.uuid4())[:8]
    
    def _generate_user_friendly_message(self) -> str:
        """生成用户友好的错误消息"""
        error_messages = {
            ErrorType.CONNECTION_ERROR: "无法连接到数据库，请检查网络连接和数据库配置",
            ErrorType.QUERY_ERROR: "查询执行失败，请检查查询语法和参数",
            ErrorType.VALIDATION_ERROR: "输入数据验证失败，请检查输入格式",
            ErrorType.PERMISSION_ERROR: "权限不足，无法执行此操作",
            ErrorType.TIMEOUT_ERROR: "操作超时，请稍后重试或简化查询条件",
            ErrorType.RESOURCE_ERROR: "系统资源不足，请稍后重试",
            ErrorType.CONFIGURATION_ERROR: "系统配置错误，请联系管理员",
            ErrorType.INTERNAL_ERROR: "系统内部错误，请联系技术支持",
            ErrorType.USER_INPUT_ERROR: "输入内容有误，请检查并重新输入",
            ErrorType.SEMANTIC_ERROR: "无法理解查询意图，请提供更具体的描述"
        }
        return error_messages.get(self.error_type, "发生未知错误，请联系技术支持")
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "error_id": self.error_id,
            "message": self.message,
            "user_friendly_message": self.user_friendly_message,
            "error_type": self.error_type.value,
            "severity": self.severity.value,
            "details": self.details,
            "suggestions": self.suggestions,
            "timestamp": self.timestamp.isoformat()
        }


class ConnectionError(QueryNestError):
    """连接错误"""
    
    def __init__(self, message: str, instance_id: str = None, **kwargs):
        details = kwargs.get('details', {})
        if instance_id:
            details['instance_id'] = instance_id
        
        suggestions = [
            "检查数据库服务是否正常运行",
            "验证网络连接是否正常",
            "确认数据库连接配置是否正确",
            "检查防火墙设置"
        ]
        
        super().__init__(
            message=message,
            error_type=ErrorType.CONNECTION_ERROR,
            severity=ErrorSeverity.HIGH,
            details=details,
            suggestions=suggestions,
            **kwargs
        )


class QueryExecutionError(QueryNestError):
    """查询执行错误"""
    
    def __init__(self, message: str, query: Dict[str, Any] = None, **kwargs):
        details = kwargs.get('details', {})
        if query:
            details['query'] = query
        
        suggestions = [
            "检查查询语法是否正确",
            "验证字段名称是否存在",
            "确认查询条件是否合理",
            "尝试简化查询条件"
        ]
        
        super().__init__(
            message=message,
            error_type=ErrorType.QUERY_ERROR,
            severity=ErrorSeverity.MEDIUM,
            details=details,
            suggestions=suggestions,
            **kwargs
        )


class ValidationError(QueryNestError):
    """验证错误"""
    
    def __init__(self, message: str, field: str = None, value: Any = None, **kwargs):
        details = kwargs.get('details', {})
        if field:
            details['field'] = field
        if value is not None:
            details['value'] = str(value)
        
        suggestions = [
            "检查输入数据格式是否正确",
            "确认必填字段是否已提供",
            "验证数据类型是否匹配"
        ]
        
        super().__init__(
            message=message,
            error_type=ErrorType.VALIDATION_ERROR,
            severity=ErrorSeverity.LOW,
            details=details,
            suggestions=suggestions,
            **kwargs
        )


class PermissionError(QueryNestError):
    """权限错误"""
    
    def __init__(self, message: str, operation: str = None, resource: str = None, **kwargs):
        details = kwargs.get('details', {})
        if operation:
            details['operation'] = operation
        if resource:
            details['resource'] = resource
        
        suggestions = [
            "联系管理员获取相应权限",
            "确认当前用户角色是否正确",
            "检查资源访问策略"
        ]
        
        super().__init__(
            message=message,
            error_type=ErrorType.PERMISSION_ERROR,
            severity=ErrorSeverity.HIGH,
            details=details,
            suggestions=suggestions,
            **kwargs
        )


class SemanticError(QueryNestError):
    """语义理解错误"""
    
    def __init__(self, message: str, user_intent: str = None, **kwargs):
        details = kwargs.get('details', {})
        if user_intent:
            details['user_intent'] = user_intent
        
        suggestions = [
            "请提供更具体的查询描述",
            "尝试使用不同的表达方式",
            "参考查询示例重新组织语言",
            "指定具体的字段名称和条件"
        ]
        
        super().__init__(
            message=message,
            error_type=ErrorType.SEMANTIC_ERROR,
            severity=ErrorSeverity.LOW,
            details=details,
            suggestions=suggestions,
            **kwargs
        )


class ErrorHandler:
    """错误处理器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.error_history: List[Dict[str, Any]] = []
        self.max_history_size = 1000
        self.config = {}
    
    def initialize(self, config: Dict[str, Any]):
        """初始化错误处理器"""
        self.config = config
        
        # 更新最大历史记录大小
        if 'max_history_size' in config:
            self.max_history_size = config['max_history_size']
        
        # 设置日志级别
        if 'log_level' in config:
            log_level = getattr(logging, config['log_level'].upper(), logging.INFO)
            self.logger.setLevel(log_level)
        
        self.logger.info("错误处理器已初始化")
    
    def handle_error(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """处理错误并返回标准化的错误响应"""
        
        # 如果是QueryNest自定义错误
        if isinstance(error, QueryNestError):
            error_response = error.to_dict()
        else:
            # 处理其他类型的错误
            error_response = self._handle_generic_error(error)
        
        # 添加上下文信息
        if context:
            error_response['context'] = context
        
        # 记录错误
        self._log_error(error_response)
        
        # 保存到历史记录
        self._save_to_history(error_response)
        
        return error_response
    
    def _handle_generic_error(self, error: Exception) -> Dict[str, Any]:
        """处理通用错误"""
        error_type = self._classify_error(error)
        
        querynest_error = QueryNestError(
            message=str(error),
            error_type=error_type,
            severity=self._determine_severity(error),
            details={
                'original_type': type(error).__name__,
                'traceback': traceback.format_exc()
            }
        )
        
        return querynest_error.to_dict()
    
    def _classify_error(self, error: Exception) -> ErrorType:
        """分类错误类型"""
        error_name = type(error).__name__.lower()
        
        if 'connection' in error_name or 'network' in error_name:
            return ErrorType.CONNECTION_ERROR
        elif 'timeout' in error_name:
            return ErrorType.TIMEOUT_ERROR
        elif 'permission' in error_name or 'auth' in error_name:
            return ErrorType.PERMISSION_ERROR
        elif 'validation' in error_name or 'value' in error_name:
            return ErrorType.VALIDATION_ERROR
        elif 'memory' in error_name or 'resource' in error_name:
            return ErrorType.RESOURCE_ERROR
        else:
            return ErrorType.INTERNAL_ERROR
    
    def _determine_severity(self, error: Exception) -> ErrorSeverity:
        """确定错误严重程度"""
        error_name = type(error).__name__.lower()
        
        if 'critical' in error_name or 'fatal' in error_name:
            return ErrorSeverity.CRITICAL
        elif 'connection' in error_name or 'timeout' in error_name:
            return ErrorSeverity.HIGH
        elif 'validation' in error_name or 'value' in error_name:
            return ErrorSeverity.LOW
        else:
            return ErrorSeverity.MEDIUM
    
    def _log_error(self, error_response: Dict[str, Any]):
        """记录错误日志"""
        severity = error_response.get('severity', 'medium')
        error_id = error_response.get('error_id', 'unknown')
        message = error_response.get('message', 'Unknown error')
        
        log_message = f"[{error_id}] {message}"
        
        if severity == 'critical':
            self.logger.critical(log_message, extra={'error_data': error_response})
        elif severity == 'high':
            self.logger.error(log_message, extra={'error_data': error_response})
        elif severity == 'medium':
            self.logger.warning(log_message, extra={'error_data': error_response})
        else:
            self.logger.info(log_message, extra={'error_data': error_response})
    
    def _save_to_history(self, error_response: Dict[str, Any]):
        """保存错误到历史记录"""
        self.error_history.append(error_response)
        
        # 限制历史记录大小
        if len(self.error_history) > self.max_history_size:
            self.error_history = self.error_history[-self.max_history_size:]
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """获取错误统计信息"""
        if not self.error_history:
            return {
                'total_errors': 0,
                'error_types': {},
                'severity_distribution': {},
                'recent_errors': []
            }
        
        # 统计错误类型
        error_types = {}
        severity_distribution = {}
        
        for error in self.error_history:
            error_type = error.get('error_type', 'unknown')
            severity = error.get('severity', 'unknown')
            
            error_types[error_type] = error_types.get(error_type, 0) + 1
            severity_distribution[severity] = severity_distribution.get(severity, 0) + 1
        
        # 获取最近的错误
        recent_errors = self.error_history[-10:] if len(self.error_history) > 10 else self.error_history
        
        return {
            'total_errors': len(self.error_history),
            'error_types': error_types,
            'severity_distribution': severity_distribution,
            'recent_errors': recent_errors
        }
    
    def clear_history(self):
        """清空错误历史记录"""
        self.error_history.clear()


class UserFeedbackCollector:
    """用户反馈收集器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.feedback_history: List[Dict[str, Any]] = []
    
    def collect_feedback(
        self,
        session_id: str,
        error_id: str,
        feedback_type: str,
        rating: Optional[int] = None,
        comment: Optional[str] = None,
        suggestions: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """收集用户反馈"""
        
        feedback = {
            'feedback_id': self._generate_feedback_id(),
            'session_id': session_id,
            'error_id': error_id,
            'feedback_type': feedback_type,  # 'helpful', 'not_helpful', 'suggestion'
            'rating': rating,  # 1-5 星级评分
            'comment': comment,
            'suggestions': suggestions or [],
            'timestamp': datetime.now().isoformat()
        }
        
        self.feedback_history.append(feedback)
        
        self.logger.info(
            f"收到用户反馈: {feedback_type} (错误ID: {error_id})",
            extra={'feedback_data': feedback}
        )
        
        return feedback
    
    def _generate_feedback_id(self) -> str:
        """生成反馈ID"""
        import uuid
        return str(uuid.uuid4())[:8]
    
    def get_feedback_summary(self) -> Dict[str, Any]:
        """获取反馈摘要"""
        if not self.feedback_history:
            return {
                'total_feedback': 0,
                'feedback_types': {},
                'average_rating': 0,
                'recent_feedback': []
            }
        
        # 统计反馈类型
        feedback_types = {}
        ratings = []
        
        for feedback in self.feedback_history:
            feedback_type = feedback.get('feedback_type', 'unknown')
            rating = feedback.get('rating')
            
            feedback_types[feedback_type] = feedback_types.get(feedback_type, 0) + 1
            
            if rating is not None:
                ratings.append(rating)
        
        # 计算平均评分
        average_rating = sum(ratings) / len(ratings) if ratings else 0
        
        # 获取最近的反馈
        recent_feedback = self.feedback_history[-10:] if len(self.feedback_history) > 10 else self.feedback_history
        
        return {
            'total_feedback': len(self.feedback_history),
            'feedback_types': feedback_types,
            'average_rating': round(average_rating, 2),
            'total_ratings': len(ratings),
            'recent_feedback': recent_feedback
        }


# 全局错误处理器和反馈收集器实例
error_handler = ErrorHandler()
feedback_collector = UserFeedbackCollector()


def handle_error(error: Exception, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """全局错误处理函数"""
    return error_handler.handle_error(error, context)


def collect_user_feedback(
    session_id: str,
    error_id: str,
    feedback_type: str,
    rating: Optional[int] = None,
    comment: Optional[str] = None,
    suggestions: Optional[List[str]] = None
) -> Dict[str, Any]:
    """全局用户反馈收集函数"""
    return feedback_collector.collect_feedback(
        session_id, error_id, feedback_type, rating, comment, suggestions
    )


def initialize(config: Dict[str, Any]):
    """初始化全局错误处理器"""
    error_handler.initialize(config)