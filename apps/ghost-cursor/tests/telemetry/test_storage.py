import pytest
import os
import json
from unittest.mock import patch, MagicMock
from datetime import datetime

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from models import GuidancePlan, GuidancePlanStep
from telemetry.clicky_telemetry_logger import ClickyTelemetryLogger

# Test storage integration using in-memory SQLite DB pool
import apps.shail.db as db_module
import sqlite3
import queue

class MemoryConnectionPool:
    def __init__(self):
        # We share one connection per thread in memory mode using a queue
        self._pool = queue.Queue(1)
        self.db_path = "file:testdb?mode=memory&cache=shared"
        conn = sqlite3.connect(self.db_path, uri=True, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        self._pool.put(conn)

    def get_connection(self):
        try:
            conn = self._pool.get(timeout=1.0)
        except queue.Empty:
            conn = sqlite3.connect(self.db_path, uri=True, timeout=30.0, check_same_thread=False)
            conn.row_factory = sqlite3.Row
        return db_module.PooledConnectionProxy(self, conn)

    def release_connection(self, conn):
        self._pool.put(conn)

    def connection(self):
        from contextlib import contextmanager
        @contextmanager
        def _ctx():
            proxy = self.get_connection()
            try:
                with proxy:
                    yield proxy
            finally:
                proxy.close()
        return _ctx()

@pytest.fixture(autouse=True)
def mock_db():
    # Patch get_db to use our test pool
    test_pool = MemoryConnectionPool()
    with patch("apps.shail.db.get_db", side_effect=test_pool.connection):
        yield test_pool

@pytest.fixture
def dummy_plan():
    return GuidancePlan(
        schema_version="1",
        steps=[
            GuidancePlanStep(
                action="click",
                target_selector="button.submit",
                fallback_coords=(100, 200),
                expected_outcome="Submits form"
            ),
            GuidancePlanStep(
                action="type",
                target_selector="input.name",
                fallback_coords=(150, 250),
                expected_outcome="Types name"
            )
        ]
    )

def test_session_storage_integration(dummy_plan):
    """Test that ClickyTelemetryLogger writes correctly to SQLite during plan lifecycle."""
    # Ensure PostHog remote calls are completely mocked
    with patch("telemetry.clicky_telemetry_logger.posthog"):
        logger = ClickyTelemetryLogger()
        
        # Start Plan
        logger.log_plan_start(dummy_plan)
        session_id = logger._current_session_id
        assert session_id is not None
        
        # Verify row created in SQLite
        from apps.shail.db import get_db
        with get_db() as conn:
            row = conn.execute("SELECT * FROM ghost_sessions WHERE session_id = ?", (session_id,)).fetchone()
            assert row is not None
            assert row["total_steps"] == 2
            assert row["completed_steps"] == 0
            assert row["status"] == "in_progress"
            
        # Step 1 Success
        logger.log_step_result(dummy_plan.steps[0], 0, True, True, 100.5)
        with get_db() as conn:
            row = conn.execute("SELECT * FROM ghost_sessions WHERE session_id = ?", (session_id,)).fetchone()
            assert row["completed_steps"] == 1
            
        # Step 2 Failure
        logger.log_step_result(dummy_plan.steps[1], 1, False, False, 200.0)
        with get_db() as conn:
            row = conn.execute("SELECT * FROM ghost_sessions WHERE session_id = ?", (session_id,)).fetchone()
            assert row["completed_steps"] == 1 # Unchanged
            
        # Complete plan
        logger.log_plan_complete(False, 300.5)
        
        # Verify row updated in SQLite
        with get_db() as conn:
            row = conn.execute("SELECT * FROM ghost_sessions WHERE session_id = ?", (session_id,)).fetchone()
            assert row["status"] == "failed"
            
            clicky_log = json.loads(row["clicky_log"])
            assert len(clicky_log) == 4
            assert clicky_log[0]["event"] == "ghost_cursor_plan_start"
            assert clicky_log[1]["event"] == "ghost_cursor_step_result"
            assert clicky_log[2]["event"] == "ghost_cursor_step_result"
            assert clicky_log[3]["event"] == "ghost_cursor_plan_complete"
            
        # Logger state reset
        assert logger._current_session_id is None

def test_aborted_session(dummy_plan):
    with patch("telemetry.clicky_telemetry_logger.posthog"):
        logger = ClickyTelemetryLogger()
        logger.log_plan_start(dummy_plan)
        session_id = logger._current_session_id
        
        logger.log_plan_aborted("user_cancelled")
        
        from apps.shail.db import get_db
        with get_db() as conn:
            row = conn.execute("SELECT * FROM ghost_sessions WHERE session_id = ?", (session_id,)).fetchone()
            assert row["status"] == "aborted"
            clicky_log = json.loads(row["clicky_log"])
            assert clicky_log[-1]["event"] == "ghost_cursor_plan_aborted"
