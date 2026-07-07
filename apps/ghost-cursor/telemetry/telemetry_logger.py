from abc import ABC, abstractmethod
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from models import GuidancePlan, GuidancePlanStep

class TelemetryLogger(ABC):
    """
    Interface for logging Ghost Cursor execution events.
    """
    @abstractmethod
    def log_plan_start(self, plan: GuidancePlan) -> None:
        pass

    @abstractmethod
    def log_step_result(self, step: GuidancePlanStep, index: int, success: bool, verified: bool, latency_ms: float) -> None:
        pass

    @abstractmethod
    def log_plan_complete(self, success: bool, total_ms: float) -> None:
        pass

    @abstractmethod
    def log_plan_aborted(self, reason: str) -> None:
        pass

    @abstractmethod
    def get_recent_events(self, limit: int = 3) -> list:
        """
        Returns a defensive copy of up to `limit` recent telemetry events from the current session.
        """
        pass
