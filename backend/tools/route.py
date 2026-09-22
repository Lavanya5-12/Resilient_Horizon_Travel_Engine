"""
Route / Distance Tool implementation.
Estimates travel distance and transit time between activity locations.
"""

from typing import Any, Dict
from backend.tools.base import BaseTool

class RouteTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="route.estimateTravel",
            description="Estimates transit distance and travel time in minutes between two activity locations.",
            input_schema={
                "type": "object",
                "properties": {
                    "origin": {"type": "string"},
                    "destination": {"type": "string"},
                    "mode": {"type": "string"}
                },
                "required": ["origin", "destination"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "distance_km": {"type": "number"},
                    "travel_time_mins": {"type": "integer"},
                    "estimated_transit_cost_inr": {"type": "number"}
                }
            }
        )

    def execute(self, provider: Any, origin: str, destination: str, mode: str = "cab") -> Dict[str, Any]:
        return provider.estimate_route(origin=origin, destination=destination, mode=mode)
