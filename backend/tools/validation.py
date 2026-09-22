"""
Validation Tool implementation.
Evaluates itinerary feasibility against budget, time constraints, user preferences, availability, and weather conflicts.
"""

from typing import Any, Dict, List
from backend.tools.base import BaseTool

class ValidationTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="validation.validateItinerary",
            description="Validates full itinerary against budget, time constraints, preferences, availability, and weather conflicts.",
            input_schema={
                "type": "object",
                "properties": {
                    "itinerary": {"type": "array", "items": {"type": "object"}},
                    "budget_inr": {"type": "number"},
                    "interests": {"type": "array", "items": {"type": "string"}},
                    "weather_conditions": {"type": "array", "items": {"type": "object"}}
                },
                "required": ["itinerary", "budget_inr"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "valid": {"type": "boolean"},
                    "budgetValid": {"type": "boolean"},
                    "timeValid": {"type": "boolean"},
                    "preferencesValid": {"type": "boolean"},
                    "availabilityValid": {"type": "boolean"},
                    "weatherValid": {"type": "boolean"},
                    "issues": {"type": "array", "items": {"type": "string"}}
                }
            }
        )

    def execute(self, provider: Any, itinerary: List[Dict[str, Any]], budget_inr: float, interests: List[str] = None, weather_conditions: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        return provider.validate_itinerary(
            itinerary=itinerary,
            budget_inr=budget_inr,
            interests=interests or [],
            weather_conditions=weather_conditions or []
        )
