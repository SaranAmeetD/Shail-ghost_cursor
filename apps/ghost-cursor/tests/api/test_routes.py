import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
import sys
import os
import sqlite3
import queue

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../..")))

import apps.shail.db as db_module
from unittest.mock import patch

# Need to set up path to allow importing from apps/ghost-cursor correctly
import importlib.util
gc_routes_path = os.path.join(os.path.dirname(__file__), "../../api/routes.py")
spec = importlib.util.spec_from_file_location("gc_routes", gc_routes_path)
gc_routes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gc_routes)

from apps.shail.db import PooledConnectionProxy

# We need to manually load storage to avoid "apps.ghost-cursor" naming issues
storage_path = os.path.join(os.path.dirname(__file__), "../../telemetry/storage.py")
storage_spec = importlib.util.spec_from_file_location("gc_storage", storage_path)
storage = importlib.util.module_from_spec(storage_spec)
storage_spec.loader.exec_module(storage)

class MemoryConnectionPool:
    def __init__(self):
        self._pool = queue.Queue(1)
        self.db_path = "file:testapidb?mode=memory&cache=shared"
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

def test_get_sessions():
    session_id = storage.create_session(5, "Test session")
    storage.end_session(session_id, "completed", [{"event": "test"}])
    
    response = client.get("/ghost/sessions")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["session_id"] == session_id
    assert data[0]["intent_text"] == "Test session"
    assert data[0]["status"] == "completed"

def test_get_session_detail():
    session_id = storage.create_session(5, "Test session 2")
    storage.end_session(session_id, "completed", [{"event": "test_event_2"}])
    
    response = client.get(f"/ghost/sessions/{session_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    assert len(data["clicky_log"]) == 1
    assert data["clicky_log"][0]["event"] == "test_event_2"

    response_not_found = client.get("/ghost/sessions/nonexistent")
    assert response_not_found.status_code == 404

def test_delete_session():
    session_id = storage.create_session(5, "Delete me")
    
    response = client.delete(f"/ghost/sessions/{session_id}")
    assert response.status_code == 200
    assert response.json() == {"success": True}
    
    response_check = client.get(f"/ghost/sessions/{session_id}")
    assert response_check.status_code == 404

def test_bulk_delete_sessions():
    storage.create_session(1, "S1")
    storage.create_session(2, "S2")
    storage.create_session(3, "S3")
    storage.create_session(4, "S4")
    
    with db_module.get_db() as conn:
        conn.execute("UPDATE ghost_sessions SET created_at = '2020-01-01T00:00:00Z' WHERE intent_text = 'S1'")
        conn.execute("UPDATE ghost_sessions SET created_at = '2020-06-01T00:00:00Z' WHERE intent_text = 'S2'")
        conn.execute("UPDATE ghost_sessions SET created_at = '2021-01-01T00:00:00Z' WHERE intent_text = 'S3'")
        conn.execute("UPDATE ghost_sessions SET created_at = '2021-06-01T00:00:00Z' WHERE intent_text = 'S4'")
        
    with TestClient(app) as local_client:
        # Test only end_date
        response = local_client.delete("/ghost/sessions/bulk?end_date=2020-03-01T00:00:00Z")
        assert response.status_code == 200
        assert response.json()["deleted_count"] == 1 # S1 deleted
        
        # Test only start_date
        response = local_client.delete("/ghost/sessions/bulk?start_date=2021-03-01T00:00:00Z")
        assert response.status_code == 200
        assert response.json()["deleted_count"] == 1 # S4 deleted
        
        # Test both parameters
        response = local_client.delete("/ghost/sessions/bulk?start_date=2020-05-01T00:00:00Z&end_date=2021-02-01T00:00:00Z")
        assert response.status_code == 200
        assert response.json()["deleted_count"] == 2 # S2 and S3 deleted
        
        # Test no parameters
        storage.create_session(5, "S5")
        response = local_client.delete("/ghost/sessions/bulk")
        assert response.status_code == 200
        assert response.json()["deleted_count"] == 1 # S5 deleted
