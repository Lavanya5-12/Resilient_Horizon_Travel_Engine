
"""
Evidence-aware Recovery Engine for Resilient Horizon Travel Engine.

Replaces weather-affected outdoor activities only when:
1. The MCP places tool returns an explicitly indoor attraction.
2. The attraction has a name, location, and valid estimated cost.
3. The MCP route tool returns a valid travel-time estimate.

Failed or missing tool evidence never produces invented attractions or routes.
"""

from copy import deepcopy
from math import isfinite
from typing import Any, Dict, List, Optional, Tuple


class RecoveryEngine:
    SLOTS = ("morning", "afternoon", "evening")

    @staticmethod
    def _observation_dict(observation: Any) -> Dict[str, Any]:
        """Convert an MCP observation into a trace-friendly dictionary."""
        if hasattr(observation, "model_dump"):
            return observation.model_dump()

        if isinstance(observation, dict):
            return observation

        return {
            "tool": "unknown",
            "status": "error",
            "data": {},
            "evidence": "Unsupported observation format",
        }

    @staticmethod
    def _valid_number(value: Any) -> Optional[float]:
        """Return a finite non-negative number, otherwise None."""
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None

        if not isfinite(number) or number < 0:
            return None

        return number

    @staticmethod
    def _day_number(value: Any) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def detect_and_recover(
        self,
        itinerary: List[Dict[str, Any]],
        weather_observations: List[Dict[str, Any]],
        provider: Any,
        user_interests: List[str],
        mcp_boundary: Any,
        observations: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:

        trace_observations = observations if observations is not None else []

        recovery_info: Dict[str, Any] = {
            "occurred": False,
            "status": "not_needed",
            "verified": False,
            "reason": "",
            "affectedDay": None,
            "affectedSlots": [],
            "failedSlots": [],
            "originalActivities": [],
            "replacementActivities": [],
            "originalActivity": "",
            "replacementActivity": "",
            "issueDetected": "",
            "impact": "",
            "recoveryAction": "",
            "recalculation": "",
            "verification": "",
        }

        revised_itinerary = deepcopy(itinerary)

        weather_map = {}
        for weather in weather_observations:
            day_number = self._day_number(weather.get("day"))
            if day_number is not None:
                weather_map[day_number] = weather

        replacement_count = 0
        failed_count = 0

        for day_item in revised_itinerary:
            day_num = self._day_number(day_item.get("day"))

            if day_num is None:
                continue

            day_weather = weather_map.get(day_num, {})

            if (
                not day_weather
                or day_weather.get("suitableForOutdoor", True) is not False
            ):
                continue

            target_destination = day_weather.get(
                "destination",
                "",
            )
            condition_name = day_weather.get(
                "condition",
                "unfavorable weather",
            )

            # Do not invent a destination if the weather observation
            # does not identify one.
            if not target_destination:
                target_destination = day_weather.get(
                    "city",
                    "",
                )

            if not target_destination:
                recovery_info["failedSlots"].append(
                    f"Day {day_num}: destination missing from weather evidence"
                )
                failed_count += 1
                continue

            # Search for indoor alternatives through the MCP boundary.
            try:
                places_obs = mcp_boundary.invoke_tool(
                    tool_name="places.searchAttractions",
                    arguments={
                        "destination": target_destination,
                        "interests": user_interests,
                        "indoor_only": True,
                    },
                    provider=provider,
                )

                places_record = self._observation_dict(places_obs)
                trace_observations.append(places_record)

            except Exception as exc:
                places_record = {
                    "tool": "places.searchAttractions",
                    "status": "error",
                    "data": {},
                    "evidence": str(exc),
                }
                trace_observations.append(places_record)

            places_data = places_record.get("data") or {}

            candidates = (
                places_data.get("attractions", [])
                if places_record.get("status") == "success"
                else []
            )

            # Accept only explicitly indoor attractions with usable data.
            verified_candidates = []

            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue

                if candidate.get("is_outdoor") is not False:
                    continue

                name = candidate.get("name")
                location = candidate.get("location")

                cost = self._valid_number(
                    candidate.get(
                        "estimated_cost_inr",
                        candidate.get("cost_inr"),
                    )
                )

                if (
                    not isinstance(name, str)
                    or not name.strip()
                    or not isinstance(location, str)
                    or not location.strip()
                    or cost is None
                ):
                    continue

                verified_candidates.append({
                    **candidate,
                    "name": name.strip(),
                    "location": location.strip(),
                    "estimated_cost_inr": cost,
                })

            candidate_index = 0

            for slot in self.SLOTS:
                activity = day_item.get(slot)

                if (
                    not isinstance(activity, dict)
                    or activity.get("is_outdoor") is not True
                ):
                    continue

                original_name = activity.get(
                    "activity",
                    "Unnamed outdoor activity",
                )

                # No verified indoor alternative remains.
                if candidate_index >= len(verified_candidates):
                    recovery_info["failedSlots"].append(
                        f"Day {day_num} {slot}: no verified indoor alternative available"
                    )
                    failed_count += 1
                    continue

                replacement = verified_candidates[candidate_index]
                candidate_index += 1

                origin = (
                    day_item.get("morning", {}).get("location")
                    if isinstance(day_item.get("morning"), dict)
                    else None
                )

                if not origin:
                    recovery_info["failedSlots"].append(
                        f"Day {day_num} {slot}: route origin is unavailable"
                    )
                    failed_count += 1
                    continue

                # Obtain a route estimate through MCP.
                try:
                    route_obs = mcp_boundary.invoke_tool(
                        tool_name="route.estimateTravel",
                        arguments={
                            "origin": origin,
                            "destination": replacement["location"],
                        },
                        provider=provider,
                    )

                    route_record = self._observation_dict(route_obs)
                    trace_observations.append(route_record)

                except Exception as exc:
                    route_record = {
                        "tool": "route.estimateTravel",
                        "status": "error",
                        "data": {},
                        "evidence": str(exc),
                    }
                    trace_observations.append(route_record)

                route_data = route_record.get("data") or {}

                travel_time = None

                if route_record.get("status") == "success":
                    travel_time = self._valid_number(
                        route_data.get("travel_time_mins")
                    )

                if travel_time is None:
                    recovery_info["failedSlots"].append(
                        f"Day {day_num} {slot}: route estimate could not be verified"
                    )
                    failed_count += 1
                    continue

                replacement_activity = {
                    "activity": replacement["name"],
                    "location": replacement["location"],
                    "cost_inr": replacement["estimated_cost_inr"],
                    "travel_time_mins": int(travel_time),
                    "category": replacement.get(
                        "category",
                        "Unspecified",
                    ),
                    "is_outdoor": False,
                    "was_recovered": True,
                    "original_activity": original_name,
                    "recovery_evidence": {
                        "places_tool": "places.searchAttractions",
                        "route_tool": "route.estimateTravel",
                        "indoor_status_confirmed": True,
                        "route_estimate_confirmed": True,
                    },
                }

                day_item[slot] = replacement_activity

                replacement_count += 1

                recovery_info["occurred"] = True
                recovery_info["affectedSlots"].append(
                    f"Day {day_num} {slot.capitalize()}"
                )
                recovery_info["originalActivities"].append(
                    original_name
                )
                recovery_info["replacementActivities"].append(
                    replacement["name"]
                )

                if recovery_info["affectedDay"] is None:
                    recovery_info["affectedDay"] = day_num
                    recovery_info["originalActivity"] = original_name
                    recovery_info["replacementActivity"] = (
                        replacement["name"]
                    )

                recovery_info["issueDetected"] = (
                    f"Unsuitable outdoor weather on Day {day_num}: "
                    f"{condition_name}"
                )

        if replacement_count:
            recovery_info["status"] = (
                "completed" if failed_count == 0 else "partial"
            )

            recovery_info["verified"] = failed_count == 0

            recovery_info["reason"] = (
                f"Replaced {replacement_count} outdoor activity "
                "or activities using indoor place results and "
                "successful route observations."
            )

            recovery_info["impact"] = (
                "Weather-affected outdoor activities were identified "
                "and eligible activities were replaced."
            )

            recovery_info["recoveryAction"] = (
                "Selected explicitly indoor attractions returned by "
                "the MCP places tool and obtained route estimates "
                "through the MCP route tool."
            )

            recovery_info["recalculation"] = (
                "Replacement activity costs and route travel times "
                "were taken from successful tool observations."
            )

            if failed_count:
                recovery_info["verification"] = (
                    "Partial recovery: some affected activities "
                    "could not be replaced with fully supported evidence."
                )
            else:
                recovery_info["verification"] = (
                    "Every attempted replacement has an explicitly "
                    "indoor places result and a successful route estimate. "
                    "Final itinerary validation is still required."
                )

        elif failed_count:
            recovery_info["status"] = "failed"
            recovery_info["verified"] = False
            recovery_info["reason"] = (
                "Recovery could not find and verify suitable replacements."
            )
            recovery_info["verification"] = (
                "Recovery was not verified. Original activities were retained."
            )

        return revised_itinerary, recovery_info
