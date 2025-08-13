# -*- coding: utf-8 -*-
"""
MCP工具基类

提供通用功能的工具基类实现
"""

from typing import Dict, Any, List, Optional, Union, Type
import inspect
import asyncio
import structlog
from mcp.types import Tool, TextContent

from mcp_tools.interfaces import (
    MCPToolInterface, 
    WorkflowAwareTool,
    ValidationAwareTool,
    ContextAwareTool,
    ErrorHandlingTool,
    DocumentableTool,
    ToolValidationResult
)

logger = structlog.get_logger(__name__)


class BaseTool(MCPToolInterface):
    """基础工具类"""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        
    def get_tool_definition(self) -> Tool:
        """获取工具定义"""
        return Tool(
            name=self.name,
            description=self.description,
            parameters=self._get_parameter_schema()
        )
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """执行工具"""
        # 基本实现，子类应该覆盖此方法
        return [TextContent(
            type="text",
            text=f"工具 {self.name} 的默认实现"
        )]
    
    def _get_parameter_schema(self) -> Dict[str, Any]:
        """获取参数模式"""
        # 默认实现返回空模式
        return {"type": "object", "properties": {}, "required": []}


class BaseWorkflowTool(BaseTool, WorkflowAwareTool):
    """支持工作流的基础工具类"""
    
    def __init__(self, name: str, description: str, workflow_manager=None):
        super().__init__(name, description)
        self.workflow_manager = workflow_manager
        
    async def validate_workflow(self, session_id: str) -> Dict[str, Any]:
        """验证工作流状态"""
        if self.workflow_manager is None:
            # 工作流管理器未注入时返回默认允许状态
            return {
                "can_call": True,
                "message": "工作流管理器未配置，跳过工作流验证",
                "stage_info": {}
            }
            
        can_call, message, stage_info = self.workflow_manager.validate_tool_call(session_id, self.name)
        return {
            "can_call": can_call,
            "message": message,
            "stage_info": stage_info
        }
    
    async def update_workflow(self, session_id: str, arguments: Dict[str, Any], 
                           result: List[TextContent]) -> bool:
        """更新工作流状态"""
        if self.workflow_manager is None:
            # 工作流管理器未注入时直接返回成功
            return True
            
        # 收集需要更新到工作流的数据
        update_data = {}
        
        # 常见字段
        for key in ['instance_id', 'database_name', 'collection_name', 'query_description']:
            if key in arguments and arguments[key]:
                update_data[key] = arguments[key]
        
        # 特殊处理生成的查询
        if self.name == 'generate_query' and len(result) > 0:
            # 尝试从结果中提取生成的查询
            try:
                # 假设查询在第一个TextContent中
                import json
                content = result[0].text
                # 尝试提取JSON块
                import re
                json_matches = re.findall(r'```json\n(.*?)\n```', content, re.DOTALL)
                if json_matches:
                    query_data = json.loads(json_matches[0])
                    update_data['generated_query'] = query_data
            except Exception as e:
                logger.warning("无法从结果中提取查询", error=str(e))
                
        # 更新工作流数据
        if update_data:
            self.workflow_manager.update_workflow_data(session_id, update_data)
            
        return True


class BaseValidationTool(BaseTool, ValidationAwareTool):
    """支持参数验证的基础工具类"""
    
    async def validate_arguments(self, arguments: Dict[str, Any]) -> ToolValidationResult:
        """验证工具参数"""
        # 基本实现，检查必要参数
        schema = self._get_parameter_schema()
        required = schema.get("required", [])
        
        missing = [param for param in required if param not in arguments or arguments[param] is None]
        
        if missing:
            return ToolValidationResult(
                valid=False,
                message=f"缺少必要参数: {', '.join(missing)}",
                suggestions=[f"请提供 {param} 参数" for param in missing]
            )
        
        return ToolValidationResult(valid=True, message="参数验证通过")
    
    async def enhance_arguments(self, arguments: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        """增强工具参数"""
        # 默认实现，子类应覆盖此方法
        return arguments.copy()


class BaseErrorHandlingTool(BaseTool, ErrorHandlingTool):
    """支持错误处理的基础工具类"""
    
    def __init__(self, name: str, description: str, max_retries: int = 3):
        super().__init__(name, description)
        self.max_retries = max_retries
    
    async def handle_error(self, error: Exception, arguments: Dict[str, Any]) -> List[TextContent]:
        """处理错误"""
        logger.error(f"工具 {self.name} 执行失败", error=str(error), arguments=arguments)
        
        error_message = str(error)
        error_type = error.__class__.__name__
        
        return [TextContent(
            type="text",
            text=f"执行失败: {error_type} - {error_message}\n\n请检查参数或稍后重试。"
        )]
    
    async def should_retry(self, error: Exception, attempt: int) -> bool:
        """是否应该重试"""
        # 默认实现：网络错误重试，其他错误不重试
        if attempt >= self.max_retries:
            return False
            
        # 可重试的错误类型
        retriable_errors = [
            'ConnectionError', 
            'TimeoutError',
            'RequestException',
            'TemporaryFailure'
        ]
        
        error_type = error.__class__.__name__
        return any(err_type in error_type for err_type in retriable_errors)
    
    async def get_retry_delay(self, attempt: int) -> float:
        """获取重试延迟（秒）"""
        # 指数退避策略
        return min(2 ** attempt, 30)  # 最多等待30秒
        

class CompleteTool(BaseWorkflowTool, BaseValidationTool, BaseErrorHandlingTool, DocumentableTool):
    """完整功能的工具类"""
    
    def __init__(self, name: str, description: str, workflow_manager=None, max_retries: int = 3):
        # 调用所有父类的初始化方法
        BaseTool.__init__(self, name, description)
        # workflow_manager会在BaseWorkflowTool中使用
        self.workflow_manager = workflow_manager
        self.max_retries = max_retries
        self.docs = ""
        self.examples = []
        
    async def execute(self, arguments: Dict[str, Any], session_id: str = "default") -> List[TextContent]:
        """执行工具，带有完整的工作流验证、参数验证和错误处理"""
        # 工作流验证
        workflow_result = await self.validate_workflow(session_id)
        if not workflow_result["can_call"]:
            return [TextContent(
                type="text",
                text=f"工作流约束错误: {workflow_result['message']}"
            )]
        
        # 参数验证
        validation_result = await self.validate_arguments(arguments)
        if not validation_result.valid:
            return [TextContent(
                type="text",
                text=f"参数验证失败: {validation_result.message}\n\n" + 
                     (f"建议: {'; '.join(validation_result.suggestions)}" if validation_result.suggestions else "")
            )]
        
        # 参数增强
        enhanced_arguments = await self.enhance_arguments(arguments)
        
        # 错误处理和重试
        attempt = 0
        while True:
            try:
                # 执行实际功能
                result = await self._execute_core(enhanced_arguments)
                
                # 更新工作流状态
                await self.update_workflow(session_id, enhanced_arguments, result)
                
                return result
                
            except Exception as e:
                attempt += 1
                should_retry = await self.should_retry(e, attempt)
                
                if should_retry and attempt <= self.max_retries:
                    # 等待并重试
                    retry_delay = await self.get_retry_delay(attempt)
                    logger.info(f"工具 {self.name} 将在 {retry_delay} 秒后重试 (尝试 {attempt}/{self.max_retries})")
                    await asyncio.sleep(retry_delay)
                else:
                    # 不再重试，返回错误
                    return await self.handle_error(e, enhanced_arguments)
    
    async def _execute_core(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """核心执行逻辑，子类应覆盖此方法"""
        # 此方法应由子类实现
        raise NotImplementedError("子类必须实现_execute_core方法")
    
    def get_documentation(self) -> str:
        """获取工具文档"""
        return self.docs or f"{self.name} - {self.description}"
    
    def get_examples(self) -> List[Dict[str, Any]]:
        """获取工具示例"""
        return self.examples