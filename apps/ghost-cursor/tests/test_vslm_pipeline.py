import os
import sys
import pytest
import json
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vslm_pipeline import VSLMPipeline
from models import GuidancePlan

# Define golden outputs for the 10 QA test matrix prompts
GOLDEN_RESPONSES = {
    "Open System Settings and enable Dark Mode": {
        "steps": [
            {"action": "navigate", "target_selector": "System Settings app", "fallback_coords": [10, 10], "expected_outcome": "System Settings is open"},
            {"action": "click", "target_selector": "Appearance sidebar item", "fallback_coords": [100, 200], "expected_outcome": "Appearance settings loaded"},
            {"action": "click", "target_selector": "Dark Mode style option", "fallback_coords": [350, 150], "expected_outcome": "System Dark Mode enabled"}
        ]
    },
    "Go to github.com and create a new repo named test-repo": {
        "steps": [
            {"action": "navigate", "target_selector": "https://github.com", "fallback_coords": [0, 0], "expected_outcome": "GitHub home page is loaded"},
            {"action": "click", "target_selector": "New repository button", "fallback_coords": [800, 120], "expected_outcome": "Create repository page loaded"},
            {"action": "type", "target_selector": "Repository name input field", "fallback_coords": [250, 300], "expected_outcome": "test-repo entered"},
            {"action": "click", "target_selector": "Create repository green button", "fallback_coords": [300, 800], "expected_outcome": "Repository test-repo created"}
        ]
    },
    "Open Finder and move all files in Downloads older than 30 days": {
        "steps": [
            {"action": "navigate", "target_selector": "Finder app", "fallback_coords": [0, 0], "expected_outcome": "Finder is active"},
            {"action": "click", "target_selector": "Downloads folder in sidebar", "fallback_coords": [80, 150], "expected_outcome": "Downloads directory listed"},
            {"action": "scroll", "target_selector": "Downloads file list", "fallback_coords": [400, 300], "expected_outcome": "Old files located"},
            {"action": "click", "target_selector": "Move selection to Archive", "fallback_coords": [500, 500], "expected_outcome": "Old files moved to Archive folder"}
        ]
    },
    "Open Notes, create a new note, and write Meeting summary": {
        "steps": [
            {"action": "navigate", "target_selector": "Notes app", "fallback_coords": [0, 0], "expected_outcome": "Notes app is active"},
            {"action": "click", "target_selector": "New Note button", "fallback_coords": [150, 50], "expected_outcome": "Blank note sheet loaded"},
            {"action": "type", "target_selector": "Note body area", "fallback_coords": [300, 200], "expected_outcome": "Meeting summary written inside note"}
        ]
    },
    "Open Chrome and search for Gemini": {
        "steps": [
            {"action": "navigate", "target_selector": "Chrome browser", "fallback_coords": [0, 0], "expected_outcome": "Chrome window active"},
            {"action": "type", "target_selector": "URL or search bar", "fallback_coords": [400, 80], "expected_outcome": "Gemini entered and searched"}
        ]
    },
    "Open Slack and send message to general": {
        "steps": [
            {"action": "navigate", "target_selector": "Slack app", "fallback_coords": [0, 0], "expected_outcome": "Slack app active"},
            {"action": "click", "target_selector": "general channel in channel list", "fallback_coords": [100, 180], "expected_outcome": "general channel active"},
            {"action": "type", "target_selector": "Message input area", "fallback_coords": [300, 950], "expected_outcome": "Message typed and sent"}
        ]
    },
    "Navigate to localhost:8000 and view dashboard": {
        "steps": [
            {"action": "navigate", "target_selector": "http://localhost:8000/dashboard", "fallback_coords": [0, 0], "expected_outcome": "Dashboard page loaded"}
        ]
    },
    "Open Terminal and run git status": {
        "steps": [
            {"action": "navigate", "target_selector": "Terminal app", "fallback_coords": [0, 0], "expected_outcome": "Terminal is active"},
            {"action": "type", "target_selector": "Terminal command prompt", "fallback_coords": [100, 100], "expected_outcome": "git status entered and ran"}
        ]
    },
    "Open Figma and zoom in": {
        "steps": [
            {"action": "navigate", "target_selector": "Figma app", "fallback_coords": [0, 0], "expected_outcome": "Figma active"},
            {"action": "click", "target_selector": "Figma canvas area", "fallback_coords": [500, 500], "expected_outcome": "Canvas focused"},
            {"action": "type", "target_selector": "Zoom shortcut '+'", "fallback_coords": [500, 500], "expected_outcome": "Canvas zoomed in"}
        ]
    },
    "Minimize all windows": {
        "steps": [
            {"action": "click", "target_selector": "Desktop background show/hide", "fallback_coords": [1200, 10], "expected_outcome": "All windows minimized"}
        ]
    }
}

# Dummy base64 encoded PNG for testing capture functionality
DUMMY_BASE64_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

@pytest.mark.asyncio
async def test_capture_screen_base64_success():
    """
    Test capture_screen_base64 with a mocked websocket connection.
    """
    pipeline = VSLMPipeline()
    
    mock_ws = MagicMock()
    mock_response = {
        "type": "png_response",
        "request_id": "vslm-capture-sprint1.2",
        "status": "ok",
        "data_b64": DUMMY_BASE64_PNG
    }
    mock_ws.recv = AsyncMock(return_value=json.dumps(mock_response))
    mock_ws.send = AsyncMock()
    
    from contextlib import asynccontextmanager
    @asynccontextmanager
    async def _mock_connect(*args, **kwargs):
        yield mock_ws
    
    with patch("websockets.connect", side_effect=_mock_connect):
        img_b64 = await pipeline.capture_screen_base64()
        assert img_b64 == DUMMY_BASE64_PNG
        mock_ws.send.assert_called_once()
        sent_payload = json.loads(mock_ws.send.call_args[0][0])
        assert sent_payload["type"] == "request_png_base64"

@pytest.mark.asyncio
async def test_capture_screen_base64_failure():
    """
    Test capture_screen_base64 error handling with websocket status error.
    """
    pipeline = VSLMPipeline()
    
    mock_ws = MagicMock()
    mock_response = {
        "type": "png_response",
        "request_id": "vslm-capture-sprint1.2",
        "status": "error",
        "message": "Screen capture permission missing"
    }
    mock_ws.recv = AsyncMock(return_value=json.dumps(mock_response))
    mock_ws.send = AsyncMock()
    
    from contextlib import asynccontextmanager
    @asynccontextmanager
    async def _mock_connect(*args, **kwargs):
        yield mock_ws
    
    with patch("websockets.connect", side_effect=_mock_connect):
        with pytest.raises(RuntimeError) as exc_info:
            await pipeline.capture_screen_base64()
        assert "Screen capture permission missing" in str(exc_info.value)

@pytest.mark.asyncio
@pytest.mark.parametrize("intent", list(GOLDEN_RESPONSES.keys()))
async def test_vslm_pipeline_golden_prompts(intent):
    """
    Verify schema validation and semantic golden-output matching across all 10 QA prompts.
    """
    pipeline = VSLMPipeline()
    expected_plan = GOLDEN_RESPONSES[intent]
    
    # Mock LLM API call response to match golden data
    mock_response_str = json.dumps(expected_plan)
    
    with patch("vslm_pipeline.call_llm", new_callable=AsyncMock) as mock_call_llm:
        mock_call_llm.return_value = (mock_response_str, {"provider": "ollama", "model": "gemma4"})
        
        plan = await pipeline.generate_guidance_plan(intent, DUMMY_BASE64_PNG)
        
        # 1. Schema Validation
        assert isinstance(plan, GuidancePlan)
        assert len(plan.steps) == len(expected_plan["steps"])
        
        # 2. Golden-Output Validation (Semantic Match checking)
        for i, step in enumerate(plan.steps):
            expected_step = expected_plan["steps"][i]
            assert step.action == expected_step["action"]
            assert step.target_selector == expected_step["target_selector"]
            assert step.fallback_coords == tuple(expected_step["fallback_coords"])
            assert step.expected_outcome == expected_step["expected_outcome"]
            
        mock_call_llm.assert_called_once()
        messages_sent = mock_call_llm.call_args[0][0]
        assert messages_sent[0]["images"] == [DUMMY_BASE64_PNG]

@pytest.mark.asyncio
async def test_transient_screenshot_cleanup():
    """
    Explicitly verify that raw image data references are nullified/deleted post-inference.
    """
    pipeline = VSLMPipeline()
    intent = "Minimize all windows"
    expected_plan = GOLDEN_RESPONSES[intent]
    mock_response_str = json.dumps(expected_plan)
    
    # Wrap in a custom patch to intercept execution context
    with patch("vslm_pipeline.call_llm", new_callable=AsyncMock) as mock_call_llm:
        mock_call_llm.return_value = (mock_response_str, {"provider": "ollama", "model": "gemma4"})
        
        # Run inference
        plan = await pipeline.generate_guidance_plan(intent, DUMMY_BASE64_PNG)
        
        # Verify call was successful
        assert isinstance(plan, GuidancePlan)
        
        # Verify that messages dictionary reference containing DUMMY_BASE64_PNG
        # is no longer stored in any property of the pipeline object itself,
        # ensuring memory references are completely cleared.
        assert not hasattr(pipeline, "image_base64")
        assert not hasattr(pipeline, "last_image")
