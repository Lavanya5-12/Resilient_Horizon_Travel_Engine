"""
Weather Tool implementation with strict Pydantic input and output validation.
Incomplete or malformed provider responses are rejected.
"""

from typing import Any, Dict

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    StrictBool,
    StrictInt,
    StrictStr,
)

from backend.tools.base import BaseTool


class WeatherInput(BaseModel):
    destination: str = Field(
        ...,
        min_length=1,
        description="Target destination city or region",
    )
    date: str = Field(
        default="",
        description="Target travel date string YYYY-MM-DD",
    )
    day: int = Field(
        default=1,
        ge=1,
        le=14,
        description="Day number of the itinerary (1-14)",
    )


class WeatherOutput(BaseModel):
    """Required fields for a trustworthy weather observation."""

    model_config = ConfigDict(extra="allow")

    destination: StrictStr = Field(min_length=1)
    day: StrictInt = Field(ge=1, le=14)
    condition: StrictStr = Field(min_length=1)
    temperature_c: FiniteFloat
    suitableForOutdoor: StrictBool
    evidence: StrictStr = Field(min_length=1)


class WeatherTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="weather.getForecast",
            description=(
                "Fetches weather forecast for a destination and "
                "evaluates outdoor activity suitability."
            ),
            input_model=WeatherInput,
            output_schema={
                "type": "object",
                "required": [
                    "destination",
                    "day",
                    "condition",
                    "temperature_c",
                    "suitableForOutdoor",
                    "evidence",
                ],
                "properties": {
                    "destination": {"type": "string"},
                    "day": {"type": "integer", "minimum": 1, "maximum": 14},
                    "condition": {"type": "string"},
                    "temperature_c": {"type": "number"},
                    "suitableForOutdoor": {"type": "boolean"},
                    "evidence": {"type": "string"},
                },
            },
        )

    def execute(self, provider: Any, **kwargs) -> Dict[str, Any]:
        validated_input = WeatherInput.model_validate(kwargs)

        response = provider.get_weather_forecast(
            destination=validated_input.destination,
            date=validated_input.date,
            day=validated_input.day,
        )

        if not isinstance(response, dict):
            raise ValueError(
                "Weather provider returned an invalid response: "
                "expected a dictionary."
            )

        validated_output = WeatherOutput.model_validate(response)

        if validated_output.destination.strip().lower() != (
            validated_input.destination.strip().lower()
        ):
            raise ValueError(
                "Weather provider returned data for a different destination."
            )

        if validated_output.day != validated_input.day:
            raise ValueError(
                "Weather provider returned data for a different itinerary day."
            )

        return validated_output.model_dump()