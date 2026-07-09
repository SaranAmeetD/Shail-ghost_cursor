import os
import json
import time
import tempfile
import logging
from typing import Optional

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from models import GuidancePlan, GuidancePlanStep
from telemetry.telemetry_logger import TelemetryLogger

logger = logging.getLogger(__name__)

class DevelopmentTelemetryLogger(TelemetryLogger):
    """
    Concrete implementation of TelemetryLogger for development.
    Writes NDJSON lines to a file in the temp directory.
    Active only when DEV_TELEMETRY=1 is set.
    """
    def __init__(self, purge_hours: int = 24):
        self.is_active = os.environ.get("DEV_TELEMETRY") == "1"
        self.log_file = os.path.join(tempfile.gettempdir(), "ghost_cursor_telemetry.ndjson")
        if self.is_active:
            self._purge_stale_logs(purge_hours)

    def _purge_stale_logs(self, purge_hours: int):
        if not os.path.exists(self.log_file):
            return
        
        cutoff = time.time() - (purge_hours * 3600)
        valid_lines = []
        try:
            with open(self.log_file, "r") as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        if data.get("timestamp", 0) >= cutoff:
                            valid_lines.append(line)
                    except json.JSONDecodeError:
                        continue
            
            with open(self.log_file, "w") as f:
                for line in valid_lines:
                    f.write(line)
        except IOError as e:
            logger.warning(f"Failed to purge telemetry logs: {e}")

    def _write_log(self, event_data: dict):
        if not self.is_active:
            return
        event_data["timestamp"] = time.time()
        
        if not hasattr(self, "_recent_events"):
            self._recent_events = []
        
        # Keep track of recent events in memory for get_recent_events
        self._recent_events.append(event_data)
        if len(self._recent_events) > 10:
            self._recent_events.pop(0)

        try:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(event_data) + "\n")
        except IOError as e:
            logger.warning(f"Failed to write telemetry log: {e}")

    def log_plan_start(self, plan: GuidancePlan) -> None:
        self._recent_events = []
        self._current_perception_mode = getattr(plan, "perception_mode", "vision")
        self._write_log({
            "event": "plan_start",
            "step_count": len(plan.steps)
        })

    def log_step_result(self, step: GuidancePlanStep, index: int, success: bool, verified: bool, latency_ms: float) -> None:
        self._write_log({
            "event": "step_result",
            "properties": {
                "step_index": index,
                "action": step.action,
                "success": success,
                "verified": verified,
                "latency_ms": latency_ms,
                "perception_mode": getattr(self, "_current_perception_mode", "vision")
            }
        })

    def log_plan_complete(self, success: bool, total_ms: float) -> None:
        self._write_log({
            "event": "plan_complete",
            "success": success,
            "total_ms": total_ms
        })

    def log_plan_aborted(self, reason: str) -> None:
        self._write_log({
            "event": "plan_aborted",
            "reason": reason
        })

    def get_recent_events(self, limit: int = 3) -> list:
        import copy
        if not hasattr(self, "_recent_events") or not self._recent_events:
            return []
        return copy.deepcopy(self._recent_events[-limit:])

