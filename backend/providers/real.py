
"""
Real Data Provider for Resilient Horizon Travel Engine.

Uses Open-Meteo for live weather observations.
Other provider methods currently return estimates or simulated catalog data;
they are not live external integrations.
"""

from typing import Any, Dict, List
from datetime import date as Date
from urllib.parse import urlencode
import json
import logging
import math
import urllib.request

logger = logging.getLogger(__name__)

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

        attractions = [
            {
                "id": f"{dest_clean.lower()}_real_01",
                "name": f"{dest_clean} Heritage & Cultural Center",
                "category": category,
                "is_outdoor": not indoor_only,
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
    ) -> Dict[str, Any]:

        total_cost = 0.0
        issues = []
        weather_valid = True

        weather_map = {
            w.get("day"): w
            for w in (weather_conditions or [])
        }

        for day_item in itinerary:
            day_num = day_item.get("day", 1)
            weather_for_day = weather_map.get(day_num, {})

            for slot in ("morning", "afternoon", "evening"):
                activity = day_item.get(slot)

                if activity and isinstance(activity, dict):
                    cost = float(
                        activity.get("cost_inr", 0)
                    )
                    total_cost += cost

                    if (
                        weather_for_day
                        and not weather_for_day.get(
                            "suitableForOutdoor", True
                        )
                        and activity.get("is_outdoor", False)
                    ):
                        weather_valid = False
                        issues.append(
                            f"Day {day_num} {slot}: Activity "
                            f"'{activity.get('activity')}' is outdoor "
                            f"but weather condition is "
                            f"'{weather_for_day.get('condition')}'"
                        )

        days = len(itinerary)
        transit_estimate = days * 400.0
        food_estimate = days * 1200.0
        grand_total = (
            total_cost + transit_estimate + food_estimate
        )

        budget_valid = grand_total <= budget_inr

        if not budget_valid:
            issues.append(
                f"Grand total INR {grand_total:,.2f} "
                f"exceeds user budget INR {budget_inr:,.2f}"
            )

        overall_valid = budget_valid and weather_valid

        return {
            "valid": overall_valid,
            "budgetValid": budget_valid,
            "timeValid": True,
            "preferencesValid": True,
            "availabilityValid": True,
            "weatherValid": weather_valid,
            "calculatedTotalCost": round(grand_total, 2),
            "remainingBudget": round(
                budget_inr - grand_total, 2
            ),
            "issues": issues,
            "source": "Estimated Constraint Calculator",
        }
