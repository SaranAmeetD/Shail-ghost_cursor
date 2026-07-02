"""
screen_understanding.py — Sprint 1.3

Fetches the active window's element tree from AccessibilityBridge
(ws://localhost:8766/accessibility) using the `get_window_elements` command.

Normalises each element into the canonical ScreenRect coordinate format
(top-left origin, logical pixels) and returns a ScreenContext dataclass.

All failure modes (connection refused, timeout, malformed JSON, success=false)
are caught and result in an empty ScreenContext — never an unhandled exception.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional

import websockets

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Canonical coordinate type (stable for Branch 2)
# ---------------------------------------------------------------------------

@dataclass
class ScreenRect:
    """
    Canonical screen coordinate format used throughout Ghost Cursor.

    Origin: top-left corner of the primary display.
    All values are in logical pixels (not physical / Retina pixels).
    macOS CGPoint via kAXPositionAttribute uses this convention natively.
    OCR output from pytesseract also uses top-left origin — no conversion needed.

    fallback_coords centre point:  (x + width // 2,  y + height // 2)
    """
    x: int
    y: int
    width: int
    height: int

    @property
    def centre(self) -> tuple[int, int]:
        """Returns the element centre point for use as fallback_coords."""
        return (self.x + self.width // 2, self.y + self.height // 2)

    def contains_point(self, px: int, py: int, margin: int = 0) -> bool:
        """Returns True if (px, py) falls within the rect (inclusive, inflated by margin)."""
        return (
            (self.x - margin) <= px <= (self.x + self.width + margin)
            and (self.y - margin) <= py <= (self.y + self.height + margin)
        )


# ---------------------------------------------------------------------------
# Element and context dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ScreenElement:
    """A single UI element returned by the AccessibilityBridge element tree query."""
    element_id: str
    role: str
    title: str
    value: str
    description: str
    rect: ScreenRect

    @property
    def best_label(self) -> str:
        """Returns the most descriptive non-empty label for deduplication."""
        return self.title or self.description or self.value

    def to_prompt_line(self) -> str:
        """Compact one-line representation for LLM prompt inclusion."""
        label = self.best_label[:120]
        cx, cy = self.rect.centre
        return f"[{self.role}] \"{label}\" at ({self.rect.x},{self.rect.y}) size {self.rect.width}x{self.rect.height} centre ({cx},{cy})"


@dataclass
class ScreenContext:
    """
    Aggregated screen state returned by fetch_screen_elements.

    Always safe to use: `elements` is an empty list when the bridge
    is unavailable or returns an error.
    """
    application: dict = field(default_factory=dict)    # {"name": str, "bundle_id": str, "pid": int}
    active_window: dict = field(default_factory=dict)  # {"title": str, "x":int, "y":int, "width":int, "height":int}
    elements: List[ScreenElement] = field(default_factory=list)
    element_count: int = 0
    timestamp: str = ""
    available: bool = False   # False when bridge was unreachable or returned an error


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_screen_elements(
    ax_uri: str = "ws://localhost:8766/accessibility",
    timeout: float = 5.0,
) -> ScreenContext:
    """
    Requests the bounded element tree from AccessibilityBridge.

    Sends: {"command": "get_window_elements"}
    Expects: extensible response envelope (see architecture plan §4.2)

    Returns an empty ScreenContext (available=False) on any failure —
    never raises an exception to the caller.

    Timeout: `timeout` seconds for both connect and recv, enforced via
    asyncio.wait_for.
    """
    t_start = time.monotonic()
    try:
        return await asyncio.wait_for(
            _fetch(ax_uri),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        elapsed = (time.monotonic() - t_start) * 1000
        logger.warning(
            "AccessibilityBridge timed out after %.0fms (limit %.0fs) at %s; "
            "proceeding without element map.",
            elapsed, timeout, ax_uri,
        )
        return ScreenContext()
    except Exception as exc:
        logger.warning(
            "AccessibilityBridge unavailable (%s: %s); "
            "proceeding with screenshot + OCR only.",
            type(exc).__name__, exc,
        )
        return ScreenContext()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _fetch(ax_uri: str) -> ScreenContext:
    """
    Inner coroutine (no timeout guard — caller wraps with wait_for).
    Separated so the outer function can apply a single clean timeout.
    """
    try:
        async with websockets.connect(ax_uri) as ws:
            await ws.send(json.dumps({"command": "get_window_elements"}))
            raw = await ws.recv()
    except ConnectionRefusedError as exc:
        logger.warning(
            "AccessibilityBridge connection refused at %s: %s", ax_uri, exc
        )
        return ScreenContext()

    # --- Parse response ---
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning(
            "AccessibilityBridge returned malformed JSON: %s (raw: %.120s…)",
            exc, raw,
        )
        return ScreenContext()

    if not data.get("success"):
        error_msg = data.get("error", "(no error field)")
        logger.warning(
            "AccessibilityBridge returned success=false: %s", error_msg
        )
        return ScreenContext(
            application=data.get("application", {}),
            active_window=data.get("active_window", {}),
            elements=[],
            element_count=0,
            timestamp=data.get("timestamp", ""),
            available=False,
        )

    # --- Normalise elements ---
    raw_elements: list = data.get("elements", [])
    elements: List[ScreenElement] = []
    for raw_elem in raw_elements:
        parsed = _parse_element(raw_elem)
        if parsed is not None:
            elements.append(parsed)

    ctx = ScreenContext(
        application=data.get("application", {}),
        active_window=data.get("active_window", {}),
        elements=elements,
        element_count=len(elements),
        timestamp=data.get("timestamp", ""),
        available=True,
    )
    logger.debug(
        "AccessibilityBridge: %d elements from %s/%s",
        ctx.element_count,
        ctx.application.get("name", "?"),
        ctx.active_window.get("title", "?"),
    )
    return ctx


def _parse_element(raw: dict) -> Optional[ScreenElement]:
    """
    Converts a raw dict from the WS response into a ScreenElement.

    The AX response uses {x, y, width, height} keys — the canonical ScreenRect
    format. The `bbox` array used in older AccessibilityBridge events is NOT
    present in the get_window_elements response and is intentionally ignored here.
    Returns None for malformed entries (missing required keys).
    """
    try:
        rect = ScreenRect(
            x=int(raw["x"]),
            y=int(raw["y"]),
            width=int(raw["width"]),
            height=int(raw["height"]),
        )
        return ScreenElement(
            element_id=str(raw.get("element_id", "")),
            role=str(raw.get("role", "")),
            title=str(raw.get("title", "")),
            value=str(raw.get("value", "")),
            description=str(raw.get("description", "")),
            rect=rect,
        )
    except (KeyError, TypeError, ValueError) as exc:
        logger.debug("Skipping malformed element %s: %s", raw, exc)
        return None
