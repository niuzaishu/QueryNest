#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
参数处理优化工具
统一处理所有MCP工具的参数验证、转换和优化
"""

import re
from typing import Dict, Any, List, Optional, Tuple, Union
from datetime import datetime
import structlog
from dataclasses import dataclass
from enum import Enum

logger = structlog.get_logger(__name__)

class ParameterType(Enum):
    """参数类型枚举"""
    STRING = "string"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    FLOAT = "float"
    LIST = "list"
    DICT = "dict"
    OBJECT_ID = "object_id"
    CONNECTION_STRING = "connection_string"

@dataclass
class ParameterRule:
    """参数规则定义"""
    name: str
    param_type: ParameterType
    required: bool = False
    default_value: Any = None
    validator: Optional[callable] = None
    transformer: Optional[callable] = None
    aliases: List[str] = None
    description: str = ""
    
    def __post_init__(self):
        if self.aliases is None:
            self.aliases = []

class ParameterProcessor:
    """参数处理器"""
    
    def __init__(self):
        self.rules: Dict[str, ParameterRule] = {}
        self._setup_common_rules()
    
    def _setup_common_rules(self):
        """设置通用参数规则"""
        # 实例ID规则
        self.add_rule(ParameterRule(
            name="instance_id",
            param_type=ParameterType.STRING,
            required=True,
            aliases=["instance", "inst_id"],
            validator=self._validate_instance_id,
            transformer=self._transform_instance_id,
            description="MongoDB实例标识符"
        ))
        
        # 数据库名称规则
        self.add_rule(ParameterRule(
            name="database_name",
            param_type=ParameterType.STRING,
            required=False,
            aliases=["database", "db", "db_name"],
            validator=self._validate_database_name,
            transformer=self._transform_database_name,
            description="数据库名称"
        ))
        
        # 集合名称规则
        self.add_rule(ParameterRule(
            name="collection_name",
            param_type=ParameterType.STRING,
            required=False,
            aliases=["collection", "col", "col_name"],
            validator=self._validate_collection_name,
            transformer=self._transform_collection_name,
            description="集合名称"
        ))
        
        # 限制数量规则
        self.add_rule(ParameterRule(
            name="limit",
            param_type=ParameterType.INTEGER,
            required=False,
            default_value=10,
            validator=self._validate_positive_integer,
            transformer=self._transform_integer,
            description="返回结果数量限制"
        ))
        
        # 跳过数量规则
        self.add_rule(ParameterRule(
            name="skip",
            param_type=ParameterType.INTEGER,
            required=False,
            default_value=0,
            validator=self._validate_non_negative_integer,
            transformer=self._transform_integer,
            description="跳过的结果数量"
        ))
        
        # 超时时间规则
        self.add_rule(ParameterRule(
            name="timeout",
            param_type=ParameterType.INTEGER,
            required=False,
            default_value=30,
            validator=self._validate_positive_integer,
            transformer=self._transform_integer,
            description="操作超时时间（秒）"
        ))
        
        # 布尔类型规则
        for bool_param in ["include_system_dbs", "detailed", "force", "confirm"]:
            self.add_rule(ParameterRule(
                name=bool_param,
                param_type=ParameterType.BOOLEAN,
                required=False,
                default_value=False,
                transformer=self._transform_boolean,
                description=f"布尔参数: {bool_param}"
            ))
    
    def add_rule(self, rule: ParameterRule):
        """添加参数规则"""
        self.rules[rule.name] = rule
        
        # 为别名创建映射
        for alias in rule.aliases:
            if alias not in self.rules:
                alias_rule = ParameterRule(
                    name=alias,
                    param_type=rule.param_type,
                    required=rule.required,
                    default_value=rule.default_value,
                    validator=rule.validator,
                    transformer=rule.transformer,
                    description=f"别名: {rule.name}"
                )
                self.rules[alias] = alias_rule
    
    def process_parameters(self, parameters: Dict[str, Any], 
                         tool_specific_rules: Dict[str, ParameterRule] = None) -> Tuple[Dict[str, Any], List[str]]:
        """处理参数"""
        processed = {}
        errors = []
        
        # 合并工具特定规则
        all_rules = self.rules.copy()
        if tool_specific_rules:
            all_rules.update(tool_specific_rules)
        
        # 标准化参数名称
        normalized_params = self._normalize_parameter_names(parameters, all_rules)
        
        # 处理每个参数
        for param_name, rule in all_rules.items():
            try:
                value = normalized_params.get(param_name)
                
                # 处理必需参数
                if rule.required and (value is None or value == ""):
                    errors.append(f"缺少必需参数: {param_name}")
                    continue
                
                # 使用默认值
                if value is None and rule.default_value is not None:
                    value = rule.default_value
                
                # 跳过None值
                if value is None:
                    continue
                
                # 转换参数
                if rule.transformer:
                    try:
                        value = rule.transformer(value)
                    except Exception as e:
                        errors.append(f"参数 {param_name} 转换失败: {str(e)}")
                        continue
                
                # 验证参数
                if rule.validator:
                    try:
                        if not rule.validator(value):
                            errors.append(f"参数 {param_name} 验证失败")
                            continue
                    except Exception as e:
                        errors.append(f"参数 {param_name} 验证异常: {str(e)}")
                        continue
                
                processed[param_name] = value
                
            except Exception as e:
                errors.append(f"处理参数 {param_name} 时发生错误: {str(e)}")
        
        return processed, errors
    
    def _normalize_parameter_names(self, parameters: Dict[str, Any], 
                                 rules: Dict[str, ParameterRule]) -> Dict[str, Any]:
        """标准化参数名称"""
        normalized = {}
        
        # 创建别名映射
        alias_map = {}
        for rule_name, rule in rules.items():
            for alias in rule.aliases:
                alias_map[alias] = rule_name
        
        for key, value in parameters.items():
            # 使用别名映射或原始名称
            normalized_key = alias_map.get(key, key)
            normalized[normalized_key] = value
        
        return normalized
    
    def optimize_parameter_order(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """优化参数顺序"""
        # 定义参数优先级
        priority_order = [
            "instance_id",
            "database_name",
            "collection_name",
            "operation",
            "query_type",
            "query",
            "filter",
            "projection",
            "sort",
            "limit",
            "skip",
            "timeout"
        ]
        
        ordered = {}
        
        # 按优先级添加参数
        for param in priority_order:
            if param in parameters:
                ordered[param] = parameters[param]
        
        # 添加其他参数
        for key, value in parameters.items():
            if key not in ordered:
                ordered[key] = value
        
        return ordered
    
    # 验证器方法
    def _validate_instance_id(self, value: Any) -> bool:
        """验证实例ID"""
        if not isinstance(value, str):
            return False
        return len(value.strip()) > 0
    
    def _validate_database_name(self, value: Any) -> bool:
        """验证数据库名称"""
        if not isinstance(value, str):
            return False
        # MongoDB数据库名称规则
        invalid_chars = ['/', '\\', '.', '"', '*', '<', '>', ':', '|', '?']
        return len(value.strip()) > 0 and not any(char in value for char in invalid_chars)
    
    def _validate_collection_name(self, value: Any) -> bool:
        """验证集合名称"""
        if not isinstance(value, str):
            return False
        # MongoDB集合名称规则
        return len(value.strip()) > 0 and not value.startswith('system.')
    
    def _validate_positive_integer(self, value: Any) -> bool:
        """验证正整数"""
        try:
            return isinstance(value, int) and value > 0
        except:
            return False
    
    def _validate_non_negative_integer(self, value: Any) -> bool:
        """验证非负整数"""
        try:
            return isinstance(value, int) and value >= 0
        except:
            return False
    
    # 转换器方法
    def _transform_instance_id(self, value: Any) -> str:
        """转换实例ID"""
        return str(value).strip()
    
    def _transform_database_name(self, value: Any) -> str:
        """转换数据库名称"""
        return str(value).strip()
    
    def _transform_collection_name(self, value: Any) -> str:
        """转换集合名称"""
        return str(value).strip()
    
    def _transform_integer(self, value: Any) -> int:
        """转换整数"""
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            return int(value)
        if isinstance(value, float):
            return int(value)
        raise ValueError(f"无法转换为整数: {value}")
    
    def _transform_boolean(self, value: Any) -> bool:
        """转换布尔值"""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ['true', '1', 'yes', 'on', 'enabled']
        if isinstance(value, int):
            return value != 0
        return bool(value)
    
    def get_parameter_info(self, param_name: str) -> Optional[ParameterRule]:
        """获取参数信息"""
        return self.rules.get(param_name)
    
    def get_required_parameters(self, tool_name: str = None) -> List[str]:
        """获取必需参数列表"""
        required = []
        for name, rule in self.rules.items():
            if rule.required and name not in [alias for r in self.rules.values() for alias in r.aliases]:
                required.append(name)
        return required
    
    def validate_parameter_completeness(self, parameters: Dict[str, Any], 
                                      required_params: List[str] = None) -> Tuple[bool, List[str]]:
        """验证参数完整性"""
        if required_params is None:
            required_params = self.get_required_parameters()
        
        missing = []
        for param in required_params:
            if param not in parameters or parameters[param] is None or parameters[param] == "":
                missing.append(param)
        
        return len(missing) == 0, missing

# 全局参数处理器实例
parameter_processor = ParameterProcessor()