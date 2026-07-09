import logging
from typing import Optional

from perception_source import PerceptionSource, PerceptionResult

logger = logging.getLogger(__name__)

class AccessibilityPermissionError(Exception):
    """Raised when the Accessibility API indicates it is disabled or cannot complete."""
    pass

class PerceptionCoordinator:
    """
    Coordinates the choice between Accessibility-first perception and Vision fallback.
    Standalone and unit-testable.
    """
    
    # Thresholds confirmed in Phase R1
    MIN_ACTIONABLE_ELEMENTS = 3
    ACTIONABLE_ROLES = {
        "AXButton", "AXTextField", "AXTextArea", "AXCheckBox",
        "AXMenuItem", "AXLink", "AXPopUpButton", "AXRadioButton",
        "AXSlider", "AXComboBox"
    }
    MIN_LABELED_RATIO = 0.6

    def __init__(self, ax_reader: PerceptionSource, vision_reader: PerceptionSource):
        self.ax_reader = ax_reader
        self.vision_reader = vision_reader

    async def get_perception(self, pid: int, intent: str) -> PerceptionResult:
        logger.debug(f"PerceptionCoordinator: Requesting AX tree for pid {pid}")
        ax_result = await self.ax_reader.read(pid)

        # 1. Handle native macOS accessibility errors
        if ax_result.error_code == "kAXErrorAPIDisabled":
            logger.warning("Accessibility API disabled. Raising PermissionError.")
            raise AccessibilityPermissionError("macOS Accessibility API is disabled for this process.")
            
        if ax_result.error_code == "kAXErrorCannotComplete":
            logger.warning("Accessibility API cannot complete. Cross-checking Finder.")
            # Note: The adapter must expose this method for the check
            if hasattr(self.ax_reader, "probe_finder_succeeds"):
                if await self.ax_reader.probe_finder_succeeds():
                    logger.info("Finder cross-check succeeded. Target app lacks AX support. Falling back to Vision.")
                    pass
                else:
                    logger.warning("Finder cross-check failed. System-wide permissions issue suspected.")
                    raise AccessibilityPermissionError("macOS Accessibility API is failing globally (permissions issue).")
            else:
                # If no probe method exists on the interface, fall back to vision safely.
                pass

        # 2. Evaluate AX Thresholds
        actionable = [e for e in ax_result.elements if e.role in self.ACTIONABLE_ROLES]
        
        # Elements are considered labeled if they have a non-empty best_label.
        # ScreenElement.best_label falls back to title -> description -> value.
        # We check title and description specifically as per pseudo-code.
        labeled = [e for e in actionable if getattr(e, 'title', '') or getattr(e, 'description', '')]
        
        labeled_ratio = (len(labeled) / len(actionable)) if actionable else 0.0

        sufficient = (
            len(actionable) >= self.MIN_ACTIONABLE_ELEMENTS
            and labeled_ratio >= self.MIN_LABELED_RATIO
        )

        if sufficient:
            logger.debug(f"AX tree sufficient ({len(actionable)} actionable, {labeled_ratio:.0%} labeled). Using AX mode.")
            # Return the ax_result with mode="ax". payload is already set by AXTreeReader.
            return ax_result

        # 3. Fallback to Vision
        logger.debug(f"AX tree insufficient ({len(actionable)} actionable, {labeled_ratio:.0%} labeled). Falling back to Vision mode.")
        vision_result = await self.vision_reader.read(pid)
        return vision_result
