# 贡献指南

感谢您对QueryNest项目的关注！我们欢迎各种形式的贡献，包括但不限于：

**项目地址**: [https://github.com/niuzaishu/QueryNest](https://github.com/niuzaishu/QueryNest)

- 🐛 报告Bug
- 💡 提出新功能建议
- 📝 改进文档
- 🔧 提交代码修复
- ✨ 添加新功能
- 🧪 编写测试
- 🎨 改进用户界面

## 📋 开始之前

### 行为准则

参与本项目即表示您同意遵守我们的行为准则：

- 使用友好和包容的语言
- 尊重不同的观点和经验
- 优雅地接受建设性批评
- 专注于对社区最有利的事情
- 对其他社区成员表现出同理心

### 开发环境要求

- Python 3.8+
- MongoDB 4.4+
- Git
- Docker（可选，用于容器化开发）

## 🚀 快速开始

### 1. Fork和克隆项目

```bash
# Fork项目到您的GitHub账户
# 然后克隆您的fork
git clone https://github.com/YOUR_USERNAME/QueryNest.git
cd QueryNest

# 添加上游仓库
git remote add upstream https://github.com/niuzaishu/QueryNest.git
```

### 2. 设置开发环境

```bash
# 使用安装脚本
python install.py --dev

# 或手动安装
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. 运行测试

```bash
# 运行所有测试
python test_service.py

# 运行特定类型的测试
python test_service.py --test-type basic
python test_service.py --test-type advanced
```

## 🔄 开发流程

### 分支策略

我们使用以下分支策略：

- `main`: 主分支，包含稳定的生产代码
- `develop`: 开发分支，包含最新的开发代码
- `feature/*`: 功能分支，用于开发新功能
- `bugfix/*`: 修复分支，用于修复Bug
- `hotfix/*`: 热修复分支，用于紧急修复

### 创建功能分支

```bash
# 确保您在最新的develop分支上
git checkout develop
git pull upstream develop

# 创建新的功能分支
git checkout -b feature/your-feature-name
```

### 提交规范

我们使用[约定式提交](https://www.conventionalcommits.org/)规范：

```
<类型>[可选的作用域]: <描述>

[可选的正文]

[可选的脚注]
```

**类型**：
- `feat`: 新功能
- `fix`: Bug修复
- `docs`: 文档更新
- `style`: 代码格式化（不影响代码运行的变动）
- `refactor`: 重构（既不是新增功能，也不是修改Bug的代码变动）
- `test`: 增加测试
- `chore`: 构建过程或辅助工具的变动
- `perf`: 性能优化
- `ci`: CI/CD相关变动

**示例**：
```bash
git commit -m "feat(scanner): 添加增量扫描功能"
git commit -m "fix(connection): 修复连接池内存泄漏问题"
git commit -m "docs: 更新Docker部署指南"
```

## 🧪 测试指南

### 测试类型

1. **单元测试**: 测试单个函数或类
2. **集成测试**: 测试组件之间的交互
3. **端到端测试**: 测试完整的用户场景

### 编写测试

```python
# 示例：为新功能编写测试
import pytest
from src.scanner.structure_scanner import StructureScanner

class TestStructureScanner:
    @pytest.fixture
    async def scanner(self):
        # 设置测试环境
        pass
    
    async def test_scan_collection_structure(self, scanner):
        # 测试集合结构扫描
        result = await scanner.scan_collection_structure(
            instance_id="test",
            database_name="test_db",
            collection_name="test_collection"
        )
        assert result is not None
        assert "fields" in result
```

### 运行测试

```bash
# 运行所有测试
pytest

# 运行特定测试文件
pytest tests/test_scanner.py

# 运行特定测试函数
pytest tests/test_scanner.py::TestStructureScanner::test_scan_collection_structure

# 生成覆盖率报告
pytest --cov=src --cov-report=html
```

## 📝 代码规范

### Python代码风格

我们使用以下工具确保代码质量：

- **Black**: 代码格式化
- **Flake8**: 代码检查
- **MyPy**: 类型检查
- **isort**: 导入排序

```bash
# 格式化代码
black src/ tests/

# 检查代码风格
flake8 src/ tests/

# 类型检查
mypy src/

# 排序导入
isort src/ tests/
```

### 代码风格指南

1. **命名规范**：
   - 类名：`PascalCase`
   - 函数和变量名：`snake_case`
   - 常量：`UPPER_SNAKE_CASE`
   - 私有成员：以`_`开头

2. **文档字符串**：
   ```python
   def scan_collection_structure(self, instance_id: str, database_name: str, collection_name: str) -> Dict[str, Any]:
       """扫描集合结构
       
       Args:
           instance_id: 实例ID
           database_name: 数据库名称
           collection_name: 集合名称
           
       Returns:
           包含集合结构信息的字典
           
       Raises:
           ConnectionError: 连接失败时抛出
       """
   ```

3. **类型注解**：
   ```python
   from typing import Dict, List, Optional, Any
   
   async def get_databases(self, instance_id: str) -> List[Dict[str, Any]]:
       pass
   ```

## 🔧 添加新功能

### 1. MCP工具开发

如果您要添加新的MCP工具：

```python
# src/mcp_tools/your_new_tool.py
from typing import Dict, Any, List
from mcp.types import Tool, TextContent
from ..database.connection_manager import ConnectionManager

class YourNewTool:
    def __init__(self, connection_manager: ConnectionManager):
        self.connection_manager = connection_manager
    
    def get_tool_definition(self) -> Tool:
        return Tool(
            name="your_new_tool",
            description="您的新工具描述",
            inputSchema={
                "type": "object",
                "properties": {
                    "param1": {
                        "type": "string",
                        "description": "参数1描述"
                    }
                },
                "required": ["param1"]
            }
        )
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        # 实现工具逻辑
        pass
```

### 2. 扫描器扩展

如果您要扩展扫描功能：

```python
# src/scanner/your_scanner.py
class YourScanner:
    def __init__(self, connection_manager, metadata_manager):
        self.connection_manager = connection_manager
        self.metadata_manager = metadata_manager
    
    async def scan_your_feature(self, instance_id: str) -> Dict[str, Any]:
        # 实现扫描逻辑
        pass
```

### 3. 更新配置

如果您的功能需要新的配置选项：

```python
# src/config.py
@dataclass
class YourFeatureConfig:
    enabled: bool = True
    option1: str = "default_value"
    option2: int = 100

@dataclass
class QueryNestConfig:
    # 现有配置...
    your_feature: YourFeatureConfig = field(default_factory=YourFeatureConfig)
```

## 📖 文档贡献

### 文档类型

1. **API文档**: 代码中的文档字符串
2. **用户指南**: README.md和相关文档
3. **开发文档**: 本文档和技术文档
4. **示例代码**: 使用示例和教程

### 文档规范

- 使用清晰、简洁的语言
- 提供实际的代码示例
- 包含必要的截图或图表
- 保持文档与代码同步

## 🐛 报告Bug

### Bug报告模板

请使用以下模板报告Bug：

```markdown
## Bug描述
简要描述Bug的现象

## 复现步骤
1. 执行步骤1
2. 执行步骤2
3. 看到错误

## 期望行为
描述您期望发生的情况

## 实际行为
描述实际发生的情况

## 环境信息
- OS: [例如 Windows 10, Ubuntu 20.04]
- Python版本: [例如 3.9.7]
- QueryNest版本: [例如 1.0.0]
- MongoDB版本: [例如 5.0.3]

## 附加信息
- 错误日志
- 配置文件（删除敏感信息）
- 截图（如果适用）
```

## 💡 功能建议

### 功能建议模板

```markdown
## 功能描述
简要描述建议的功能

## 问题背景
描述这个功能要解决的问题

## 解决方案
描述您建议的解决方案

## 替代方案
描述您考虑过的其他解决方案

## 附加信息
任何其他相关信息
```

## 🔍 代码审查

### 审查清单

在提交PR之前，请确保：

- [ ] 代码遵循项目的编码规范
- [ ] 添加了适当的测试
- [ ] 测试全部通过
- [ ] 更新了相关文档
- [ ] 提交信息遵循约定式提交规范
- [ ] 没有引入破坏性变更（或已在PR中说明）

### PR模板

```markdown
## 变更描述
简要描述这个PR的变更内容

## 变更类型
- [ ] Bug修复
- [ ] 新功能
- [ ] 破坏性变更
- [ ] 文档更新
- [ ] 性能优化
- [ ] 代码重构

## 测试
- [ ] 添加了新的测试
- [ ] 现有测试全部通过
- [ ] 手动测试通过

## 检查清单
- [ ] 代码遵循项目规范
- [ ] 自我审查了代码
- [ ] 添加了必要的注释
- [ ] 更新了文档
- [ ] 没有新的警告

## 相关Issue
关闭 #(issue编号)
```

## 🚀 发布流程

### 版本号规范

我们使用[语义化版本](https://semver.org/)：

- `MAJOR.MINOR.PATCH`
- `MAJOR`: 不兼容的API变更
- `MINOR`: 向后兼容的功能性新增
- `PATCH`: 向后兼容的问题修正

### 发布步骤

1. 更新版本号
2. 更新CHANGELOG.md
3. 创建发布标签
4. 构建和发布包
5. 更新文档

## 🤝 社区

### 沟通渠道

- **GitHub Issues**: 报告Bug和功能建议
- **GitHub Discussions**: 一般讨论和问答
- **Pull Requests**: 代码贡献

### 获取帮助

如果您需要帮助：

1. 查看现有的Issues和Discussions
2. 搜索相关文档
3. 创建新的Issue或Discussion
4. 联系维护者

## 📜 许可证

通过贡献代码，您同意您的贡献将在[MIT许可证](LICENSE)下授权。

## 🙏 致谢

感谢所有为QueryNest项目做出贡献的开发者！

---

再次感谢您的贡献！如果您有任何问题，请随时联系我们。