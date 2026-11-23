
"""
Validation Tool implementation with strict Pydantic input validation.

Binds final itinerary verification to the original trip request,
including its SHA-256 integrity hash.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.tools.base import BaseTool


class RequestContext(BaseModel):
    """Original, authoritative TripRequest supplied by the application."""

    destination: str = Field(..., min_length=1)
    days: int = Field(..., ge=1, le=14)
    budget: float = Field(..., ge=1000.0)
    interests: List[str] = Field(default_factory=list)
    travel_date: Optional[str] = None
    demo_mode: bool
    request_sha256: str = Field(
        ...,
        min_length=64,
        max_length=64,
        pattern=r"^[a-fA-F0-9]{64}$",
    )


class ValidationInput(BaseModel):
    """Validated arguments for final itinerary verification."""

    itinerary: List[Dict[str, Any]] = Field(
        ...,
        description="Final day-by-day itinerary schedule",
    )
    budget_inr: float = Field(
        ...,
        ge=1000.0,
        description="Original user budget limit in INR",
    )
    interests: List[str] = Field(
        default_factory=list,
        description="Original user interests",
    )
    weather_conditions: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Weather observations for requested trip days",
    )
    request_context: Optional[RequestContext] = Field(
        default=None,
        description="Original trip request and its integrity hash",
    )


class ValidationTool(BaseTool):

    def __init__(self):
        super().__init__(
            name="validation.validateItinerary",
            description=(
                "Validates the final itinerary against the original trip "
                "request, budget, itinerary completeness, weather evidence, "
                "and available constraint evidence. Unknown checks must "
                "never be reported as successful."
            ),
            input_model=ValidationInput,
            output_schema={
                "type": "object",
                "properties": {
                    "valid": {"type": "boolean"},
                    "budgetValid": {"type": "boolean"},
                    "timeValid": {
                        "type": ["boolean", "null"]
                    },
                    "preferencesValid": {
                        "type": ["boolean", "null"]
                    },
                    "availabilityValid": {
                        "type": ["boolean", "null"]
                    },
                    "weatherValid": {"type": "boolean"},
                    "weatherCoverageValid": {"type": "boolean"},
                    "itineraryStructureValid": {"type": "boolean"},
                    "activitiesComplete": {"type": "boolean"},
                    "requestContextValid": {"type": "boolean"},
                    "requestSha256": {
                        "type": ["string", "null"]
                    },
                    "itinerarySha256": {
                        "type": "string",
                        "pattern": "^[a-fA-F0-9]{64}$"
                    },
                    "calculatedTotalCost": {"type": "number"},
                    "remainingBudget": {
                        "type": ["number", "null"]
                    },
                    "issues": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": [
                    "valid",
                    "requestContextValid",
                    "itinerarySha256",
                    "issues",
                ],
            },
        )

    def execute(self, provider: Any, **kwargs) -> Dict[str, Any]:
        validated_input = ValidationInput.model_validate(kwargs)

        request_context = (
            validated_input.request_context.model_dump()
            if validated_input.request_context is not None
            else None
        )

        return provider.validate_itinerary(
            itinerary=validated_input.itinerary,
            budget_inr=validated_input.budget_inr,
            interests=validated_input.interests,
            weather_conditions=validated_input.weather_conditions,
            request_context=request_context,
        )
