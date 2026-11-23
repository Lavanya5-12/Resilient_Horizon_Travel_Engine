
"""
Travel Agent Orchestrator for Resilient Horizon Travel Engine.

Executes dynamic LLM policy decisions across the MCP Tool Boundary.
Requires complete itinerary structure and usable weather evidence.
Validates the exact final itinerary and records durable execution traces.
"""

from typing import Any, Dict, List, Optional
from copy import deepcopy
import datetime
import os
import json
import uuid
import logging
import math
import hashlib

from backend.agent.action_models import (
    TripRequest,
    AgentAction,
    ValidatedAction,
)
from backend.agent.llm_policy import LLMPolicyEngine
from backend.tools.mcp_boundary import MCPToolBoundary
from backend.tools.base import ToolObservation
from backend.providers.demo import DemoProvider
from backend.providers.real import RealProvider
from backend.agent.planner import TravelPlanner
from backend.agent.recovery import RecoveryEngine
from backend.agent.reflection import AgentReflection

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 8
ITINERARY_SLOTS = ("morning", "afternoon", "evening")


class ResilientTravelAgent:

    def __init__(self):
        self.mcp = MCPToolBoundary()
        self.policy = LLMPolicyEngine()
        self.planner = TravelPlanner()
        self.recovery_engine = RecoveryEngine()
        self.reflection_engine = AgentReflection()

        self.trace_dir = os.path.join(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(os.path.abspath(__file__))
                )
            ),
            "traces",
        )
        os.makedirs(self.trace_dir, exist_ok=True)

    @staticmethod
    def _canonical_hash(value: Any) -> str:
        """Create a stable SHA-256 hash for JSON-compatible data."""
        serialized = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _is_usable_weather_observation(obs: Dict[str, Any]) -> bool:
        """Accept successful forecasts and weather warnings with valid data."""
        if not isinstance(obs, dict):
            return False

        if (
            obs.get("tool") != "weather.getForecast"
            or obs.get("status") not in ("success", "warning")
        ):
            return False

        data = obs.get("data")
        if not isinstance(data, dict):
            return False

        destination = data.get("destination")
        day = data.get("day")
        condition = data.get("condition")
        suitability = data.get("suitableForOutdoor")
        evidence = data.get("evidence") or obs.get("evidence")
        temperature = data.get("temperature_c")

        if (
            not isinstance(destination, str)
            or not destination.strip()
            or isinstance(day, bool)
            or not isinstance(day, int)
            or day < 1
            or day > 14
            or not isinstance(condition, str)
            or not condition.strip()
            or not isinstance(suitability, bool)
            or not isinstance(evidence, str)
            or not evidence.strip()
        ):
            return False

        if isinstance(temperature, bool):
            return False

        try:
            if not math.isfinite(float(temperature)):
                return False
        except (TypeError, ValueError):
            return False

        return True

    @classmethod
    def _get_checked_weather_days(
        cls,
        observations: List[Dict[str, Any]],
    ) -> set:
        """Count days with structurally valid success OR warning forecasts."""
        checked_days = set()

        for obs in observations:
            if not cls._is_usable_weather_observation(obs):
                continue
            checked_days.add(obs["data"]["day"])

        return checked_days

    @staticmethod
    def _valid_number(value: Any) -> Optional[float]:
        """Return a finite non-negative number, or None."""
        if isinstance(value, bool):
            return None

        try:
            number = float(value)
        except (TypeError, ValueError):
            return None

        if not math.isfinite(number) or number < 0:
            return None

        return number

    @staticmethod
    def _has_weather_conflict(
        itinerary: List[Dict[str, Any]],
        weather_conditions: List[Dict[str, Any]],
    ) -> bool:
        """Check whether an outdoor activity remains on a bad-weather day."""

        unsuitable_days = set()

        for weather in weather_conditions:
            if (
                isinstance(weather, dict)
                and weather.get("suitableForOutdoor") is False
            ):
                try:
                    unsuitable_days.add(int(weather.get("day")))
                except (TypeError, ValueError):
                    continue

        for day_item in itinerary:
            if not isinstance(day_item, dict):
                continue

            try:
                day_number = int(day_item.get("day"))
            except (TypeError, ValueError):
                continue

            if day_number not in unsuitable_days:
                continue

            for slot in ITINERARY_SLOTS:
                activity = day_item.get(slot)

                if (
                    isinstance(activity, dict)
                    and activity.get("is_outdoor") is True
                ):
                    return True

        return False

    @staticmethod
    def _itinerary_has_all_days(
        itinerary: List[Dict[str, Any]],
        requested_days: int,
    ) -> bool:
        """Require every requested day and all three non-empty activity slots."""
        if not isinstance(itinerary, list) or not itinerary:
            return False

        if requested_days < 1 or len(itinerary) != requested_days:
            return False

        present_days = []

        for item in itinerary:
            if not isinstance(item, dict):
                return False

            day_number = item.get("day")

            if (
                isinstance(day_number, bool)
                or not isinstance(day_number, int)
                or day_number < 1
            ):
                return False

            present_days.append(day_number)

            for slot in ITINERARY_SLOTS:
                activity = item.get(slot)

                if not isinstance(activity, dict):
                    return False

                name = activity.get("activity") or activity.get("name")

                if not isinstance(name, str) or not name.strip():
                    return False

        return sorted(present_days) == list(
            range(1, requested_days + 1)
        )

    @staticmethod
    def _ordered_unique(values: List[str]) -> List[str]:
        """Remove duplicates without changing execution order."""
        return list(dict.fromkeys(values))

    @classmethod
    def _aggregate_recovery_info(
        cls,
        existing_info: Dict[str, Any],
        new_info: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Aggregate recovery results across multiple recovery attempts.

        Preserves all replacement details, evidence, and failed slots.
        Ensures budgetFeasibilityVerified is True only when at least one replacement
        exists and every replacement across all attempts has verified budget feasibility.
        Never overwrites a False budget verification result with True.
        """
        aggregated = deepcopy(existing_info)

        list_fields = (
            "affectedSlots",
            "failedSlots",
            "originalActivities",
            "replacementActivities",
            "replacementDetails",
        )

        for field in list_fields:
            prev_vals = aggregated.get(field, [])
            new_vals = new_info.get(field, [])
            if not isinstance(prev_vals, list):
                prev_vals = []
            if not isinstance(new_vals, list):
                new_vals = []
            aggregated[field] = prev_vals + new_vals

        aggregated["occurred"] = (
            aggregated.get("occurred") is True
            or new_info.get("occurred") is True
        )

        if aggregated.get("affectedDay") is None and new_info.get("affectedDay") is not None:
            aggregated["affectedDay"] = new_info["affectedDay"]

        for field in ("originalActivity", "replacementActivity", "issueDetected"):
            if not aggregated.get(field) and new_info.get(field):
                aggregated[field] = new_info[field]

        for field in ("impact", "recoveryAction", "recalculation", "verification"):
            new_text = new_info.get(field)
            if new_text:
                old_text = aggregated.get(field, "")
                aggregated[field] = f"{old_text} {new_text}".strip()

        aggregated["hasSimulatedEvidence"] = (
            aggregated.get("hasSimulatedEvidence") is True
            or new_info.get("hasSimulatedEvidence") is True
        )
        aggregated["hasRealWorldConfirmation"] = (
            aggregated.get("hasRealWorldConfirmation", True)
            and new_info.get("hasRealWorldConfirmation", True)
            and aggregated["occurred"]
        )

        # Track unverified budget occurrences across attempts
        attempt_had_replacements = len(new_info.get("replacementActivities", [])) > 0
        if attempt_had_replacements and new_info.get("budgetFeasibilityVerified") is not True:
            aggregated["budget_unverified_found"] = True

        all_failed_slots = aggregated.get("failedSlots", [])
        any_recovery = aggregated.get("occurred") is True
        has_replacements = len(aggregated.get("replacementActivities", [])) > 0

        # Check every replacement detail across all attempts
        all_rep_budgets_verified = True
        rep_details = aggregated.get("replacementDetails", [])
        if rep_details:
            for rep in rep_details:
                if not isinstance(rep, dict):
                    all_rep_budgets_verified = False
                    break
                rep_ev = rep.get("recovery_evidence")
                if not isinstance(rep_ev, dict) or rep_ev.get("budget_feasibility_verified") is not True:
                    all_rep_budgets_verified = False
                    break
        elif has_replacements:
            all_rep_budgets_verified = False
        else:
            all_rep_budgets_verified = False

        aggregated_bfv = (
            has_replacements
            and all_rep_budgets_verified
            and not aggregated.get("budget_unverified_found", False)
        )
        aggregated["budgetFeasibilityVerified"] = aggregated_bfv

        if all_failed_slots and any_recovery:
            aggregated["status"] = "partial"
            aggregated["verified"] = False
        elif all_failed_slots:
            aggregated["status"] = "failed"
            aggregated["verified"] = False
        elif any_recovery:
            aggregated["status"] = "completed"
            aggregated["verified"] = (
                not all_failed_slots
                and aggregated_bfv is True
                and new_info.get("verified", False) is True
                and (existing_info.get("verified", True) if existing_info.get("occurred") else True)
            )
        else:
            aggregated["status"] = "not_needed"
            aggregated["verified"] = False

        reason_parts = []
        if aggregated["replacementActivities"]:
            reason_parts.append(
                "Replaced "
                f"{len(aggregated['replacementActivities'])} "
                "weather-affected activity slot(s) using "
                "indoor place and route observations."
            )
            if not aggregated_bfv:
                reason_parts.append(
                    "Complete budget feasibility could not be verified."
                )

        if all_failed_slots:
            reason_parts.append(
                f"{len(all_failed_slots)} affected slot(s) "
                "could not be fully recovered."
            )

        if not reason_parts:
            reason_parts.append(
                "No eligible outdoor activity required replacement "
                "for the processed disruption observations."
            )

        aggregated["reason"] = " ".join(reason_parts)
        return aggregated

    def _check_planning_complete(
        self,
        req_obj: TripRequest,
        current_itinerary: List[Dict[str, Any]],
        observations: List[Dict[str, Any]],
        weather_conditions: List[Dict[str, Any]],
        processed_recovery_days: set,
        recovery_info: Dict[str, Any],
    ) -> tuple[bool, str]:
        """
        Deterministically verifies if all five planning requirements are satisfied:
        1. Complete itinerary for all requested days.
        2. Usable weather coverage for every requested day.
        3. Successful availability checks for actual planned attractions.
        4. Valid route observations for actual itinerary locations.
        5. Valid cost estimation.

        Pending weather recovery, unresolved disruptions, failed observations,
        warnings, empty results, or invalid data prevent early completion.
        """
        # 1. Complete itinerary for all requested days
        if not self._itinerary_has_all_days(current_itinerary, req_obj.days):
            return False, "Itinerary is missing requested days or has empty activity slots."

        # Collect all planned attraction names
        planned_attraction_names = set()
        for day_dict in current_itinerary:
            for slot_key in ITINERARY_SLOTS:
                slot = day_dict.get(slot_key)
                if isinstance(slot, dict):
                    name = slot.get("activity") or slot.get("name")
                    if isinstance(name, str) and name.strip():
                        planned_attraction_names.add(name.strip().lower())

        if not planned_attraction_names:
            return False, "Itinerary contains no named attractions."

        # 2. Usable weather coverage for every requested day
        checked_days = self._get_checked_weather_days(observations)
        missing_weather_days = [
            d for d in range(1, req_obj.days + 1)
            if d not in checked_days
        ]
        if missing_weather_days:
            return False, f"Missing weather coverage for requested day(s): {missing_weather_days}."

        # 3. Weather disruptions & recovery resolution
        for w in weather_conditions:
            if isinstance(w, dict) and w.get("suitableForOutdoor") is False:
                try:
                    w_day = int(w.get("day"))
                except (TypeError, ValueError):
                    continue
                if w_day in range(1, req_obj.days + 1):
                    if w_day not in processed_recovery_days:
                        return False, f"Weather disruption on Day {w_day} has not been processed for recovery."

        if self._has_weather_conflict(current_itinerary, weather_conditions):
            return False, "Outdoor activities remain scheduled on bad-weather day(s)."

        if recovery_info.get("status") == "failed":
            return False, f"Weather recovery failed: {recovery_info.get('reason')}."

        if recovery_info.get("failedSlots"):
            return False, f"Unresolved failed slots remain: {recovery_info.get('failedSlots')}."

        # 4. Check for any failed observations across all tools
        for obs in observations:
            if not isinstance(obs, dict):
                continue
            if str(obs.get("status", "")).lower() == "error":
                return False, f"Observation for tool '{obs.get('tool')}' reported error: {obs.get('evidence')}."

        # 5. Successful availability checks for actual planned attractions
        avail_obs = [
            obs for obs in observations
            if isinstance(obs, dict) and obs.get("tool") == "availability.checkStatus"
        ]
        if not avail_obs:
            return False, "No availability check observations found."

        for obs in avail_obs:
            if str(obs.get("status", "")).lower() == "warning":
                return False, f"Availability check returned warning status: {obs.get('evidence')}."
            data = obs.get("data")
            if not isinstance(data, dict):
                return False, "Availability check data is missing or invalid."
            if data.get("is_open") is not True:
                return False, f"Availability check reported attraction is not open: {obs.get('evidence')}."

        successful_avail = [
            obs for obs in avail_obs
            if str(obs.get("status", "")).lower() == "success"
            and isinstance(obs.get("data"), dict)
            and obs["data"].get("is_open") is True
        ]
        if not successful_avail:
            return False, "No successful availability check observation found."

        has_matching_avail = False
        for obs in successful_avail:
            data = obs.get("data", {})
            checked_name = str(data.get("attraction_name") or obs.get("evidence", "")).strip().lower()
            if any(p in checked_name or checked_name in p for p in planned_attraction_names) or req_obj.destination.lower() in checked_name:
                has_matching_avail = True
                break

        if not has_matching_avail:
            return False, "Availability check was not for any attraction in the current itinerary."

        # 6. Valid route observations for actual itinerary locations
        route_obs = [
            obs for obs in observations
            if isinstance(obs, dict) and obs.get("tool") == "route.estimateTravel"
        ]
        if not route_obs:
            return False, "No route estimation observations found."

        for obs in route_obs:
            if str(obs.get("status", "")).lower() == "warning":
                return False, f"Route estimation returned warning status: {obs.get('evidence')}."
            data = obs.get("data")
            if not isinstance(data, dict):
                return False, "Route estimation data is missing or invalid."

        successful_route = [
            obs for obs in route_obs
            if str(obs.get("status", "")).lower() == "success"
            and isinstance(obs.get("data"), dict)
            and (self._valid_number(obs["data"].get("distance_km")) or 0) > 0
            and (self._valid_number(obs["data"].get("travel_time_mins")) or 0) > 0
        ]
        if not successful_route:
            return False, "No successful route estimation with valid positive distance and time found."

        # 7. Valid cost estimation
        cost_obs = [
            obs for obs in observations
            if isinstance(obs, dict) and obs.get("tool") == "cost.calculateEstimate"
        ]
        if not cost_obs:
            return False, "No cost estimation observations found."

        for obs in cost_obs:
            if str(obs.get("status", "")).lower() == "warning":
                return False, f"Cost estimation returned warning status: {obs.get('evidence')}."
            data = obs.get("data")
            if not isinstance(data, dict):
                return False, "Cost estimation data is missing or invalid."

        successful_cost = [
            obs for obs in cost_obs
            if str(obs.get("status", "")).lower() == "success"
            and isinstance(obs.get("data"), dict)
            and (self._valid_number(obs["data"].get("total_cost_inr")) or 0) > 0
        ]
        if not successful_cost:
            return False, "No successful cost estimation with valid positive total cost found."

        return True, "All five planning requirements (itinerary, weather coverage, availability, route, cost) are genuinely satisfied."

    def run(
        self,
        destination: str,
        days: int = 4,
        budget: float = 15000.0,
        interests: List[str] = None,
        travel_date: Optional[str] = None,
        demo_mode: bool = True,
        max_iterations: Optional[int] = None,
        require_ollama: Optional[bool] = None,
    ) -> Dict[str, Any]:

        req_obj = TripRequest(
            destination=destination,
            days=days,
            budget=budget,
            interests=interests or [
                "Beaches",
                "Historical Places",
            ],
            travel_date=travel_date,
            demo_mode=demo_mode,
        )

        req_dict = req_obj.model_dump()
        request_hash = self._canonical_hash(req_dict)

        if max_iterations is None:
            max_iterations = max(
                MAX_ITERATIONS,
                req_obj.days + 6,
            )

        provider = (
            DemoProvider()
            if req_obj.demo_mode
            else RealProvider()
        )

        session_id = str(uuid.uuid4())[:8]
        start_time = datetime.datetime.now().isoformat()

        stages_log: List[Dict[str, Any]] = []
        observations: List[Dict[str, Any]] = []
        tools_executed: List[str] = []
        iteration_steps: List[Dict[str, Any]] = []

        def record_stage(
            stage_id: str,
            stage_name: str,
            status: str,
            detail: str,
        ):
            stages_log.append({
                "id": stage_id,
                "name": stage_name,
                "status": status,
                "detail": detail,
                "timestamp": datetime.datetime.now().isoformat(),
            })

        record_stage(
            "1",
            "UNDERSTAND",
            "completed",
            (
                f"Parsed trip request for {req_obj.destination} "
                f"({req_obj.days} Days, "
                f"INR {req_obj.budget:,.0f} Budget)."
            ),
        )

        iteration = 0
        current_itinerary: List[Dict[str, Any]] = []

        recovery_info: Dict[str, Any] = {
            "occurred": False,
            "status": "not_needed",
            "verified": False,
            "budgetFeasibilityVerified": False,
            "reason": "No weather disruption has been processed.",
            "affectedDay": None,
            "affectedSlots": [],
            "failedSlots": [],
            "originalActivities": [],
            "replacementActivities": [],
            "replacementDetails": [],
            "originalActivity": "",
            "replacementActivity": "",
            "issueDetected": "",
            "impact": "",
            "recoveryAction": "",
            "recalculation": "",
            "verification": "",
            "hasSimulatedEvidence": False,
            "hasRealWorldConfirmation": False,
        }

        # Tracks days already passed to the recovery engine.
        # Weather warnings received before the plan exists remain pending.
        processed_recovery_days = set()

        validation_res: Dict[str, Any] = {}
        weather_conditions: List[Dict[str, Any]] = []
        final_validation_executed = False
        final_validation_succeeded = False

        def process_pending_weather_recovery():
            """
            Process bad-weather observations only after an itinerary exists.

            This handles both possible tool orders:
            1. Weather first, then places.
            2. Places first, then weather.

            Only newly pending disruption days are sent to the recovery
            engine, preventing previous recovery results from being lost.
            """
            nonlocal current_itinerary
            nonlocal recovery_info

            pending_weather = []

            for weather in weather_conditions:
                if not isinstance(weather, dict):
                    continue

                if weather.get("suitableForOutdoor") is not False:
                    continue

                try:
                    day_number = int(weather.get("day"))
                except (TypeError, ValueError):
                    continue

                if day_number in processed_recovery_days:
                    continue

                pending_weather.append(weather)

            if not pending_weather:
                return

            pending_days = {
                int(item["day"])
                for item in pending_weather
            }

            if not current_itinerary:
                record_stage(
                    "5",
                    "RECOVER",
                    "pending",
                    (
                        "Weather disruption recorded for "
                        f"Day(s) {sorted(pending_days)}, but recovery "
                        "is deferred until the itinerary is created."
                    ),
                )
                return

            record_stage(
                "5",
                "RECOVER",
                "running",
                (
                    "Attempting evidence-based recovery for "
                    f"Day(s) {sorted(pending_days)}."
                ),
            )

            try:
                revised_itinerary, new_recovery_info = (
                    self.recovery_engine.detect_and_recover(
                        itinerary=current_itinerary,
                        weather_observations=pending_weather,
                        provider=provider,
                        user_interests=req_obj.interests,
                        mcp_boundary=self.mcp,
                        observations=observations,
                        budget=req_obj.budget,
                        trip_context={
                            "destination": req_obj.destination,
                            "budget": req_obj.budget,
                            "interests": req_obj.interests,
                            "travel_date": req_obj.travel_date,
                            "days": req_obj.days,
                        },
                    )
                )

                if isinstance(revised_itinerary, list):
                    current_itinerary = revised_itinerary
                else:
                    raise TypeError(
                        "Recovery engine returned an invalid itinerary."
                    )

                if not isinstance(new_recovery_info, dict):
                    raise TypeError(
                        "Recovery engine returned invalid recovery details."
                    )

                # Aggregate recovery details, preserving replacement evidence,
                # failed slots, and strict budget feasibility across attempts.
                recovery_info = self._aggregate_recovery_info(
                    existing_info=recovery_info,
                    new_info=new_recovery_info,
                )

                # Mark these days as processed only after the recovery
                # attempt has returned successfully.
                processed_recovery_days.update(pending_days)

                record_stage(
                    "5",
                    "RECOVER",
                    (
                        "completed"
                        if recovery_info.get("verified") is True
                        else "warning"
                    ),
                    (
                        "Recovery result: "
                        f"{recovery_info.get('reason')}"
                    ),
                )

            except Exception as exc:
                logger.exception("Weather recovery attempt failed.")

                recovery_info["status"] = "failed"
                recovery_info["verified"] = False
                recovery_info["budgetFeasibilityVerified"] = False
                recovery_info["reason"] = (
                    f"Recovery attempt failed: {exc}"
                )
                recovery_info["failedSlots"].append(
                    f"Recovery engine error for Day(s) "
                    f"{sorted(pending_days)}: {exc}"
                )

                # Mark attempted days to avoid an uncontrolled retry loop.
                processed_recovery_days.update(pending_days)

                record_stage(
                    "5",
                    "RECOVER",
                    "failed",
                    recovery_info["reason"],
                )

        mcp_catalog = self.mcp.list_mcp_tools()

        # Decision provenance and termination tracking
        termination_reason: Optional[str] = None
        policy_finished_successfully: bool = False
        finish_source: Optional[str] = None
        ollama_attempt_count: int = 0
        ollama_successful_requests_count: int = 0
        ollama_accepted_decisions_count: int = 0
        fallback_decisions_count: int = 0
        safety_overrides_count: int = 0

        # Dynamic agent loop:
        # DECIDE -> VALIDATE -> ACT -> OBSERVE -> REPEAT

        while iteration < max_iterations:

            # -------------------------------------------------------------
            # Deterministic orchestrator completion detection
            # Before requesting another LLM decision, check if all five
            # planning requirements are already genuinely satisfied.
            # -------------------------------------------------------------
            process_pending_weather_recovery()

            is_llm_mode = bool(
                require_ollama
                or not req_obj.demo_mode
                or getattr(self.policy, "require_ollama_for_demo", False)
            )

            if is_llm_mode:
                is_complete, completion_reason = self._check_planning_complete(
                    req_obj=req_obj,
                    current_itinerary=current_itinerary,
                    observations=observations,
                    weather_conditions=weather_conditions,
                    processed_recovery_days=processed_recovery_days,
                    recovery_info=recovery_info,
                )

                if is_complete:
                    logger.info(
                        "Deterministic completion detected: %s",
                        completion_reason,
                    )
                    policy_finished_successfully = True
                    finish_source = "orchestrator"

                    record_stage(
                        "6",
                        "VERIFY",
                        "running",
                        "All five planning requirements satisfied. "
                        "Orchestrator completing planning to proceed to authoritative validation.",
                    )

                    step_record = {
                        "iteration": iteration + 1,
                        "decision_provider": "orchestrator",
                        "model": self.policy.model_name,
                        "ollama_request_attempted": False,
                        "ollama_request_succeeded": False,
                        "fallback_used": False,
                        "fallback_reason": None,
                        "original_decision": {
                            "action": "finish",
                            "tool_name": None,
                            "arguments": {},
                            "reasoning": completion_reason,
                        },
                        "policy_decision": {
                            "action": "finish",
                            "tool_name": None,
                            "arguments": {},
                            "reasoning": completion_reason,
                        },
                        "safety_override_applied": False,
                        "safety_override_reason": None,
                        "llm_decision_selected_for_execution": False,
                        "is_llm_decision_executed": False,
                        "reasoning": completion_reason,
                        "action": "finish",
                        "tool_name": None,
                        "arguments": {},
                        "is_valid": True,
                        "validation_errors": [],
                        "executed_action": "finish",
                        "executed_tool": None,
                        "executed_arguments": {},
                        "tool_execution_status": "completed",
                        "observation_summary": (
                            "All five planning requirements satisfied; "
                            "orchestrator completed planning and proceeded to authoritative validation."
                        ),
                        "status": "finished",
                    }
                    iteration += 1
                    iteration_steps.append(step_record)
                    break

            iteration += 1

            try:
                val_action: ValidatedAction = (
                    self.policy.decide_next_action(
                        request=req_dict,
                        iteration=iteration,
                        max_iterations=max_iterations,
                        current_itinerary=current_itinerary,
                        observations=observations,
                        mcp_tools=mcp_catalog,
                        validation_res=validation_res,
                        require_ollama=require_ollama,
                    )
                )
            except Exception as pol_exc:
                logger.exception("Policy decision failed with exception: %s", pol_exc)
                termination_reason = "exception"
                break

            prov = val_action.provenance
            if prov and prov.ollama_request_attempted:
                ollama_attempt_count += 1

            if prov and prov.ollama_request_succeeded:
                ollama_successful_requests_count += 1

            is_accepted_ollama_decision = bool(
                prov
                and prov.policy_provider == "ollama"
                and not prov.fallback_used
                and prov.ollama_request_succeeded
                and prov.model_response_valid_json
                and prov.action_schema_valid
                and prov.argument_schema_valid
                and val_action.is_valid
            )
            if is_accepted_ollama_decision:
                ollama_accepted_decisions_count += 1

            if prov and prov.fallback_used:
                fallback_decisions_count += 1

            act_obj = val_action.action
            model_original_decision = (
                prov.original_action
                if (prov and prov.original_action)
                else {
                    "action": act_obj.action,
                    "tool_name": act_obj.tool_name,
                    "arguments": dict(act_obj.arguments or {}),
                    "reasoning": act_obj.reasoning,
                }
            )
            final_policy_decision = (
                prov.final_action
                if (prov and prov.final_action)
                else {
                    "action": act_obj.action,
                    "tool_name": act_obj.tool_name,
                    "arguments": dict(act_obj.arguments or {}),
                    "reasoning": act_obj.reasoning,
                }
            )

            safety_override_applied = False
            safety_override_reason = None

            checked_days = self._get_checked_weather_days(
                observations
            )

            missing_days = [
                day
                for day in range(1, req_obj.days + 1)
                if day not in checked_days
            ]

            # Safety gate: do not finish before an itinerary exists.
            if val_action.is_valid and act_obj.action == "finish":

                if not current_itinerary:
                    safety_override_applied = True
                    safety_override_reason = (
                        "Completion blocked because an itinerary "
                        "has not yet been created."
                    )
                    act_obj = AgentAction(
                        action="tool",
                        tool_name="places.searchAttractions",
                        arguments={
                            "destination": req_obj.destination,
                            "interests": req_obj.interests,
                        },
                        reasoning=safety_override_reason,
                    )

                    val_action = ValidatedAction(
                        is_valid=True,
                        action=act_obj,
                        errors=[],
                        provenance=val_action.provenance,
                    )

                elif missing_days:
                    next_day = missing_days[0]
                    safety_override_applied = True
                    safety_override_reason = (
                        f"Completion blocked because usable weather "
                        f"evidence for Day {next_day} is missing."
                    )
                    act_obj = AgentAction(
                        action="tool",
                        tool_name="weather.getForecast",
                        arguments={
                            "destination": req_obj.destination,
                            "day": next_day,
                        },
                        reasoning=safety_override_reason,
                    )

                    val_action = ValidatedAction(
                        is_valid=True,
                        action=act_obj,
                        errors=[],
                        provenance=val_action.provenance,
                    )

            # Prevent endless repeated weather requests after coverage.
            if (
                val_action.is_valid
                and act_obj.action == "tool"
                and act_obj.tool_name == "weather.getForecast"
                and not missing_days
            ):
                safety_override_applied = True
                safety_override_reason = (
                    "Weather coverage is complete. "
                    "Proceeding to final itinerary validation."
                )
                act_obj = AgentAction(
                    action="finish",
                    reasoning=safety_override_reason,
                )

                val_action = ValidatedAction(
                    is_valid=True,
                    action=act_obj,
                    errors=[],
                    provenance=val_action.provenance,
                )

            if safety_override_applied:
                safety_overrides_count += 1

            llm_decision_selected_for_execution = bool(
                is_accepted_ollama_decision
                and not safety_override_applied
            )

            step_record = {
                "iteration": iteration,
                "decision_provider": (
                    prov.policy_provider
                    if prov
                    else ("ollama" if not req_obj.demo_mode else "deterministic_fallback")
                ),
                "model": (
                    prov.configured_model
                    if prov
                    else self.policy.model_name
                ),
                "ollama_request_attempted": (
                    prov.ollama_request_attempted
                    if prov
                    else False
                ),
                "ollama_request_succeeded": (
                    prov.ollama_request_succeeded
                    if prov
                    else False
                ),
                "fallback_used": (
                    prov.fallback_used
                    if prov
                    else True
                ),
                "fallback_reason": (
                    prov.fallback_reason
                    if prov
                    else None
                ),
                "original_decision": model_original_decision,
                "policy_decision": final_policy_decision,
                "safety_override_applied": safety_override_applied,
                "safety_override_reason": safety_override_reason,
                "llm_decision_selected_for_execution": llm_decision_selected_for_execution,
                "is_llm_decision_executed": False,
                "reasoning": act_obj.reasoning,
                "action": act_obj.action,
                "tool_name": act_obj.tool_name,
                "arguments": act_obj.arguments,
                "is_valid": val_action.is_valid,
                "validation_errors": val_action.errors,
                "executed_action": act_obj.action if val_action.is_valid else None,
                "executed_tool": act_obj.tool_name if val_action.is_valid else None,
                "executed_arguments": act_obj.arguments if val_action.is_valid else {},
                "tool_execution_status": None,
                "observation_summary": None,
            }

            if not val_action.is_valid:
                termination_reason = "invalid_action"
                step_record["status"] = "invalid_action"
                step_record["tool_execution_status"] = "rejected"
                step_record["is_llm_decision_executed"] = False
                step_record["observation_summary"] = (
                    f"Action rejected: {', '.join(val_action.errors)}"
                )
                iteration_steps.append(step_record)

                logger.warning(
                    "Invalid agent action at iteration %s: %s",
                    iteration,
                    val_action.errors,
                )
                break

            if act_obj.action == "finish":
                policy_finished_successfully = True
                if safety_override_applied:
                    finish_source = "safety_override"
                    step_record["is_llm_decision_executed"] = False
                else:
                    finish_source = "policy"
                    step_record["is_llm_decision_executed"] = llm_decision_selected_for_execution

                step_record["status"] = "finished"
                step_record["executed_action"] = "finish"
                step_record["executed_tool"] = None
                step_record["executed_arguments"] = {}
                step_record["tool_execution_status"] = "completed"
                step_record["observation_summary"] = (
                    "Finish action selected; proceeding to authoritative final validation."
                )
                iteration_steps.append(step_record)
                break

            tool_name = act_obj.tool_name
            args = dict(act_obj.arguments or {})

            # Supply authoritative request values and safe defaults.

            if tool_name == "places.searchAttractions":
                args.setdefault("destination", req_obj.destination)
                args.setdefault("interests", req_obj.interests)

            elif tool_name == "weather.getForecast":
                args["destination"] = req_obj.destination

                checked_days = self._get_checked_weather_days(
                    observations
                )

                missing_days = [
                    day
                    for day in range(1, req_obj.days + 1)
                    if day not in checked_days
                ]

                requested_day = args.get("day")

                try:
                    requested_day = int(requested_day)
                except (TypeError, ValueError):
                    requested_day = None

                if requested_day not in missing_days and missing_days:
                    requested_day = missing_days[0]

                if requested_day is not None:
                    args["day"] = requested_day

                # Calculate the exact calendar date for the requested day:
                raw_travel_date = (req_obj.travel_date or "").strip()
                if raw_travel_date and raw_travel_date.lower() not in ("flexible", "none"):
                    try:
                        base_date = datetime.date.fromisoformat(raw_travel_date)
                        target_day = int(args.get("day", 1))
                        forecast_date = base_date + datetime.timedelta(days=target_day - 1)
                        args["date"] = forecast_date.isoformat()
                    except (ValueError, TypeError):
                        args["date"] = raw_travel_date
                else:
                    args["date"] = ""

            elif tool_name == "route.estimateTravel":
                fallback_dest = f"Central {req_obj.destination}"
                if current_itinerary and isinstance(current_itinerary[0], dict):
                    morning_act = current_itinerary[0].get("morning")
                    if isinstance(morning_act, dict) and morning_act.get("location"):
                        fallback_dest = str(morning_act["location"])
                args.setdefault(
                    "origin",
                    f"Hotel in {req_obj.destination}",
                )
                args.setdefault(
                    "destination",
                    fallback_dest,
                )

            elif tool_name == "availability.checkStatus":
                fallback_attr = f"Main Landmark in {req_obj.destination}"
                if current_itinerary and isinstance(current_itinerary[0], dict):
                    morning_act = current_itinerary[0].get("morning")
                    if isinstance(morning_act, dict) and morning_act.get("activity"):
                        fallback_attr = str(morning_act["activity"])
                args.setdefault(
                    "attraction_name",
                    fallback_attr,
                )

            elif tool_name == "cost.calculateEstimate":
                args.setdefault(
                    "activities",
                    [
                        day.get(slot)
                        for day in current_itinerary
                        for slot in ITINERARY_SLOTS
                        if isinstance(day.get(slot), dict)
                    ],
                )

            elif tool_name == "validation.validateItinerary":
                args.setdefault("itinerary", current_itinerary)
                args.setdefault("budget_inr", req_obj.budget)
                args.setdefault("interests", req_obj.interests)
                args.setdefault("weather_conditions", weather_conditions)
                args["request_context"] = {
                    **req_dict,
                    "request_sha256": request_hash,
                }

            step_record["executed_action"] = "tool"
            step_record["executed_tool"] = tool_name
            step_record["executed_arguments"] = dict(args)

            try:
                obs_obj: ToolObservation = self.mcp.invoke_tool(
                    tool_name=tool_name,
                    arguments=args,
                    provider=provider,
                )

                obs_dict = obs_obj.model_dump()

            except Exception as exc:
                logger.exception(
                    "MCP invocation failed for %s",
                    tool_name,
                )

                obs_dict = {
                    "tool": tool_name,
                    "status": "error",
                    "evidence": str(exc),
                    "data": {},
                }

                step_record["observation"] = obs_dict
                step_record["tool_execution_status"] = "error"
                step_record["observation_summary"] = f"Tool invocation error: {exc}"
                step_record["status"] = "tool_error"
                step_record["is_llm_decision_executed"] = False

                observations.append(obs_dict)
                tools_executed.append(tool_name)
                iteration_steps.append(step_record)

                if getattr(exc, "is_fatal", False) or "fatal" in str(exc).lower():
                    termination_reason = "tool_execution_failure"
                    break
                continue

            tools_executed.append(tool_name)
            observations.append(obs_dict)

            tool_succeeded = obs_obj.status in ("success", "warning")

            step_record["observation"] = obs_dict
            step_record["tool_execution_status"] = obs_obj.status
            step_record["observation_summary"] = str(obs_obj.evidence)
            step_record["status"] = (
                "completed"
                if tool_succeeded
                else "tool_error"
            )
            step_record["is_llm_decision_executed"] = bool(
                llm_decision_selected_for_execution and tool_succeeded
            )
            iteration_steps.append(step_record)

            if obs_obj.status == "error" and ("fatal" in str(obs_obj.evidence).lower() or getattr(obs_obj, "fatal", False)):
                termination_reason = "tool_execution_failure"
                break

            # Update internal state from tool observations.

            if tool_name == "places.searchAttractions":

                record_stage(
                    "2",
                    "PLAN",
                    "completed" if obs_obj.status == "success" else "failed",
                    (
                        "Places observation received from MCP boundary: "
                        f"{obs_obj.evidence}"
                    ),
                )

                if (
                    obs_obj.status == "success"
                    and not current_itinerary
                ):
                    places_list = (
                        obs_obj.data.get("attractions", [])
                        if isinstance(obs_obj.data, dict)
                        else []
                    )

                    current_itinerary = (
                        self.planner.create_initial_plan(
                            destination=req_obj.destination,
                            days=req_obj.days,
                            budget=req_obj.budget,
                            interests=req_obj.interests,
                            places_data=places_list,
                        )
                    )

                    # IMPORTANT:
                    # Weather may have been observed before the itinerary
                    # existed. Process those pending disruptions now.
                    process_pending_weather_recovery()

            elif tool_name == "weather.getForecast":

                weather_observation = obs_dict
                weather_is_usable = self._is_usable_weather_observation(
                    weather_observation
                )

                if weather_is_usable:
                    weather_data = dict(obs_obj.data)
                    weather_day = weather_data.get("day")
                    weather_data["observation_status"] = obs_obj.status

                    existing_days = {
                        item.get("day")
                        for item in weather_conditions
                        if isinstance(item, dict)
                    }
                    is_new_weather_day = weather_day not in existing_days

                    if is_new_weather_day:
                        weather_conditions.append(weather_data)

                    record_stage(
                        "3",
                        "OBSERVE",
                        "completed",
                        (
                            f"Collected usable weather observation for Day "
                            f"{weather_day} (MCP status={obs_obj.status}): "
                            f"{obs_obj.evidence}"
                        ),
                    )

                    if (
                        is_new_weather_day
                        and weather_data.get("suitableForOutdoor") is False
                    ):
                        record_stage(
                            "4",
                            "DETECT",
                            "completed",
                            (
                                f"Detected unsuitable outdoor weather "
                                f"on Day {weather_day}: "
                                f"{weather_data.get('condition')}"
                            ),
                        )

                    # If the itinerary exists, recover immediately.
                    # Otherwise this remains pending until places succeeds.
                    process_pending_weather_recovery()

                else:
                    record_stage(
                        "3",
                        "OBSERVE",
                        "failed",
                        (
                            f"Weather observation was unusable for "
                            f"Day {args.get('day')}: {obs_obj.evidence}"
                        ),
                    )

            elif tool_name == "validation.validateItinerary":

                # A warning can contain useful validation findings.
                # Preserve those findings instead of discarding them.
                validation_res = (
                    obs_obj.data
                    if isinstance(obs_obj.data, dict)
                    else {}
                )

                record_stage(
                    "6",
                    "VERIFY",
                    (
                        "completed"
                        if validation_res.get("valid") is True
                        else "warning"
                    ),
                    (
                        "Validation observation received. "
                        f"Valid={validation_res.get('valid')}"
                    ),
                )

        # ---------------------------------------------------------
        # AUTHORITATIVE FINAL VALIDATION
        # Always execute this, including when the itinerary is empty.
        # ---------------------------------------------------------

        # One final safety attempt: if a disruption is pending and an
        # itinerary exists, process it before authoritative validation.
        process_pending_weather_recovery()

        final_itinerary_hash_before = self._canonical_hash(
            current_itinerary
        )

        final_request_hash_before = self._canonical_hash(req_dict)

        try:
            obs_val = self.mcp.invoke_tool(
                tool_name="validation.validateItinerary",
                arguments={
                    "itinerary": current_itinerary,
                    "budget_inr": req_obj.budget,
                    "interests": req_obj.interests,
                    "weather_conditions": weather_conditions,
                    "request_context": {
                        **req_dict,
                        "request_sha256": request_hash,
                    },
                },
                provider=provider,
            )

            obs_val_dict = obs_val.model_dump()
            observations.append(obs_val_dict)
            tools_executed.append("validation.validateItinerary")

            final_validation_executed = (
                obs_val.status in ("success", "warning")
            )

            # Preserve data for warning observations as well.
            validation_res = (
                obs_val.data
                if isinstance(obs_val.data, dict)
                else {}
            )

            final_validation_succeeded = (
                final_validation_executed
                and validation_res.get("valid") is True
            )

            record_stage(
                "6",
                "VERIFY",
                (
                    "completed"
                    if final_validation_succeeded
                    else "warning"
                ),
                (
                    "Final validation executed. "
                    f"Tool status={obs_val.status}; "
                    f"valid={validation_res.get('valid')}"
                ),
            )

        except Exception as exc:
            logger.exception("Final itinerary validation failed.")

            observations.append({
                "tool": "validation.validateItinerary",
                "status": "error",
                "evidence": str(exc),
                "data": {},
            })

            tools_executed.append("validation.validateItinerary")
            validation_res = {}
            final_validation_executed = False
            final_validation_succeeded = False

            record_stage(
                "6",
                "VERIFY",
                "failed",
                f"Final validation failed: {exc}",
            )

        # Compare the exact itinerary and request before and after validation.
        final_itinerary_hash_after = self._canonical_hash(
            current_itinerary
        )

        final_request_hash_after = self._canonical_hash(req_dict)

        validation_matches_final_itinerary = (
            final_itinerary_hash_before == final_itinerary_hash_after
            and validation_res.get("itinerarySha256")
            == final_itinerary_hash_before
        )

        validation_matches_request = (
            final_request_hash_before == final_request_hash_after
            and final_request_hash_before == request_hash
        )

        # Confirm that the validator checked the same original request.
        request_context_valid = (
            validation_res.get("requestContextValid") is True
            and validation_res.get("requestSha256") == request_hash
        )

        # ---------------------------------------------------------
        # EVIDENCE-BASED REFLECTION
        # ---------------------------------------------------------

        reflection_res = self.reflection_engine.reflect_and_explain(
            validation_res=validation_res,
            recovery_info=recovery_info,
            observations=observations,
            destination=req_obj.destination,
            user_budget=req_obj.budget,
            user_interests=req_obj.interests,
        )

        checked_days = self._get_checked_weather_days(observations)

        weather_coverage_complete = all(
            day in checked_days
            for day in range(1, req_obj.days + 1)
        )

        itinerary_complete = self._itinerary_has_all_days(
            current_itinerary,
            req_obj.days,
        )

        weather_conflict_remaining = self._has_weather_conflict(
            current_itinerary,
            weather_conditions,
        )

        recovery_status = recovery_info.get("status", "not_needed")
        recovery_incomplete = recovery_status in ("partial", "failed")

        validation_passed = (
            final_validation_executed
            and final_validation_succeeded
            and validation_res.get("valid") is True
            and request_context_valid
            and validation_matches_request
            and validation_matches_final_itinerary
        )

        budget_validation_passed = (
            validation_res.get("budgetValid") is True
        )

        weather_validation_passed = (
            validation_res.get("weatherValid") is True
        )

        time_feasibility_confirmed = (
            validation_res.get("timeValid") is True
        )

        preferences_confirmed = (
            validation_res.get("preferencesValid") is True
        )

        availability_confirmed = (
            validation_res.get("availabilityValid") is True
        )

        verification_checks = {
            "finalValidationExecuted": final_validation_executed,
            "finalValidationSucceeded": final_validation_succeeded,
            "validationPassed": validation_passed,
            "validationMatchesFinalItinerary": (
                validation_matches_final_itinerary
            ),
            "validationMatchesRequest": validation_matches_request,
            "requestContextValid": request_context_valid,
            "budgetValidationPassed": budget_validation_passed,
            "weatherValidationPassed": weather_validation_passed,
            "weatherCoverageComplete": weather_coverage_complete,
            "itineraryComplete": itinerary_complete,
            "timeFeasibilityConfirmed": time_feasibility_confirmed,
            "preferencesConfirmed": preferences_confirmed,
            "availabilityConfirmed": availability_confirmed,
            "noWeatherConflictRemaining": not weather_conflict_remaining,
            "recoveryComplete": not recovery_incomplete,
        }

        final_validation_passed = (
            all(verification_checks.values())
            and policy_finished_successfully
            and termination_reason not in ("invalid_action", "tool_execution_failure", "iteration_limit", "exception")
        )

        final_status = (
            "verified"
            if final_validation_passed
            else "unverified"
        )

        if termination_reason is None:
            if policy_finished_successfully:
                if final_status == "verified":
                    if finish_source == "policy":
                        termination_reason = "policy_finish"
                    elif finish_source == "orchestrator":
                        termination_reason = "orchestrator_completion"
                    else:
                        termination_reason = "safety_termination"
                else:
                    termination_reason = "final_validation_failure"
            else:
                termination_reason = "iteration_limit"

        failed_checks = [
            name
            for name, passed in verification_checks.items()
            if not passed
        ]

        if final_status == "verified":
            if termination_reason == "policy_finish":
                final_status_reason = "All required verification checks passed."
            elif termination_reason == "orchestrator_completion":
                final_status_reason = (
                    "All required verification checks passed following deterministic orchestrator completion."
                )
            elif termination_reason == "safety_termination":
                final_status_reason = (
                    "All required verification checks passed following safety-directed completion."
                )
            else:
                final_status_reason = "All required verification checks passed."
        elif termination_reason == "invalid_action":
            final_status_reason = (
                "Planning terminated early due to invalid action schema "
                "or strict Ollama requirement failure."
            )
        elif termination_reason == "iteration_limit":
            final_status_reason = (
                f"Planning terminated because iteration limit "
                f"({max_iterations}) was reached without finishing."
            )
        elif termination_reason == "tool_execution_failure":
            final_status_reason = (
                "Planning terminated early due to fatal tool execution failure."
            )
        elif termination_reason == "safety_termination":
            final_status_reason = (
                "Planning terminated early due to safety intervention."
            )
        elif termination_reason == "exception":
            final_status_reason = (
                "Planning terminated early due to an unhandled runtime exception."
            )
        elif failed_checks:
            final_status_reason = (
                f"Verification incomplete ({termination_reason}). Failed checks: "
                + ", ".join(failed_checks)
            )
        else:
            final_status_reason = f"Verification incomplete: {termination_reason}."

        decision_summary = {
            "ollamaCalled": ollama_attempt_count > 0,
            "ollamaAttemptCount": ollama_attempt_count,
            "ollamaSuccessfulRequestsCount": ollama_successful_requests_count,
            "ollamaAcceptedDecisionsCount": ollama_accepted_decisions_count,
            "ollamaDecisionsCount": ollama_accepted_decisions_count,
            "fallbackDecisionsCount": fallback_decisions_count,
            "safetyOverridesCount": safety_overrides_count,
            "configuredModel": self.policy.model_name,
            "effectiveTimeoutSeconds": self.policy.request_timeout,
            "requireOllamaForDemo": self.policy.require_ollama_for_demo,
            "totalIterations": iteration,
            "terminationReason": termination_reason,
        }

        record_stage(
            "7",
            "FINAL PLAN",
            "completed" if final_status == "verified" else "warning",
            final_status_reason,
        )

        # ---------------------------------------------------------
        # METRICS
        # ---------------------------------------------------------

        total_activities = sum(
            1
            for day in current_itinerary
            if isinstance(day, dict)
            for slot in ITINERARY_SLOTS
            if isinstance(day.get(slot), dict)
        )

        total_cost = self._valid_number(
            validation_res.get("calculatedTotalCost")
        )

        remaining_budget = (
            round(req_obj.budget - total_cost, 2)
            if total_cost is not None
            else None
        )

        activity_travel_times = []
        travel_time_complete = True

        for day in current_itinerary:
            if not isinstance(day, dict):
                travel_time_complete = False
                continue

            for slot in ITINERARY_SLOTS:
                activity = day.get(slot)

                if not isinstance(activity, dict):
                    travel_time_complete = False
                    continue

                travel_time = self._valid_number(
                    activity.get("travel_time_mins")
                )

                if travel_time is None:
                    travel_time_complete = False
                else:
                    activity_travel_times.append(travel_time)

        total_travel_mins = (
            int(sum(activity_travel_times))
            if travel_time_complete
            and len(activity_travel_times) == total_activities
            else None
        )

        formatted_travel_time = (
            f"{total_travel_mins // 60}h "
            f"{total_travel_mins % 60}m"
            if total_travel_mins is not None
            else None
        )

        ordered_tools = self._ordered_unique(tools_executed)

        final_payload = {
            "session_id": session_id,
            "request": req_dict,
            "status": final_status,
            "final_status_reason": final_status_reason,
            "termination_reason": termination_reason,
            "decision_summary": decision_summary,
            "verification_checks": verification_checks,
            "itinerary": current_itinerary,
            "metrics": {
                "totalCost": (
                    round(total_cost, 2)
                    if total_cost is not None
                    else None
                ),
                "remainingBudget": remaining_budget,
                "totalTravelTimeMinutes": total_travel_mins,
                "totalTravelTimeFormatted": formatted_travel_time,
                "activityCount": total_activities,
                "iterationsUsed": iteration,
                "maxIterations": max_iterations,
            },
            "validation": validation_res,
            "recovery": recovery_info,
            "reflection": reflection_res,
            "explanation": reflection_res.get(
                "summary_explanation",
                "",
            ),
            "stages": stages_log,
            "evidence": observations,
            "technicalDetails": {
                "toolsExecuted": ordered_tools,
                "providerUsed": provider.provider_name,
                "isDemoMode": req_obj.demo_mode,
                "iterationCount": iteration,
                "llmModel": self.policy.model_name,
                "terminationReason": termination_reason,
                "decisionSummary": decision_summary,
                "ollamaTimeoutSeconds": self.policy.request_timeout,
                "effectiveTimeoutSeconds": self.policy.request_timeout,
                "requireOllamaForDemo": self.policy.require_ollama_for_demo,
                "ollamaCalled": ollama_attempt_count > 0,
                "ollamaAttemptCount": ollama_attempt_count,
                "ollamaSuccessfulRequestsCount": ollama_successful_requests_count,
                "ollamaAcceptedDecisionsCount": ollama_accepted_decisions_count,
                "ollamaDecisionsCount": ollama_accepted_decisions_count,
                "fallbackDecisionsCount": fallback_decisions_count,
                "safetyOverridesCount": safety_overrides_count,
                "weatherCoverageComplete": weather_coverage_complete,
                "checkedWeatherDays": sorted(checked_days),
                "requestSha256": request_hash,
                "validatedItinerarySha256": final_itinerary_hash_before,
                "finalItinerarySha256": final_itinerary_hash_after,
                "validationMatchesFinalItinerary": (
                    validation_matches_final_itinerary
                ),
                "validationMatchesRequest": validation_matches_request,
                "requestContextValid": request_context_valid,
                "validationRequestSha256": validation_res.get(
                    "requestSha256"
                ),
                "finalValidationExecuted": final_validation_executed,
                "processedRecoveryDays": sorted(
                    processed_recovery_days
                ),
            },
        }

        # ---------------------------------------------------------
        # DURABLE EXECUTION TRACE
        # ---------------------------------------------------------

        try:
            safe_dest = "".join(
                c
                for c in req_obj.destination
                if c.isalnum() or c in ("_", "-")
            ).lower()

            trace_filename = (
                f"trace_{session_id}_{safe_dest}.json"
            )

            trace_filepath = os.path.join(
                self.trace_dir,
                trace_filename,
            )

            trace_data = {
                "session_id": session_id,
                "created_at": start_time,
                "completed_at": datetime.datetime.now().isoformat(),
                "termination_reason": termination_reason,
                "decision_summary": decision_summary,
                "request": req_dict,
                "request_sha256": request_hash,
                "iteration_steps": iteration_steps,
                "observations": observations,
                "stages": stages_log,
                "recovery": recovery_info,
                "reflection": reflection_res,
                "final_status": final_status,
                "final_status_reason": final_status_reason,
                "verification_checks": verification_checks,
                "validation": validation_res,
                "final_validation_executed": final_validation_executed,
                "validated_itinerary_sha256": final_itinerary_hash_before,
                "final_itinerary_sha256": final_itinerary_hash_after,
                "validation_matches_final_itinerary": (
                    validation_matches_final_itinerary
                ),
                "validation_matches_request": validation_matches_request,
                "request_context_valid": request_context_valid,
                "validation_request_sha256": validation_res.get(
                    "requestSha256"
                ),
                "weather_coverage_complete": weather_coverage_complete,
                "checked_weather_days": sorted(checked_days),
                "processed_recovery_days": sorted(
                    processed_recovery_days
                ),
            }

            with open(
                trace_filepath,
                "w",
                encoding="utf-8",
            ) as tf:
                json.dump(
                    trace_data,
                    tf,
                    indent=2,
                    ensure_ascii=False,
                )

            final_payload["trace_file"] = trace_filepath

        except Exception as te:
            logger.warning(
                "Failed to save trace file: %s",
                te,
            )

        return final_payload
