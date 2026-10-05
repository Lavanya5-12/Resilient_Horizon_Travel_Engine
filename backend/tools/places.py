"""
Places Tool implementation with strict Pydantic input validation.
Searches attractions and activities matching specified user interests.
"""

from typing import Any, Dict, List
from pydantic import BaseModel, Field
from backend.tools.base import BaseTool

class PlacesInput(BaseModel):
    destination: str = Field(..., min_length=1, description="Target destination city or region")
    interests: List[str] = Field(default_factory=list, description="User interest categories")
    indoor_only: bool = Field(default=False, description="Filter only weather-safe indoor attractions")

class PlacesTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="places.searchAttractions",
            description="Finds top attractions and activities in a destination filtered by user interests (e.g. Beaches, Historical Places, Indoor, Food).",
            input_model=PlacesInput,
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

    def execute(self, provider: Any, **kwargs) -> Dict[str, Any]:
        validated_input = PlacesInput.model_validate(kwargs)
        return provider.search_places(
            destination=validated_input.destination,
            interests=validated_input.interests,
            indoor_only=validated_input.indoor_only
        )
