# -*- coding: utf-8 -*-
"""
工作流管理器单元测试
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from utils.workflow_manager import (
    WorkflowManager, WorkflowState, WorkflowStage, 
    setup_workflow_manager
)
from storage.workflow_state_storage import WorkflowStateStorage


class MockStorage:
    """模拟存储类"""
    
    def __init__(self):
        self.states = {}
    
    async def save_workflow_state(self, workflow_state):
        # 深拷贝工作流状态以避免引用问题
        from utils.workflow_manager import WorkflowState
        self.states[workflow_state.session_id] = WorkflowState.from_dict(workflow_state.to_dict())
        return True
    
    async def load_workflow_state(self, session_id):
        return self.states.get(session_id)
    
    async def delete_workflow_state(self, session_id):
        if session_id in self.states:
            del self.states[session_id]
            return True
        return False
    
    async def list_sessions(self):
        return [{"session_id": sid} for sid in self.states.keys()]
    
    async def cleanup_old_sessions(self, days):
        return 0
    
    async def backup_all_sessions(self):
        return len(self.states)


class TestWorkflowManager:
    """工作流管理器测试类"""
    
    def setup_method(self):
        """测试前准备"""
        self.mock_storage = MockStorage()
        self.workflow_manager = WorkflowManager(storage=self.mock_storage)
        self.session_id = "test_session_001"
    
    @pytest.mark.asyncio
    async def test_create_workflow(self):
        """测试创建工作流"""
        workflow = await self.workflow_manager.create_workflow(self.session_id)
        
        assert workflow is not None
        assert workflow.session_id == self.session_id
        assert workflow.current_stage == WorkflowStage.INIT
        assert isinstance(workflow.created_at, datetime)
        
        # 检查是否保存到存储
        assert self.session_id in self.mock_storage.states
    
    @pytest.mark.asyncio
    async def test_get_workflow(self):
        """测试获取工作流"""
        # 创建工作流
        created_workflow = await self.workflow_manager.create_workflow(self.session_id)
        
        # 获取工作流
        retrieved_workflow = await self.workflow_manager.get_workflow(self.session_id)
        
        assert retrieved_workflow is not None
        assert retrieved_workflow.session_id == created_workflow.session_id
        assert retrieved_workflow.current_stage == created_workflow.current_stage
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_workflow(self):
        """测试获取不存在的工作流"""
        workflow = await self.workflow_manager.get_workflow("nonexistent")
        assert workflow is None
    
    @pytest.mark.asyncio
    async def test_get_or_create_workflow(self):
        """测试获取或创建工作流"""
        # 第一次调用应该创建新工作流
        workflow1 = await self.workflow_manager.get_or_create_workflow(self.session_id)
        assert workflow1 is not None
        assert workflow1.current_stage == WorkflowStage.INIT
        
        # 第二次调用应该返回相同的工作流
        workflow2 = await self.workflow_manager.get_or_create_workflow(self.session_id)
        assert workflow2.session_id == workflow1.session_id
    
    @pytest.mark.asyncio
    async def test_can_transition_to(self):
        """测试阶段转换验证"""
        workflow = await self.workflow_manager.create_workflow(self.session_id)
        
        # 从INIT阶段可以转换到INSTANCE_DISCOVERY
        can_transition, message = await self.workflow_manager.can_transition_to(
            self.session_id, WorkflowStage.INSTANCE_DISCOVERY
        )
        assert can_transition is True
        
        # 从INIT阶段不能直接转换到QUERY_GENERATION
        can_transition, message = await self.workflow_manager.can_transition_to(
            self.session_id, WorkflowStage.QUERY_GENERATION
        )
        assert can_transition is False
        assert "不能从" in message
    
    @pytest.mark.asyncio
    async def test_transition_to(self):
        """测试阶段转换"""
        workflow = await self.workflow_manager.create_workflow(self.session_id)
        
        # 转换到INSTANCE_DISCOVERY阶段
        success, message = await self.workflow_manager.transition_to(
            self.session_id, WorkflowStage.INSTANCE_DISCOVERY
        )
        
        assert success is True
        assert "已转换到" in message
        
        # 验证工作流状态已更新
        updated_workflow = await self.workflow_manager.get_workflow(self.session_id)
        assert updated_workflow.current_stage == WorkflowStage.INSTANCE_DISCOVERY
        assert len(updated_workflow.stage_history) == 1
        assert updated_workflow.stage_history[0] == WorkflowStage.INIT
    
    @pytest.mark.asyncio
    async def test_transition_with_data(self):
        """测试带数据的阶段转换"""
        workflow = await self.workflow_manager.create_workflow(self.session_id)
        
        # 转换并更新数据
        update_data = {"instance_id": "test_instance"}
        success, message = await self.workflow_manager.transition_to(
            self.session_id, WorkflowStage.INSTANCE_DISCOVERY, update_data
        )
        
        assert success is True
        
        # 验证数据已更新
        updated_workflow = await self.workflow_manager.get_workflow(self.session_id)
        assert updated_workflow.instance_id == "test_instance"
    
    @pytest.mark.asyncio
    async def test_delete_workflow(self):
        """测试删除工作流"""
        # 创建工作流
        await self.workflow_manager.create_workflow(self.session_id)
        
        # 验证工作流存在
        workflow = await self.workflow_manager.get_workflow(self.session_id)
        assert workflow is not None
        
        # 删除工作流
        success = await self.workflow_manager.delete_workflow(self.session_id)
        assert success is True
        
        # 验证工作流已被删除
        workflow = await self.workflow_manager.get_workflow(self.session_id)
        assert workflow is None
        assert self.session_id not in self.mock_storage.states
    
    @pytest.mark.asyncio
    async def test_list_all_workflows(self):
        """测试列出所有工作流"""
        # 创建多个工作流
        await self.workflow_manager.create_workflow("session1")
        await self.workflow_manager.create_workflow("session2")
        
        # 列出工作流
        workflows = await self.workflow_manager.list_all_workflows()
        
        assert len(workflows) == 2
        session_ids = [w["session_id"] for w in workflows]
        assert "session1" in session_ids
        assert "session2" in session_ids
    
    @pytest.mark.asyncio
    async def test_cleanup_expired_workflows(self):
        """测试清理过期工作流"""
        # 创建工作流
        workflow = await self.workflow_manager.create_workflow(self.session_id)
        
        # 模拟过期时间
        workflow.updated_at = datetime.now() - timedelta(hours=25)
        self.workflow_manager._workflows[self.session_id] = workflow
        
        # 清理过期工作流
        cleaned_count = await self.workflow_manager.cleanup_expired_workflows(24)
        
        assert cleaned_count >= 1
        # 验证过期工作流已从缓存中移除
        assert self.session_id not in self.workflow_manager._workflows
    
    @pytest.mark.asyncio
    async def test_backup_all_workflows(self):
        """测试备份所有工作流"""
        # 创建工作流
        await self.workflow_manager.create_workflow("session1")
        await self.workflow_manager.create_workflow("session2")
        
        # 备份工作流
        success = await self.workflow_manager.backup_all_workflows()
        assert success is True
    
    def test_set_storage(self):
        """测试设置存储"""
        new_storage = MockStorage()
        manager = WorkflowManager()
        
        manager.set_storage(new_storage)
        assert manager.storage == new_storage
    
    @pytest.mark.asyncio
    async def test_workflow_persistence(self):
        """测试工作流持久化"""
        # 创建工作流管理器，不带存储
        manager_without_storage = WorkflowManager(storage=None)
        
        # 创建工作流
        workflow1 = await manager_without_storage.create_workflow("test1")
        assert workflow1 is not None
        
        # 创建带存储的管理器
        manager_with_storage = WorkflowManager(storage=self.mock_storage)
        
        # 创建工作流
        workflow2 = await manager_with_storage.create_workflow("test2")
        
        # 验证存储中有数据
        assert "test2" in self.mock_storage.states
        assert "test1" not in self.mock_storage.states
    
    @pytest.mark.asyncio
    async def test_workflow_from_storage_recovery(self):
        """测试从存储恢复工作流"""
        # 直接在存储中创建工作流状态
        workflow_state = WorkflowState(
            current_stage=WorkflowStage.DATABASE_SELECTION,
            session_id="recovery_test"
        )
        workflow_state.instance_id = "test_instance"
        workflow_state.database_name = "test_db"
        
        await self.mock_storage.save_workflow_state(workflow_state)
        
        # 从工作流管理器获取（应该从存储加载）
        recovered_workflow = await self.workflow_manager.get_workflow("recovery_test")
        
        assert recovered_workflow is not None
        assert recovered_workflow.session_id == "recovery_test"
        assert recovered_workflow.current_stage == WorkflowStage.DATABASE_SELECTION
        assert recovered_workflow.instance_id == "test_instance"
        assert recovered_workflow.database_name == "test_db"


class TestWorkflowState:
    """工作流状态测试类"""
    
    def test_workflow_state_creation(self):
        """测试工作流状态创建"""
        state = WorkflowState(
            current_stage=WorkflowStage.INIT,
            session_id="test_session"
        )
        
        assert state.session_id == "test_session"
        assert state.current_stage == WorkflowStage.INIT
        assert isinstance(state.created_at, datetime)
        assert isinstance(state.updated_at, datetime)
        assert state.stage_data == {}
        assert state.stage_history == []
    
    def test_workflow_state_to_dict(self):
        """测试工作流状态序列化"""
        state = WorkflowState(
            current_stage=WorkflowStage.DATABASE_SELECTION,
            session_id="test_session"
        )
        state.instance_id = "test_instance"
        state.database_name = "test_db"
        
        state_dict = state.to_dict()
        
        assert state_dict["session_id"] == "test_session"
        assert state_dict["current_stage"] == WorkflowStage.DATABASE_SELECTION.value
        assert state_dict["instance_id"] == "test_instance"
        assert state_dict["database_name"] == "test_db"
        assert "created_at" in state_dict
        assert "updated_at" in state_dict
    
    def test_workflow_state_from_dict(self):
        """测试工作流状态反序列化"""
        state_data = {
            "current_stage": "database_selection",
            "session_id": "test_session",
            "instance_id": "test_instance",
            "database_name": "test_db",
            "query_description": None,
            "generated_query": None,
            "refinement_count": 0,
            "max_refinements": 5,
            "stage_data": {"key": "value"},
            "stage_history": ["init"],
            "created_at": "2023-01-01T00:00:00",
            "updated_at": "2023-01-01T00:00:00"
        }
        
        state = WorkflowState.from_dict(state_data)
        
        assert state.session_id == "test_session"
        assert state.current_stage == WorkflowStage.DATABASE_SELECTION
        assert state.instance_id == "test_instance"
        assert state.database_name == "test_db"
        assert state.stage_data == {"key": "value"}
        assert len(state.stage_history) == 1


class TestWorkflowIntegration:
    """工作流集成测试"""
    
    def setup_method(self):
        """测试前准备"""
        self.mock_storage = MockStorage()
    
    def test_setup_workflow_manager(self):
        """测试工作流管理器设置"""
        manager = setup_workflow_manager(storage=self.mock_storage)
        
        assert manager is not None
        assert manager.storage == self.mock_storage
    
    @pytest.mark.asyncio
    async def test_full_workflow_cycle(self):
        """测试完整的工作流周期"""
        manager = WorkflowManager(storage=self.mock_storage)
        session_id = "full_cycle_test"
        
        # 1. 创建工作流
        workflow = await manager.create_workflow(session_id)
        assert workflow.current_stage == WorkflowStage.INIT
        
        # 2. 转换到实例发现
        success, _ = await manager.transition_to(
            session_id, WorkflowStage.INSTANCE_DISCOVERY
        )
        assert success is True
        
        # 3. 转换到实例选择，带数据
        success, _ = await manager.transition_to(
            session_id, WorkflowStage.INSTANCE_SELECTION,
            {"instance_id": "prod_instance"}
        )
        assert success is True
        
        # 4. 转换到数据库发现
        success, _ = await manager.transition_to(
            session_id, WorkflowStage.DATABASE_DISCOVERY
        )
        assert success is True
        
        # 5. 验证最终状态
        final_workflow = await manager.get_workflow(session_id)
        assert final_workflow.current_stage == WorkflowStage.DATABASE_DISCOVERY
        assert final_workflow.instance_id == "prod_instance"
        assert len(final_workflow.stage_history) == 3  # INIT -> INSTANCE_DISCOVERY -> INSTANCE_SELECTION
    
    @pytest.mark.asyncio
    async def test_workflow_data_persistence_across_sessions(self):
        """测试跨会话的工作流数据持久化"""
        session_id = "persistence_test"
        
        # 第一个管理器实例
        manager1 = WorkflowManager(storage=self.mock_storage)
        workflow = await manager1.create_workflow(session_id)
        
        # 先转换到 INSTANCE_DISCOVERY，然后再到 INSTANCE_SELECTION
        await manager1.transition_to(session_id, WorkflowStage.INSTANCE_DISCOVERY)
        await manager1.transition_to(
            session_id, WorkflowStage.INSTANCE_SELECTION,
            {"instance_id": "test_instance", "database_name": "test_db"}
        )
        
        # 验证状态已保存到存储
        assert session_id in self.mock_storage.states
        stored_state = self.mock_storage.states[session_id]
        assert stored_state.current_stage == WorkflowStage.INSTANCE_SELECTION
        
        # 第二个管理器实例（模拟重启）
        manager2 = WorkflowManager(storage=self.mock_storage)
        
        # 从存储恢复工作流（不能使用get_or_create_workflow，因为它会创建新的）
        recovered_workflow = await manager2.get_workflow(session_id)
        
        assert recovered_workflow is not None
        assert recovered_workflow.current_stage == WorkflowStage.INSTANCE_SELECTION
        assert recovered_workflow.instance_id == "test_instance"
        assert recovered_workflow.database_name == "test_db"