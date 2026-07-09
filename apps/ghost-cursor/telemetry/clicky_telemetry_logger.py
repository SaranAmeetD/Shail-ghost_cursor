import os
import logging
import uuid
from datetime import datetime

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from models import GuidancePlan, GuidancePlanStep
from telemetry.telemetry_logger import TelemetryLogger
from telemetry.storage import init_ghost_sessions_db, create_session, update_session_progress, end_session

# PostHog SDK import — guarded to avoid hard failure if not installed.
try:
    import posthog
except ImportError:
    posthog = None

logger = logging.getLogger(__name__)


def _get_distinct_id() -> str:
    """
    Returns a stable anonymous identifier for this machine.
    Uses uuid.getnode() which returns the hardware MAC address as a 48-bit
    integer. Falls back to a random UUID if getnode() returns a synthetic
    address (indicated by the multicast bit being set).
    """
    node = uuid.getnode()
    if node & (1 << 40):
        return str(uuid.uuid4())
    return str(node)


_DISTINCT_ID = _get_distinct_id()


class ClickyTelemetryLogger(TelemetryLogger):
    """
    Concrete implementation of TelemetryLogger that sends Ghost Cursor
    execution events to PostHog, and additionally stores full session telemetry
    in the local SHAIL SQLite database.

    Remote logging is active only when POSTHOG_API_KEY is set in the environment.
    Local SQLite session logging is always active.
    """
    def __init__(self):
        self._api_key = os.environ.get("POSTHOG_API_KEY")
        self.is_active = bool(self._api_key) and posthog is not None

        if self.is_active:
            posthog.project_api_key = self._api_key
            posthog.host = "https://us.i.posthog.com"
        elif self._api_key and posthog is None:
            logger.warning(
                "POSTHOG_API_KEY is set but posthog package is not installed. "
                "Remote logging is inactive."
            )

        # Initialize SQLite storage
        init_ghost_sessions_db()
        self._current_session_id = None
        self._current_completed_steps = 0
        self._current_session_events = []

    def _capture(self, event: str, properties: dict) -> None:
        """Store locally for SQLite session log, and send to PostHog if active."""
        if self._current_session_id is not None:
            self._current_session_events.append({
                "event": event,
                "properties": properties,
                "timestamp": datetime.utcnow().isoformat()
            })

        if not self.is_active:
            return
        try:
            posthog.capture(_DISTINCT_ID, event, properties)
        except Exception as e:
            logger.warning(f"Failed to send PostHog event '{event}': {e}")

    def log_plan_start(self, plan: GuidancePlan) -> None:
        step_count = len(plan.steps)
        # Create a new session in SQLite
        self._current_session_id = create_session(total_steps=step_count)
        self._current_completed_steps = 0
        self._current_session_events = []
        
        # Cache the perception mode for logging against each step
        self._current_perception_mode = getattr(plan, "perception_mode", "vision")

        self._capture("ghost_cursor_plan_start", {
            "step_count": step_count
        })

    def log_step_result(self, step: GuidancePlanStep, index: int, success: bool, verified: bool, latency_ms: float) -> None:
        self._capture("ghost_cursor_step_result", {
            "step_index": index,
            "action": step.action,
            "success": success,
            "verified": verified,
            "latency_ms": latency_ms,
            "perception_mode": getattr(self, "_current_perception_mode", "vision")
        })

        if success and verified:
            self._current_completed_steps += 1
            if self._current_session_id is not None:
                update_session_progress(self._current_session_id, self._current_completed_steps)

    def log_plan_complete(self, success: bool, total_ms: float) -> None:
        self._capture("ghost_cursor_plan_complete", {
            "success": success,
            "total_ms": total_ms
        })

        if self._current_session_id is not None:
            status = "completed" if success else "failed"
            end_session(self._current_session_id, status, self._current_session_events)
            self._current_session_id = None

    def log_plan_aborted(self, reason: str) -> None:
        self._capture("ghost_cursor_plan_aborted", {
            "reason": reason
        })

        if self._current_session_id is not None:
            end_session(self._current_session_id, "aborted", self._current_session_events)
            self._current_session_id = None

    def get_recent_events(self, limit: int = 3) -> list:
        import copy
        if not self._current_session_events:
            return []
        # Return a defensive copy of the last `limit` events
        return copy.deepcopy(self._current_session_events[-limit:])

