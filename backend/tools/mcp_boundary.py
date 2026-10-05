"""
In-Process MCP-Equivalent Local Tool Boundary for Resilient Horizon Travel Engine.
Provides an in-process tool boundary abstraction for tool discovery, input validation, and execution.
All tool invocations (including agent actions and recovery operations) MUST route through this boundary.
Note: This is an in-process local tool boundary abstraction (MCP-equivalent/inspired), not a networked JSON-RPC server/client.
"""

from typing import Any, Dict, List, Optional
import datetime
from backend.tools.base import BaseTool, ToolRegistry, ToolObservation
from backend.tools.weather import WeatherTool
from backend.tools.places import PlacesTool
from backend.tools.route import RouteTool
from backend.tools.availability import AvailabilityTool
from backend.tools.cost import CostTool
from backend.tools.validation import ValidationTool

class MCPToolBoundary:
    def __init__(self):
        self.registry = ToolRegistry()
        self.registry.register(WeatherTool())
        self.registry.register(PlacesTool())
        self.registry.register(RouteTool())
        self.registry.register(AvailabilityTool())
        self.registry.register(CostTool())
        self.registry.register(ValidationTool())

    def list_mcp_tools(self) -> List[Dict[str, Any]]:
        """Returns MCP-equivalent tool schema definitions for all registered tools."""
        return self.registry.list_tools()

    def get_tool_names(self) -> List[str]:
        return [t["name"] for t in self.list_mcp_tools()]

    def invoke_tool(self, tool_name: str, arguments: Dict[str, Any], provider: Any) -> ToolObservation:
        """
        Invokes a tool across the local MCP tool boundary.
        Enforces input validation, exception handling, and structured observation packaging.
        """
        tool = self.registry.get_tool(tool_name)
        timestamp = datetime.datetime.now().isoformat()

        if not tool:
            return ToolObservation(
                tool=tool_name,
                status="error",
                destination=arguments.get("destination", "Unknown"),
                data={"error": f"Tool '{tool_name}' is not registered in the MCP tool catalog."},
                evidence=f"MCP Error: Unknown tool '{tool_name}'.",
                timestamp=timestamp
            )

        # Enforce Pydantic Input Model Validation
        validation_errors = tool.validate_input(arguments)
        if validation_errors:
            err_msg = "; ".join(validation_errors)
            return ToolObservation(
                tool=tool_name,
                status="error",
                destination=arguments.get("destination", "Unknown"),
                data={"error": "InputValidationError", "details": validation_errors},
                evidence=f"MCP Validation Error for '{tool_name}': {err_msg}",
                timestamp=timestamp
            )

        # Execute Tool securely through provider
        try:
            raw_output = tool.execute(provider, **arguments)
            
            # Format evidence string
            dest = arguments.get("destination", raw_output.get("destination", "Destination"))
            if tool_name == "weather.getForecast":
                ev = raw_output.get("evidence", f"Weather forecast condition: {raw_output.get('condition')}")
                status = "warning" if not raw_output.get("suitableForOutdoor", True) else "success"
            elif tool_name == "places.searchAttractions":
                ev = f"Found {raw_output.get('count', 0)} attractions matching requested interests."
                status = "success"
            elif tool_name == "route.estimateTravel":
                ev = f"Estimated travel distance {raw_output.get('distance_km')}km in {raw_output.get('travel_time_mins')} mins."
                status = "success"
            elif tool_name == "availability.checkStatus":
                ev = raw_output.get("evidence", f"Status for {arguments.get('attraction_name')}: open.")
                status = "success" if raw_output.get("is_open", True) else "warning"
            elif tool_name == "cost.calculateEstimate":
                ev = f"Calculated total estimated cost ₹{raw_output.get('total_cost_inr'):,.0f}."
                status = "success"
            elif tool_name == "validation.validateItinerary":
                is_v = raw_output.get("valid", False)
                ev = f"Validated itinerary total cost ₹{raw_output.get('calculatedTotalCost', 0):,.0f}. Valid={is_v}."
                status = "success" if is_v else "warning"
            else:
                ev = f"Executed {tool_name} successfully."
                status = "success"

            return ToolObservation(
                tool=tool_name,
                status=status,
                destination=dest,
                data=raw_output,
                evidence=ev,
                timestamp=timestamp
            )

        except Exception as exc:
            return ToolObservation(
                tool=tool_name,
                status="error",
                destination=arguments.get("destination", "Unknown"),
                data={"error": type(exc).__name__, "message": str(exc)},
                evidence=f"MCP Execution Exception in '{tool_name}': {type(exc).__name__} - {str(exc)}",
                timestamp=timestamp
            )
