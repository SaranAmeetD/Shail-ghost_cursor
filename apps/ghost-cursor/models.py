from pydantic import BaseModel, Field
from typing import List, Literal, Tuple

class GuidancePlanStep(BaseModel):
    action: Literal["click", "type", "scroll", "navigate"]
    target_selector: str = Field(description="CSS selector or human-readable description of target element")
    fallback_coords: Tuple[int, int] = Field(description="Fallback pixel coordinates [x, y] on the screen")
    expected_outcome: str = Field(description="Description of visual state change after this step")

class GuidancePlan(BaseModel):
    steps: List[GuidancePlanStep]
