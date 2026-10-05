"""
Weather Tool implementation with strict Pydantic input validation.
Gets weather forecast and determines outdoor activity suitability.
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from backend.tools.base import BaseTool

class WeatherInput(BaseModel):
    destination: str = Field(..., min_length=1, description="Target destination city or region")
    date: str = Field(default="", description="Target travel date string YYYY-MM-DD")
    day: int = Field(default=1, ge=1, le=14, description="Day number of the itinerary (1-14)")

class WeatherTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="weather.getForecast",
            description="Fetches weather forecast for a destination and evaluates outdoor activity suitability.",
            input_model=WeatherInput,
            output_schema={
                "type": "object",
                "properties": {
                    "destination": {"type": "string"},
                    "condition": {"type": "string"},
                    "temperature_c": {"type": "number"},
                    "suitableForOutdoor": {"type": "boolean"},
                    "evidence": {"type": "string"}
                }
            }
        )

    def execute(self, provider: Any, **kwargs) -> Dict[str, Any]:
        # Validate inputs via Pydantic model
        validated_input = WeatherInput.model_validate(kwargs)
        return provider.get_weather_forecast(
            destination=validated_input.destination,
            date=validated_input.date,
            day=validated_input.day
        )
