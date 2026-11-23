
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
import math
import urllib.request
import logging

from dotenv import load_dotenv

from backend.agent.action_models import (
    AgentAction,
    ValidatedAction,
    PolicyDecisionProvenance,
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
        if "://localhost" in self.ollama_base_url:
            self.ollama_base_url = self.ollama_base_url.replace("://localhost", "://127.0.0.1")

        # Configurable request timeout with safe minimum (1.0s) and fallback (10.0s)
        raw_timeout = os.getenv("OLLAMA_REQUEST_TIMEOUT", "10.0")
        try:
            val_timeout = float(raw_timeout)
            if not math.isfinite(val_timeout) or val_timeout <= 0:
                self.request_timeout = 10.0
            else:
                self.request_timeout = max(1.0, val_timeout)
        except (TypeError, ValueError):
            self.request_timeout = 10.0

        # Strict Ollama-required mode for demonstration runs
        raw_require = os.getenv("REQUIRE_OLLAMA_FOR_DEMO", "false")
        self.require_ollama_for_demo = (
            str(raw_require).strip().lower() in ("true", "1", "yes")
        )

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

        schema_errors = cls._validate_schema_value(
            arguments,
            input_schema,
            path=f"{tool_name}.arguments",
        )
        if schema_errors:
            return schema_errors

        semantic_errors = []
        # Semantic validation against MCP tool requirements:
        if tool_name == "route.estimateTravel":
            orig = str(arguments.get("origin", "")).strip()
            dest = str(arguments.get("destination", "")).strip()
            if not orig:
                semantic_errors.append("route.estimateTravel.arguments.origin: origin cannot be empty.")
            if not dest:
                semantic_errors.append("route.estimateTravel.arguments.destination: destination cannot be empty.")
            if orig and dest and orig.lower() == dest.lower():
                semantic_errors.append(
                    f"route.estimateTravel.arguments: origin and destination must be distinct locations, but both were '{orig}'."
                )

        elif tool_name == "availability.checkStatus":
            attr = str(arguments.get("attraction_name", "")).strip()
            if not attr:
                semantic_errors.append("availability.checkStatus.arguments.attraction_name: attraction_name cannot be empty.")

        elif tool_name == "weather.getForecast":
            dest = str(arguments.get("destination", "")).strip()
            if not dest:
                semantic_errors.append("weather.getForecast.arguments.destination: destination cannot be empty.")
            if "day" in arguments:
                day_val = arguments["day"]
                if isinstance(day_val, bool) or not isinstance(day_val, int) or day_val < 1:
                    semantic_errors.append("weather.getForecast.arguments.day: day must be a positive integer (>= 1).")

        return semantic_errors

    @staticmethod
    def _tool_observation_succeeded(
        observations: List[Dict[str, Any]],
        tool_name: str,
    ) -> bool:
        """
        A tool is considered completed only when it returned
        a usable success observation with valid data.

        Failed or warning observations do not count as successful completion.
        """
        for obs in observations:
            if not isinstance(obs, dict):
                continue
            if obs.get("tool") != tool_name:
                continue
            if str(obs.get("status", "")).lower() != "success":
                continue
            data = obs.get("data")
            if not isinstance(data, dict) or not data:
                continue

            if tool_name == "places.searchAttractions":
                attractions = data.get("attractions")
                count = data.get("count", len(attractions) if isinstance(attractions, list) else 0)
                if count > 0 or (isinstance(attractions, list) and len(attractions) > 0):
                    return True
            elif tool_name == "weather.getForecast":
                if any(k in data for k in ("condition", "suitableForOutdoor", "temperature_c")):
                    return True
            elif tool_name == "availability.checkStatus":
                if data.get("is_open") is not None:
                    return True
            elif tool_name == "route.estimateTravel":
                if "distance_km" in data or "travel_time_mins" in data:
                    return True
            elif tool_name == "cost.calculateEstimate":
                if any(k in data for k in ("total_cost_inr", "total_estimated_cost_inr", "estimated_total_cost_inr", "grand_total_inr")):
                    return True
            elif tool_name == "validation.validateItinerary":
                if data.get("valid") is True:
                    return True
            else:
                return True
        return False

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
        require_ollama: Optional[bool] = None,
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

        # Determine whether strict Ollama mode applies for this execution.
        is_demo = bool(request.get("demo_mode", True))
        strict_ollama = (
            require_ollama
            if require_ollama is not None
            else (self.require_ollama_for_demo and is_demo)
        )

        provenance = PolicyDecisionProvenance(
            policy_provider="ollama",
            configured_model=self.model_name,
            ollama_request_attempted=True,
            ollama_request_succeeded=False,
            model_response_valid_json=False,
            action_schema_valid=False,
            argument_schema_valid=False,
            fallback_used=False,
            fallback_reason=None,
            original_action=None,
            final_action=None,
        )

        # Step 1: Ask Ollama to choose the next action.
        ollama_res = self._call_ollama_detailed(
            sys_prompt,
            user_prompt,
        )

        provenance.ollama_request_attempted = True

        provenance.ollama_request_succeeded = ollama_res["succeeded"]
        provenance.model_response_valid_json = ollama_res["valid_json"]
        raw_dict = ollama_res.get("parsed_dict")

        if raw_dict is not None:
            provenance.original_action = raw_dict

        action_source = "Ollama"

        # Step 2: Handle Ollama failure / invalid output.
        if raw_dict is None:
            err_msg = (
                ollama_res.get("error")
                or "Ollama unavailable or returned invalid output."
            )
            logger.warning(
                "Ollama request did not produce usable output: %s",
                err_msg,
            )

            if strict_ollama:
                # In strict Ollama mode: reject without fallback!
                provenance.fallback_used = False
                provenance.fallback_reason = (
                    f"Strict Ollama mode failed: {err_msg}"
                )
                action_fail = AgentAction(
                    action="finish",
                    reasoning=f"Strict Ollama requirement failed: {err_msg}",
                )
                provenance.final_action = {
                    "action": action_fail.action,
                    "tool_name": action_fail.tool_name,
                    "arguments": action_fail.arguments,
                    "reasoning": action_fail.reasoning,
                }
                return ValidatedAction(
                    is_valid=False,
                    action=action_fail,
                    errors=[f"Strict Ollama requirement failed: {err_msg}"],
                    provenance=provenance,
                )

            action_source = "deterministic fallback"
            provenance.fallback_used = True
            provenance.policy_provider = "deterministic_fallback"
            provenance.fallback_reason = err_msg

            raw_dict = self._fallback_policy_solver(
                request=request,
                iteration=iteration,
                max_iterations=max_iterations,
                current_itinerary=current_itinerary,
                observations=observations,
                validation_res=validation_res,
            )

        # Step 3: Validate candidate action and MCP arguments.
        base_val = validate_agent_action(
            raw_dict,
            registered_tool_names,
            provenance=provenance,
        )
        provenance.action_schema_valid = base_val.is_valid

        arg_errors = []
        if base_val.is_valid and base_val.action.action == "tool":
            arg_errors = self._validate_tool_arguments(
                base_val.action.tool_name,
                base_val.action.arguments,
                mcp_tools,
            )
            provenance.argument_schema_valid = not bool(arg_errors)
        elif base_val.is_valid:
            provenance.argument_schema_valid = True

        validation_errors = list(base_val.errors) + arg_errors
        validated_action = ValidatedAction(
            is_valid=not bool(validation_errors),
            action=base_val.action,
            errors=validation_errors,
            provenance=provenance,
        )

        # Step 4: Prevent unnecessary repeated tool calls.
        repeated_call = False
        repeat_reason = None

        if validated_action.is_valid and validated_action.action.action == "tool":
            cand_tool = validated_action.action.tool_name
            cand_args = validated_action.action.arguments or {}

            if cand_tool == "places.searchAttractions":
                is_indoor = bool(cand_args.get("indoor_only", False))
                if not is_indoor and self._tool_observation_succeeded(observations, "places.searchAttractions"):
                    repeated_call = True
                    repeat_reason = (
                        "Rejected repeated places.searchAttractions action "
                        "because a successful places observation already exists."
                    )

            elif cand_tool == "weather.getForecast":
                req_day = cand_args.get("day", 1)
                try:
                    req_day = int(req_day)
                except (TypeError, ValueError):
                    req_day = 1
                checked_days = self._get_checked_weather_days(observations)
                if req_day in checked_days:
                    repeated_call = True
                    repeat_reason = (
                        f"Rejected repeated weather.getForecast action for Day {req_day} "
                        f"because usable weather forecast already exists for this day."
                    )

            elif cand_tool == "validation.validateItinerary":
                if self._tool_observation_succeeded(observations, "validation.validateItinerary"):
                    repeated_call = True
                    repeat_reason = (
                        "Rejected repeated validation.validateItinerary action "
                        "because itinerary has already been successfully validated."
                    )

        if repeated_call:
            logger.warning(
                "%s Selecting the next unfinished task.",
                repeat_reason,
            )

            if strict_ollama and not provenance.fallback_used:
                provenance.fallback_used = False
                provenance.fallback_reason = (
                    f"Strict Ollama mode failed: {repeat_reason}"
                )
                provenance.final_action = {
                    "action": validated_action.action.action,
                    "tool_name": validated_action.action.tool_name,
                    "arguments": validated_action.action.arguments,
                    "reasoning": validated_action.action.reasoning,
                }
                return ValidatedAction(
                    is_valid=False,
                    action=validated_action.action,
                    errors=[f"Strict Ollama requirement failed: {repeat_reason}"],
                    provenance=provenance,
                )

            provenance.fallback_used = True
            provenance.policy_provider = "deterministic_fallback"
            provenance.fallback_reason = repeat_reason
            action_source = "deterministic fallback (repeat prevention)"

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

        # Step 5: Recover from malformed LLM decisions.
        if not validated_action.is_valid and not provenance.fallback_used:
            reason = (
                f"Model action failed validation: {validated_action.errors}"
            )
            logger.warning(
                "%s action failed validation: %s.",
                action_source,
                validated_action.errors,
            )

            if strict_ollama:
                provenance.fallback_used = False
                provenance.fallback_reason = (
                    f"Strict Ollama mode failed: {reason}"
                )
                provenance.final_action = {
                    "action": validated_action.action.action,
                    "tool_name": validated_action.action.tool_name,
                    "arguments": validated_action.action.arguments,
                    "reasoning": validated_action.action.reasoning,
                }
                validated_action.provenance = provenance
                return validated_action

            provenance.fallback_used = True
            provenance.policy_provider = "deterministic_fallback"
            provenance.fallback_reason = reason
            action_source = "deterministic fallback"

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

        # Step 6: Finalize provenance and log.
        provenance.final_action = {
            "action": validated_action.action.action,
            "tool_name": validated_action.action.tool_name,
            "arguments": validated_action.action.arguments,
            "reasoning": validated_action.action.reasoning,
        }
        validated_action.provenance = provenance

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

    def _call_ollama_detailed(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> Dict[str, Any]:
        """Invoke the configured local Ollama chat model and return structured execution details."""

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

        result: Dict[str, Any] = {
            "succeeded": False,
            "http_status": None,
            "valid_json": False,
            "parsed_dict": None,
            "error": None,
            "is_timeout": False,
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

                result["http_status"] = resp.status

                if resp.status != 200:
                    result["error"] = f"Ollama returned HTTP status {resp.status}"
                    logger.warning(result["error"])
                    return result

                body_bytes = resp.read()

                try:
                    body = json.loads(body_bytes.decode("utf-8"))
                except Exception as exc:
                    result["error"] = f"Failed to parse Ollama response body: {exc}"
                    logger.warning(result["error"])
                    return result

                content_str = body.get(
                    "message", {}
                ).get("content", "")

                if not content_str:
                    result["error"] = "Ollama returned empty message content."
                    return result

                try:
                    parsed = json.loads(content_str)
                except Exception as exc:
                    result["succeeded"] = True
                    result["error"] = f"Ollama content was not valid JSON: {exc}"
                    logger.warning(result["error"])
                    return result

                if not isinstance(parsed, dict):
                    result["succeeded"] = True
                    result["error"] = f"Ollama content was not a JSON object (type {type(parsed).__name__})"
                    logger.warning(result["error"])
                    return result

                result["succeeded"] = True
                result["valid_json"] = True
                result["parsed_dict"] = parsed
                return result

        except Exception as exc:
            err_msg = f"{type(exc).__name__}: {exc}"
            is_to = (
                isinstance(exc, (TimeoutError,))
                or "timed out" in str(exc).lower()
                or "timeout" in type(exc).__name__.lower()
            )
            result["error"] = err_msg
            result["is_timeout"] = is_to
            logger.warning("Ollama request failed: %s", err_msg)
            return result

    def _call_ollama(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> Optional[Dict[str, Any]]:
        """Invoke the configured local Ollama chat model."""
        outcome = self._call_ollama_detailed(system_prompt, user_prompt)
        return outcome.get("parsed_dict")

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
        validation_already_run = any(
            isinstance(obs, dict)
            and obs.get("tool") == "validation.validateItinerary"
            and obs.get("status") in ("success", "warning")
            for obs in observations
        )

        if not validation_already_run:

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
