
"""
LLM Policy Engine for Resilient Horizon Travel Engine.

Provides model-mediated dynamic tool selection with:
- Ollama-based decision making.
- MCP tool catalogue awareness.
- JSON Schema-compatible argument validation.
- Evidence-aware deterministic fallback.
- Configurable Ollama request timeout.
- Safe rejection of malformed actions and arguments.
- Prevention of unnecessary repeated places searches.
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

        try:
            self.request_timeout = max(
                5.0,
                float(os.getenv("OLLAMA_REQUEST_TIMEOUT", "60")),
            )
        except (TypeError, ValueError):
            self.request_timeout = 60.0

    @staticmethod
    def _get_checked_weather_days(
        observations: List[Dict[str, Any]],
    ) -> set:
        """Return unique days with usable weather observations."""

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

    @staticmethod
    def _validate_schema_value(
        value: Any,
        schema: Dict[str, Any],
        path: str = "arguments",
    ) -> List[str]:
        """
        Validate a value against the JSON Schema features used
        by the discovered MCP tool catalogue.

        Supports:
        - object and required properties
        - nested object properties
        - arrays and array items
        - string, integer, number, boolean and null
        - anyOf
        - enum
        """

        if not isinstance(schema, dict):
            return [f"{path}: invalid or missing schema definition."]

        if "anyOf" in schema:

            alternatives = schema.get("anyOf", [])

            if not isinstance(alternatives, list):
                return [f"{path}: invalid anyOf schema."]

            for alternative in alternatives:

                errors = LLMPolicyEngine._validate_schema_value(
                    value,
                    alternative,
                    path,
                )

                if not errors:
                    return []

            return [
                f"{path}: value does not match any permitted schema."
            ]

        expected_type = schema.get("type")

        type_valid = True

        if expected_type == "object":
            type_valid = isinstance(value, dict)

        elif expected_type == "array":
            type_valid = isinstance(value, list)

        elif expected_type == "string":
            type_valid = isinstance(value, str)

        elif expected_type == "integer":
            type_valid = (
                isinstance(value, int)
                and not isinstance(value, bool)
            )

        elif expected_type == "number":
            type_valid = (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
            )

        elif expected_type == "boolean":
            type_valid = isinstance(value, bool)

        elif expected_type == "null":
            type_valid = value is None

        if not type_valid:
            return [
                f"{path}: expected {expected_type}, "
                f"received {type(value).__name__}."
            ]

        errors = []

        if "enum" in schema and value not in schema["enum"]:
            errors.append(
                f"{path}: value is not one of the permitted enum values."
            )

        if expected_type == "object":

            properties = schema.get("properties", {})
            required = schema.get("required", [])

            if not isinstance(properties, dict):
                return [f"{path}: invalid properties schema."]

            if not isinstance(required, list):
                return [f"{path}: invalid required schema."]

            for field in required:
                if field not in value:
                    errors.append(
                        f"{path}.{field}: required field is missing."
                    )

            for field, field_value in value.items():

                if field in properties:

                    errors.extend(
                        LLMPolicyEngine._validate_schema_value(
                            field_value,
                            properties[field],
                            f"{path}.{field}",
                        )
                    )

                elif schema.get("additionalProperties") is False:
                    errors.append(
                        f"{path}.{field}: additional property is not allowed."
                    )

        if expected_type == "array":

            item_schema = schema.get("items")

            if isinstance(item_schema, dict):

                for index, item in enumerate(value):

                    errors.extend(
                        LLMPolicyEngine._validate_schema_value(
                            item,
                            item_schema,
                            f"{path}[{index}]",
                        )
                    )

        return errors

    @classmethod
    def _validate_tool_arguments(
        cls,
        tool_name: str,
        arguments: Dict[str, Any],
        mcp_tools: List[Dict[str, Any]],
    ) -> List[str]:
        """Validate selected tool arguments against its MCP schema."""

        if not isinstance(arguments, dict):
            return ["Tool arguments must be a JSON object."]

        tool_definition = next(
            (
                tool
                for tool in mcp_tools
                if tool.get("name") == tool_name
            ),
            None,
        )

        if tool_definition is None:
            return [f"No MCP schema found for tool '{tool_name}'."]

        input_schema = tool_definition.get("input_schema")

        if not isinstance(input_schema, dict):
            return [
                f"MCP input schema is unavailable for '{tool_name}'."
            ]

        return cls._validate_schema_value(
            arguments,
            input_schema,
            path=f"{tool_name}.arguments",
        )

    @staticmethod
    def _tool_observation_succeeded(
        observations: List[Dict[str, Any]],
        tool_name: str,
    ) -> bool:
        """
        A tool is considered completed only when it returned
        a usable success or warning observation.

        Failed MCP calls do not count as completed work.
        """

        return any(
            obs.get("tool") == tool_name
            and obs.get("status") in ("success", "warning")
            for obs in observations
        )

    @classmethod
    def _validate_candidate(
        cls,
        raw_action: Dict[str, Any],
        registered_tool_names: List[str],
        mcp_tools: List[Dict[str, Any]],
    ) -> ValidatedAction:
        """Validate both the AgentAction and its MCP arguments."""

        validated = validate_agent_action(
            raw_action,
            registered_tool_names,
        )

        if not validated.is_valid:
            return validated

        if validated.action.action == "tool":

            argument_errors = cls._validate_tool_arguments(
                validated.action.tool_name,
                validated.action.arguments,
                mcp_tools,
            )

            if argument_errors:

                return ValidatedAction(
                    is_valid=False,
                    action=validated.action,
                    errors=argument_errors,
                )

        return validated

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
            tool["name"]
            for tool in mcp_tools
            if isinstance(tool, dict) and tool.get("name")
        ]

        tool_catalog_json = json.dumps(
            mcp_tools,
            separators=(",", ":"),
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

        # Step 1: Ask Ollama to choose the next action.
        raw_dict = self._call_ollama(
            sys_prompt,
            user_prompt,
        )

        action_source = "Ollama"

        # Step 2: Use fallback if Ollama is unavailable.
        if not raw_dict:

            logger.warning(
                "Ollama unavailable or returned invalid output. "
                "Using deterministic fallback."
            )

            action_source = "deterministic fallback"

            raw_dict = self._fallback_policy_solver(
                request=request,
                iteration=iteration,
                max_iterations=max_iterations,
                current_itinerary=current_itinerary,
                observations=observations,
                validation_res=validation_res,
            )

        # Step 3: Validate action and MCP arguments.
        validated_action = self._validate_candidate(
            raw_dict,
            registered_tool_names,
            mcp_tools,
        )

        # Step 4: Prevent unnecessary repeated places searches.
        #
        # In the current orchestrator, a successful places search
        # creates the initial itinerary. Further places searches
        # do not update that itinerary. Therefore, repeating this
        # successful tool is unnecessary work.
        #
        # Other tools are not blocked here. In particular, weather
        # forecasts must remain available for different trip days.
        repeated_places_search = (
            validated_action.is_valid
            and validated_action.action.action == "tool"
            and validated_action.action.tool_name
            == "places.searchAttractions"
            and self._tool_observation_succeeded(
                observations,
                "places.searchAttractions",
            )
        )

        if repeated_places_search:

            logger.warning(
                "Rejected repeated places.searchAttractions action "
                "because a successful places observation already exists. "
                "Selecting the next unfinished task."
            )

            fallback_action = self._fallback_policy_solver(
                request=request,
                iteration=iteration,
                max_iterations=max_iterations,
                current_itinerary=current_itinerary,
                observations=observations,
                validation_res=validation_res,
            )

            validated_action = self._validate_candidate(
                fallback_action,
                registered_tool_names,
                mcp_tools,
            )

            action_source = "deterministic fallback (repeat prevention)"

        # Step 5: Recover from malformed LLM decisions.
        if not validated_action.is_valid:

            logger.warning(
                "%s action failed validation: %s. "
                "Switching to deterministic fallback.",
                action_source,
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

            validated_action = self._validate_candidate(
                fallback_action,
                registered_tool_names,
                mcp_tools,
            )

            action_source = "deterministic fallback"

        # Step 6: Report the selected decision source.
        if validated_action.is_valid:

            logger.info(
                "Accepted %s action at iteration %s: %s",
                action_source,
                iteration,
                validated_action.action.tool_name
                or validated_action.action.action,
            )

        else:

            logger.error(
                "No valid action could be produced at iteration %s: %s",
                iteration,
                validated_action.errors,
            )

        return validated_action

    def _call_ollama(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> Optional[Dict[str, Any]]:
        """Invoke the configured local Ollama chat model."""

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
        Evidence-aware deterministic fallback.

        Failed tool calls are not treated as completed work.
        Weather coverage is tracked separately for every trip day.
        """

        dest = request.get("destination", "Goa")

        interests = request.get(
            "interests",
            ["Beaches", "Historical Places"],
        )

        trip_days = int(request.get("days", 4))

        # Tool 1: Attraction discovery.
        if not self._tool_observation_succeeded(
            observations,
            "places.searchAttractions",
        ):

            return {
                "action": "tool",
                "tool_name": "places.searchAttractions",
                "arguments": {
                    "destination": dest,
                    "interests": interests,
                },
                "reasoning": (
                    f"Discovering candidate attractions for {dest} "
                    f"using the registered MCP places tool."
                ),
            }

        # Tool 2: Weather coverage for every travel day.
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
                    f"Retrieving weather evidence for {dest}, "
                    f"Day {next_day}. "
                    f"Completed forecast days: "
                    f"{sorted(checked_weather_days)}."
                ),
            }

        # Tool 3: Availability.
        if not self._tool_observation_succeeded(
            observations,
            "availability.checkStatus",
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
        if not self._tool_observation_succeeded(
            observations,
            "route.estimateTravel",
        ):

            return {
                "action": "tool",
                "tool_name": "route.estimateTravel",
                "arguments": {
                    "origin": f"Hotel in {dest}",
                    "destination": f"Central {dest}",
                },
                "reasoning": (
                    "Estimating travel distance and journey time."
                ),
            }

        # Tool 5: Itinerary validation.
        if not self._tool_observation_succeeded(
            observations,
            "validation.validateItinerary",
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
                    "Validating the itinerary against the budget "
                    "and travel preferences."
                ),
            }

        # Tool 6: Cost calculation.
        if not self._tool_observation_succeeded(
            observations,
            "cost.calculateEstimate",
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

        # All fallback observations have been collected.
        return {
            "action": "finish",
            "tool_name": None,
            "arguments": {},
            "reasoning": (
                "The fallback policy has collected its required "
                "tool observations. Returning control for final "
                "agent-level validation."
            ),
        }
