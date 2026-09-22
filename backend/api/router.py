"""
API Router for Resilient Horizon Travel Engine.
Defines endpoints for travel planning, health checks, and tool registry schemas.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from backend.agent.travel_agent import ResilientTravelAgent

router = APIRouter(prefix="/api", tags=["Travel Engine"])

agent_instance = ResilientTravelAgent()

class PlanRequest(BaseModel):
    destination: str = Field("Goa", description="Target destination city or region")
    days: int = Field(4, ge=1, le=14, description="Duration in days")
    budget: float = Field(15000.0, ge=1000.0, description="Total budget in INR")
    interests: List[str] = Field(default_factory=lambda: ["Beaches", "Historical Places"], description="User travel preferences")
    travelDate: Optional[str] = Field(None, description="Optional target travel date")
    demoMode: bool = Field(True, description="Enable deterministic demo mode for disruption simulation")

@router.get("/health")
def health_check():
    return {
        "status": "online",
        "service": "Resilient Horizon Travel Engine API",
        "agent": "Ready",
        "version": "1.0.0"
    }

@router.get("/tools")
def get_registered_tools():
    """Returns metadata and MCP schemas for all registered dynamic tools."""
    return {
        "count": len(agent_instance.registry.list_tools()),
        "tools": agent_instance.registry.list_tools()
    }

@router.post("/travel/plan")
def create_travel_plan(req: PlanRequest):
    try:
        result = agent_instance.run(
            destination=req.destination,
            days=req.days,
            budget=req.budget,
            interests=req.interests,
            travel_date=req.travelDate,
            demo_mode=req.demoMode
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {str(e)}")
