"""
models.py — Ghost Cursor Pydantic schemas.

Sprint 1.2: GuidancePlanStep, GuidancePlan
Sprint 1.3: ScreenRect, OCREntry added; GuidancePlan gains schema_version.

Versioning contract
-------------------
- schema_version defaults to "1" so all Sprint 1.2 test fixtures that do not
  include the field continue to validate without modification.
- Future schema versions use Literal["2"] etc. and add ONLY new OPTIONAL fields.
  No existing required field is ever removed or changed in a prior version string.
- Consumers must check schema_version before applying version-specific logic.
"""

from pydantic import BaseModel, Field
from typing import List, Literal, Tuple


# ---------------------------------------------------------------------------
# Coordinate model (canonical ScreenRect — stable for Branch 2)
# ---------------------------------------------------------------------------

class ScreenRect(BaseModel):
    """
    Canonical screen coordinate format used by all Ghost Cursor components.

    Origin: top-left corner of the primary display.
    Units: logical pixels (same convention as macOS CGPoint via kAXPositionAttribute
    and pytesseract image_to_data output — no conversion required for either source).
    """
    x: int = Field(description="Left edge of element in screen coordinates")
    y: int = Field(description="Top edge of element in screen coordinates")
    width: int = Field(description="Element width in logical pixels")
    height: int = Field(description="Element height in logical pixels")


# ---------------------------------------------------------------------------
# OCR result model
# ---------------------------------------------------------------------------

class OCREntry(BaseModel):
    """A single text token detected by Tesseract OCR."""
    text: str = Field(description="Detected text, stripped, max 80 chars")
    confidence: float = Field(description="Normalised confidence 0.0–1.0")
    rect: ScreenRect = Field(description="Position and size in canonical ScreenRect format")


# ---------------------------------------------------------------------------
# GuidancePlan schema (v1)
# ---------------------------------------------------------------------------

class GuidancePlanStep(BaseModel):
    action: Literal["click", "type", "scroll", "navigate"]
    target_selector: str = Field(description="CSS selector or human-readable description of target element")
    fallback_coords: Tuple[int, int] = Field(description="Fallback pixel coordinates [x, y] on the screen")
    expected_outcome: str = Field(description="Description of visual state change after this step")


class GuidancePlan(BaseModel):
    """
    Structured execution plan produced by the VSLM pipeline.

    schema_version
        Frozen at "1" for Sprint 1.3.  Branch 2 may introduce "2" by adding
        new OPTIONAL fields only.  This field defaults to "1" so Sprint 1.2
        golden test fixtures (which omit it) continue to validate unchanged.
    """
    schema_version: Literal["1"] = "1"
    steps: List[GuidancePlanStep]
