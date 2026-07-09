import sys
import os
import asyncio
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple
import websockets
from apps.shail.llm import call_llm

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from models import GuidancePlan
from screen_understanding import ScreenContext, ScreenElement, fetch_screen_elements
from ocr_extractor import OCREntry, extract_text
from perception_coordinator import PerceptionCoordinator
from perception_source import AXTreeReader, ScreenshotCapture


logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Ghost Cursor, an AI-powered UI execution engine.
Your task is to analyze the provided screenshot — and the supplementary structured
screen data below it — then convert the user's high-level intent into a structured,
ordered GuidancePlan.

Supplementary screen data (if present) contains two sections:
  ACCESSIBILITY ELEMENTS: Interactive UI elements with their roles, labels, and
    screen positions reported by the macOS Accessibility API.  These are the
    most reliable source for element targeting.
  OCR TEXT: Text tokens detected visually on screen.  Use this to identify labels
    that the Accessibility API may not expose (e.g., canvas-rendered text).

Element targeting priority:
  1. Use `target_selector` from an ACCESSIBILITY ELEMENTS entry (role + label).
  2. If no matching AX element exists, use an OCR TEXT entry.
  3. Use `fallback_coords` (element centre point) only as a last resort.

You MUST respond with a valid JSON object matching the following GuidancePlan schema:
{
  "schema_version": "1",
  "steps": [
    {
      "action": "click" | "type" | "scroll" | "navigate",
      "target_selector": "string (AX role + label, or human-readable description)",
      "fallback_coords": [x, y],
      "expected_outcome": "string describing what changes visually"
    }
  ]
}

Only return valid JSON. Do not include markdown formatting or extra conversational text.
"""

class VSLMPipeline:
    def __init__(
        self,
        ws_uri: str = "ws://localhost:8765/capture",
        model: str = "gemma4",
        ax_uri: str = "ws://localhost:8766/accessibility",
    ):
        self.ws_uri = ws_uri
        self.model = model
        self.ax_uri = ax_uri

        # Timeout constants (seconds)
        self._capture_timeout: float = 10.0
        self._ax_timeout: float = 5.0
        self._ocr_timeout: float = 8.0

        # Prompt budget constants
        self._max_ax_nodes: int = 40
        self._max_ocr_entries: int = 30
        self._ocr_confidence_threshold: float = 0.60
        self._max_context_chars: int = 4000

        # Phase R4: Integrate hybrid perception coordinator
        self.coordinator = PerceptionCoordinator(
            ax_reader=AXTreeReader(ax_uri=self.ax_uri, timeout=self._ax_timeout),
            vision_reader=ScreenshotCapture(
                capture_func=lambda: self.capture_screen_base64(timeout=self._capture_timeout),
                ocr_timeout=self._ocr_timeout,
                ocr_confidence_threshold=self._ocr_confidence_threshold
            )
        )

    async def capture_screen_base64(self, timeout: float = 10.0) -> str:
        """
        Connect to CaptureService WebSocket and request a single-frame base64 PNG.
        """
        logger.info(f"Connecting to CaptureService at {self.ws_uri}...")
        async with websockets.connect(self.ws_uri) as ws:
            request_id = "vslm-capture-sprint1.2"
            request_payload = {
                "type": "request_png_base64",
                "request_id": request_id
            }
            await ws.send(json.dumps(request_payload))
            
            # Await single frame response
            while True:
                response_str = await asyncio.wait_for(ws.recv(), timeout=timeout)
                response = json.loads(response_str)
                if response.get("type") == "png_response" and response.get("request_id") == request_id:
                    if response.get("status") == "ok":
                        data_b64 = response["data_b64"]
                        # Verify it is not empty
                        if not data_b64 or len(data_b64.strip()) == 0:
                            raise ValueError("Received empty base64 image data")
                        return data_b64
                    else:
                        raise RuntimeError(f"Capture failed: {response.get('message', 'Unknown error')}")

    async def generate_guidance_plan(
        self,
        intent: str,
        image_base64: str,
        screen_context: str = "",
    ) -> GuidancePlan:
        """
        Send image + intent (+ optional enriched screen context) to Ollama via
        the Shail LLM interface and parse the response into a validated GuidancePlan.

        Parameters
        ----------
        intent : str
            The user's high-level natural-language instruction.
        image_base64 : str
            Base64-encoded PNG screenshot.
        screen_context : str
            Pre-built context string from _build_screen_context().  Embedded in
            the user message when non-empty.  Empty string disables the context
            section (Sprint 1.2 backward-compatible mode).
        """
        content_parts = [f"User intent: {intent}"]
        if screen_context:
            content_parts.append(f"\n---\n{screen_context}\n---")
        user_content = "\n".join(content_parts)

        msg = {
            "role": "user",
            "content": user_content,
        }
        if image_base64:
            msg["images"] = [image_base64]
            
        messages = [msg]

        try:
            # Deep-copy to prevent the finally-block image nullification from
            # mutating the list we pass to call_llm.
            messages_copy = [
                {k: (list(v) if isinstance(v, list) else v) for k, v in m.items()}
                for m in messages
            ]
            response_text, meta = await call_llm(
                messages_copy,
                system_prompt=SYSTEM_PROMPT,
                model=self.model
            )

            logger.info("Parsing VSLM output...")
            # Strip markdown code fences (```json ... ```) if the model wraps output.
            cleaned_text = self._clean_json_response(response_text)

            parsed_dict = json.loads(cleaned_text)
            plan = GuidancePlan.model_validate(parsed_dict)
            return plan
        finally:
            # Transient image cleanup: nullify base64 references to encourage GC.
            # This is not a security mechanism — it is a best-effort memory hygiene step.
            if 'messages' in locals():
                for m in messages:
                    if 'images' in m:
                        m['images'] = None
                del messages
            logger.info("Transient screenshot memory reference cleared.")

    # -----------------------------------------------------------------------
    # Sprint 1.3: Screen context fusion
    # -----------------------------------------------------------------------

    def _build_screen_context(
        self,
        screen_ctx: ScreenContext,
        ocr_results: List[OCREntry],
    ) -> str:
        """
        Merges the Accessibility element list and OCR text into a bounded,
        deterministic context string for inclusion in the LLM prompt.

        Deduplication
        -------------
        1. Normalised string match: OCR entries whose text appears as a
           substring (or contains as substring) of any AX element label
           (≥4 chars) are dropped.  The AX element carries the canonical label.
        2. Spatial overlap: OCR entries whose bounding-box centre falls within
           any AX element's ScreenRect (inflated by 4px) are dropped.

        Budget enforcement
        ------------------
        - Max 40 AX nodes, max 30 OCR entries, OCR confidence ≥ 0.60.
        - If total char count > 4000, cascade:
            Step 1: drop OCR entries with confidence < 0.80
            Step 2: reduce AX budget to 25
            Step 3: reduce OCR budget to 15
        """
        ax_nodes = screen_ctx.elements[: self._max_ax_nodes]
        ocr_entries = [
            e for e in ocr_results if e.confidence >= self._ocr_confidence_threshold
        ][: self._max_ocr_entries]

        # --- Deduplication ---
        ax_labels_normalised = [
            elem.best_label.strip().lower() for elem in ax_nodes
        ]

        deduped_ocr: List[OCREntry] = []
        for ocr_entry in ocr_entries:
            norm_ocr = ocr_entry.text.strip().lower()
            # String dedup: skip if OCR text is substring of any AX label (or vice versa)
            is_text_dup = any(
                (len(norm_ocr) >= 4 and norm_ocr in ax_lbl)
                or (len(ax_lbl) >= 4 and ax_lbl in norm_ocr)
                for ax_lbl in ax_labels_normalised
            )
            if is_text_dup:
                continue
            # Spatial dedup: skip if OCR centre is inside any AX element rect
            ocr_cx, ocr_cy = ocr_entry.rect.centre
            is_spatial_dup = any(
                elem.rect.contains_point(ocr_cx, ocr_cy, margin=4)
                for elem in ax_nodes
            )
            if is_spatial_dup:
                continue
            deduped_ocr.append(ocr_entry)

        # --- Build sections ---
        def _ax_lines(nodes: List[ScreenElement]) -> List[str]:
            return [elem.to_prompt_line() for elem in nodes]

        def _ocr_lines(entries: List[OCREntry]) -> List[str]:
            return [e.to_prompt_line() for e in entries]

        def _assemble(ax_lines: List[str], ocr_lines: List[str]) -> str:
            parts: List[str] = []
            if ax_lines:
                parts.append("ACCESSIBILITY ELEMENTS:")
                parts.extend(ax_lines)
            if ocr_lines:
                parts.append("OCR TEXT:")
                parts.extend(ocr_lines)
            return "\n".join(parts)

        context = _assemble(_ax_lines(ax_nodes), _ocr_lines(deduped_ocr))

        # Pre-compute high-confidence OCR subset used by cascade steps 2 and 3.
        # Computed unconditionally so later steps can always reference it.
        high_conf_ocr = [e for e in deduped_ocr if e.confidence >= 0.80]

        # --- Truncation cascade ---
        if len(context) > self._max_context_chars:
            # Step 1: raise OCR confidence bar
            context = _assemble(_ax_lines(ax_nodes), _ocr_lines(high_conf_ocr))

        if len(context) > self._max_context_chars:
            # Step 2: reduce AX budget
            context = _assemble(_ax_lines(ax_nodes[:25]), _ocr_lines(high_conf_ocr))

        if len(context) > self._max_context_chars:
            # Step 3: reduce both to minimum budget
            context = _assemble(_ax_lines(ax_nodes[:25]), _ocr_lines(high_conf_ocr[:15]))

        logger.debug(
            "_build_screen_context: %d AX nodes, %d OCR entries, %d chars",
            len(ax_nodes), len(deduped_ocr), len(context),
        )
        return context

    # -----------------------------------------------------------------------
    # Sprint 1.3: Full orchestrated pipeline with latency instrumentation
    # -----------------------------------------------------------------------

    async def run(self, intent: str) -> Tuple[GuidancePlan, Dict[str, float]]:
        """
        Orchestrates the full Sprint 1.3 pipeline:
          1. Screenshot capture (CaptureService, WS 8765)
          2. Accessibility element tree (AccessibilityBridge, WS 8766)
          3. OCR extraction (Tesseract, optional)
          4. Context fusion (_build_screen_context)
          5. GuidancePlan generation (Gemma 4 via Ollama)

        Returns
        -------
        (GuidancePlan, latency_ms)
            `latency_ms` is a dict with keys:
              capture_ms, accessibility_ms, ocr_ms,
              context_build_ms, inference_ms, total_ms
            All values are wall-clock milliseconds (time.monotonic-based).
            The dict is logged at INFO level after every run.
        """
        t_total = time.monotonic()
        latency_ms: Dict[str, float] = {
            "capture_ms": 0.0,
            "accessibility_ms": 0.0,
            "ocr_ms": 0.0,
            "context_build_ms": 0.0,
            "inference_ms": 0.0,
            "total_ms": 0.0,
        }

        # Phase R4: Delegating perception gathering to Coordinator
        # Active window logic usually implies pid=0 for frontmost
        perception = await self.coordinator.get_perception(0, intent)

        screen_context = perception.to_text()
        
        image_base64 = ""
        if perception.mode == "vision" and perception.raw_data:
            image_base64 = perception.raw_data.get("image_base64", "")

        # 5. GuidancePlan generation
        t0 = time.monotonic()
        plan = await self.generate_guidance_plan(intent, image_base64, screen_context)
        latency_ms["inference_ms"] = (time.monotonic() - t0) * 1000

        # Phase R5: Attach perception mode for downstream telemetry tracking
        plan.perception_mode = perception.mode

        latency_ms["total_ms"] = (time.monotonic() - t_total) * 1000
        logger.info(
            "VSLMPipeline.run completed: %s",
            " | ".join(f"{k}={v:.0f}ms" for k, v in latency_ms.items()),
        )
        return plan, latency_ms

    def _clean_json_response(self, text: str) -> str:
        """
        Helper to strip markdown JSON codeblock markers and whitespace.
        """
        cleaned = text.strip()
        # Find JSON blocks: ```json ... ```
        pattern = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
        match = pattern.search(cleaned)
        if match:
            cleaned = match.group(1).strip()
        return cleaned
