
"""
LLM Policy Engine for Resilient Horizon Travel Engine.

Provides model-mediated decision making for dynamic tool selection
and step planning.

Supports Ollama and a deterministic fallback policy.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
import os
import json
import urllib.request
import logging

from dotenv import load_dotenv

from backend.agent.action_models import (
    AgentAction,
    ValidatedAction,
    validate_agent_action,
)
from backend.agent.prompts import (
    SYSTEM_POLICY_PROMPT,
    format_policy_prompt,
)

# Load environment variables from the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger(__name__)


class LLMPolicyEngine:

    def __init__(
        self,
        model_name: str = "llama3.2:3b",
        ollama_base_url: str = "http://localhost:11434",
    ):
        self.model_name = os.getenv("LLM_MODEL", model_name)

        self.ollama_base_url = os.getenv(
            "OLLAMA_BASE_URL",
            ollama_base_url,
        ).rstrip("/")

        self.request_timeout = 15.0

    @staticmethod
    def _get_checked_weather_days(
        observations: List[Dict[str, Any]],
    ) -> set:
        """
        Return unique days for which a usable forecast was retrieved.

        Both success and warning are valid retrieval outcomes.
        A warning means the forecast was retrieved but conditions
        may be unsuitable for outdoor activities.
        """

        checked_days = set()

        for obs in observations:

            if obs.get("tool") != "weather.getForecast":
                continue

            if obs.get("status") not in ("success", "warning"):
                continue

            data = obs.get("data")

            if not isinstance(data, dict):
                continue

            day = data.get("day")

            if isinstance(day, bool):
                continue

            try:
                day = int(day)
            except (TypeError, ValueError):
                continue

            if day < 1:
                continue

            # Require actual forecast information.
            has_forecast = any(
                key in data
                for key in (
                    "condition",
                    "suitableForOutdoor",
                    "temperature_c",
                )
            )

            if has_forecast:
                checked_days.add(day)

        return checked_days

    def decide_next_action(
        self,
        request: Dict[str, Any],
        iteration: int,
        max_iterations: int,
        current_itinerary: List[Dict[str, Any]],
        observations: List[Dict[str, Any]],
        mcp_tools: List[Dict[str, Any]],
        validation_res: Dict[str, Any],
    ) -> ValidatedAction:

        registered_tool_names = [
            tool["name"] for tool in mcp_tools
        ]

        tool_catalog_json = json.dumps(
            mcp_tools,
            indent=2,
        )

        sys_prompt = SYSTEM_POLICY_PROMPT.format(
            tool_catalog_json=tool_catalog_json
        )

        user_prompt = format_policy_prompt(
            request=request,
            iteration=iteration,
            max_iterations=max_iterations,
            current_itinerary=current_itinerary,
            observations=observations,
            tool_catalog=mcp_tools,
            validation_res=validation_res,
        )

        # Step 1: Ask the LLM to select the next action.
        raw_dict = self._call_ollama(
            sys_prompt,
            user_prompt,
        )

        # Step 2: Use deterministic fallback if Ollama fails.
        if not raw_dict:

            logger.warning(
                "Ollama unavailable or returned invalid output. "
                "Using deterministic fallback."
            )

            raw_dict = self._fallback_policy_solver(
                request=request,
                iteration=iteration,
                max_iterations=max_iterations,
                current_itinerary=current_itinerary,
                observations=observations,
                validation_res=validation_res,
            )

        # Step 3: Validate the selected action.
        validated_action = validate_agent_action(
            raw_dict,
            registered_tool_names,
        )

        # Step 4: Recover from invalid LLM actions or unknown tools.
        if not validated_action.is_valid:

            logger.warning(
                "LLM action failed validation: %s. "
                "Switching to deterministic fallback.",
                validated_action.errors,
            )

            fallback_action = self._fallback_policy_solver(
                request=request,
                iteration=iteration,
                max_iterations=max_iterations,
                current_itinerary=current_itinerary,
                observations=observations,
                validation_res=validation_res,
            )

            validated_action = validate_agent_action(
                fallback_action,
                registered_tool_names,
            )

        # Step 5: Never return an unvalidated action as valid.
        if not validated_action.is_valid:

            logger.error(
                "Deterministic fallback also returned an invalid "
                "action: %s",
                validated_action.errors,
            )

        return validated_action

    def _call_ollama(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> Optional[Dict[str, Any]]:
        """Invokes the local Ollama server."""

        url = f"{self.ollama_base_url}/api/chat"

        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0.1,
            },
        }

        try:
            req_bytes = json.dumps(payload).encode("utf-8")

            req = urllib.request.Request(
                url,
                data=req_bytes,
                headers={
                    "Content-Type": "application/json",
                },
            )

            with urllib.request.urlopen(
                req,
                timeout=self.request_timeout,
            ) as resp:

                if resp.status != 200:
                    logger.warning(
                        "Ollama returned HTTP status %s",
                        resp.status,
                    )
                    return None

                body = json.loads(
                    resp.read().decode("utf-8")
                )

                content_str = body.get(
                    "message", {}
                ).get("content", "")

                if not content_str:
                    return None

                parsed = json.loads(content_str)

                if not isinstance(parsed, dict):
                    logger.warning(
                        "Ollama returned a non-object response."
                    )
                    return None

                return parsed

        except Exception as exc:

            logger.warning(
                "Ollama request failed: %s: %s",
                type(exc).__name__,
                exc,
            )

            return None

    def _fallback_policy_solver(
        self,
        request: Dict[str, Any],
        iteration: int,
        max_iterations: int,
        current_itinerary: List[Dict[str, Any]],
        observations: List[Dict[str, Any]],
        validation_res: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Deterministic, evidence-aware policy solver.

        Selects tools based on available observations,
        unique weather forecast days, and validation requirements.
        """

        dest = request.get("destination", "Goa")

        interests = request.get(
            "interests",
            ["Beaches", "Historical Places"],
        )

        trip_days = int(request.get("days", 4))

        # Tool 1: Places discovery.
        if not any(
            obs.get("tool") == "places.searchAttractions"
            for obs in observations
        ):
            return {
                "action": "tool",
                "tool_name": "places.searchAttractions",
                "arguments": {
                    "destination": dest,
                    "interests": interests,
                },
                "reasoning": (
                    f"Querying place discovery tool to find "
                    f"candidate attractions for {dest}."
                ),
            }

        # Tool 2: Weather forecast across all travel days.
        checked_weather_days = self._get_checked_weather_days(
            observations
        )

        missing_weather_days = [
            day
            for day in range(1, trip_days + 1)
            if day not in checked_weather_days
        ]

        if missing_weather_days:

            next_day = missing_weather_days[0]

            return {
                "action": "tool",
                "tool_name": "weather.getForecast",
                "arguments": {
                    "destination": dest,
                    "day": next_day,
                },
                "reasoning": (
                    f"Checking weather forecast for {dest}, "
                    f"Day {next_day}. "
                    f"Previously retrieved forecast days: "
                    f"{sorted(checked_weather_days)}."
                ),
            }

        # Tool 3: Availability check.
        if not any(
            obs.get("tool") == "availability.checkStatus"
            for obs in observations
        ):

            top_place = (
                "Fort Aguada Exploration"
                if "goa" in dest.lower()
                else f"{dest} Heritage Center"
            )

            return {
                "action": "tool",
                "tool_name": "availability.checkStatus",
                "arguments": {
                    "attraction_name": top_place,
                    "time_of_day": "Morning",
                },
                "reasoning": (
                    f"Checking availability for {top_place}."
                ),
            }

        # Tool 4: Route estimation.
        if not any(
            obs.get("tool") == "route.estimateTravel"
            for obs in observations
        ):
            return {
                "action": "tool",
                "tool_name": "route.estimateTravel",
                "arguments": {
                    "origin": f"Hotel in {dest}",
                    "destination": f"Central {dest}",
                },
                "reasoning": (
                    "Estimating transit distance and travel time."
                ),
            }

        # Tool 5: Itinerary validation.
        if not any(
            obs.get("tool") == "validation.validateItinerary"
            for obs in observations
        ):
            return {
                "action": "tool",
                "tool_name": "validation.validateItinerary",
                "arguments": {
                    "itinerary": current_itinerary,
                    "budget_inr": float(
                        request.get("budget", 15000.0)
                    ),
                    "interests": interests,
                },
                "reasoning": (
                    "Validating itinerary against budget, "
                    "interests, and constraints."
                ),
            }

        # Tool 6: Cost calculation.
        if not any(
            obs.get("tool") == "cost.calculateEstimate"
            for obs in observations
        ):
            return {
                "action": "tool",
                "tool_name": "cost.calculateEstimate",
                "arguments": {
                    "activities": [
                        day.get("morning", {})
                        for day in current_itinerary
                        if day.get("morning")
                    ],
                    "transit_costs": 1200.0,
                },
                "reasoning": (
                    "Calculating the estimated trip cost."
                ),
            }

        # Finish after collecting the required observations.
        return {
            "action": "finish",
            "tool_name": None,
            "arguments": {},
            "reasoning": (
                "Sufficient observations collected. "
                "Finalizing the itinerary."
            ),
        }
