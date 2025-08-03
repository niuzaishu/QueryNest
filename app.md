# QueryNest - MCP MongoDB查询服务技术方案

## 项目概述

QueryNest是一个基于MCP（Model Context Protocol）的MongoDB数据库查询服务端，旨在为上层AI工具提供安全、智能的数据库查询能力。该服务作为MCP服务端，通过自动发现数据库结构，在与上层工具的对话交互中逐步理解业务含义，并提供交互式查询确认机制，确保数据安全的同时提升查询效率。

**项目地址**: [https://github.com/niuzaishu/QueryNest](https://github.com/niuzaishu/QueryNest)  
**作者**: [niuzaishu](https://github.com/niuzaishu)

## 核心功能需求

1. **自动数据库发现**：能够自动扫描并识别需要查询的MongoDB数据库
2. **业务语义理解**：通过MCP协议与上层工具交互，在对话中了解各库表各字段的业务含义
3. **只读权限控制**：严格限制为查询操作，避免任何数据更改
4. **MCP交互式查询**：通过MCP协议支持对话式的数据库选择和查询条件调整

## 技术架构设计

### 1. 数据库权限分层设计

#### 1.1 元数据管理库（读写权限）
- **库名**：`querynest_metadata`
- **用途**：存储多实例配置、数据库结构信息和业务语义
- **权限**：MCP服务对此库拥有完整读写权限

**核心集合设计**：

```
// MongoDB实例信息表
instances: {
  _id: ObjectId,
  instance_name: String,
  instance_alias: String,
  connection_string: String,
  description: String,
  environment: String, // dev, test, prod
  status: String, // active, inactive
  created_at: Date,
  updated_at: Date
}

// 数据库信息表
databases: {
  _id: ObjectId,
  instance_id: ObjectId,
  database_name: String,
  description: String,
  business_domain: String,
  created_at: Date,
  updated_at: Date,
  status: String // active, inactive
}

// 集合信息表
collections: {
  _id: ObjectId,
  instance_id: ObjectId,
  database_name: String,
  collection_name: String,
  description: String,
  business_purpose: String,
  sample_documents: Array,
  document_count: Number,
  created_at: Date,
  updated_at: Date
}

// 字段信息表
fields: {
  _id: ObjectId,
  instance_id: ObjectId,
  database_name: String,
  collection_name: String,
  field_path: String, // 支持嵌套字段，如 "user.profile.age"
  field_type: String,
  business_meaning: String,
  examples: Array,
  is_indexed: Boolean,
  is_required: Boolean,
  created_at: Date,
  updated_at: Date
}

// 查询历史表
query_history: {
  _id: ObjectId,
  session_id: String,
  instance_id: ObjectId,
  user_intent: String,
  selected_database: String,
  selected_collection: String,
  generated_query: Object,
  execution_result: Object,
  user_feedback: String,
  created_at: Date
}
```

#### 1.2 多实例业务数据库（只读权限）
- **权限**：MCP服务对所有实例的业务数据库仅拥有读取权限
- **操作限制**：禁止insert、update、delete、drop等写操作
- **连接配置**：每个实例使用专门的只读用户连接
- **实例隔离**：不同实例间的数据完全隔离，避免交叉访问

### 2. 系统初始化流程

#### 2.1 多实例数据库结构扫描
1. **实例连接**：根据配置连接到所有已配置的MongoDB实例
2. **数据库发现**：扫描每个实例中的所有数据库
3. **集合分析**：遍历每个实例每个数据库的所有集合
4. **字段提取**：分析集合中的文档结构，提取字段信息
5. **类型推断**：基于样本数据推断字段类型和特征
6. **索引识别**：获取集合的索引信息
7. **实例标记**：为所有元数据标记所属实例

#### 2.2 业务语义初始化
1. **基础信息录入**：为数据库、集合、字段创建基础记录
2. **智能推断**：基于字段名称和数据特征进行业务含义的初步推断
3. **对话式完善**：通过MCP协议与上层工具交互，在用户查询过程中逐步完善业务语义
4. **持续更新**：定期扫描数据库结构变化并更新元数据

### 3. MCP查询交互流程

#### 3.1 MCP工具调用阶段
1. **需求接收**：通过MCP协议接收上层工具传递的查询需求
2. **意图解析**：分析用户的查询需求和业务意图
3. **实例选择**：基于查询需求推荐合适的MongoDB实例
4. **数据库匹配**：在选定实例中基于业务语义匹配最相关的数据库和集合
5. **字段映射**：将用户描述的业务概念映射到具体字段

#### 3.2 交互式实例和数据库选择
1. **实例推荐**：通过MCP响应向上层工具返回推荐的MongoDB实例
2. **数据库推荐**：在选定实例中推荐相关的数据库和集合
3. **详细说明**：提供实例、数据库、集合的业务用途说明
4. **对话确认**：通过MCP协议与用户进行多轮对话确认或调整选择
5. **语义完善**：在对话过程中收集并完善业务语义信息
6. **反馈学习**：记录用户的选择偏好用于优化推荐

#### 3.3 查询生成与确认
1. **查询生成**：基于确认的数据库和用户需求生成MongoDB查询
2. **查询解释**：通过MCP协议向用户说明查询逻辑和预期结果
3. **安全检查**：确保查询不包含任何写操作
4. **对话确认**：通过MCP协议等待用户确认执行或要求调整

#### 3.4 执行与结果处理
1. **安全执行**：在只读权限下执行查询
2. **结果格式化**：将查询结果转换为用户友好的格式
3. **结果解释**：通过MCP协议提供结果的业务含义解释
4. **历史记录**：保存查询历史和语义学习记录用于后续优化

### 4. 安全控制机制

#### 4.1 权限控制
- **数据库级别**：业务数据库使用只读用户连接
- **操作级别**：代码层面禁止所有写操作
- **网络级别**：限制连接来源和端口访问

#### 4.2 查询安全
- **语法检查**：验证查询语法，拒绝包含写操作的查询
- **资源限制**：设置查询超时时间和结果集大小限制
- **审计日志**：记录所有查询操作和结果

#### 4.3 数据保护
- **敏感字段识别**：自动识别可能包含敏感信息的字段
- **数据脱敏**：对敏感数据进行适当的脱敏处理
- **访问控制**：基于用户角色控制可访问的数据范围

### 5. 智能优化机制

#### 5.1 查询优化
- **索引建议**：基于查询模式提供索引优化建议
- **查询重写**：优化查询性能，避免全表扫描
- **查询历史**：保存查询记录用于追踪和分析

#### 5.2 学习机制
- **用户偏好学习**：记录用户的查询习惯和偏好
- **语义关联学习**：基于用户反馈优化业务语义映射
- **查询模式识别**：识别常见查询模式并提供快捷方式

### 6. 系统架构组件

#### 6.1 核心服务组件
- **MCP服务端框架**：实现MCP协议的服务端功能，处理工具调用和响应
- **多实例连接管理器**：管理多个MongoDB实例的连接池
- **查询引擎**：负责查询生成和执行
- **语义分析器**：处理业务语义理解和映射
- **安全控制器**：实施安全策略和权限控制
- **对话状态管理器**：管理多轮对话的上下文和状态，包括实例选择状态

#### 6.2 数据管理组件
- **元数据管理器**：管理多实例的数据库结构和业务语义信息
- **结构扫描器**：定期扫描数据库结构变化
- **缓存管理器**：管理查询结果和元数据缓存

#### 6.3 MCP交互组件
- **MCP对话管理器**：通过MCP协议处理与上层工具的交互和确认流程
- **结果格式化器**：格式化查询结果为用户友好格式
- **解释生成器**：生成查询和结果的业务解释
- **语义学习接口**：提供MCP工具接口供用户完善业务语义信息

### 7. MCP服务端部署

#### 7.1 MCP服务端配置
- **启动方式**：作为MCP服务端进程启动，监听stdio或HTTP端口
- **多实例配置**：使用配置文件管理多个MongoDB实例的连接信息
- **配置示例**：
```yaml
# MongoDB实例配置
mongodb:
  instances:
    prod-main:
      name: "生产主库"
      environment: "prod"
      connection_string: "mongodb://readonly:password@prod-host:27017/prod_database"
      database: "prod_database"
      description: "生产环境主数据库"
      status: "active"
      tags: ["prod", "main"]
      
    test-db:
      name: "测试环境"
      environment: "test"
      connection_string: "mongodb://readonly:password@test-host:27017/test_database"
      database: "test_database"
      description: "测试环境数据库"
      status: "active"
      tags: ["test"]

# 元数据库配置
metadata:
  database_name: "querynest_metadata"
  collections:
    instances: "instances"
    databases: "databases"
    collections: "collections"
    fields: "fields"
    query_history: "query_history"
  retention:
    query_history_days: 30
    scan_history_days: 90

# MCP服务配置
mcp:
  name: "querynest"
  version: "0.1.0"
  description: "QueryNest MCP MongoDB查询服务"
  transport: "stdio"
```
- **服务发现**：通过MCP协议向客户端暴露可用工具

#### 7.2 集成方式
- **Claude Desktop集成**：通过配置文件集成到Claude Desktop
- **其他MCP客户端**：支持任何兼容MCP协议的客户端工具
- **开发调试**：使用MCP Inspector进行开发和调试

#### 7.3 监控和日志
- **MCP协议日志**：记录所有MCP工具调用和响应
- **查询审计**：完整记录所有数据库查询操作
- **性能监控**：监控查询性能和响应时间
- **错误追踪**：记录和追踪系统错误和异常

#### 7.4 数据管理
- **元数据备份**：定期备份querynest_metadata数据库
- **配置备份**：备份MCP服务配置和业务语义数据
- **版本管理**：管理业务语义的版本变更

## MCP工具定义

### 核心MCP工具接口

#### 1. 实例发现工具
```json
{
  "name": "list_instances",
  "description": "列出所有可用的MongoDB实例",
  "inputSchema": {
    "type": "object",
    "properties": {
      "environment": {"type": "string", "description": "环境过滤（dev/test/prod）"}
    }
  }
}
```

#### 2. 数据库发现工具
```json
{
  "name": "discover_databases",
  "description": "发现并列出指定实例的MongoDB数据库",
  "inputSchema": {
    "type": "object",
    "properties": {
      "instance_name": {"type": "string", "description": "MongoDB实例名称"},
      "filter_pattern": {"type": "string", "description": "数据库名称过滤模式"}
    },
    "required": ["instance_name"]
  }
}
```

#### 3. 集合结构分析工具
```json
{
  "name": "analyze_collection",
  "description": "分析指定集合的结构和字段信息",
  "inputSchema": {
     "type": "object",
     "properties": {
       "instance_name": {"type": "string", "description": "MongoDB实例名称"},
       "database": {"type": "string", "description": "数据库名称"},
       "collection": {"type": "string", "description": "集合名称"}
     },
     "required": ["instance_name", "database", "collection"]
   }
}
```

#### 4. 业务语义管理工具
```json
{
  "name": "update_field_semantics",
  "description": "更新字段的业务语义信息",
  "inputSchema": {
    "type": "object",
    "properties": {
       "instance_name": {"type": "string"},
       "database": {"type": "string"},
       "collection": {"type": "string"},
       "field_path": {"type": "string"},
       "business_meaning": {"type": "string"},
       "examples": {"type": "array", "items": {"type": "string"}}
     },
     "required": ["instance_name", "database", "collection", "field_path", "business_meaning"]
  }
}
```

#### 5. 智能查询工具
```json
{
  "name": "query_data",
  "description": "基于自然语言描述查询数据",
  "inputSchema": {
    "type": "object",
    "properties": {
       "query_description": {"type": "string", "description": "查询需求的自然语言描述"},
       "preferred_instance": {"type": "string", "description": "首选MongoDB实例（可选）"},
       "preferred_database": {"type": "string", "description": "首选数据库（可选）"},
       "limit": {"type": "integer", "default": 10, "description": "结果数量限制"}
     },
     "required": ["query_description"]
  }
}
```

#### 6. 查询确认工具
```json
{
  "name": "confirm_and_execute",
  "description": "确认并执行生成的查询",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query_id": {"type": "string", "description": "查询ID"},
      "confirmed": {"type": "boolean", "description": "是否确认执行"},
      "modifications": {"type": "string", "description": "修改建议（可选）"}
    },
    "required": ["query_id", "confirmed"]
  }
}
```

## 技术栈选择

### MCP服务端技术
- **编程语言**：Python 3.9+
- **MCP框架**：基于官方MCP Python SDK
- **数据库驱动**：PyMongo
- **异步处理**：asyncio
- **配置管理**：Pydantic
- **协议通信**：JSON-RPC over stdio/HTTP

### 数据存储
- **主数据库**：MongoDB 5.0+（支持多实例）
- **元数据存储**：MongoDB（每个实例都创建独立的querynest_metadata库，按需初始化）
  - **按需初始化机制**：系统启动时不预先初始化所有实例的元数据库，当用户通过查询交互确认选择某个实例后，才异步初始化该实例的元数据库，避免了不必要的资源消耗和连接开销，提高了系统启动速度和资源利用效率
- **会话状态**：内存存储（Redis可选）
- **实例配置**：YAML/JSON配置文件，支持多实例连接信息

### 开发工具
- **代码质量**：Black, Flake8, MyPy
- **测试框架**：Pytest
- **MCP测试**：MCP Inspector
- **容器化**：Docker

## 风险评估和应对

### 技术风险
- **性能风险**：多实例大型数据库扫描可能影响性能
  - 应对：实现增量扫描、后台处理和实例负载均衡
- **兼容性风险**：不同MongoDB版本和实例配置的兼容性问题
  - 应对：充分测试和版本适配，支持实例特定配置
- **连接风险**：多实例连接管理的复杂性和稳定性
  - 应对：实现连接池管理、故障转移和健康检查

### 安全风险
- **权限泄露**：可能的权限提升攻击
  - 应对：严格的权限控制和代码审查
- **数据泄露**：敏感数据的意外暴露
  - 应对：数据脱敏和访问控制
- **实例隔离风险**：不同实例间的数据交叉访问
  - 应对：严格的实例隔离机制和访问控制
- **配置安全**：多实例连接信息的安全存储
  - 应对：配置文件加密和安全的密钥管理

### 业务风险
- **误操作风险**：用户可能进行不当查询或选择错误实例
  - 应对：多重确认机制、查询限制和实例选择确认
- **依赖风险**：对特定数据库结构的依赖
  - 应对：灵活的配置和适配机制
- **实例管理风险**：多实例配置和管理的复杂性
  - 应对：清晰的实例命名规范和管理流程

## 总结

本技术方案设计了一个完整的MCP MongoDB查询服务端，通过标准的MCP协议为上层AI工具提供安全、智能的数据库查询能力。该方案的核心特点包括：

1. **标准MCP协议**：完全基于MCP协议实现，确保与各种MCP客户端的兼容性
2. **对话式语义学习**：通过与用户的多轮对话逐步完善业务语义，无需额外的管理界面
3. **分层权限控制**：严格的只读权限控制和多层安全机制
4. **智能查询生成**：基于自然语言描述和业务语义智能生成MongoDB查询
5. **交互式确认**：通过MCP协议实现查询前的多重确认机制

该方案作为MCP服务端，可以无缝集成到Claude Desktop等支持MCP的AI工具中，为用户提供安全、便捷的数据库查询体验，同时在使用过程中不断学习和完善业务知识。