# QueryNest 项目结构

```
QueryNest/
├── README.md                      # 项目主文档
├── LICENSE                        # 开源许可证
├── CHANGELOG.md                   # 版本变更记录
├── CLAUDE.md                      # Claude Code 工作指南
├── config.yaml                    # 主配置文件
├── config.example.yaml            # 配置文件模板
├── config.py                      # 配置管理模块
├── mcp_server.py                  # MCP服务器主入口
├── start.py                       # 备用启动脚本
├── setup.py                       # Python包安装脚本
├── pyproject.toml                 # 项目构建配置
├── requirements.txt               # 依赖包列表
├── pytest.ini                    # pytest配置
│
├── docs/                          # 文档目录
│   ├── PROJECT_STRUCTURE.md       # 项目结构说明(本文件)
│   ├── COMPREHENSIVE_TEST_REPORT.md           # 综合测试报告
│   ├── FUNCTIONALITY_VERIFICATION_REPORT.md  # 功能验证报告
│   ├── EXECUTABLE_QUERY_GUIDE.md             # 可执行查询使用指南
│   ├── PARAMETER_OPTIMIZATION_GUIDE.md       # 参数优化指南
│   ├── SEMANTIC_WRITE_SCENARIOS.md           # 语义写入场景文档
│   └── CONTRIBUTING.md                       # 贡献指南
│
├── deployment/                    # 部署相关文件
│   ├── Dockerfile                 # Docker容器化配置
│   ├── querynest.service          # systemd服务配置
│   └── start.sh                   # Linux启动脚本
│
├── database/                      # 数据库层
│   ├── __init__.py
│   ├── connection_manager.py      # 多实例连接管理
│   ├── metadata_manager.py        # 元数据管理
│   └── query_engine.py            # 查询执行引擎
│
├── scanner/                       # 数据扫描和分析
│   ├── __init__.py
│   ├── structure_scanner.py       # 结构扫描器
│   ├── semantic_analyzer.py       # 语义分析器
│   └── database_scanner.py        # 数据库扫描器
│
├── mcp_tools/                     # MCP工具集
│   ├── __init__.py
│   ├── instance_discovery.py      # 实例发现工具
│   ├── database_discovery.py      # 数据库发现工具
│   ├── collection_analysis.py     # 集合分析工具
│   ├── semantic_management.py     # 语义管理工具
│   ├── semantic_completion.py     # 语义补全工具
│   ├── semantic_confirmation.py   # 语义确认工具
│   ├── semantic_feedback.py       # 语义反馈工具
│   ├── query_generation.py        # 查询生成工具
│   ├── query_confirmation.py      # 查询确认工具
│   └── workflow_management.py     # 工作流管理工具
│
├── utils/                         # 工具类
│   ├── config_validator.py        # 配置验证工具
│   ├── error_handler.py           # 错误处理工具
│   ├── logger.py                  # 日志工具
│   ├── parameter_validator.py     # 参数验证工具
│   ├── startup_validator.py       # 启动验证工具
│   ├── tool_context.py            # 工具上下文管理
│   ├── workflow_manager.py        # 工作流管理器
│   └── workflow_wrapper.py        # 工作流包装器
│
├── tests/                         # 测试代码
│   ├── __init__.py
│   ├── unit/                      # 单元测试
│   │   ├── test_dual_semantic_unit.py      # 双重语义存储测试
│   │   ├── test_mcp_tools_unit.py          # MCP工具单元测试
│   │   ├── test_integration.py             # 集成测试
│   │   ├── test_mongodb_setup.py           # MongoDB设置测试
│   │   ├── test_semantic_completion.py     # 语义补全测试
│   │   └── test_service.py                 # 服务测试
│   └── integration/               # 集成测试
│       ├── __init__.py
│       ├── base_integration_test.py        # 集成测试基类
│       ├── test_config.py                  # 测试配置
│       ├── test_dual_semantic_storage.py   # 双重语义存储集成测试
│       ├── test_end_to_end.py              # 端到端测试
│       └── test_mcp_tools_integration.py   # MCP工具集成测试
│
├── scripts/                       # 脚本工具
│   ├── check_db.py                # 数据库连接检查
│   ├── insert_test_data.py        # 插入测试数据
│   └── run_integration_tests.py   # 运行集成测试
│
└── logs/                          # 日志文件目录
    └── (运行时生成的日志文件)
```

## 核心模块说明

### 1. 服务器入口 (`mcp_server.py`)
- MCP协议服务器实现
- 工具注册和管理
- 异步事件处理
- 配置初始化

### 2. 配置管理 (`config.py`)
- 多环境配置支持
- MongoDB实例配置
- 安全设置管理
- 环境变量覆盖

### 3. 数据库层 (`database/`)
- **连接管理器**: 多实例连接池，健康检查，故障转移
- **元数据管理器**: 双重存储策略，语义信息管理
- **查询引擎**: 安全查询执行，结果格式化

### 4. 扫描模块 (`scanner/`)
- **结构扫描器**: 数据库结构发现，字段类型分析
- **语义分析器**: 自动字段含义识别，模式匹配
- **数据库扫描器**: 批量数据库扫描和分析

### 5. MCP工具集 (`mcp_tools/`)
- **发现工具**: 实例、数据库、集合发现
- **分析工具**: 集合结构分析，索引信息
- **语义工具**: 语义管理、补全、确认、反馈
- **查询工具**: 查询生成、执行确认
- **工作流工具**: 工作流状态管理

### 6. 工具类 (`utils/`)
- **验证工具**: 配置、参数、启动验证
- **错误处理**: 统一异常处理，用户友好错误
- **工作流管理**: 工具调用链，状态管理
- **上下文管理**: 工具间数据传递，历史记录

## 设计原则

### 1. 模块化架构
- 每个模块职责清晰
- 低耦合高内聚
- 易于扩展和维护

### 2. 异步优先
- 全异步数据库操作
- 支持并发查询处理
- 非阻塞工具执行

### 3. 安全第一
- 只读数据库访问
- 查询安全验证
- 数据脱敏处理

### 4. 双重存储
- 元数据库主存储
- 业务库fallback
- 保证高可用性

### 5. 智能参数处理
- 自动参数验证
- 上下文感知补全
- 用户友好提示

## 扩展指南

### 添加新的MCP工具
1. 在`mcp_tools/`创建新工具文件
2. 实现`get_tool_definition()`和`execute()`方法
3. 在`mcp_server.py`中注册工具
4. 添加相应的单元测试

### 添加新的数据源类型
1. 在`database/`添加新的连接管理器
2. 实现统一的查询接口
3. 更新配置结构支持新类型
4. 添加相应的扫描器支持

### 扩展语义分析能力
1. 在`scanner/semantic_analyzer.py`添加新模式
2. 更新字段匹配规则
3. 增强推理算法
4. 添加领域特定词库

---

**最后更新**: 2025-08-05  
**维护者**: QueryNest Team