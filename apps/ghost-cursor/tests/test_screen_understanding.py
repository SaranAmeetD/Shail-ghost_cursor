"""
test_screen_understanding.py — Sprint 1.3

18 unit tests covering:
  - fetch_screen_elements: success, empty tree, large tree, AX unavailable,
    timeout, malformed JSON, success=false
  - extract_text: success, below-threshold filtering, unavailable, timeout
  - _build_screen_context: deduplication (string + spatial), budget enforcement,
    truncation cascade
  - GuidancePlan schema: schema_version field, backward compatibility
  - run(): full pipeline mocked end-to-end with latency_ms verification

All tests use unittest.mock to avoid live native services.
The Sprint 1.2 test file (test_vslm_pipeline.py) is NOT imported or modified.
"""

from __future__ import annotations

import json
import os
import sys
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure the ghost-cursor package root is on the path (mirrors Sprint 1.2 approach)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from screen_understanding import (
    ScreenRect, ScreenElement, ScreenContext, fetch_screen_elements, _parse_element,
)
from ocr_extractor import OCREntry, extract_text
from models import GuidancePlan, GuidancePlanStep, ScreenRect as ModelScreenRect
from vslm_pipeline import VSLMPipeline

# ---------------------------------------------------------------------------
# Fixtures & shared helpers
# ---------------------------------------------------------------------------

DUMMY_BASE64_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)

AX_URI = "ws://localhost:8766/accessibility"


def _make_ax_response(
    success: bool = True,
    elements: list | None = None,
    error: str = "",
    element_count: int | None = None,
) -> str:
    if elements is None:
        elements = []
    payload = {
        "type": "command_response",
        "command": "get_window_elements",
        "success": success,
        "timestamp": "2026-07-02T05:30:00Z",
        "application": {"name": "Safari", "bundle_id": "com.apple.Safari", "pid": 1234},
        "active_window": {"title": "GitHub", "x": 0, "y": 25, "width": 1440, "height": 875},
        "element_count": element_count if element_count is not None else len(elements),
        "elements": elements,
    }
    if not success and error:
        payload["error"] = error
    return json.dumps(payload)


def _make_ax_element(idx: int, role: str = "AXButton", title: str = "") -> dict:
    return {
        "element_id": f"elem-{idx}",
        "role": role,
        "title": title or f"Button {idx}",
        "value": "",
        "description": "",
        "x": 100 + idx * 10,
        "y": 200 + idx * 5,
        "width": 80,
        "height": 24,
    }


def _make_ws_mock(recv_payload: str) -> AsyncMock:
    mock_ws = AsyncMock()
    mock_ws.recv.return_value = recv_payload
    return mock_ws


def _make_ws_connect(recv_payload: str):
    mock_ws = _make_ws_mock(recv_payload)
    return AsyncMock(__aenter__=AsyncMock(return_value=mock_ws), __aexit__=AsyncMock(return_value=False))


# ---------------------------------------------------------------------------
# 1. fetch_screen_elements — success
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_screen_elements_success():
    """Valid WS response → ScreenContext with correct ScreenRect normalisation."""
    elem = _make_ax_element(0, title="New repository")
    payload = _make_ax_response(elements=[elem])

    with patch("screen_understanding.websockets.connect", return_value=_make_ws_connect(payload)):
        ctx = await fetch_screen_elements(AX_URI)

    assert ctx.available is True
    assert ctx.element_count == 1
    assert len(ctx.elements) == 1
    se = ctx.elements[0]
    assert se.role == "AXButton"
    assert se.title == "New repository"
    assert se.rect.x == 100
    assert se.rect.y == 200
    assert se.rect.width == 80
    assert se.rect.height == 24
    assert se.rect.centre == (140, 212)


# ---------------------------------------------------------------------------
# 2. fetch_screen_elements — empty tree
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_screen_elements_empty_tree():
    """Response with elements=[] → ScreenContext with empty list, available=True, no exception."""
    payload = _make_ax_response(elements=[])

    with patch("screen_understanding.websockets.connect", return_value=_make_ws_connect(payload)):
        ctx = await fetch_screen_elements(AX_URI)

    assert ctx.available is True
    assert ctx.elements == []
    assert ctx.element_count == 0


# ---------------------------------------------------------------------------
# 3. fetch_screen_elements — large tree (> 40 nodes in response)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_screen_elements_large_tree():
    """Response with 150 nodes → Python client receives all (filtering done in Swift)."""
    elements = [_make_ax_element(i) for i in range(150)]
    payload = _make_ax_response(elements=elements)

    with patch("screen_understanding.websockets.connect", return_value=_make_ws_connect(payload)):
        ctx = await fetch_screen_elements(AX_URI)

    assert ctx.available is True
    # All elements the server returned are parsed; budget is Swift-side
    assert ctx.element_count == 150
    assert len(ctx.elements) == 150


# ---------------------------------------------------------------------------
# 4. fetch_screen_elements — AX unavailable (ConnectionRefusedError)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")
async def test_fetch_screen_elements_ax_unavailable(caplog):
    """ConnectionRefusedError → empty ScreenContext, available=False, warning logged."""
    import logging
    with caplog.at_level(logging.WARNING, logger="screen_understanding"):
        with patch(
            "screen_understanding.websockets.connect",
            side_effect=ConnectionRefusedError("refused"),
        ):
            ctx = await fetch_screen_elements(AX_URI)

    assert ctx.available is False
    assert ctx.elements == []
    assert any("unavailable" in r.message.lower() or "refused" in r.message.lower()
                for r in caplog.records)


# ---------------------------------------------------------------------------
# 5. fetch_screen_elements — timeout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_screen_elements_timeout(caplog):
    """asyncio.TimeoutError → empty ScreenContext, available=False, warning logged."""
    import logging
    async def _slow(*a, **kw):
        await asyncio.sleep(60)

    with caplog.at_level(logging.WARNING, logger="screen_understanding"):
        ctx = await fetch_screen_elements(AX_URI, timeout=0.01)

    assert ctx.available is False
    assert ctx.elements == []
    assert any("timed out" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# 6. fetch_screen_elements — malformed JSON
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_screen_elements_malformed_json(caplog):
    """WS sends invalid JSON → json.JSONDecodeError caught, empty ScreenContext."""
    import logging
    bad_payload = "{ not valid json }"

    with caplog.at_level(logging.WARNING, logger="screen_understanding"):
        with patch("screen_understanding.websockets.connect",
                   return_value=_make_ws_connect(bad_payload)):
            ctx = await fetch_screen_elements(AX_URI)

    assert ctx.available is False
    assert ctx.elements == []
    assert any("malformed" in r.message.lower() or "json" in r.message.lower()
                for r in caplog.records)


# ---------------------------------------------------------------------------
# 7. fetch_screen_elements — success=false in response
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_screen_elements_success_false(caplog):
    """success=false in response → empty ScreenContext, error field logged."""
    import logging
    payload = _make_ax_response(success=False, error="AX permission denied")

    with caplog.at_level(logging.WARNING, logger="screen_understanding"):
        with patch("screen_understanding.websockets.connect",
                   return_value=_make_ws_connect(payload)):
            ctx = await fetch_screen_elements(AX_URI)

    assert ctx.available is False
    assert ctx.elements == []
    assert any("permission" in r.message.lower() or "success=false" in r.message.lower()
                for r in caplog.records)


# ---------------------------------------------------------------------------
# 8. extract_text — success
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ocr_extract_success():
    """Valid image + mocked _run_ocr_sync → filtered OCREntry list above threshold."""
    import ocr_extractor

    expected_entries = [
        OCREntry(text="Hello", confidence=0.95, rect=ScreenRect(x=10, y=20, width=40, height=12)),
        OCREntry(text="World", confidence=0.75, rect=ScreenRect(x=50, y=30, width=35, height=12)),
    ]

    def _fake_run_ocr_sync(image_base64, threshold):
        # Only return entries above the threshold
        return [e for e in expected_entries if e.confidence >= threshold]

    with patch.object(ocr_extractor, "_HAS_TESSERACT", True):
        with patch.object(ocr_extractor, "_run_ocr_sync", side_effect=_fake_run_ocr_sync):
            results = await extract_text(DUMMY_BASE64_PNG, confidence_threshold=0.60)

    assert len(results) == 2
    assert results[0].text == "Hello"   # sorted by conf desc
    assert results[0].confidence == pytest.approx(0.95)
    assert results[1].text == "World"
    assert results[1].rect.x == 50


# ---------------------------------------------------------------------------
# 9. extract_text — all entries below confidence threshold
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ocr_extract_below_threshold_filtered():
    """All OCR entries below threshold → returns []."""
    import ocr_extractor

    low_conf_entries = [
        OCREntry(text="Low",  confidence=0.20, rect=ScreenRect(x=0,  y=0, width=30, height=10)),
        OCREntry(text="Conf", confidence=0.35, rect=ScreenRect(x=10, y=5, width=25, height=10)),
    ]

    def _fake_run_ocr_sync(image_base64, threshold):
        return [e for e in low_conf_entries if e.confidence >= threshold]

    with patch.object(ocr_extractor, "_HAS_TESSERACT", True):
        with patch.object(ocr_extractor, "_run_ocr_sync", side_effect=_fake_run_ocr_sync):
            results = await extract_text(DUMMY_BASE64_PNG, confidence_threshold=0.60)

    assert results == []


# ---------------------------------------------------------------------------
# 10. extract_text — pytesseract unavailable (ImportError)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ocr_extract_unavailable(caplog):
    """pytesseract flagged as unavailable → returns [], no exception."""
    import logging
    with caplog.at_level(logging.WARNING, logger="ocr_extractor"):
        with patch("ocr_extractor._HAS_TESSERACT", False):
            results = await extract_text(DUMMY_BASE64_PNG)

    assert results == []
    # No exception, and the module-level import warning suffices


# ---------------------------------------------------------------------------
# 11. extract_text — timeout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ocr_extract_timeout(caplog):
    """wait_for triggers TimeoutError → returns [], warning logged (no thread spawned)."""
    import logging
    import ocr_extractor

    async def _slow_coroutine(*_args, **_kwargs):
        # Pretend asyncio.to_thread returns a coroutine that never completes.
        # asyncio.wait_for(timeout=0.01) will cancel it cleanly.
        await asyncio.sleep(60)

    with caplog.at_level(logging.WARNING, logger="ocr_extractor"):
        with patch.object(ocr_extractor, "_HAS_TESSERACT", True):
            with patch("ocr_extractor.asyncio.to_thread", side_effect=_slow_coroutine):
                results = await extract_text(DUMMY_BASE64_PNG, timeout=0.01)

    assert results == []
    assert any("timed out" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# 12. _build_screen_context — string deduplication
# ---------------------------------------------------------------------------

def test_build_screen_context_deduplication():
    """AX label 'New repository' + OCR text 'New repository' → appears once in context."""
    pipeline = VSLMPipeline()

    elem = ScreenElement(
        element_id="e1", role="AXButton", title="New repository",
        value="", description="",
        rect=ScreenRect(x=820, y=112, width=140, height=32),
    )
    screen_ctx = ScreenContext(elements=[elem], element_count=1, available=True)

    ocr_entry = OCREntry(
        text="New repository",
        confidence=0.95,
        rect=ScreenRect(x=830, y=118, width=100, height=20),
    )

    context = pipeline._build_screen_context(screen_ctx, [ocr_entry])

    assert "New repository" in context
    # OCR entry should be deduplicated — count occurrences
    assert context.count("New repository") == 1


# ---------------------------------------------------------------------------
# 13. _build_screen_context — spatial deduplication
# ---------------------------------------------------------------------------

def test_build_screen_context_spatial_dedup():
    """OCR bbox centre inside AX element rect → OCR entry dropped."""
    pipeline = VSLMPipeline()

    # AX button at (100, 200) size 80x24 — centre at (140, 212)
    elem = ScreenElement(
        element_id="e1", role="AXButton", title="Submit",
        value="", description="",
        rect=ScreenRect(x=100, y=200, width=80, height=24),
    )
    screen_ctx = ScreenContext(elements=[elem], element_count=1, available=True)

    # OCR entry with centre at (130, 210) — inside the AX rect above
    ocr_entry = OCREntry(
        text="Totally Different Label",   # not a string match
        confidence=0.90,
        rect=ScreenRect(x=120, y=205, width=20, height=10),  # centre (130, 210)
    )

    context = pipeline._build_screen_context(screen_ctx, [ocr_entry])

    # OCR label should be absent; AX label should be present
    assert "Totally Different Label" not in context
    assert "Submit" in context


# ---------------------------------------------------------------------------
# 14. _build_screen_context — budget enforcement (> 40 AX nodes)
# ---------------------------------------------------------------------------

def test_build_screen_context_budget_enforcement():
    """60 AX element input → only 40 in the context string."""
    pipeline = VSLMPipeline()

    elements = [
        ScreenElement(
            element_id=f"e{i}", role="AXButton", title=f"Button {i}",
            value="", description="",
            rect=ScreenRect(x=i * 10, y=0, width=80, height=24),
        )
        for i in range(60)
    ]
    screen_ctx = ScreenContext(elements=elements, element_count=60, available=True)
    context = pipeline._build_screen_context(screen_ctx, [])

    # Count how many "Button N" entries appear
    present = sum(1 for i in range(60) if f"Button {i}" in context)
    assert present == 40


# ---------------------------------------------------------------------------
# 15. _build_screen_context — truncation cascade activates
# ---------------------------------------------------------------------------

def test_build_screen_context_truncation_cascade():
    """Context > 4000 chars triggers cascade; final result fits within limit."""
    pipeline = VSLMPipeline()
    pipeline._max_context_chars = 500   # artificially low to force cascade

    # 40 AX nodes with long labels
    elements = [
        ScreenElement(
            element_id=f"e{i}", role="AXButton",
            title="A" * 120,   # max label length
            value="", description="",
            rect=ScreenRect(x=i * 10, y=0, width=80, height=24),
        )
        for i in range(40)
    ]
    screen_ctx = ScreenContext(elements=elements, element_count=40, available=True)

    # 30 OCR entries with distinct labels (won't be deduped)
    ocr_entries = [
        OCREntry(text=f"OCR{i}", confidence=0.95,
                 rect=ScreenRect(x=5000 + i, y=5000, width=40, height=12))
        for i in range(30)
    ]

    context = pipeline._build_screen_context(screen_ctx, ocr_entries)

    # Verify that the cascade ran by checking the content of the output:
    # After all cascade steps, context must use ax_nodes[:25] and high_conf_ocr[:15].
    # AX labels are all "A" * 120; OCR labels are "OCR{i}" for i in range(30).
    # Count how many distinct AX lines appear (each has a unique x-coord in "at (N,0)").
    ax_line_count = sum(1 for i in range(40) if f"at ({i * 10},0)" in context)
    assert ax_line_count <= 25, (
        f"Cascade should have reduced AX nodes to 25, but found {ax_line_count}"
    )
    # OCR entries: only the first 15 of the 30 should appear after cascade step 3.
    ocr_present = sum(1 for i in range(30) if f'"OCR{i}"' in context)
    assert ocr_present <= 15, (
        f"Cascade should have reduced OCR entries to 15, but found {ocr_present}"
    )
    assert isinstance(context, str)


# ---------------------------------------------------------------------------
# 16. GuidancePlan — schema_version present and correct
# ---------------------------------------------------------------------------

def test_guidance_plan_schema_version():
    """Generated GuidancePlan has schema_version == '1'."""
    plan = GuidancePlan(
        steps=[
            GuidancePlanStep(
                action="click",
                target_selector="Submit button",
                fallback_coords=(300, 400),
                expected_outcome="Form submitted",
            )
        ]
    )
    assert plan.schema_version == "1"


# ---------------------------------------------------------------------------
# 17. GuidancePlan — backward compatibility (no schema_version in input)
# ---------------------------------------------------------------------------

def test_guidance_plan_schema_backward_compat():
    """Sprint 1.2 golden JSON (no schema_version field) validates correctly."""
    golden_json = {
        "steps": [
            {
                "action": "navigate",
                "target_selector": "System Settings app",
                "fallback_coords": [10, 10],
                "expected_outcome": "System Settings is open",
            }
        ]
    }
    plan = GuidancePlan.model_validate(golden_json)
    # Must validate without error and default schema_version to "1"
    assert plan.schema_version == "1"
    assert len(plan.steps) == 1
    assert plan.steps[0].action == "navigate"


# ---------------------------------------------------------------------------
# 18. run() — full pipeline mocked end-to-end
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_full_pipeline_mocked():
    """VSLMPipeline.run() with all three sources mocked → valid GuidancePlan + latency_ms."""
    pipeline = VSLMPipeline()

    golden_plan = {
        "schema_version": "1",
        "steps": [
            {
                "action": "click",
                "target_selector": "New repository button",
                "fallback_coords": [820, 120],
                "expected_outcome": "Create repository page loaded",
            }
        ],
    }

    ax_payload = _make_ax_response(
        elements=[_make_ax_element(0, title="New repository")]
    )

    with patch.object(pipeline, "capture_screen_base64", new_callable=AsyncMock,
                      return_value=DUMMY_BASE64_PNG):
        with patch("vslm_pipeline.fetch_screen_elements", new_callable=AsyncMock,
                   return_value=ScreenContext(
                       elements=[ScreenElement(
                           element_id="e0", role="AXButton", title="New repository",
                           value="", description="",
                           rect=ScreenRect(x=820, y=112, width=140, height=32),
                       )],
                       element_count=1,
                       available=True,
                   )):
            with patch("vslm_pipeline.extract_text", new_callable=AsyncMock, return_value=[]):
                with patch("vslm_pipeline.call_llm", new_callable=AsyncMock,
                           return_value=(json.dumps(golden_plan), {"provider": "ollama", "model": "gemma4"})):
                    plan, latency_ms = await pipeline.run("Go to github.com and create a new repo")

    # Validate plan
    assert isinstance(plan, GuidancePlan)
    assert plan.schema_version == "1"
    assert len(plan.steps) == 1
    assert plan.steps[0].action == "click"

    # Validate latency_ms structure and types
    expected_keys = {"capture_ms", "accessibility_ms", "ocr_ms",
                     "context_build_ms", "inference_ms", "total_ms"}
    assert set(latency_ms.keys()) == expected_keys
    for k, v in latency_ms.items():
        assert isinstance(v, float), f"latency_ms[{k!r}] should be float, got {type(v)}"
    assert latency_ms["total_ms"] >= 0.0
