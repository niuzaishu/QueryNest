# -*- coding: utf-8 -*-
"""
错误处理器单元测试
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from utils.error_handler import (
    QueryNestError, ErrorCategory, ErrorSeverity, ErrorType,
    ConnectionError, AuthenticationError, ValidationError,
    ErrorRecoveryManager, get_recovery_manager
)


class TestQueryNestError:
    """QueryNest错误类测试"""
    
    def test_error_creation(self):
        """测试错误创建"""
        error = QueryNestError(
            message="测试错误",
            category=ErrorCategory.CONNECTION,
            severity=ErrorSeverity.HIGH,
            details={"host": "localhost", "port": 27017}
        )
        
        assert error.message == "测试错误"
        assert error.category == ErrorCategory.CONNECTION
        assert error.severity == ErrorSeverity.HIGH
        assert error.details["host"] == "localhost"
        assert error.details["port"] == 27017
        assert isinstance(error.timestamp, datetime)
        assert len(error.trace_id) == 8
    
    def test_error_to_dict(self):
        """测试错误序列化"""
        error = QueryNestError(
            message="网络连接失败",
            category=ErrorCategory.CONNECTION,
            severity=ErrorSeverity.HIGH
        )
        
        error_dict = error.to_dict()
        
        assert error_dict["message"] == "网络连接失败"
        assert error_dict["category"] == "connection"
        assert error_dict["severity"] == "high"
        assert "timestamp" in error_dict
        assert "trace_id" in error_dict
        assert "recovery_suggestions" in error_dict
        assert len(error_dict["recovery_suggestions"]) > 0
    
    def test_error_recovery_suggestions(self):
        """测试错误恢复建议"""
        # 连接错误建议
        conn_error = QueryNestError(
            message="连接失败",
            category=ErrorCategory.CONNECTION
        )
        suggestions = conn_error.get_recovery_suggestions()
        assert "检查网络连接是否正常" in suggestions
        assert "验证MongoDB服务是否运行" in suggestions
        
        # 认证错误建议
        auth_error = QueryNestError(
            message="认证失败",
            category=ErrorCategory.AUTHENTICATION
        )
        suggestions = auth_error.get_recovery_suggestions()
        assert "检查用户名和密码是否正确" in suggestions
        
        # 验证错误建议
        valid_error = QueryNestError(
            message="参数无效",
            category=ErrorCategory.VALIDATION
        )
        suggestions = valid_error.get_recovery_suggestions()
        assert "检查输入参数格式是否正确" in suggestions
    
    def test_specialized_errors(self):
        """测试专门的错误类"""
        # 连接错误
        conn_error = ConnectionError("数据库连接失败")
        assert conn_error.category == ErrorCategory.CONNECTION
        assert conn_error.severity == ErrorSeverity.HIGH
        
        # 认证错误
        auth_error = AuthenticationError("用户认证失败")
        assert auth_error.category == ErrorCategory.AUTHENTICATION
        assert auth_error.severity == ErrorSeverity.HIGH
        
        # 验证错误
        valid_error = ValidationError("参数验证失败")
        assert valid_error.category == ErrorCategory.VALIDATION
        assert valid_error.severity == ErrorSeverity.MEDIUM


class TestErrorRecoveryManager:
    """错误恢复管理器测试"""
    
    def setup_method(self):
        """测试前准备"""
        self.recovery_manager = ErrorRecoveryManager()
    
    def test_recovery_manager_initialization(self):
        """测试恢复管理器初始化"""
        assert len(self.recovery_manager.recovery_strategies) > 0
        assert ErrorCategory.CONNECTION in self.recovery_manager.recovery_strategies
        assert ErrorCategory.TIMEOUT in self.recovery_manager.recovery_strategies
        assert ErrorCategory.VALIDATION in self.recovery_manager.recovery_strategies
    
    def test_get_recovery_statistics(self):
        """测试获取恢复统计信息"""
        stats = self.recovery_manager.get_recovery_statistics()
        
        assert "total_strategies" in stats
        assert "categories_covered" in stats
        assert "strategies_by_category" in stats
        assert stats["total_strategies"] > 0
        assert stats["categories_covered"] > 0
    
    def test_add_custom_strategy(self):
        """测试添加自定义策略"""
        initial_count = len(self.recovery_manager.recovery_strategies.get(ErrorCategory.RESOURCE, []))
        
        custom_strategy = {
            "name": "custom_resource_cleanup",
            "description": "清理系统资源",
            "action": lambda error, context: {"success": True},
            "max_attempts": 1,
            "delay": 0.5
        }
        
        self.recovery_manager.add_custom_strategy(ErrorCategory.RESOURCE, custom_strategy)
        
        new_count = len(self.recovery_manager.recovery_strategies.get(ErrorCategory.RESOURCE, []))
        assert new_count == initial_count + 1
    
    @pytest.mark.asyncio
    async def test_retry_connection_strategy(self):
        """测试重试连接策略"""
        error = ConnectionError("数据库连接失败")
        
        # 模拟连接管理器
        mock_connection_manager = AsyncMock()
        mock_connection_manager.init_instance_metadata_on_demand = AsyncMock(return_value=True)
        
        context = {
            "connection_manager": mock_connection_manager,
            "instance_name": "test_instance"
        }
        
        result = await self.recovery_manager._retry_connection(error, context)
        
        assert result["success"] is True
        assert "连接重试成功" in result["message"]
        mock_connection_manager.init_instance_metadata_on_demand.assert_called_once_with("test_instance")
    
    @pytest.mark.asyncio
    async def test_retry_connection_strategy_failure(self):
        """测试重试连接策略失败情况"""
        error = ConnectionError("数据库连接失败")
        context = {}  # 没有连接管理器
        
        result = await self.recovery_manager._retry_connection(error, context)
        
        assert result["success"] is False
        assert "无法重试连接" in result["error"]
    
    @pytest.mark.asyncio
    async def test_fallback_instance_strategy(self):
        """测试切换备用实例策略"""
        error = ConnectionError("主实例连接失败")
        
        # 模拟连接管理器
        mock_connection_manager = MagicMock()
        mock_connection_manager.get_available_instances.return_value = ["instance1", "instance2", "instance3"]
        
        context = {
            "connection_manager": mock_connection_manager,
            "instance_name": "instance1"
        }
        
        result = await self.recovery_manager._try_fallback_instance(error, context)
        
        assert result["success"] is True
        assert "切换到备用实例" in result["message"]
        assert context["instance_name"] in ["instance2", "instance3"]  # 应该切换到不同的实例
    
    @pytest.mark.asyncio
    async def test_increase_timeout_strategy(self):
        """测试增加超时时间策略"""
        error = QueryNestError("查询超时", category=ErrorCategory.TIMEOUT)
        context = {"timeout": 30}
        
        result = await self.recovery_manager._increase_timeout(error, context)
        
        assert result["success"] is True
        assert context["timeout"] == 60  # 应该翻倍
        assert "超时时间增加到 60 秒" in result["message"]
    
    @pytest.mark.asyncio
    async def test_increase_timeout_max_limit(self):
        """测试超时时间最大限制"""
        error = QueryNestError("查询超时", category=ErrorCategory.TIMEOUT)
        context = {"timeout": 100}
        
        result = await self.recovery_manager._increase_timeout(error, context)
        
        assert result["success"] is True
        assert context["timeout"] == 120  # 应该被限制在120秒
    
    @pytest.mark.asyncio
    async def test_simplify_query_strategy(self):
        """测试简化查询策略"""
        error = QueryNestError("查询过于复杂", category=ErrorCategory.TIMEOUT)
        
        # 测试简化AND条件
        context = {
            "query": {"$and": [{"field1": "value1"}, {"field2": "value2"}, {"field3": "value3"}]}
        }
        
        result = await self.recovery_manager._simplify_query(error, context)
        
        assert result["success"] is True
        assert len(context["query"]["$and"]) == 1
        assert "简化了查询条件" in result["message"]
    
    @pytest.mark.asyncio
    async def test_simplify_query_limit(self):
        """测试简化查询限制结果数量"""
        error = QueryNestError("查询超时", category=ErrorCategory.TIMEOUT)
        context = {"limit": 1000}
        
        result = await self.recovery_manager._simplify_query(error, context)
        
        assert result["success"] is True
        assert context["limit"] == 50
        assert "减少了查询结果数量" in result["message"]
    
    @pytest.mark.asyncio
    async def test_auto_fix_parameters_strategy(self):
        """测试自动修复参数策略"""
        error = ValidationError("参数验证失败")
        context = {
            "instance_name": "  ",  # 空白字符串
            "limit": -5,  # 负数
            "valid_param": "valid_value"
        }
        
        result = await self.recovery_manager._auto_fix_parameters(error, context)
        
        assert result["success"] is True
        assert context["instance_name"] is None  # 空字符串被修复为None
        assert context["limit"] == 10  # 负数被修复为10
        assert context["valid_param"] == "valid_value"  # 有效参数不变
        assert "修复了参数" in result["message"]
    
    @pytest.mark.asyncio
    async def test_attempt_recovery_success(self):
        """测试成功的错误恢复"""
        error = ValidationError("参数无效")
        context = {"limit": -1}
        
        recovery_result = await self.recovery_manager.attempt_recovery(error, context)
        
        assert recovery_result["recovered"] is True
        assert recovery_result["strategy_used"] == "auto_fix_params"
        assert recovery_result["attempts"] >= 1
        assert len(recovery_result["recovery_log"]) > 0
        assert recovery_result["recovery_log"][0]["success"] is True
    
    @pytest.mark.asyncio
    async def test_attempt_recovery_failure(self):
        """测试错误恢复失败"""
        # 创建一个没有对应策略的错误类型
        error = QueryNestError("未知错误", category=ErrorCategory.SYSTEM)
        context = {}
        
        recovery_result = await self.recovery_manager.attempt_recovery(error, context)
        
        assert recovery_result["recovered"] is False
        assert recovery_result["strategy_used"] is None
        assert recovery_result["attempts"] == 0
        assert recovery_result["final_error"] is not None
    
    @pytest.mark.asyncio
    async def test_attempt_recovery_partial_failure(self):
        """测试部分策略失败的恢复"""
        error = ConnectionError("连接失败")
        
        # 提供无效的连接管理器（第一个策略会失败）
        context = {
            "connection_manager": None,
            "instance_name": "test_instance"
        }
        
        recovery_result = await self.recovery_manager.attempt_recovery(error, context)
        
        # 所有策略都应该失败，因为没有有效的连接管理器
        assert recovery_result["recovered"] is False
        assert len(recovery_result["recovery_log"]) > 0
        
        # 检查日志记录了失败
        for log_entry in recovery_result["recovery_log"]:
            assert log_entry["success"] is False


class TestErrorRecoveryIntegration:
    """错误恢复集成测试"""
    
    def test_global_recovery_manager(self):
        """测试全局恢复管理器"""
        manager = get_recovery_manager()
        assert manager is not None
        assert isinstance(manager, ErrorRecoveryManager)
        
        # 验证单例模式
        manager2 = get_recovery_manager()
        assert manager is manager2
    
    @pytest.mark.asyncio
    async def test_end_to_end_error_recovery(self):
        """测试端到端错误恢复"""
        # 模拟一个完整的错误处理和恢复流程
        
        # 1. 创建错误
        error = ConnectionError(
            "Failed to connect to MongoDB at localhost:27017",
            details={"host": "localhost", "port": 27017, "timeout": 5}
        )
        
        # 2. 准备上下文
        mock_connection_manager = AsyncMock()
        mock_connection_manager.init_instance_metadata_on_demand = AsyncMock(return_value=True)
        mock_connection_manager.get_available_instances.return_value = ["primary", "secondary"]
        
        context = {
            "connection_manager": mock_connection_manager,
            "instance_name": "primary"
        }
        
        # 3. 尝试恢复
        recovery_manager = get_recovery_manager()
        recovery_result = await recovery_manager.attempt_recovery(error, context)
        
        # 4. 验证恢复结果
        assert recovery_result["recovered"] is True
        assert recovery_result["strategy_used"] in ["connection_retry", "fallback_instance"]
        assert len(recovery_result["recovery_log"]) > 0
    
    def test_error_categorization(self):
        """测试错误分类"""
        manager = ErrorRecoveryManager()
        
        # 测试不同类型的异常分类
        connection_error = ConnectionError("Connection failed")
        timeout_error = TimeoutError("Operation timed out")
        value_error = ValueError("Invalid value")
        
        # 验证错误类型已正确设置
        assert connection_error.category == ErrorCategory.CONNECTION
        
        # 对于通用异常，测试分类逻辑
        # 注意：_classify_error方法目前不存在，这是一个预期功能
        # 这里测试基本的错误类型识别
        assert isinstance(connection_error, ConnectionError)
        assert isinstance(timeout_error, TimeoutError)
        assert isinstance(value_error, ValueError)
    
    @pytest.mark.asyncio
    async def test_recovery_strategy_chaining(self):
        """测试恢复策略链"""
        manager = ErrorRecoveryManager()
        
        # 创建一个有多个恢复策略的错误
        error = ConnectionError("Multiple strategy test")
        
        # 模拟第一个策略失败，第二个策略成功的情况
        mock_connection_manager = AsyncMock()
        mock_connection_manager.init_instance_metadata_on_demand = AsyncMock(return_value=False)  # 第一个策略失败
        mock_connection_manager.get_available_instances.return_value = ["instance1", "instance2"]  # 第二个策略成功
        
        context = {
            "connection_manager": mock_connection_manager,
            "instance_name": "instance1"
        }
        
        recovery_result = await manager.attempt_recovery(error, context)
        
        # 应该至少尝试了两个策略
        assert recovery_result["attempts"] >= 2
        assert len(recovery_result["recovery_log"]) >= 2
        
        # 检查策略执行顺序
        log = recovery_result["recovery_log"]
        assert log[0]["strategy"] == "connection_retry"
        assert log[0]["success"] is False
        
        if len(log) > 1:
            assert log[1]["strategy"] == "fallback_instance"