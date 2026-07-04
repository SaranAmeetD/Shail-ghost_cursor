import os
import logging
import uuid

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from models import GuidancePlan, GuidancePlanStep
from telemetry.telemetry_logger import TelemetryLogger

# PostHog SDK import — guarded to avoid hard failure if not installed.
# Matches the try/except import pattern used by accessibility_bridge_driver.py
# for the websockets package.
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
    # uuid.getnode() sets bit 40 (multicast bit) if it fabricates an address
    if node & (1 << 40):
        # Fabricated address — fall back to a persistent random ID.
        # We do not persist it across restarts; a random UUID per process
        # is acceptable for anonymous telemetry grouping.
        return str(uuid.uuid4())
    return str(node)


# Module-level constant so all instances share the same distinct_id
_DISTINCT_ID = _get_distinct_id()


class ClickyTelemetryLogger(TelemetryLogger):
    """
    Concrete implementation of TelemetryLogger that sends Ghost Cursor
    execution events to PostHog — the same analytics backend used by
    Clicky (packages/clicky/leanring-buddy/ClickyAnalytics.swift).

    Active only when POSTHOG_API_KEY is set in the environment.
    When inactive, all methods are silent no-ops.

    Event names follow the Clicky naming convention (snake_case, product prefix):
        ghost_cursor_plan_start
        ghost_cursor_step_result
        ghost_cursor_plan_complete
        ghost_cursor_plan_aborted
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
                "ClickyTelemetryLogger is inactive."
            )

    def _capture(self, event: str, properties: dict) -> None:
        """Send a single event to PostHog. Silent on failure."""
        if not self.is_active:
            return
        try:
            posthog.capture(_DISTINCT_ID, event, properties)
        except Exception as e:
            logger.warning(f"Failed to send PostHog event '{event}': {e}")

    def log_plan_start(self, plan: GuidancePlan) -> None:
        self._capture("ghost_cursor_plan_start", {
            "step_count": len(plan.steps)
        })

    def log_step_result(self, step: GuidancePlanStep, index: int, success: bool, verified: bool, latency_ms: float) -> None:
        self._capture("ghost_cursor_step_result", {
            "step_index": index,
            "action": step.action,
            "success": success,
            "verified": verified,
            "latency_ms": latency_ms
        })

    def log_plan_complete(self, success: bool, total_ms: float) -> None:
        self._capture("ghost_cursor_plan_complete", {
            "success": success,
            "total_ms": total_ms
        })

    def log_plan_aborted(self, reason: str) -> None:
        self._capture("ghost_cursor_plan_aborted", {
            "reason": reason
        })
