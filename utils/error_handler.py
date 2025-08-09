#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一错误处理和重试机制
"""

import asyncio
import functools
from typing import Any, Callable, Optional, Type, Union, List, Dict
from datetime import datetime, timedelta
import structlog
import traceback
from enum import Enum
import json
import logging

logger = structlog.get_logger(__name__)


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


class ErrorCategory(Enum):
    """错误分类"""
    CONNECTION = "connection"
    AUTHENTICATION = "authentication"
    PERMISSION = "permission"
    VALIDATION = "validation"
    TIMEOUT = "timeout"
    RESOURCE = "resource"
    BUSINESS = "business"
    SYSTEM = "system"
    UNKNOWN = "unknown"


class QueryNestError(Exception):
    """QueryNest基础异常类"""
    
    def __init__(self, message: str, category: ErrorCategory = ErrorCategory.UNKNOWN, 
                 severity: ErrorSeverity = ErrorSeverity.MEDIUM, 
                 details: Optional[dict] = None, cause: Optional[Exception] = None):
        super().__init__(message)
        self.message = message
        self.category = category
        self.severity = severity
        self.details = details or {}
        self.cause = cause
        self.timestamp = datetime.now()
        self.trace_id = self._generate_trace_id()
    
    def _generate_trace_id(self) -> str:
        """生成追踪ID"""
        import uuid
        return str(uuid.uuid4())[:8]
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "message": self.message,
            "category": self.category.value,
            "severity": self.severity.value,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
            "trace_id": self.trace_id,
            "cause": str(self.cause) if self.cause else None
        }


class ConnectionError(QueryNestError):
    """连接错误"""
    def __init__(self, message: str, details: Optional[dict] = None, cause: Optional[Exception] = None):
        super().__init__(message, ErrorCategory.CONNECTION, ErrorSeverity.HIGH, details, cause)


class AuthenticationError(QueryNestError):
    """认证错误"""
    def __init__(self, message: str, details: Optional[dict] = None, cause: Optional[Exception] = None):
        super().__init__(message, ErrorCategory.AUTHENTICATION, ErrorSeverity.HIGH, details, cause)


class ValidationError(QueryNestError):
    """验证错误"""
    def __init__(self, message: str, details: Optional[dict] = None, cause: Optional[Exception] = None):
        super().__init__(message, ErrorCategory.VALIDATION, ErrorSeverity.MEDIUM, details, cause)


class TimeoutError(QueryNestError):
    """超时错误"""
    def __init__(self, message: str, details: Optional[dict] = None, cause: Optional[Exception] = None):
        super().__init__(message, ErrorCategory.TIMEOUT, ErrorSeverity.MEDIUM, details, cause)


class ConfigurationError(QueryNestError):
    """配置错误"""
    def __init__(self, message: str, details: Optional[dict] = None, cause: Optional[Exception] = None):
        super().__init__(message, ErrorCategory.SYSTEM, ErrorSeverity.HIGH, details, cause)


class ToolError(QueryNestError):
    """工具执行错误"""
    def __init__(self, message: str, tool_name: str, details: Optional[dict] = None, cause: Optional[Exception] = None):
        details = details or {}
        details["tool_name"] = tool_name
        super().__init__(message, ErrorCategory.BUSINESS, ErrorSeverity.MEDIUM, details, cause)


class RetryConfig:
    """重试配置"""
    
    def __init__(self, max_attempts: int = 3, base_delay: float = 1.0, 
                 max_delay: float = 60.0, exponential_base: float = 2.0,
                 jitter: bool = True, retryable_exceptions: Optional[List[Type[Exception]]] = None):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retryable_exceptions = retryable_exceptions or [
            ConnectionError, TimeoutError, OSError, asyncio.TimeoutError
        ]
    
    def calculate_delay(self, attempt: int) -> float:
        """计算延迟时间"""
        delay = self.base_delay * (self.exponential_base ** (attempt - 1))
        delay = min(delay, self.max_delay)
        
        if self.jitter:
            import random
            delay *= (0.5 + random.random() * 0.5)  # 添加50%的随机抖动
        
        return delay
    
    def should_retry(self, exception: Exception, attempt: int) -> bool:
        """判断是否应该重试"""
        if attempt >= self.max_attempts:
            return False
        
        return any(isinstance(exception, exc_type) for exc_type in self.retryable_exceptions)


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


def with_error_handling(context: Optional[dict] = None):
    """错误处理装饰器"""
    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    qn_error = error_handler.handle_error(e, context)
                    raise qn_error
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    qn_error = error_handler.handle_error(e, context)
                    raise qn_error
            return sync_wrapper
    return decorator


def with_retry(config: Optional[RetryConfig] = None):
    """重试装饰器"""
    retry_config = config or RetryConfig()
    
    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                last_exception = None
                
                for attempt in range(1, retry_config.max_attempts + 1):
                    try:
                        return await func(*args, **kwargs)
                    except Exception as e:
                        last_exception = e
                        
                        if not retry_config.should_retry(e, attempt):
                            break
                        
                        if attempt < retry_config.max_attempts:
                            delay = retry_config.calculate_delay(attempt)
                            logger.warning(
                                f"函数 {func.__name__} 第 {attempt} 次尝试失败，{delay:.2f}秒后重试",
                                error=str(e), attempt=attempt, max_attempts=retry_config.max_attempts
                            )
                            await asyncio.sleep(delay)
                
                # 所有重试都失败了
                logger.error(
                    f"函数 {func.__name__} 在 {retry_config.max_attempts} 次尝试后仍然失败",
                    error=str(last_exception)
                )
                raise last_exception
            
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                last_exception = None
                
                for attempt in range(1, retry_config.max_attempts + 1):
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        last_exception = e
                        
                        if not retry_config.should_retry(e, attempt):
                            break
                        
                        if attempt < retry_config.max_attempts:
                            delay = retry_config.calculate_delay(attempt)
                            logger.warning(
                                f"函数 {func.__name__} 第 {attempt} 次尝试失败，{delay:.2f}秒后重试",
                                error=str(e), attempt=attempt, max_attempts=retry_config.max_attempts
                            )
                            import time
                            time.sleep(delay)
                
                # 所有重试都失败了
                logger.error(
                    f"函数 {func.__name__} 在 {retry_config.max_attempts} 次尝试后仍然失败",
                    error=str(last_exception)
                )
                raise last_exception
            
            return sync_wrapper
    
    return decorator


# 便捷的组合装饰器
def with_error_handling_and_retry(error_context: Optional[dict] = None, 
                                 retry_config: Optional[RetryConfig] = None):
    """错误处理和重试组合装饰器"""
    def decorator(func: Callable) -> Callable:
        # 先应用重试，再应用错误处理
        func = with_retry(retry_config)(func)
        func = with_error_handling(error_context)(func)
        return func
    return decorator


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