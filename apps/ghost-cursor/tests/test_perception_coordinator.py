import pytest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from unittest.mock import AsyncMock, MagicMock
from perception_source import PerceptionSource, PerceptionResult
from screen_understanding import ScreenElement, ScreenContext
from perception_coordinator import PerceptionCoordinator, AccessibilityPermissionError

@pytest.fixture
def ax_reader():
    reader = AsyncMock()
    # Give it a probe method stub returning True by default
    reader.probe_finder_succeeds = AsyncMock(return_value=True)
    return reader

@pytest.fixture
def vision_reader():
    reader = AsyncMock()
    return reader

@pytest.fixture
def coordinator(ax_reader, vision_reader):
    return PerceptionCoordinator(ax_reader, vision_reader)

def create_mock_ax_result(error_code=None, elements=None):
    if elements is None:
        elements = []
    
    screen_ctx = ScreenContext(elements=elements, element_count=len(elements), available=True)
    
    return PerceptionResult(
        mode="ax",
        payload="ax_payload",
        element_count=len(elements),
        confidence_ok=True,
        error_code=error_code,
        raw_data=screen_ctx
    )

def create_element(role="AXButton", title="Submit"):
    return ScreenElement(
        element_id="1", role=role, title=title, value="", description="",
        rect=MagicMock()
    )

@pytest.mark.asyncio
async def test_ax_api_disabled_raises_error(coordinator, ax_reader):
    ax_reader.read.return_value = create_mock_ax_result(error_code="kAXErrorAPIDisabled")
    
    with pytest.raises(AccessibilityPermissionError, match="disabled"):
        await coordinator.get_perception(123, "click")

@pytest.mark.asyncio
async def test_cannot_complete_finder_fails_raises_error(coordinator, ax_reader):
    ax_reader.read.return_value = create_mock_ax_result(error_code="kAXErrorCannotComplete")
    ax_reader.probe_finder_succeeds.return_value = False
    
    with pytest.raises(AccessibilityPermissionError, match="failing globally"):
        await coordinator.get_perception(123, "click")

@pytest.mark.asyncio
async def test_cannot_complete_finder_succeeds_falls_back(coordinator, ax_reader, vision_reader):
    ax_reader.read.return_value = create_mock_ax_result(error_code="kAXErrorCannotComplete")
    ax_reader.probe_finder_succeeds.return_value = True
    vision_reader.read.return_value = PerceptionResult(mode="vision", payload="vision_payload", element_count=1, confidence_ok=True)
    
    result = await coordinator.get_perception(123, "click")
    assert result.mode == "vision"
    vision_reader.read.assert_awaited_once_with(123)

@pytest.mark.asyncio
async def test_sufficient_ax_tree_returns_ax(coordinator, ax_reader):
    # 3 actionable, labeled elements
    elements = [
        create_element(role="AXButton", title="Btn1"),
        create_element(role="AXButton", title="Btn2"),
        create_element(role="AXButton", title="Btn3")
    ]
    ax_reader.read.return_value = create_mock_ax_result(elements=elements)
    
    result = await coordinator.get_perception(123, "click")
    assert result.mode == "ax"

@pytest.mark.asyncio
async def test_insufficient_ax_tree_falls_back_vision(coordinator, ax_reader, vision_reader):
    # 2 actionable, labeled elements (below MIN_ACTIONABLE_ELEMENTS=3)
    elements = [
        create_element(role="AXButton", title="Btn1"),
        create_element(role="AXButton", title="Btn2")
    ]
    ax_reader.read.return_value = create_mock_ax_result(elements=elements)
    vision_reader.read.return_value = PerceptionResult(mode="vision", payload="vision_payload", element_count=1, confidence_ok=True)
    
    result = await coordinator.get_perception(123, "click")
    assert result.mode == "vision"
    vision_reader.read.assert_awaited_once_with(123)

@pytest.mark.asyncio
async def test_insufficient_labeled_ratio_falls_back_vision(coordinator, ax_reader, vision_reader):
    # 3 actionable elements, but only 1 labeled (ratio 33% < 60%)
    elements = [
        create_element(role="AXButton", title="Btn1"),
        create_element(role="AXButton", title=""),
        create_element(role="AXButton", title="")
    ]
    ax_reader.read.return_value = create_mock_ax_result(elements=elements)
    vision_reader.read.return_value = PerceptionResult(mode="vision", payload="vision_payload", element_count=1, confidence_ok=True)
    
    result = await coordinator.get_perception(123, "click")
    assert result.mode == "vision"
    vision_reader.read.assert_awaited_once_with(123)
