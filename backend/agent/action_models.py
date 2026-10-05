"""
Pydantic Action Models & Validation for Resilient Horizon Travel Engine.
Defines structured AgentAction models and strict input validation boundaries.
"""

from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field, ValidationError

class TripRequest(BaseModel):
    destination: str = Field(..., description="Target destination city or region")
    days: int = Field(default=4, ge=1, le=14, description="Duration in days")
    budget: float = Field(default=15000.0, ge=1000.0, description="Total budget in INR")
    interests: List[str] = Field(default_factory=lambda: ["Beaches", "Historical Places"], description="User travel preferences")
    travel_date: Optional[str] = Field(default=None, description="Optional travel start date")
    demo_mode: bool = Field(default=True, description="Enable deterministic demo mode for disruption simulation")

class AgentAction(BaseModel):
    action: Literal["tool", "finish"] = Field(..., description="Action type: 'tool' to execute a tool, or 'finish' to complete planning")
    tool_name: Optional[str] = Field(default=None, description="Name of the registered tool if action is 'tool'")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Keyword arguments for tool execution")
    reasoning: str = Field(..., description="Reasoning/rationale behind choosing this action")

class ValidatedAction(BaseModel):
    is_valid: bool
    action: AgentAction
    errors: List[str] = Field(default_factory=list)

def validate_agent_action(raw_action_dict: Dict[str, Any], registered_tool_names: List[str]) -> ValidatedAction:
    """
    Validates LLM-generated action dictionary against Pydantic schema and tool catalog rules.
    Reject invalid actions safely without crashing the agent.
    """
    try:
        action_obj = AgentAction.model_validate(raw_action_dict)
    except ValidationError as ve:
        return ValidatedAction(
            is_valid=False,
            action=AgentAction(
                action="finish",
                reasoning=f"Invalid action payload: {str(ve)}"
            ),
            errors=[f"Schema validation error: {err['msg']} at {'.'.join(str(loc) for loc in err['loc'])}" for err in ve.errors()]
        )

    errors = []
    if action_obj.action == "tool":
        if not action_obj.tool_name:
            errors.append("Action type 'tool' requires a non-empty 'tool_name'.")
        elif action_obj.tool_name not in registered_tool_names:
            errors.append(f"Unknown tool '{action_obj.tool_name}'. Allowed tools: {', '.join(registered_tool_names)}")

    if errors:
        return ValidatedAction(is_valid=False, action=action_obj, errors=errors)

    return ValidatedAction(is_valid=True, action=action_obj, errors=[])
