#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test script to verify the fix for workflow transitions
"""

import asyncio
import structlog
from database.connection_manager import ConnectionManager
from database.metadata_manager_file import FileBasedMetadataManager
from utils.workflow_manager import get_workflow_manager, WorkflowStage

logger = structlog.get_logger(__name__)

async def test_search_fields_by_meaning():
    """Test that the search_fields_by_meaning method works in FileBasedMetadataManager"""
    # Initialize the connection manager
    conn_manager = ConnectionManager()
    await conn_manager.initialize()
    
    # Initialize the file-based metadata manager
    metadata_manager = FileBasedMetadataManager(conn_manager)
    await metadata_manager.initialize()
    
    # Try to call the search_fields_by_meaning method
    try:
        results = await metadata_manager.search_fields_by_meaning("test_instance", "test_term")
        print("Method call succeeded")
        print(f"Results: {results}")
        return True
    except Exception as e:
        print(f"Method call failed: {e}")
        return False

async def test_workflow_transition():
    """Test that workflow transitions work properly"""
    # Get the workflow manager
    workflow_manager = get_workflow_manager()
    
    # Reset workflow state
    session_id = "test_session"
    await workflow_manager.reset_workflow(session_id)
    
    # Set initial data for instance selection
    await workflow_manager.update_workflow_data(session_id, {"instance_id": "test_instance"})
    
    # Try to advance to database selection
    success = await workflow_manager.try_advance_to_stage(session_id, WorkflowStage.DATABASE_SELECTION)
    
    print(f"Transition to DATABASE_SELECTION: {'succeeded' if success else 'failed'}")
    
    # Get current stage
    stage_info = await workflow_manager.get_current_stage_info(session_id)
    current_stage = stage_info.get('stage_name', 'Unknown')
    
    print(f"Current stage: {current_stage}")
    return success

async def main():
    print("Testing search_fields_by_meaning method...")
    method_result = await test_search_fields_by_meaning()
    
    print("\nTesting workflow transition...")
    transition_result = await test_workflow_transition()
    
    if method_result and transition_result:
        print("\nAll tests passed! The fix works correctly.")
    else:
        print("\nTests failed. The fix is incomplete or there are additional issues.")

if __name__ == "__main__":
    asyncio.run(main())