# QueryNest MCP 参数优化指南

本文档介绍了 QueryNest MCP 服务器中实施的参数优化和用户体验改进。

## 优化概述

### 主要改进点

1. **统一参数验证框架** (`utils/parameter_validator.py`)
2. **智能上下文管理** (`utils/tool_context.py`) 
3. **用户友好的错误提示和参数选择**
4. **参数智能推断和补全**
5. **工具链上下文记忆**

## 核心组件

### 1. 参数验证器 (ParameterValidator)

#### 功能特性
- ✅ **类型检查**: 验证参数类型是否正确
- ✅ **业务逻辑验证**: 检查参数值是否符合业务规则
- ✅ **选项提供**: 当参数缺失时，提供可用选项列表
- ✅ **用户友好提示**: 生成清晰的错误信息和选择界面
- ✅ **异步验证**: 支持需要数据库查询的验证逻辑

#### 使用示例

```python
from utils.parameter_validator import ParameterValidator, is_string

# 创建验证器
validator = ParameterValidator()

# 添加必需参数
validator.add_required_parameter(
    name="instance_id",
    type_check=is_valid_instance_id,
    validator=lambda x, ctx: validate_instance_exists(x, ctx.connection_manager),
    options_provider=get_instance_options,
    description="MongoDB实例标识符",
    user_friendly_name="MongoDB实例"
)

# 验证参数
result, errors = await validator.validate_parameters(arguments, context)
```

#### 验证结果类型
- `VALID`: 所有参数验证通过
- `MISSING_REQUIRED`: 缺少必需参数
- `INVALID_VALUE`: 参数值无效
- `NEEDS_USER_SELECTION`: 需要用户选择参数值
- `NEEDS_CONFIRMATION`: 需要用户确认

### 2. 工具执行上下文 (ToolExecutionContext)

#### 功能特性
- ✅ **状态保持**: 在工具调用之间保持状态
- ✅ **参数推断**: 从历史调用中推断缺失参数
- ✅ **调用链记录**: 记录工具调用历史
- ✅ **智能建议**: 基于上下文提供下一步操作建议

#### 上下文管理

```python
from utils.tool_context import get_context_manager

# 获取上下文管理器
context_manager = get_context_manager()

# 获取或创建上下文
context = context_manager.get_or_create_context()

# 更新上下文
context_manager.update_context(
    instance_id="prod-mongodb",
    database_name="users_db"
)

# 推断缺失参数
inferred_params = context.infer_missing_parameters()
```

## 用户体验改进

### 1. 智能参数提示

当用户调用工具但缺少必需参数时，系统会：

**之前的体验**:
```
错误：缺少参数 'instance_id'
```

**优化后的体验**:
```
## 参数选择

请选择 MongoDB实例:

1. **prod-mongodb** - 生产环境 - 主要业务数据库
   状态: active

2. **test-mongodb** - 测试环境 - 开发测试数据库  
   状态: active

3. **staging-mongodb** - 预发布环境 - 预发布测试数据库
   状态: active

请回复实例名称或编号来选择 MongoDB实例。
```

### 2. 上下文感知的参数推断

工具能够记住之前的调用，并自动推断相关参数：

```python
# 用户先调用实例发现
discover_instances({})

# 然后调用数据库发现，如果没提供 instance_id
discover_databases({})  
# 系统会提示："从上下文推断instance_id: prod-mongodb"

# 继续调用查询生成
generate_query({"query_description": "查找所有用户"})
# 系统自动推断: instance_id, database_name 等参数
```

### 3. 分层错误提示

根据错误类型提供不同层次的帮助信息：

#### 参数选择错误
提供具体的选项列表和选择界面

#### 参数验证错误  
提供详细的错误原因和修正建议

#### 缺失参数错误
提供参数说明和使用提示

## 已优化的工具

### 1. InstanceDiscoveryTool (实例发现)

**参数验证**:
- `include_health`: 布尔值类型检查
- `include_stats`: 布尔值类型检查

**用户体验**:
- 参数类型错误时提供友好提示
- 所有参数都是可选的，提供合理默认值

### 2. DatabaseDiscoveryTool (数据库发现)

**参数验证**:
- `instance_id`: 必需参数，提供实例选择界面
- `include_collections`: 布尔值验证  
- `include_stats`: 布尔值验证
- `filter_system`: 布尔值验证

**智能功能**:
- 从上下文自动推断 `instance_id`
- 实时验证实例是否存在和健康
- 提供所有可用实例的选择界面

### 3. QueryGenerationTool (查询生成)

**参数验证**:
- `instance_id`: 实例存在性验证 + 选择界面
- `database_name`: 数据库存在性验证 + 选择界面  
- `collection_name`: 集合存在性验证 + 选择界面
- `query_description`: 非空字符串验证
- `query_type`: 枚举值验证
- `limit`: 正整数范围验证

**智能功能**:
- 三级参数推断 (实例 → 数据库 → 集合)
- 动态选项获取 (数据库列表基于选择的实例)
- 上下文感知的参数补全

## 技术实现细节

### 1. 异步验证支持

```python
async def validate_instance_exists(instance_id: str, connection_manager) -> Union[bool, str]:
    """异步验证实例是否存在"""
    try:
        if not connection_manager.has_instance(instance_id):
            available = list(connection_manager.get_all_instances().keys())
            return f"实例不存在。可用实例: {', '.join(available)}"
        return True
    except Exception as e:
        return f"验证失败: {str(e)}"
```

### 2. 动态选项提供

```python
async def get_database_options(context):
    """动态获取数据库选项"""
    if not context.instance_id:
        return []
    
    connection = connection_manager.get_instance_connection(context.instance_id)
    db_names = await connection.client.list_database_names()
    
    return [{'value': name, 'display_name': name, 'description': f'数据库: {name}'} 
            for name in db_names if name not in {'admin', 'local', 'config'}]
```

### 3. 上下文链式推断

```python
def infer_missing_parameters(self) -> Dict[str, Any]:
    """从工具调用链推断参数"""
    inferred = {}
    
    # 从最近的调用向前推断
    for call in reversed(self.tool_chain):
        arguments = call.get('arguments', {})
        
        if not inferred.get('instance_id') and arguments.get('instance_id'):
            inferred['instance_id'] = arguments['instance_id']
        
        if not inferred.get('database_name') and arguments.get('database_name'):
            inferred['database_name'] = arguments['database_name']
    
    return inferred
```

## 使用指南

### 1. 为新工具添加参数验证

```python
def _setup_validator(self) -> ParameterValidator:
    """为新工具设置验证器"""
    validator = ParameterValidator()
    
    # 必需参数
    validator.add_required_parameter(
        name="param_name",
        type_check=validation_function,
        validator=business_logic_validator,
        options_provider=option_provider_function,
        description="参数描述",
        user_friendly_name="用户友好名称"
    )
    
    # 可选参数
    validator.add_optional_parameter(
        name="optional_param",
        type_check=type_validator,
        default_provider=default_value_provider,
        description="可选参数描述"
    )
    
    return validator
```

### 2. 在工具执行中使用验证器

```python
async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
    """工具执行方法"""
    # 获取上下文
    context = self.context_manager.get_or_create_context()
    context.connection_manager = self.connection_manager
    
    # 参数推断
    inferred = context.infer_missing_parameters()
    for param in ['instance_id', 'database_name']:
        if not arguments.get(param) and inferred.get(param):
            arguments[param] = inferred[param]
    
    # 参数验证
    result, errors = await self.validator.validate_parameters(arguments, context)
    if result != ValidationResult.VALID:
        return MCPParameterHelper.create_error_response(errors)
    
    # 记录调用并更新上下文
    context.add_to_chain(tool_name, arguments)
    self.context_manager.update_context(**relevant_params)
    
    # 执行工具逻辑...
```

## 测试和验证

运行参数优化测试：

```bash
cd C:\my\QueryNest
"C:\Users\zaishu.niu\AppData\Local\Programs\Python\Python312\python.exe" test_parameter_optimization.py
```

测试覆盖：
- ✅ 参数类型验证
- ✅ 业务逻辑验证  
- ✅ 缺失参数处理
- ✅ 选项提供功能
- ✅ 上下文推断
- ✅ 错误消息格式

## 扩展建议

### 1. 添加参数历史记录
- 记录用户常用的参数组合
- 提供基于历史的智能建议

### 2. 参数模板支持
- 允许用户保存常用参数组合
- 支持参数模板的导入导出

### 3. 多语言支持
- 支持英文错误提示
- 国际化参数描述

### 4. 高级验证规则
- 支持复杂的跨参数验证
- 添加正则表达式验证支持

## 总结

通过实施统一的参数验证框架和智能上下文管理，QueryNest MCP 服务器显著提升了用户体验：

1. **减少用户错误**: 通过类型检查和业务逻辑验证
2. **提高操作效率**: 通过参数推断和上下文记忆
3. **改善可用性**: 通过友好的错误提示和选择界面
4. **增强一致性**: 通过统一的验证和错误处理框架

这些改进使得用户在使用 MCP 工具时能够获得更加流畅和直观的体验，同时减少了因参数错误导致的工具调用失败。