
"""
Evidence-Based Reflection Module for Resilient Horizon Travel Engine.

Audits tool observations and validation results independently.
Warnings and errors are never treated as proof that a check passed.
Availability is not considered confirmed merely because a tool responded.
"""

from typing import Any, Dict, List, Optional


class AgentReflection:

    @staticmethod
    def _successful_observation(obs: Dict[str, Any]) -> bool:
        return obs.get("status") == "success"

    @staticmethod
    def _format_money(value: Any) -> str:
        try:
            amount = float(value)
            return f"INR {amount:,.2f}"
        except (TypeError, ValueError):
            return "an unknown amount"

    def reflect_and_explain(
        self,
        validation_res: Dict[str, Any],
        recovery_info: Dict[str, Any],
        observations: List[Dict[str, Any]],
        destination: str,
        user_budget: float,
        user_interests: List[str],
        itinerary: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:

        evidence_citations = []
        failed_observations = []
        warning_observations = []
        weather_warnings = []
        successful_weather_days = set()

        successful_places = False
        successful_routes = False
        cost_evidence_found = False

        availability_observation_found = False
        availability_successful_call = False
        availability_open = False
        availability_closed = False
        availability_missing_status = False
        availability_is_simulated = False
        availability_confirmed = False

        for idx, obs in enumerate(observations, 1):

            tool = str(obs.get("tool", "unknown"))
            status = str(obs.get("status", "unknown"))
            evidence = str(obs.get("evidence", ""))
            data = obs.get("data") or {}

            if not isinstance(data, dict):
                data = {}

            safe_tool_name = (
                tool.replace(".", "_").replace("/", "_")
            )
            obs_id = f"ev_{idx:03d}_{safe_tool_name}"

            if status == "warning":
                warning_observations.append({
                    "id": obs_id,
                    "tool": tool,
                    "status": status,
                    "evidence": evidence,
                })

                if tool == "weather.getForecast":
                    weather_warnings.append({
                        "evidence_id": obs_id,
                        "description": evidence,
                        "condition": data.get(
                            "condition",
                            "Weather result requires attention",
                        ),
                    })

                elif tool == "availability.checkStatus":
                    availability_observation_found = True
                    is_open_val = data.get("is_open") if "is_open" in data else data.get("available")
                    if is_open_val is False:
                        availability_closed = True
                    elif not isinstance(is_open_val, bool):
                        availability_missing_status = True

                continue

            if status != "success":
                failed_observations.append({
                    "id": obs_id,
                    "tool": tool,
                    "status": status,
                    "evidence": evidence,
                })

                if tool == "availability.checkStatus":
                    availability_observation_found = True

                continue

            # A successful tool response is evidence of execution,
            # not automatic proof that every business constraint passed.
            evidence_citations.append(obs_id)

            if tool == "weather.getForecast":

                day = data.get("day")
                condition = data.get("condition")
                suitable = data.get("suitableForOutdoor")

                try:
                    day_number = int(day)
                except (TypeError, ValueError):
                    day_number = None

                if (
                    day_number is not None
                    and isinstance(condition, str)
                    and condition.strip()
                    and isinstance(suitable, bool)
                ):
                    successful_weather_days.add(day_number)

                if suitable is False:
                    weather_warnings.append({
                        "evidence_id": obs_id,
                        "description": evidence,
                        "condition": condition or "Unsuitable weather",
                    })

            elif tool == "places.searchAttractions":
                attractions = data.get("attractions", [])
                if isinstance(attractions, list) and attractions:
                    successful_places = True

            elif tool == "route.estimateTravel":
                travel_time = data.get("travel_time_mins")
                if travel_time is not None:
                    successful_routes = True

            elif tool == "cost.calculateEstimate":
                if (
                    data.get("estimated_cost_inr") is not None
                    or data.get("total_cost_inr") is not None
                    or data.get("calculatedTotalCost") is not None
                ):
                    cost_evidence_found = True

            elif tool == "validation.validateItinerary":
                if data.get("calculatedTotalCost") is not None:
                    cost_evidence_found = True

            elif tool == "availability.checkStatus":
                availability_observation_found = True
                availability_successful_call = True

                is_open_val = data.get("is_open") if "is_open" in data else data.get("available")

                if not isinstance(is_open_val, bool):
                    availability_missing_status = True
                elif is_open_val is False:
                    availability_closed = True
                else:
                    availability_open = True
                    source_str = (
                        str(data.get("source", ""))
                        + " "
                        + str(evidence)
                        + " "
                        + str(data.get("evidence", ""))
                    ).lower()

                    is_sim = (
                        "simulated" in source_str
                        or "demo" in source_str
                        or "mock" in source_str
                        or "not confirmed with the attraction" in source_str
                        or not bool(str(data.get("source", "")).strip())
                    )

                    if is_sim:
                        availability_is_simulated = True
                        availability_confirmed = False
                    else:
                        availability_is_simulated = False
                        availability_confirmed = True

        # Inspect final validation independently.
        is_valid = validation_res.get("valid") is True
        budget_valid = validation_res.get("budgetValid") is True
        weather_valid = validation_res.get("weatherValid") is True

        time_valid = validation_res.get("timeValid") is True
        preferences_valid = (
            validation_res.get("preferencesValid") is True
        )
        availability_valid = (
            validation_res.get("availabilityValid") is True
            and not availability_closed
        )

        calculated_cost = validation_res.get(
            "calculatedTotalCost"
        )

        if calculated_cost is not None:
            cost_evidence_found = True

        issues = validation_res.get("issues", [])
        if not isinstance(issues, list):
            issues = [str(issues)]

        # Collect replacement activities to audit recovery evidence
        replacement_activities_to_audit: List[Dict[str, Any]] = []

        if itinerary and isinstance(itinerary, list):
            for day_item in itinerary:
                if isinstance(day_item, dict):
                    for slot_name in ("morning", "afternoon", "evening"):
                        act = day_item.get(slot_name)
                        if isinstance(act, dict) and (
                            act.get("was_recovered") is True
                            or "recovery_evidence" in act
                        ):
                            replacement_activities_to_audit.append(act)

        for detail in (
            recovery_info.get("replacementDetails", [])
            + recovery_info.get("replacements", [])
        ):
            if isinstance(detail, dict) and detail not in replacement_activities_to_audit:
                replacement_activities_to_audit.append(detail)

        for act in recovery_info.get("replacementActivities", []):
            if isinstance(act, dict) and act not in replacement_activities_to_audit:
                replacement_activities_to_audit.append(act)

        replacements = recovery_info.get(
            "replacementActivities",
            [],
        )
        if not replacements and replacement_activities_to_audit:
            replacements = [
                act.get("activity") or act.get("name") or "Replacement Activity"
                for act in replacement_activities_to_audit
            ]

        recovery_needed = bool(
            weather_warnings
            or recovery_info.get("occurred")
            or replacements
            or replacement_activities_to_audit
        )

        recovery_budget_verified = False
        fully_verified_recovery = False
        if recovery_needed:
            if replacement_activities_to_audit:
                all_rep_budgets_verified = True
                for rep_act in replacement_activities_to_audit:
                    rec_ev = rep_act.get("recovery_evidence")
                    if (
                        not isinstance(rec_ev, dict)
                        or rec_ev.get("budget_feasibility_verified") is not True
                    ):
                        all_rep_budgets_verified = False
                        break
                recovery_budget_verified = all_rep_budgets_verified
            else:
                recovery_budget_verified = (
                    recovery_info.get("budgetFeasibilityVerified") is True
                )

            if recovery_info.get("budgetFeasibilityVerified") is False:
                recovery_budget_verified = False

        explanation_parts = []

        if recovery_needed:
            affected_day = recovery_info.get("affectedDay")

            has_places_ev = successful_places or any(
                isinstance(act.get("recovery_evidence"), dict) and "places_tool" in act["recovery_evidence"]
                for act in replacement_activities_to_audit
            )
            has_route_ev = successful_routes or any(
                isinstance(act.get("recovery_evidence"), dict) and "route_tool" in act["recovery_evidence"]
                for act in replacement_activities_to_audit
            )

            # Fully verified recovery requires:
            # 1. recovery_info verified is True
            # 2. replacements exist
            # 3. places and route evidence confirmed
            # 4. recovery_budget_verified is True (does not rely only on recovery_info["verified"])
            fully_verified_recovery = (
                recovery_info.get("verified") is True
                and bool(replacements)
                and has_places_ev
                and has_route_ev
                and recovery_budget_verified
            )

            if replacements and (has_places_ev or has_route_ev):
                replacement_names = ", ".join(
                    dict.fromkeys(
                        item.get("activity") or item.get("name") if isinstance(item, dict) else str(item)
                        for item in replacements
                    )
                )

                if fully_verified_recovery:
                    explanation_parts.append(
                        f"Weather disruption was detected during the "
                        f"trip to {destination}. Recovery recorded "
                        f"replacement activities: {replacement_names}."
                    )
                    if affected_day is not None:
                        explanation_parts.append(
                            f" The first affected day was Day {affected_day}."
                        )
                else:
                    explanation_parts.append(
                        f"Weather disruption was detected during the trip to {destination}. "
                        f"Recovery recorded replacement activities: {replacement_names}, "
                        f"but budget feasibility was not established."
                    )
                    if affected_day is not None:
                        explanation_parts.append(
                            f" The first affected day was Day {affected_day}."
                        )
            else:
                explanation_parts.append(
                    f"Unsuitable weather was reported for {destination}. "
                    "Complete replacement evidence was not established."
                )
        else:
            explanation_parts.append(
                f"Valid weather observations were recorded for "
                f"{len(successful_weather_days)} distinct trip day(s) "
                f"at {destination}."
            )

        if calculated_cost is not None:
            explanation_parts.append(
                f" Final validation calculated a cost of "
                f"{self._format_money(calculated_cost)} against the "
                f"requested budget of {self._format_money(user_budget)}."
            )
        else:
            explanation_parts.append(
                " A final calculated trip cost was not available."
            )

        explanation_parts.append(
            " Budget constraint: "
            + ("passed." if budget_valid else "not confirmed as passed.")
        )

        explanation_parts.append(
            " Weather constraint: "
            + ("passed." if weather_valid else "not confirmed as passed.")
        )

        explanation_parts.append(
            " Time feasibility: "
            + ("passed." if time_valid else "not established.")
        )

        explanation_parts.append(
            " Preference matching: "
            + (
                "passed."
                if preferences_valid
                else "not established."
            )
        )

        if availability_confirmed:
            explanation_parts.append(
                " Availability was independently confirmed by real-world provider evidence."
            )
        elif availability_open and availability_is_simulated:
            explanation_parts.append(
                " Attraction operating status check reported open via simulated provider data, but real-world booking or ticketing has not been independently confirmed."
            )
        elif availability_closed:
            explanation_parts.append(
                " Attraction availability check reported that the attraction is closed or unavailable."
            )
        elif availability_missing_status:
            explanation_parts.append(
                " An availability observation was recorded, but operating status was missing."
            )
        elif availability_observation_found:
            explanation_parts.append(
                " An availability check was attempted, but did not return a successful observation."
            )
        else:
            explanation_parts.append(
                " No availability observation was recorded."
            )

        if is_valid:
            explanation_parts.append(
                " The final validation tool reported the itinerary "
                "as valid."
            )
        else:
            explanation_parts.append(
                " The itinerary is not confirmed as valid by "
                "the final validation result."
            )

        if warning_observations:
            explanation_parts.append(
                f" {len(warning_observations)} warning observation(s) "
                "were kept separate from successful evidence."
            )

        if failed_observations:
            explanation_parts.append(
                f" {len(failed_observations)} failed observation(s) "
                "were excluded from supporting evidence."
            )

        return {
            "decision": "valid" if is_valid else "unverified",
            "summary_explanation": "".join(explanation_parts),
            "issues": issues,
            "evidence_citations": evidence_citations,
            "warning_observations": warning_observations,
            "failed_observations": failed_observations,
            "audit_checks": {
                "budget_valid": budget_valid,
                "weather_valid": weather_valid,
                "time_valid": time_valid,
                "preferences_valid": preferences_valid,
                "availability_valid": availability_valid,
                "availability_observation_present": availability_observation_found,
                "availability_successful_call": availability_successful_call,
                "availability_open": availability_open,
                "availability_closed": availability_closed,
                "availability_missing_status": availability_missing_status,
                "availability_is_simulated": availability_is_simulated,
                "availability_confirmed": availability_confirmed,
                "cost_evidence_present": cost_evidence_found,
                "weather_warning_count": len(weather_warnings),
                "successful_weather_days": sorted(
                    successful_weather_days
                ),
                "places_evidence_present": successful_places,
                "route_evidence_present": successful_routes,
                "recovery_budget_verified": recovery_budget_verified if recovery_needed else True,
                "recovery_verified": fully_verified_recovery if recovery_needed else True,
                "observations_count": len(observations),
                "warning_observations_count": len(
                    warning_observations
                ),
                "failed_observations_count": len(
                    failed_observations
                ),
            },
        }
