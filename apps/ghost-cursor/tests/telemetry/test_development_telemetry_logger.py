import os
import json
import time
import tempfile
import pytest
from unittest import mock

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from models import GuidancePlan, GuidancePlanStep
from telemetry.development_telemetry_logger import DevelopmentTelemetryLogger

@pytest.fixture
def temp_log_file():
    fd, path = tempfile.mkstemp(suffix=".ndjson")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)

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
            )
        ]
    )

def test_telemetry_inactive_by_default(temp_log_file, dummy_plan):
    with mock.patch("os.environ.get", return_value=None):
        logger = DevelopmentTelemetryLogger()
        logger.log_file = temp_log_file
        
        logger.log_plan_start(dummy_plan)
        
        with open(temp_log_file, "r") as f:
            assert len(f.readlines()) == 0

def test_telemetry_writes_when_active(temp_log_file, dummy_plan):
    with mock.patch("os.environ.get", return_value="1"):
        logger = DevelopmentTelemetryLogger()
        logger.log_file = temp_log_file
        
        logger.log_plan_start(dummy_plan)
        logger.log_step_result(dummy_plan.steps[0], 0, True, True, 150.5)
        logger.log_plan_complete(True, 200.0)
        
        with open(temp_log_file, "r") as f:
            lines = f.readlines()
            assert len(lines) == 3
            
            plan_start = json.loads(lines[0])
            assert plan_start["event"] == "plan_start"
            assert plan_start["step_count"] == 1
            assert "timestamp" in plan_start
            
            step_result = json.loads(lines[1])
            assert step_result["event"] == "step_result"
            props = step_result["properties"]
            assert props["action"] == "click"
            assert props["success"] is True
            assert props["verified"] is True
            assert props["latency_ms"] == 150.5
            # Ensure no forbidden keys
            assert "image" not in props
            assert "ocr" not in props
            assert "base64" not in props
            assert "text" not in props
            assert "selector" not in props

def test_telemetry_purge_stale_logs(temp_log_file):
    with mock.patch("os.environ.get", return_value="1"):
        now = time.time()
        
        # Write some logs directly
        with open(temp_log_file, "w") as f:
            # 25 hours ago - should be purged
            f.write(json.dumps({"event": "old_event", "timestamp": now - (25 * 3600)}) + "\n")
            # 1 hour ago - should be kept
            f.write(json.dumps({"event": "new_event", "timestamp": now - 3600}) + "\n")
            
        logger = DevelopmentTelemetryLogger(purge_hours=24)
        # Note: the logger __init__ will use its own temp file by default, 
        # so we need to manually call purge on our test file to test the logic
        logger.log_file = temp_log_file
        logger._purge_stale_logs(24)
        
        with open(temp_log_file, "r") as f:
            lines = f.readlines()
            assert len(lines) == 1
            kept_event = json.loads(lines[0])
            assert kept_event["event"] == "new_event"
