
"""
Travel Agent Orchestrator for Resilient Horizon Travel Engine.

Executes dynamic LLM policy decisions across the MCP Tool Boundary.
Ensures complete per-day weather coverage before finishing.
Handles disruptions, validates the final itinerary, and saves durable traces.
"""

from typing import Any, Dict, List, Optional
import datetime
import os
import json
import uuid
import logging
import math

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
    def _get_checked_weather_days(
        observations: List[Dict[str, Any]],
    ) -> set:
        """Return days with successful or warning weather observations."""

        checked_days = set()

        for obs in observations:
            if (
                obs.get("tool") == "weather.getForecast"
                and obs.get("status") in ("success", "warning")
            ):
                data = obs.get("data") or {}
                day = data.get("day")

                try:
                    if day is not None:
                        checked_days.add(int(day))
                except (TypeError, ValueError):
                    logger.warning(
                        "Ignoring invalid weather day value: %s",
                        day,
                    )

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
            if weather.get("suitableForOutdoor", True) is False:
                try:
                    unsuitable_days.add(int(weather.get("day")))
                except (TypeError, ValueError):
                    continue

        for day_item in itinerary:
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
        """Check that the itinerary contains every requested day."""

        present_days = set()

        for item in itinerary:
            try:
                present_days.add(int(item.get("day")))
            except (TypeError, ValueError):
                continue

        return all(
            day in present_days
            for day in range(1, requested_days + 1)
        )

    @staticmethod
    def _ordered_unique(values: List[str]) -> List[str]:
        """Remove duplicates without changing execution order."""
        return list(dict.fromkeys(values))

    def run(
        self,
        destination: str,
        days: int = 4,
        budget: float = 15000.0,
        interests: List[str] = None,
        travel_date: Optional[str] = None,
        demo_mode: bool = True,
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
            "reason": "No weather disruption has been processed.",
            "affectedDay": None,
            "affectedSlots": [],
            "failedSlots": [],
            "originalActivities": [],
            "replacementActivities": [],
        }

        validation_res: Dict[str, Any] = {}
        weather_conditions: List[Dict[str, Any]] = []
        final_validation_succeeded = False

        mcp_catalog = self.mcp.list_mcp_tools()

        # Dynamic agent loop:
        # DECIDE -> VALIDATE -> ACT -> OBSERVE -> REPEAT

        while iteration < max_iterations:

            iteration += 1

            val_action: ValidatedAction = (
                self.policy.decide_next_action(
                    request=req_dict,
                    iteration=iteration,
                    max_iterations=max_iterations,
                    current_itinerary=current_itinerary,
                    observations=observations,
                    mcp_tools=mcp_catalog,
                    validation_res=validation_res,
                )
            )

            act_obj = val_action.action

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
                    act_obj = AgentAction(
                        action="tool",
                        tool_name="places.searchAttractions",
                        arguments={
                            "destination": req_obj.destination,
                            "interests": req_obj.interests,
                        },
                        reasoning=(
                            "Completion blocked because an itinerary "
                            "has not yet been created."
                        ),
                    )

                    val_action = ValidatedAction(
                        is_valid=True,
                        action=act_obj,
                        errors=[],
                    )

                elif missing_days:
                    next_day = missing_days[0]

                    act_obj = AgentAction(
                        action="tool",
                        tool_name="weather.getForecast",
                        arguments={
                            "destination": req_obj.destination,
                            "day": next_day,
                        },
                        reasoning=(
                            f"Completion blocked because weather "
                            f"evidence for Day {next_day} is missing."
                        ),
                    )

                    val_action = ValidatedAction(
                        is_valid=True,
                        action=act_obj,
                        errors=[],
                    )

            # Do not spend iterations repeating weather checks
            # after all requested days have been covered.
            if (
                val_action.is_valid
                and act_obj.action == "tool"
                and act_obj.tool_name == "weather.getForecast"
                and not missing_days
            ):
                act_obj = AgentAction(
                    action="finish",
                    reasoning=(
                        "Weather coverage is complete. "
                        "Proceeding to final itinerary validation."
                    ),
                )

                val_action = ValidatedAction(
                    is_valid=True,
                    action=act_obj,
                    errors=[],
                )

            step_record = {
                "iteration": iteration,
                "reasoning": act_obj.reasoning,
                "action": act_obj.action,
                "tool_name": act_obj.tool_name,
                "arguments": act_obj.arguments,
                "is_valid": val_action.is_valid,
                "validation_errors": val_action.errors,
            }

            if not val_action.is_valid:
                step_record["status"] = "invalid_action"
                iteration_steps.append(step_record)

                logger.warning(
                    "Invalid agent action at iteration %s: %s",
                    iteration,
                    val_action.errors,
                )
                break

            if act_obj.action == "finish":
                step_record["status"] = "finished"
                iteration_steps.append(step_record)
                break

            tool_name = act_obj.tool_name
            args = dict(act_obj.arguments or {})

            # Supply request defaults without overriding
            # explicitly provided valid arguments unnecessarily.

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

                # The application is authoritative for travel dates.
                # Never allow an LLM-generated date to override the request.
                # An empty date tells the provider to use its flexible forecast.
                args["date"] = (req_obj.travel_date or "").strip()

            elif tool_name == "route.estimateTravel":
                args.setdefault(
                    "origin",
                    f"Hotel in {req_obj.destination}",
                )
                args.setdefault(
                    "destination",
                    f"Central {req_obj.destination}",
                )

            elif tool_name == "availability.checkStatus":
                args.setdefault(
                    "attraction_name",
                    f"Main Landmark in {req_obj.destination}",
                )

            elif tool_name == "cost.calculateEstimate":
                args.setdefault(
                    "activities",
                    [
                        day.get("morning", {})
                        for day in current_itinerary
                        if day.get("morning")
                    ],
                )

            elif tool_name == "validation.validateItinerary":
                args.setdefault("itinerary", current_itinerary)
                args.setdefault("budget_inr", req_obj.budget)
                args.setdefault("interests", req_obj.interests)
                args.setdefault("weather_conditions", weather_conditions)

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
                step_record["status"] = "tool_error"

                observations.append(obs_dict)
                tools_executed.append(tool_name)
                iteration_steps.append(step_record)
                continue

            tools_executed.append(tool_name)
            observations.append(obs_dict)

            step_record["observation"] = obs_dict
            step_record["status"] = (
                "completed"
                if obs_obj.status in ("success", "warning")
                else "tool_error"
            )
            iteration_steps.append(step_record)

            # Update internal state from observations.

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

            elif tool_name == "weather.getForecast":

                if obs_obj.status in ("success", "warning"):

                    record_stage(
                        "3",
                        "OBSERVE",
                        "completed",
                        (
                            "Collected weather observation: "
                            f"{obs_obj.evidence}"
                        ),
                    )

                    weather_day = obs_obj.data.get("day")

                    existing_days = set()
                    for item in weather_conditions:
                        try:
                            existing_days.add(int(item.get("day")))
                        except (TypeError, ValueError):
                            continue

                    try:
                        weather_day_number = int(weather_day)
                    except (TypeError, ValueError):
                        weather_day_number = None

                    if (
                        weather_day_number is not None
                        and weather_day_number not in existing_days
                    ):
                        weather_conditions.append(obs_obj.data)

                    if (
                        obs_obj.data.get("suitableForOutdoor")
                        is False
                    ):
                        record_stage(
                            "4",
                            "DETECT",
                            "completed",
                            (
                                f"Detected unsuitable outdoor weather "
                                f"on Day {weather_day}: "
                                f"{obs_obj.data.get('condition')}"
                            ),
                        )

                        record_stage(
                            "5",
                            "RECOVER",
                            "running",
                            "Attempting evidence-based disruption recovery.",
                        )

                        (
                            current_itinerary,
                            recovery_info,
                        ) = self.recovery_engine.detect_and_recover(
                            itinerary=current_itinerary,
                            weather_observations=weather_conditions,
                            provider=provider,
                            user_interests=req_obj.interests,
                            mcp_boundary=self.mcp,
                            observations=observations,
                        )

                        record_stage(
                            "5",
                            "RECOVER",
                            (
                                "completed"
                                if recovery_info.get("verified")
                                else "warning"
                            ),
                            (
                                "Recovery result: "
                                f"{recovery_info.get('reason')}"
                            ),
                        )

                else:
                    record_stage(
                        "3",
                        "OBSERVE",
                        "failed",
                        (
                            f"Weather observation failed for Day "
                            f"{args.get('day')}: {obs_obj.evidence}"
                        ),
                    )

            elif tool_name == "validation.validateItinerary":

                if obs_obj.status == "success":
                    validation_res = obs_obj.data or {}
                else:
                    validation_res = {}

                record_stage(
                    "6",
                    "VERIFY",
                    (
                        "completed"
                        if obs_obj.status == "success"
                        else "failed"
                    ),
                    (
                        "Validation observation received. "
                        f"Valid={validation_res.get('valid')}"
                    ),
                )

        # Final validation is always run against the latest itinerary.
        # Errors must not be mistaken for successful validation.

        if current_itinerary:
            try:
                obs_val = self.mcp.invoke_tool(
                    tool_name="validation.validateItinerary",
                    arguments={
                        "itinerary": current_itinerary,
                        "budget_inr": req_obj.budget,
                        "interests": req_obj.interests,
                        "weather_conditions": weather_conditions,
                    },
                    provider=provider,
                )

                observations.append(obs_val.model_dump())
                tools_executed.append("validation.validateItinerary")

                final_validation_succeeded = (
                    obs_val.status == "success"
                )

                validation_res = (
                    obs_val.data or {}
                    if final_validation_succeeded
                    else {}
                )

                record_stage(
                    "6",
                    "VERIFY",
                    (
                        "completed"
                        if final_validation_succeeded
                        else "failed"
                    ),
                    (
                        "Final validation result: "
                        f"{validation_res.get('valid')}"
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
                final_validation_succeeded = False

                record_stage(
                    "6",
                    "VERIFY",
                    "failed",
                    f"Final validation failed: {exc}",
                )

        # Evidence-based reflection.

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
            final_validation_succeeded
            and validation_res.get("valid") is True
        )

        budget_validation_passed = (
            validation_res.get("budgetValid") is True
        )

        weather_validation_passed = (
            validation_res.get("weatherValid") is True
        )

        verification_checks = {
            "finalValidationSucceeded": final_validation_succeeded,
            "validationPassed": validation_passed,
            "budgetValidationPassed": budget_validation_passed,
            "weatherValidationPassed": weather_validation_passed,
            "weatherCoverageComplete": weather_coverage_complete,
            "itineraryComplete": itinerary_complete,
            "noWeatherConflictRemaining": not weather_conflict_remaining,
            "recoveryComplete": not recovery_incomplete,
        }

        final_status = (
            "verified"
            if all(verification_checks.values())
            else "unverified"
        )

        failed_checks = [
            name
            for name, passed in verification_checks.items()
            if not passed
        ]

        final_status_reason = (
            "All required verification checks passed."
            if final_status == "verified"
            else (
                "Verification incomplete. Failed checks: "
                + ", ".join(failed_checks)
            )
        )

        record_stage(
            "7",
            "FINAL PLAN",
            "completed" if final_status == "verified" else "warning",
            final_status_reason,
        )

        # Calculate metrics only from available evidence.
        total_activities = sum(
            1
            for day in current_itinerary
            for slot in ITINERARY_SLOTS
            if day.get(slot)
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
            for slot in ITINERARY_SLOTS:
                activity = day.get(slot)

                if not activity:
                    continue

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
                "weatherCoverageComplete": weather_coverage_complete,
                "checkedWeatherDays": sorted(checked_days),
            },
        }

        # Save a durable execution trace.

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
                "request": req_dict,
                "iteration_steps": iteration_steps,
                "observations": observations,
                "stages": stages_log,
                "recovery": recovery_info,
                "reflection": reflection_res,
                "final_status": final_status,
                "final_status_reason": final_status_reason,
                "verification_checks": verification_checks,
                "validation": validation_res,
                "weather_coverage_complete": weather_coverage_complete,
                "checked_weather_days": sorted(checked_days),
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
