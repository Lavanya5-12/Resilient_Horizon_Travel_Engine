
"""
Evidence-Based Reflection Module for Resilient Horizon Travel Engine.

Audits tool observations and validation results independently.
Only successful tool observations are cited as supporting evidence.
Avoids unsupported claims about weather, cost, availability, and recovery.
"""

from typing import Any, Dict, List


class AgentReflection:

    @staticmethod
    def _successful_observation(obs: Dict[str, Any]) -> bool:
        return obs.get("status") in ("success", "warning")

    @staticmethod
    def _format_money(value: Any) -> str:
        try:
            return f"INR {float(value):,.2f}"
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
    ) -> Dict[str, Any]:

        evidence_citations = []
        failed_observations = []
        weather_warnings = []
        successful_weather_days = set()

        successful_places = False
        successful_routes = False
        cost_evidence_found = False
        availability_evidence_found = False

        # Audit each tool observation independently.
        for idx, obs in enumerate(observations, 1):

            tool = str(obs.get("tool", "unknown"))
            status = obs.get("status", "")
            evidence = str(obs.get("evidence", ""))
            data = obs.get("data") or {}

            safe_tool_name = (
                tool.replace(".", "_")
                .replace("/", "_")
            )

            obs_id = f"ev_{idx:03d}_{safe_tool_name}"

            if not self._successful_observation(obs):
                failed_observations.append({
                    "id": obs_id,
                    "tool": tool,
                    "status": status or "unknown",
                    "evidence": evidence,
                })
                continue

            evidence_citations.append(obs_id)

            if tool == "weather.getForecast":

                try:
                    day = int(data.get("day"))
                    successful_weather_days.add(day)
                except (TypeError, ValueError):
                    pass

                if (
                    status == "warning"
                    or data.get("suitableForOutdoor") is False
                ):
                    weather_warnings.append({
                        "evidence_id": obs_id,
                        "description": evidence,
                        "condition": data.get(
                            "condition",
                            "Unsuitable outdoor conditions",
                        ),
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
                availability_evidence_found = True

        # Independently inspect the final validation result.
        is_valid = validation_res.get("valid") is True
        budget_valid = validation_res.get("budgetValid") is True
        weather_valid = validation_res.get("weatherValid") is True

        calculated_cost = validation_res.get(
            "calculatedTotalCost"
        )

        if calculated_cost is not None:
            cost_evidence_found = True

        issues = validation_res.get("issues", [])

        if not isinstance(issues, list):
            issues = [str(issues)]

        explanation_parts = []

        # Explain weather disruption and recovery conservatively.
        if weather_warnings:

            warning_days = sorted({
                int(item["evidence_id"].split("_")[1])
                for item in []
            })

            warning_descriptions = [
                item["condition"]
                for item in weather_warnings
            ]

            affected_day = recovery_info.get("affectedDay")
            replacements = recovery_info.get(
                "replacementActivities",
                [],
            )

            if (
                recovery_info.get("verified") is True
                and replacements
                and successful_places
                and successful_routes
            ):
                replacement_names = ", ".join(
                    dict.fromkeys(replacements)
                )

                explanation_parts.append(
                    f"Weather disruption was detected during the trip "
                    f"to {destination}. The recovery process obtained "
                    f"indoor place results and route observations through "
                    f"the MCP tools. The recorded replacement activities "
                    f"are: {replacement_names}."
                )

                if affected_day is not None:
                    explanation_parts.append(
                        f" The first recorded affected day was Day "
                        f"{affected_day}."
                    )

            else:
                explanation_parts.append(
                    f"Unsuitable outdoor weather was reported for "
                    f"{destination}. The recovery process did not establish "
                    f"complete verified replacement evidence."
                )

        else:
            explanation_parts.append(
                f"Weather observations were collected for "
                f"{destination} on {len(successful_weather_days)} "
                f"distinct trip day(s)."
            )

        # Report budget only when an actual calculated amount exists.
        if calculated_cost is not None:

            explanation_parts.append(
                f" The itinerary validation reported a calculated "
                f"cost of {self._format_money(calculated_cost)} "
                f"against the requested budget of "
                f"{self._format_money(user_budget)}."
            )

            if budget_valid:
                explanation_parts.append(
                    " The validation result reports that the budget "
                    "constraint passed."
                )
            else:
                explanation_parts.append(
                    " The validation result did not confirm that "
                    "the budget constraint passed."
                )

        else:
            explanation_parts.append(
                " A final calculated trip cost was not available "
                "in the validation evidence."
            )

        # Report weather validation independently.
        if weather_valid:
            explanation_parts.append(
                " The final validation result reports that its "
                "weather constraint passed."
            )
        else:
            explanation_parts.append(
                " The final validation result did not confirm "
                "that its weather constraint passed."
            )

        # Do not claim live availability from a simulated provider.
        if availability_evidence_found:
            explanation_parts.append(
                " An availability tool observation was received; "
                "its result should be interpreted according to the "
                "configured provider and its data source."
            )
        else:
            explanation_parts.append(
                " No successful availability tool observation "
                "was recorded."
            )

        if is_valid:
            explanation_parts.append(
                " The final validation tool reported the itinerary "
                "as valid."
            )
        else:
            explanation_parts.append(
                " The itinerary is not confirmed as valid by the "
                "final validation result."
            )

        if failed_observations:
            explanation_parts.append(
                f" {len(failed_observations)} tool observation(s) "
                f"failed and were excluded from supporting evidence."
            )

        final_explanation = "".join(explanation_parts)

        return {
            "decision": "valid" if is_valid else "unverified",
            "summary_explanation": final_explanation,
            "issues": issues,
            "evidence_citations": evidence_citations,
            "failed_observations": failed_observations,
            "audit_checks": {
                "budget_valid": budget_valid,
                "weather_valid": weather_valid,
                "cost_evidence_present": cost_evidence_found,
                "weather_warning_count": len(weather_warnings),
                "successful_weather_days": sorted(
                    successful_weather_days
                ),
                "places_evidence_present": successful_places,
                "route_evidence_present": successful_routes,
                "availability_observation_present": (
                    availability_evidence_found
                ),
                "observations_count": len(observations),
                "failed_observations_count": len(
                    failed_observations
                ),
            },
        }
