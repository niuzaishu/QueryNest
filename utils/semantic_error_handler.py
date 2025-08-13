# -*- coding: utf-8 -*-
"""
语义处理错误处理和恢复机制

提供全面的语义分析和存储错误处理、恢复和重试策略
"""

import asyncio
import traceback
import time
from typing import Dict, Any, Optional, List, Callable, Union, Type
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta
from functools import wraps
import structlog
from pathlib import Path
import json

logger = structlog.get_logger(__name__)


class ErrorSeverity(Enum):
    """错误严重程度"""
    LOW = "low"           # 低级错误，不影响核心功能
    MEDIUM = "medium"     # 中级错误，影响部分功能
    HIGH = "high"         # 高级错误，影响核心功能
    CRITICAL = "critical" # 严重错误，系统无法正常工作


class ErrorCategory(Enum):
    """错误类别"""
    STORAGE = "storage"             # 存储层错误
    SEMANTIC = "semantic"           # 语义分析错误
    VALIDATION = "validation"       # 数据验证错误
    NETWORK = "network"             # 网络连接错误
    RESOURCE = "resource"           # 资源限制错误
    CONFIGURATION = "configuration" # 配置错误
    DEPENDENCY = "dependency"       # 依赖服务错误
    UNKNOWN = "unknown"             # 未知错误


@dataclass
class ErrorContext:
    """错误上下文信息"""
    error: Exception
    severity: ErrorSeverity
    category: ErrorCategory
    operation: str
    parameters: Dict[str, Any]
    timestamp: datetime
    stack_trace: str
    recovery_attempted: bool = False
    recovery_successful: bool = False
    retry_count: int = 0
    max_retries: int = 3
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "error_type": self.error.__class__.__name__,
            "error_message": str(self.error),
            "severity": self.severity.value,
            "category": self.category.value,
            "operation": self.operation,
            "parameters": self.parameters,
            "timestamp": self.timestamp.isoformat(),
            "stack_trace": self.stack_trace,
            "recovery_attempted": self.recovery_attempted,
            "recovery_successful": self.recovery_successful,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries
        }


class RecoveryStrategy:
    """恢复策略基类"""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
    
    async def can_recover(self, error_context: ErrorContext) -> bool:
        """检查是否可以恢复"""
        return False
    
    async def recover(self, error_context: ErrorContext) -> bool:
        """执行恢复操作"""
        return False


class RetryStrategy(RecoveryStrategy):
    """重试策略"""
    
    def __init__(self, max_retries: int = 3, delay: float = 1.0, backoff_factor: float = 2.0):
        super().__init__("retry", "重试执行操作")
        self.max_retries = max_retries
        self.delay = delay
        self.backoff_factor = backoff_factor
    
    async def can_recover(self, error_context: ErrorContext) -> bool:
        """检查是否可以重试"""
        if error_context.retry_count >= self.max_retries:
            return False
        
        # 可重试的错误类型
        retriable_errors = [
            "ConnectionError", "TimeoutError", "TemporaryFailure",
            "ResourceBusyError", "NetworkError"
        ]
        
        error_name = error_context.error.__class__.__name__
        return any(retriable in error_name for retriable in retriable_errors)
    
    async def recover(self, error_context: ErrorContext) -> bool:
        """执行重试"""
        try:
            # 计算延迟时间
            delay = self.delay * (self.backoff_factor ** error_context.retry_count)
            
            logger.info(f"重试操作 {error_context.operation}",
                       retry_count=error_context.retry_count + 1,
                       max_retries=self.max_retries,
                       delay=delay)
            
            await asyncio.sleep(delay)
            error_context.retry_count += 1
            
            return True
            
        except Exception as e:
            logger.error("重试策略执行失败", error=str(e))
            return False


class FallbackStrategy(RecoveryStrategy):
    """降级策略"""
    
    def __init__(self, fallback_func: Callable = None):
        super().__init__("fallback", "使用降级方案")
        self.fallback_func = fallback_func
    
    async def can_recover(self, error_context: ErrorContext) -> bool:
        """检查是否可以降级"""
        return self.fallback_func is not None
    
    async def recover(self, error_context: ErrorContext) -> bool:
        """执行降级操作"""
        try:
            if self.fallback_func:
                logger.info(f"执行降级操作 {error_context.operation}")
                
                # 执行降级函数
                if asyncio.iscoroutinefunction(self.fallback_func):
                    await self.fallback_func(error_context)
                else:
                    self.fallback_func(error_context)
                
                return True
            
            return False
            
        except Exception as e:
            logger.error("降级策略执行失败", error=str(e))
            return False


class CacheRecoveryStrategy(RecoveryStrategy):
    """缓存恢复策略"""
    
    def __init__(self, cache_manager=None):
        super().__init__("cache_recovery", "从缓存恢复数据")
        self.cache_manager = cache_manager
    
    async def can_recover(self, error_context: ErrorContext) -> bool:
        """检查是否可以从缓存恢复"""
        return (self.cache_manager is not None and 
                error_context.category == ErrorCategory.STORAGE)
    
    async def recover(self, error_context: ErrorContext) -> bool:
        """从缓存恢复"""
        try:
            logger.info(f"尝试从缓存恢复 {error_context.operation}")
            
            # 这里应该根据具体的缓存键策略来恢复数据
            # 简化实现，仅作示例
            
            return False  # 实际实现中应该返回真实的恢复结果
            
        except Exception as e:
            logger.error("缓存恢复策略执行失败", error=str(e))
            return False


class ErrorRecorder:
    """错误记录器"""
    
    def __init__(self, log_file: str = "data/logs/semantic_errors.jsonl"):
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
    
    async def record_error(self, error_context: ErrorContext):
        """记录错误"""
        try:
            error_record = {
                **error_context.to_dict(),
                "recorded_at": datetime.now().isoformat()
            }
            
            # 异步写入日志文件
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(error_record, ensure_ascii=False) + '\n')
            
            # 同时记录到结构化日志
            logger.error("语义处理错误记录",
                        operation=error_context.operation,
                        error_type=error_context.error.__class__.__name__,
                        severity=error_context.severity.value,
                        category=error_context.category.value,
                        retry_count=error_context.retry_count)
            
        except Exception as e:
            logger.error("错误记录失败", error=str(e))
    
    async def get_error_statistics(self, days: int = 7) -> Dict[str, Any]:
        """获取错误统计"""
        stats = {
            "total_errors": 0,
            "by_category": {},
            "by_severity": {},
            "by_operation": {},
            "recovery_rate": 0.0,
            "retry_success_rate": 0.0
        }
        
        try:
            if not self.log_file.exists():
                return stats
            
            cutoff_time = datetime.now() - timedelta(days=days)
            
            total_errors = 0
            successful_recoveries = 0
            retry_successes = 0
            total_retries = 0
            
            with open(self.log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        error_record = json.loads(line.strip())
                        error_time = datetime.fromisoformat(error_record["timestamp"])
                        
                        if error_time < cutoff_time:
                            continue
                        
                        total_errors += 1
                        
                        # 按类别统计
                        category = error_record.get("category", "unknown")
                        stats["by_category"][category] = stats["by_category"].get(category, 0) + 1
                        
                        # 按严重程度统计
                        severity = error_record.get("severity", "unknown")
                        stats["by_severity"][severity] = stats["by_severity"].get(severity, 0) + 1
                        
                        # 按操作统计
                        operation = error_record.get("operation", "unknown")
                        stats["by_operation"][operation] = stats["by_operation"].get(operation, 0) + 1
                        
                        # 恢复统计
                        if error_record.get("recovery_successful", False):
                            successful_recoveries += 1
                        
                        # 重试统计
                        retry_count = error_record.get("retry_count", 0)
                        if retry_count > 0:
                            total_retries += 1
                            if error_record.get("recovery_successful", False):
                                retry_successes += 1
                    
                    except (json.JSONDecodeError, ValueError):
                        continue
            
            stats["total_errors"] = total_errors
            stats["recovery_rate"] = successful_recoveries / total_errors if total_errors > 0 else 0
            stats["retry_success_rate"] = retry_successes / total_retries if total_retries > 0 else 0
            
        except Exception as e:
            logger.error("获取错误统计失败", error=str(e))
        
        return stats


class SemanticErrorHandler:
    """语义处理错误处理器"""
    
    def __init__(self):
        self.recovery_strategies: List[RecoveryStrategy] = []
        self.error_recorder = ErrorRecorder()
        
        # 注册默认恢复策略
        self._register_default_strategies()
        
        logger.info("语义错误处理器初始化完成")
    
    def _register_default_strategies(self):
        """注册默认恢复策略"""
        # 重试策略
        self.recovery_strategies.append(RetryStrategy(max_retries=3, delay=1.0))
        
        # 缓存恢复策略
        self.recovery_strategies.append(CacheRecoveryStrategy())
        
        # 降级策略（默认无降级函数）
        self.recovery_strategies.append(FallbackStrategy())
    
    def register_recovery_strategy(self, strategy: RecoveryStrategy):
        """注册自定义恢复策略"""
        self.recovery_strategies.append(strategy)
        logger.info(f"已注册恢复策略: {strategy.name}")
    
    def _classify_error(self, error: Exception, operation: str) -> Tuple[ErrorSeverity, ErrorCategory]:
        """分类错误"""
        error_name = error.__class__.__name__
        
        # 错误类别分类
        category = ErrorCategory.UNKNOWN
        
        if "Storage" in error_name or "File" in error_name or "IO" in error_name:
            category = ErrorCategory.STORAGE
        elif "Semantic" in error_name or "Analysis" in error_name:
            category = ErrorCategory.SEMANTIC
        elif "Validation" in error_name or "Invalid" in error_name:
            category = ErrorCategory.VALIDATION
        elif "Connection" in error_name or "Network" in error_name or "Timeout" in error_name:
            category = ErrorCategory.NETWORK
        elif "Memory" in error_name or "Resource" in error_name:
            category = ErrorCategory.RESOURCE
        elif "Config" in error_name or "Setting" in error_name:
            category = ErrorCategory.CONFIGURATION
        elif "Service" in error_name or "Dependency" in error_name:
            category = ErrorCategory.DEPENDENCY
        
        # 错误严重程度分类
        severity = ErrorSeverity.MEDIUM
        
        critical_patterns = ["Critical", "Fatal", "Shutdown", "Corruption"]
        high_patterns = ["Database", "Storage", "Security", "Authentication"]
        low_patterns = ["Temporary", "Retry", "Cache", "Warning"]
        
        error_str = str(error).lower()
        
        if any(pattern.lower() in error_str for pattern in critical_patterns):
            severity = ErrorSeverity.CRITICAL
        elif any(pattern.lower() in error_str for pattern in high_patterns):
            severity = ErrorSeverity.HIGH
        elif any(pattern.lower() in error_str for pattern in low_patterns):
            severity = ErrorSeverity.LOW
        
        return severity, category
    
    async def handle_error(self, error: Exception, operation: str, 
                          parameters: Dict[str, Any] = None) -> bool:
        """处理错误"""
        if parameters is None:
            parameters = {}
        
        # 分类错误
        severity, category = self._classify_error(error, operation)
        
        # 创建错误上下文
        error_context = ErrorContext(
            error=error,
            severity=severity,
            category=category,
            operation=operation,
            parameters=parameters,
            timestamp=datetime.now(),
            stack_trace=traceback.format_exc()
        )
        
        # 记录错误
        await self.error_recorder.record_error(error_context)
        
        # 尝试恢复
        recovery_successful = False
        
        for strategy in self.recovery_strategies:
            try:
                if await strategy.can_recover(error_context):
                    logger.info(f"尝试使用恢复策略: {strategy.name}",
                               operation=operation,
                               error_type=error.__class__.__name__)
                    
                    error_context.recovery_attempted = True
                    recovery_successful = await strategy.recover(error_context)
                    
                    if recovery_successful:
                        error_context.recovery_successful = True
                        logger.info(f"恢复策略成功: {strategy.name}",
                                   operation=operation)
                        break
                    else:
                        logger.warning(f"恢复策略失败: {strategy.name}",
                                      operation=operation)
            
            except Exception as strategy_error:
                logger.error(f"恢复策略异常: {strategy.name}",
                            error=str(strategy_error))
        
        # 更新错误记录
        if error_context.recovery_attempted:
            await self.error_recorder.record_error(error_context)
        
        return recovery_successful


def with_error_handling(operation_name: str, 
                       max_retries: int = 3,
                       fallback_func: Callable = None):
    """错误处理装饰器"""
    
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            error_handler = SemanticErrorHandler()
            
            # 添加自定义重试策略
            retry_strategy = RetryStrategy(max_retries=max_retries)
            error_handler.recovery_strategies.insert(0, retry_strategy)
            
            # 添加自定义降级策略
            if fallback_func:
                fallback_strategy = FallbackStrategy(fallback_func)
                error_handler.recovery_strategies.append(fallback_strategy)
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                    
                except Exception as e:
                    if attempt == max_retries:
                        # 最后一次尝试失败，进行错误处理
                        parameters = {
                            "args": [str(arg) for arg in args],
                            "kwargs": {k: str(v) for k, v in kwargs.items()},
                            "attempt": attempt + 1
                        }
                        
                        recovery_successful = await error_handler.handle_error(
                            e, operation_name, parameters
                        )
                        
                        if not recovery_successful:
                            raise e
                    else:
                        # 创建临时错误上下文用于重试判断
                        severity, category = error_handler._classify_error(e, operation_name)
                        temp_context = ErrorContext(
                            error=e, severity=severity, category=category,
                            operation=operation_name, parameters={},
                            timestamp=datetime.now(), stack_trace="",
                            retry_count=attempt
                        )
                        
                        # 检查是否应该重试
                        should_retry = await retry_strategy.can_recover(temp_context)
                        
                        if should_retry:
                            delay = retry_strategy.delay * (retry_strategy.backoff_factor ** attempt)
                            logger.info(f"重试 {operation_name}",
                                       attempt=attempt + 1,
                                       delay=delay)
                            await asyncio.sleep(delay)
                        else:
                            raise e
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # 同步函数的简化错误处理
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"操作失败: {operation_name}",
                            error=str(e),
                            error_type=e.__class__.__name__)
                raise e
        
        # 根据函数类型返回相应的包装器
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# 便捷函数
async def handle_semantic_error(error: Exception, operation: str, 
                              parameters: Dict[str, Any] = None) -> bool:
    """处理语义处理错误的便捷函数"""
    handler = SemanticErrorHandler()
    return await handler.handle_error(error, operation, parameters)


async def get_error_statistics(days: int = 7) -> Dict[str, Any]:
    """获取错误统计的便捷函数"""
    recorder = ErrorRecorder()
    return await recorder.get_error_statistics(days)


# 使用示例装饰器
@with_error_handling("semantic_analysis", max_retries=2)
async def example_semantic_operation():
    """使用装饰器的示例函数"""
    # 这里是实际的语义操作代码
    pass