"""
Route / Distance Tool implementation with strict Pydantic input validation.
Estimates travel distance and transit time between activity locations.
"""

from typing import Any, Dict
from pydantic import BaseModel, Field
from backend.tools.base import BaseTool

class RouteInput(BaseModel):
    origin: str = Field(..., min_length=1, description="Starting location name or address")
    destination: str = Field(..., min_length=1, description="Ending location name or address")
    mode: str = Field(default="cab", description="Transit mode (cab, transit, walk)")

class RouteTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="route.estimateTravel",
            description="Estimates transit distance and travel time in minutes between two activity locations.",
            input_model=RouteInput,
            output_schema={
                "type": "object",
                "properties": {
                    "distance_km": {"type": "number"},
                    "travel_time_mins": {"type": "integer"},
                    "estimated_transit_cost_inr": {"type": "number"}
                }
            }
        )

    def execute(self, provider: Any, **kwargs) -> Dict[str, Any]:
        validated_input = RouteInput.model_validate(kwargs)
        return provider.estimate_route(
            origin=validated_input.origin,
            destination=validated_input.destination,
            mode=validated_input.mode
        )
