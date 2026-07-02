"""
ocr_extractor.py — Sprint 1.3

Wraps pytesseract to extract OCR text from a base64-encoded PNG.
Returns a list of OCREntry objects, each carrying normalised ScreenRect
coordinates and a confidence score.

All failure conditions are handled without raising exceptions:

  ImportError / pytesseract missing  → WARNING + return []
  Tesseract binary missing            → WARNING + return []
  asyncio.TimeoutError (> timeout)    → WARNING + return []
  Empty result (no text above thresh) → INFO    + return []
  Any unexpected exception            → ERROR   + return []
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import time
from dataclasses import dataclass
from typing import List

from screen_understanding import ScreenRect

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Import guard: pytesseract is optional in the ghost-cursor environment
# ---------------------------------------------------------------------------

try:
    import pytesseract
    from PIL import Image as _PIL_Image
    _HAS_TESSERACT = True
except ImportError:
    _HAS_TESSERACT = False
    logger.warning(
        "pytesseract / PIL not importable; OCR disabled for this session. "
        "GuidancePlan generation will rely on screenshot + Accessibility data only."
    )


# ---------------------------------------------------------------------------
# OCR result type
# ---------------------------------------------------------------------------

@dataclass
class OCREntry:
    """A single text token detected by Tesseract OCR."""
    text: str           # raw detected text (stripped)
    confidence: float   # normalised 0.0–1.0
    rect: ScreenRect    # position on screen (canonical ScreenRect)

    def to_prompt_line(self) -> str:
        """Compact representation for LLM prompt inclusion."""
        label = self.text[:80]
        cx, cy = self.rect.centre
        return f"[OCR] \"{label}\" conf={self.confidence:.2f} at ({self.rect.x},{self.rect.y}) size {self.rect.width}x{self.rect.height}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def extract_text(
    image_base64: str,
    timeout: float = 8.0,
    confidence_threshold: float = 0.60,
) -> List[OCREntry]:
    """
    Decodes `image_base64` (PNG/JPEG base64 string) and runs Tesseract OCR
    in a thread pool to avoid blocking the event loop.

    Parameters
    ----------
    image_base64 : str
        Base64-encoded PNG or JPEG image bytes.
    timeout : float
        Maximum seconds to wait for OCR (default 8.0).  Enforced via
        asyncio.wait_for around the thread pool call.
    confidence_threshold : float
        Minimum normalised confidence (0.0–1.0).  Entries below this value
        are filtered out.  Default 0.60.

    Returns
    -------
    List[OCREntry]
        Filtered, confidence-sorted OCR results.  Empty list on any failure.
    """
    if not _HAS_TESSERACT:
        # Warning already logged at import time; return silently here.
        return []

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_run_ocr_sync, image_base64, confidence_threshold),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "OCR extraction timed out after %.0fs; proceeding without OCR results.", timeout
        )
        return []
    except EnvironmentError as exc:
        logger.warning(
            "Tesseract binary not found or unusable: %s; OCR skipped.", exc
        )
        return []
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "OCR extraction failed unexpectedly (%s: %s); returning empty results.",
            type(exc).__name__, exc,
        )
        return []


# ---------------------------------------------------------------------------
# Synchronous OCR worker (runs in thread pool via asyncio.to_thread)
# ---------------------------------------------------------------------------

def _run_ocr_sync(image_base64: str, confidence_threshold: float) -> List[OCREntry]:
    """
    Called inside asyncio.to_thread.  Decodes the image, invokes Tesseract,
    and filters + normalises results.

    Raises EnvironmentError if the Tesseract binary is not present.
    Raises ValueError if base64 decoding fails.
    """
    # Decode base64 → PIL Image
    image_bytes = base64.b64decode(image_base64)
    image = _PIL_Image.open(io.BytesIO(image_bytes)).convert("RGB")

    # Run OCR — may raise pytesseract.TesseractNotFoundError (subclass of EnvironmentError)
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)

    results: List[OCREntry] = []
    n = len(data["text"])
    for i in range(n):
        raw_text = (data["text"][i] or "").strip()
        if not raw_text:
            continue

        raw_conf = data["conf"][i]
        # pytesseract returns -1 for layout-only rows with no confidence
        if raw_conf < 0:
            continue

        conf_normalised = float(raw_conf) / 100.0
        if conf_normalised < confidence_threshold:
            continue

        x = int(data["left"][i])
        y = int(data["top"][i])
        w = int(data["width"][i])
        h = int(data["height"][i])

        # Skip zero-size entries
        if w <= 0 or h <= 0:
            continue

        results.append(OCREntry(
            text=raw_text[:80],         # truncate to budget limit
            confidence=conf_normalised,
            rect=ScreenRect(x=x, y=y, width=w, height=h),
        ))

    if not results:
        logger.info("OCR returned no text above confidence threshold %.0f%%.", confidence_threshold * 100)

    # Return sorted by confidence descending (highest-confidence first for budget slicing)
    results.sort(key=lambda e: e.confidence, reverse=True)
    return results
