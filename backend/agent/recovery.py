"""
Evidence-aware Recovery Engine for Resilient Horizon Travel Engine.

Replaces weather-affected outdoor activities only when:
1. The MCP places tool returns an explicitly indoor attraction.
2. The attraction has a name, location, and valid estimated cost.
3. The attraction is distinct and does not exhaust or duplicate candidates.
4. The attraction operating status is confirmed (fail-closed, explicit is_open is True).
5. The MCP route tool returns a valid travel-time estimate using the replaced
   activity's actual location or documented itinerary fallback (fail-closed, <= 180m).
6. The candidate is feasible and respects remaining budget limits without double-counting.
7. Simulated provider data is clearly preserved and distinguishable from live confirmation.

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

    @classmethod
    def _determine_route_origin(
        cls,
        activity: Dict[str, Any],
        day_item: Dict[str, Any],
        slot: str,
        trip_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Determine a reliable route origin for replacing an activity.

        1. Checks the location of the activity being replaced.
        2. If missing/invalid, checks documented fallbacks from the itinerary/context:
           - Other slots on the same day with valid locations (preceding first, then succeeding).
           - Day-level hotel, accommodation, or base_location.
           - Trip-level hotel, accommodation, or base_location in trip_context.
        3. If no reliable origin exists, returns None (does not invent a location).
        """
        # 1. Activity being replaced
        if isinstance(activity, dict):
            loc = activity.get("location")
            if isinstance(loc, str) and loc.strip():
                return loc.strip()

        # 2. Other slots on this day (prefer preceding slots)
        slot_order = ("morning", "afternoon", "evening")
        if slot in slot_order:
            current_idx = slot_order.index(slot)
            # Check preceding slots first
            for idx in reversed(range(current_idx)):
                other_act = day_item.get(slot_order[idx])
                if isinstance(other_act, dict):
                    loc = other_act.get("location")
                    if isinstance(loc, str) and loc.strip():
                        return loc.strip()
            # Then check succeeding slots
            for idx in range(current_idx + 1, len(slot_order)):
                other_act = day_item.get(slot_order[idx])
                if isinstance(other_act, dict):
                    loc = other_act.get("location")
                    if isinstance(loc, str) and loc.strip():
                        return loc.strip()
        else:
            for s in slot_order:
                other_act = day_item.get(s)
                if isinstance(other_act, dict):
                    loc = other_act.get("location")
                    if isinstance(loc, str) and loc.strip():
                        return loc.strip()

        # 3. Day-level accommodation / hotel
        for key in ("hotel", "accommodation", "base_location"):
            val = day_item.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()

        # 4. Trip context accommodation / hotel
        if trip_context and isinstance(trip_context, dict):
            for key in ("hotel", "accommodation", "base_location"):
                val = trip_context.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()

        return None

    @classmethod
    def _calculate_remaining_budget(
        cls,
        itinerary: List[Dict[str, Any]],
        budget: Optional[float],
        replacing_day: int,
        replacing_slot: str,
        trip_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[float], bool]:
        """Determine remaining trip budget without double-counting the replaced activity.

        Uses the actual ₹1,200/day food allowance and reliably supplied transit costs.
        Does not invent a fixed ₹400/day transit overhead.
        Fails unverified if any committed activity cost is missing, malformed, negative, or non-finite.

        Returns:
            (remaining_budget, is_calculable)
        """
        if budget is None:
            return None, False

        try:
            budget_val = float(budget)
        except (TypeError, ValueError):
            return None, False

        if not isfinite(budget_val) or budget_val < 0:
            return None, False

        committed_activity_costs = 0.0
        itinerary_day_numbers = set()

        for day in itinerary:
            if not isinstance(day, dict):
                return None, False
            day_num = cls._day_number(day.get("day"))
            if day_num is None:
                return None, False
            itinerary_day_numbers.add(day_num)

            for s in cls.SLOTS:
                # Exclude the exact activity currently being replaced to avoid double-counting
                if day_num == replacing_day and s == replacing_slot:
                    continue
                act = day.get(s)
                if act is not None:
                    if not isinstance(act, dict):
                        return None, False
                    raw_cost = act.get("cost_inr")
                    if raw_cost is None:
                        raw_cost = act.get("estimated_cost_inr")
                    if raw_cost is None:
                        # Missing activity cost -> cannot verify budget reliably
                        return None, False
                    cost = cls._valid_number(raw_cost)
                    if cost is None:
                        # Malformed, negative, or non-finite cost -> cannot verify budget reliably
                        return None, False
                    committed_activity_costs += cost

        # Determine total trip days consistently
        requested_days = None
        if trip_context and isinstance(trip_context, dict):
            requested_days = cls._day_number(trip_context.get("days"))

        if requested_days is not None and requested_days >= 1:
            total_days = requested_days
        elif itinerary_day_numbers:
            total_days = len(itinerary_day_numbers)
        else:
            # Cannot determine trip duration; do not silently invent 1 day
            return None, False

        # Actual food allowance: ₹1,200 per day (no invented transit overhead)
        food_cost = total_days * 1200.0

        # Transit costs: include only when reliably supplied
        transit_cost = 0.0
        if trip_context and isinstance(trip_context, dict) and "transit_costs" in trip_context:
            raw_tc = trip_context.get("transit_costs")
            if raw_tc is not None:
                tc = cls._valid_number(raw_tc)
                if tc is None:
                    # Transit cost provided but invalid/negative/non-finite
                    return None, False
                transit_cost = tc

        total_committed = committed_activity_costs + food_cost + transit_cost
        remaining = round(budget_val - total_committed, 2)
        return remaining, True

    def detect_and_recover(
        self,
        itinerary: List[Dict[str, Any]],
        weather_observations: List[Dict[str, Any]],
        provider: Any,
        user_interests: List[str],
        mcp_boundary: Any,
        observations: Optional[List[Dict[str, Any]]] = None,
        budget: Optional[float] = None,
        trip_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:

        trace_observations = observations if observations is not None else []

        recovery_info: Dict[str, Any] = {
            "occurred": False,
            "status": "not_needed",
            "verified": False,
            "budgetFeasibilityVerified": False,
            "reason": "",
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

        revised_itinerary = deepcopy(itinerary)

        weather_map = {}
        for weather in weather_observations:
            day_number = self._day_number(weather.get("day"))
            if day_number is not None:
                weather_map[day_number] = weather

        # Track attraction names already in the itinerary so we do not duplicate them
        # when distinct suitable alternatives exist.
        used_attractions = set()
        for d in revised_itinerary:
            if not isinstance(d, dict):
                continue
            d_num = self._day_number(d.get("day"))
            is_rainy = (
                d_num is not None
                and weather_map.get(d_num, {}).get("suitableForOutdoor", True) is False
            )
            for s in self.SLOTS:
                act = d.get(s)
                if isinstance(act, dict):
                    name = act.get("activity") or act.get("name")
                    if isinstance(name, str) and name.strip():
                        # Do not register outdoor activities on rainy days as active indoor places
                        if not (is_rainy and act.get("is_outdoor") is True):
                            used_attractions.add(name.strip().lower())

        destination_candidates_map: Dict[str, List[Dict[str, Any]]] = {}

        replacement_count = 0
        failed_count = 0
        any_simulated_evidence = False
        all_real_world_confirmed = True
        all_budget_verified = True

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

            # Do not invent a destination if weather evidence does not identify one.
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

            # Retrieve indoor alternatives through the MCP boundary if not already cached
            if target_destination not in destination_candidates_map:
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
                raw_candidates = (
                    places_data.get("attractions", [])
                    if places_record.get("status") == "success"
                    else []
                )

                # Accept only explicitly indoor attractions with usable data.
                verified_candidates = []
                for candidate in raw_candidates:
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

                destination_candidates_map[target_destination] = verified_candidates

            verified_candidates = destination_candidates_map[target_destination]

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

                # Determine route origin from the activity being replaced or documented fallback
                origin = self._determine_route_origin(
                    activity=activity,
                    day_item=day_item,
                    slot=slot,
                    trip_context=trip_context,
                )

                if not origin:
                    recovery_info["failedSlots"].append(
                        f"Day {day_num} {slot}: route origin is unavailable"
                    )
                    failed_count += 1
                    continue

                # Select a distinct, suitable, open, route-feasible indoor candidate
                chosen_candidate = None
                chosen_travel_time = None
                chosen_avail_evidence = {}
                chosen_route_evidence = {}
                chosen_budget_evidence = {}

                for candidate in verified_candidates:
                    cand_name = candidate["name"]
                    cand_norm = cand_name.strip().lower()

                    # Deduplication: avoid repeatedly selecting the same attraction
                    if cand_norm in used_attractions:
                        continue

                    # -------------------------------------------------------------
                    # 1. AVAILABILITY VERIFICATION (FAIL-CLOSED)
                    # -------------------------------------------------------------
                    avail_obs = None
                    try:
                        avail_obs = mcp_boundary.invoke_tool(
                            tool_name="availability.checkStatus",
                            arguments={
                                "attraction_name": cand_name,
                                "date": day_item.get("date", ""),
                                "time_of_day": slot.capitalize(),
                            },
                            provider=provider,
                        )
                        avail_rec = self._observation_dict(avail_obs)
                        trace_observations.append(avail_rec)
                    except Exception as exc:
                        trace_observations.append({
                            "tool": "availability.checkStatus",
                            "status": "error",
                            "data": {},
                            "evidence": f"Availability check failed: {exc}",
                        })
                        avail_obs = None

                    # Fail-closed: require successful observation
                    if avail_obs is None or getattr(avail_obs, "status", None) != "success":
                        continue

                    avail_data = getattr(avail_obs, "data", None)
                    if not isinstance(avail_data, dict):
                        continue

                    # Require explicit boolean is_open is True (reject False, None, missing, non-bool)
                    if avail_data.get("is_open") is not True:
                        continue

                    avail_source = str(
                        avail_data.get("source")
                        or getattr(provider, "provider_name", "Availability Service")
                    ).strip()

                    is_simulated_avail = (
                        bool(getattr(provider, "is_demo", False))
                        or avail_data.get("is_simulated") is True
                        or "simulat" in avail_source.lower()
                        or "mock" in avail_source.lower()
                        or "demo" in avail_source.lower()
                    )

                    avail_confirmed_real = (
                        not is_simulated_avail
                        and avail_data.get("confirmed") is True
                    )

                    # -------------------------------------------------------------
                    # 2. ROUTE EVIDENCE VERIFICATION (FAIL-CLOSED)
                    # -------------------------------------------------------------
                    route_obs = None
                    try:
                        route_obs = mcp_boundary.invoke_tool(
                            tool_name="route.estimateTravel",
                            arguments={
                                "origin": origin,
                                "destination": candidate["location"],
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
                        route_obs = None

                    # Fail-closed: require successful route observation
                    if route_obs is None or getattr(route_obs, "status", None) != "success":
                        continue

                    route_data = getattr(route_obs, "data", None)
                    if not isinstance(route_data, dict):
                        continue

                    travel_time = self._valid_number(
                        route_data.get("travel_time_mins")
                    )

                    # Reject excessive or unverified transit (must be finite non-negative <= 180 mins)
                    if travel_time is None or travel_time > 180.0:
                        continue

                    route_source = str(
                        route_data.get("source")
                        or getattr(provider, "provider_name", "Transit Calculator")
                    ).strip()

                    is_simulated_route = (
                        bool(getattr(provider, "is_demo", False))
                        or route_data.get("is_simulated") is True
                        or "simulat" in route_source.lower()
                        or "estimat" in route_source.lower()
                        or "demo" in route_source.lower()
                    )

                    route_confirmed_real = (
                        not is_simulated_route
                        and route_data.get("confirmed") is True
                    )

                    # -------------------------------------------------------------
                    # 3. BUDGET FEASIBILITY VERIFICATION
                    # -------------------------------------------------------------
                    remaining_budget, is_calculable = self._calculate_remaining_budget(
                        itinerary=revised_itinerary,
                        budget=budget,
                        replacing_day=day_num,
                        replacing_slot=slot,
                        trip_context=trip_context,
                    )

                    cand_cost = candidate["estimated_cost_inr"]

                    # If budget is provided and calculable, candidate cost must not exceed remaining budget
                    if is_calculable and remaining_budget is not None:
                        if cand_cost > remaining_budget:
                            continue
                        budget_feasibility_verified = True
                    else:
                        budget_feasibility_verified = False

                    # All verification checks passed
                    chosen_candidate = candidate
                    chosen_travel_time = travel_time
                    chosen_avail_evidence = {
                        "availability_tool": "availability.checkStatus",
                        "availability_open": True,
                        "availability_source": avail_source,
                        "availability_is_simulated": is_simulated_avail,
                        "availability_confirmed_real": avail_confirmed_real,
                    }
                    chosen_route_evidence = {
                        "route_tool": "route.estimateTravel",
                        "route_estimate_confirmed": True,
                        "route_origin": origin,
                        "route_destination": candidate["location"],
                        "route_travel_time_mins": int(travel_time),
                        "route_source": route_source,
                        "route_is_simulated": is_simulated_route,
                        "route_confirmed_real": route_confirmed_real,
                    }
                    chosen_budget_evidence = {
                        "budget_feasibility_verified": budget_feasibility_verified,
                        "remaining_budget": remaining_budget if is_calculable else None,
                    }
                    break

                if chosen_candidate is None:
                    # Candidate exhaustion or no suitable candidate remaining
                    recovery_info["failedSlots"].append(
                        f"Day {day_num} {slot}: no suitable verified indoor alternative available"
                    )
                    failed_count += 1
                    # Original activity is retained
                    continue

                if not chosen_budget_evidence.get("budget_feasibility_verified"):
                    all_budget_verified = False

                if chosen_avail_evidence.get("availability_is_simulated") or chosen_route_evidence.get("route_is_simulated"):
                    any_simulated_evidence = True
                if not (chosen_avail_evidence.get("availability_confirmed_real") and chosen_route_evidence.get("route_confirmed_real")):
                    all_real_world_confirmed = False

                # Apply selected replacement and mark candidate as used
                used_attractions.add(chosen_candidate["name"].strip().lower())

                replacement_activity = {
                    "activity": chosen_candidate["name"],
                    "location": chosen_candidate["location"],
                    "cost_inr": chosen_candidate["estimated_cost_inr"],
                    "travel_time_mins": int(chosen_travel_time),
                    "category": chosen_candidate.get(
                        "category",
                        "Historical Places",
                    ),
                    "is_outdoor": False,
                    "was_recovered": True,
                    "original_activity": original_name,
                    "recovery_evidence": {
                        "places_tool": "places.searchAttractions",
                        "indoor_status_confirmed": True,
                        **chosen_avail_evidence,
                        **chosen_route_evidence,
                        **chosen_budget_evidence,
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
                    chosen_candidate["name"]
                )
                recovery_info["replacementDetails"].append(
                    replacement_activity
                )

                if recovery_info["affectedDay"] is None:
                    recovery_info["affectedDay"] = day_num
                    recovery_info["originalActivity"] = original_name
                    recovery_info["replacementActivity"] = (
                        chosen_candidate["name"]
                    )

                recovery_info["issueDetected"] = (
                    f"Unsuitable outdoor weather on Day {day_num}: "
                    f"{condition_name}"
                )

        recovery_info["hasSimulatedEvidence"] = any_simulated_evidence
        recovery_info["hasRealWorldConfirmation"] = all_real_world_confirmed and replacement_count > 0
        recovery_info["budgetFeasibilityVerified"] = all_budget_verified and replacement_count > 0

        if replacement_count:
            recovery_info["status"] = (
                "completed" if failed_count == 0 else "partial"
            )

            # Fully verified recovery requires zero failed slots AND verified budget feasibility for all replacements
            recovery_info["verified"] = (
                failed_count == 0 and all_budget_verified
            )

            recovery_info["reason"] = (
                f"Replaced {replacement_count} outdoor activity "
                "or activities using indoor place results, confirmed "
                "availability, and successful route observations."
            )

            recovery_info["impact"] = (
                "Weather-affected outdoor activities were identified "
                "and eligible activities were replaced."
            )

            recovery_info["recoveryAction"] = (
                "Selected explicitly indoor attractions returned by "
                "the MCP places tool, checked operating status via "
                "the MCP availability tool, and obtained route estimates "
                "through the MCP route tool."
            )

            if not all_budget_verified:
                recovery_info["recalculation"] = (
                    "Replacement activities were selected, but budget feasibility "
                    "remains unverified due to missing or uncalculable budget data."
                )
            else:
                recovery_info["recalculation"] = (
                    "Replacement activity costs, remaining budget feasibility, and route "
                    "travel times were verified from successful tool observations."
                )

            if failed_count:
                recovery_info["verification"] = (
                    "Partial recovery: some affected activities "
                    "could not be replaced with fully supported evidence."
                )
            elif not all_budget_verified:
                sim_note = (
                    " Observations are labelled as simulated (no real-world live confirmation claimed)."
                    if any_simulated_evidence
                    else ""
                )
                recovery_info["verification"] = (
                    "Recovery activities were selected with confirmed indoor status and route "
                    f"estimates, but budget feasibility was not established.{sim_note}"
                )
            elif any_simulated_evidence:
                recovery_info["verification"] = (
                    "Every attempted replacement has an explicitly indoor places result, "
                    "simulated open operating status, budget feasibility verified, and a valid route estimate. "
                    "Observations are labelled as simulated (no real-world live confirmation claimed)."
                )
            else:
                recovery_info["verification"] = (
                    "Every attempted replacement has an explicitly indoor places result, "
                    "real-world confirmed availability, budget feasibility verified, and confirmed route feasibility."
                )

        elif failed_count:
            recovery_info["status"] = "failed"
            recovery_info["verified"] = False
            recovery_info["budgetFeasibilityVerified"] = False
            recovery_info["reason"] = (
                "Recovery could not find and verify suitable replacements."
            )
            recovery_info["verification"] = (
                "Recovery was not verified. Original activities were retained."
            )

        return revised_itinerary, recovery_info
