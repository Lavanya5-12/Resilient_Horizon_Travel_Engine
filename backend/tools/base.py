"""
Base tool specification and registry for Resilient Horizon Travel Engine.
Defines MCP-style tool boundaries with metadata, input validation, and observation wrappers.
"""

from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, Field, ValidationError
import datetime

class ToolObservation(BaseModel):
    tool: str
    status: str  # "success", "warning", "error"
    destination: str
    data: Dict[str, Any]
    evidence: str
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())

class BaseTool:
    def __init__(self, name: str, description: str, input_model: Optional[Type[BaseModel]] = None, input_schema: Optional[Dict[str, Any]] = None, output_schema: Optional[Dict[str, Any]] = None):
        self.name = name
        self.description = description
        self.input_model = input_model
        
        if input_model:
            self.input_schema = input_model.model_json_schema()
        else:
            self.input_schema = input_schema or {}
            
        self.output_schema = output_schema or {"type": "object"}

    def validate_input(self, params: Dict[str, Any]) -> List[str]:
        """
        Validates tool parameters against the tool's Pydantic model.
        Returns a list of error string messages if validation fails.
        """
        if self.input_model:
            try:
                self.input_model.model_validate(params)
                return []
            except ValidationError as ve:
                return [f"Field '{'.'.join(str(loc) for loc in err['loc'])}': {err['msg']}" for err in ve.errors()]

        # Fallback dictionary check
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
