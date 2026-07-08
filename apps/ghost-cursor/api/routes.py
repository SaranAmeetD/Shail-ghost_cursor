from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from telemetry.storage import (
    get_sessions,
    get_session,
    delete_session,
    bulk_delete_sessions
)
import logging

from models import GuidancePlan
from execution.loop import ExecutionLoop
from execution.adapters.accessibility_bridge_driver import AccessibilityBridgeDriver
from execution.interfaces import OverlayRenderer
from validation.observer import ResultObserver
from telemetry.clicky_telemetry_logger import ClickyTelemetryLogger
from execution.privacy_guard import PrivacyGuard
from fastapi import BackgroundTasks

logger = logging.getLogger(__name__)

router = APIRouter()

active_loop: Optional[ExecutionLoop] = None

class DummyOverlayRenderer(OverlayRenderer):
    def move_to(self, x: int, y: int) -> bool: return True
    def flash(self) -> bool: return True

@router.post("/execute")
def execute_plan(plan: GuidancePlan, background_tasks: BackgroundTasks) -> Dict[str, Any]:
    global active_loop
    driver = AccessibilityBridgeDriver()
    renderer = DummyOverlayRenderer()
    observer = ResultObserver()
    telemetry = ClickyTelemetryLogger()
    privacy_guard = PrivacyGuard()

    active_loop = ExecutionLoop(
        driver=driver,
        renderer=renderer,
        observer=observer,
        telemetry=telemetry,
        privacy_guard=privacy_guard
    )

    background_tasks.add_task(active_loop.run, plan)
    return {"status": "started", "message": "Execution started"}

@router.post("/step-result")
def step_result(payload: Dict[str, Any]) -> Dict[str, Any]:
    # Resume endpoint
    return {"status": "acknowledged"}

@router.post("/abort")
def abort_execution() -> Dict[str, Any]:
    global active_loop
    if active_loop:
        active_loop.cancel()
        return {"status": "aborted"}
    raise HTTPException(status_code=400, detail="No active execution loop to abort.")

@router.get("/sessions")
def list_sessions() -> List[Dict[str, Any]]:
    try:
        return get_sessions()
    except Exception as e:
        logger.error(f"Failed to fetch sessions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch sessions")

@router.get("/sessions/{session_id}")
def get_session_detail(session_id: str) -> Dict[str, Any]:
    try:
        session = get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch session {session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch session")

@router.delete("/sessions/bulk")
def bulk_delete(start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, int]:
    try:
        count = bulk_delete_sessions(start_date, end_date)
        return {"deleted_count": count}
    except Exception as e:
        logger.error(f"Failed to bulk delete sessions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to bulk delete sessions")

@router.delete("/sessions/{session_id}")
def delete_single_session(session_id: str) -> Dict[str, bool]:
    try:
        success = delete_session(session_id)
        if not success:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete session {session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete session")
