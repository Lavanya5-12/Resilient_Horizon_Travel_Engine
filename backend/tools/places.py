"""
Places Tool implementation.
Searches attractions and activities matching specified user interests.
"""

from typing import Any, Dict, List
from backend.tools.base import BaseTool

class PlacesTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="places.searchAttractions",
            description="Finds top attractions and activities in a destination filtered by user interests (e.g. Beaches, Historical Places, Indoor, Food).",
            input_schema={
                "type": "object",
                "properties": {
                    "destination": {"type": "string"},
                    "interests": {"type": "array", "items": {"type": "string"}},
                    "indoor_only": {"type": "boolean"}
                },
                "required": ["destination"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "destination": {"type": "string"},
                    "attractions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "name": {"type": "string"},
                                "category": {"type": "string"},
                                "is_outdoor": {"type": "boolean"},
                                "estimated_cost_inr": {"type": "number"},
                                "duration_hours": {"type": "number"},
                                "location": {"type": "string"}
                            }
                        }
                    }
                }
            }
        )

    def execute(self, provider: Any, destination: str, interests: List[str] = None, indoor_only: bool = False) -> Dict[str, Any]:
        return provider.search_places(destination=destination, interests=interests or [], indoor_only=indoor_only)
