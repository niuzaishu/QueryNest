# 可执行MongoDB查询输出功能使用指南

## 功能概述

QueryNest MCP服务器的`generate_query`工具现在支持多种输出格式，特别是新增的`executable`格式，可以直接返回可在MongoDB shell或客户端中执行的语句。

## 输出格式选项

### 1. executable - 仅可执行语句
返回纯净的、可直接执行的MongoDB查询语句，无额外格式。

**使用场景**：
- 需要将查询语句复制到MongoDB shell
- 集成到其他MongoDB客户端工具
- 自动化脚本中需要查询语句

**示例**：
```javascript
// 输入参数
{
  "instance_id": "production",
  "database_name": "ecommerce", 
  "collection_name": "orders",
  "query_description": "查找今天创建的订单，按金额降序排列",
  "output_format": "executable"
}

// 输出结果
db.orders.find({"created_at":{"$gte":"2025-08-04T00:00:00Z","$lt":"2025-08-05T00:00:00Z"}}).sort({"amount":-1}).limit(100)
```

### 2. query_only - 查询语句+简单格式
返回查询类型说明和格式化的MongoDB语句。

**使用场景**：
- 需要了解查询类型但不需要详细解释
- 快速获取格式化的查询语句
- 简洁的查询展示

**示例**：
```markdown
**查询类型**: FIND

```javascript
db.orders.find({"created_at":{"$gte":"2025-08-04T00:00:00Z","$lt":"2025-08-05T00:00:00Z"}}).sort({"amount":-1}).limit(100)
```
```

### 3. full - 完整格式（默认）
返回完整的查询分析、解释、语义匹配信息和使用建议。

**使用场景**：
- 学习MongoDB查询语法
- 需要详细的查询解释
- 调试和优化查询语句
- 首次使用或复杂查询

## 支持的查询类型

### FIND 查询
```javascript
// 基础查询
db.users.find({"status":"active"})

// 带排序和限制
db.users.find({"status":"active"}).sort({"name":1}).limit(10)

// 复杂条件
db.orders.find({"amount":{"$gte":100,"$lte":500},"status":"completed"}).sort({"created_at":-1}).limit(20)
```

### COUNT 查询
```javascript
// 简单计数
db.users.countDocuments({"status":"active"})

// 复杂条件计数
db.orders.countDocuments({"created_at":{"$gte":"2025-01-01T00:00:00Z"},"status":"completed"})
```

### AGGREGATE 查询
```javascript
// 聚合管道
db.sales.aggregate([{"$match":{"date":{"$gte":"2025-01-01"}}},{"$group":{"_id":"$category","total":{"$sum":"$amount"}}},{"$sort":{"total":-1}}])

// 复杂聚合
db.orders.aggregate([{"$match":{"status":"completed"}},{"$group":{"_id":{"year":{"$year":"$created_at"},"month":{"$month":"$created_at"}},"count":{"$sum":1},"total":{"$sum":"$amount"}}},{"$sort":{"_id.year":1,"_id.month":1}}])
```

### DISTINCT 查询
```javascript
// 简单去重
db.products.distinct("category")

// 带条件去重
db.products.distinct("category", {"status":"available"})
```

## 实际使用示例

### 示例1：电商订单查询
```json
{
  "instance_id": "ecommerce_prod",
  "database_name": "shop", 
  "collection_name": "orders",
  "query_description": "查找最近7天金额大于500元的已完成订单",
  "query_type": "find",
  "limit": 50,
  "output_format": "executable"
}
```

**输出**：
```javascript
db.orders.find({"amount":{"$gte":500},"status":"completed","created_at":{"$gte":"2025-07-28T00:00:00Z"}}).limit(50)
```

### 示例2：用户统计查询
```json
{
  "instance_id": "user_system",
  "database_name": "accounts", 
  "collection_name": "users",
  "query_description": "按注册月份统计用户数量",
  "query_type": "aggregate",
  "output_format": "executable"
}
```

**输出**：
```javascript
db.users.aggregate([{"$group":{"_id":{"year":{"$year":"$created_at"},"month":{"$month":"$created_at"}},"count":{"$sum":1}}},{"$sort":{"_id.year":1,"_id.month":1}}])
```

### 示例3：产品分类查询
```json
{
  "instance_id": "inventory",
  "database_name": "catalog", 
  "collection_name": "products",
  "query_description": "获取所有可用产品的分类列表",
  "query_type": "distinct",
  "output_format": "executable"
}
```

**输出**：
```javascript
db.products.distinct("category", {"status":"available"})
```

## 集成建议

### MongoDB Shell 中使用
直接将executable格式的输出复制粘贴到MongoDB shell中：
```bash
mongo your-database
> db.orders.find({"status":"active"}).limit(10)
```

### Node.js 应用中使用
```javascript
const { MongoClient } = require('mongodb');

// 从QueryNest获取的查询语句：
// db.orders.find({"status":"active"}).sort({"created_at":-1}).limit(10)

// 转换为Node.js代码：
const result = await db.collection('orders')
  .find({"status":"active"})
  .sort({"created_at":-1})
  .limit(10)
  .toArray();
```

### Python/PyMongo 中使用
```python
from pymongo import MongoClient

# 从QueryNest获取的查询语句：
# db.orders.find({"status":"active"}).sort({"created_at":-1}).limit(10)

# 转换为Python代码：
result = list(db.orders.find(
    {"status": "active"}
).sort("created_at", -1).limit(10))
```

## 最佳实践

1. **选择合适的输出格式**：
   - 生产环境集成：使用`executable`格式
   - 开发调试：使用`full`格式
   - 快速验证：使用`query_only`格式

2. **性能考虑**：
   - 大数据集先用count查询确认数量
   - 合理设置limit参数
   - 复杂查询建议添加适当索引

3. **安全注意事项**：
   - 验证查询条件的合理性
   - 敏感数据查询会自动脱敏
   - 只读权限确保数据安全

## 故障排除

### 常见问题

**Q: 输出的查询语句在MongoDB shell中执行失败**
A: 确保MongoDB版本兼容，检查字段名和数据类型是否正确

**Q: 查询结果不符合预期**
A: 使用`full`格式查看详细解释，检查字段映射和条件是否正确

**Q: 无法识别查询意图**
A: 使用更明确的自然语言描述，或指定`query_type`参数

### 获取帮助

如需更多帮助，请：
1. 使用`full`格式获取详细解释
2. 检查CLAUDE.md中的完整文档
3. 查看具体错误信息和日志