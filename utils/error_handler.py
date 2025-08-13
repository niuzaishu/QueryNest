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
            "cause": str(self.cause) if self.cause else None,
            "recovery_suggestions": self.get_recovery_suggestions()
        }
    
    def get_recovery_suggestions(self) -> List[str]:
        """获取错误恢复建议"""
        suggestions = []
        
        if self.category == ErrorCategory.CONNECTION:
            suggestions.extend([
                "检查网络连接是否正常",
                "验证MongoDB服务是否运行",
                "确认连接字符串是否正确",
                "检查防火墙设置"
            ])
        elif self.category == ErrorCategory.AUTHENTICATION:
            suggestions.extend([
                "检查用户名和密码是否正确",
                "验证用户是否有相应权限",
                "确认认证数据库是否正确"
            ])
        elif self.category == ErrorCategory.VALIDATION:
            suggestions.extend([
                "检查输入参数格式是否正确",
                "验证必需字段是否已提供",
                "确认参数值是否在有效范围内"
            ])
        elif self.category == ErrorCategory.TIMEOUT:
            suggestions.extend([
                "尝试增加超时时间",
                "检查查询是否过于复杂",
                "验证数据库性能是否正常"
            ])
        elif self.category == ErrorCategory.RESOURCE:
            suggestions.extend([
                "检查系统资源使用情况",
                "清理临时文件和缓存",
                "考虑增加系统资源配置"
            ])
        
        return suggestions


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
            severity=self._determine_severity(error),
            details={
                'original_type': type(error).__name__,
                'error_type': error_type.value,
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
                    # 如果已经是QueryNestError，直接抛出
                    if isinstance(e, QueryNestError):
                        raise e
                    # 否则处理错误并创建新的QueryNestError
                    error_response = error_handler.handle_error(e, context)
                    qn_error = QueryNestError(
                        message=error_response.get('message', str(e)),
                        severity=ErrorSeverity(error_response.get('severity', 'medium')),
                        details=error_response.get('details', {}),
                        cause=e
                    )
                    raise qn_error
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    # 如果已经是QueryNestError，直接抛出
                    if isinstance(e, QueryNestError):
                        raise e
                    # 否则处理错误并创建新的QueryNestError
                    error_response = error_handler.handle_error(e, context)
                    qn_error = QueryNestError(
                        message=error_response.get('message', str(e)),
                        severity=ErrorSeverity(error_response.get('severity', 'medium')),
                        details=error_response.get('details', {}),
                        cause=e
                    )
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


class ErrorRecoveryManager:
    """智能错误恢复管理器"""
    
    def __init__(self):
        self.recovery_strategies = {}
        self.failure_patterns = {}
        self.success_patterns = {}
        self._setup_default_strategies()
    
    def _setup_default_strategies(self):
        """设置默认恢复策略"""
        
        # 连接错误恢复策略
        self.recovery_strategies[ErrorCategory.CONNECTION] = [
            {
                "name": "connection_retry",
                "description": "重试连接",
                "action": self._retry_connection,
                "max_attempts": 3,
                "delay": 2.0
            },
            {
                "name": "fallback_instance",
                "description": "切换到备用实例",
                "action": self._try_fallback_instance,
                "max_attempts": 1,
                "delay": 0.5
            }
        ]
        
        # 超时错误恢复策略
        self.recovery_strategies[ErrorCategory.TIMEOUT] = [
            {
                "name": "increase_timeout",
                "description": "增加超时时间",
                "action": self._increase_timeout,
                "max_attempts": 2,
                "delay": 1.0
            },
            {
                "name": "simplify_query",
                "description": "简化查询",
                "action": self._simplify_query,
                "max_attempts": 1,
                "delay": 0.5
            }
        ]
        
        # 验证错误恢复策略
        self.recovery_strategies[ErrorCategory.VALIDATION] = [
            {
                "name": "auto_fix_params",
                "description": "自动修复参数",
                "action": self._auto_fix_parameters,
                "max_attempts": 1,
                "delay": 0.1
            }
        ]
    
    async def attempt_recovery(self, error: QueryNestError, context: Dict[str, Any]) -> Dict[str, Any]:
        """尝试错误恢复"""
        recovery_result = {
            "recovered": False,
            "strategy_used": None,
            "attempts": 0,
            "final_error": None,
            "recovery_log": []
        }
        
        # 获取该错误类别的恢复策略
        strategies = self.recovery_strategies.get(error.category, [])
        
        for strategy in strategies:
            recovery_result["attempts"] += 1
            
            try:
                logger.info(f"尝试恢复策略: {strategy['name']}", 
                           trace_id=error.trace_id)
                
                # 执行恢复策略
                result = await strategy["action"](error, context)
                
                if result.get("success", False):
                    recovery_result["recovered"] = True
                    recovery_result["strategy_used"] = strategy["name"]
                    recovery_result["recovery_log"].append({
                        "strategy": strategy["name"],
                        "success": True,
                        "result": result
                    })
                    
                    logger.info(f"恢复成功: {strategy['name']}", 
                               trace_id=error.trace_id)
                    break
                else:
                    recovery_result["recovery_log"].append({
                        "strategy": strategy["name"],
                        "success": False,
                        "error": result.get("error", "Unknown error")
                    })
                    
                    # 等待后重试
                    if strategy.get("delay", 0) > 0:
                        await asyncio.sleep(strategy["delay"])
                        
            except Exception as e:
                recovery_result["recovery_log"].append({
                    "strategy": strategy["name"],
                    "success": False,
                    "error": str(e)
                })
                logger.error(f"恢复策略执行失败: {strategy['name']}", 
                           error=str(e), trace_id=error.trace_id)
        
        if not recovery_result["recovered"]:
            recovery_result["final_error"] = error.to_dict()
        
        return recovery_result
    
    async def _retry_connection(self, error: QueryNestError, context: Dict[str, Any]) -> Dict[str, Any]:
        """重试连接策略"""
        try:
            # 模拟重试连接逻辑
            connection_manager = context.get("connection_manager")
            instance_name = context.get("instance_name")
            
            if connection_manager and instance_name:
                # 重新初始化连接
                success = await connection_manager.init_instance_metadata_on_demand(instance_name)
                if success:
                    return {"success": True, "message": "连接重试成功"}
            
            return {"success": False, "error": "无法重试连接"}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _try_fallback_instance(self, error: QueryNestError, context: Dict[str, Any]) -> Dict[str, Any]:
        """切换到备用实例策略"""
        try:
            connection_manager = context.get("connection_manager")
            
            if connection_manager:
                # 获取可用实例列表
                available_instances = connection_manager.get_available_instances()
                current_instance = context.get("instance_name")
                
                # 找到第一个可用的备用实例
                for instance in available_instances:
                    if instance != current_instance:
                        context["instance_name"] = instance
                        return {"success": True, "message": f"切换到备用实例: {instance}"}
            
            return {"success": False, "error": "没有可用的备用实例"}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _increase_timeout(self, error: QueryNestError, context: Dict[str, Any]) -> Dict[str, Any]:
        """增加超时时间策略"""
        try:
            current_timeout = context.get("timeout", 30)
            new_timeout = min(current_timeout * 2, 120)  # 最大120秒
            context["timeout"] = new_timeout
            
            return {"success": True, "message": f"超时时间增加到 {new_timeout} 秒"}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _simplify_query(self, error: QueryNestError, context: Dict[str, Any]) -> Dict[str, Any]:
        """简化查询策略"""
        try:
            query = context.get("query", {})
            
            # 简化查询的一些策略
            if "$and" in query and len(query["$and"]) > 1:
                # 减少AND条件数量
                query["$and"] = query["$and"][:1]
                context["query"] = query
                return {"success": True, "message": "简化了查询条件"}
            
            if "limit" not in context or context.get("limit", 0) > 100:
                # 减少查询结果数量
                context["limit"] = 50
                return {"success": True, "message": "减少了查询结果数量"}
            
            return {"success": False, "error": "无法进一步简化查询"}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _auto_fix_parameters(self, error: QueryNestError, context: Dict[str, Any]) -> Dict[str, Any]:
        """自动修复参数策略"""
        try:
            # 一些常见的参数修复策略
            fixed_params = []
            
            # 修复空字符串
            for key, value in context.items():
                if isinstance(value, str) and value.strip() == "":
                    context[key] = None
                    fixed_params.append(f"{key}: 空字符串->None")
            
            # 修复负数限制
            if "limit" in context and context["limit"] < 0:
                context["limit"] = 10
                fixed_params.append("limit: 负数->10")
            
            if fixed_params:
                return {"success": True, "message": f"修复了参数: {', '.join(fixed_params)}"}
            
            return {"success": False, "error": "没有需要修复的参数"}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def add_custom_strategy(self, category: ErrorCategory, strategy: Dict[str, Any]):
        """添加自定义恢复策略"""
        if category not in self.recovery_strategies:
            self.recovery_strategies[category] = []
        
        self.recovery_strategies[category].append(strategy)
        logger.info(f"添加了自定义恢复策略: {strategy['name']}", category=category.value)
    
    def get_recovery_statistics(self) -> Dict[str, Any]:
        """获取恢复统计信息"""
        return {
            "total_strategies": sum(len(strategies) for strategies in self.recovery_strategies.values()),
            "categories_covered": len(self.recovery_strategies),
            "strategies_by_category": {
                category.value: len(strategies) 
                for category, strategies in self.recovery_strategies.items()
            }
        }


# 全局错误恢复管理器实例
recovery_manager = ErrorRecoveryManager()


def get_recovery_manager() -> ErrorRecoveryManager:
    """获取全局错误恢复管理器"""
    return recovery_manager