# CLAUDE.md

此文件为Claude Code (claude.ai/code) 在此代码库中工作时提供指导。

## 项目概述

QueryNest 是一个基于 MCP (Model Context Protocol) 的 MongoDB 多实例查询服务，提供智能数据库结构发现、语义分析和自然语言查询生成功能。它作为具有安全控制和智能查询辅助的只读 MongoDB 接口。

## 核心架构

### MCP 服务器结构
- **主入口**: `mcp_server.py` - MCP 服务器实现，包含工具注册
- **配置管理**: `config.py` 和 `config.yaml` - 集中配置管理
- **数据库层**: `database/` - 连接管理、元数据和查询引擎
- **扫描模块**: `scanner/` - 结构扫描、语义分析和数据库扫描
- **MCP 工具**: `mcp_tools/` - 单独的 MCP 工具实现
- **工具类**: `utils/` - 日志记录、验证和错误处理

### 关键组件

**连接管理器** (`database/connection_manager.py`):
- 多实例 MongoDB 连接池管理
- 健康检查和自动故障转移
- 只读连接强制执行

**元数据管理器** (`database/metadata_manager.py`):
- 在 `querynest_metadata` 数据库中存储发现的数据库结构
- 跟踪通过交互学习到的语义含义
- 查询历史和用户反馈

**查询引擎** (`database/query_engine.py`):
- 带有安全控制的安全查询执行
- 查询验证和优化
- 结果格式化和数据脱敏

**MCP 工具集** (`mcp_tools/`):
- `instance_discovery.py` - 发现 MongoDB 实例
- `database_discovery.py` - 列出数据库和集合
- `collection_analysis.py` - 分析集合结构
- `semantic_management.py` - 管理字段语义
- `semantic_completion.py` - 语义补全功能
- `query_generation.py` - 从自然语言生成 MongoDB 查询
- `query_confirmation.py` - 执行和确认查询
- `feedback_tools.py` - 用户反馈收集

## 常用命令

### 安装和运行服务
```bash
# 安装 uv 工具（使用 pip）
pip install uv

# 通过 uvx 运行 MCP 服务器（推荐）
# 方法1：从项目目录运行
uvx --from . querynest-mcp

# 方法2：使用绝对路径（如果工作目录问题）
uvx --from "完整项目路径" querynest-mcp

# 方法3：指定配置文件路径
uvx --from . querynest-mcp --config "config.yaml的完整路径"
```

### 配置文件查找策略
服务器会按以下顺序查找配置文件：
1. 命令行参数指定的路径
2. `QUERYNEST_CONFIG_PATH` 环境变量
3. 当前工作目录中的 `config.yaml`
4. 项目根目录中的 `config.yaml`
5. `QUERYNEST_CONFIG_DIR` 环境变量指定目录
6. 用户主目录的 `.querynest/config.yaml`

### 测试命令
```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行特定测试类别
python -m pytest -m unit tests/        # 单元测试
python -m pytest -m integration tests/ # 集成测试
python -m pytest -m mongodb tests/     # MongoDB 测试

# 带覆盖率报告
python -m pytest tests/ --cov=. --cov-report=html

# 集成测试
python run_integration_tests.py

# 特定测试文件
python test_integration.py
python test_service.py
python test_semantic_completion.py
```

### 代码质量检查
```bash
# 代码格式化
black .

# 代码检查
flake8 .

# 类型检查
mypy .
```

### 数据库连接检查
```bash
# 检查数据库连接
python check_db.py

# 测试 MongoDB 设置
python test_mongodb_setup.py
```


## 配置架构

### 主配置文件 (`config.yaml`)
- **MongoDB 实例** (`mongodb.instances`): 多环境连接字符串，强制只读访问
- **安全设置** (`security`): 查询限制、操作限制、数据脱敏配置
- **MCP 工具** (`mcp.tools`): 各个工具的启用状态和参数配置
- **性能配置** (`performance`): 连接池、缓存、扫描间隔设置
- **日志配置** (`logging`): 结构化日志记录，支持控制台和文件输出
- **元数据配置** (`metadata`): 元数据库名称和集合配置
- **监控配置** (`monitoring`): 指标收集和健康检查设置

### 环境变量
- `QUERYNEST_CONFIG_PATH` - 配置文件路径
- `QUERYNEST_LOG_LEVEL` - 日志级别（DEBUG、INFO、WARNING、ERROR）
- `QUERYNEST_MCP_TRANSPORT` - MCP 传输模式（目前仅支持 stdio）
- 实例连接字符串可通过环境变量覆盖 YAML 配置
- 所有配置项都支持 `QUERYNEST_` 前缀的环境变量覆盖

### 配置示例文件
- `config.example.yaml` - 配置模板
- 支持多种环境配置：dev、test、uat、sit、staging、prod
- 配置格式转换：YAML 中的 `mongodb.instances` 自动转换为代码中的 `mongo_instances`
- 支持环境变量覆盖所有配置项

## 安全模型

**只读操作限制**: 服务对所有业务数据库强制执行只读访问
- 允许的操作: `find`、`count`、`aggregate`、`distinct`
- 禁止的操作: `insert`、`update`、`delete`、`drop`、`create`
- 禁止的聚合阶段: `$out`、`$merge`、`$function`、`$accumulator`、`$where`
- 禁止的查询操作符: `$where`、`$function`、`$accumulator`
- 查询复杂度限制和超时控制
- 敏感字段自动数据脱敏

**元数据库访问**: 服务仅对 `querynest_metadata` 有读写权限，用于:
- 存储发现的数据库结构信息
- 缓存语义分析结果
- 记录查询历史和用户反馈

**数据脱敏配置**:
- 自动识别敏感字段模式：password、secret、token、key、phone、email、id_card、credit_card
- 支持部分遮蔽和完全遮蔽策略
- 可在 config.yaml 中自定义脱敏规则

## 开发模式和扩展

### 添加新的 MCP 工具
1. 在 `mcp_tools/` 中创建工具类，继承基础模式
2. 实现 `get_tool_definition()` 和 `execute()` 方法
3. 在 `mcp_server.py` 中注册工具
4. 在 `config.yaml` 中添加配置项

### 扩展语义分析功能
- 修改 `scanner/semantic_analyzer.py` 添加新的字段模式识别
- 在配置中更新语义规则
- 增强字段含义推理算法
- 支持中文分词和语义分析（使用 jieba 和 NLTK）

### 数据库扫描器扩展
- 扩展 `scanner/structure_scanner.py` 增加新的集合分析功能
- 添加元数据收集策略
- 实现增量扫描优化
- 支持大集合的采样分析

### 查询生成器增强
- 支持中文自然语言查询描述
- 支持复杂聚合管道生成
- 添加查询优化建议
- 集成查询性能分析

## 测试策略

### 测试结构
- `tests/integration/` - 端到端 MCP 工具测试
- 根目录测试文件：`test_integration.py`、`test_service.py`、`test_semantic_completion.py` 等
- `pytest.ini` - 测试配置，支持异步测试
- `run_integration_tests.py` - 集成测试运行器

### 集成测试要求
- MongoDB 实例必须运行
- 测试配置位于 `tests/integration/test_config.py`
- 模拟 MCP 客户端交互

### 测试标记
- `@pytest.mark.unit` - 单元测试
- `@pytest.mark.integration` - 集成测试
- `@pytest.mark.slow` - 慢速测试
- `@pytest.mark.mongodb` - 需要 MongoDB 的测试

### 特定测试文件
- `test_integration.py` - 主要集成测试
- `test_service.py` - 服务测试
- `test_semantic_completion.py` - 语义补全测试
- `test_mongodb_setup.py` - MongoDB 设置测试
- `run_integration_tests.py` - 集成测试运行器

## 核心依赖

- **MCP**: 核心模型上下文协议实现
- **PyMongo/Motor**: 同步和异步 MongoDB 驱动
- **Pydantic**: 配置验证和数据建模
- **StructLog**: 结构化日志记录，用于调试和监控
- **NLTK/scikit-learn**: 自然语言处理，用于语义分析

## 部署方式

### MCP 集成
- 使用 uvx 安装和执行
- stdio 传输协议用于 AI 工具集成
- 工具发现和能力通告
- 主入口点：`mcp_server.py` 中的 `cli_main()` 函数
- 开发调试：`start.py` 提供独立启动方式（需修复导入路径）

## 错误处理

`utils/error_handler.py` 中的集中式错误处理：
- MongoDB 连接失败的重试逻辑
- 查询验证和安全违规处理
- MCP 协议错误响应
- 用户友好的错误消息和故障排除指导

## 监控和可观测性

- 带上下文信息的结构化日志记录
- 查询性能跟踪
- 连接健康监控
- 可选的 Prometheus 指标导出

## 中文开发约定和规范

### 代码注释规范
- **所有代码注释必须使用中文**，包括类注释、方法注释、行内注释
- 使用标准的 Python docstring 格式，但内容为中文
- 重要的业务逻辑和算法必须有详细的中文注释说明
- 配置项和枚举值使用中文描述

```python
class ConnectionManager:
    """MongoDB 连接管理器
    
    负责管理多个 MongoDB 实例的连接池，提供健康检查、
    故障转移和只读访问控制功能。
    
    Attributes:
        connections (Dict): MongoDB 连接池字典
        health_status (Dict): 实例健康状态字典
    """
    
    def create_connection(self, instance_name: str) -> MongoClient:
        """创建 MongoDB 连接
        
        Args:
            instance_name: 实例名称，对应配置文件中的实例标识
            
        Returns:
            MongoClient: MongoDB 客户端连接
            
        Raises:
            ConnectionError: 连接失败时抛出异常
        """
        # 检查实例配置是否存在
        if instance_name not in self.config.instances:
            raise ValueError(f"未找到实例配置: {instance_name}")
```

### 变量和函数命名规范
- **类名**: 使用英文驼峰命名，但类注释必须使用中文
- **方法名**: 使用英文下划线命名，但方法注释必须使用中文
- **变量名**: 重要业务变量可使用拼音缩写，但须有中文注释
- **常量名**: 使用英文大写，配合中文注释说明含义

```python
# 正确示例
user_count = 0  # 用户数量
db_instance_list = []  # 数据库实例列表
MAX_QUERY_TIMEOUT = 30  # 查询超时时间（秒）

def get_collection_structure(collection_name: str):
    """获取集合结构信息"""
    pass

def analyze_field_semantics(field_data: dict):
    """分析字段语义含义"""
    pass
```

### 错误信息和日志规范
- **错误消息必须使用中文**，便于用户理解
- **日志输出使用中文描述**，方便运维人员排查问题
- **异常类型保持英文**，但异常消息使用中文

```python
# 正确示例
logger.info("开始连接 MongoDB 实例: %s", instance_name)
logger.error("连接数据库失败，实例: %s，错误: %s", instance_name, str(e))
raise ConnectionError(f"无法连接到 MongoDB 实例 {instance_name}: {str(e)}")
```

### 配置文件注释规范
- **YAML 配置文件中的注释使用中文**
- **环境变量说明使用中文**
- **配置示例包含中文说明**

### 文档和测试规范
- **README 文件使用中文编写**
- **API 文档使用中文描述**
- **测试用例的描述使用中文**
- **测试数据使用中文示例**

```python
def test_connection_manager_创建连接():
    """测试连接管理器创建数据库连接功能"""
    pass

def test_query_engine_查询验证():
    """测试查询引擎的安全验证功能"""
    pass
```

## 问题排查和常见问题

### MongoDB 连接问题
**问题**: 连接超时或拒绝连接
```bash
# 检查连接状态
python check_db.py

# 查看详细连接信息
python -c "from database.connection_manager import ConnectionManager; cm = ConnectionManager(); cm.test_all_connections()"
```

**解决方案**:
1. 检查 MongoDB 服务是否运行
2. 验证连接字符串和认证信息
3. 确认网络连通性和防火墙设置
4. 检查 MongoDB 用户权限配置

### MCP 工具注册失败
**问题**: MCP 工具无法正常注册或调用
```bash
# 检查 MCP 服务器状态
uvx --from . querynest-mcp --debug

# 测试特定工具
python -c "from mcp_tools.instance_discovery import InstanceDiscoveryTool; tool = InstanceDiscoveryTool(); print(tool.get_tool_definition())"
```

**解决方案**:
1. 确认配置文件格式正确
2. 检查工具类实现是否完整
3. 验证依赖包版本兼容性
4. 查看详细错误日志

### 查询性能问题
**问题**: 查询执行缓慢或超时
```bash
# 启用查询性能分析
export QUERYNEST_LOG_LEVEL=DEBUG
uvx --from . querynest-mcp

# 查看慢查询日志
grep "SLOW_QUERY" logs/querynest.log
```

**解决方案**:
1. 检查查询复杂度和数据量
2. 优化 MongoDB 索引
3. 调整查询超时设置
4. 使用采样查询替代全表扫描

### 语义分析异常
**问题**: 字段语义识别不准确
```bash
# 重新扫描数据库结构
python -c "from scanner.structure_scanner import StructureScanner; scanner = StructureScanner(); scanner.scan_all_instances()"

# 测试语义分析
python test_semantic_completion.py
```

**解决方案**:
1. 更新语义规则配置
2. 增加训练样本数据
3. 调整字段匹配模式
4. 手动标注重要字段语义

### 数据脱敏问题
**问题**: 敏感数据未正确脱敏
```python
# 检查脱敏配置
from utils.data_masking import DataMasker
masker = DataMasker()
print(masker.get_sensitive_patterns())

# 测试脱敏功能
test_data = {"password": "123456", "phone": "13800138000"}
masked_data = masker.mask_data(test_data)
print(masked_data)
```

**解决方案**:
1. 检查敏感字段匹配规则
2. 更新脱敏策略配置
3. 验证脱敏算法实现
4. 添加自定义敏感模式

### 内存和性能优化
**问题**: 服务占用内存过高
```bash
# 检查连接池配置
grep -A 10 "connection_pool" config.yaml

# 监控连接状态
python -c "from database.connection_manager import ConnectionManager; cm = ConnectionManager(); print(cm.get_health_status())"
```

**解决方案**:
1. 调整连接池大小设置
2. 启用结果集分页查询
3. 优化缓存策略配置
4. 定期清理过期元数据

### 日志和调试技巧
**启用详细日志**:
```bash
export QUERYNEST_LOG_LEVEL=DEBUG
export PYTHONPATH=$PWD
uvx --from . querynest-mcp 2>&1 | tee logs/debug.log
```

**常用调试命令**:
```bash
# 检查所有组件状态
python -c "
from database.connection_manager import ConnectionManager
from scanner.structure_scanner import StructureScanner
from utils.config_manager import ConfigManager

config = ConfigManager()
print('配置加载:', config.is_loaded())

cm = ConnectionManager()
print('连接状态:', cm.get_health_status())

scanner = StructureScanner()
print('扫描器状态:', scanner.get_scan_status())
"
```

### 运维建议
**性能优化建议**:
1. 合理配置连接池大小
2. 启用适当的缓存策略
3. 定期清理历史数据
4. 监控查询性能指标

**安全配置检查**:
1. 确认只读权限配置
2. 验证数据脱敏规则
3. 检查网络安全策略
4. 定期更新依赖包版本

### 已修复的问题
**代码结构问题（已修复）**:
1. ✅ `start.py` 文件中的导入路径错误 - 已修复所有 `src.` 前缀导入
2. ✅ `test_integration.py` 的错误导入路径 - 已修复
3. ✅ `test_service.py` 的错误导入路径 - 已修复
4. ✅ `test_semantic_completion.py` 的错误导入路径 - 已修复
5. ✅ `tests/integration/` 目录下所有测试文件的导入路径 - 已修复
6. ✅ 配置文件格式兼容 - `mongodb.instances` 自动转换为 `mongo_instances`

**修复内容**:
- 移除了所有错误的 `src.` 前缀导入
- 为测试文件添加了正确的项目根目录路径
- 确保所有模块导入使用正确的相对路径