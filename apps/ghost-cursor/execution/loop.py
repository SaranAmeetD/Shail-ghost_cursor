import logging
import time
from typing import Optional
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from models import GuidancePlan
from execution.interfaces import CursorDriver, OverlayRenderer

logger = logging.getLogger(__name__)

class ExecutionLoop:
    """
    Sequential execution loop for a Ghost Cursor GuidancePlan.
    """
    def __init__(self, driver: CursorDriver, renderer: OverlayRenderer):
        self.driver = driver
        self.renderer = renderer
        self._is_cancelled = False

    def cancel(self):
        """Signals the execution loop to stop before the next step."""
        self._is_cancelled = True

    def run(self, plan: GuidancePlan) -> bool:
        """
        Executes the plan sequentially.
        Returns True if all steps completed (or were attempted without abort), 
        False if cancelled.
        """
        self._is_cancelled = False
        
        for index, step in enumerate(plan.steps):
            if self._is_cancelled:
                logger.info(f"Execution loop cancelled by user at step {index + 1}.")
                return False
                
            logger.info(f"Executing step {index + 1}/{len(plan.steps)}: {step.action}")
            
            x, y = step.fallback_coords
            
            # Move overlay to target coordinates
            self.renderer.move_to(x, y)
            
            # Short sleep to allow the overlay to animate (placeholder for async coordination)
            time.sleep(0.3)
            
            # Execute the action based on the step definition
            success = False
            if step.action == "click":
                success = self.driver.click(x, y)
            elif step.action == "type":
                # Fallback to typing the expected_outcome if there's no dedicated text field.
                text_to_type = step.expected_outcome if step.expected_outcome else "test"
                success = self.driver.type_text(text_to_type)
            elif step.action == "scroll":
                # Perform a default scroll
                success = self.driver.scroll(x, y, 0, -50)
            elif step.action == "navigate":
                success = self.driver.navigate(step.target_selector)
            
            if not success:
                logger.warning(f"Step {index + 1} ({step.action}) reported failure from driver.")
            
            # Flash the overlay to indicate action execution
            self.renderer.flash()
            
            # Short pause before next step
            time.sleep(0.2)
                
        logger.info("Execution loop completed.")
        return True
