
import os
from typing import Any

try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:
    from mcp.server.fastmcp import FastMCP

from backend.tools.base import ToolRegistry
from backend.tools.weather import WeatherTool
from backend.tools.places import PlacesTool
from backend.tools.route import RouteTool
from backend.tools.availability import AvailabilityTool
from backend.tools.cost import CostTool
from backend.tools.validation import ValidationTool

from backend.providers.demo import DemoProvider
from backend.providers.real import RealProvider


mcp = FastMCP("Resilient Horizon Travel Engine")

registry = ToolRegistry()
registry.register(WeatherTool())
registry.register(PlacesTool())
registry.register(RouteTool())
registry.register(AvailabilityTool())
registry.register(CostTool())
registry.register(ValidationTool())

demo_mode = os.getenv("RH_DEMO_MODE", "true").lower() == "true"
provider = DemoProvider() if demo_mode else RealProvider()


def execute_existing_tool(
    tool_name: str,
    arguments: dict[str, Any],
):
    """Validate and execute an existing application tool."""

    tool = registry.get_tool(tool_name)

    if tool is None:
        raise ValueError(f"Unknown tool: {tool_name}")

    validated = tool.input_model.model_validate(arguments)
    return tool.execute(provider, **validated.model_dump())


@mcp.tool(
    name="weather.getForecast",
    description="Get weather forecast information for a destination and itinerary day.",
)
def get_weather_forecast(
    destination: str,
    date: str = "",
    day: int = 1,
) -> dict[str, Any]:
    return execute_existing_tool(
        "weather.getForecast",
        {"destination": destination, "date": date, "day": day},
    )


@mcp.tool(
    name="places.searchAttractions",
    description="Find attractions matching destination, interests, and indoor-only preferences.",
)
def search_attractions(
    destination: str,
    interests: list[str] | None = None,
    indoor_only: bool = False,
) -> dict[str, Any]:
    return execute_existing_tool(
        "places.searchAttractions",
        {
            "destination": destination,
            "interests": interests if interests is not None else [],
            "indoor_only": indoor_only,
        },
    )


@mcp.tool(
    name="route.estimateTravel",
    description="Estimate travel distance, time, and transport details between two locations.",
)
def estimate_route(
    origin: str,
    destination: str,
    mode: str = "cab",
) -> dict[str, Any]:
    return execute_existing_tool(
        "route.estimateTravel",
        {"origin": origin, "destination": destination, "mode": mode},
    )


@mcp.tool(
    name="availability.checkStatus",
    description="Check the reported availability status of a named attraction.",
)
def check_availability(
    attraction_name: str,
    date: str = "",
    time_of_day: str = "Morning",
) -> dict[str, Any]:
    return execute_existing_tool(
        "availability.checkStatus",
        {
            "attraction_name": attraction_name,
            "date": date,
            "time_of_day": time_of_day,
        },
    )


@mcp.tool(
    name="cost.calculateEstimate",
    description="Calculate an estimated trip cost using activities, transport, and food allowance.",
)
def calculate_cost(
    activities: list[dict[str, Any]] | None = None,
    transit_costs: float = 0.0,
    daily_food_allowance_inr: float = 1200.0,
) -> dict[str, Any]:
    return execute_existing_tool(
        "cost.calculateEstimate",
        {
            "activities": activities if activities is not None else [],
            "transit_costs": transit_costs,
            "daily_food_allowance_inr": daily_food_allowance_inr,
        },
    )


@mcp.tool(
    name="validation.validateItinerary",
    description=(
        "Validate the final itinerary against the original trip request, "
        "budget, interests, and weather observations."
    ),
)
def validate_itinerary(
    itinerary: list[dict[str, Any]],
    budget_inr: float,
    interests: list[str] | None = None,
    weather_conditions: list[dict[str, Any]] | None = None,
    request_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return execute_existing_tool(
        "validation.validateItinerary",
        {
            "itinerary": itinerary,
            "budget_inr": budget_inr,
            "interests": interests if interests is not None else [],
            "weather_conditions": (
                weather_conditions if weather_conditions is not None else []
            ),
            "request_context": request_context,
        },
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
