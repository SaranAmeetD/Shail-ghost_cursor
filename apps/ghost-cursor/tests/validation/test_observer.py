import pytest
from unittest import mock
from typing import Dict, Any, Optional

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from models import GuidancePlanStep
from validation.observer import ResultObserver, ObservationResult
from execution.interfaces import CursorDriver, VerifiableCursorDriver

class MockUnverifiableDriver(CursorDriver):
    def click(self, x: int, y: int) -> bool: return True
    def type_text(self, text: str) -> bool: return True
    def press_key(self, key: str) -> bool: return True
    def scroll(self, x: int, y: int, dx: int, dy: int) -> bool: return True
    def navigate(self, url: str) -> bool: return True

class MockVerifiableDriver(VerifiableCursorDriver):
    def __init__(self):
        self.element_to_return = None
        self.calls = 0
        
    def click(self, x: int, y: int) -> bool: return True
    def type_text(self, text: str) -> bool: return True
    def press_key(self, key: str) -> bool: return True
    def scroll(self, x: int, y: int, dx: int, dy: int) -> bool: return True
    def navigate(self, url: str) -> bool: return True
    
    def get_element_at(self, x: int, y: int) -> Optional[Dict[str, Any]]:
        self.calls += 1
        if isinstance(self.element_to_return, list):
            if len(self.element_to_return) > 0:
                return self.element_to_return.pop(0)
            return None
        return self.element_to_return


@pytest.fixture
def observer():
    return ResultObserver(poll_interval_s=0.01, max_attempts=3)

def test_unverifiable_driver(observer):
    driver = MockUnverifiableDriver()
    step = GuidancePlanStep(action="click", target_selector="btn", fallback_coords=(0,0), expected_outcome="")
    result = observer.observe(step, driver)
    assert result.is_verifiable is False
    assert result.verified is True

def test_unverifiable_actions(observer):
    driver = MockVerifiableDriver()
    
    step_scroll = GuidancePlanStep(action="scroll", target_selector="", fallback_coords=(0,0), expected_outcome="")
    res = observer.observe(step_scroll, driver)
    assert res.is_verifiable is False
    assert res.verified is True
    
    step_nav = GuidancePlanStep(action="navigate", target_selector="", fallback_coords=(0,0), expected_outcome="")
    res = observer.observe(step_nav, driver)
    assert res.is_verifiable is False
    assert res.verified is True

def test_click_success(observer):
    driver = MockVerifiableDriver()
    # Element disappears on first check
    driver.element_to_return = None 
    
    step = GuidancePlanStep(action="click", target_selector="btn", fallback_coords=(0,0), expected_outcome="")
    res = observer.observe(step, driver)
    
    assert res.is_verifiable is True
    assert res.verified is True
    assert driver.calls == 1

def test_click_failure_timeout(observer):
    driver = MockVerifiableDriver()
    # Element stays present for all polls
    driver.element_to_return = {"role": "AXButton"}
    
    step = GuidancePlanStep(action="click", target_selector="btn", fallback_coords=(0,0), expected_outcome="")
    res = observer.observe(step, driver)
    
    assert res.is_verifiable is True
    assert res.verified is False
    assert driver.calls == 3

def test_type_success(observer):
    driver = MockVerifiableDriver()
    # Element remains focused during type
    driver.element_to_return = {"role": "AXTextField"}
    
    step = GuidancePlanStep(action="type", target_selector="input", fallback_coords=(0,0), expected_outcome="")
    res = observer.observe(step, driver)
    
    assert res.is_verifiable is True
    assert res.verified is True
    assert driver.calls == 1
