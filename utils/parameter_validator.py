# -*- coding: utf-8 -*-
"""参数验证和用户提示工具"""

from typing import Dict, List, Any, Optional, Union, Callable, Tuple
from dataclasses import dataclass
from enum import Enum
import re
import structlog
from mcp.types import TextContent

logger = structlog.get_logger(__name__)


class ValidationResult(Enum):
    """验证结果枚举"""
    VALID = "valid"
    MISSING_REQUIRED = "missing_required"
    INVALID_VALUE = "invalid_value"
    NEEDS_USER_SELECTION = "needs_user_selection"
    NEEDS_CONFIRMATION = "needs_confirmation"


@dataclass
class ValidationError:
    """验证错误信息"""
    parameter: str
    error_type: ValidationResult
    message: str
    suggestions: List[str] = None
    available_options: List[Dict[str, Any]] = None
    user_prompt: str = None


@dataclass
class ParameterRule:
    """参数验证规则"""
    name: str
    required: bool = False
    type_check: Callable = None
    validator: Callable = None
    default_provider: Callable = None
    options_provider: Callable = None
    description: str = ""
    user_friendly_name: str = ""


class ParameterValidator:
    """参数验证器"""
    
    def __init__(self):
        self.rules: Dict[str, ParameterRule] = {}
        
    def add_rule(self, rule: ParameterRule):
        """添加验证规则"""
        self.rules[rule.name] = rule
        
    def add_required_parameter(self, name: str, type_check: Callable = None, 
                             validator: Callable = None, options_provider: Callable = None,
                             description: str = "", user_friendly_name: str = ""):
        """添加必需参数规则"""
        rule = ParameterRule(
            name=name,
            required=True,
            type_check=type_check,
            validator=validator,
            options_provider=options_provider,
            description=description,
            user_friendly_name=user_friendly_name or name
        )
        self.add_rule(rule)
        
    def add_optional_parameter(self, name: str, type_check: Callable = None,
                              validator: Callable = None, default_provider: Callable = None,
                              description: str = "", user_friendly_name: str = ""):
        """添加可选参数规则"""
        rule = ParameterRule(
            name=name,
            required=False,
            type_check=type_check,
            validator=validator,
            default_provider=default_provider,
            description=description,
            user_friendly_name=user_friendly_name or name
        )
        self.add_rule(rule)
        
    async def validate_parameters(self, arguments: Dict[str, Any], 
                                context: Any = None) -> Tuple[ValidationResult, List[ValidationError]]:
        """验证参数"""
        errors = []
        
        for rule_name, rule in self.rules.items():
            error = await self._validate_single_parameter(arguments, rule, context)
            if error:
                errors.append(error)
        
        if not errors:
            return ValidationResult.VALID, []
        
        # 确定总体验证结果
        if any(error.error_type == ValidationResult.NEEDS_USER_SELECTION for error in errors):
            return ValidationResult.NEEDS_USER_SELECTION, errors
        elif any(error.error_type == ValidationResult.MISSING_REQUIRED for error in errors):
            return ValidationResult.MISSING_REQUIRED, errors
        elif any(error.error_type == ValidationResult.NEEDS_CONFIRMATION for error in errors):
            return ValidationResult.NEEDS_CONFIRMATION, errors
        else:
            return ValidationResult.INVALID_VALUE, errors
    
    async def _validate_single_parameter(self, arguments: Dict[str, Any], 
                                       rule: ParameterRule, context: Any) -> Optional[ValidationError]:
        """验证单个参数"""
        param_name = rule.name
        param_value = arguments.get(param_name)
        
        # 检查必需参数是否缺失
        if rule.required and param_value is None:
            # 尝试提供选项
            options = None
            user_prompt = None
            
            if rule.options_provider:
                try:
                    options = await rule.options_provider(context) if context else await rule.options_provider()
                    if options:
                        user_prompt = self._generate_selection_prompt(rule, options)
                        return ValidationError(
                            parameter=param_name,
                            error_type=ValidationResult.NEEDS_USER_SELECTION,
                            message=f"参数 '{rule.user_friendly_name}' 是必需的，请选择一个选项",
                            available_options=options,
                            user_prompt=user_prompt
                        )
                except Exception as e:
                    logger.warning("获取参数选项失败", parameter=param_name, error=str(e))
            
            return ValidationError(
                parameter=param_name,
                error_type=ValidationResult.MISSING_REQUIRED,
                message=f"缺少必需参数: {rule.user_friendly_name}",
                user_prompt=f"请提供 {rule.user_friendly_name}。{rule.description}"
            )
        
        # 如果参数存在，进行类型检查
        if param_value is not None and rule.type_check:
            try:
                if not rule.type_check(param_value):
                    return ValidationError(
                        parameter=param_name,
                        error_type=ValidationResult.INVALID_VALUE,
                        message=f"参数 '{rule.user_friendly_name}' 类型不正确"
                    )
            except Exception as e:
                return ValidationError(
                    parameter=param_name,
                    error_type=ValidationResult.INVALID_VALUE,
                    message=f"参数 '{rule.user_friendly_name}' 类型检查失败: {str(e)}"
                )
        
        # 进行业务逻辑验证
        if param_value is not None and rule.validator:
            try:
                validation_result = await rule.validator(param_value, context) if context else await rule.validator(param_value)
                if validation_result is not True:
                    if isinstance(validation_result, str):
                        message = validation_result
                    else:
                        message = f"参数 '{rule.user_friendly_name}' 验证失败"
                    
                    return ValidationError(
                        parameter=param_name,
                        error_type=ValidationResult.INVALID_VALUE,
                        message=message
                    )
            except Exception as e:
                return ValidationError(
                    parameter=param_name,
                    error_type=ValidationResult.INVALID_VALUE,
                    message=f"参数 '{rule.user_friendly_name}' 验证失败: {str(e)}"
                )
        
        return None
    
    def _generate_selection_prompt(self, rule: ParameterRule, options: List[Dict[str, Any]]) -> str:
        """生成选择提示"""
        if not options:
            return f"请提供 {rule.user_friendly_name}"
        
        if len(options) == 1:
            option = options[0]
            return f"将使用 {rule.user_friendly_name}: {option.get('display_name', option.get('value', ''))}"
        
        prompt = f"请选择 {rule.user_friendly_name}:\n\n"
        
        for i, option in enumerate(options, 1):
            display_name = option.get('display_name', option.get('value', f'选项{i}'))
            description = option.get('description', '')
            
            prompt += f"{i}. **{display_name}**"
            if description:
                prompt += f" - {description}"
            prompt += "\n"
        
        prompt += f"\n请回复选项编号或名称来选择 {rule.user_friendly_name}。"
        return prompt
    
    def generate_help_message(self) -> str:
        """生成帮助信息"""
        help_text = "## 参数说明\n\n"
        
        required_params = [rule for rule in self.rules.values() if rule.required]
        optional_params = [rule for rule in self.rules.values() if not rule.required]
        
        if required_params:
            help_text += "### 必需参数\n\n"
            for rule in required_params:
                help_text += f"- **{rule.user_friendly_name}**: {rule.description}\n"
            help_text += "\n"
        
        if optional_params:
            help_text += "### 可选参数\n\n"
            for rule in optional_params:
                help_text += f"- **{rule.user_friendly_name}**: {rule.description}\n"
            help_text += "\n"
        
        return help_text


class MCPParameterHelper:
    """MCP参数帮助器"""
    
    @staticmethod
    def create_error_response(errors: List[ValidationError]) -> List[TextContent]:
        """创建参数验证错误响应"""
        if not errors:
            return [TextContent(type="text", text="参数验证通过")]
        
        # 优先处理需要用户选择的错误
        selection_errors = [e for e in errors if e.error_type == ValidationResult.NEEDS_USER_SELECTION]
        if selection_errors:
            return MCPParameterHelper._create_selection_response(selection_errors[0])
        
        # 处理缺失必需参数的错误
        missing_errors = [e for e in errors if e.error_type == ValidationResult.MISSING_REQUIRED]
        if missing_errors:
            return MCPParameterHelper._create_missing_parameter_response(missing_errors)
        
        # 处理其他验证错误
        return MCPParameterHelper._create_validation_error_response(errors)
    
    @staticmethod
    def _create_selection_response(error: ValidationError) -> List[TextContent]:
        """创建选择响应"""
        response_text = f"## 参数选择\n\n{error.user_prompt}\n\n"
        
        if error.available_options:
            response_text += "### 可用选项详情\n\n"
            for option in error.available_options:
                name = option.get('display_name', option.get('value', ''))
                desc = option.get('description', '')
                extra_info = option.get('extra_info', '')
                
                response_text += f"**{name}**\n"
                if desc:
                    response_text += f"- 描述: {desc}\n"
                if extra_info:
                    response_text += f"- 详情: {extra_info}\n"
                response_text += "\n"
        
        response_text += "请重新调用工具并提供所选的参数值。"
        
        return [TextContent(type="text", text=response_text)]
    
    @staticmethod
    def _create_missing_parameter_response(errors: List[ValidationError]) -> List[TextContent]:
        """创建缺失参数响应"""
        response_text = "## 缺少必需参数\n\n"
        response_text += "以下参数是必需的，请提供这些参数后重新调用工具:\n\n"
        
        for error in errors:
            response_text += f"- **{error.parameter}**: {error.message}\n"
            if error.user_prompt:
                response_text += f"  *{error.user_prompt}*\n"
        
        response_text += "\n### 使用提示\n\n"
        response_text += "1. 如果不确定参数值，可以使用相关的发现工具先查看可用选项\n"
        response_text += "2. 参数名称区分大小写，请确保拼写正确\n"
        response_text += "3. 如需帮助，请查看工具说明或使用帮助命令\n"
        
        return [TextContent(type="text", text=response_text)]
    
    @staticmethod
    def _create_validation_error_response(errors: List[ValidationError]) -> List[TextContent]:
        """创建验证错误响应"""
        response_text = "## 参数验证失败\n\n"
        response_text += "发现以下参数问题:\n\n"
        
        for error in errors:
            response_text += f"- **{error.parameter}**: {error.message}\n"
            if error.suggestions:
                response_text += f"  建议: {', '.join(error.suggestions)}\n"
        
        response_text += "\n请修正参数后重新调用工具。"
        
        return [TextContent(type="text", text=response_text)]


# 常用验证函数
def is_string(value: Any) -> bool:
    """检查是否为字符串"""
    return isinstance(value, str)


def is_non_empty_string(value: Any) -> bool:
    """检查是否为非空字符串"""
    return isinstance(value, str) and len(value.strip()) > 0


def is_positive_integer(value: Any) -> bool:
    """检查是否为正整数"""
    return isinstance(value, int) and value > 0


def is_boolean(value: Any) -> bool:
    """检查是否为布尔值"""
    return isinstance(value, bool)


def is_valid_instance_id(value: Any) -> bool:
    """检查是否为有效的实例ID格式"""
    if not isinstance(value, str):
        return False
    # 实例ID可以包含字母、数字、下划线、连字符和Unicode字符（包括中文）
    # 只要不是空字符串且不包含特殊控制字符即可
    return bool(value.strip() and not re.search(r'[\x00-\x1f\x7f-\x9f]', value))


def is_valid_database_name(value: Any) -> bool:
    """检查是否为有效的数据库名称"""
    if not isinstance(value, str):
        return False
    # MongoDB数据库名称规则
    return bool(re.match(r'^[a-zA-Z0-9_-]+$', value)) and len(value) <= 64


def is_valid_collection_name(value: Any) -> bool:
    """检查是否为有效的集合名称"""
    if not isinstance(value, str):
        return False
    # MongoDB集合名称规则
    return not value.startswith('$') and '\\' not in value and len(value) <= 127


# 异步验证函数示例
async def validate_instance_exists(instance_name: str, connection_manager) -> Union[bool, str]:
    """验证实例是否存在"""
    try:
        if not connection_manager.has_instance(instance_name):
            available_instances = list(connection_manager.get_all_instances().keys())
            if available_instances:
                return f"实例 '{instance_name}' 不存在。可用实例: {', '.join(available_instances)}"
            else:
                return "没有可用的MongoDB实例，请检查配置"
        return True
    except Exception as e:
        return f"验证实例时发生错误: {str(e)}"


async def validate_database_exists(database_name: str, context) -> Union[bool, str]:
    """验证数据库是否存在"""
    try:
        # 这里需要根据具体的context结构来实现
        # context应该包含instance_id和connection_manager
        instance_id = getattr(context, 'instance_id', None)
        connection_manager = getattr(context, 'connection_manager', None)
        
        if not instance_id or not connection_manager:
            return "缺少验证数据库所需的上下文信息"
        
        # 检查数据库是否存在
        connection = connection_manager.get_instance_connection(instance_id)
        if not connection:
            return f"无法连接到实例 '{instance_id}'"
        
        db_names = await connection.client.list_database_names()
        if database_name not in db_names:
            return f"数据库 '{database_name}' 不存在。可用数据库: {', '.join(db_names)}"
        
        return True
    except Exception as e:
        return f"验证数据库时发生错误: {str(e)}"


async def validate_collection_exists(collection_name: str, context) -> Union[bool, str]:
    """验证集合是否存在"""
    try:
        instance_id = getattr(context, 'instance_id', None)
        database_name = getattr(context, 'database_name', None)
        connection_manager = getattr(context, 'connection_manager', None)
        
        if not all([instance_id, database_name, connection_manager]):
            return "缺少验证集合所需的上下文信息"
        
        connection = connection_manager.get_instance_connection(instance_id)
        if not connection:
            return f"无法连接到实例 '{instance_id}'"
        
        db = connection.client[database_name]
        collection_names = await db.list_collection_names()
        
        if collection_name not in collection_names:
            return f"集合 '{collection_name}' 不存在。可用集合: {', '.join(collection_names)}"
        
        return True
    except Exception as e:
        return f"验证集合时发生错误: {str(e)}"