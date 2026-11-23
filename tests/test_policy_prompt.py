
from backend.agent.prompts import (
    build_planning_progress,
    format_policy_prompt,
)


def test_initial_progress_shows_all_work_pending():
    progress = build_planning_progress(
        request={"destination": "Goa", "days": 4},
        current_itinerary=[],
        observations=[],
        validation_res={},
    )

    assert "Attraction discovery: PENDING" in progress
    assert "Itinerary generation: NOT GENERATED" in progress
    assert "0/4 days" in progress
    assert "missing days: [1, 2, 3, 4]" in progress
    assert "Availability check: PENDING" in progress
    assert "Route estimation: PENDING" in progress
    assert "Cost estimation: PENDING" in progress
    assert "Itinerary validation: NOT VALIDATED" in progress


def test_progress_recognizes_successful_places_and_itinerary():
    observations = [
        {
            "tool": "places.searchAttractions",
            "status": "success",
            "data": {
                "attractions": [
                    {"name": "Calangute Beach"}
                ]
            },
        }
    ]

    itinerary = [
        {"day": 1, "morning": {"name": "Calangute Beach"}},
        {"day": 2, "morning": {"name": "Fort Aguada"}},
    ]

    progress = build_planning_progress(
        request={"destination": "Goa", "days": 2},
        current_itinerary=itinerary,
        observations=observations,
        validation_res={},
    )

    assert "successful attraction discovery" in progress
    assert "GENERATED - 2 requested days" in progress


def test_weather_progress_lists_only_usable_forecast_days():
    observations = [
        {
            "tool": "weather.getForecast",
            "status": "success",
            "data": {
                "day": 1,
                "condition": "Sunny",
            },
        },
        {
            "tool": "weather.getForecast",
            "status": "warning",
            "data": {
                "day": 2,
                "condition": "Cloudy",
            },
        },
        {
            "tool": "weather.getForecast",
            "status": "error",
            "data": {
                "day": 3,
                "condition": "Rainy",
            },
        },
        {
            "tool": "weather.getForecast",
            "status": "success",
            "data": {
                "day": 4,
            },
        },
    ]

    progress = build_planning_progress(
        request={"destination": "Goa", "days": 4},
        current_itinerary=[],
        observations=observations,
        validation_res={},
    )

    assert "2/4 days" in progress
    assert "missing days: [3, 4]" in progress


def test_failed_tool_observations_do_not_count_as_completed():
    observations = [
        {
            "tool": "places.searchAttractions",
            "status": "error",
            "data": {"error": "Provider unavailable"},
        },
        {
            "tool": "availability.checkStatus",
            "status": "error",
            "data": {"error": "Request failed"},
        },
    ]

    progress = build_planning_progress(
        request={"destination": "Goa", "days": 1},
        current_itinerary=[],
        observations=observations,
        validation_res={},
    )

    assert "Attraction discovery: INCOMPLETE" in progress
    assert "Availability check: INCOMPLETE" in progress


def test_validation_pass_and_failure_are_distinguished():
    common = {
        "request": {"destination": "Goa", "days": 1},
        "current_itinerary": [{"day": 1}],
        "observations": [],
    }

    passed = build_planning_progress(
        **common,
        validation_res={"valid": True, "issues": []},
    )

    failed = build_planning_progress(
        **common,
        validation_res={
            "valid": False,
            "issues": ["Missing weather evidence"],
        },
    )

    assert "Itinerary validation: PASSED" in passed
    assert "Itinerary validation: FAILED" in failed
    assert "Missing weather evidence" in failed


def test_warning_observation_is_not_reported_as_real_confirmation():
    observations = [
        {
            "tool": "availability.checkStatus",
            "status": "warning",
            "data": {
                "is_open": True,
                "source": "Simulated provider",
            },
        }
    ]

    progress = build_planning_progress(
        request={"destination": "Goa", "days": 1},
        current_itinerary=[],
        observations=observations,
        validation_res={},
    )

    assert "OBSERVED - warning; inspect evidence" in progress


def test_prompt_includes_dynamic_planning_progress():
    observations = [
        {
            "tool": "weather.getForecast",
            "status": "success",
            "data": {
                "day": 1,
                "condition": "Sunny",
            },
        }
    ]

    prompt = format_policy_prompt(
        request={
            "destination": "Goa",
            "days": 3,
            "budget": 15000,
            "interests": ["Beaches"],
            "demo_mode": True,
        },
        iteration=2,
        max_iterations=8,
        current_itinerary=[{"day": 1}],
        observations=observations,
        tool_catalog=[],
        validation_res={},
    )

    assert "### PLANNING PROGRESS SUMMARY" in prompt
    assert "1/3 days" in prompt
    assert "missing days: [2, 3]" in prompt
    assert "Itinerary generation: GENERATED" in prompt
    assert "There is no mandatory fixed tool sequence" in prompt
