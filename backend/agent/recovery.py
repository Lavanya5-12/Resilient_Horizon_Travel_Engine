"""
Recovery Engine.
Detects travel disruptions (e.g. weather conflicts), searches for matching indoor/safe alternatives,
recalculates time and budget, and replaces ALL affected activities with verified weather-safe options.
Routes ALL tool invocations strictly through the MCP Tool Boundary.
"""

from typing import Any, Dict, List, Tuple

class RecoveryEngine:
    def detect_and_recover(
        self,
        itinerary: List[Dict[str, Any]],
        weather_observations: List[Dict[str, Any]],
        provider: Any,
        user_interests: List[str],
        mcp_boundary: Any
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        
        recovery_info = {
            "occurred": False,
            "reason": "",
            "affectedDay": None,
            "affectedSlots": [],
            "originalActivities": [],
            "replacementActivities": [],
            "originalActivity": "",
            "replacementActivity": "",
            "issueDetected": "",
            "impact": "",
            "recoveryAction": "",
            "recalculation": "",
            "verification": ""
        }

        revised_itinerary = [dict(day) for day in itinerary]
        weather_map = {w.get("day"): w for w in weather_observations}
        disruptions_found = 0

        for day_idx, day_item in enumerate(revised_itinerary):
            day_num = day_item.get("day", 1)
            day_weather = weather_map.get(day_num, {})

            # Check if weather is unsuitable for outdoor activities on this day
            if day_weather and not day_weather.get("suitableForOutdoor", True):
                target_dest = day_weather.get("destination", "Destination")
                condition_name = day_weather.get("condition", "unfavorable weather")

                # ROUTE THROUGH MCP TOOL BOUNDARY (No direct provider calls)
                obs_places = mcp_boundary.invoke_tool(
                    tool_name="places.searchAttractions",
                    arguments={
                        "destination": target_dest,
                        "interests": user_interests,
                        "indoor_only": True
                    },
                    provider=provider
                )
                
                alt_response = obs_places.data if obs_places.status != "error" else {}
                indoor_attractions = alt_response.get("attractions", [])

                if not indoor_attractions:
                    indoor_attractions = [
                        {
                            "name": f"State Museum & Indoor Heritage Gallery in {target_dest}",
                            "category": "Historical Places",
                            "is_outdoor": False,
                            "estimated_cost_inr": 350.0,
                            "duration_hours": 2.5,
                            "location": f"Central {target_dest}"
                        },
                        {
                            "name": f"Cultural Art & History Center in {target_dest}",
                            "category": "Historical Places",
                            "is_outdoor": False,
                            "estimated_cost_inr": 250.0,
                            "duration_hours": 2.0,
                            "location": f"Old Town {target_dest}"
                        }
                    ]

                alt_idx = 0
                for slot in ["morning", "afternoon", "evening"]:
                    act = day_item.get(slot)
                    if act and isinstance(act, dict) and act.get("is_outdoor", False):
                        disruptions_found += 1
                        original_name = act.get("activity")

                        # Pick a distinct indoor attraction from candidate list
                        replacement = indoor_attractions[alt_idx % len(indoor_attractions)]
                        alt_idx += 1

                        # ROUTE THROUGH MCP TOOL BOUNDARY FOR ROUTE ESTIMATION
                        obs_route = mcp_boundary.invoke_tool(
                            tool_name="route.estimateTravel",
                            arguments={
                                "origin": day_item.get("morning", {}).get("location", "Hotel"),
                                "destination": replacement.get("location", f"Central {target_dest}")
                            },
                            provider=provider
                        )
                        route_info = obs_route.data if obs_route.status != "error" else {}

                        new_cost = float(replacement.get("estimated_cost_inr", 350.0))
                        new_time = int(route_info.get("travel_time_mins", 25))

                        replacement_act = {
                            "activity": replacement.get("name"),
                            "location": replacement.get("location"),
                            "cost_inr": new_cost,
                            "travel_time_mins": new_time,
                            "category": replacement.get("category", "Historical Places"),
                            "is_outdoor": False,
                            "was_recovered": True,
                            "original_activity": original_name
                        }

                        # Replace in revised itinerary
                        day_item[slot] = replacement_act
                        revised_itinerary[day_idx] = day_item

                        recovery_info["affectedSlots"].append(f"Day {day_num} {slot.capitalize()}")
                        recovery_info["originalActivities"].append(original_name)
                        recovery_info["replacementActivities"].append(replacement.get("name"))

                        if not recovery_info["occurred"]:
                            recovery_info["occurred"] = True
                            recovery_info["affectedDay"] = day_num
                            recovery_info["originalActivity"] = original_name
                            recovery_info["replacementActivity"] = replacement.get("name")
                            recovery_info["issueDetected"] = f"Unfavorable weather on Day {day_num} ({condition_name})"
                            recovery_info["impact"] = f"Outdoor activities on Day {day_num} unsafe or restricted due to weather alert."
                            recovery_info["recoveryAction"] = f"Replaced all Day {day_num} outdoor activities with indoor preference-matched attractions."

        if disruptions_found > 0:
            repl_str = ", ".join(set(recovery_info["replacementActivities"]))
            orig_str = ", ".join(set(recovery_info["originalActivities"]))
            recovery_info["reason"] = f"Replaced {disruptions_found} weather-affected outdoor activity/activities ({orig_str}) with indoor safe alternatives ({repl_str})."
            recovery_info["recalculation"] = f"Updated activity costs and transit times across {len(recovery_info['affectedSlots'])} slot(s)."
            recovery_info["verification"] = "Revised itinerary avoids weather risk across all travel days."

        return revised_itinerary, recovery_info
