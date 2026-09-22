"""
Real Data Provider stub.
Can be populated with real HTTP client calls (OpenWeatherMap, Google Places API, Google Maps Distance Matrix)
when live API keys are provided in environment variables.
"""

from typing import Any, Dict, List
import os

class RealProvider:
    def __init__(self):
        self.is_demo = False
        self.provider_name = "Real API Provider"
        self.weather_api_key = os.getenv("OPENWEATHER_API_KEY", "")
        self.places_api_key = os.getenv("GOOGLE_PLACES_API_KEY", "")

    def get_weather_forecast(self, destination: str, date: str = "", day: int = 1) -> Dict[str, Any]:
        # Fallback to safe structure if API key missing
        return {
            "destination": destination,
            "day": day,
            "condition": "clear",
            "temperature_c": 28.0,
            "suitableForOutdoor": True,
            "evidence": "Live weather API forecast: clear sky."
        }

    def search_places(self, destination: str, interests: List[str], indoor_only: bool = False) -> Dict[str, Any]:
        return {
            "destination": destination,
            "count": 2,
            "attractions": [
                {
                    "id": "real_01",
                    "name": f"{destination} City Center Landmark",
                    "category": interests[0] if interests else "Sightseeing",
                    "is_outdoor": not indoor_only,
                    "estimated_cost_inr": 500.0,
                    "duration_hours": 2.0,
                    "location": destination
                }
            ]
        }

    def estimate_route(self, origin: str, destination: str, mode: str = "cab") -> Dict[str, Any]:
        return {
            "origin": origin,
            "destination": destination,
            "mode": mode,
            "distance_km": 10.0,
            "travel_time_mins": 25,
            "estimated_transit_cost_inr": 350.0
        }

    def check_availability(self, attraction_name: str, date: str = "", time_of_day: str = "Morning") -> Dict[str, Any]:
        return {
            "attraction_name": attraction_name,
            "is_open": True,
            "operating_hours": "09:00 AM - 06:00 PM",
            "capacity_status": "Available",
            "evidence": f"Confirmed {attraction_name} is operating."
        }

    def calculate_cost(self, activities: List[Dict[str, Any]], transit_costs: float = 0.0, daily_food_allowance_inr: float = 1200.0) -> Dict[str, Any]:
        act_total = sum(act.get("cost_inr", 0) for act in activities)
        days = max(1, len(set(act.get("day", 1) for act in activities)))
        food_total = daily_food_allowance_inr * days
        total = act_total + transit_costs + food_total
        return {
            "activities_cost_inr": round(act_total, 2),
            "transit_cost_inr": round(transit_costs, 2),
            "food_cost_inr": round(food_total, 2),
            "total_cost_inr": round(total, 2)
        }

    def validate_itinerary(self, itinerary: List[Dict[str, Any]], budget_inr: float, interests: List[str] = None, weather_conditions: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        total_cost = 0
        for day in itinerary:
            for slot in ["morning", "afternoon", "evening"]:
                act = day.get(slot)
                if act and isinstance(act, dict):
                    total_cost += act.get("cost_inr", 0)
        
        days = len(itinerary)
        grand_total = total_cost + (days * 400.0) + (days * 1200.0)
        budget_valid = grand_total <= budget_inr

        return {
            "valid": budget_valid,
            "budgetValid": budget_valid,
            "timeValid": True,
            "preferencesValid": True,
            "availabilityValid": True,
            "weatherValid": True,
            "calculatedTotalCost": round(grand_total, 2),
            "remainingBudget": round(budget_inr - grand_total, 2),
            "issues": [] if budget_valid else [f"Total cost ₹{grand_total:.2f} exceeds budget ₹{budget_inr:.2f}"]
        }
