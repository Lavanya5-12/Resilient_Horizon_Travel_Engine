"""
Availability Tool implementation with strict Pydantic input validation.
Checks if an attraction/activity is currently open and operating.
"""

from typing import Any, Dict
from pydantic import BaseModel, Field
from backend.tools.base import BaseTool

class AvailabilityInput(BaseModel):
    attraction_name: str = Field(..., min_length=1, description="Name of the attraction/venue")
    date: str = Field(default="", description="Target date YYYY-MM-DD")
    time_of_day: str = Field(default="Morning", description="Slot time of day (Morning, Afternoon, Evening)")

class AvailabilityTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="availability.checkStatus",
            description="Checks operating hours and slot availability for an attraction on a target date/time.",
            input_model=AvailabilityInput,
            output_schema={
                "type": "object",
                "properties": {
                    "is_open": {"type": "boolean"},
                    "operating_hours": {"type": "string"},
                    "capacity_status": {"type": "string"}
                }
            }
        )

    def execute(self, provider: Any, **kwargs) -> Dict[str, Any]:
        validated_input = AvailabilityInput.model_validate(kwargs)
        return provider.check_availability(
            attraction_name=validated_input.attraction_name,
            date=validated_input.date,
            time_of_day=validated_input.time_of_day
        )
