import pytest
import os
import sys
import json
import sqlite3
import queue
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
import apps.shail.db as db_module
from apps.shail.db import PooledConnectionProxy

# Need to set up path to allow importing from apps/ghost-cursor correctly
import importlib.util
gc_routes_path = os.path.join(os.path.dirname(__file__), "../api/routes.py")
spec = importlib.util.spec_from_file_location("gc_routes", gc_routes_path)
gc_routes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gc_routes)

storage_path = os.path.join(os.path.dirname(__file__), "../telemetry/storage.py")
storage_spec = importlib.util.spec_from_file_location("gc_storage", storage_path)
storage = importlib.util.module_from_spec(storage_spec)
storage_spec.loader.exec_module(storage)

class MemoryConnectionPool:
    def __init__(self):
        self._pool = queue.Queue(1)
        self.db_path = "file:testintdb_sprint4?mode=memory&cache=shared"
        conn = sqlite3.connect(self.db_path, uri=True, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        self._pool.put(conn)

    def get_connection(self):
        try:
            conn = self._pool.get(timeout=1.0)
        except queue.Empty:
            conn = sqlite3.connect(self.db_path, uri=True, timeout=30.0, check_same_thread=False)
            conn.row_factory = sqlite3.Row
        return PooledConnectionProxy(self, conn)

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
    test_pool = MemoryConnectionPool()
    with patch("apps.shail.db.get_db", side_effect=test_pool.connection):
        storage.init_ghost_sessions_db()
        with test_pool.connection() as conn:
            conn.execute("DELETE FROM ghost_sessions")
        yield test_pool

app = FastAPI()
app.include_router(gc_routes.router, prefix="/ghost")
client = TestClient(app)

def test_workflow_1_system_settings():
    plan = {
        "schema_version": "1",
        "steps": [
            {"action": "navigate", "target_selector": "System Settings app", "fallback_coords": [10, 10], "expected_outcome": "System Settings is open"},
            {"action": "click", "target_selector": "Appearance sidebar item", "fallback_coords": [100, 200], "expected_outcome": "Appearance settings loaded"},
            {"action": "click", "target_selector": "Dark Mode style option", "fallback_coords": [350, 150], "expected_outcome": "System Dark Mode enabled"}
        ]
    }
    
    with patch("execution.adapters.accessibility_bridge_driver.AccessibilityBridgeDriver._send_command", return_value=True), \
         patch("execution.adapters.accessibility_bridge_driver.AccessibilityBridgeDriver._send_command_raw", return_value={"success": True, "element": None}):
         
        response = client.post("/ghost/execute", json=plan)
        assert response.status_code == 200
        sessions = client.get("/ghost/sessions").json()
        assert len(sessions) == 1
        assert sessions[0]["total_steps"] == 3

def test_workflow_2_github_repo():
    plan = {
        "schema_version": "1",
        "steps": [
            {"action": "navigate", "target_selector": "https://github.com", "fallback_coords": [0, 0], "expected_outcome": "GitHub home page is loaded"},
            {"action": "click", "target_selector": "New repository button", "fallback_coords": [800, 120], "expected_outcome": "Create repository page loaded"},
            {"action": "type", "target_selector": "Repository name input field", "fallback_coords": [250, 300], "expected_outcome": "test-repo entered"},
            {"action": "click", "target_selector": "Create repository green button", "fallback_coords": [300, 800], "expected_outcome": "Repository test-repo created"}
        ]
    }
    def mock_send_command_raw(payload):
        if payload.get("command") == "get_element_at":
            if payload.get("x") == 250: # type action coords
                return {"success": True, "element": {"id": "mock"}}
            return {"success": True, "element": None} # clicks expect None
        return {"success": True, "element": None}

    with patch("execution.adapters.accessibility_bridge_driver.AccessibilityBridgeDriver._send_command", return_value=True), \
         patch("execution.adapters.accessibility_bridge_driver.AccessibilityBridgeDriver._send_command_raw", side_effect=mock_send_command_raw):
        
        response = client.post("/ghost/execute", json=plan)
        assert response.status_code == 200
        sessions = client.get("/ghost/sessions").json()
        assert sessions[0]["completed_steps"] == 4

def test_workflow_3_complex_scrolling():
    plan = {
        "schema_version": "1",
        "steps": [
            {"action": "navigate", "target_selector": "Finder app", "fallback_coords": [0, 0], "expected_outcome": "Finder is active"},
            {"action": "click", "target_selector": "Downloads folder in sidebar", "fallback_coords": [80, 150], "expected_outcome": "Downloads directory listed"},
            {"action": "scroll", "target_selector": "Downloads file list", "fallback_coords": [400, 300], "expected_outcome": "Old files located"},
            {"action": "click", "target_selector": "Move selection to Archive", "fallback_coords": [500, 500], "expected_outcome": "Old files moved to Archive folder"}
        ]
    }
    with patch("execution.adapters.accessibility_bridge_driver.AccessibilityBridgeDriver._send_command", return_value=True), \
         patch("execution.adapters.accessibility_bridge_driver.AccessibilityBridgeDriver._send_command_raw", return_value={"success": True, "element": None}):
        response = client.post("/ghost/execute", json=plan)
        assert response.status_code == 200

def test_workflow_4_typing():
    plan = {
        "schema_version": "1",
        "steps": [
            {"action": "navigate", "target_selector": "Notes app", "fallback_coords": [0, 0], "expected_outcome": "Notes app is active"},
            {"action": "click", "target_selector": "New Note button", "fallback_coords": [150, 50], "expected_outcome": "Blank note sheet loaded"},
            {"action": "type", "target_selector": "Note body area", "fallback_coords": [300, 200], "expected_outcome": "Meeting summary written inside note"}
        ]
    }
    with patch("execution.adapters.accessibility_bridge_driver.AccessibilityBridgeDriver._send_command", return_value=True), \
         patch("execution.adapters.accessibility_bridge_driver.AccessibilityBridgeDriver._send_command_raw", return_value={"success": True, "element": {"id": "mock"}}):
        response = client.post("/ghost/execute", json=plan)
        assert response.status_code == 200

def test_workflow_5_deliberate_failure():
    plan = {
        "schema_version": "1",
        "steps": [
            {"action": "click", "target_selector": "Missing element", "fallback_coords": [10, 10], "expected_outcome": "Never succeeds"}
        ]
    }
    
    with patch("execution.adapters.accessibility_bridge_driver.AccessibilityBridgeDriver._send_command", return_value=True), \
         patch("execution.adapters.accessibility_bridge_driver.AccessibilityBridgeDriver._send_command_raw", return_value={"success": True, "element": {"id": "mock"}}):
        
        response = client.post("/ghost/execute", json=plan)
        assert response.status_code == 200
        
        abort_res = client.post("/ghost/abort")
        assert abort_res.status_code in (200, 400)
