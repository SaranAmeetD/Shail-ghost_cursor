import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List, Callable, Awaitable, Any

from screen_understanding import fetch_screen_elements, ScreenContext, ScreenElement
from ocr_extractor import extract_text, OCREntry

logger = logging.getLogger(__name__)

@dataclass
class PerceptionResult:
    mode: str          # "ax" or "vision"
    payload: str       # normalized text intended for VSLM
    element_count: int
    confidence_ok: bool
    error_code: Optional[str] = None
    
    # Exposing the underlying domain objects for threshold evaluation in Phase R3
    raw_data: Any = None 

    @property
    def elements(self) -> List[ScreenElement]:
        """Convenience property for Phase R3 threshold evaluation."""
        if self.mode == "ax" and isinstance(self.raw_data, ScreenContext):
            return self.raw_data.elements
        return []

    def to_text(self) -> str:
        """Convenience method matching the pseudo-code in Retrofit Guide."""
        return self.payload


class PerceptionSource(ABC):
    """
    Abstract interface for gathering Ghost Cursor screen perception data.
    """
    @abstractmethod
    async def read(self, pid: int) -> PerceptionResult:
        pass


class AXTreeReader(PerceptionSource):
    """
    Wraps the EXISTING accessibility-reading code found in Phase R0.
    Does not rewrite the AX-reading logic — just wraps its existing output
    into a PerceptionResult.
    """
    def __init__(self, ax_uri: str = "ws://localhost:8766/accessibility", timeout: float = 5.0):
        self.ax_uri = ax_uri
        self.timeout = timeout

    async def read(self, pid: int) -> PerceptionResult:
        # Note: fetch_screen_elements requests the active window directly, so pid is ignored here
        # but kept in the signature to satisfy the protocol contract.
        screen_ctx: ScreenContext = await fetch_screen_elements(ax_uri=self.ax_uri, timeout=self.timeout)
        
        # INTENTIONAL LIMITATION REMOVED:
        # Phase R3 approval granted modifying screen_understanding to expose error_code.
        error_code = screen_ctx.error_code

        # Format the payload using the same logic used in VSLMPipeline._ax_lines
        payload_lines = [node.to_prompt_line() for node in screen_ctx.elements]
        payload = "\n".join(payload_lines)

        return PerceptionResult(
            mode="ax",
            payload=payload,
            element_count=screen_ctx.element_count,
            confidence_ok=screen_ctx.available,
            error_code=error_code,
            raw_data=screen_ctx
        )

    async def probe_finder_succeeds(self) -> bool:
        # Stubbed as requested: "Do not add Finder logic yet"
        # Always return True so we fall through to Vision fallback.
        return True


class ScreenshotCapture(PerceptionSource):
    """
    Wraps the EXISTING screenshot + OCR code found in Phase R0.
    Does not rewrite the screenshot/OCR logic — just wraps its existing
    output into a PerceptionResult.
    """
    def __init__(
        self, 
        capture_func: Callable[[], Awaitable[str]], 
        ocr_timeout: float = 8.0, 
        ocr_confidence_threshold: float = 0.60
    ):
        # We accept a capture_func (e.g., pipeline.capture_screen_base64) 
        # to avoid duplicating the WebSocket logic that lives on VSLMPipeline.
        self.capture_func = capture_func
        self.ocr_timeout = ocr_timeout
        self.ocr_confidence_threshold = ocr_confidence_threshold

    async def read(self, pid: int) -> PerceptionResult:
        try:
            image_base64 = await self.capture_func()
        except Exception as exc:
            logger.warning(f"Screenshot capture failed in wrapper: {exc}")
            return PerceptionResult(
                mode="vision", 
                payload="", 
                element_count=0, 
                confidence_ok=False, 
                error_code="capture_failed"
            )
            
        ocr_results: List[OCREntry] = await extract_text(
            image_base64, 
            timeout=self.ocr_timeout, 
            confidence_threshold=self.ocr_confidence_threshold
        )
        
        # Format the payload using the same logic used in VSLMPipeline._ocr_lines
        payload_lines = [e.to_prompt_line() for e in ocr_results]
        payload = "\n".join(payload_lines)
        
        return PerceptionResult(
            mode="vision",
            payload=payload,
            element_count=len(ocr_results),
            confidence_ok=len(ocr_results) > 0,
            error_code=None,
            raw_data={"image_base64": image_base64, "ocr_results": ocr_results}
        )
