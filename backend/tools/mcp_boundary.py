
"""
Persistent official MCP client boundary for Resilient Horizon Travel Engine.

Maintains reusable MCP stdio connections.
Preserves the synchronous interface used by the travel agent and recovery engine.
"""

import atexit
import asyncio
import datetime
import json
import os
import sys
import threading

from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Dict, List

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from backend.tools.base import ToolObservation


class PersistentMCPConnection:
    """Runs one persistent MCP server connection on a dedicated event loop."""

    def __init__(self, parameters: StdioServerParameters):
        self.parameters = parameters
        self.loop = None
        self.session = None
        self.exit_stack = None
        self.catalog = []
        self.startup_error = None
        self.ready = threading.Event()
        self.closed = False

        self.thread = threading.Thread(
            target=self._thread_main,
            name="PersistentMCPClient",
            daemon=True
        )

        self.thread.start()

        if not self.ready.wait(timeout=30):
            raise RuntimeError("MCP server startup timed out.")

        if self.startup_error:
            raise RuntimeError(
                f"MCP server startup failed: {self.startup_error}"
            )

    async def _start(self):
        """Start the MCP stdio transport and initialize the client."""

        self.exit_stack = AsyncExitStack()

        read_stream, write_stream = await self.exit_stack.enter_async_context(
            stdio_client(self.parameters)
        )

        self.session = await self.exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )

        await self.session.initialize()

        result = await self.session.list_tools()

        self.catalog = [
            {
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": tool.inputSchema,
                "output_schema": (
                    tool.outputSchema
                    if tool.outputSchema
                    else {"type": "object"}
                )
            }
            for tool in result.tools
        ]

        self.call_lock = asyncio.Lock()

    def _thread_main(self):
        """Own the event loop for the complete MCP connection lifetime."""

        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        try:
            self.loop.run_until_complete(self._start())
        except Exception as exc:
            self.startup_error = exc
            self.ready.set()
            self.loop.close()
            return

        self.ready.set()

        try:
            self.loop.run_forever()
        finally:
            try:
                self.loop.run_until_complete(self._shutdown())
            except Exception:
                pass

            self.loop.close()
            self.closed = True

    async def _shutdown(self):
        """Close the MCP transport and server process."""

        if self.exit_stack is not None:
            await self.exit_stack.aclose()

    def submit(self, coroutine, timeout=60):
        """Run an async operation safely from synchronous application code."""

        if self.closed or not self.thread.is_alive():
            raise RuntimeError("Persistent MCP connection is closed.")

        future = asyncio.run_coroutine_threadsafe(
            coroutine,
            self.loop
        )

        return future.result(timeout=timeout)

    async def _call_tool_async(self, tool_name, arguments):
        """Call an MCP tool using the existing session."""

        async with self.call_lock:
            return await self.session.call_tool(
                tool_name,
                arguments=arguments
            )

    def call_tool(self, tool_name, arguments):
        return self.submit(
            self._call_tool_async(tool_name, arguments)
        )

    def get_catalog(self):
        return self.catalog.copy()

    def close(self):
        """Stop the event loop and close the MCP connection."""

        if self.closed or not self.thread.is_alive():
            return

        if self.loop is not None and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)

        self.thread.join(timeout=15)


class MCPToolBoundary:
    """
    Synchronous application-facing boundary backed by persistent MCP clients.

    Connections are shared by provider mode:
    one Demo connection and one Real connection.
    """

    _connections = {}
    _pool_lock = threading.RLock()

    def __init__(self):
        self.project_root = str(
            Path(__file__).resolve().parents[2]
        )

    def _server_parameters(self, provider: Any):
        """Build parameters for launching the MCP server."""

        demo_mode = getattr(provider, "is_demo", True)

        return StdioServerParameters(
            command=sys.executable,
            args=["-m", "backend.tools.mcp_server"],
            env={
                **os.environ,
                "RH_DEMO_MODE": str(bool(demo_mode)).lower()
            },
            cwd=self.project_root
        )

    def _get_connection(self, provider=None):
        """Return an existing connection or create one for this mode."""

        demo_mode = bool(getattr(provider, "is_demo", True))

        with self._pool_lock:
            connection = self._connections.get(demo_mode)

            if connection is not None:
                if not connection.closed and connection.thread.is_alive():
                    return connection

                self._connections.pop(demo_mode, None)

            parameters = self._server_parameters(provider)

            connection = PersistentMCPConnection(parameters)

            self._connections[demo_mode] = connection

            return connection

    def list_mcp_tools(self) -> List[Dict[str, Any]]:
        """Discover and return the persistent MCP server's tool catalog."""

        try:
            connection = self._get_connection()
            return connection.get_catalog()

        except Exception as exc:
            raise RuntimeError(
                f"Unable to discover MCP tools: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

    def get_tool_names(self) -> List[str]:
        return [
            tool["name"]
            for tool in self.list_mcp_tools()
        ]

    def _parse_result(self, result):
        """Convert an MCP result into a normal dictionary."""

        if result.isError:
            messages = [
                item.text
                for item in (result.content or [])
                if hasattr(item, "text")
            ]

            return {
                "is_error": True,
                "data": {
                    "error": "MCPToolExecutionError",
                    "details": messages
                }
            }

        output = result.structuredContent

        if output is None:
            messages = [
                item.text
                for item in (result.content or [])
                if hasattr(item, "text")
            ]

            if messages:
                try:
                    output = json.loads(messages[0])
                except (ValueError, TypeError):
                    output = {"result": messages[0]}
            else:
                output = {}

        if not isinstance(output, dict):
            output = {"result": output}

        return {
            "is_error": False,
            "data": output
        }

    def invoke_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        provider: Any
    ) -> ToolObservation:
        """Invoke a tool through the persistent official MCP connection."""

        timestamp = datetime.datetime.now().isoformat()
        arguments = arguments or {}

        try:
            connection = self._get_connection(provider)

            known_tools = {
                tool["name"]
                for tool in connection.get_catalog()
            }

            if tool_name not in known_tools:
                return ToolObservation(
                    tool=tool_name,
                    status="error",
                    destination=arguments.get("destination", "Unknown"),
                    data={
                        "error": f"Unknown MCP tool: {tool_name}"
                    },
                    evidence=f"Unknown MCP tool: {tool_name}",
                    timestamp=timestamp
                )

            result = connection.call_tool(
                tool_name,
                arguments
            )

            response = self._parse_result(result)
            raw_output = response["data"]

            if response["is_error"]:
                error_message = raw_output.get(
                    "error",
                    "MCP tool error"
                )

                details = raw_output.get("details", [])

                return ToolObservation(
                    tool=tool_name,
                    status="error",
                    destination=arguments.get("destination", "Unknown"),
                    data=raw_output,
                    evidence=(
                        f"MCP Validation/Execution Error for "
                        f"'{tool_name}': {error_message}. {details}"
                    ),
                    timestamp=timestamp
                )

            destination = arguments.get(
                "destination",
                raw_output.get("destination", "Destination")
            )

            if tool_name == "weather.getForecast":
                evidence = raw_output.get(
                    "evidence",
                    f"Weather condition: {raw_output.get('condition')}"
                )

                status = (
                    "warning"
                    if not raw_output.get("suitableForOutdoor", True)
                    else "success"
                )

            elif tool_name == "places.searchAttractions":
                evidence = (
                    f"Found {raw_output.get('count', 0)} attractions."
                )
                status = "success"

            elif tool_name == "route.estimateTravel":
                evidence = (
                    f"Estimated travel distance "
                    f"{raw_output.get('distance_km')} km in "
                    f"{raw_output.get('travel_time_mins')} minutes."
                )
                status = "success"

            elif tool_name == "availability.checkStatus":
                evidence = raw_output.get(
                    "evidence",
                    f"Availability status for "
                    f"{arguments.get('attraction_name')}."
                )

                status = (
                    "success"
                    if raw_output.get("is_open", True)
                    else "warning"
                )

            elif tool_name == "cost.calculateEstimate":
                evidence = (
                    f"Calculated estimated cost: "
                    f"INR {raw_output.get('total_cost_inr', 0):,.0f}."
                )
                status = "success"

            elif tool_name == "validation.validateItinerary":
                is_valid = raw_output.get("valid", False)

                evidence = (
                    f"Validated itinerary. "
                    f"Total cost: INR "
                    f"{raw_output.get('calculatedTotalCost', 0):,.0f}. "
                    f"Valid={is_valid}."
                )

                status = "success" if is_valid else "warning"

            else:
                evidence = f"Executed {tool_name} successfully."
                status = "success"

            return ToolObservation(
                tool=tool_name,
                status=status,
                destination=destination,
                data=raw_output,
                evidence=evidence,
                timestamp=timestamp
            )

        except Exception as exc:
            return ToolObservation(
                tool=tool_name,
                status="error",
                destination=arguments.get("destination", "Unknown"),
                data={
                    "error": type(exc).__name__,
                    "message": str(exc)
                },
                evidence=(
                    f"MCP Client Error in '{tool_name}': "
                    f"{type(exc).__name__}: {exc}"
                ),
                timestamp=timestamp
            )

    @classmethod
    def close_all(cls):
        """Close all shared MCP connections."""

        with cls._pool_lock:
            connections = list(cls._connections.values())
            cls._connections.clear()

        for connection in connections:
            connection.close()


# Close persistent MCP connections when the Python process exits.
atexit.register(MCPToolBoundary.close_all)
