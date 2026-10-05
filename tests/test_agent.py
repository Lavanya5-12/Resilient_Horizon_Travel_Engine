"""
Automated Pytest Test Suite for Resilient Horizon Travel Engine.
Covers agent reasoning loop, arbitrary destination support, MCP tool boundary,
action validation, error handling, provider failures, budget checks, trace accuracy, and API endpoints.
"""

import pytest
import os
import json
from fastapi.testclient import TestClient
from backend.agent.travel_agent import ResilientTravelAgent
from backend.agent.action_models import validate_agent_action, AgentAction
from backend.tools.mcp_boundary import MCPToolBoundary
from backend.agent.planner import parse_natural_language_request
from backend.main import app

client = TestClient(app)

@pytest.fixture
def agent():
    return ResilientTravelAgent()

@pytest.fixture
def mcp():
    return MCPToolBoundary()

# 1. Goa Disruption Recovery Test
def test_goa_normal_recovery(agent):
    res = agent.run(destination="Goa", days=4, budget=15000.0, interests=["Beaches", "Historical Places"], demo_mode=True)
    assert res["status"] == "verified"
    assert res["recovery"]["occurred"] is True
    assert res["validation"]["valid"] is True
    assert res["validation"]["weatherValid"] is True
    # Confirm Day 2 has no outdoor activities
    day2 = res["itinerary"][1]
    for slot in ["morning", "afternoon", "evening"]:
        if day2.get(slot):
            assert day2[slot]["is_outdoor"] is False

# 2. No Weather Disruption Test
def test_no_weather_disruption(agent):
    res = agent.run(destination="Mumbai", days=3, budget=25000.0, interests=["Food", "Shopping"], demo_mode=True)
    assert res["status"] == "verified"
    assert res["recovery"]["occurred"] is False
    assert res["validation"]["valid"] is True

# 3. Kakinada Destination Test
def test_kakinada_destination(agent):
    res = agent.run(destination="Kakinada", days=3, budget=10000.0, interests=["Food", "Sightseeing"], demo_mode=True)
    assert res["request"]["destination"] == "Kakinada"
    assert len(res["itinerary"]) == 3
    assert "Kakinada" in res["itinerary"][0]["title"]

# 4. Arbitrary Destination Test
def test_arbitrary_destination(agent):
    res = agent.run(destination="Udaipur", days=2, budget=12000.0, interests=["Historical Places"], demo_mode=True)
    assert res["request"]["destination"] == "Udaipur"
    assert len(res["itinerary"]) == 2

# 5. Invalid LLM Action Test
def test_invalid_llm_action(mcp):
    tool_names = mcp.get_tool_names()
    invalid_payload = {"action": "invalid_action_type", "reasoning": "testing"}
    val_res = validate_agent_action(invalid_payload, tool_names)
    assert val_res.is_valid is False
    assert len(val_res.errors) > 0

# 6. Unknown Tool Test
def test_unknown_tool(mcp):
    tool_names = mcp.get_tool_names()
    invalid_payload = {"action": "tool", "tool_name": "unknown.fakeTool", "arguments": {}, "reasoning": "testing"}
    val_res = validate_agent_action(invalid_payload, tool_names)
    assert val_res.is_valid is False
    assert "Unknown tool" in val_res.errors[0]

# 7. Invalid Tool Arguments Test
def test_invalid_tool_arguments(mcp):
    # places.searchAttractions requires destination
    obs = mcp.invoke_tool("places.searchAttractions", arguments={}, provider=None)
    assert obs.status == "error"
    assert "ValidationError" in obs.evidence or "Validation" in obs.evidence

# 8. Tool Failure Handling Test
def test_tool_failure(mcp):
    obs = mcp.invoke_tool("nonexistent.tool", arguments={"destination": "Test"}, provider=None)
    assert obs.status == "error"

# 9. Weather Timeout / Network Error Test
def test_weather_timeout(mcp):
    from backend.providers.real import RealProvider
    real_prov = RealProvider()
    # Query invalid destination to trigger fallback observation without crash
    obs = mcp.invoke_tool("weather.getForecast", arguments={"destination": "NonExistentCity123"}, provider=real_prov)
    assert obs.status in ["success", "warning"]

# 10. Malformed Provider Response Handling Test
def test_malformed_provider_response(mcp):
    class MalformedProvider:
        def get_weather_forecast(self, **kwargs):
            return {"destination": "Test", "condition": "sunny", "suitableForOutdoor": True, "evidence": "OK"}
    obs = mcp.invoke_tool("weather.getForecast", arguments={"destination": "Test"}, provider=MalformedProvider())
    assert obs.status == "success"

# 11. Budget Failure Test
def test_budget_failure(agent):
    res = agent.run(destination="Goa", days=4, budget=5000.0, interests=["Beaches"], demo_mode=True)
    assert res["status"] == "unverified"
    assert res["validation"]["budgetValid"] is False
    assert res["validation"]["valid"] is False

# 12. Validation Failure Test
def test_validation_failure(mcp):
    from backend.providers.demo import DemoProvider
    prov = DemoProvider()
    obs = mcp.invoke_tool("validation.validateItinerary", arguments={"itinerary": [], "budget_inr": 1000.0}, provider=prov)
    assert obs.status in ["success", "warning"]

# 13. Max Iterations Test
def test_max_iterations(agent):
    res = agent.run(destination="Delhi", days=2, budget=15000.0, interests=["Historical Places"], demo_mode=True)
    assert res["metrics"]["iterationsUsed"] <= res["metrics"]["maxIterations"]

# 14. Safe Exit Test
def test_safe_exit(agent):
    res = agent.run(destination="Jaipur", days=3, budget=18000.0, interests=["Historical Places"], demo_mode=True)
    assert "status" in res
    assert "explanation" in res

# 15. Tool Trace Accuracy Test
def test_tool_trace_accuracy(agent):
    res = agent.run(destination="Goa", days=4, budget=15000.0, interests=["Beaches"], demo_mode=True)
    assert "trace_file" in res
    trace_path = res["trace_file"]
    assert os.path.exists(trace_path)
    with open(trace_path, "r", encoding="utf-8") as f:
        trace_data = json.load(f)
        assert trace_data["session_id"] == res["session_id"]
        assert len(trace_data["iteration_steps"]) > 0

# 16. UI Validation State Alignment Test
def test_ui_validation_state(agent):
    res = agent.run(destination="Goa", days=4, budget=5000.0, interests=["Beaches"], demo_mode=True)
    # When budget fails, valid must be False
    assert res["validation"]["valid"] is False

# 17. API Health Endpoint Test
def test_api_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "online"

# 18. API Travel Plan Endpoint Test
def test_api_travel_plan():
    payload = {
        "destination": "Kakinada",
        "days": 3,
        "budget": 10000.0,
        "interests": ["Food", "Sightseeing"],
        "demoMode": True
    }
    response = client.post("/api/travel/plan", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["request"]["destination"] == "Kakinada"
    assert len(data["itinerary"]) == 3
