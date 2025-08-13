# -*- coding: utf-8 -*-
"""
工作流状态序列化器

提供工作流状态的高级序列化和反序列化功能，支持版本控制和格式转换
"""

import json
from typing import Dict, Any, Optional, Union, List, Type
from datetime import datetime
import structlog
from enum import Enum

# 导入工作流状态相关类
from utils.workflow_state import WorkflowState, WorkflowStage, WorkflowTransition

logger = structlog.get_logger(__name__)


class SerializationFormat(Enum):
    """序列化格式类型"""
    JSON = "json"           # JSON格式
    COMPACT_JSON = "compact_json"  # 压缩的JSON格式
    MSGPACK = "msgpack"     # MessagePack二进制格式
    BSON = "bson"           # BSON格式(MongoDB使用的格式)


class WorkflowStateSerializer:
    """工作流状态序列化器"""
    
    VERSION = "1.0.0"  # 序列化器版本
    
    @classmethod
    def serialize(cls, state: WorkflowState, 
                 format_type: SerializationFormat = SerializationFormat.JSON) -> Union[str, bytes]:
        """
        序列化工作流状态
        
        Args:
            state: 工作流状态对象
            format_type: 序列化格式类型
            
        Returns:
            序列化后的字符串或字节数据
        """
        try:
            # 转换为标准字典
            data = cls._state_to_dict(state)
            
            # 根据格式类型序列化
            if format_type == SerializationFormat.JSON:
                return json.dumps(data, ensure_ascii=False, indent=2)
                
            elif format_type == SerializationFormat.COMPACT_JSON:
                return json.dumps(data, ensure_ascii=False, separators=(',', ':'))
                
            elif format_type == SerializationFormat.MSGPACK:
                try:
                    import msgpack
                    return msgpack.packb(data)
                except ImportError:
                    logger.warning("MessagePack库未安装，回退到JSON格式")
                    return json.dumps(data, ensure_ascii=False)
                    
            elif format_type == SerializationFormat.BSON:
                try:
                    import bson
                    return bson.encode(data)
                except ImportError:
                    logger.warning("BSON库未安装，回退到JSON格式")
                    return json.dumps(data, ensure_ascii=False)
                
            else:
                logger.warning(f"未知的序列化格式: {format_type}，使用默认JSON格式")
                return json.dumps(data, ensure_ascii=False)
                
        except Exception as e:
            logger.error("工作流状态序列化失败", error=str(e))
            raise
    
    @classmethod
    def deserialize(cls, data: Union[str, bytes, Dict[str, Any]], 
                   format_type: Optional[SerializationFormat] = None) -> WorkflowState:
        """
        反序列化工作流状态
        
        Args:
            data: 序列化后的数据
            format_type: 序列化格式类型，如果为None则自动检测
            
        Returns:
            工作流状态对象
        """
        try:
            # 如果输入是字典，直接使用
            if isinstance(data, dict):
                return cls._dict_to_state(data)
                
            # 自动检测格式
            if format_type is None:
                format_type = cls._detect_format(data)
            
            # 解析不同格式
            parsed_data = None
            
            if format_type == SerializationFormat.JSON or format_type == SerializationFormat.COMPACT_JSON:
                if isinstance(data, bytes):
                    data = data.decode('utf-8')
                parsed_data = json.loads(data)
                
            elif format_type == SerializationFormat.MSGPACK:
                try:
                    import msgpack
                    parsed_data = msgpack.unpackb(data)
                except ImportError:
                    logger.error("MessagePack库未安装，无法解析")
                    raise ImportError("MessagePack库未安装")
                    
            elif format_type == SerializationFormat.BSON:
                try:
                    import bson
                    parsed_data = bson.decode(data)
                except ImportError:
                    logger.error("BSON库未安装，无法解析")
                    raise ImportError("BSON库未安装")
            
            if parsed_data is None:
                raise ValueError("无法解析数据")
                
            # 转换为工作流状态对象
            return cls._dict_to_state(parsed_data)
                
        except Exception as e:
            logger.error("工作流状态反序列化失败", error=str(e))
            raise
    
    @classmethod
    def _detect_format(cls, data: Union[str, bytes]) -> SerializationFormat:
        """
        自动检测序列化格式
        
        Args:
            data: 序列化后的数据
            
        Returns:
            序列化格式类型
        """
        # 如果是字符串，尝试JSON解析
        if isinstance(data, str):
            return SerializationFormat.JSON
            
        # 如果是字节，检查特征
        elif isinstance(data, bytes):
            # BSON格式的前4个字节表示文档长度
            if len(data) >= 4:
                try:
                    import bson
                    bson.decode(data)
                    return SerializationFormat.BSON
                except (ImportError, Exception):
                    pass
                
            # 尝试解析为MessagePack
            try:
                import msgpack
                msgpack.unpackb(data)
                return SerializationFormat.MSGPACK
            except (ImportError, Exception):
                pass
                
            # 尝试解析为JSON
            try:
                json.loads(data.decode('utf-8'))
                return SerializationFormat.JSON
            except Exception:
                pass
        
        # 默认假设为JSON
        return SerializationFormat.JSON
    
    @classmethod
    def _state_to_dict(cls, state: WorkflowState) -> Dict[str, Any]:
        """
        将工作流状态对象转换为字典
        
        Args:
            state: 工作流状态对象
            
        Returns:
            包含所有状态信息的字典
        """
        # 获取基础字典
        data = state.to_dict()
        
        # 添加序列化元数据
        data['_serializer'] = {
            'version': cls.VERSION,
            'format': 'standard',
            'serialized_at': datetime.now().isoformat(),
        }
        
        return data
    
    @classmethod
    def _dict_to_state(cls, data: Dict[str, Any]) -> WorkflowState:
        """
        将字典转换为工作流状态对象
        
        Args:
            data: 包含状态信息的字典
            
        Returns:
            工作流状态对象
        """
        # 记录序列化版本
        serializer_info = data.pop('_serializer', {'version': '1.0.0', 'format': 'standard'})
        logger.debug("反序列化工作流状态", serializer_version=serializer_info.get('version'))
        
        # 移除序列化元数据，确保不会干扰WorkflowState构建
        if '_serializer' in data:
            del data['_serializer']
            
        # 使用WorkflowState的from_dict方法
        return WorkflowState.from_dict(data)
    
    @classmethod
    def convert_format(cls, data: Union[str, bytes], 
                      source_format: SerializationFormat,
                      target_format: SerializationFormat) -> Union[str, bytes]:
        """
        转换序列化格式
        
        Args:
            data: 源格式的序列化数据
            source_format: 源序列化格式
            target_format: 目标序列化格式
            
        Returns:
            目标格式的序列化数据
        """
        # 先反序列化，再重新序列化为目标格式
        state = cls.deserialize(data, source_format)
        return cls.serialize(state, target_format)
    
    @classmethod
    def validate(cls, data: Union[str, bytes, Dict[str, Any]], 
                format_type: Optional[SerializationFormat] = None) -> bool:
        """
        验证序列化数据是否有效
        
        Args:
            data: 序列化数据
            format_type: 序列化格式类型，如果为None则自动检测
            
        Returns:
            是否为有效的序列化数据
        """
        try:
            cls.deserialize(data, format_type)
            return True
        except Exception:
            return False