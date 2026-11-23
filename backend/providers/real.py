
"""
Real Data Provider for Resilient Horizon Travel Engine.

Uses Open-Meteo for live weather observations.
Other provider methods currently return estimates or simulated catalog data;
they are not live external integrations.
"""

from typing import Any, Dict, List, Optional
from datetime import date as Date, timedelta
from urllib.parse import urlencode
import json
import logging
import math
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)


def calculate_forecast_date(start_date: str, day: int) -> str:
    """Calculate the requested calendar date for day N of a trip: start_date + timedelta(days=day - 1)."""
    if not start_date or str(start_date).strip().lower() in ("flexible", "none"):
        return ""
    base = Date.fromisoformat(str(start_date).strip())
    target = base + timedelta(days=max(1, int(day)) - 1)
    return target.isoformat()

CITY_COORDINATES = {
    "goa": (15.2993, 74.1240),
    "kakinada": (16.9891, 82.2475),
    "bangalore": (12.9716, 77.5946),
    "bengaluru": (12.9716, 77.5946),
    "hyderabad": (17.3850, 78.4867),
    "mumbai": (19.0760, 72.8777),
    "delhi": (28.6139, 77.2090),
    "new delhi": (28.6139, 77.2090),
    "jaipur": (26.9124, 75.7873),
    "chennai": (13.0827, 80.2707),
    "kolkata": (22.5726, 88.3639),
}


class RealProvider:

    def __init__(self):
        self.is_demo = False
        self.provider_name = "Real Live API Provider (Open-Meteo Weather)"

    def get_weather_forecast(
        self,
        destination: str,
        date: str = "",
        day: int = 1,
        start_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Retrieve the requested day's forecast from Open-Meteo.

        Network failures, unsupported destinations, and incomplete API
        responses raise errors. They are never converted into fake weather.
        """

        if not isinstance(destination, str) or not destination.strip():
            raise ValueError("A valid destination is required.")

        destination_clean = destination.strip()
        city_key = destination_clean.lower()

        coordinates = CITY_COORDINATES.get(city_key)

        if coordinates is None:
            raise ValueError(
                f"Weather coordinates are not configured for "
                f"'{destination_clean}'. Cannot retrieve a reliable forecast."
            )

        if isinstance(day, bool) or not isinstance(day, int):
            raise ValueError("Forecast day must be an integer.")

        if day < 1 or day > 16:
            raise ValueError(
                "Forecast day must be between 1 and 16."
            )

        latitude, longitude = coordinates

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "daily": (
                "weather_code,"
                "temperature_2m_max,"
                "precipitation_sum"
            ),
            "timezone": "auto",
        }

        # If start_date is supplied, calculate the date for this itinerary day:
        if start_date and str(start_date).strip().lower() not in ("flexible", "none"):
            date = calculate_forecast_date(str(start_date).strip(), day)

        # An explicitly supplied ISO date requests that calendar date.
        # Flexible/empty dates use the requested day from today.
        if date and date.strip().lower() not in ("flexible", "none"):
            try:
                requested_date = Date.fromisoformat(date.strip())
            except ValueError as exc:
                raise ValueError(
                    "Travel date must use YYYY-MM-DD format."
                ) from exc

            params["start_date"] = requested_date.isoformat()
            params["end_date"] = requested_date.isoformat()
        else:
            params["forecast_days"] = day

        url = (
            "https://api.open-meteo.com/v1/forecast?"
            + urlencode(params)
        )

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "ResilientHorizonEngine/1.0"
            },
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=10,
            ) as response:

                if response.status != 200:
                    raise RuntimeError(
                        f"Open-Meteo returned HTTP {response.status}."
                    )

                response_data = json.loads(
                    response.read().decode("utf-8")
                )

        except urllib.error.HTTPError as exc:
            err_body = ""
            try:
                err_body = exc.read().decode("utf-8")
            except Exception:
                pass

            if exc.code == 400 and (
                "out of allowed range" in err_body.lower()
                or "range" in err_body.lower()
                or "invalid date" in err_body.lower()
            ):
                raise ValueError(
                    f"Requested date '{params.get('start_date', date)}' is outside Open-Meteo's allowed forecast horizon (live horizon is up to 16 days). API response: {err_body}"
                ) from exc

            raise RuntimeError(
                f"Open-Meteo HTTP {exc.code} for {destination_clean}: {err_body}"
            ) from exc
        except Exception as exc:
            logger.exception(
                "Open-Meteo weather request failed for %s",
                destination_clean,
            )

            raise RuntimeError(
                f"Live weather forecast unavailable for "
                f"{destination_clean}: {type(exc).__name__}: {exc}"
            ) from exc

        daily = response_data.get("daily")

        if not isinstance(daily, dict):
            raise ValueError(
                "Open-Meteo response does not contain daily forecast data."
            )

        required_fields = (
            "time",
            "weather_code",
            "temperature_2m_max",
            "precipitation_sum",
        )

        for field in required_fields:
            if not isinstance(daily.get(field), list):
                raise ValueError(
                    f"Open-Meteo response is missing valid '{field}' data."
                )

        # Explicit dates return a one-day result. Otherwise, select
        # the requested itinerary day using its zero-based array index.
        forecast_index = 0 if (
            date and date.strip().lower() not in ("flexible", "none")
        ) else day - 1

        try:
            forecast_date = daily["time"][forecast_index]
            weather_code = int(
                daily["weather_code"][forecast_index]
            )
            temperature = float(
                daily["temperature_2m_max"][forecast_index]
            )
            precipitation = float(
                daily["precipitation_sum"][forecast_index]
            )
        except (IndexError, TypeError, ValueError) as exc:
            raise ValueError(
                f"Open-Meteo did not return complete forecast data "
                f"for requested Day {day}."
            ) from exc

        if not all(
            math.isfinite(value)
            for value in (temperature, precipitation)
        ):
            raise ValueError(
                "Open-Meteo returned non-finite weather measurements."
            )

        if precipitation < 0:
            raise ValueError(
                "Open-Meteo returned invalid negative precipitation."
            )

        # WMO weather interpretation:
        # 51-67: drizzle/rain, 71-77: snow, 80-82: rain showers,
        # 85-86: snow showers, 95-99: thunderstorms.
        is_suitable = (
            precipitation < 10.0
            and weather_code < 60
        )

        condition = (
            "heavy_rain"
            if precipitation >= 10.0 or weather_code >= 60
            else "clear_to_partly_cloudy"
        )

        return {
            "destination": destination_clean,
            "day": day,
            "date": forecast_date,
            "condition": condition,
            "temperature_c": temperature,
            "precipitation_mm": precipitation,
            "suitableForOutdoor": is_suitable,
            "source": "Open-Meteo Live API",
            "evidence": (
                f"Live Open-Meteo forecast for {forecast_date}: "
                f"{condition}; maximum temperature "
                f"{temperature} C; precipitation "
                f"{precipitation} mm. "
                f"Outdoor suitable: {is_suitable}."
            ),
        }

    def search_places(
        self,
        destination: str,
        interests: List[str],
        indoor_only: bool = False,
    ) -> Dict[str, Any]:

        dest_clean = destination.strip().title()
        category = interests[0] if interests else "Sightseeing"

        if indoor_only:
            attractions = [
                {
                    "id": f"{dest_clean.lower()}_real_ind_01",
                    "name": f"{dest_clean} Heritage & Cultural Center",
                    "category": category,
                    "is_outdoor": False,
                    "estimated_cost_inr": 350.0,
                    "duration_hours": 2.5,
                    "location": f"Central {dest_clean}",
                },
                {
                    "id": f"{dest_clean.lower()}_real_ind_02",
                    "name": f"{dest_clean} City Museum & Exhibition Gallery",
                    "category": "Historical Places",
                    "is_outdoor": False,
                    "estimated_cost_inr": 250.0,
                    "duration_hours": 2.0,
                    "location": f"Downtown {dest_clean}",
                },
                {
                    "id": f"{dest_clean.lower()}_real_ind_03",
                    "name": f"{dest_clean} Regional Art & Science Pavilion",
                    "category": category,
                    "is_outdoor": False,
                    "estimated_cost_inr": 200.0,
                    "duration_hours": 2.0,
                    "location": f"Civic Quarter, {dest_clean}",
                },
                {
                    "id": f"{dest_clean.lower()}_real_ind_04",
                    "name": f"{dest_clean} Historic Palace Indoor Gallery",
                    "category": "Historical Places",
                    "is_outdoor": False,
                    "estimated_cost_inr": 300.0,
                    "duration_hours": 2.5,
                    "location": f"Old Town, {dest_clean}",
                },
                {
                    "id": f"{dest_clean.lower()}_real_ind_05",
                    "name": f"{dest_clean} Folk & Craft Indoor Exhibition",
                    "category": "Historical Places",
                    "is_outdoor": False,
                    "estimated_cost_inr": 180.0,
                    "duration_hours": 2.0,
                    "location": f"Arts District, {dest_clean}",
                },
            ]
        else:
            attractions = [
                {
                    "id": f"{dest_clean.lower()}_real_01",
                    "name": f"{dest_clean} Heritage & Cultural Center",
                    "category": category,
                    "is_outdoor": False,
                    "estimated_cost_inr": 350.0,
                    "duration_hours": 2.5,
                    "location": f"Central {dest_clean}",
                },
                {
                    "id": f"{dest_clean.lower()}_real_02",
                    "name": f"{dest_clean} City Museum & Exhibition Gallery",
                    "category": "Historical Places",
                    "is_outdoor": False,
                    "estimated_cost_inr": 250.0,
                    "duration_hours": 2.0,
                    "location": f"Downtown {dest_clean}",
                },
            ]

        return {
            "destination": destination,
            "count": len(attractions),
            "attractions": attractions,
            "source": "Simulated Place Catalog",
        }

    def estimate_route(
        self,
        origin: str,
        destination: str,
        mode: str = "cab",
    ) -> Dict[str, Any]:

        return {
            "origin": origin,
            "destination": destination,
            "mode": mode,
            "distance_km": 11.5,
            "travel_time_mins": 25,
            "estimated_transit_cost_inr": 380.0,
            "source": "Estimated Transit Calculator",
            "is_simulated": True,
            "confirmed": False,
        }

    def check_availability(
        self,
        attraction_name: str,
        date: str = "",
        time_of_day: str = "Morning",
    ) -> Dict[str, Any]:

        return {
            "attraction_name": attraction_name,
            "is_open": True,
            "operating_hours": "09:00 AM - 06:00 PM",
            "capacity_status": "Available",
            "evidence": (
                "Simulated availability result; "
                "not confirmed with the attraction."
            ),
            "source": "Simulated Availability Service",
            "is_simulated": True,
            "confirmed": False,
        }

    def calculate_cost(
        self,
        activities: List[Dict[str, Any]],
        transit_costs: float = 0.0,
        daily_food_allowance_inr: float = 1200.0,
    ) -> Dict[str, Any]:

        act_total = sum(
            act.get("cost_inr", 0)
            for act in activities
        )

        days = max(
            1,
            len(set(act.get("day", 1) for act in activities)),
        )

        food_total = daily_food_allowance_inr * days
        total = act_total + transit_costs + food_total

        return {
            "activities_cost_inr": round(act_total, 2),
            "transit_cost_inr": round(transit_costs, 2),
            "food_cost_inr": round(food_total, 2),
            "total_cost_inr": round(total, 2),
            "source": "Estimated Cost Calculator",
        }

    def validate_itinerary(
        self,
        itinerary: List[Dict[str, Any]],
        budget_inr: float,
        interests: List[str] = None,
        weather_conditions: List[Dict[str, Any]] = None,
        request_context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        import hashlib
        import json
        import math

        issues = []
        itinerary = itinerary or []
        canonical_itinerary = json.dumps(
            itinerary, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, default=str,
        )
        verified_itinerary_hash = hashlib.sha256(
            canonical_itinerary.encode("utf-8")
        ).hexdigest()
        interests = interests or []
        weather_conditions = weather_conditions or []

        # 1. Verify the original request and its SHA-256 hash.
        request_context_valid = False
        verified_request_hash = None
        requested_days = None

        if not isinstance(request_context, dict):
            issues.append("Original request context is missing.")
        else:
            required_fields = (
                "destination", "days", "budget", "interests",
                "travel_date", "demo_mode", "request_sha256",
            )
            missing = [key for key in required_fields if key not in request_context]

            if missing:
                issues.append("Request context is missing fields: " + ", ".join(missing))
            else:
                original_request = {
                    key: request_context[key]
                    for key in (
                        "destination", "days", "budget",
                        "interests", "travel_date", "demo_mode",
                    )
                }

                canonical = json.dumps(
                    original_request,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                    default=str,
                )
                calculated_hash = hashlib.sha256(
                    canonical.encode("utf-8")
                ).hexdigest()
                verified_request_hash = calculated_hash

                supplied_hash = request_context["request_sha256"]
                hash_matches = (
                    isinstance(supplied_hash, str)
                    and supplied_hash.lower() == calculated_hash
                )

                context_days = request_context["days"]
                context_budget = request_context["budget"]
                context_interests = request_context["interests"]

                values_valid = (
                    isinstance(request_context["destination"], str)
                    and bool(request_context["destination"].strip())
                    and isinstance(context_days, int)
                    and not isinstance(context_days, bool)
                    and 1 <= context_days <= 14
                    and isinstance(context_budget, (int, float))
                    and not isinstance(context_budget, bool)
                    and math.isfinite(float(context_budget))
                    and context_budget >= 1000
                    and isinstance(context_interests, list)
                    and all(isinstance(item, str) for item in context_interests)
                    and isinstance(request_context["demo_mode"], bool)
                )

                budget_matches = (
                    values_valid
                    and isinstance(budget_inr, (int, float))
                    and not isinstance(budget_inr, bool)
                    and math.isfinite(float(budget_inr))
                    and math.isclose(
                        float(budget_inr),
                        float(context_budget),
                        rel_tol=0,
                        abs_tol=0.001,
                    )
                )

                interests_match = (
                    values_valid and interests == context_interests
                )

                request_context_valid = (
                    values_valid and hash_matches
                    and budget_matches and interests_match
                )

                if not hash_matches:
                    issues.append("Original request SHA-256 hash does not match.")
                if not values_valid:
                    issues.append("Original request context contains invalid values.")
                if not budget_matches:
                    issues.append("Validation budget does not match the original request.")
                if not interests_match:
                    issues.append("Validation interests do not match the original request.")

                if values_valid:
                    requested_days = context_days

        if not request_context_valid:
            issues.append("Itinerary cannot be verified against the original request.")

        # 2. Check exact requested itinerary duration and day numbering.
        expected_days = (
            list(range(1, requested_days + 1))
            if requested_days is not None else []
        )

        day_numbers = []
        for item in itinerary:
            if not isinstance(item, dict):
                issues.append("Invalid day entry: expected an object.")
                continue

            number = item.get("day")
            if isinstance(number, int) and not isinstance(number, bool) and number >= 1:
                day_numbers.append(number)
            else:
                issues.append(f"Invalid itinerary day number: {number}.")

        structure_valid = (
            bool(expected_days)
            and len(day_numbers) == len(itinerary)
            and sorted(day_numbers) == expected_days
        )
        if not structure_valid:
            issues.append("Itinerary must contain exactly the requested consecutive days.")

        # 3. Check all three activity slots and their costs.
        total_activity_cost = 0.0
        required_slots = ("morning", "afternoon", "evening")
        valid_activity_count = 0

        for item in itinerary:
            if not isinstance(item, dict):
                continue

            day_number = item.get("day", "unknown")
            for slot in required_slots:
                activity = item.get(slot)

                if not isinstance(activity, dict):
                    issues.append(f"Day {day_number}: missing or invalid {slot} activity.")
                    continue

                name = activity.get("activity") or activity.get("name")
                if not isinstance(name, str) or not name.strip():
                    issues.append(f"Day {day_number} {slot}: activity name is missing.")
                    continue

                cost = activity.get("cost_inr")
                if (
                    isinstance(cost, bool)
                    or not isinstance(cost, (int, float))
                    or not math.isfinite(float(cost))
                    or cost < 0
                ):
                    issues.append(f"Day {day_number} {slot}: invalid activity cost.")
                    continue

                total_activity_cost += float(cost)
                valid_activity_count += 1

        activities_complete = (
            structure_valid
            and valid_activity_count == len(expected_days) * len(required_slots)
        )

        # 4. Require usable weather evidence for every requested day.
        weather_by_day = {}
        for weather in weather_conditions:
            if not isinstance(weather, dict):
                continue
            number = weather.get("day")
            if isinstance(number, int) and not isinstance(number, bool):
                weather_by_day[number] = weather

        weather_valid = bool(expected_days)
        weather_coverage_valid = bool(expected_days)

        for number in expected_days:
            weather = weather_by_day.get(number)
            if not isinstance(weather, dict):
                weather_valid = False
                weather_coverage_valid = False
                issues.append(f"Day {number}: no weather evidence available.")
                continue

            if not isinstance(weather.get("condition"), str) or not weather["condition"].strip():
                weather_valid = False
                issues.append(f"Day {number}: weather condition is missing.")

            if not isinstance(weather.get("suitableForOutdoor"), bool):
                weather_valid = False
                issues.append(f"Day {number}: outdoor suitability is unknown.")

        # 5. Check outdoor activities against their own day's weather.
        for item in itinerary:
            if not isinstance(item, dict):
                continue

            number = item.get("day")
            weather = weather_by_day.get(number, {})
            if weather.get("suitableForOutdoor") is False:
                for slot in required_slots:
                    activity = item.get(slot)
                    if isinstance(activity, dict) and activity.get("is_outdoor") is True:
                        weather_valid = False
                        name = activity.get("activity") or activity.get("name") or "Unnamed activity"
                        issues.append(
                            f"Day {number} {slot}: outdoor activity '{name}' "
                            "conflicts with unfavorable weather."
                        )

        # 6. Calculate documented estimated costs.
        days_for_cost = requested_days or len(itinerary)
        transit_estimate = days_for_cost * 400.0
        food_estimate = days_for_cost * 1200.0
        grand_total = total_activity_cost + transit_estimate + food_estimate

        budget_valid = (
            isinstance(budget_inr, (int, float))
            and not isinstance(budget_inr, bool)
            and math.isfinite(float(budget_inr))
            and budget_inr >= 1000
            and grand_total <= budget_inr
        )
        if not budget_valid:
            issues.append(
                f"Estimated total Rs.{grand_total:,.2f} exceeds or cannot "
                f"be validated against budget Rs.{budget_inr:,.2f}."
            )

        # 6. Genuine time feasibility check.
        time_valid = True
        for day_item in itinerary:
            if not isinstance(day_item, dict):
                continue
            day_number = day_item.get("day", "unknown")
            day_duration = 0.0
            for slot in required_slots:
                activity = day_item.get(slot)
                if not isinstance(activity, dict):
                    continue
                duration = activity.get("duration_hours", 2.5)
                if (
                    isinstance(duration, bool)
                    or not isinstance(duration, (int, float))
                    or not math.isfinite(float(duration))
                    or duration <= 0
                    or duration > 8.0
                ):
                    time_valid = False
                    issues.append(
                        f"Day {day_number} {slot}: activity duration ({duration}) is invalid."
                    )
                else:
                    day_duration += float(duration)
            if day_duration > 14.0:
                time_valid = False
                issues.append(
                    f"Day {day_number}: total scheduled activity time ({day_duration:.1f}h) exceeds feasible daily limit (14h)."
                )

        # 7. Genuine preference matching check.
        preferences_valid = True
        if interests:
            clean_interests = [
                i.strip().lower() for i in interests
                if isinstance(i, str) and i.strip()
            ]
            if clean_interests:
                matched_interests = set()
                for day_item in itinerary:
                    if not isinstance(day_item, dict):
                        continue
                    for slot in required_slots:
                        activity = day_item.get(slot)
                        if not isinstance(activity, dict):
                            continue
                        cat = str(activity.get("category", "")).lower()
                        name = str(activity.get("activity") or activity.get("name", "")).lower()
                        desc = str(activity.get("description", "")).lower()
                        for target in clean_interests:
                            if target in cat or target in name or target in desc:
                                matched_interests.add(target)
                if not matched_interests:
                    preferences_valid = False
                    issues.append(
                        f"Itinerary does not contain attractions matching requested interests: {interests}."
                    )

        # 8. Attraction availability check.
        availability_valid = True
        for day_item in itinerary:
            if not isinstance(day_item, dict):
                continue
            day_number = day_item.get("day", "unknown")
            for slot in required_slots:
                activity = day_item.get(slot)
                if isinstance(activity, dict):
                    if activity.get("is_open") is False:
                        availability_valid = False
                        act_name = activity.get("activity") or activity.get("name") or slot
                        issues.append(f"Day {day_number} {slot}: attraction '{act_name}' is reported closed.")

        overall_valid = (
            request_context_valid
            and structure_valid
            and activities_complete
            and budget_valid
            and weather_valid
            and weather_coverage_valid
            and time_valid is True
            and preferences_valid is True
            and availability_valid is True
        )

        return {
            "valid": overall_valid,
            "requestContextValid": request_context_valid,
            "requestSha256": verified_request_hash,
            "itinerarySha256": verified_itinerary_hash,
            "budgetValid": budget_valid,
            "timeValid": time_valid,
            "preferencesValid": preferences_valid,
            "availabilityValid": availability_valid,
            "weatherValid": weather_valid,
            "weatherCoverageValid": weather_coverage_valid,
            "itineraryStructureValid": structure_valid,
            "activitiesComplete": activities_complete,
            "calculatedTotalCost": round(grand_total, 2),
            "remainingBudget": (
                round(float(budget_inr) - grand_total, 2)
                if isinstance(budget_inr, (int, float))
                and not isinstance(budget_inr, bool)
                and math.isfinite(float(budget_inr))
                else None
            ),
            "issues": issues,
            "source": "Estimated Constraint Calculator; places and availability are simulated",
        }