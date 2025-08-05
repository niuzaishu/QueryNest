# QueryNest - MongoDB多实例查询服务

QueryNest是一个基于MCP (Model Context Protocol) 的MongoDB多实例查询服务，提供智能化的数据库结构发现、语义分析和自然语言查询生成功能。

## 📍 项目信息

- **版本**: v1.0.0
- **状态**: ✅ 生产就绪
- **许可证**: MIT License
- **语言**: Python 3.12+
- **架构**: 异步/基于MCP协议

## 🚀 主要特性

### 🔍 智能查询
- **自然语言查询**：支持中文自然语言描述查询需求
- **MongoDB原生查询**：支持标准MongoDB查询语法
- **聚合管道**：支持复杂的数据聚合操作
- **查询优化**：自动优化查询性能
- **查询缓存**：智能缓存提升查询速度

### 🏢 多实例管理
- **实例发现**：自动发现和连接多个MongoDB实例
- **负载均衡**：智能分配查询请求
- **健康检查**：实时监控实例状态
- **故障转移**：自动处理实例故障
- **连接池管理**：优化数据库连接使用

### 🛡️ 安全控制
- **只读权限**：确保数据安全，仅支持读取操作
- **查询限制**：限制查询复杂度和返回数据量
- **数据脱敏**：自动识别和脱敏敏感信息
- **访问控制**：基于角色的访问权限管理
- **安全审计**：记录所有查询操作

### 🧠 智能分析
- **结构发现**：自动分析数据库结构和字段类型
- **语义理解**：理解字段的业务含义
- **查询建议**：提供查询优化建议
- **性能分析**：分析查询性能和瓶颈
- **索引建议**：智能推荐索引优化方案

### 📊 监控与指标
- **实时监控**：系统性能和查询指标实时监控
- **性能分析**：详细的查询性能统计
- **错误追踪**：完整的错误记录和分析
- **健康检查**：系统健康状态评估
- **指标导出**：支持多种格式的指标导出

### 🔧 用户体验
- **错误处理**：友好的错误提示和建议
- **用户反馈**：完整的反馈收集系统
- **帮助系统**：内置帮助文档和FAQ
- **配置验证**：自动验证配置文件和环境

### 🔌 MCP集成
- **标准协议**：完全兼容MCP（Model Context Protocol）
- **工具丰富**：提供完整的查询和分析工具集
- **交互式**：支持对话式查询和探索
- **可扩展**：易于集成到各种AI应用中
- **反馈工具**：内置用户反馈和帮助工具

## 📦 安装部署

### 环境要求

- Python 3.8+
- MongoDB 4.0+
- 可选：Redis（用于缓存）

### 🚀 快速开始

#### 快速启动（推荐）

使用uvx快速启动服务：

```bash
# 安装uv工具（如果尚未安装）
pip install uv

# 从项目目录启动（推荐）
cd /path/to/QueryNest
uvx --from . --no-cache querynest-mcp

# 或从任何位置启动
uvx --from /path/to/QueryNest --no-cache querynest-mcp
```

uvx启动的优势：
- 自动处理依赖关系
- 无需预安装包到环境
- 使用隔离的执行环境
- 自动缓存加速后续启动

#### 手动安装

1. **克隆项目**
```bash
git clone https://github.com/niuzaishu/QueryNest.git
cd QueryNest
```

2. **安装依赖**
```bash
cd QueryNest
pip install -r requirements.txt
```

3. **配置服务**
```bash
# 复制配置模板
cp config.example.yaml config.yaml

# 编辑配置文件（根据实际环境修改MongoDB连接字符串）
vim config.yaml  # 或使用您喜欢的编辑器
```

4. **启动服务**
```bash
# 开发模式（直接运行）
python mcp_server.py --log-level DEBUG

# 生产模式（使用uvx，推荐）
uvx --from . --no-cache querynest-mcp

# 设置配置文件路径（如果需要）
export QUERYNEST_CONFIG_PATH=/path/to/config.yaml
```

#### Docker 部署

```bash
# 构建并启动
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

## ⚙️ 配置说明

### 🔌 MCP 客户端配置

服务启动后，可以在支持MCP协议的AI客户端中配置QueryNest服务以实现智能数据库查询功能。

#### 1. 项目结构

```
QueryNest/
├── 📄 配置文件
│   ├── config.yaml              # 主配置文件
│   ├── config.example.yaml      # 配置模板
│   └── config.py               # 配置管理
├── 🚀 核心服务
│   ├── mcp_server.py           # MCP服务器入口
│   ├── start.py               # 备用启动脚本
│   └── database/              # 数据库连接和管理
├── 🔧 MCP工具集
│   └── mcp_tools/             # MCP协议工具实现
├── 🔍 扫描分析
│   └── scanner/               # 数据库扫描和语义分析
├── 🛠️ 工具类
│   └── utils/                 # 验证、错误处理、工作流管理
├── 🧪 测试代码
│   └── tests/                 # 单元测试和集成测试
├── 📚 文档
│   └── docs/                  # 完整项目文档
├── 📦 部署
│   └── deployment/            # Docker和服务配置
└── 📜 脚本
    └── scripts/               # 数据库检查和测试工具
```

> 📖 详细结构说明请参考 [`docs/PROJECT_STRUCTURE.md`](docs/PROJECT_STRUCTURE.md)

QueryNest 已经配置为可通过 uvx 运行的包，项目包含以下关键文件：

**setup.py** - 包配置文件：
```python
setup(
    name="querynest",
    version="1.0.0",
    description="QueryNest MCP MongoDB查询服务",
    py_modules=["mcp_server", "config"],
    packages=["database", "scanner", "mcp_tools", "utils"],
    entry_points={
        "console_scripts": [
            "querynest-mcp=mcp_server:cli_main",
        ]
    },
)
```

**入口点配置** - 在 `mcp_server.py` 中定义了 CLI 入口：
```python
def cli_main():
    """命令行入口点"""
    # 自动查找配置文件并设置环境
    # 支持从不同目录启动
    asyncio.run(main())

if __name__ == "__main__":
    cli_main()
```

#### 2. 本地运行步骤

**步骤 1：安装 uv 工具**

如果尚未安装uv，可通过以下方式安装：

```bash
# 使用pip安装（推荐）
pip install uv

# 或使用官方安装脚本（Linux/macOS）
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows PowerShell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# 验证安装
uvx --version
```

**步骤 2：启动服务**

在项目根目录下运行：

```bash
# 推荐方式：从项目目录运行
cd /path/to/QueryNest
uvx --from . --no-cache querynest-mcp

# 或设置环境变量指定配置文件
export QUERYNEST_CONFIG_PATH=/path/to/QueryNest/config.yaml
uvx --from /path/to/QueryNest --no-cache querynest-mcp
```

**步骤 3：验证服务启动**

服务启动成功后，您应该看到类似以下的日志输出：
```json
{"event": "Starting QueryNest MCP server initialization", "config_path": "/path/to/config.yaml"}
{"event": "Configuration loaded successfully", "instances_count": 2}
{"event": "MCP tools initialized successfully", "tools_count": 13}
{"event": "Starting stdio MCP server"}
```

#### 3. MCP客户端集成

**uvx 工作原理：**

uvx 是一个现代的 Python 包执行工具，它可以：
- 自动从当前目录（`.`）安装包
- 管理临时虚拟环境
- 执行包的入口点命令

**MCP 客户端配置要点：**

对于支持MCP协议的AI客户端，QueryNest 的配置示例：

```json
{
  "mcpServers": {
    "QueryNest": {
      "command": "uvx",
      "args": ["--from", "/path/to/QueryNest", "--no-cache", "querynest-mcp"],
      "cwd": "/path/to/QueryNest",
      "env": {
        "QUERYNEST_CONFIG_PATH": "/path/to/QueryNest/config.yaml",
        "QUERYNEST_LOG_LEVEL": "INFO"
      }
    }
  }
}
```

**Windows 配置示例：**

```json
{
  "mcpServers": {
    "QueryNest": {
      "command": "uvx",
      "args": ["--from", "C:\\path\\to\\QueryNest", "--no-cache", "querynest-mcp"],
      "cwd": "C:\\path\\to\\QueryNest",
      "env": {
        "QUERYNEST_CONFIG_PATH": "C:\\path\\to\\QueryNest\\config.yaml"
      }
    }
  }
}
```

**关键配置说明：**
- `--from /path/to/QueryNest`: 指定项目绝对路径
- `--no-cache`: 确保使用最新代码
- `cwd`: 设置工作目录为项目根目录
- `querynest-mcp`: 在 setup.py 中定义的入口点命令

**优势：**
1. **项目路径明确**: 使用绝对路径确保找到正确的项目
2. **自动依赖管理**: uvx 自动处理所有依赖包
3. **隔离环境**: 每次运行都在独立的临时环境中
4. **配置文件自动发现**: 服务器会自动查找配置文件

#### 4. 故障排除

**常见问题及解决方案：**

**问题 1：uvx 命令不存在**
```bash
# 解决方案：安装uv工具
pip install uv

# 或使用官方安装脚本
curl -LsSf https://astral.sh/uv/install.sh | sh  # Linux/macOS
# powershell -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

# 验证安装
uvx --version
```

**问题 2：配置文件未找到**
```bash
# 检查配置文件是否存在
ls -la config.yaml

# 从示例创建配置文件
cp config.example.yaml config.yaml

# 设置环境变量
export QUERYNEST_CONFIG_PATH=/path/to/QueryNest/config.yaml
```

**问题 3：MCP 服务连接失败**
- 检查 MCP 客户端配置文件格式
- 确认项目路径是否正确（使用绝对路径）
- 验证 MongoDB 服务是否运行
- 检查配置文件 `config.yaml` 是否存在

**问题 4：MongoDB连接失败**
```bash
# 检查MongoDB服务状态
python scripts/check_db.py

# 手动测试MongoDB连接
python -c "
from pymongo import MongoClient
client = MongoClient('mongodb://localhost:27017/')
print('MongoDB连接成功')
"

# 检查MongoDB服务是否运行
# Linux/macOS
sudo systemctl status mongod
# Windows
net start | findstr -i mongo
```

**验证配置成功：**
```bash
# 测试本地运行
cd /path/to/QueryNest
uvx --from . --no-cache querynest-mcp --help

# 检查项目结构
ls -la setup.py mcp_server.py config.yaml

# 验证入口点
python -c "
from mcp_server import cli_main
print('Entry point OK')
"

# 测试完整启动流程
uvx --from . --no-cache querynest-mcp --log-level INFO
```



### MongoDB实例配置

QueryNest支持灵活的环境配置，您可以根据实际需求配置不同类型的实例：

1. **传统环境配置**（dev、test、uat、sit、staging、prod）
2. **业务系统配置**（crm-prod、order-system、user-center）
3. **地域集群配置**（beijing、shanghai、guangzhou）
4. **自定义环境配置**（任意命名）

```yaml
mongodb:
  instances:
    prod-main:
      name: "生产主库"
      environment: "prod"
      connection_string: "mongodb://admin:password@localhost:27017/admin"
      database: "prod_database"
      description: "生产环境主数据库"
      status: "active"
      tags: ["production", "primary"]
    
    crm-prod:
      name: "CRM生产库"
      environment: "crm-prod"
      connection_string: "mongodb://crm_user:${CRM_DB_PASSWORD}@crm-db.company.com:27017/admin"
      database: "crm_database"
      description: "CRM系统生产数据库"
      status: "active"
      tags: ["crm", "production"]
    
    beijing-cluster:
      name: "北京集群"
      environment: "beijing"
      connection_string: "mongodb://readonly:${BEIJING_DB_PASSWORD}@beijing-mongo.company.com:27017/admin"
      database: "beijing_database"
      description: "北京地域MongoDB集群"
      status: "active"
      tags: ["beijing", "cluster"]
```

### 安全配置

```yaml
security:
  permissions:
    allowed_operations:
      - "find"
      - "count"
      - "aggregate"
      - "distinct"
    forbidden_operations:
      - "insert"
      - "update"
      - "delete"
  limits:
    max_documents: 1000
    query_timeout: 30
  data_masking:
    enabled: true
    sensitive_field_patterns:
      - "password"
      - "email"
      - "phone"
```

### 环境变量配置

支持多实例独立的环境变量管理：

```bash
# .env 文件示例
# 传统环境密码
PROD_DB_PASSWORD=your_prod_password
TEST_DB_PASSWORD=your_test_password
DEV_DB_PASSWORD=your_dev_password

# 业务系统密码
CRM_DB_PASSWORD=your_crm_password
ORDER_DB_PASSWORD=your_order_password
USER_CENTER_DB_PASSWORD=your_user_center_password

# 地域集群密码
BEIJING_DB_PASSWORD=your_beijing_password
SHANGHAI_DB_PASSWORD=your_shanghai_password
GUANGZHOU_DB_PASSWORD=your_guangzhou_password

# 自定义实例密码
CUSTOM_INSTANCE_PASSWORD=your_custom_password
```

### 端口配置

- **MCP服务**: 默认使用stdio通信，无需端口；HTTP模式可配置端口（默认8000）
- **MongoDB**: 27017 (Docker容器内部)
- **Prometheus**: 9090 (监控面板)
- **应用监控**: 8000 (可选，用于健康检查)

**端口说明：**
- stdio模式：通过标准输入输出通信，无需网络端口
- HTTP模式：通过环境变量 `QUERYNEST_MCP_PORT` 配置端口

### 元数据配置

```yaml
metadata:
  instance_id: "dev-local"  # 可以是任意环境标识
  database_name: "querynest_metadata"
  collections:
    instances: "instances"
    databases: "databases"
    collections: "collections"
    fields: "fields"
    query_history: "query_history"
```

## 🛠️ MCP工具使用

### 1. 实例发现 (discover_instances)

发现和列出所有可用的MongoDB实例。

```json
{
  "name": "discover_instances",
  "arguments": {
    "include_health": true,
    "include_stats": true
  }
}
```

### 2. 数据库发现 (discover_databases)

列出指定实例中的所有数据库。

```json
{
  "name": "discover_databases",
  "arguments": {
    "instance_id": "prod-main",
    "include_collections": true,
    "exclude_system": true
  }
}
```

### 3. 集合分析 (analyze_collection)

分析指定集合的结构和字段信息。

```json
{
  "name": "analyze_collection",
  "arguments": {
    "instance_id": "prod-main",
    "database_name": "ecommerce",
    "collection_name": "users",
    "include_semantics": true,
    "include_examples": true,
    "rescan": false
  }
}
```

### 4. 语义管理 (manage_semantics)

管理字段的业务语义信息。

```json
{
  "name": "manage_semantics",
  "arguments": {
    "action": "batch_analyze",
    "instance_id": "prod-main",
    "database_name": "ecommerce",
    "collection_name": "users"
  }
}
```

### 5. 查询生成 (generate_query)

根据自然语言描述生成MongoDB查询。

```json
{
  "name": "generate_query",
  "arguments": {
    "instance_id": "prod-main",
    "database_name": "ecommerce",
    "collection_name": "orders",
    "query_description": "查找今天创建的订单，按金额降序排列",
    "query_type": "auto",
    "limit": 50
  }
}
```

### 6. 查询确认 (confirm_query)

执行生成的查询并返回结果。

```json
{
  "name": "confirm_query",
  "arguments": {
    "instance_id": "prod-main",
    "database_name": "ecommerce",
    "collection_name": "orders",
    "query_type": "find",
    "mongodb_query": {
      "filter": {"created_at": {"$gte": "2024-01-01T00:00:00Z"}},
      "sort": {"amount": -1},
      "limit": 50
    },
    "explain": true
  }
}
```

## 📊 使用示例

### 场景1：电商数据分析

1. **发现实例和数据库**
```
用户："帮我查看有哪些可用的数据库实例"
助手：使用 discover_instances 工具
```

2. **分析用户集合**
```
用户："分析一下电商数据库中的用户表结构"
助手：使用 analyze_collection 工具分析 users 集合
```

3. **自然语言查询**
```
用户："查找最近一周注册的活跃用户，按注册时间排序"
助手：使用 generate_query 生成查询，然后用 confirm_query 执行
```

### 场景2：日志数据查询

1. **语义分析**
```
用户："帮我理解日志集合中各个字段的含义"
助手：使用 manage_semantics 进行批量语义分析
```

2. **复杂聚合查询**
```
用户："统计每小时的错误日志数量，按时间分组"
助手：生成聚合查询并执行
```

## 🔧 开发指南

### 项目结构

```
QueryNest/
├── src/
│   ├── __init__.py
│   ├── config.py              # 配置管理
│   ├── mcp_server.py          # MCP服务器主文件
│   ├── database/              # 数据库模块
│   │   ├── __init__.py
│   │   ├── connection_manager.py
│   │   ├── metadata_manager.py
│   │   └── query_engine.py
│   ├── scanner/               # 扫描模块
│   │   ├── __init__.py
│   │   ├── structure_scanner.py
│   │   └── semantic_analyzer.py
│   └── mcp_tools/             # MCP工具
│       ├── __init__.py
│       ├── instance_discovery.py
│       ├── database_discovery.py
│       ├── collection_analysis.py
│       ├── semantic_management.py
│       ├── query_generation.py
│       └── query_confirmation.py
├── config.yaml                # 配置文件
├── requirements.txt           # 依赖列表
└── README.md                  # 项目文档
```

### 添加新工具

1. **创建工具类**
```python
class NewTool:
    def get_tool_definition(self) -> Tool:
        # 定义工具接口
        pass
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        # 实现工具逻辑
        pass
```

2. **注册工具**
```python
# 在 mcp_server.py 中注册
new_tool = NewTool(...)
self.tools["new_tool"] = new_tool
```

### 扩展语义分析

1. **添加语义规则**
```python
# 在 semantic_analyzer.py 中添加
self.semantic_patterns.update({
    "custom_field": {
        "patterns": [r"custom_.*"],
        "meaning": "自定义字段",
        "confidence": 0.8
    }
})
```

2. **自定义分析逻辑**
```python
def analyze_custom_semantics(self, field_info):
    # 实现自定义语义分析逻辑
    pass
```

## 🚨 注意事项

### 安全考虑

1. **权限控制**
   - 确保只允许读取操作
   - 配置适当的查询限制
   - 启用数据脱敏功能

2. **网络安全**
   - 使用SSL/TLS连接
   - 配置防火墙规则
   - 定期更新密码

3. **数据保护**
   - 避免记录敏感信息
   - 定期清理查询历史
   - 监控异常访问

### 性能优化

1. **连接管理**
   - 合理配置连接池大小
   - 启用连接复用
   - 监控连接健康状态

2. **查询优化**
   - 使用适当的索引
   - 限制查询结果数量
   - 避免复杂的聚合操作

3. **缓存策略**
   - 启用元数据缓存
   - 缓存常用查询结果
   - 定期清理过期缓存

## 📝 更新日志

### v1.0.0 (2024-01-01)
- 初始版本发布
- 支持多实例MongoDB连接
- 实现基础的结构扫描和语义分析
- 提供完整的MCP工具集
- 支持自然语言查询生成

## 🧪 测试

### 运行所有测试

```bash
python -m pytest tests/ -v
```

### 运行单元测试

```bash
# 测试连接管理器
python -m pytest tests/unit/test_connection_manager.py -v

# 测试查询引擎
python -m pytest tests/unit/test_query_engine.py -v

# 测试元数据管理器
python -m pytest tests/unit/test_metadata_manager.py -v

# 测试数据库扫描器
python -m pytest tests/unit/test_database_scanner.py -v

# 测试MCP工具
python -m pytest tests/unit/test_mcp_tools.py -v
```

### 测试覆盖率

```bash
pip install pytest-cov
python -m pytest tests/ --cov=src --cov-report=html
```

### 环境验证

```bash
# 验证启动环境
python -c "
from utils.startup_validator import validate_startup_environment
print(validate_startup_environment())
"
```

## 📚 文档

### 核心文档
- [技术架构](app.md) - 详细的技术架构说明
- [配置指南](config.example.yaml) - 配置文件说明
- [环境变量](.env.example) - 环境变量配置说明

### 部署文档
- [部署脚本](deploy.py) - 自动部署工具
- [Docker部署](docker-compose.yml) - 容器化部署
- [服务配置](querynest.service) - 系统服务配置

### 开发文档
- [单元测试](tests/unit/) - 完整的单元测试套件
- [错误处理](src/utils/error_handler.py) - 错误处理机制
- [监控指标](src/utils/monitoring.py) - 性能监控系统
- [配置验证](src/utils/config_validator.py) - 配置验证工具

### 用户指南
- [快速开始](#-快速开始) - 快速部署和使用
- [功能特性](#-功能特性) - 详细功能说明
- [故障排除](#-故障排除) - 常见问题解决

## 📚 更多资源

- [Docker部署指南](DOCKER.md)
- [贡献指南](CONTRIBUTING.md)
- [变更日志](CHANGELOG.md)
- [MCP协议文档](https://modelcontextprotocol.io/)
- [MongoDB官方文档](https://docs.mongodb.com/)
- [Python异步编程指南](https://docs.python.org/3/library/asyncio.html)

## 🔧 故障排除

### 常见问题

#### 3. 连接MongoDB失败
```bash
# 检查MongoDB服务状态
sudo systemctl status mongod

# 测试网络连接
telnet <mongodb_host> <mongodb_port>

# 验证认证信息
mongo --host <host> --port <port> -u <username> -p
```

#### 4. 配置文件错误
```bash
# 验证配置文件
python -c "
from utils.config_validator import ConfigValidator
validator = ConfigValidator()
print(validator.validate_config_file('config.yaml'))
"
```

### 环境变量配置

QueryNest 支持以下环境变量：

| 环境变量 | 描述 | 默认值 | 示例 |
|---------|------|--------|---------|
| `QUERYNEST_CONFIG_PATH` | 配置文件路径 | `config.yaml` | `/app/config.yaml` |
| `QUERYNEST_LOG_LEVEL` | 日志级别 | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `QUERYNEST_MCP_TRANSPORT` | MCP传输方式 | `stdio` | `stdio`, `http` |
| `QUERYNEST_MCP_HOST` | HTTP模式主机地址 | `None` | `0.0.0.0` |
| `QUERYNEST_MCP_PORT` | HTTP模式端口 | `None` | `8000` |
| `MONGO_PROD_PASSWORD` | 生产环境MongoDB密码 | - | `your_password` |
| `MONGO_TEST_PASSWORD` | 测试环境MongoDB密码 | - | `your_password` |
| `MONGO_DEV_PASSWORD` | 开发环境MongoDB密码 | - | `your_password` |

**Linux/macOS 示例：**
```bash
# 设置配置文件路径
export QUERYNEST_CONFIG_PATH=/path/to/QueryNest/config.yaml

# 设置日志级别
export QUERYNEST_LOG_LEVEL=DEBUG

# MCP传输模式（目前仅支持stdio）
export QUERYNEST_MCP_TRANSPORT=stdio
```

**Windows 示例：**
```cmd
# CMD
set QUERYNEST_CONFIG_PATH=C:\path\to\QueryNest\config.yaml
set QUERYNEST_LOG_LEVEL=DEBUG

# PowerShell
$env:QUERYNEST_CONFIG_PATH="C:\path\to\QueryNest\config.yaml"
$env:QUERYNEST_LOG_LEVEL="DEBUG"
```

#### 5. 依赖包问题
```bash
cd /path/to/QueryNest

# 重新安装依赖
pip install -r requirements.txt --force-reinstall

# 检查Python版本
python --version

# 检查关键包安装状态
pip list | grep -E "(mcp|pymongo|motor)"
```

#### 6. 权限和路径问题
```bash
# 检查文件是否存在
ls -la config.yaml mcp_server.py

# 检查目录权限
ls -ld . logs/

# 修复权限（如果需要）
chmod 755 .
chmod 644 config.yaml
chmod +x mcp_server.py

# 创建日志目录（如果不存在）
mkdir -p logs/
```

### 日志分析

查看详细日志：
```bash
# 查看应用日志
tail -f logs/querynest.log

# 查看错误日志
tail -f logs/error.log

# 查看系统日志
journalctl -u querynest -f
```

### 性能调优

```bash
# 查看系统资源使用
top
htop

# 查看MongoDB性能
mongotop
mongostat

# 查看网络连接
netstat -an | grep :27017
```

## 🤝 贡献指南

我们欢迎各种形式的贡献！请查看 [CONTRIBUTING.md](CONTRIBUTING.md) 了解如何参与项目开发。

### 快速贡献指南

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 添加测试用例
4. 运行测试确保通过 (`python -m pytest tests/ -v`)
5. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
6. 推送到分支 (`git push origin feature/AmazingFeature`)
7. 开启 Pull Request

### 开发环境

```bash
# 克隆项目
git clone <repository_url>
cd QueryNest

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# 安装开发依赖
pip install -r requirements.txt
pip install pytest pytest-cov black flake8

# 运行代码格式化
black src/ tests/

# 运行代码检查
flake8 src/ tests/
```

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🙏 致谢

感谢所有贡献者和以下开源项目：

- [PyMongo](https://pymongo.readthedocs.io/) - MongoDB Python驱动
- [PyYAML](https://pyyaml.org/) - YAML解析器
- [psutil](https://psutil.readthedocs.io/) - 系统监控库
- [pytest](https://pytest.org/) - 测试框架

## 📞 支持

如果您遇到问题或有建议，请：

1. 查看 [FAQ](docs/FAQ.md)
2. 搜索 [Issues](../../issues)
3. 创建新的 [Issue](../../issues/new)
4. 查看 [GitHub Discussions](https://github.com/your-repo/QueryNest/discussions)
5. 联系维护者

## 🙏 致谢

感谢以下项目和贡献者：

- [MCP (Model Context Protocol)](https://github.com/modelcontextprotocol/python-sdk)
- [PyMongo](https://github.com/mongodb/mongo-python-driver)
- [Motor](https://github.com/mongodb/motor)
- [Pydantic](https://github.com/pydantic/pydantic)
- [StructLog](https://github.com/hynek/structlog)

---

**QueryNest** - 让MongoDB查询变得简单智能 🚀