"""
Cost Tool implementation with strict Pydantic input validation.
Estimates total activity and travel expenses against user budget.
"""

from typing import Any, Dict, List
from pydantic import BaseModel, Field
from backend.tools.base import BaseTool

class CostInput(BaseModel):
    activities: List[Dict[str, Any]] = Field(default_factory=list, description="List of activity items or itinerary days")
    transit_costs: float = Field(default=0.0, ge=0.0, description="Estimated transit expenses in INR")
    daily_food_allowance_inr: float = Field(default=1200.0, ge=0.0, description="Daily food allowance in INR")

class CostTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="cost.calculateEstimate",
            description="Calculates itemized breakdown of activity entry fees, travel transit, food, and total trip budget.",
            input_model=CostInput,
            output_schema={
                "type": "object",
                "properties": {
                    "total_cost_inr": {"type": "number"},
                    "activities_cost_inr": {"type": "number"},
                    "transit_cost_inr": {"type": "number"},
                    "food_cost_inr": {"type": "number"}
                }
            }
        )

    def execute(self, provider: Any, **kwargs) -> Dict[str, Any]:
        validated_input = CostInput.model_validate(kwargs)
        return provider.calculate_cost(
            activities=validated_input.activities,
            transit_costs=validated_input.transit_costs,
            daily_food_allowance_inr=validated_input.daily_food_allowance_inr
        )
