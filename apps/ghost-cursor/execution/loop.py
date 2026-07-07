import logging
import time
from typing import Optional, Callable
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from models import GuidancePlan, GuidancePlanStep
from execution.interfaces import CursorDriver, OverlayRenderer
from validation.observer import ResultObserver
from telemetry.telemetry_logger import TelemetryLogger
from execution.privacy_guard import PrivacyGuard

logger = logging.getLogger(__name__)

class ExecutionLoop:
    """
    Sequential execution loop for a Ghost Cursor GuidancePlan.
    """
    def __init__(
        self, 
        driver: CursorDriver, 
        renderer: OverlayRenderer,
        observer: Optional[ResultObserver] = None,
        telemetry: Optional[TelemetryLogger] = None,
        privacy_guard: Optional[PrivacyGuard] = None,
        on_step_failure: Optional[Callable[[GuidancePlanStep, int, str], None]] = None,
        on_privacy_block: Optional[Callable[[str], None]] = None,
        retry_delay_s: float = 0.5
    ):
        self.driver = driver
        self.renderer = renderer
        self.observer = observer
        self.telemetry = telemetry
        self.privacy_guard = privacy_guard
        self.on_step_failure = on_step_failure
        self.on_privacy_block = on_privacy_block
        self.retry_delay_s = retry_delay_s
        self._is_cancelled = False

    def cancel(self):
        """Signals the execution loop to stop before the next step."""
        self._is_cancelled = True

    def _execute_action(self, step: GuidancePlanStep, x: int, y: int) -> bool:
        if step.action == "click":
            return self.driver.click(x, y)
        elif step.action == "type":
            text_to_type = step.expected_outcome if step.expected_outcome else "test"
            return self.driver.type_text(text_to_type)
        elif step.action == "scroll":
            return self.driver.scroll(x, y, 0, -50)
        elif step.action == "navigate":
            return self.driver.navigate(step.target_selector)
        return False

    def run(self, plan: GuidancePlan, current_url: Optional[str] = None) -> bool:
        """
        Executes the plan sequentially.
        Returns True if all steps completed (or were attempted without abort), 
        False if cancelled or blocked.
        """
        self._is_cancelled = False
        plan_start_time = time.monotonic()
        
        # Pre-flight privacy check
        if self.privacy_guard and current_url:
            if self.privacy_guard.check(current_url):
                logger.warning(f"PrivacyGuard blocked execution on {current_url}")
                if self.on_privacy_block:
                    self.on_privacy_block(current_url)
                return False

        if self.telemetry:
            self.telemetry.log_plan_start(plan)
            
        for index, step in enumerate(plan.steps):
            if self._is_cancelled:
                logger.info(f"Execution loop cancelled by user at step {index + 1}.")
                if self.telemetry:
                    self.telemetry.log_plan_aborted("user_cancelled")
                return False
                
            # Per-step privacy check for navigation
            if step.action == "navigate" and self.privacy_guard:
                if self.privacy_guard.check(step.target_selector):
                    logger.warning(f"PrivacyGuard blocked navigate to {step.target_selector}")
                    if self.on_privacy_block:
                        self.on_privacy_block(step.target_selector)
                    if self.telemetry:
                        self.telemetry.log_plan_aborted("privacy_blocked")
                    return False

            logger.info(f"Executing step {index + 1}/{len(plan.steps)}: {step.action}")
            x, y = step.fallback_coords
            self.renderer.move_to(x, y)
            time.sleep(0.3)
            
            step_start_time = time.monotonic()
            success = self._execute_action(step, x, y)
            verified = True
            
            if self.observer:
                result = self.observer.observe(step, self.driver)
                if result.is_verifiable and not result.verified:
                    logger.info(f"Step {index + 1} observation failed: {result.reason}. Retrying...")
                    time.sleep(self.retry_delay_s)
                    success = self._execute_action(step, x, y)
                    result = self.observer.observe(step, self.driver)
                    
                verified = result.verified
                if not verified:
                    logger.warning(f"Step {index + 1} verification failed after retry: {result.reason}")
                    if self.on_step_failure:
                        from validation.failure_diagnostics import FailureDiagnostics
                        if self.telemetry:
                            recent_events = self.telemetry.get_recent_events(limit=3)
                            enriched_context = FailureDiagnostics.format_failure_context(step, recent_events)
                            logger.info(f"Enriched failure context:\n{enriched_context}")
                            self.on_step_failure(step, index, enriched_context)
                        else:
                            self.on_step_failure(step, index, "No telemetry available.")
            elif not success:
                logger.warning(f"Step {index + 1} ({step.action}) reported failure from driver.")
            
            latency_ms = (time.monotonic() - step_start_time) * 1000
            if self.telemetry:
                self.telemetry.log_step_result(step, index, success, verified, latency_ms)
            
            self.renderer.flash()
            time.sleep(0.2)
                
        logger.info("Execution loop completed.")
        if self.telemetry:
            self.telemetry.log_plan_complete(True, (time.monotonic() - plan_start_time) * 1000)
        return True
