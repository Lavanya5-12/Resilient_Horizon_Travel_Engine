"""
Availability Tool implementation.
Checks if an attraction/activity is currently open and operating.
"""

from typing import Any, Dict
from backend.tools.base import BaseTool

class AvailabilityTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="availability.checkStatus",
            description="Checks operating hours and slot availability for an attraction on a target date/time.",
            input_schema={
                "type": "object",
                "properties": {
                    "attraction_name": {"type": "string"},
                    "date": {"type": "string"},
                    "time_of_day": {"type": "string"}
                },
                "required": ["attraction_name"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "is_open": {"type": "boolean"},
                    "operating_hours": {"type": "string"},
                    "capacity_status": {"type": "string"}
                }
            }
        )

    def execute(self, provider: Any, attraction_name: str, date: str = "", time_of_day: str = "Morning") -> Dict[str, Any]:
        return provider.check_availability(attraction_name=attraction_name, date=date, time_of_day=time_of_day)
