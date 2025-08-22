# -*- coding: utf-8 -*-
"""
工作流状态定义

提供增强的工作流状态数据模型和序列化支持
"""

from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field
from enum import Enum
import json
from datetime import datetime
import copy
import structlog

logger = structlog.get_logger(__name__)


class WorkflowStage(Enum):
    """精简的工作流阶段枚举"""
    INIT = "init"                           # 初始化
    INSTANCE_ANALYSIS = "instance_analysis" # 发现和分析实例
    INSTANCE_SELECTION = "instance_selection" # 选择实例
    DATABASE_ANALYSIS = "database_analysis" # 发现和分析数据库
    DATABASE_SELECTION = "database_selection" # 选择数据库
    COLLECTION_ANALYSIS = "collection_analysis" # 发现和分析集合
    COLLECTION_SELECTION = "collection_selection" # 选择集合
    FIELD_ANALYSIS = "field_analysis"       # 分析字段
    QUERY_GENERATION = "query_generation"   # 生成查询
    QUERY_REFINEMENT = "query_refinement"   # 查询优化
    QUERY_EXECUTION = "query_execution"     # 执行查询
    RESULT_PRESENTATION = "result_presentation" # 结果展示
    COMPLETED = "completed"                 # 完成


class WorkflowTransition(Enum):
    """工作流转换类型"""
    NEXT = "next"           # 进入下一阶段
    BACK = "back"           # 返回上一阶段
    RETRY = "retry"         # 重试当前阶段
    JUMP = "jump"           # 跳转到指定阶段
    RESET = "reset"         # 重置工作流


@dataclass
class WorkflowState:
    """
    工作流状态
    
    增强版的工作流状态类，提供更强大的序列化和版本控制能力
    """
    current_stage: WorkflowStage
    session_id: str
    instance_id: Optional[str] = None
    database_name: Optional[str] = None
    collection_name: Optional[str] = None
    query_description: Optional[str] = None
    generated_query: Optional[Dict[str, Any]] = None
    refinement_count: int = 0
    max_refinements: int = 5
    stage_data: Dict[str, Any] = field(default_factory=dict)
    stage_history: List[WorkflowStage] = field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    # 新增字段
    version: str = "1.0.0"
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """初始化后处理"""
        if self.created_at is None:
            self.created_at = datetime.now()
        self.updated_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典格式
        
        增强版的序列化方法，包括版本号和完整的元数据
        """
        return {
            # 版本信息
            'version': self.version,
            
            # 核心状态信息
            'current_stage': self.current_stage.value,
            'session_id': self.session_id,
            'instance_id': self.instance_id,
            'database_name': self.database_name,
            'collection_name': self.collection_name,
            'query_description': self.query_description,
            'generated_query': self.generated_query,
            'refinement_count': self.refinement_count,
            'max_refinements': self.max_refinements,
            
            # 状态数据和历史
            'stage_data': self.stage_data,
            'stage_history': [stage.value for stage in self.stage_history],
            
            # 时间戳
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            
            # 附加信息
            'tags': self.tags,
            'metadata': self.metadata
        }
    
    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkflowState':
        """
        从字典创建工作流状态
        
        增强版的反序列化方法，支持版本检查和兼容性处理
        """
        # 检查版本兼容性
        version = data.get('version', '1.0.0')
        
        # 处理不同版本的数据格式
        if version != cls.version:
            logger.info(f"工作流状态版本不匹配: 存储={version}, 当前={cls.version}，将尝试转换")
            data = cls._convert_from_version(data, version)
        
        # 转换枚举值
        current_stage = WorkflowStage(data['current_stage'])
        stage_history = [WorkflowStage(stage) for stage in data.get('stage_history', [])]
        
        # 处理日期时间
        created_at = None
        if data.get('created_at'):
            try:
                created_at = datetime.fromisoformat(data['created_at'])
            except ValueError:
                logger.warning(f"无法解析created_at: {data['created_at']}")
                created_at = datetime.now()
        
        updated_at = None
        if data.get('updated_at'):
            try:
                updated_at = datetime.fromisoformat(data['updated_at'])
            except ValueError:
                logger.warning(f"无法解析updated_at: {data['updated_at']}")
                updated_at = datetime.now()
        
        # 提取核心字段
        state = cls(
            current_stage=current_stage,
            session_id=data['session_id'],
            instance_id=data.get('instance_id'),
            database_name=data.get('database_name'),
            collection_name=data.get('collection_name'),
            query_description=data.get('query_description'),
            generated_query=data.get('generated_query'),
            refinement_count=data.get('refinement_count', 0),
            max_refinements=data.get('max_refinements', 5),
            stage_data=data.get('stage_data', {}),
            stage_history=stage_history,
            created_at=created_at,
            updated_at=updated_at,
            version=version,
            tags=data.get('tags', []),
            metadata=data.get('metadata', {})
        )
        
        return state
    
    @classmethod
    def from_json(cls, json_str: str) -> 'WorkflowState':
        """从JSON字符串创建工作流状态"""
        data = json.loads(json_str)
        return cls.from_dict(data)
    
    @staticmethod
    def _convert_from_version(data: Dict[str, Any], from_version: str) -> Dict[str, Any]:
        """从指定版本转换数据格式"""
        result = copy.deepcopy(data)
        
        # 默认版本号
        if from_version == "1.0.0" or not from_version:
            # 添加新字段默认值
            if 'tags' not in result:
                result['tags'] = []
            if 'metadata' not in result:
                result['metadata'] = {}
            result['version'] = "1.0.0"
        # 其他版本转换...
        
        return result
    
    def update_metadata(self, key: str, value: Any) -> None:
        """更新元数据"""
        self.metadata[key] = value
        self.updated_at = datetime.now()
    
    def update_stage_data(self, key: str, value: Any) -> None:
        """更新阶段数据"""
        self.stage_data[key] = value
        self.updated_at = datetime.now()
    
    def add_tag(self, tag: str) -> None:
        """添加标签"""
        if tag not in self.tags:
            self.tags.append(tag)
            self.updated_at = datetime.now()
    
    def remove_tag(self, tag: str) -> None:
        """移除标签"""
        if tag in self.tags:
            self.tags.remove(tag)
            self.updated_at = datetime.now()
    
    def add_to_history(self, stage: Union[WorkflowStage, str]) -> None:
        """添加阶段到历史记录"""
        if isinstance(stage, str):
            stage = WorkflowStage(stage)
        self.stage_history.append(stage)
        self.updated_at = datetime.now()
    
    def clone(self) -> 'WorkflowState':
        """克隆工作流状态"""
        return WorkflowState.from_dict(self.to_dict())
    
    def __str__(self) -> str:
        """字符串表示"""
        return (
            f"WorkflowState(session={self.session_id}, "
            f"stage={self.current_stage.value}, "
            f"instance={self.instance_id or '-'}, "
            f"db={self.database_name or '-'}, "
            f"collection={self.collection_name or '-'}, "
            f"history_len={len(self.stage_history)})"
        )