import copy
from typing import List, Dict, Any

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from models import GuidancePlanStep

class FailureDiagnostics:
    @staticmethod
    def format_failure_context(step: GuidancePlanStep, recent_events: List[Dict[str, Any]]) -> str:
        """
        Formats the recent telemetry events into a readable context string for the UI.
        """
        if not recent_events:
            return "Last 3 events before failure: None"

        lines = ["Last 3 events before failure:"]
        for event in recent_events:
            event_name = event.get("event", "unknown")
            props = event.get("properties", {})
            action = props.get("action", "unknown_action")
            step_idx = props.get("step_index", "?")
            success = props.get("success", False)
            
            # Formatting event summary
            summary = f"  - Step {step_idx} ({action}): {'Success' if success else 'Failed'}"
            lines.append(summary)

        return "\n".join(lines)
