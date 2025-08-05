# 语义库写入场景分析与补充方案

## 当前已实现的语义写入场景

### 1. 自动语义分析写入
**位置**: `scanner/semantic_analyzer.py:328-334`
**触发条件**: 置信度 > 0.6
**写入时机**: 集合结构扫描期间
```python
if analysis["confidence"] > 0.6 and analysis["suggested_meaning"]:
    success = await self.metadata_manager.update_field_semantics(
        instance_id, database_name, collection_name, field_path,
        analysis["suggested_meaning"]
    )
```

### 2. 手动语义管理写入
**位置**: `mcp_tools/semantic_management.py:145`
**触发条件**: 用户主动更新
**写入时机**: MCP工具调用时

### 3. 语义确认写入
**位置**: `mcp_tools/semantic_completion.py:445`
**触发条件**: 用户确认建议语义
**写入时机**: 用户确认操作时

## 缺失的关键语义写入场景

### 1. 查询执行后的用户反馈场景 ❌
**问题**: 用户执行查询后，发现结果不符合预期，需要纠正字段语义
**场景**: 
- 用户执行查询得到错误结果
- 用户通过反馈指出字段理解错误
- 系统应自动更新相关字段语义

### 2. 查询历史学习场景 ❌
**问题**: 系统未从成功的查询历史中学习语义
**场景**:
- 用户多次成功查询某个字段
- 查询模式显示字段的真实用途
- 系统应从查询模式中推断并更新语义

### 3. 跨集合语义关联场景 ❌
**问题**: 发现相似字段但未自动关联语义
**场景**:
- 在不同集合中发现相似名称/类型的字段
- 已知字段A的语义，新发现字段B与A相似
- 系统应建议或自动关联语义

### 4. 增量语义补充场景 ❌ 
**问题**: 新增字段或数据变化时，语义未及时更新
**场景**:
- 数据库结构发生变化，新增字段
- 现有字段数据类型或内容发生重大变化
- 系统应主动分析并更新语义

### 5. 用户交互式语义确认场景 ❌
**问题**: 缺乏友好的语义确认流程
**场景**:
- 系统对字段语义不确定（置信度中等）
- 需要用户确认或选择语义含义
- 提供多个选项让用户选择

## 补充方案设计

### 方案1: 查询反馈语义学习
```python
# 在 mcp_tools/feedback_tools.py 中添加
async def update_semantics_from_feedback(self, feedback_data):
    """根据用户反馈更新字段语义"""
    if feedback_data.get("semantic_correction"):
        field_path = feedback_data.get("field_path")
        corrected_meaning = feedback_data.get("corrected_meaning")
        
        success = await self.metadata_manager.update_field_semantics(
            instance_id, database_name, collection_name, 
            field_path, corrected_meaning
        )
        
        # 记录反馈学习历史
        await self._record_semantic_learning(feedback_data)
```

### 方案2: 查询历史语义挖掘
```python
# 在 database/metadata_manager.py 中添加
async def learn_semantics_from_query_history(self, instance_id: str):
    """从查询历史中学习字段语义"""
    # 分析查询模式
    query_patterns = await self._analyze_query_patterns(instance_id)
    
    for pattern in query_patterns:
        if pattern["confidence"] > 0.7:
            # 更新字段语义
            await self.update_field_semantics(
                pattern["instance_id"], pattern["database_name"],
                pattern["collection_name"], pattern["field_path"],
                pattern["inferred_meaning"]
            )
```

### 方案3: 交互式语义确认工具
```python
# 新增 mcp_tools/semantic_confirmation.py
class SemanticConfirmationTool(BaseMCPTool):
    """语义确认交互工具"""
    
    async def get_pending_confirmations(self, instance_id: str):
        """获取需要用户确认的语义项"""
        # 查找置信度中等(0.3-0.6)的语义分析结果
        pending_items = await self._get_uncertain_semantics(instance_id)
        return pending_items
    
    async def confirm_semantics_batch(self, confirmations: List[Dict]):
        """批量确认语义"""
        for confirmation in confirmations:
            await self.metadata_manager.update_field_semantics(
                confirmation["instance_id"],
                confirmation["database_name"], 
                confirmation["collection_name"],
                confirmation["field_path"],
                confirmation["confirmed_meaning"]
            )
```

### 方案4: 增量语义更新服务
```python
# 新增 services/semantic_update_service.py
class SemanticUpdateService:
    """语义增量更新服务"""
    
    async def check_for_schema_changes(self, instance_id: str):
        """检查数据库结构变化"""
        changes = await self._detect_schema_changes(instance_id)
        
        for change in changes:
            if change["type"] == "new_field":
                # 分析新字段语义
                analysis = await self.semantic_analyzer.analyze_field_semantics(
                    change["instance_id"], change["database_name"],
                    change["collection_name"], change["field_path"],
                    change["field_info"]
                )
                
                # 自动更新或标记为待确认
                if analysis["confidence"] > 0.6:
                    await self._auto_update_semantics(change, analysis)
                else:
                    await self._mark_for_confirmation(change, analysis)
```

## 实施优先级

### 高优先级 🔴
1. **查询反馈语义学习** - 直接影响用户体验
2. **交互式语义确认工具** - 提升语义准确性

### 中优先级 🟡  
3. **查询历史语义挖掘** - 被动学习提升
4. **增量语义更新服务** - 保持数据同步

### 低优先级 🟢
5. **跨集合语义关联** - 智能化增强

## 技术实现要点

### 1. 语义写入时机优化
- 在查询执行后添加反馈收集点
- 在用户反馈中增加语义纠错选项
- 定期触发语义挖掘任务

### 2. 置信度阈值调整
- 当前自动写入阈值：0.6
- 建议增加中等置信度处理：0.3-0.6 (待确认)
- 低置信度处理：< 0.3 (标记为未知)

### 3. 语义版本管理
- 记录语义变更历史
- 支持语义回滚操作
- 跟踪语义来源（自动/手动/反馈）

### 4. 性能考虑
- 异步处理语义更新
- 批量处理语义分析
- 缓存常用语义查询结果