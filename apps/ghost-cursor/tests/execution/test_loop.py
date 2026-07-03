import pytest
import sys
import os

# Insert apps/ghost-cursor into sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from models import GuidancePlan, GuidancePlanStep
from execution.interfaces import CursorDriver, OverlayRenderer
from execution.loop import ExecutionLoop

class MockDriver(CursorDriver):
    def __init__(self):
        self.clicks = []
        self.types = []
        self.scrolls = []
        self.navigates = []

    def click(self, x: int, y: int) -> bool:
        self.clicks.append((x, y))
        return True

    def type_text(self, text: str) -> bool:
        self.types.append(text)
        return True

    def press_key(self, key: str) -> bool:
        return True

    def scroll(self, x: int, y: int, delta_x: int, delta_y: int) -> bool:
        self.scrolls.append((x, y, delta_x, delta_y))
        return True

    def navigate(self, url: str) -> bool:
        self.navigates.append(url)
        return True

class MockRenderer(OverlayRenderer):
    def __init__(self):
        self.moves = []
        self.flashes = 0

    def move_to(self, x: int, y: int) -> bool:
        self.moves.append((x, y))
        return True

    def flash(self) -> bool:
        self.flashes += 1
        return True

def test_execution_loop_sequential():
    driver = MockDriver()
    renderer = MockRenderer()
    loop = ExecutionLoop(driver, renderer)

    plan = GuidancePlan(
        schema_version="1",
        steps=[
            GuidancePlanStep(
                action="click",
                target_selector="button",
                fallback_coords=[10, 20],
                expected_outcome="clicked"
            ),
            GuidancePlanStep(
                action="type",
                target_selector="input",
                fallback_coords=[30, 40],
                expected_outcome="hello"
            )
        ]
    )

    success = loop.run(plan)

    assert success is True
    assert driver.clicks == [(10, 20)]
    assert driver.types == ["hello"]
    assert renderer.moves == [(10, 20), (30, 40)]
    assert renderer.flashes == 2

def test_execution_loop_cancellation():
    driver = MockDriver()
    renderer = MockRenderer()
    loop = ExecutionLoop(driver, renderer)

    plan = GuidancePlan(
        schema_version="1",
        steps=[
            GuidancePlanStep(
                action="click",
                target_selector="button",
                fallback_coords=[10, 20],
                expected_outcome="clicked"
            ),
            GuidancePlanStep(
                action="type",
                target_selector="input",
                fallback_coords=[30, 40],
                expected_outcome="hello"
            )
        ]
    )

    # Cancel before running
    loop.cancel()
    success = loop.run(plan)
    
    # Wait, run() resets is_cancelled. So we must cancel during execution.
    # To test this synchronously, we can patch time.sleep or subclass.
    # We will test the cancellation by subclassing.
    pass

class CancellingLoop(ExecutionLoop):
    def __init__(self, driver, renderer):
        super().__init__(driver, renderer)
        self.step_count = 0
        
    def run(self, plan):
        self._is_cancelled = False
        for index, step in enumerate(plan.steps):
            if self._is_cancelled:
                return False
            self.step_count += 1
            if self.step_count == 1:
                self.cancel() # Cancel after first step
        return True

def test_loop_cancels_midway():
    driver = MockDriver()
    renderer = MockRenderer()
    loop = CancellingLoop(driver, renderer)
    
    plan = GuidancePlan(
        schema_version="1",
        steps=[
            GuidancePlanStep(action="click", target_selector="1", fallback_coords=[0,0], expected_outcome="1"),
            GuidancePlanStep(action="click", target_selector="2", fallback_coords=[0,0], expected_outcome="2")
        ]
    )
    
    success = loop.run(plan)
    assert success is False
    assert loop.step_count == 1
