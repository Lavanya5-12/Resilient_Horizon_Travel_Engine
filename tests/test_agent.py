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
from backend.agent.action_models import validate_agent_action, AgentAction, ValidatedAction, PolicyDecisionProvenance
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
    # Query invalid destination to trigger error observation safely without crashing
    obs = mcp.invoke_tool("weather.getForecast", arguments={"destination": "NonExistentCity123"}, provider=real_prov)
    assert obs.status == "error"

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


# 19. Issue 1 Regression: Time Feasibility Validation
def test_validation_time_feasibility():
    from backend.providers.demo import DemoProvider
    import hashlib
    import json

    prov = DemoProvider()
    valid_day = {
        "day": 1,
        "morning": {"activity": "Beach Walk", "location": "Goa", "cost_inr": 100.0, "duration_hours": 2.0, "is_outdoor": True},
        "afternoon": {"activity": "Fort Tour", "location": "Goa", "cost_inr": 200.0, "duration_hours": 3.0, "is_outdoor": False},
        "evening": {"activity": "Sunset Dinner", "location": "Goa", "cost_inr": 500.0, "duration_hours": 2.5, "is_outdoor": False},
    }
    weather = [{"day": 1, "condition": "sunny", "suitableForOutdoor": True}]
    req = {
        "destination": "Goa", "days": 1, "budget": 5000.0,
        "interests": ["Beach"], "travel_date": None, "demo_mode": True,
    }
    req_sha = hashlib.sha256(json.dumps(req, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")).hexdigest()
    req_ctx = {**req, "request_sha256": req_sha}

    res_valid = prov.validate_itinerary(
        itinerary=[valid_day], budget_inr=5000.0, interests=["Beach"],
        weather_conditions=weather, request_context=req_ctx,
    )
    assert res_valid["timeValid"] is True
    assert res_valid["valid"] is True

    # Overloaded day (> 14h)
    overloaded_day = {
        "day": 1,
        "morning": {"activity": "Marathon Hike", "location": "Goa", "cost_inr": 100.0, "duration_hours": 7.0, "is_outdoor": True},
        "afternoon": {"activity": "Extended Exploration", "location": "Goa", "cost_inr": 200.0, "duration_hours": 7.5, "is_outdoor": False},
        "evening": {"activity": "Night Out", "location": "Goa", "cost_inr": 500.0, "duration_hours": 3.0, "is_outdoor": False},
    }
    res_overloaded = prov.validate_itinerary(
        itinerary=[overloaded_day], budget_inr=5000.0, interests=["Beach"],
        weather_conditions=weather, request_context=req_ctx,
    )
    assert res_overloaded["timeValid"] is False
    assert res_overloaded["valid"] is False


# 20. Issue 1 Regression: Preference Satisfaction Validation
def test_validation_preference_matching():
    from backend.providers.demo import DemoProvider
    import hashlib
    import json

    prov = DemoProvider()
    itinerary = [{
        "day": 1,
        "morning": {"activity": "Aguada Fort", "category": "Historical Places", "location": "Goa", "cost_inr": 200.0, "duration_hours": 2.0, "is_outdoor": False},
        "afternoon": {"activity": "Museum Tour", "category": "Historical Places", "location": "Goa", "cost_inr": 250.0, "duration_hours": 2.0, "is_outdoor": False},
        "evening": {"activity": "Old Church", "category": "Historical Places", "location": "Goa", "cost_inr": 150.0, "duration_hours": 2.0, "is_outdoor": False},
    }]
    weather = [{"day": 1, "condition": "sunny", "suitableForOutdoor": True}]

    # Request matching Historical Places
    req_match = {
        "destination": "Goa", "days": 1, "budget": 5000.0,
        "interests": ["Historical Places"], "travel_date": None, "demo_mode": True,
    }
    req_sha_match = hashlib.sha256(json.dumps(req_match, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")).hexdigest()
    res_match = prov.validate_itinerary(
        itinerary=itinerary, budget_inr=5000.0, interests=["Historical Places"],
        weather_conditions=weather, request_context={**req_match, "request_sha256": req_sha_match},
    )
    assert res_match["preferencesValid"] is True
    assert res_match["valid"] is True

    # Request for Beaches when none are planned
    req_mismatch = {
        "destination": "Goa", "days": 1, "budget": 5000.0,
        "interests": ["Beaches"], "travel_date": None, "demo_mode": True,
    }
    req_sha_mismatch = hashlib.sha256(json.dumps(req_mismatch, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")).hexdigest()
    res_mismatch = prov.validate_itinerary(
        itinerary=itinerary, budget_inr=5000.0, interests=["Beaches"],
        weather_conditions=weather, request_context={**req_mismatch, "request_sha256": req_sha_mismatch},
    )
    assert res_mismatch["preferencesValid"] is False
    assert res_mismatch["valid"] is False


# 21. Issue 2 Regression: AgentReflection Availability Schema & Evidence Alignment
def test_reflection_availability_open_demo():
    from backend.agent.reflection import AgentReflection
    reflector = AgentReflection()
    obs = [{
        "tool": "availability.checkStatus",
        "status": "success",
        "evidence": "Attraction is open",
        "data": {"attraction_name": "Aguada Fort", "is_open": True, "operating_hours": "09:00 AM - 06:00 PM"},
    }]
    val_res = {"valid": True, "budgetValid": True, "weatherValid": True, "availabilityValid": True}
    res = reflector.reflect_and_explain(val_res, {}, obs, "Goa", 15000.0, ["Historical Places"])

    audit = res["audit_checks"]
    assert audit["availability_observation_present"] is True
    assert audit["availability_open"] is True
    assert audit["availability_is_simulated"] is True
    assert audit["availability_confirmed"] is False
    assert "open via simulated provider data" in res["summary_explanation"]
    assert "ev_001_availability_checkStatus" in res["evidence_citations"]


def test_reflection_availability_closed():
    from backend.agent.reflection import AgentReflection
    reflector = AgentReflection()
    obs = [{
        "tool": "availability.checkStatus",
        "status": "warning",
        "evidence": "Attraction is closed today",
        "data": {"attraction_name": "Museum", "is_open": False},
    }]
    val_res = {"valid": False, "budgetValid": True, "weatherValid": True, "availabilityValid": False}
    res = reflector.reflect_and_explain(val_res, {}, obs, "Goa", 15000.0, ["Historical Places"])

    audit = res["audit_checks"]
    assert audit["availability_observation_present"] is True
    assert audit["availability_closed"] is True
    assert audit["availability_confirmed"] is False
    assert len(res["warning_observations"]) == 1
    assert len(res["evidence_citations"]) == 0
    assert "closed or unavailable" in res["summary_explanation"]


def test_reflection_availability_missing_status():
    from backend.agent.reflection import AgentReflection
    reflector = AgentReflection()
    obs = [{
        "tool": "availability.checkStatus",
        "status": "success",
        "evidence": "Unknown status",
        "data": {"attraction_name": "Park"},
    }]
    val_res = {"valid": True, "budgetValid": True, "weatherValid": True, "availabilityValid": True}
    res = reflector.reflect_and_explain(val_res, {}, obs, "Goa", 15000.0, ["Historical Places"])

    audit = res["audit_checks"]
    assert audit["availability_observation_present"] is True
    assert audit["availability_missing_status"] is True
    assert audit["availability_confirmed"] is False
    assert "operating status was missing" in res["summary_explanation"]


def test_reflection_availability_simulated_source():
    from backend.agent.reflection import AgentReflection
    reflector = AgentReflection()
    obs = [{
        "tool": "availability.checkStatus",
        "status": "success",
        "evidence": "Simulated result",
        "data": {"attraction_name": "Beach", "is_open": True, "source": "Simulated Availability Service"},
    }]
    val_res = {"valid": True, "budgetValid": True, "weatherValid": True, "availabilityValid": True}
    res = reflector.reflect_and_explain(val_res, {}, obs, "Goa", 15000.0, ["Beaches"])

    audit = res["audit_checks"]
    assert audit["availability_open"] is True
    assert audit["availability_is_simulated"] is True
    assert audit["availability_confirmed"] is False
    assert "open via simulated provider data" in res["summary_explanation"]


def test_reflection_availability_failed_tool():
    from backend.agent.reflection import AgentReflection
    reflector = AgentReflection()
    obs = [{
        "tool": "availability.checkStatus",
        "status": "error",
        "evidence": "MCP execution timeout",
        "data": {"error": "TimeoutError"},
    }]
    val_res = {"valid": False, "budgetValid": True, "weatherValid": True, "availabilityValid": False}
    res = reflector.reflect_and_explain(val_res, {}, obs, "Goa", 15000.0, ["Historical Places"])

    audit = res["audit_checks"]
    assert audit["availability_observation_present"] is True
    assert audit["availability_confirmed"] is False
    assert len(res["failed_observations"]) == 1
    assert len(res["evidence_citations"]) == 0
    assert "did not return a successful observation" in res["summary_explanation"]


def test_reflection_availability_real_confirmed():
    from backend.agent.reflection import AgentReflection
    reflector = AgentReflection()
    obs = [{
        "tool": "availability.checkStatus",
        "status": "success",
        "evidence": "Confirmed live with ticketing office",
        "data": {"attraction_name": "Monument", "is_open": True, "source": "Official Ticketing API", "confirmed": True},
    }]
    val_res = {"valid": True, "budgetValid": True, "weatherValid": True, "availabilityValid": True}
    res = reflector.reflect_and_explain(val_res, {}, obs, "Goa", 15000.0, ["Historical Places"])

    audit = res["audit_checks"]
    assert audit["availability_open"] is True
    assert audit["availability_is_simulated"] is False
    assert audit["availability_confirmed"] is True
    assert "independently confirmed by real-world provider evidence" in res["summary_explanation"]
    assert "ev_001_availability_checkStatus" in res["evidence_citations"]


# ==============================================================================
# Issue 3 Regression Tests: Multi-Day Weather Calendar Dates & API Horizon Checks
# ==============================================================================

def test_weather_day1_date():
    """Verify Day 1 uses the trip start date."""
    from backend.providers.real import calculate_forecast_date, RealProvider
    from backend.providers.demo import DemoProvider

    start_date = "2026-11-20"
    expected = "2026-11-20"
    assert calculate_forecast_date(start_date, 1) == expected

    demo = DemoProvider()
    res = demo.get_weather_forecast("Goa", start_date=start_date, day=1)
    assert res["day"] == 1
    assert res["date"] == expected

    real = RealProvider()
    res_real = real.get_weather_forecast("Goa", day=1, start_date=start_date)
    assert res_real["day"] == 1
    assert res_real["date"] == expected


def test_weather_day2_date():
    """Verify Day 2 uses start_date + 1 day."""
    from backend.providers.real import calculate_forecast_date, RealProvider
    from backend.providers.demo import DemoProvider

    start_date = "2026-11-20"
    expected = "2026-11-21"
    assert calculate_forecast_date(start_date, 2) == expected

    demo = DemoProvider()
    res = demo.get_weather_forecast("Goa", start_date=start_date, day=2)
    assert res["day"] == 2
    assert res["date"] == expected
    assert res["condition"] == "heavy_rain_warning"
    assert res["suitableForOutdoor"] is False

    real = RealProvider()
    res_real = real.get_weather_forecast("Goa", day=2, start_date=start_date)
    assert res_real["day"] == 2
    assert res_real["date"] == expected


def test_weather_day7_date():
    """Verify Day 7 uses start_date + 6 days."""
    from backend.providers.real import calculate_forecast_date, RealProvider
    from backend.providers.demo import DemoProvider

    start_date = "2026-11-20"
    expected = "2026-11-26"
    assert calculate_forecast_date(start_date, 7) == expected

    demo = DemoProvider()
    res = demo.get_weather_forecast("Goa", start_date=start_date, day=7)
    assert res["day"] == 7
    assert res["date"] == expected

    real = RealProvider()
    res_real = real.get_weather_forecast("Goa", day=7, start_date=start_date)
    assert res_real["day"] == 7
    assert res_real["date"] == expected


def test_weather_consecutive_trip_days():
    """Verify consecutive trip days calculate and increment dates correctly."""
    from backend.providers.real import calculate_forecast_date
    from backend.providers.demo import DemoProvider
    import datetime

    start_str = "2026-12-01"
    base_date = datetime.date.fromisoformat(start_str)

    for day in range(1, 15):
        expected_date = (base_date + datetime.timedelta(days=day - 1)).isoformat()
        assert calculate_forecast_date(start_str, day) == expected_date

    demo = DemoProvider()
    for d in range(1, 5):
        expected_date = (datetime.date(2026, 11, 20) + datetime.timedelta(days=d - 1)).isoformat()
        res = demo.get_weather_forecast("Goa", start_date="2026-11-20", day=d)
        assert res["date"] == expected_date
        assert res["day"] == d


def test_weather_outside_horizon(mcp):
    """Verify dates outside Open-Meteo horizon raise ValueError and are treated as unusable evidence."""
    from backend.providers.real import RealProvider
    from backend.agent.travel_agent import ResilientTravelAgent

    real = RealProvider()

    # Dates far in the future (>16 days) raise ValueError
    with pytest.raises(ValueError) as excinfo:
        real.get_weather_forecast("Goa", date="2099-01-01", day=1)
    assert "allowed forecast horizon" in str(excinfo.value)

    # When invoked via MCP Tool Boundary with RealProvider
    obs = mcp.invoke_tool(
        "weather.getForecast",
        {"destination": "Goa", "date": "2099-01-01", "day": 1},
        provider=real,
    )
    assert obs.status == "error"

    # Must NOT be counted as usable weather observation
    assert ResilientTravelAgent._is_usable_weather_observation(obs.model_dump()) is False


def test_weather_flexible_date():
    """Verify flexible dates without a calendar start date return valid forecasts from today."""
    from backend.providers.real import calculate_forecast_date, RealProvider
    from backend.providers.demo import DemoProvider

    # calculate_forecast_date returns empty string for flexible/none
    assert calculate_forecast_date("", 1) == ""
    assert calculate_forecast_date("flexible", 2) == ""
    assert calculate_forecast_date(None, 3) == ""

    demo = DemoProvider()
    res_demo = demo.get_weather_forecast("Goa", date="", day=1)
    assert res_demo["day"] == 1
    assert res_demo["suitableForOutdoor"] is True

    real = RealProvider()
    res_real = real.get_weather_forecast("Goa", date="", day=1)
    assert res_real["day"] == 1
    assert res_real["date"] != ""
    assert res_real["suitableForOutdoor"] is True


def test_weather_api_failure(mcp):
    """Verify unconfigured destination produces error observation without crashing."""
    from backend.providers.real import RealProvider
    from backend.agent.travel_agent import ResilientTravelAgent

    real = RealProvider()

    # Destination not in coordinates dictionary raises ValueError
    with pytest.raises(ValueError) as excinfo:
        real.get_weather_forecast("AtlantisCity", day=1)
    assert "not configured" in str(excinfo.value)

    # MCP boundary returns structured error observation
    obs = mcp.invoke_tool(
        "weather.getForecast",
        {"destination": "AtlantisCity", "day": 1},
        provider=real,
    )
    assert obs.status == "error"
    assert ResilientTravelAgent._is_usable_weather_observation(obs.model_dump()) is False


# ==============================================================================
# Issue 4 Regression Tests: RecoveryEngine Route Origin & Candidate Deduplication
# ==============================================================================

def test_recovery_morning_activity_location_origin(mcp):
    """Verify replacing a morning activity uses that activity's location as route origin."""
    from backend.agent.recovery import RecoveryEngine
    from backend.providers.demo import DemoProvider

    engine = RecoveryEngine()
    provider = DemoProvider()

    itinerary = [
        {
            "day": 1,
            "morning": {"activity": "Fort Aguada", "location": "Candolim, Goa", "is_outdoor": False, "cost_inr": 350.0},
            "afternoon": {"activity": "Beach Walk", "location": "Baga, Goa", "is_outdoor": True, "cost_inr": 200.0},
            "evening": {"activity": "Market", "location": "Anjuna, Goa", "is_outdoor": False, "cost_inr": 300.0},
        },
        {
            "day": 2,
            "morning": {"activity": "Calangute Beach Sports", "location": "Calangute Beach, North Goa", "is_outdoor": True, "cost_inr": 1500.0},
            "afternoon": {"activity": "Spice Plantation", "location": "Ponda, Goa", "is_outdoor": False, "cost_inr": 800.0},
            "evening": {"activity": "Dinner Cruise", "location": "Panaji, Goa", "is_outdoor": False, "cost_inr": 1000.0},
        }
    ]
    weather_obs = [
        {"day": 2, "destination": "Goa", "suitableForOutdoor": False, "condition": "heavy_rain_warning"}
    ]

    revised, info = engine.detect_and_recover(
        itinerary=itinerary,
        weather_observations=weather_obs,
        provider=provider,
        user_interests=["Historical Places"],
        mcp_boundary=mcp,
    )

    assert info["occurred"] is True
    assert info["status"] == "completed"
    recovered_morning = revised[1]["morning"]
    assert recovered_morning["was_recovered"] is True
    assert recovered_morning["recovery_evidence"]["route_origin"] == "Calangute Beach, North Goa"


def test_recovery_non_morning_activity_location_origin(mcp):
    """Verify replacing a non-morning activity uses that activity's own location, not morning."""
    from backend.agent.recovery import RecoveryEngine
    from backend.providers.demo import DemoProvider

    engine = RecoveryEngine()
    provider = DemoProvider()

    itinerary = [
        {
            "day": 2,
            "morning": {"activity": "Indoor State Museum", "location": "Panaji, Goa", "is_outdoor": False, "cost_inr": 250.0},
            "afternoon": {"activity": "Baga Beach Parasailing", "location": "Baga Beach, North Goa", "is_outdoor": True, "cost_inr": 1200.0},
            "evening": {"activity": "Fontainhas Walk", "location": "Panaji, Goa", "is_outdoor": False, "cost_inr": 300.0},
        }
    ]
    weather_obs = [
        {"day": 2, "destination": "Goa", "suitableForOutdoor": False, "condition": "heavy_rain"}
    ]

    revised, info = engine.detect_and_recover(
        itinerary=itinerary,
        weather_observations=weather_obs,
        provider=provider,
        user_interests=["Historical Places"],
        mcp_boundary=mcp,
    )

    assert info["occurred"] is True
    recovered_afternoon = revised[0]["afternoon"]
    assert recovered_afternoon["was_recovered"] is True
    # Crucial: Origin MUST be the afternoon activity's location, NOT morning's location!
    assert recovered_afternoon["recovery_evidence"]["route_origin"] == "Baga Beach, North Goa"


def test_recovery_missing_activity_location_uses_fallback(mcp):
    """Verify missing activity location uses a valid documented fallback from the itinerary."""
    from backend.agent.recovery import RecoveryEngine
    from backend.providers.demo import DemoProvider

    engine = RecoveryEngine()
    provider = DemoProvider()

    itinerary = [
        {
            "day": 2,
            # Morning activity location is empty/missing
            "morning": {"activity": "Outdoor Trek", "location": "", "is_outdoor": True, "cost_inr": 500.0},
            "afternoon": {"activity": "Spice Garden", "location": "Ponda Foothills, Goa", "is_outdoor": False, "cost_inr": 600.0},
            "evening": {"activity": "Dinner", "location": "Panaji, Goa", "is_outdoor": False, "cost_inr": 800.0},
            "hotel": "Heritage Resort, Candolim, Goa",
        }
    ]
    weather_obs = [
        {"day": 2, "destination": "Goa", "suitableForOutdoor": False, "condition": "monsoon_rain"}
    ]

    revised, info = engine.detect_and_recover(
        itinerary=itinerary,
        weather_observations=weather_obs,
        provider=provider,
        user_interests=["Historical Places"],
        mcp_boundary=mcp,
    )

    assert info["occurred"] is True
    assert info["status"] == "completed"
    recovered_morning = revised[0]["morning"]
    assert recovered_morning["was_recovered"] is True
    # Used afternoon location or hotel as valid fallback
    assert recovered_morning["recovery_evidence"]["route_origin"] in [
        "Ponda Foothills, Goa",
        "Heritage Resort, Candolim, Goa",
    ]


def test_recovery_missing_location_and_missing_fallback_fails(mcp):
    """Verify missing activity location AND missing fallback causes explicit failure without inventing a location."""
    from backend.agent.recovery import RecoveryEngine
    from backend.providers.demo import DemoProvider

    engine = RecoveryEngine()
    provider = DemoProvider()

    itinerary = [
        {
            "day": 2,
            # Missing location and no other slot or hotel has any location
            "morning": {"activity": "Outdoor Walk", "location": None, "is_outdoor": True, "cost_inr": 200.0},
            "afternoon": None,
            "evening": None,
        }
    ]
    weather_obs = [
        {"day": 2, "destination": "Goa", "suitableForOutdoor": False, "condition": "heavy_rain"}
    ]

    revised, info = engine.detect_and_recover(
        itinerary=itinerary,
        weather_observations=weather_obs,
        provider=provider,
        user_interests=["Historical Places"],
        mcp_boundary=mcp,
    )

    assert info["status"] == "failed"
    assert info["verified"] is False
    assert any("route origin is unavailable" in f for f in info["failedSlots"])
    # Original activity preserved without inventing fake location
    assert revised[0]["morning"]["activity"] == "Outdoor Walk"


def test_recovery_distinct_candidates_multiple_rainy_slots(mcp):
    """Verify multiple rainy slots select distinct suitable replacement candidates without reusing the same attraction."""
    from backend.agent.recovery import RecoveryEngine
    from backend.providers.demo import DemoProvider

    engine = RecoveryEngine()
    provider = DemoProvider()

    # Day 2 has 3 outdoor activities
    itinerary = [
        {
            "day": 2,
            "morning": {"activity": "Beach Sports", "location": "Calangute, Goa", "is_outdoor": True, "cost_inr": 1000.0},
            "afternoon": {"activity": "Boat Tour", "location": "Baga, Goa", "is_outdoor": True, "cost_inr": 800.0},
            "evening": {"activity": "Sunset Walk", "location": "Anjuna, Goa", "is_outdoor": True, "cost_inr": 300.0},
        }
    ]
    weather_obs = [
        {"day": 2, "destination": "Goa", "suitableForOutdoor": False, "condition": "storm"}
    ]

    revised, info = engine.detect_and_recover(
        itinerary=itinerary,
        weather_observations=weather_obs,
        provider=provider,
        user_interests=["Historical Places"],
        mcp_boundary=mcp,
    )

    assert info["occurred"] is True
    assert info["status"] == "completed"
    assert len(info["replacementActivities"]) == 3

    # All 3 replacements MUST be distinct
    replacements = [
        revised[0]["morning"]["activity"],
        revised[0]["afternoon"]["activity"],
        revised[0]["evening"]["activity"],
    ]
    assert len(set(replacements)) == 3, f"Expected 3 distinct replacements, got: {replacements}"


def test_recovery_candidate_exhaustion_does_not_report_success():
    """Verify candidate exhaustion does NOT report successful recovery and leaves original activity in place."""
    from backend.agent.recovery import RecoveryEngine
    from backend.tools.base import ToolObservation

    class MockMCPSingleCandidate:
        """Mock MCP boundary that returns only 1 indoor candidate to test candidate exhaustion."""
        def invoke_tool(self, tool_name, arguments, provider=None):
            if tool_name == "places.searchAttractions":
                return ToolObservation(
                    tool=tool_name,
                    status="success",
                    destination=arguments.get("destination", "Goa"),
                    data={
                        "attractions": [
                            {
                                "id": "single_01",
                                "name": "Sole Indoor Museum",
                                "location": "Center, Goa",
                                "estimated_cost_inr": 200.0,
                                "is_outdoor": False,
                            }
                        ]
                    },
                    evidence="Sole indoor candidate",
                )
            elif tool_name == "availability.checkStatus":
                return ToolObservation(tool=tool_name, status="success", data={"is_open": True}, evidence="Open")
            elif tool_name == "route.estimateTravel":
                return ToolObservation(tool=tool_name, status="success", data={"travel_time_mins": 20}, evidence="Route ok")
            return ToolObservation(tool=tool_name, status="error", data={}, evidence="Unknown tool")

    engine = RecoveryEngine()
    mock_mcp = MockMCPSingleCandidate()

    # 2 outdoor slots, but boundary only returns 1 candidate
    itinerary = [
        {
            "day": 2,
            "morning": {"activity": "Outdoor 1", "location": "North Goa", "is_outdoor": True, "cost_inr": 500.0},
            "afternoon": {"activity": "Outdoor 2", "location": "North Goa", "is_outdoor": True, "cost_inr": 600.0},
            "evening": {"activity": "Indoor Dinner", "location": "Panaji, Goa", "is_outdoor": False, "cost_inr": 700.0},
        }
    ]
    weather_obs = [
        {"day": 2, "destination": "Goa", "suitableForOutdoor": False, "condition": "rain"}
    ]

    revised, info = engine.detect_and_recover(
        itinerary=itinerary,
        weather_observations=weather_obs,
        provider=None,
        user_interests=["Historical Places"],
        mcp_boundary=mock_mcp,
    )

    # Recovery must be partial, NOT completed or verified!
    assert info["status"] == "partial"
    assert info["verified"] is False
    assert any("no suitable verified indoor alternative available" in f for f in info["failedSlots"])
    # Second slot must retain original activity
    assert revised[0]["afternoon"]["activity"] == "Outdoor 2"


def test_recovery_rejects_closed_and_overbudget_candidates():
    """Verify closed and over-budget candidates are rejected in favor of suitable open ones."""
    from backend.agent.recovery import RecoveryEngine
    from backend.tools.base import ToolObservation

    class MockMCPFilterBoundary:
        def invoke_tool(self, tool_name, arguments, provider=None):
            if tool_name == "places.searchAttractions":
                return ToolObservation(
                    tool=tool_name,
                    status="success",
                    destination=arguments.get("destination", "Goa"),
                    data={
                        "attractions": [
                            {"id": "cand_01", "name": "Closed Art Gallery", "location": "North, Goa", "estimated_cost_inr": 200.0, "is_outdoor": False},
                            {"id": "cand_02", "name": "Super Luxury Palace", "location": "South, Goa", "estimated_cost_inr": 50000.0, "is_outdoor": False},
                            {"id": "cand_03", "name": "Open Affordable Museum", "location": "Central, Goa", "estimated_cost_inr": 300.0, "is_outdoor": False},
                        ]
                    },
                    evidence="Attractions list",
                )
            elif tool_name == "availability.checkStatus":
                name = arguments.get("attraction_name", "")
                if "Closed" in name:
                    return ToolObservation(tool=tool_name, status="warning", data={"is_open": False}, evidence="Closed")
                return ToolObservation(tool=tool_name, status="success", data={"is_open": True}, evidence="Open daily")
            elif tool_name == "route.estimateTravel":
                return ToolObservation(tool=tool_name, status="success", data={"travel_time_mins": 25}, evidence="Route ok")
            return ToolObservation(tool=tool_name, status="error", data={}, evidence="Unknown tool")

    engine = RecoveryEngine()
    mock_mcp = MockMCPFilterBoundary()

    itinerary = [
        {
            "day": 2,
            "morning": {"activity": "Beach Trek", "location": "Calangute, Goa", "is_outdoor": True, "cost_inr": 500.0},
        }
    ]
    weather_obs = [{"day": 2, "destination": "Goa", "suitableForOutdoor": False, "condition": "rain"}]

    revised, info = engine.detect_and_recover(
        itinerary=itinerary,
        weather_observations=weather_obs,
        provider=None,
        user_interests=["Historical Places"],
        mcp_boundary=mock_mcp,
        budget=10000.0,  # Rejects 50000.0 candidate
    )

    assert info["status"] == "completed"
    assert info["verified"] is True
    # Must select cand_03 ("Open Affordable Museum"), skipping closed cand_01 and over-budget cand_02!
    assert revised[0]["morning"]["activity"] == "Open Affordable Museum"


def test_recovery_failure_visible_in_trace():
    """Verify recovery failure remains visible in central execution trace observations."""
    from backend.agent.recovery import RecoveryEngine
    from backend.tools.base import ToolObservation

    class MockMCPNoPlacesBoundary:
        def invoke_tool(self, tool_name, arguments, provider=None):
            return ToolObservation(
                tool=tool_name,
                status="success",
                destination=arguments.get("destination", "Goa"),
                data={"attractions": []},
                evidence="No places found",
            )

    engine = RecoveryEngine()
    mock_mcp = MockMCPNoPlacesBoundary()
    trace_obs = []

    itinerary = [
        {
            "day": 2,
            "morning": {"activity": "Surfing", "location": "Anjuna, Goa", "is_outdoor": True, "cost_inr": 1500.0},
        }
    ]
    weather_obs = [{"day": 2, "destination": "Goa", "suitableForOutdoor": False, "condition": "cyclone"}]

    revised, info = engine.detect_and_recover(
        itinerary=itinerary,
        weather_observations=weather_obs,
        provider=None,
        user_interests=["Beaches"],
        mcp_boundary=mock_mcp,
        observations=trace_obs,
    )

    assert info["status"] == "failed"
    assert info["verified"] is False
    assert len(info["failedSlots"]) > 0
    # Search places observation must be visible in the trace
    assert len(trace_obs) > 0
    assert trace_obs[0]["tool"] == "places.searchAttractions"


# ==============================================================================
# Issue 4 Follow-up Regression Tests: Availability Fail-Closed, Budget & Route
# ==============================================================================

def test_recovery_availability_open_demo_labelled_simulated(mcp):
    """Verify availability explicitly open in DemoProvider is labelled simulated and not real confirmation."""
    from backend.agent.recovery import RecoveryEngine
    from backend.providers.demo import DemoProvider

    engine = RecoveryEngine()
    provider = DemoProvider()
    itinerary = [
        {"day": 2, "morning": {"activity": "Beach Sports", "location": "Calangute, Goa", "is_outdoor": True, "cost_inr": 800.0}}
    ]
    weather_obs = [{"day": 2, "destination": "Goa", "suitableForOutdoor": False, "condition": "rain"}]

    revised, info = engine.detect_and_recover(itinerary, weather_obs, provider, ["Historical Places"], mcp)
    assert info["status"] == "completed"
    recovered = revised[0]["morning"]
    evidence = recovered["recovery_evidence"]

    assert evidence["availability_open"] is True
    assert evidence["availability_is_simulated"] is True
    assert evidence["availability_confirmed_real"] is False
    assert "Simulated" in evidence["availability_source"]
    assert info["hasSimulatedEvidence"] is True
    assert info["hasRealWorldConfirmation"] is False


def test_recovery_availability_explicitly_closed_rejected():
    """Verify candidate with is_open=False is rejected under fail-closed verification."""
    from backend.agent.recovery import RecoveryEngine
    from backend.tools.base import ToolObservation

    class MockMCPClosed:
        def invoke_tool(self, tool_name, arguments, provider=None):
            if tool_name == "places.searchAttractions":
                return ToolObservation(
                    tool=tool_name, status="success",
                    data={"attractions": [{"id": "c1", "name": "Closed Museum", "location": "Goa", "estimated_cost_inr": 200.0, "is_outdoor": False}]},
                    evidence="Places ok"
                )
            elif tool_name == "availability.checkStatus":
                return ToolObservation(tool=tool_name, status="success", data={"is_open": False}, evidence="Closed")
            elif tool_name == "route.estimateTravel":
                return ToolObservation(tool=tool_name, status="success", data={"travel_time_mins": 20}, evidence="Route ok")
            return ToolObservation(tool=tool_name, status="error", data={}, evidence="Err")

    engine = RecoveryEngine()
    itinerary = [{"day": 2, "morning": {"activity": "Beach", "location": "Goa", "is_outdoor": True, "cost_inr": 500.0}}]
    weather = [{"day": 2, "destination": "Goa", "suitableForOutdoor": False}]

    revised, info = engine.detect_and_recover(itinerary, weather, None, ["Historical Places"], MockMCPClosed())
    assert info["status"] == "failed"
    assert info["verified"] is False
    assert revised[0]["morning"]["activity"] == "Beach"


def test_recovery_availability_missing_is_open_rejected():
    """Verify candidate with missing or None is_open is rejected under fail-closed verification."""
    from backend.agent.recovery import RecoveryEngine
    from backend.tools.base import ToolObservation

    class MockMCPMissingIsOpen:
        def invoke_tool(self, tool_name, arguments, provider=None):
            if tool_name == "places.searchAttractions":
                return ToolObservation(
                    tool=tool_name, status="success",
                    data={"attractions": [{"id": "c1", "name": "Missing Status Museum", "location": "Goa", "estimated_cost_inr": 200.0, "is_outdoor": False}]},
                    evidence="Places ok"
                )
            elif tool_name == "availability.checkStatus":
                # Returns data dict without explicit is_open boolean
                return ToolObservation(tool=tool_name, status="success", data={"operating_hours": "09:00 - 18:00"}, evidence="Missing is_open")
            elif tool_name == "route.estimateTravel":
                return ToolObservation(tool=tool_name, status="success", data={"travel_time_mins": 20}, evidence="Route ok")
            return ToolObservation(tool=tool_name, status="error", data={}, evidence="Err")

    engine = RecoveryEngine()
    itinerary = [{"day": 2, "morning": {"activity": "Beach", "location": "Goa", "is_outdoor": True, "cost_inr": 500.0}}]
    weather = [{"day": 2, "destination": "Goa", "suitableForOutdoor": False}]

    revised, info = engine.detect_and_recover(itinerary, weather, None, ["Historical Places"], MockMCPMissingIsOpen())
    assert info["status"] == "failed"
    assert info["verified"] is False
    assert revised[0]["morning"]["activity"] == "Beach"


def test_recovery_availability_failed_observation_rejected():
    """Verify failed availability tool call rejects candidate fail-closed."""
    from backend.agent.recovery import RecoveryEngine
    from backend.tools.base import ToolObservation

    class MockMCPFailedAvail:
        def invoke_tool(self, tool_name, arguments, provider=None):
            if tool_name == "places.searchAttractions":
                return ToolObservation(
                    tool=tool_name, status="success",
                    data={"attractions": [{"id": "c1", "name": "Museum", "location": "Goa", "estimated_cost_inr": 200.0, "is_outdoor": False}]},
                    evidence="Places ok"
                )
            elif tool_name == "availability.checkStatus":
                return ToolObservation(tool=tool_name, status="error", data={"error": "API timeout"}, evidence="Timeout")
            elif tool_name == "route.estimateTravel":
                return ToolObservation(tool=tool_name, status="success", data={"travel_time_mins": 20}, evidence="Route ok")
            return ToolObservation(tool=tool_name, status="error", data={}, evidence="Err")

    engine = RecoveryEngine()
    itinerary = [{"day": 2, "morning": {"activity": "Beach", "location": "Goa", "is_outdoor": True, "cost_inr": 500.0}}]
    weather = [{"day": 2, "destination": "Goa", "suitableForOutdoor": False}]

    revised, info = engine.detect_and_recover(itinerary, weather, None, ["Historical Places"], MockMCPFailedAvail())
    assert info["status"] == "failed"
    assert info["verified"] is False


def test_recovery_real_provider_simulated_not_real_confirmation(mcp):
    """Verify RealProvider availability and route are marked simulated, not real booking confirmation."""
    from backend.agent.recovery import RecoveryEngine
    from backend.providers.real import RealProvider

    engine = RecoveryEngine()
    provider = RealProvider()
    itinerary = [
        {"day": 2, "morning": {"activity": "Beach Walk", "location": "Central Goa", "is_outdoor": True, "cost_inr": 500.0}}
    ]
    weather = [{"day": 2, "destination": "Goa", "suitableForOutdoor": False, "condition": "rain"}]

    revised, info = engine.detect_and_recover(itinerary, weather, provider, ["Historical Places"], mcp)
    assert info["status"] == "completed"
    recovered = revised[0]["morning"]
    ev = recovered["recovery_evidence"]

    assert ev["availability_is_simulated"] is True
    assert ev["availability_confirmed_real"] is False
    assert "Simulated Availability" in ev["availability_source"]
    assert ev["route_is_simulated"] is True
    assert ev["route_confirmed_real"] is False
    assert info["hasRealWorldConfirmation"] is False


def test_recovery_budget_exhausted_by_previous_activities():
    """Verify replacement candidate is rejected if remaining budget is already exhausted."""
    from backend.agent.recovery import RecoveryEngine
    from backend.tools.base import ToolObservation

    class MockMCPBudget:
        def invoke_tool(self, tool_name, arguments, provider=None):
            if tool_name == "places.searchAttractions":
                return ToolObservation(
                    tool=tool_name, status="success",
                    data={"attractions": [{"id": "c1", "name": "Indoor Gallery", "location": "Goa", "estimated_cost_inr": 400.0, "is_outdoor": False}]},
                    evidence="Places ok"
                )
            elif tool_name == "availability.checkStatus":
                return ToolObservation(tool=tool_name, status="success", data={"is_open": True}, evidence="Open")
            elif tool_name == "route.estimateTravel":
                return ToolObservation(tool=tool_name, status="success", data={"travel_time_mins": 20}, evidence="Route ok")
            return ToolObservation(tool=tool_name, status="error", data={}, evidence="Err")

    engine = RecoveryEngine()
    # 2 days: food overhead = 2 * 1200 = 2400 (no transit 400).
    # Other activity costs 2500. Committed = 4900.
    # Budget = 5000. Remaining budget = 100.
    # Candidate costs 400 > 100 -> Exceeds remaining budget!
    itinerary = [
        {"day": 1, "morning": {"activity": "Expensive Activity", "location": "Goa", "is_outdoor": False, "cost_inr": 2500.0}},
        {"day": 2, "morning": {"activity": "Outdoor Trek", "location": "Goa", "is_outdoor": True, "cost_inr": 200.0}},
    ]
    weather = [{"day": 2, "destination": "Goa", "suitableForOutdoor": False}]

    revised, info = engine.detect_and_recover(itinerary, weather, None, ["Historical Places"], MockMCPBudget(), budget=5000.0)
    assert info["status"] == "failed"
    assert info["verified"] is False
    assert revised[1]["morning"]["activity"] == "Outdoor Trek"


def test_recovery_cost_within_remaining_budget():
    """Verify replacement candidate is accepted when cost is within remaining budget."""
    from backend.agent.recovery import RecoveryEngine
    from backend.tools.base import ToolObservation

    class MockMCPBudget:
        def invoke_tool(self, tool_name, arguments, provider=None):
            if tool_name == "places.searchAttractions":
                return ToolObservation(
                    tool=tool_name, status="success",
                    data={"attractions": [{"id": "c1", "name": "Affordable Gallery", "location": "Goa", "estimated_cost_inr": 300.0, "is_outdoor": False}]},
                    evidence="Places ok"
                )
            elif tool_name == "availability.checkStatus":
                return ToolObservation(tool=tool_name, status="success", data={"is_open": True}, evidence="Open")
            elif tool_name == "route.estimateTravel":
                return ToolObservation(tool=tool_name, status="success", data={"travel_time_mins": 20}, evidence="Route ok")
            return ToolObservation(tool=tool_name, status="error", data={}, evidence="Err")

    engine = RecoveryEngine()
    # 2 days: food overhead = 2 * 1200 = 2400 (no transit 400). Other activity = 500. Committed = 2900.
    # Budget = 5000. Remaining = 2100. Candidate = 300 <= 2100 -> Accepted!
    itinerary = [
        {"day": 1, "morning": {"activity": "Museum 1", "location": "Goa", "is_outdoor": False, "cost_inr": 500.0}},
        {"day": 2, "morning": {"activity": "Outdoor Trek", "location": "Goa", "is_outdoor": True, "cost_inr": 200.0}},
    ]
    weather = [{"day": 2, "destination": "Goa", "suitableForOutdoor": False}]

    revised, info = engine.detect_and_recover(itinerary, weather, None, ["Historical Places"], MockMCPBudget(), budget=5000.0)
    assert info["status"] == "completed"
    assert info["verified"] is True
    assert revised[1]["morning"]["activity"] == "Affordable Gallery"
    assert revised[1]["morning"]["recovery_evidence"]["budget_feasibility_verified"] is True


def test_recovery_original_activity_cost_not_double_counted():
    """Verify original activity being replaced is not double-counted in committed cost."""
    from backend.agent.recovery import RecoveryEngine
    from backend.tools.base import ToolObservation

    class MockMCPBudget:
        def invoke_tool(self, tool_name, arguments, provider=None):
            if tool_name == "places.searchAttractions":
                return ToolObservation(
                    tool=tool_name, status="success",
                    data={"attractions": [{"id": "c1", "name": "Replacement Art Gallery", "location": "Goa", "estimated_cost_inr": 800.0, "is_outdoor": False}]},
                    evidence="Places ok"
                )
            elif tool_name == "availability.checkStatus":
                return ToolObservation(tool=tool_name, status="success", data={"is_open": True}, evidence="Open")
            elif tool_name == "route.estimateTravel":
                return ToolObservation(tool=tool_name, status="success", data={"travel_time_mins": 20}, evidence="Route ok")
            return ToolObservation(tool=tool_name, status="error", data={}, evidence="Err")

    engine = RecoveryEngine()
    # 1 day: food overhead = 1200 (no transit 400).
    # Original activity being replaced cost 3000.0!
    # Budget = 3000.0.
    # If double-counted: committed = 3000 + 1200 = 4200 > 3000 (remaining < 0, rejected!).
    # Without double-counting: committed = 0 + 1200 = 1200. Remaining = 1800.
    # Candidate costs 800 <= 1800 -> Accepted!
    itinerary = [
        {"day": 1, "morning": {"activity": "Very Expensive Outdoor Activity", "location": "Goa", "is_outdoor": True, "cost_inr": 3000.0}}
    ]
    weather = [{"day": 1, "destination": "Goa", "suitableForOutdoor": False}]

    revised, info = engine.detect_and_recover(itinerary, weather, None, ["Historical Places"], MockMCPBudget(), budget=3000.0)
    assert info["status"] == "completed"
    assert info["verified"] is True
    assert revised[0]["morning"]["activity"] == "Replacement Art Gallery"


def test_recovery_malformed_route_observation_rejected():
    """Verify malformed or invalid travel_time_mins rejects candidate fail-closed."""
    from backend.agent.recovery import RecoveryEngine
    from backend.tools.base import ToolObservation

    class MockMCPBadRoute:
        def invoke_tool(self, tool_name, arguments, provider=None):
            if tool_name == "places.searchAttractions":
                return ToolObservation(
                    tool=tool_name, status="success",
                    data={"attractions": [{"id": "c1", "name": "Museum", "location": "Goa", "estimated_cost_inr": 200.0, "is_outdoor": False}]},
                    evidence="Places ok"
                )
            elif tool_name == "availability.checkStatus":
                return ToolObservation(tool=tool_name, status="success", data={"is_open": True}, evidence="Open")
            elif tool_name == "route.estimateTravel":
                # Malformed: negative travel time or missing number
                return ToolObservation(tool=tool_name, status="success", data={"travel_time_mins": -15.0}, evidence="Bad time")
            return ToolObservation(tool=tool_name, status="error", data={}, evidence="Err")

    engine = RecoveryEngine()
    itinerary = [{"day": 2, "morning": {"activity": "Beach", "location": "Goa", "is_outdoor": True, "cost_inr": 500.0}}]
    weather = [{"day": 2, "destination": "Goa", "suitableForOutdoor": False}]

    revised, info = engine.detect_and_recover(itinerary, weather, None, ["Historical Places"], MockMCPBadRoute())
    assert info["status"] == "failed"
    assert info["verified"] is False
    assert revised[0]["morning"]["activity"] == "Beach"


def test_recovery_simulated_route_evidence_accurately_labelled(mcp):
    """Verify simulated route evidence is accurately marked as simulated and not confirmed real."""
    from backend.agent.recovery import RecoveryEngine
    from backend.providers.demo import DemoProvider

    engine = RecoveryEngine()
    provider = DemoProvider()
    itinerary = [{"day": 2, "morning": {"activity": "Beach", "location": "Calangute, Goa", "is_outdoor": True, "cost_inr": 500.0}}]
    weather = [{"day": 2, "destination": "Goa", "suitableForOutdoor": False}]

    revised, info = engine.detect_and_recover(itinerary, weather, provider, ["Historical Places"], mcp)
    ev = revised[0]["morning"]["recovery_evidence"]

    assert ev["route_is_simulated"] is True
    assert ev["route_confirmed_real"] is False
    assert "Simulated" in ev["route_source"] or "Demo" in ev["route_source"]


def test_recovery_does_not_claim_real_confirmation_from_simulated_tools(mcp):
    """Verify recovery explanation and verification never claims real confirmation when using simulated tools."""
    from backend.agent.recovery import RecoveryEngine
    from backend.providers.demo import DemoProvider

    engine = RecoveryEngine()
    provider = DemoProvider()
    itinerary = [{"day": 2, "morning": {"activity": "Beach", "location": "Calangute, Goa", "is_outdoor": True, "cost_inr": 500.0}}]
    weather = [{"day": 2, "destination": "Goa", "suitableForOutdoor": False}]

    revised, info = engine.detect_and_recover(itinerary, weather, provider, ["Historical Places"], mcp)
    assert info["hasRealWorldConfirmation"] is False
    assert info["hasSimulatedEvidence"] is True
    assert "no real-world live confirmation claimed" in info["verification"].lower()


def test_recovery_no_invented_transit_cost():
    """Verify remaining budget does not subtract any invented transit overhead when none is supplied."""
    from backend.agent.recovery import RecoveryEngine
    itinerary = [
        {"day": 1, "morning": {"activity": "Museum", "cost_inr": 500.0}},
        {"day": 2, "morning": {"activity": "Trek", "cost_inr": 200.0}},
    ]
    # Budget 5000, replacing day 2 morning. Committed activity: day 1 morning = 500.
    # 2 days food = 2 * 1200 = 2400.
    # Total committed = 2900.
    # Remaining budget = 5000 - 2900 = 2100 (if 400/day transit were added, it would be 1300).
    rem, ok = RecoveryEngine._calculate_remaining_budget(itinerary, 5000.0, 2, "morning")
    assert ok is True
    assert rem == 2100.0


def test_recovery_food_allowance_calculation():
    """Verify food allowance is calculated as exactly total_days * 1200.0."""
    from backend.agent.recovery import RecoveryEngine
    # 3 days: food = 3 * 1200 = 3600.
    itinerary = [
        {"day": 1, "morning": {"activity": "Act 1", "cost_inr": 100.0}},
        {"day": 2, "morning": {"activity": "Act 2", "cost_inr": 100.0}},
        {"day": 3, "morning": {"activity": "Act 3", "cost_inr": 100.0}},
    ]
    # Replacing day 3 morning. Committed activities = 100 + 100 = 200.
    # Budget = 4000. Total committed = 3600 + 200 = 3800. Remaining = 200.
    rem, ok = RecoveryEngine._calculate_remaining_budget(itinerary, 4000.0, 3, "morning")
    assert ok is True
    assert rem == 200.0

    # With trip_context specifying 4 days: food = 4 * 1200 = 4800.
    # Budget = 6000. Total committed = 4800 + 200 = 5000. Remaining = 1000.
    rem4, ok4 = RecoveryEngine._calculate_remaining_budget(
        itinerary, 6000.0, 3, "morning", trip_context={"days": 4}
    )
    assert ok4 is True
    assert rem4 == 1000.0


def test_recovery_missing_activity_cost_unverified():
    """Verify missing activity cost causes budget verification to fail (is_calculable=False)."""
    from backend.agent.recovery import RecoveryEngine
    itinerary = [
        {"day": 1, "morning": {"activity": "Mystery Activity"}},  # No cost_inr or estimated_cost_inr
        {"day": 2, "morning": {"activity": "Trek", "cost_inr": 200.0}},
    ]
    rem, ok = RecoveryEngine._calculate_remaining_budget(itinerary, 5000.0, 2, "morning")
    assert ok is False
    assert rem is None


def test_recovery_invalid_and_nonfinite_activity_costs_unverified():
    """Verify invalid, negative, or non-finite activity costs cause is_calculable=False."""
    from backend.agent.recovery import RecoveryEngine
    for bad_cost in [-100.0, "invalid", float("nan"), float("inf"), None]:
        itinerary = [
            {"day": 1, "morning": {"activity": "Museum", "cost_inr": bad_cost}},
            {"day": 2, "morning": {"activity": "Trek", "cost_inr": 200.0}},
        ]
        rem, ok = RecoveryEngine._calculate_remaining_budget(itinerary, 5000.0, 2, "morning")
        assert ok is False, f"Failed to reject bad cost: {bad_cost}"
        assert rem is None


def test_recovery_previously_selected_replacements_included():
    """Verify previously selected replacement costs are included in committed budget for subsequent slots."""
    from backend.agent.recovery import RecoveryEngine
    from backend.tools.base import ToolObservation

    class MockMCPSlots:
        def invoke_tool(self, tool_name, arguments, provider=None):
            if tool_name == "places.searchAttractions":
                return ToolObservation(
                    tool=tool_name, status="success",
                    data={"attractions": [
                        {"id": "c1", "name": "Indoor Place 1", "location": "Goa", "estimated_cost_inr": 500.0, "is_outdoor": False},
                        {"id": "c2", "name": "Indoor Place 2", "location": "Goa", "estimated_cost_inr": 500.0, "is_outdoor": False},
                    ]},
                    evidence="Places ok"
                )
            elif tool_name == "availability.checkStatus":
                return ToolObservation(tool=tool_name, status="success", data={"is_open": True}, evidence="Open")
            elif tool_name == "route.estimateTravel":
                return ToolObservation(tool=tool_name, status="success", data={"travel_time_mins": 20}, evidence="Route ok")
            return ToolObservation(tool=tool_name, status="error", data={}, evidence="Err")

    # 1 day: food = 1200. Budget = 2000.
    # Morning and afternoon both outdoor:
    # Initial morning replacement costs 500 -> committed becomes 1200 + 500 = 1700.
    # Remaining budget for afternoon is 2000 - 1700 = 300.
    # Place 2 costs 500 > 300 -> cannot be recovered due to insufficient budget!
    engine = RecoveryEngine()
    itinerary = [
        {
            "day": 1,
            "morning": {"activity": "Outdoor Trek 1", "location": "Goa", "is_outdoor": True, "cost_inr": 100.0},
            "afternoon": {"activity": "Outdoor Trek 2", "location": "Goa", "is_outdoor": True, "cost_inr": 100.0},
        }
    ]
    weather = [{"day": 1, "destination": "Goa", "suitableForOutdoor": False}]

    revised, info = engine.detect_and_recover(itinerary, weather, None, ["Historical Places"], MockMCPSlots(), budget=2000.0)
    # Morning should be recovered to Indoor Place 1
    assert revised[0]["morning"]["activity"] == "Indoor Place 1"
    # Afternoon should NOT be recovered because 500 > remaining budget 300
    assert revised[0]["afternoon"]["activity"] == "Outdoor Trek 2"
    assert "afternoon" in info["failedSlots"][0].lower()


def test_recovery_replaced_activity_cost_excluded_exactly_once():
    """Verify replaced activity is excluded exactly once and other slots on same day are included."""
    from backend.agent.recovery import RecoveryEngine
    itinerary = [
        {
            "day": 1,
            "morning": {"activity": "Museum", "cost_inr": 300.0},
            "afternoon": {"activity": "Outdoor Park", "cost_inr": 1500.0},
            "evening": {"activity": "Dinner Show", "cost_inr": 400.0},
        }
    ]
    # 1 day food = 1200.
    # Replacing day 1 afternoon (cost 1500 excluded).
    # Committed = 1200 (food) + 300 (morning) + 400 (evening) = 1900.
    # Budget = 3000. Remaining = 3000 - 1900 = 1100.
    rem, ok = RecoveryEngine._calculate_remaining_budget(itinerary, 3000.0, 1, "afternoon")
    assert ok is True
    assert rem == 1100.0


def test_recovery_known_transit_costs_included_when_reliably_supplied():
    """Verify transit costs are included when reliably supplied, and rejected if invalid."""
    from backend.agent.recovery import RecoveryEngine
    itinerary = [
        {"day": 1, "morning": {"activity": "Trek", "cost_inr": 100.0}}
    ]
    # Valid transit cost in trip_context: 350.0
    # 1 day food = 1200. Replacing morning (cost 100 excluded).
    # Committed = 1200 + 350 = 1550. Budget = 2000. Remaining = 450.
    rem, ok = RecoveryEngine._calculate_remaining_budget(
        itinerary, 2000.0, 1, "morning", trip_context={"transit_costs": 350.0}
    )
    assert ok is True
    assert rem == 450.0

    # Invalid transit cost in trip_context: -50.0 -> unverified
    rem_inv, ok_inv = RecoveryEngine._calculate_remaining_budget(
        itinerary, 2000.0, 1, "morning", trip_context={"transit_costs": -50.0}
    )
    assert ok_inv is False
    assert rem_inv is None


def test_recovery_budget_insufficient_after_committed_costs_rejects_candidate():
    """Verify replacement candidate is rejected when remaining budget is insufficient after committed costs."""
    from backend.agent.recovery import RecoveryEngine
    from backend.tools.base import ToolObservation

    class MockMCP:
        def invoke_tool(self, tool_name, arguments, provider=None):
            if tool_name == "places.searchAttractions":
                return ToolObservation(
                    tool=tool_name, status="success",
                    data={"attractions": [{"id": "c1", "name": "Fancy Museum", "location": "Goa", "estimated_cost_inr": 350.0, "is_outdoor": False}]},
                    evidence="Places ok"
                )
            elif tool_name == "availability.checkStatus":
                return ToolObservation(tool=tool_name, status="success", data={"is_open": True}, evidence="Open")
            elif tool_name == "route.estimateTravel":
                return ToolObservation(tool=tool_name, status="success", data={"travel_time_mins": 20}, evidence="Route ok")
            return ToolObservation(tool=tool_name, status="error", data={}, evidence="Err")

    engine = RecoveryEngine()
    # 2 days: food = 2400.
    # Day 1 morning committed = 400.
    # Total committed = 2800.
    # Budget = 3000. Remaining = 200.
    # Candidate cost = 350 > 200 -> rejected!
    itinerary = [
        {"day": 1, "morning": {"activity": "Boat Tour", "location": "Goa", "is_outdoor": False, "cost_inr": 400.0}},
        {"day": 2, "morning": {"activity": "Beach Trek", "location": "Goa", "is_outdoor": True, "cost_inr": 200.0}},
    ]
    weather = [{"day": 2, "destination": "Goa", "suitableForOutdoor": False}]

    revised, info = engine.detect_and_recover(itinerary, weather, None, ["Historical Places"], MockMCP(), budget=3000.0)
    assert info["status"] == "failed"
    assert info["verified"] is False
    assert revised[1]["morning"]["activity"] == "Beach Trek"


def test_recovery_unverified_budget_not_fully_verified():
    """Verify that a replacement with valid route and availability but unverified budget produces verified=False."""
    from backend.agent.recovery import RecoveryEngine
    from backend.tools.base import ToolObservation

    class MockMCP:
        def invoke_tool(self, tool_name, arguments, provider=None):
            if tool_name == "places.searchAttractions":
                return ToolObservation(
                    tool=tool_name, status="success",
                    data={"attractions": [{"id": "c1", "name": "Indoor Gallery", "location": "Goa", "estimated_cost_inr": 300.0, "is_outdoor": False}]},
                    evidence="Places ok"
                )
            elif tool_name == "availability.checkStatus":
                return ToolObservation(tool=tool_name, status="success", data={"is_open": True}, evidence="Open")
            elif tool_name == "route.estimateTravel":
                return ToolObservation(tool=tool_name, status="success", data={"travel_time_mins": 25}, evidence="Route ok")
            return ToolObservation(tool=tool_name, status="error", data={}, evidence="Err")

    engine = RecoveryEngine()
    # Itinerary has an uncalculable activity cost (missing cost_inr) -> budget is unverified
    itinerary = [
        {"day": 1, "morning": {"activity": "Unknown Cost Activity", "location": "Goa", "is_outdoor": False}},
        {"day": 2, "morning": {"activity": "Outdoor Trek", "location": "Goa", "is_outdoor": True, "cost_inr": 200.0}},
    ]
    weather = [{"day": 2, "destination": "Goa", "suitableForOutdoor": False}]

    revised, info = engine.detect_and_recover(itinerary, weather, None, ["Historical Places"], MockMCP(), budget=5000.0)

    # Replacement execution succeeded: outdoor trek was replaced by Indoor Gallery
    assert revised[1]["morning"]["activity"] == "Indoor Gallery"
    assert revised[1]["morning"]["was_recovered"] is True
    assert revised[1]["morning"]["recovery_evidence"]["budget_feasibility_verified"] is False

    # But overall verification must NOT be True:
    assert info["status"] == "completed"
    assert info["budgetFeasibilityVerified"] is False
    assert info["verified"] is False
    assert "budget feasibility was not established" in info["verification"].lower() or "budget feasibility remains unverified" in info["recalculation"].lower()


def test_recovery_multiple_replacements_one_unverified_budget_makes_overall_unverified():
    """Verify multiple replacements where one budget is unverified makes overall budget feasibility unverified."""
    from backend.agent.recovery import RecoveryEngine
    from backend.tools.base import ToolObservation

    class MockMCPMulti:
        def invoke_tool(self, tool_name, arguments, provider=None):
            if tool_name == "places.searchAttractions":
                return ToolObservation(
                    tool=tool_name, status="success",
                    data={"attractions": [
                        {"id": "c1", "name": "Indoor Place 1", "location": "Goa", "estimated_cost_inr": 200.0, "is_outdoor": False},
                        {"id": "c2", "name": "Indoor Place 2", "location": "Goa", "estimated_cost_inr": 200.0, "is_outdoor": False},
                    ]},
                    evidence="Places ok"
                )
            elif tool_name == "availability.checkStatus":
                return ToolObservation(tool=tool_name, status="success", data={"is_open": True}, evidence="Open")
            elif tool_name == "route.estimateTravel":
                return ToolObservation(tool=tool_name, status="success", data={"travel_time_mins": 20}, evidence="Route ok")
            return ToolObservation(tool=tool_name, status="error", data={}, evidence="Err")

    engine = RecoveryEngine()
    # No budget provided (budget=None) -> budget feasibility cannot be verified for any replacement
    itinerary = [
        {"day": 1, "morning": {"activity": "Outdoor Trek 1", "location": "Goa", "is_outdoor": True, "cost_inr": 100.0}},
        {"day": 2, "morning": {"activity": "Outdoor Trek 2", "location": "Goa", "is_outdoor": True, "cost_inr": 100.0}},
    ]
    weather = [
        {"day": 1, "destination": "Goa", "suitableForOutdoor": False},
        {"day": 2, "destination": "Goa", "suitableForOutdoor": False},
    ]

    revised, info = engine.detect_and_recover(itinerary, weather, None, ["Historical Places"], MockMCPMulti(), budget=None)

    assert info["status"] == "completed"
    assert len(info["replacementActivities"]) == 2
    assert info["budgetFeasibilityVerified"] is False
    assert info["verified"] is False


def test_reflection_rejects_verified_flag_when_budget_evidence_missing_or_false():
    """Verify reflection rejects recovery verified=True if replacement budget evidence is missing or false."""
    from backend.agent.reflection import AgentReflection

    reflector = AgentReflection()
    val_res = {"valid": True, "budgetValid": True, "weatherValid": True, "timeValid": True, "preferencesValid": True, "availabilityValid": True}
    obs = [
        {"tool": "weather.getForecast", "status": "warning", "evidence": "Heavy rain on Day 1", "data": {"day": 1, "suitableForOutdoor": False, "condition": "rain"}},
        {"tool": "places.searchAttractions", "status": "success", "evidence": "Places found", "data": {"attractions": [{"name": "Art Museum"}]}},
        {"tool": "route.estimateTravel", "status": "success", "evidence": "Route ok", "data": {"travel_time_mins": 25}},
    ]

    # recovery_info claims verified=True, but replacementDetails has budget_feasibility_verified=False
    recovery_info_false = {
        "occurred": True,
        "status": "completed",
        "verified": True,
        "affectedDay": 1,
        "replacementActivities": ["Art Museum"],
        "replacementDetails": [
            {
                "activity": "Art Museum",
                "recovery_evidence": {
                    "places_tool": "places.searchAttractions",
                    "route_tool": "route.estimateTravel",
                    "budget_feasibility_verified": False,
                }
            }
        ]
    }

    res_false = reflector.reflect_and_explain(val_res, recovery_info_false, obs, "Goa", 10000.0, ["Historical Places"])
    assert res_false["audit_checks"]["recovery_budget_verified"] is False
    assert res_false["audit_checks"]["recovery_verified"] is False
    assert "budget feasibility was not established" in res_false["summary_explanation"]

    # Also test when recovery_evidence is missing entirely from replacement
    recovery_info_missing = {
        "occurred": True,
        "status": "completed",
        "verified": True,
        "affectedDay": 1,
        "replacementActivities": ["Art Museum"],
        "replacementDetails": [{"activity": "Art Museum"}]
    }

    res_missing = reflector.reflect_and_explain(val_res, recovery_info_missing, obs, "Goa", 10000.0, ["Historical Places"])
    assert res_missing["audit_checks"]["recovery_budget_verified"] is False
    assert res_missing["audit_checks"]["recovery_verified"] is False
    assert "budget feasibility was not established" in res_missing["summary_explanation"]


def test_reflection_accepts_verified_budget_evidence_when_valid():
    """Verify reflection accepts fully verified recovery when replacement budget evidence is valid."""
    from backend.agent.reflection import AgentReflection

    reflector = AgentReflection()
    val_res = {"valid": True, "budgetValid": True, "weatherValid": True, "timeValid": True, "preferencesValid": True, "availabilityValid": True}
    obs = [
        {"tool": "weather.getForecast", "status": "warning", "evidence": "Heavy rain on Day 1", "data": {"day": 1, "suitableForOutdoor": False, "condition": "rain"}},
        {"tool": "places.searchAttractions", "status": "success", "evidence": "Places found", "data": {"attractions": [{"name": "Art Museum"}]}},
        {"tool": "route.estimateTravel", "status": "success", "evidence": "Route ok", "data": {"travel_time_mins": 25}},
    ]

    recovery_info = {
        "occurred": True,
        "status": "completed",
        "verified": True,
        "affectedDay": 1,
        "budgetFeasibilityVerified": True,
        "replacementActivities": ["Art Museum"],
        "replacementDetails": [
            {
                "activity": "Art Museum",
                "recovery_evidence": {
                    "places_tool": "places.searchAttractions",
                    "route_tool": "route.estimateTravel",
                    "budget_feasibility_verified": True,
                    "remaining_budget": 5000.0,
                }
            }
        ]
    }

    res = reflector.reflect_and_explain(val_res, recovery_info, obs, "Goa", 10000.0, ["Historical Places"])
    assert res["audit_checks"]["recovery_budget_verified"] is True
    assert res["audit_checks"]["recovery_verified"] is True
    assert "Recovery recorded replacement activities: Art Museum" in res["summary_explanation"]
    assert "budget feasibility was not established" not in res["summary_explanation"]


def test_simulated_availability_never_described_as_real_world_booking_confirmation():
    """Verify simulated availability is never described as real-world booking or ticketing confirmation."""
    from backend.agent.reflection import AgentReflection

    reflector = AgentReflection()
    val_res = {"valid": True, "budgetValid": True, "weatherValid": True, "availabilityValid": True}
    obs = [
        {
            "tool": "availability.checkStatus",
            "status": "success",
            "evidence": "Simulated check passed",
            "data": {
                "attraction_name": "Beach Fort",
                "is_open": True,
                "is_simulated": True,
                "confirmed": False,
                "source": "Demo Availability Service"
            }
        }
    ]

    res = reflector.reflect_and_explain(val_res, {}, obs, "Goa", 10000.0, ["Historical Places"])
    summary = res["summary_explanation"]

    assert res["audit_checks"]["availability_is_simulated"] is True
    assert res["audit_checks"]["availability_confirmed"] is False
    assert "independently confirmed by real-world" not in summary.lower()
    assert "booking or ticketing has not been independently confirmed" in summary.lower()


def test_travel_agent_recovery_aggregation_one_unverified_budget_remains_unverified():
    """Verify that aggregating multiple recovery attempts where one has unverified budget keeps aggregated verified=False."""
    from backend.agent.travel_agent import ResilientTravelAgent

    initial_info = {
        "occurred": False,
        "status": "not_needed",
        "verified": False,
        "budgetFeasibilityVerified": False,
        "affectedSlots": [],
        "failedSlots": [],
        "originalActivities": [],
        "replacementActivities": [],
        "replacementDetails": [],
    }

    # Attempt 1: Day 1 weather recovery with verified budget
    attempt_1 = {
        "occurred": True,
        "status": "completed",
        "verified": True,
        "budgetFeasibilityVerified": True,
        "affectedSlots": ["Day 1 Morning"],
        "failedSlots": [],
        "originalActivities": ["Beach 1"],
        "replacementActivities": ["Indoor Museum 1"],
        "replacementDetails": [
            {
                "activity": "Indoor Museum 1",
                "recovery_evidence": {
                    "budget_feasibility_verified": True,
                    "remaining_budget": 5000.0,
                }
            }
        ],
        "impact": "Day 1 recovered.",
    }

    step1 = ResilientTravelAgent._aggregate_recovery_info(initial_info, attempt_1)
    assert step1["status"] == "completed"
    assert step1["budgetFeasibilityVerified"] is True
    assert step1["verified"] is True
    assert len(step1["replacementDetails"]) == 1

    # Attempt 2: Day 2 weather recovery with UNVERIFIED budget
    attempt_2 = {
        "occurred": True,
        "status": "completed",
        "verified": False,
        "budgetFeasibilityVerified": False,
        "affectedSlots": ["Day 2 Morning"],
        "failedSlots": [],
        "originalActivities": ["Beach 2"],
        "replacementActivities": ["Indoor Museum 2"],
        "replacementDetails": [
            {
                "activity": "Indoor Museum 2",
                "recovery_evidence": {
                    "budget_feasibility_verified": False,
                    "remaining_budget": None,
                }
            }
        ],
        "impact": "Day 2 recovered with unverified budget.",
    }

    step2 = ResilientTravelAgent._aggregate_recovery_info(step1, attempt_2)

    # Execution completed for both attempts, 2 replacements present
    assert step2["status"] == "completed"
    assert len(step2["replacementActivities"]) == 2
    assert len(step2["replacementDetails"]) == 2

    # But overall budget feasibility is NOT verified, so overall verified MUST be False
    assert step2["budgetFeasibilityVerified"] is False
    assert step2["verified"] is False
    assert "Complete budget feasibility could not be verified" in step2["reason"]

    # Also test the reverse order: Attempt 1 unverified, Attempt 2 verified
    step1_rev = ResilientTravelAgent._aggregate_recovery_info(initial_info, attempt_2)
    assert step1_rev["budgetFeasibilityVerified"] is False
    assert step1_rev["verified"] is False

    step2_rev = ResilientTravelAgent._aggregate_recovery_info(step1_rev, attempt_1)
    assert step2_rev["budgetFeasibilityVerified"] is False
    assert step2_rev["verified"] is False


def test_travel_agent_recovery_aggregation_fully_verified_remains_verified():
    """Verify that multiple fully verified recovery attempts remain verified after aggregation."""
    from backend.agent.travel_agent import ResilientTravelAgent

    initial_info = {
        "occurred": False,
        "status": "not_needed",
        "verified": False,
        "budgetFeasibilityVerified": False,
        "affectedSlots": [],
        "failedSlots": [],
        "originalActivities": [],
        "replacementActivities": [],
        "replacementDetails": [],
    }

    attempt_1 = {
        "occurred": True,
        "status": "completed",
        "verified": True,
        "budgetFeasibilityVerified": True,
        "affectedSlots": ["Day 1 Morning"],
        "failedSlots": [],
        "originalActivities": ["Beach 1"],
        "replacementActivities": ["Indoor Museum 1"],
        "replacementDetails": [
            {
                "activity": "Indoor Museum 1",
                "recovery_evidence": {
                    "budget_feasibility_verified": True,
                    "remaining_budget": 5000.0,
                }
            }
        ],
    }

    attempt_2 = {
        "occurred": True,
        "status": "completed",
        "verified": True,
        "budgetFeasibilityVerified": True,
        "affectedSlots": ["Day 2 Morning"],
        "failedSlots": [],
        "originalActivities": ["Beach 2"],
        "replacementActivities": ["Indoor Museum 2"],
        "replacementDetails": [
            {
                "activity": "Indoor Museum 2",
                "recovery_evidence": {
                    "budget_feasibility_verified": True,
                    "remaining_budget": 4000.0,
                }
            }
        ],
    }

    step1 = ResilientTravelAgent._aggregate_recovery_info(initial_info, attempt_1)
    assert step1["status"] == "completed"
    assert step1["budgetFeasibilityVerified"] is True
    assert step1["verified"] is True

    step2 = ResilientTravelAgent._aggregate_recovery_info(step1, attempt_2)
    assert step2["status"] == "completed"
    assert step2["budgetFeasibilityVerified"] is True
    assert step2["verified"] is True
    assert len(step2["replacementActivities"]) == 2
    assert len(step2["replacementDetails"]) == 2
    assert "could not be verified" not in step2["reason"]


# ---------------------------------------------------------------------------
# Issue 5 Regression Tests: LLM-Driven Decisions & Auditable Execution Traces
# ---------------------------------------------------------------------------

from backend.agent.llm_policy import LLMPolicyEngine

def test_policy_provenance_records_ollama_for_valid_action():
    policy = LLMPolicyEngine()
    valid_action_dict = {
        "action": "tool",
        "tool_name": "places.searchAttractions",
        "arguments": {"destination": "Goa", "interests": ["Beaches"]},
        "reasoning": "Searching for attractions in Goa"
    }
    policy._call_ollama_detailed = lambda *a, **k: {
        "succeeded": True,
        "http_status": 200,
        "valid_json": True,
        "parsed_dict": valid_action_dict,
        "error": None,
        "is_timeout": False,
    }
    mcp = MCPToolBoundary()
    mcp_tools = mcp.list_mcp_tools()
    val_action = policy.decide_next_action(
        request={"destination": "Goa", "days": 4, "budget": 15000.0, "interests": ["Beaches"], "demo_mode": False},
        iteration=1,
        max_iterations=8,
        current_itinerary=[],
        observations=[],
        mcp_tools=mcp_tools,
        validation_res={},
    )
    assert val_action.is_valid is True
    assert val_action.provenance is not None
    assert val_action.provenance.policy_provider == "ollama"
    assert val_action.provenance.configured_model == policy.model_name
    assert val_action.provenance.ollama_request_succeeded is True
    assert val_action.provenance.model_response_valid_json is True
    assert val_action.provenance.action_schema_valid is True
    assert val_action.provenance.fallback_used is False
    assert val_action.provenance.fallback_reason is None
    assert val_action.provenance.original_action == valid_action_dict
    assert val_action.provenance.final_action == valid_action_dict

def test_policy_provenance_records_fallback_on_timeout():
    policy = LLMPolicyEngine()
    policy._call_ollama_detailed = lambda *a, **k: {
        "succeeded": False,
        "http_status": None,
        "valid_json": False,
        "parsed_dict": None,
        "error": "TimeoutError: timed out",
        "is_timeout": True,
    }
    mcp = MCPToolBoundary()
    mcp_tools = mcp.list_mcp_tools()
    val_action = policy.decide_next_action(
        request={"destination": "Goa", "days": 4, "budget": 15000.0, "interests": ["Beaches"], "demo_mode": False},
        iteration=1,
        max_iterations=8,
        current_itinerary=[],
        observations=[],
        mcp_tools=mcp_tools,
        validation_res={},
    )
    assert val_action.is_valid is True
    assert val_action.provenance is not None
    assert val_action.provenance.policy_provider == "deterministic_fallback"
    assert val_action.provenance.fallback_used is True
    assert "timed out" in (val_action.provenance.fallback_reason or "").lower()

def test_policy_provenance_records_fallback_on_malformed_json():
    policy = LLMPolicyEngine()
    policy._call_ollama_detailed = lambda *a, **k: {
        "succeeded": True,
        "http_status": 200,
        "valid_json": False,
        "parsed_dict": None,
        "error": "Ollama content was not valid JSON: Expecting value",
        "is_timeout": False,
    }
    mcp = MCPToolBoundary()
    mcp_tools = mcp.list_mcp_tools()
    val_action = policy.decide_next_action(
        request={"destination": "Goa", "days": 4, "budget": 15000.0, "interests": ["Beaches"], "demo_mode": False},
        iteration=1,
        max_iterations=8,
        current_itinerary=[],
        observations=[],
        mcp_tools=mcp_tools,
        validation_res={},
    )
    assert val_action.is_valid is True
    assert val_action.provenance.fallback_used is True
    assert val_action.provenance.policy_provider == "deterministic_fallback"
    assert "not valid json" in (val_action.provenance.fallback_reason or "").lower()

def test_policy_provenance_records_fallback_on_invalid_schema():
    policy = LLMPolicyEngine()
    invalid_dict = {
        "action": "nonexistent_action_type",
        "reasoning": "testing invalid schema"
    }
    policy._call_ollama_detailed = lambda *a, **k: {
        "succeeded": True,
        "http_status": 200,
        "valid_json": True,
        "parsed_dict": invalid_dict,
        "error": None,
        "is_timeout": False,
    }
    mcp = MCPToolBoundary()
    mcp_tools = mcp.list_mcp_tools()
    val_action = policy.decide_next_action(
        request={"destination": "Goa", "days": 4, "budget": 15000.0, "interests": ["Beaches"], "demo_mode": False},
        iteration=1,
        max_iterations=8,
        current_itinerary=[],
        observations=[],
        mcp_tools=mcp_tools,
        validation_res={},
    )
    assert val_action.is_valid is True
    assert val_action.provenance.action_schema_valid is False
    assert val_action.provenance.fallback_used is True
    assert val_action.provenance.policy_provider == "deterministic_fallback"
    assert "validation" in (val_action.provenance.fallback_reason or "").lower()

def test_policy_strict_ollama_rejects_unavailable_without_fallback():
    policy = LLMPolicyEngine()
    policy._call_ollama_detailed = lambda *a, **k: {
        "succeeded": False,
        "http_status": None,
        "valid_json": False,
        "parsed_dict": None,
        "error": "ConnectionRefusedError: Connection refused",
        "is_timeout": False,
    }
    mcp = MCPToolBoundary()
    mcp_tools = mcp.list_mcp_tools()
    val_action = policy.decide_next_action(
        request={"destination": "Goa", "days": 4, "budget": 15000.0, "interests": ["Beaches"], "demo_mode": True},
        iteration=1,
        max_iterations=8,
        current_itinerary=[],
        observations=[],
        mcp_tools=mcp_tools,
        validation_res={},
        require_ollama=True,
    )
    assert val_action.is_valid is False
    assert val_action.provenance.fallback_used is False
    assert any("Strict Ollama requirement failed" in err for err in val_action.errors)

def test_policy_strict_ollama_rejects_malformed_decisions():
    policy = LLMPolicyEngine()
    bad_action_dict = {
        "action": "tool",
        "tool_name": "unknown.toolName",
        "arguments": {},
        "reasoning": "malformed test action"
    }
    policy._call_ollama_detailed = lambda *a, **k: {
        "succeeded": True,
        "http_status": 200,
        "valid_json": True,
        "parsed_dict": bad_action_dict,
        "error": None,
        "is_timeout": False,
    }
    mcp = MCPToolBoundary()
    mcp_tools = mcp.list_mcp_tools()
    val_action = policy.decide_next_action(
        request={"destination": "Goa", "days": 4, "budget": 15000.0, "interests": ["Beaches"], "demo_mode": True},
        iteration=1,
        max_iterations=8,
        current_itinerary=[],
        observations=[],
        mcp_tools=mcp_tools,
        validation_res={},
        require_ollama=True,
    )
    assert val_action.is_valid is False
    assert val_action.provenance.fallback_used is False
    assert val_action.provenance.action_schema_valid is False

def test_llm_tool_mcp_failure_not_executed(agent):
    agent.policy._call_ollama_detailed = lambda *a, **k: {
        "succeeded": True,
        "http_status": 200,
        "valid_json": True,
        "parsed_dict": {
            "action": "tool",
            "tool_name": "places.searchAttractions",
            "arguments": {"destination": "Goa", "interests": ["Beaches"]},
            "reasoning": "Searching attractions",
        },
        "error": None,
        "is_timeout": False,
    }
    from backend.tools.base import ToolObservation
    agent.mcp.invoke_tool = lambda *a, **k: ToolObservation(
        tool="places.searchAttractions",
        status="error",
        evidence="Simulated MCP service failure",
        data={},
    )
    res = agent.run("Goa", 4, 15000.0, ["Beaches"], demo_mode=True, max_iterations=1)
    trace_path = res["trace_file"]
    with open(trace_path, "r", encoding="utf-8") as tf:
        trace = json.load(tf)
    step = trace["iteration_steps"][0]
    assert step["llm_decision_selected_for_execution"] is True
    assert step["is_llm_decision_executed"] is False
    assert step["tool_execution_status"] == "error"

def test_llm_tool_success_provenance_executed(agent):
    agent.policy._call_ollama_detailed = lambda *a, **k: {
        "succeeded": True,
        "http_status": 200,
        "valid_json": True,
        "parsed_dict": {
            "action": "tool",
            "tool_name": "places.searchAttractions",
            "arguments": {"destination": "Goa", "interests": ["Beaches"]},
            "reasoning": "Searching attractions",
        },
        "error": None,
        "is_timeout": False,
    }
    res = agent.run("Goa", 4, 15000.0, ["Beaches"], demo_mode=True, max_iterations=1)
    trace_path = res["trace_file"]
    with open(trace_path, "r", encoding="utf-8") as tf:
        trace = json.load(tf)
    step = trace["iteration_steps"][0]
    assert step["llm_decision_selected_for_execution"] is True
    assert step["is_llm_decision_executed"] is True
    assert step["tool_execution_status"] in ("success", "warning")

def test_agent_step_records_distinguish_safety_override(agent):
    agent.policy._call_ollama_detailed = lambda *a, **k: {
        "succeeded": True,
        "http_status": 200,
        "valid_json": True,
        "parsed_dict": {
            "action": "finish",
            "tool_name": None,
            "arguments": {},
            "reasoning": "Attempting early finish",
        },
        "error": None,
        "is_timeout": False,
    }
    res = agent.run(
        destination="Goa",
        days=4,
        budget=15000.0,
        interests=["Beaches"],
        demo_mode=True,
        max_iterations=1,
    )
    trace_path = res["trace_file"]
    with open(trace_path, "r", encoding="utf-8") as tf:
        trace = json.load(tf)

    assert len(trace["iteration_steps"]) >= 1
    step1 = trace["iteration_steps"][0]
    assert step1["safety_override_applied"] is True
    assert step1["llm_decision_selected_for_execution"] is False
    assert step1["is_llm_decision_executed"] is False
    assert step1["original_decision"]["action"] == "finish"
    assert step1["executed_action"] == "tool"
    assert step1["executed_tool"] == "places.searchAttractions"
    assert "Completion blocked" in (step1["safety_override_reason"] or "")
    assert res["termination_reason"] != "policy_finish"
    assert trace["termination_reason"] != "policy_finish"

def test_safety_generated_finish_after_weather_coverage_provenance(agent):
    def mock_decide(request, iteration, max_iterations, current_itinerary, observations, mcp_tools, validation_res, require_ollama=None):
        prov = agent.policy._build_mock_prov() if hasattr(agent.policy, "_build_mock_prov") else None
        if not current_itinerary:
            return ValidatedAction(
                is_valid=True,
                action=AgentAction(action="tool", tool_name="places.searchAttractions", arguments={"destination": "Goa", "interests": ["Beaches"]}, reasoning="places"),
                errors=[],
                provenance=prov,
            )
        checked = agent._get_checked_weather_days(observations)
        if len(checked) < 4:
            next_day = len(checked) + 1
            return ValidatedAction(
                is_valid=True,
                action=AgentAction(action="tool", tool_name="weather.getForecast", arguments={"destination": "Goa", "day": next_day}, reasoning=f"day {next_day}"),
                errors=[],
                provenance=prov,
            )
        return ValidatedAction(
            is_valid=True,
            action=AgentAction(action="tool", tool_name="weather.getForecast", arguments={"destination": "Goa", "day": 1}, reasoning="repeated weather"),
            errors=[],
            provenance=prov,
        )

    agent.policy.decide_next_action = mock_decide
    res = agent.run("Goa", 4, 15000.0, ["Beaches", "Historical Places"], demo_mode=True)
    trace_path = res["trace_file"]
    with open(trace_path, "r", encoding="utf-8") as tf:
        trace = json.load(tf)

    assert res["status"] == "verified"
    assert res["termination_reason"] == "safety_termination"
    assert trace["termination_reason"] == "safety_termination"
    assert res["technicalDetails"]["terminationReason"] == "safety_termination"

def test_strict_ollama_counters_on_failure(agent):
    agent.policy._call_ollama_detailed = lambda *a, **k: {
        "succeeded": False,
        "http_status": None,
        "valid_json": False,
        "parsed_dict": None,
        "error": "TimeoutError: timed out",
        "is_timeout": True,
    }
    res = agent.run("Goa", 4, 15000.0, ["Beaches"], demo_mode=True, require_ollama=True)
    ds = res["decision_summary"]
    assert ds["ollamaCalled"] is True
    assert ds["ollamaAttemptCount"] >= 1
    assert ds["ollamaSuccessfulRequestsCount"] == 0
    assert ds["ollamaAcceptedDecisionsCount"] == 0
    assert ds["fallbackDecisionsCount"] == 0
    assert res["termination_reason"] == "invalid_action"
    assert res["technicalDetails"]["terminationReason"] == "invalid_action"

def test_malformed_json_and_invalid_schema_counters(agent):
    # 6a. Malformed JSON
    agent.policy._call_ollama_detailed = lambda *a, **k: {
        "succeeded": True,
        "http_status": 200,
        "valid_json": False,
        "parsed_dict": None,
        "error": "JSONDecodeError",
        "is_timeout": False,
    }
    res_malformed = agent.run("Goa", 4, 15000.0, ["Beaches"], demo_mode=True, max_iterations=1)
    ds1 = res_malformed["decision_summary"]
    assert ds1["ollamaAttemptCount"] == 1
    assert ds1["ollamaSuccessfulRequestsCount"] == 1
    assert ds1["ollamaAcceptedDecisionsCount"] == 0
    assert ds1["fallbackDecisionsCount"] == 1

    # 6b. Invalid schema
    agent.policy._call_ollama_detailed = lambda *a, **k: {
        "succeeded": True,
        "http_status": 200,
        "valid_json": True,
        "parsed_dict": {"action": "invalid_type", "reasoning": "bad"},
        "error": None,
        "is_timeout": False,
    }
    res_schema = agent.run("Goa", 4, 15000.0, ["Beaches"], demo_mode=True, max_iterations=1)
    ds2 = res_schema["decision_summary"]
    assert ds2["ollamaAttemptCount"] == 1
    assert ds2["ollamaSuccessfulRequestsCount"] == 1
    assert ds2["ollamaAcceptedDecisionsCount"] == 0
    assert ds2["fallbackDecisionsCount"] == 1

def test_normal_accepted_ollama_decision_counters(agent):
    agent.policy._call_ollama_detailed = lambda *a, **k: {
        "succeeded": True,
        "http_status": 200,
        "valid_json": True,
        "parsed_dict": {
            "action": "tool",
            "tool_name": "places.searchAttractions",
            "arguments": {"destination": "Goa", "interests": ["Beaches"]},
            "reasoning": "Searching attractions",
        },
        "error": None,
        "is_timeout": False,
    }
    res = agent.run("Goa", 4, 15000.0, ["Beaches"], demo_mode=True, max_iterations=1)
    ds = res["decision_summary"]
    assert ds["ollamaCalled"] is True
    assert ds["ollamaAttemptCount"] == 1
    assert ds["ollamaSuccessfulRequestsCount"] == 1
    assert ds["ollamaAcceptedDecisionsCount"] == 1
    assert ds["fallbackDecisionsCount"] == 0

def test_deterministic_fallback_counters(agent):
    agent.policy._call_ollama_detailed = lambda *a, **k: {
        "succeeded": False,
        "http_status": None,
        "valid_json": False,
        "parsed_dict": None,
        "error": "ConnectionRefusedError",
        "is_timeout": False,
    }
    res = agent.run("Goa", 4, 15000.0, ["Beaches"], demo_mode=True, max_iterations=1)
    ds = res["decision_summary"]
    assert ds["ollamaAttemptCount"] == 1
    assert ds["ollamaSuccessfulRequestsCount"] == 0
    assert ds["ollamaAcceptedDecisionsCount"] == 0
    assert ds["fallbackDecisionsCount"] == 1

def test_agent_termination_records_iteration_limit(agent):
    agent.policy._call_ollama_detailed = lambda *a, **k: {
        "succeeded": False,
        "http_status": None,
        "valid_json": False,
        "parsed_dict": None,
        "error": "fallback",
        "is_timeout": False,
    }
    res = agent.run(
        destination="Goa",
        days=4,
        budget=15000.0,
        interests=["Beaches"],
        demo_mode=True,
        max_iterations=1,
    )
    assert res["status"] == "unverified"
    assert res["termination_reason"] == "iteration_limit"
    assert res["technicalDetails"]["terminationReason"] == "iteration_limit"
    assert res["decision_summary"]["terminationReason"] == "iteration_limit"
    assert "iteration limit" in res["final_status_reason"].lower()

def test_agent_distinguishes_policy_finish_from_validation_failure(agent):
    agent.policy._call_ollama_detailed = lambda *a, **k: {
        "succeeded": False,
        "http_status": None,
        "valid_json": False,
        "parsed_dict": None,
        "error": "fallback",
        "is_timeout": False,
    }
    res_ok = agent.run(
        destination="Goa",
        days=4,
        budget=15000.0,
        interests=["Beaches", "Historical Places"],
        demo_mode=True,
    )
    assert res_ok["status"] == "verified"
    assert res_ok["termination_reason"] == "policy_finish"

    res_fail = agent.run(
        destination="Goa",
        days=4,
        budget=1000.0,
        interests=["Beaches", "Historical Places"],
        demo_mode=True,
    )
    assert res_fail["status"] == "unverified"
    assert res_fail["termination_reason"] == "final_validation_failure"
    assert res_fail["technicalDetails"]["terminationReason"] == "final_validation_failure"

def test_durable_trace_contains_decision_summary_and_provenance(agent):
    agent.policy._call_ollama_detailed = lambda *a, **k: {
        "succeeded": False,
        "http_status": None,
        "valid_json": False,
        "parsed_dict": None,
        "error": "fallback",
        "is_timeout": False,
    }
    res = agent.run(
        destination="Goa",
        days=4,
        budget=15000.0,
        interests=["Beaches", "Historical Places"],
        demo_mode=True,
    )
    trace_path = res["trace_file"]
    assert os.path.exists(trace_path)
    with open(trace_path, "r", encoding="utf-8") as tf:
        trace = json.load(tf)

    assert "termination_reason" in trace
    assert trace["termination_reason"] == res["termination_reason"]
    assert "decision_summary" in trace
    ds = trace["decision_summary"]
    assert "ollamaCalled" in ds
    assert "configuredModel" in ds
    assert "effectiveTimeoutSeconds" in ds
    assert "requireOllamaForDemo" in ds
    assert "totalIterations" in ds
    assert "ollamaDecisionsCount" in ds
    assert "fallbackDecisionsCount" in ds
    assert "safetyOverridesCount" in ds
    assert "terminationReason" in ds

    for step in trace["iteration_steps"]:
        assert "decision_provider" in step
        assert "model" in step
        assert "ollama_request_attempted" in step
        assert "ollama_request_succeeded" in step
        assert "fallback_used" in step
        assert "original_decision" in step
        assert "policy_decision" in step
        assert "safety_override_applied" in step
        assert "llm_decision_selected_for_execution" in step
        assert "is_llm_decision_executed" in step
        assert "executed_action" in step

def test_demo_mode_strict_ollama_enforced(agent):
    agent.policy._call_ollama_detailed = lambda *a, **k: {
        "succeeded": False,
        "http_status": None,
        "valid_json": False,
        "parsed_dict": None,
        "error": "Ollama service unavailable on port 11434",
        "is_timeout": False,
    }
    res = agent.run(
        destination="Goa",
        days=4,
        budget=15000.0,
        interests=["Beaches"],
        demo_mode=True,
        require_ollama=True,
    )
    assert res["status"] == "unverified"
    assert res["termination_reason"] == "invalid_action"
    assert res["technicalDetails"]["terminationReason"] == "invalid_action"
    assert "strict ollama" in res["final_status_reason"].lower()

def test_all_termination_paths_accurate_in_api_and_trace(agent):
    # Path 1: iteration_limit
    agent.policy._call_ollama_detailed = lambda *a, **k: {
        "succeeded": False, "http_status": None, "valid_json": False, "parsed_dict": None, "error": "fallback", "is_timeout": False,
    }
    res1 = agent.run("Goa", 4, 15000.0, ["Beaches"], demo_mode=True, max_iterations=1)
    assert res1["termination_reason"] == "iteration_limit"
    with open(res1["trace_file"], "r", encoding="utf-8") as f:
        assert json.load(f)["termination_reason"] == "iteration_limit"

    # Path 2: invalid_action
    res2 = agent.run("Goa", 4, 15000.0, ["Beaches"], demo_mode=True, require_ollama=True)
    assert res2["termination_reason"] == "invalid_action"
    with open(res2["trace_file"], "r", encoding="utf-8") as f:
        assert json.load(f)["termination_reason"] == "invalid_action"

    # Path 3: policy_finish
    res3 = agent.run("Goa", 4, 15000.0, ["Beaches", "Historical Places"], demo_mode=True)
    assert res3["termination_reason"] == "policy_finish"
    with open(res3["trace_file"], "r", encoding="utf-8") as f:
        assert json.load(f)["termination_reason"] == "policy_finish"

    # Path 4: final_validation_failure
    res4 = agent.run("Goa", 4, 1000.0, ["Beaches"], demo_mode=True)
    assert res4["termination_reason"] == "final_validation_failure"
    with open(res4["trace_file"], "r", encoding="utf-8") as f:
        assert json.load(f)["termination_reason"] == "final_validation_failure"

    # Path 5: tool_execution_failure
    agent.policy._call_ollama_detailed = lambda *a, **k: {
        "succeeded": True, "http_status": 200, "valid_json": True,
        "parsed_dict": {"action": "tool", "tool_name": "places.searchAttractions", "arguments": {"destination": "Goa", "interests": ["Beaches"]}, "reasoning": "places"},
        "error": None, "is_timeout": False,
    }
    from backend.tools.base import ToolObservation
    agent.mcp.invoke_tool = lambda *a, **k: ToolObservation(tool="places.searchAttractions", status="error", evidence="Fatal tool memory corruption", data={})
    res5 = agent.run("Goa", 4, 15000.0, ["Beaches"], demo_mode=True, max_iterations=2)
    assert res5["termination_reason"] == "tool_execution_failure"
    with open(res5["trace_file"], "r", encoding="utf-8") as f:
        assert json.load(f)["termination_reason"] == "tool_execution_failure"

    # Path 6: exception
    def crashing_decide(*a, **k):
        raise RuntimeError("Synthetic internal failure")
    agent.policy.decide_next_action = crashing_decide
    res6 = agent.run("Goa", 4, 15000.0, ["Beaches"], demo_mode=True)
    assert res6["termination_reason"] == "exception"
    with open(res6["trace_file"], "r", encoding="utf-8") as f:
        assert json.load(f)["termination_reason"] == "exception"


# ============================================================================
# Task 2 Regression Tests: Progress Summary & Dynamic Tool Selection Integrity
# ============================================================================

def test_progress_summary_sections_completed_and_outstanding():
    from backend.agent.prompts import build_planning_progress
    summary = build_planning_progress(
        request={"destination": "Goa", "days": 2, "interests": ["Beaches"]},
        current_itinerary=[],
        observations=[],
        validation_res={},
    )
    assert "### COMPLETED REQUIREMENTS" in summary
    assert "### OUTSTANDING REQUIREMENTS" in summary
    assert "- None yet. Planning is in initial stage." in summary
    assert "'places.searchAttractions'" in summary
    assert "'weather.getForecast'" in summary

def test_completed_attractions_not_recommended_again():
    from backend.agent.prompts import build_planning_progress
    from backend.agent.llm_policy import LLMPolicyEngine
    from backend.tools.mcp_boundary import MCPToolBoundary

    obs = [{
        "tool": "places.searchAttractions",
        "status": "success",
        "destination": "Goa",
        "data": {
            "count": 2,
            "attractions": [
                {"name": "Calangute Beach", "category": "Beaches"},
                {"name": "Baga Beach", "category": "Beaches"}
            ]
        },
        "evidence": "Found 2 attractions."
    }]

    summary = build_planning_progress(
        request={"destination": "Goa", "days": 1, "interests": ["Beaches"]},
        current_itinerary=[{"day": 1, "morning": {"activity": "Calangute Beach", "location": "North Goa"}}],
        observations=obs,
        validation_res={},
    )
    assert "- Attraction discovery:" in summary
    assert "* MCP Tool: 'places.searchAttractions'" in summary
    assert "* Execution status: Successfully executed" in summary
    assert "DO NOT call places.searchAttractions again" in summary

    # In strict Ollama mode, a repeated general search is rejected
    policy = LLMPolicyEngine()
    policy._call_ollama_detailed = lambda *a, **k: {
        "succeeded": True, "http_status": 200, "valid_json": True,
        "parsed_dict": {
            "action": "tool",
            "tool_name": "places.searchAttractions",
            "arguments": {"destination": "Goa", "interests": ["Beaches"], "indoor_only": False},
            "reasoning": "Searching again",
        },
        "error": None, "is_timeout": False,
    }
    mcp = MCPToolBoundary()
    val_action = policy.decide_next_action(
        request={"destination": "Goa", "days": 1, "interests": ["Beaches"], "demo_mode": True},
        iteration=2,
        max_iterations=5,
        current_itinerary=[],
        observations=obs,
        mcp_tools=mcp.list_mcp_tools(),
        validation_res={},
        require_ollama=True,
    )
    assert val_action.is_valid is False
    assert any("Rejected repeated places.searchAttractions" in err for err in val_action.errors)

def test_completed_weather_not_unnecessarily_repeated():
    from backend.agent.prompts import build_planning_progress
    from backend.agent.llm_policy import LLMPolicyEngine
    from backend.tools.mcp_boundary import MCPToolBoundary

    obs = [{
        "tool": "weather.getForecast",
        "status": "success",
        "destination": "Goa",
        "data": {
            "day": 1,
            "condition": "sunny",
            "temperature_c": 30.0,
            "suitableForOutdoor": True,
        },
        "evidence": "Weather forecast for Goa (Day 1) is sunny."
    }]

    summary = build_planning_progress(
        request={"destination": "Goa", "days": 1, "interests": ["Beaches"]},
        current_itinerary=[{"day": 1}],
        observations=obs,
        validation_res={},
    )
    assert "- Weather coverage:" in summary
    assert "* MCP Tool: 'weather.getForecast'" in summary
    assert "* Execution status: Successfully executed" in summary
    assert "DO NOT call weather.getForecast again" in summary

    # In strict mode, repeating Day 1 is rejected
    policy = LLMPolicyEngine()
    policy._call_ollama_detailed = lambda *a, **k: {
        "succeeded": True, "http_status": 200, "valid_json": True,
        "parsed_dict": {
            "action": "tool",
            "tool_name": "weather.getForecast",
            "arguments": {"destination": "Goa", "day": 1},
            "reasoning": "Repeating day 1",
        },
        "error": None, "is_timeout": False,
    }
    mcp = MCPToolBoundary()
    val_action = policy.decide_next_action(
        request={"destination": "Goa", "days": 1, "interests": ["Beaches"], "demo_mode": True},
        iteration=2,
        max_iterations=5,
        current_itinerary=[],
        observations=obs,
        mcp_tools=mcp.list_mcp_tools(),
        validation_res={},
        require_ollama=True,
    )
    assert val_action.is_valid is False
    assert any("Rejected repeated weather.getForecast" in err for err in val_action.errors)

def test_outstanding_requirements_available_for_dynamic_selection():
    from backend.agent.prompts import build_planning_progress
    obs = [
        {"tool": "weather.getForecast", "status": "success", "data": {"day": 1, "condition": "sunny"}},
        {"tool": "places.searchAttractions", "status": "success", "data": {"count": 1, "attractions": [{"name": "Beach"}]}}
    ]
    summary = build_planning_progress(
        request={"destination": "Goa", "days": 1, "interests": ["Beaches"]},
        current_itinerary=[{"day": 1, "morning": {"activity": "Beach", "location": "North Goa"}}],
        observations=obs,
        validation_res={},
    )
    out_idx = summary.find("### OUTSTANDING REQUIREMENTS")
    assert out_idx != -1
    outstanding_part = summary[out_idx:]
    assert "'availability.checkStatus'" in outstanding_part
    assert "'route.estimateTravel'" in outstanding_part
    assert "'cost.calculateEstimate'" in outstanding_part
    assert "'validation.validateItinerary'" in outstanding_part

def test_failed_or_warning_observations_not_treated_as_successful_completion():
    from backend.agent.prompts import build_planning_progress
    from backend.agent.llm_policy import LLMPolicyEngine

    # Availability with status="warning"
    obs_warning = [{
        "tool": "availability.checkStatus",
        "status": "warning",
        "destination": "Goa",
        "data": {"attraction": "Fort", "is_open": True},
        "evidence": "Simulated availability; not verified"
    }]
    # LLMPolicyEngine should not consider warning as succeeded
    assert LLMPolicyEngine._tool_observation_succeeded(obs_warning, "availability.checkStatus") is False

    summary = build_planning_progress(
        request={"destination": "Goa", "days": 1, "interests": ["Beaches"]},
        current_itinerary=[],
        observations=obs_warning,
        validation_res={},
    )
    comp_idx = summary.find("### COMPLETED REQUIREMENTS")
    out_idx = summary.find("### OUTSTANDING REQUIREMENTS")
    comp_part = summary[comp_idx:out_idx]
    out_part = summary[out_idx:]
    assert "'availability.checkStatus'" not in comp_part
    assert "'availability.checkStatus'" in out_part
    assert "WARNING / UNCONFIRMED" in out_part

    # Places with status="error"
    obs_error = [{
        "tool": "places.searchAttractions",
        "status": "error",
        "destination": "Goa",
        "data": {},
        "evidence": "Network timeout"
    }]
    assert LLMPolicyEngine._tool_observation_succeeded(obs_error, "places.searchAttractions") is False
    summary_err = build_planning_progress(
        request={"destination": "Goa", "days": 1, "interests": ["Beaches"]},
        current_itinerary=[],
        observations=obs_error,
        validation_res={},
    )
    out_part_err = summary_err[summary_err.find("### OUTSTANDING REQUIREMENTS"):]
    assert "'places.searchAttractions'" in out_part_err
    assert "INCOMPLETE" in out_part_err

def test_invalid_tool_arguments_rejected():
    from backend.agent.llm_policy import LLMPolicyEngine
    from backend.tools.mcp_boundary import MCPToolBoundary

    mcp = MCPToolBoundary()
    mcp_tools = mcp.list_mcp_tools()

    # 1. route.estimateTravel with identical origin and destination
    errs_same = LLMPolicyEngine._validate_tool_arguments(
        "route.estimateTravel",
        {"origin": "Goa", "destination": "Goa"},
        mcp_tools,
    )
    assert any("must be distinct locations" in err for err in errs_same)

    # 2. route.estimateTravel with empty origin
    errs_empty = LLMPolicyEngine._validate_tool_arguments(
        "route.estimateTravel",
        {"origin": "", "destination": "Baga Beach"},
        mcp_tools,
    )
    assert any("cannot be empty" in err for err in errs_empty)

    # 3. availability.checkStatus with empty attraction_name
    errs_attr = LLMPolicyEngine._validate_tool_arguments(
        "availability.checkStatus",
        {"attraction_name": "  "},
        mcp_tools,
    )
    assert any("attraction_name cannot be empty" in err for err in errs_attr)

    # 4. weather.getForecast with invalid day
    errs_day = LLMPolicyEngine._validate_tool_arguments(
        "weather.getForecast",
        {"destination": "Goa", "day": -1},
        mcp_tools,
    )
    assert any("day must be a positive integer" in err for err in errs_day)

    # 5. route.estimateTravel with distinct locations is valid
    errs_valid = LLMPolicyEngine._validate_tool_arguments(
        "route.estimateTravel",
        {"origin": "Hotel in Goa", "destination": "Calangute Beach"},
        mcp_tools,
    )
    assert errs_valid == []

def test_completed_tasks_do_not_prevent_necessary_recovery_on_weather_change():
    from backend.agent.prompts import build_planning_progress
    from backend.agent.llm_policy import LLMPolicyEngine
    from backend.tools.mcp_boundary import MCPToolBoundary

    # Day 1 weather is sunny, Day 2 weather is rainy (unsuitable for outdoor)
    obs = [
        {"tool": "weather.getForecast", "status": "success", "data": {"day": 1, "condition": "sunny", "suitableForOutdoor": True}},
        {"tool": "weather.getForecast", "status": "success", "data": {"day": 2, "condition": "heavy rain", "suitableForOutdoor": False}},
        {"tool": "places.searchAttractions", "status": "success", "data": {"count": 2, "attractions": [{"name": "Beach 1"}, {"name": "Beach 2"}]}}
    ]

    summary = build_planning_progress(
        request={"destination": "Goa", "days": 2, "interests": ["Beaches"]},
        current_itinerary=[{"day": 1}, {"day": 2}],
        observations=obs,
        validation_res={},
    )
    # Highlights recovery opportunity
    assert "Weather disruption recovery" in summary
    assert "indoor_only=true" in summary

    # Searching indoor attractions with indoor_only=True is NOT rejected as a duplicate
    policy = LLMPolicyEngine()
    policy._call_ollama_detailed = lambda *a, **k: {
        "succeeded": True, "http_status": 200, "valid_json": True,
        "parsed_dict": {
            "action": "tool",
            "tool_name": "places.searchAttractions",
            "arguments": {"destination": "Goa", "interests": ["Beaches"], "indoor_only": True},
            "reasoning": "Searching indoor attractions for rainy day recovery",
        },
        "error": None, "is_timeout": False,
    }
    mcp = MCPToolBoundary()
    val_action = policy.decide_next_action(
        request={"destination": "Goa", "days": 2, "interests": ["Beaches"], "demo_mode": True},
        iteration=3,
        max_iterations=8,
        current_itinerary=[],
        observations=obs,
        mcp_tools=mcp.list_mcp_tools(),
        validation_res={},
        require_ollama=True,
    )
    assert val_action.is_valid is True
    assert val_action.action.arguments.get("indoor_only") is True


# ============================================================================
# Phase 2 Focused Verification: Completion Detection & Reasoning Normalization
# ============================================================================

def test_missing_reasoning_normalized_to_safe_default():
    from backend.agent.action_models import validate_agent_action, AgentAction

    # 1. Missing reasoning key
    action1 = {"action": "tool", "tool_name": "places.searchAttractions", "arguments": {"destination": "Goa"}}
    val1 = validate_agent_action(action1, ["places.searchAttractions"])
    assert val1.is_valid is True
    assert val1.action.reasoning == "Action selected based on planning progress."

    # 2. None reasoning
    action2 = {"action": "tool", "tool_name": "places.searchAttractions", "arguments": {"destination": "Goa"}, "reasoning": None}
    val2 = validate_agent_action(action2, ["places.searchAttractions"])
    assert val2.is_valid is True
    assert val2.action.reasoning == "Action selected based on planning progress."

    # 3. Empty whitespace reasoning
    action3 = {"action": "finish", "arguments": {}, "reasoning": "   "}
    val3 = validate_agent_action(action3, ["places.searchAttractions"])
    assert val3.is_valid is True
    assert val3.action.reasoning == "Action selected based on planning progress."

    # 4. Explicit valid reasoning is preserved
    action4 = {"action": "finish", "arguments": {}, "reasoning": "Explicit valid reason."}
    val4 = validate_agent_action(action4, ["places.searchAttractions"])
    assert val4.is_valid is True
    assert val4.action.reasoning == "Explicit valid reason."


def test_invalid_actions_and_arguments_remain_rejected():
    from backend.agent.action_models import validate_agent_action
    from backend.agent.llm_policy import LLMPolicyEngine

    # 1. Invalid action string (e.g. 'validation')
    action_bad = {"action": "validation", "tool_name": "validation.validateItinerary", "arguments": {}}
    val_bad = validate_agent_action(action_bad, ["validation.validateItinerary"])
    assert val_bad.is_valid is False
    assert any("Input should be 'tool' or 'finish'" in err for err in val_bad.errors)

    # 2. Unknown tool name
    action_unknown = {"action": "tool", "tool_name": "unknown.tool", "arguments": {}}
    val_unknown = validate_agent_action(action_unknown, ["places.searchAttractions"])
    assert val_unknown.is_valid is False
    assert any("Unknown tool 'unknown.tool'" in err for err in val_unknown.errors)

    # 3. Invalid tool arguments (missing destination in weather.getForecast)
    policy = LLMPolicyEngine()
    schema_errs = policy._validate_tool_arguments(
        "weather.getForecast",
        {"day": 1},
        [{"name": "weather.getForecast", "input_schema": {"type": "object", "properties": {"destination": {"type": "string"}}, "required": ["destination"]}}]
    )
    assert len(schema_errs) > 0
    assert any("required field is missing" in err for err in schema_errs)


def test_orchestrator_completion_when_all_requirements_complete(agent):
    from backend.agent.action_models import TripRequest
    # Mock Ollama call counter
    ollama_call_count = 0
    def mock_ollama(*a, **k):
        nonlocal ollama_call_count
        ollama_call_count += 1
        return {"succeeded": True, "http_status": 200, "valid_json": True, "parsed_dict": {"action": "finish", "arguments": {}, "reasoning": "finished"}, "error": None, "is_timeout": False}

    agent.policy._call_ollama_detailed = mock_ollama

    # Prepare observations covering all 5 requirements
    obs = [
        {"tool": "places.searchAttractions", "status": "success", "data": {"attractions": [{"name": "Calangute Beach", "cost_inr": 1000.0}]}, "evidence": "Found 1 attraction"},
        {"tool": "weather.getForecast", "status": "success", "data": {"destination": "Goa", "day": 1, "condition": "sunny", "suitableForOutdoor": True, "temperature_c": 30.0, "evidence": "Sunny"}, "evidence": "Sunny"},
        {"tool": "availability.checkStatus", "status": "success", "data": {"attraction_name": "Calangute Beach", "is_open": True}, "evidence": "Calangute Beach is open"},
        {"tool": "route.estimateTravel", "status": "success", "data": {"distance_km": 10.0, "travel_time_mins": 20.0}, "evidence": "10km in 20min"},
        {"tool": "cost.calculateEstimate", "status": "success", "data": {"total_cost_inr": 2500.0}, "evidence": "Total cost 2500 INR"},
    ]
    itinerary = [{
        "day": 1,
        "morning": {"activity": "Calangute Beach", "location": "North Goa", "cost_inr": 1000.0, "is_outdoor": True},
        "afternoon": {"activity": "Fort Aguada", "location": "Candolim", "cost_inr": 500.0, "is_outdoor": False},
        "evening": {"activity": "Sunset Point", "location": "Baga", "cost_inr": 200.0, "is_outdoor": False},
    }]

    # Run check_planning_complete directly
    req = TripRequest(destination="Goa", days=1, budget=10000.0, interests=["Beaches"])
    is_comp, reason = agent._check_planning_complete(req, itinerary, obs, [{"day": 1, "condition": "sunny", "suitableForOutdoor": True}], set(), {"status": "not_needed"})
    assert is_comp is True

    # Now verify in agent.run with require_ollama=True
    # Seed agent initial places to allow building itinerary
    call_sequence = [
        {"action": "tool", "tool_name": "places.searchAttractions", "arguments": {"destination": "Goa", "interests": ["Beaches"]}},
        {"action": "tool", "tool_name": "weather.getForecast", "arguments": {"destination": "Goa", "day": 1}},
        {"action": "tool", "tool_name": "availability.checkStatus", "arguments": {"attraction_name": "Calangute Beach Water Sports"}},
        {"action": "tool", "tool_name": "route.estimateTravel", "arguments": {"origin": "Hotel in Goa", "destination": "Calangute Beach Water Sports"}},
        {"action": "tool", "tool_name": "cost.calculateEstimate", "arguments": {"transit_costs": 400.0}},
        # Step 6 should NEVER be requested from Ollama because orchestrator completes planning!
        {"action": "finish", "arguments": {}, "reasoning": "should not be reached"}
    ]
    seq_idx = 0
    def sequential_ollama(*a, **k):
        nonlocal seq_idx, ollama_call_count
        ollama_call_count += 1
        res = call_sequence[seq_idx]
        seq_idx += 1
        return {"succeeded": True, "http_status": 200, "valid_json": True, "parsed_dict": res, "error": None, "is_timeout": False}

    agent.policy._call_ollama_detailed = sequential_ollama
    res = agent.run("Goa", 1, 10000.0, ["Beaches"], demo_mode=True, require_ollama=True)

    # Only 5 Ollama calls were made (for the 5 tools); the 6th finish call was NOT sent to Ollama!
    assert ollama_call_count == 5
    assert res["status"] == "verified"
    assert res["termination_reason"] == "orchestrator_completion"
    assert "orchestrator completion" in res["final_status_reason"].lower()

    # Verify trace provenance
    with open(res["trace_file"], "r", encoding="utf-8") as f:
        trace = json.load(f)
    assert trace["termination_reason"] == "orchestrator_completion"
    steps = trace["iteration_steps"]
    assert len(steps) == 6
    last_step = steps[-1]
    assert last_step["decision_provider"] == "orchestrator"
    assert last_step["ollama_request_attempted"] is False
    assert last_step["is_llm_decision_executed"] is False
    assert last_step["status"] == "finished"

    # Authoritative final validation executed
    assert trace["final_validation_executed"] is True
    assert trace["verification_checks"]["finalValidationSucceeded"] is True


def test_incomplete_requirements_agent_continues(agent):
    from backend.agent.action_models import TripRequest
    req = TripRequest(destination="Goa", days=1, budget=10000.0, interests=["Beaches"])
    itinerary = [{
        "day": 1,
        "morning": {"activity": "Beach", "location": "North Goa", "is_outdoor": True},
        "afternoon": {"activity": "Fort", "location": "North Goa", "is_outdoor": False},
        "evening": {"activity": "Lounge", "location": "North Goa", "is_outdoor": False},
    }]
    # Only weather and places; availability, route, cost are missing
    obs = [
        {"tool": "places.searchAttractions", "status": "success", "data": {"attractions": []}},
        {"tool": "weather.getForecast", "status": "success", "data": {"destination": "Goa", "day": 1, "condition": "sunny", "temperature_c": 30.0, "suitableForOutdoor": True, "evidence": "Sunny"}},
    ]
    is_comp, reason = agent._check_planning_complete(req, itinerary, obs, [{"day": 1, "suitableForOutdoor": True}], set(), {})
    assert is_comp is False
    assert "availability check" in reason.lower()


def test_missing_multiday_weather_coverage_prevents_early_completion(agent):
    from backend.agent.action_models import TripRequest
    req = TripRequest(destination="Goa", days=3, budget=15000.0, interests=["Beaches"])
    itinerary = [
        {"day": 1, "morning": {"activity": "A1"}, "afternoon": {"activity": "A2"}, "evening": {"activity": "A3"}},
        {"day": 2, "morning": {"activity": "A4"}, "afternoon": {"activity": "A5"}, "evening": {"activity": "A6"}},
        {"day": 3, "morning": {"activity": "A7"}, "afternoon": {"activity": "A8"}, "evening": {"activity": "A9"}},
    ]
    # Weather covers day 1 only; days 2 and 3 missing
    obs = [
        {"tool": "places.searchAttractions", "status": "success", "data": {"attractions": []}},
        {"tool": "weather.getForecast", "status": "success", "data": {"destination": "Goa", "day": 1, "condition": "sunny", "temperature_c": 30.0, "suitableForOutdoor": True, "evidence": "Sunny"}},
        {"tool": "availability.checkStatus", "status": "success", "data": {"attraction_name": "A1", "is_open": True}},
        {"tool": "route.estimateTravel", "status": "success", "data": {"distance_km": 5.0, "travel_time_mins": 15.0}},
        {"tool": "cost.calculateEstimate", "status": "success", "data": {"total_cost_inr": 3000.0}},
    ]
    is_comp, reason = agent._check_planning_complete(req, itinerary, obs, [{"day": 1, "suitableForOutdoor": True}], set(), {})
    assert is_comp is False
    assert "missing weather coverage" in reason.lower()


def test_pending_recovery_prevents_early_completion(agent):
    from backend.agent.action_models import TripRequest
    req = TripRequest(destination="Goa", days=1, budget=10000.0, interests=["Beaches"])
    itinerary = [{
        "day": 1,
        "morning": {"activity": "Calangute Beach", "location": "North Goa", "is_outdoor": True},
        "afternoon": {"activity": "Fort Aguada", "location": "North Goa", "is_outdoor": False},
        "evening": {"activity": "Dinner", "location": "North Goa", "is_outdoor": False},
    }]
    # Rainy day 1 with outdoor activity not yet recovered
    obs = [
        {"tool": "places.searchAttractions", "status": "success", "data": {"attractions": []}},
        {"tool": "weather.getForecast", "status": "success", "data": {"destination": "Goa", "day": 1, "condition": "rainy", "temperature_c": 26.0, "suitableForOutdoor": False, "evidence": "Rainy"}},
        {"tool": "availability.checkStatus", "status": "success", "data": {"attraction_name": "Calangute Beach", "is_open": True}},
        {"tool": "route.estimateTravel", "status": "success", "data": {"distance_km": 5.0, "travel_time_mins": 15.0}},
        {"tool": "cost.calculateEstimate", "status": "success", "data": {"total_cost_inr": 3000.0}},
    ]
    weather_conds = [{"day": 1, "condition": "rainy", "suitableForOutdoor": False}]
    # Day 1 not in processed_recovery_days
    is_comp, reason = agent._check_planning_complete(req, itinerary, obs, weather_conds, set(), {})
    assert is_comp is False
    assert "weather disruption" in reason.lower() or "outdoor activities remain scheduled" in reason.lower()


def test_failed_or_warning_observations_prevent_early_completion(agent):
    from backend.agent.action_models import TripRequest
    req = TripRequest(destination="Goa", days=1, budget=10000.0, interests=["Beaches"])
    itinerary = [{
        "day": 1,
        "morning": {"activity": "Calangute Beach", "location": "North Goa", "is_outdoor": False},
        "afternoon": {"activity": "Fort Aguada", "location": "North Goa", "is_outdoor": False},
        "evening": {"activity": "Dinner", "location": "North Goa", "is_outdoor": False},
    }]

    # Case A: Availability check with status="warning"
    obs_warn = [
        {"tool": "places.searchAttractions", "status": "success", "data": {"attractions": []}},
        {"tool": "weather.getForecast", "status": "success", "data": {"destination": "Goa", "day": 1, "condition": "sunny", "temperature_c": 30.0, "suitableForOutdoor": True, "evidence": "Sunny"}},
        {"tool": "availability.checkStatus", "status": "warning", "data": {"attraction_name": "Calangute Beach", "is_open": True}, "evidence": "Simulated unconfirmed"},
        {"tool": "route.estimateTravel", "status": "success", "data": {"distance_km": 5.0, "travel_time_mins": 15.0}},
        {"tool": "cost.calculateEstimate", "status": "success", "data": {"total_cost_inr": 3000.0}},
    ]
    is_comp_a, reason_a = agent._check_planning_complete(req, itinerary, obs_warn, [{"day": 1, "suitableForOutdoor": True}], set(), {})
    assert is_comp_a is False
    assert "warning" in reason_a.lower()

    # Case B: Route estimation failed with status="error"
    obs_err = [
        {"tool": "places.searchAttractions", "status": "success", "data": {"attractions": []}},
        {"tool": "weather.getForecast", "status": "success", "data": {"destination": "Goa", "day": 1, "condition": "sunny", "temperature_c": 30.0, "suitableForOutdoor": True, "evidence": "Sunny"}},
        {"tool": "availability.checkStatus", "status": "success", "data": {"attraction_name": "Calangute Beach", "is_open": True}},
        {"tool": "route.estimateTravel", "status": "error", "data": {}, "evidence": "Connection timeout"},
        {"tool": "cost.calculateEstimate", "status": "success", "data": {"total_cost_inr": 3000.0}},
    ]
    is_comp_b, reason_b = agent._check_planning_complete(req, itinerary, obs_err, [{"day": 1, "suitableForOutdoor": True}], set(), {})
    assert is_comp_b is False
    assert "error" in reason_b.lower()
