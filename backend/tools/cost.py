"""
Cost Tool implementation.
Estimates total activity and travel expenses against user budget.
"""

from typing import Any, Dict, List
from backend.tools.base import BaseTool

class CostTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="cost.calculateEstimate",
            description="Calculates itemized breakdown of activity entry fees, travel transit, food, and total trip budget.",
            input_schema={
                "type": "object",
                "properties": {
                    "activities": {"type": "array", "items": {"type": "object"}},
                    "transit_costs": {"type": "number"},
                    "daily_food_allowance_inr": {"type": "number"}
                },
                "required": ["activities"]
            },
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

    def execute(self, provider: Any, activities: List[Dict[str, Any]], transit_costs: float = 0.0, daily_food_allowance_inr: float = 1200.0) -> Dict[str, Any]:
        return provider.calculate_cost(activities=activities, transit_costs=transit_costs, daily_food_allowance_inr=daily_food_allowance_inr)
