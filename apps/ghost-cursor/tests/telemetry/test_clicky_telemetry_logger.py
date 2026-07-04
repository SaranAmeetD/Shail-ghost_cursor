import pytest
from unittest import mock
from unittest.mock import MagicMock, patch

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from models import GuidancePlan, GuidancePlanStep
from telemetry.clicky_telemetry_logger import ClickyTelemetryLogger, _DISTINCT_ID


@pytest.fixture
def dummy_plan():
    return GuidancePlan(
        schema_version="1",
        steps=[
            GuidancePlanStep(
                action="click",
                target_selector="button.submit",
                fallback_coords=(100, 200),
                expected_outcome="Submits form"
            ),
            GuidancePlanStep(
                action="type",
                target_selector="input.name",
                fallback_coords=(150, 250),
                expected_outcome="Types name"
            )
        ]
    )


@pytest.fixture
def active_logger():
    """Creates a ClickyTelemetryLogger with PostHog active and mocked."""
    with mock.patch.dict(os.environ, {"POSTHOG_API_KEY": "phc_test_key_for_unit_tests"}):
        with mock.patch("telemetry.clicky_telemetry_logger.posthog") as mock_posthog:
            mock_posthog.__bool__ = lambda self: True
            logger = ClickyTelemetryLogger()
            # Override is_active since we mocked posthog at import level
            logger.is_active = True
            logger._posthog_mock = mock_posthog
            yield logger, mock_posthog


def test_inactive_when_no_api_key(dummy_plan):
    """Logger should be inactive when POSTHOG_API_KEY is not set."""
    with mock.patch.dict(os.environ, {}, clear=True):
        # Remove POSTHOG_API_KEY if present
        os.environ.pop("POSTHOG_API_KEY", None)
        logger = ClickyTelemetryLogger()
        assert logger.is_active is False

        # Methods should not raise
        logger.log_plan_start(dummy_plan)
        logger.log_step_result(dummy_plan.steps[0], 0, True, True, 100.0)
        logger.log_plan_complete(True, 200.0)
        logger.log_plan_aborted("test_reason")


def test_log_plan_start(active_logger, dummy_plan):
    """log_plan_start should send ghost_cursor_plan_start with step_count."""
    logger, mock_posthog = active_logger

    logger.log_plan_start(dummy_plan)

    mock_posthog.capture.assert_called_once_with(
        _DISTINCT_ID,
        "ghost_cursor_plan_start",
        {"step_count": 2}
    )


def test_log_step_result(active_logger, dummy_plan):
    """log_step_result should send ghost_cursor_step_result with step details."""
    logger, mock_posthog = active_logger
    step = dummy_plan.steps[0]

    logger.log_step_result(step, 0, True, True, 150.5)

    mock_posthog.capture.assert_called_once_with(
        _DISTINCT_ID,
        "ghost_cursor_step_result",
        {
            "step_index": 0,
            "action": "click",
            "success": True,
            "verified": True,
            "latency_ms": 150.5
        }
    )


def test_log_step_result_failure(active_logger, dummy_plan):
    """log_step_result should correctly report failure and non-verified state."""
    logger, mock_posthog = active_logger
    step = dummy_plan.steps[1]

    logger.log_step_result(step, 1, False, False, 320.0)

    mock_posthog.capture.assert_called_once_with(
        _DISTINCT_ID,
        "ghost_cursor_step_result",
        {
            "step_index": 1,
            "action": "type",
            "success": False,
            "verified": False,
            "latency_ms": 320.0
        }
    )


def test_log_plan_complete_success(active_logger):
    """log_plan_complete should send ghost_cursor_plan_complete with success=True."""
    logger, mock_posthog = active_logger

    logger.log_plan_complete(True, 500.0)

    mock_posthog.capture.assert_called_once_with(
        _DISTINCT_ID,
        "ghost_cursor_plan_complete",
        {"success": True, "total_ms": 500.0}
    )


def test_log_plan_complete_failure(active_logger):
    """log_plan_complete should send ghost_cursor_plan_complete with success=False."""
    logger, mock_posthog = active_logger

    logger.log_plan_complete(False, 1200.0)

    mock_posthog.capture.assert_called_once_with(
        _DISTINCT_ID,
        "ghost_cursor_plan_complete",
        {"success": False, "total_ms": 1200.0}
    )


def test_log_plan_aborted(active_logger):
    """log_plan_aborted should send ghost_cursor_plan_aborted with reason."""
    logger, mock_posthog = active_logger

    logger.log_plan_aborted("user_cancelled")

    mock_posthog.capture.assert_called_once_with(
        _DISTINCT_ID,
        "ghost_cursor_plan_aborted",
        {"reason": "user_cancelled"}
    )


def test_log_plan_aborted_privacy(active_logger):
    """log_plan_aborted should correctly send privacy_blocked reason."""
    logger, mock_posthog = active_logger

    logger.log_plan_aborted("privacy_blocked")

    mock_posthog.capture.assert_called_once_with(
        _DISTINCT_ID,
        "ghost_cursor_plan_aborted",
        {"reason": "privacy_blocked"}
    )


def test_capture_exception_does_not_propagate(active_logger, dummy_plan):
    """If posthog.capture raises, the exception should be caught and logged, not propagated."""
    logger, mock_posthog = active_logger
    mock_posthog.capture.side_effect = Exception("Network unreachable")

    # Should not raise
    logger.log_plan_start(dummy_plan)
    logger.log_step_result(dummy_plan.steps[0], 0, True, True, 100.0)
    logger.log_plan_complete(True, 200.0)
    logger.log_plan_aborted("error")


def test_no_forbidden_properties(active_logger, dummy_plan):
    """Events must not contain image data, OCR text, or selectors — privacy constraint."""
    logger, mock_posthog = active_logger

    logger.log_plan_start(dummy_plan)
    logger.log_step_result(dummy_plan.steps[0], 0, True, True, 100.0)
    logger.log_plan_complete(True, 200.0)

    for call in mock_posthog.capture.call_args_list:
        properties = call[0][2]  # Third positional arg is properties dict
        for forbidden_key in ["image", "ocr", "base64", "text", "selector", "screenshot"]:
            assert forbidden_key not in properties, (
                f"Forbidden key '{forbidden_key}' found in PostHog event properties"
            )
