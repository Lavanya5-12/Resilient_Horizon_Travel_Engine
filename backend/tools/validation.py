"""
Validation Tool implementation with strict Pydantic input validation.
Evaluates itinerary feasibility against budget, time constraints, user preferences, availability, and weather conflicts.
"""

from typing import Any, Dict, List
from pydantic import BaseModel, Field
from backend.tools.base import BaseTool

class ValidationInput(BaseModel):
    itinerary: List[Dict[str, Any]] = Field(..., description="Day-by-day itinerary schedule")
    budget_inr: float = Field(..., ge=1000.0, description="User budget limit in INR")
    interests: List[str] = Field(default_factory=list, description="Target user interests")
    weather_conditions: List[Dict[str, Any]] = Field(default_factory=list, description="Weather forecast observations per day")

class ValidationTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="validation.validateItinerary",
            description="Validates full itinerary against budget, time constraints, preferences, availability, and weather conflicts.",
            input_model=ValidationInput,
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

    def execute(self, provider: Any, **kwargs) -> Dict[str, Any]:
        validated_input = ValidationInput.model_validate(kwargs)
        return provider.validate_itinerary(
            itinerary=validated_input.itinerary,
            budget_inr=validated_input.budget_inr,
            interests=validated_input.interests,
            weather_conditions=validated_input.weather_conditions
        )
