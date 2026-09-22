"""
Base tool specification and registry for Resilient Horizon Travel Engine.
Defines MCP-style tool boundaries with metadata, input validation, and observation wrappers.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel
import datetime

class ToolObservation(BaseModel):
    tool: str
    status: str  # "success", "warning", "error"
    destination: str
    data: Dict[str, Any]
    evidence: str
    timestamp: str

class BaseTool:
    def __init__(self, name: str, description: str, input_schema: Dict[str, Any], output_schema: Dict[str, Any]):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.output_schema = output_schema

    def validate_input(self, params: Dict[str, Any]) -> List[str]:
        errors = []
        req_keys = self.input_schema.get("required", [])
        for k in req_keys:
            if k not in params:
                errors.append(f"Missing required parameter '{k}' for tool '{self.name}'")
        return errors

    def execute(self, provider: Any, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError("Subclasses must implement execute()")

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
                "output_schema": t.output_schema
            }
            for t in self._tools.values()
        ]
