# 语义库本地文件读写改造技术文档

## 1. 项目概述

### 1.1 改造目标
将QueryNest项目中的语义库相关读写逻辑从数据库存储改为本地文件存储，提高系统的轻量化程度和部署便利性。

### 1.2 当前架构分析

#### 当前语义存储架构
- **元数据库存储**: 通过MetadataManager在元数据库的fields集合中存储语义信息
- **业务库存储**: 在业务数据库中创建`_querynest_semantics`集合作为备选存储
- **双重存储策略**: 优先使用元数据库，失败时降级到业务库

#### 涉及的核心模块
1. **SemanticAnalyzer** (`scanner/semantic_analyzer.py`)
   - 负责字段语义分析
   - 提供语义推断和建议功能
   
2. **UnifiedSemanticTool** (`mcp_tools/unified_semantic_tool.py`)
   - 统一语义操作接口
   - 处理语义的增删改查操作
   
3. **MetadataManager** (`database/metadata_manager.py`)
   - 实际的数据存储层
   - 管理元数据库和业务库的语义存储

## 2. 技术方案设计

### 2.1 文件存储结构设计

```
QueryNest/
├── data/
│   └── semantics/
│       ├── instances/
│       │   ├── {instance_name}/
│       │   │   ├── metadata.json          # 实例元数据
│       │   │   ├── databases/
│       │   │   │   ├── {database_name}/
│       │   │   │   │   ├── metadata.json  # 数据库元数据
│       │   │   │   │   ├── collections/
│       │   │   │   │   │   ├── {collection_name}/
│       │   │   │   │   │   │   ├── metadata.json     # 集合元数据
│       │   │   │   │   │   │   ├── fields.json       # 字段语义信息
│       │   │   │   │   │   │   └── analysis.json     # 分析结果缓存
│       │   │   │   │   │   └── ...
│       │   │   │   │   └── ...
│       │   │   └── query_history.json     # 查询历史
│       │   └── ...
│       ├── global_config.json             # 全局配置
│       └── semantic_patterns.json        # 语义模式库
└── ...
```

### 2.2 数据结构设计

#### 2.2.1 字段语义文件结构 (fields.json)
```json
{
  "collection_name": "users",
  "last_updated": "2024-01-15T10:30:00Z",
  "fields": {
    "user_id": {
      "business_meaning": "用户唯一标识",
      "confidence": 0.95,
      "data_type": "string",
      "examples": ["user_123", "user_456"],
      "analysis_result": {
        "suggested_meaning": "用户ID",
        "reasoning": ["字段名称匹配: user.*id"],
        "suggestions": ["建议使用UUID格式"]
      },
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-15T10:30:00Z",
      "source": "manual" // manual, auto_analysis, confirmed
    }
  }
}
```

#### 2.2.2 实例元数据文件结构 (metadata.json)
```json
{
  "instance_name": "production_mongo",
  "instance_id": "inst_001",
  "environment": "production",
  "connection_info": {
    "host": "localhost",
    "port": 27017
  },
  "created_at": "2024-01-15T10:30:00Z",
  "last_scanned": "2024-01-15T10:30:00Z",
  "scan_status": "completed",
  "statistics": {
    "total_databases": 5,
    "total_collections": 25,
    "total_fields": 150,
    "semantic_coverage": 0.75
  }
}
```

### 2.3 核心类设计

#### 2.3.1 LocalSemanticStorage 类
```python
class LocalSemanticStorage:
    """本地语义存储管理器"""
    
    def __init__(self, base_path: str = "data/semantics"):
        self.base_path = Path(base_path)
        self.ensure_directory_structure()
    
    async def save_field_semantics(self, instance_name: str, database_name: str, 
                                 collection_name: str, field_path: str, 
                                 semantic_info: Dict[str, Any]) -> bool:
        """保存字段语义信息"""
        
    async def get_field_semantics(self, instance_name: str, database_name: str,
                                collection_name: str, field_path: str) -> Optional[Dict[str, Any]]:
        """获取字段语义信息"""
        
    async def search_semantics(self, instance_name: str, search_term: str) -> List[Dict[str, Any]]:
        """搜索语义信息"""
        
    async def batch_save_collection_semantics(self, instance_name: str, database_name: str,
                                            collection_name: str, fields_data: Dict[str, Any]) -> bool:
        """批量保存集合的字段语义"""
```

#### 2.3.2 SemanticFileManager 类
```python
class SemanticFileManager:
    """语义文件管理器"""
    
    def __init__(self, storage: LocalSemanticStorage):
        self.storage = storage
        self.cache = {}  # 内存缓存
        
    async def load_file_with_cache(self, file_path: Path) -> Dict[str, Any]:
        """带缓存的文件加载"""
        
    async def save_file_atomic(self, file_path: Path, data: Dict[str, Any]) -> bool:
        """原子性文件保存"""
        
    def invalidate_cache(self, pattern: str = None):
        """缓存失效"""
```

## 3. 实施计划

### 3.1 第一阶段：基础设施搭建

#### 3.1.1 创建本地存储模块
- 创建 `storage/local_semantic_storage.py`
- 实现基础的文件读写功能
- 实现目录结构管理

#### 3.1.2 数据迁移工具
- 创建 `tools/migrate_semantics_to_local.py`
- 从现有数据库导出语义数据
- 转换为本地文件格式

### 3.2 第二阶段：核心模块改造

#### 3.2.1 MetadataManager 改造
- 替换数据库操作为文件操作
- 保持接口兼容性
- 添加文件锁机制防止并发冲突

#### 3.2.2 SemanticAnalyzer 适配
- 修改数据读取逻辑
- 优化批量分析性能
- 增加本地缓存机制

#### 3.2.3 UnifiedSemanticTool 更新
- 适配新的存储接口
- 更新错误处理逻辑
- 保持MCP工具接口不变

### 3.3 第三阶段：性能优化和测试

#### 3.3.1 性能优化
- 实现智能缓存策略
- 添加异步文件操作
- 优化大文件处理

#### 3.3.2 测试验证
- 单元测试覆盖
- 集成测试验证
- 性能基准测试

## 4. 技术实现细节

### 4.1 文件操作安全性

#### 4.1.1 原子性写入
```python
async def atomic_write(file_path: Path, data: Dict[str, Any]) -> bool:
    """原子性写入文件"""
    temp_path = file_path.with_suffix('.tmp')
    try:
        async with aiofiles.open(temp_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2))
        
        # 原子性重命名
        temp_path.replace(file_path)
        return True
    except Exception as e:
        if temp_path.exists():
            temp_path.unlink()
        raise e
```

#### 4.1.2 文件锁机制
```python
import fcntl

class FileLocker:
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.lock_file = None
    
    async def __aenter__(self):
        lock_path = self.file_path.with_suffix('.lock')
        self.lock_file = open(lock_path, 'w')
        fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.lock_file:
            fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
            self.lock_file.close()
```

### 4.2 缓存策略

#### 4.2.1 LRU缓存实现
```python
from functools import lru_cache
from typing import Optional
import time

class TimedLRUCache:
    def __init__(self, maxsize: int = 128, ttl: int = 300):
        self.maxsize = maxsize
        self.ttl = ttl
        self.cache = {}
        self.timestamps = {}
    
    def get(self, key: str) -> Optional[Any]:
        if key in self.cache:
            if time.time() - self.timestamps[key] < self.ttl:
                return self.cache[key]
            else:
                del self.cache[key]
                del self.timestamps[key]
        return None
    
    def set(self, key: str, value: Any):
        if len(self.cache) >= self.maxsize:
            # 移除最旧的条目
            oldest_key = min(self.timestamps.keys(), key=lambda k: self.timestamps[k])
            del self.cache[oldest_key]
            del self.timestamps[oldest_key]
        
        self.cache[key] = value
        self.timestamps[key] = time.time()
```

### 4.3 搜索优化

#### 4.3.1 索引文件设计
```json
{
  "semantic_index": {
    "用户": [
      {
        "instance": "prod",
        "database": "user_db",
        "collection": "users",
        "field": "user_id",
        "meaning": "用户唯一标识",
        "confidence": 0.95
      }
    ]
  },
  "field_index": {
    "user_id": [
      {
        "instance": "prod",
        "database": "user_db",
        "collection": "users",
        "meaning": "用户唯一标识"
      }
    ]
  },
  "last_updated": "2024-01-15T10:30:00Z"
}
```

## 5. 配置管理

### 5.1 全局配置文件
```json
{
  "storage": {
    "base_path": "data/semantics",
    "backup_enabled": true,
    "backup_interval": 3600,
    "max_backups": 10
  },
  "cache": {
    "enabled": true,
    "max_size": 1000,
    "ttl": 300
  },
  "indexing": {
    "auto_rebuild": true,
    "rebuild_interval": 1800
  },
  "performance": {
    "batch_size": 100,
    "concurrent_operations": 10
  }
}
```

## 6. 兼容性和迁移

### 6.1 向后兼容
- 保持现有API接口不变
- 提供数据库到文件的平滑迁移
- 支持混合模式运行（过渡期）

### 6.2 迁移策略
1. **数据导出**: 从现有数据库导出所有语义数据
2. **格式转换**: 转换为新的文件格式
3. **验证测试**: 确保数据完整性
4. **切换部署**: 逐步切换到文件存储
5. **清理优化**: 移除数据库依赖

## 7. 监控和维护

### 7.1 健康检查
- 文件系统空间监控
- 文件完整性检查
- 性能指标监控

### 7.2 备份策略
- 定期自动备份
- 增量备份支持
- 备份文件压缩

## 8. 风险评估

### 8.1 技术风险
- **文件系统性能**: 大量小文件可能影响性能
- **并发安全**: 多进程访问需要文件锁
- **数据一致性**: 需要事务性操作支持

### 8.2 缓解措施
- 实现文件合并策略减少文件数量
- 使用文件锁和原子操作保证安全性
- 实现数据校验和恢复机制

## 9. 预期收益

### 9.1 部署简化
- 减少数据库依赖
- 简化配置管理
- 提高系统可移植性

### 9.2 性能提升
- 减少网络延迟
- 提高读取速度
- 降低系统复杂度

### 9.3 维护便利
- 数据可视化管理
- 简化备份恢复
- 便于版本控制

## 10. 总结

本技术文档详细规划了将QueryNest语义库从数据库存储迁移到本地文件存储的完整方案。通过分阶段实施，可以在保证系统稳定性的前提下，实现存储架构的平滑升级，提升系统的轻量化程度和部署便利性。