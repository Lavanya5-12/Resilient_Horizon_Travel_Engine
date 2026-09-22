"""
Weather Tool implementation.
Gets weather forecast and determines outdoor activity suitability.
"""

from typing import Any, Dict
from backend.tools.base import BaseTool

class WeatherTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="weather.getForecast",
            description="Fetches weather forecast for a destination and evaluates outdoor activity suitability.",
            input_schema={
                "type": "object",
                "properties": {
                    "destination": {"type": "string"},
                    "date": {"type": "string"},
                    "day": {"type": "integer"}
                },
                "required": ["destination"]
            },
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

    def execute(self, provider: Any, destination: str, date: str = "", day: int = 1) -> Dict[str, Any]:
        return provider.get_weather_forecast(destination=destination, date=date, day=day)
