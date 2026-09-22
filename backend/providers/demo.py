"""
Demo Data Provider.
Provides realistic, deterministic travel observations and weather disruption scenarios.
Clearly separates mock/demo observations from agent reasoning logic.
"""

from typing import Any, Dict, List

class DemoProvider:
    def __init__(self):
        self.is_demo = True
        self.provider_name = "Demo Data Provider (Mock/Simulated)"

    def get_weather_forecast(self, destination: str, date: str = "", day: int = 1) -> Dict[str, Any]:
        dest_clean = destination.strip().lower()
        if "goa" in dest_clean:
            # Day 2 has unfavorable weather (heavy rain alert) to demonstrate disruption recovery in Goa
            if day == 2 or "day 2" in str(date).lower():
                return {
                    "destination": destination,
                    "day": day,
                    "condition": "heavy_rain_warning",
                    "temperature_c": 26.5,
                    "suitableForOutdoor": False,
                    "evidence": "IMD Weather Alert: High wind & heavy monsoon showers expected on Day 2 in North Goa. Outdoor beach & water sports activities restricted."
                }
            else:
                return {
                    "destination": destination,
                    "day": day,
                    "condition": "sunny",
                    "temperature_c": 31.0,
                    "suitableForOutdoor": True,
                    "evidence": f"Weather forecast for {destination} (Day {day}) is clear and sunny. Outdoor activities suitable."
                }
        else:
            return {
                "destination": destination,
                "day": day,
                "condition": "partly_cloudy",
                "temperature_c": 28.0,
                "suitableForOutdoor": True,
                "evidence": f"Weather forecast for {destination} (Day {day}) is clear and pleasant."
            }

    def search_places(self, destination: str, interests: List[str], indoor_only: bool = False) -> Dict[str, Any]:
        dest_clean = destination.strip().lower()
        interests_lower = [i.lower() for i in interests] if interests else []
        
        attractions = []

        if "goa" in dest_clean:
            if indoor_only:
                attractions = [
                    {
                        "id": "goa_hist_indoor_01",
                        "name": "State Museum & Aguada Fort Indoor Gallery",
                        "category": "Historical Places",
                        "is_outdoor": False,
                        "estimated_cost_inr": 400.0,
                        "duration_hours": 2.5,
                        "location": "Panaji / Candolim, Goa",
                        "description": "Historical exhibition of Goan heritage, naval history, and art artifacts indoors."
                    },
                    {
                        "id": "goa_hist_indoor_02",
                        "name": "Basilica of Bom Jesus & Museum",
                        "category": "Historical Places",
                        "is_outdoor": False,
                        "estimated_cost_inr": 250.0,
                        "duration_hours": 2.0,
                        "location": "Old Goa",
                        "description": "UNESCO World Heritage Baroque church and indoor art gallery."
                    }
                ]
            else:
                attractions = [
                    {"id": "goa_01", "name": "Fort Aguada Exploration", "category": "Historical Places", "is_outdoor": False, "estimated_cost_inr": 350.0, "duration_hours": 2.5, "location": "Candolim, Goa"},
                    {"id": "goa_02", "name": "Calangute Beach Water Sports", "category": "Beaches", "is_outdoor": True, "estimated_cost_inr": 1500.0, "duration_hours": 3.0, "location": "North Goa"},
                    {"id": "goa_03", "name": "Baga Beach Boardwalk & Sunset", "category": "Beaches", "is_outdoor": True, "estimated_cost_inr": 800.0, "duration_hours": 2.5, "location": "Baga, Goa"},
                    {"id": "goa_04", "name": "Anjuna Flea Market & Heritage Walk", "category": "Historical Places", "is_outdoor": False, "estimated_cost_inr": 300.0, "duration_hours": 2.5, "location": "Anjuna, Goa"},
                    {"id": "goa_05", "name": "Miramar Beach & Water Sports Lounge", "category": "Beaches", "is_outdoor": True, "estimated_cost_inr": 1200.0, "duration_hours": 3.0, "location": "Panaji, Goa"},
                    {"id": "goa_06", "name": "Mandovi River Cruise & Dinner", "category": "Historical Places", "is_outdoor": False, "estimated_cost_inr": 1000.0, "duration_hours": 2.5, "location": "Panaji, Goa"},
                    {"id": "goa_07", "name": "Old Goa Basilica of Bom Jesus", "category": "Historical Places", "is_outdoor": False, "estimated_cost_inr": 250.0, "duration_hours": 2.0, "location": "Old Goa"},
                    {"id": "goa_08", "name": "Panaji Latin Quarter (Fontainhas) Walk", "category": "Historical Places", "is_outdoor": False, "estimated_cost_inr": 400.0, "duration_hours": 2.0, "location": "Panaji, Goa"},
                    {"id": "goa_09", "name": "Spice Plantation Tour & Lunch", "category": "Historical Places", "is_outdoor": False, "estimated_cost_inr": 800.0, "duration_hours": 3.0, "location": "Ponda, Goa"},
                    {"id": "goa_10", "name": "Colva Beach Relaxation", "category": "Beaches", "is_outdoor": True, "estimated_cost_inr": 500.0, "duration_hours": 2.5, "location": "Colva, Goa"}
                ]

        elif "bangalore" in dest_clean or "bengaluru" in dest_clean:
            if indoor_only:
                attractions = [
                    {"id": "blr_ind_01", "name": "Visvesvaraya Industrial & Technological Museum", "category": "Historical Places", "is_outdoor": False, "estimated_cost_inr": 250.0, "duration_hours": 2.5, "location": "Kasturba Road, Bangalore"},
                    {"id": "blr_ind_02", "name": "National Gallery of Modern Art (NGMA)", "category": "Historical Places", "is_outdoor": False, "estimated_cost_inr": 200.0, "duration_hours": 2.0, "location": "Palace Road, Bangalore"}
                ]
            else:
                attractions = [
                    {"id": "blr_01", "name": "Bangalore Palace & Heritage Gallery", "category": "Historical Places", "is_outdoor": False, "estimated_cost_inr": 400.0, "duration_hours": 2.5, "location": "Vasanth Nagar, Bangalore"},
                    {"id": "blr_02", "name": "Lalbagh Botanical Garden Walk", "category": "Nature", "is_outdoor": True, "estimated_cost_inr": 100.0, "duration_hours": 2.0, "location": "Mavalli, Bangalore"},
                    {"id": "blr_03", "name": "MG Road & Church Street Food Crawl", "category": "Food", "is_outdoor": False, "estimated_cost_inr": 800.0, "duration_hours": 2.5, "location": "MG Road, Bangalore"},
                    {"id": "blr_04", "name": "Visvesvaraya Science Museum", "category": "Historical Places", "is_outdoor": False, "estimated_cost_inr": 250.0, "duration_hours": 2.5, "location": "Cubbon Park, Bangalore"},
                    {"id": "blr_05", "name": "Commercial Street Shopping Bazaar", "category": "Shopping", "is_outdoor": False, "estimated_cost_inr": 1200.0, "duration_hours": 3.0, "location": "Tasker Town, Bangalore"},
                    {"id": "blr_06", "name": "UB City Sky Lounge & Fine Dining", "category": "Food", "is_outdoor": False, "estimated_cost_inr": 1500.0, "duration_hours": 2.5, "location": "Vittal Mallya Road, Bangalore"},
                    {"id": "blr_07", "name": "Bull Temple & Basavanagudi Heritage Walk", "category": "Historical Places", "is_outdoor": False, "estimated_cost_inr": 150.0, "duration_hours": 2.0, "location": "Basavanagudi, Bangalore"},
                    {"id": "blr_08", "name": "Cubbon Park Morning Promenade", "category": "Nature", "is_outdoor": True, "estimated_cost_inr": 50.0, "duration_hours": 2.0, "location": "Central Bangalore"},
                    {"id": "blr_09", "name": "VV Puram Food Street Evening Tasting", "category": "Food", "is_outdoor": False, "estimated_cost_inr": 500.0, "duration_hours": 2.0, "location": "VV Puram, Bangalore"}
                ]

        elif "hyderabad" in dest_clean:
            if indoor_only:
                attractions = [
                    {"id": "hyd_ind_01", "name": "Salar Jung Museum & Art Gallery", "category": "Historical Places", "is_outdoor": False, "estimated_cost_inr": 300.0, "duration_hours": 3.0, "location": "Darulshifa, Hyderabad"},
                    {"id": "hyd_ind_02", "name": "Chowmahalla Palace Indoor Exhibition", "category": "Historical Places", "is_outdoor": False, "estimated_cost_inr": 250.0, "duration_hours": 2.0, "location": "Old City, Hyderabad"}
                ]
            else:
                attractions = [
                    {"id": "hyd_01", "name": "Charminar & Old City Heritage Walk", "category": "Historical Places", "is_outdoor": False, "estimated_cost_inr": 150.0, "duration_hours": 2.5, "location": "Charminar, Hyderabad"},
                    {"id": "hyd_02", "name": "Golconda Fort Heritage Exploration", "category": "Historical Places", "is_outdoor": True, "estimated_cost_inr": 300.0, "duration_hours": 3.0, "location": "Ibrahim Bagh, Hyderabad"},
                    {"id": "hyd_03", "name": "Salar Jung Art Museum", "category": "Historical Places", "is_outdoor": False, "estimated_cost_inr": 250.0, "duration_hours": 2.5, "location": "Darulshifa, Hyderabad"},
                    {"id": "hyd_04", "name": "Laad Bazaar Shopping & Bangles", "category": "Shopping", "is_outdoor": False, "estimated_cost_inr": 800.0, "duration_hours": 2.5, "location": "Charminar, Hyderabad"},
                    {"id": "hyd_05", "name": "Paradise Biryani Culinary Experience", "category": "Food", "is_outdoor": False, "estimated_cost_inr": 600.0, "duration_hours": 2.0, "location": "Secunderabad, Hyderabad"},
                    {"id": "hyd_06", "name": "Hussain Sagar Lake & Buddha Statue Promenade", "category": "Nature", "is_outdoor": True, "estimated_cost_inr": 200.0, "duration_hours": 2.0, "location": "Necklace Road, Hyderabad"}
                ]

        elif "mumbai" in dest_clean:
            if indoor_only:
                attractions = [
                    {"id": "mum_ind_01", "name": "Chhatrapati Shivaji Maharaj Vastu Sangrahalaya Museum", "category": "Historical Places", "is_outdoor": False, "estimated_cost_inr": 300.0, "duration_hours": 3.0, "location": "Fort, Mumbai"},
                    {"id": "mum_ind_02", "name": "Jehangir Art Gallery", "category": "Historical Places", "is_outdoor": False, "estimated_cost_inr": 150.0, "duration_hours": 2.0, "location": "Kala Ghoda, Mumbai"}
                ]
            else:
                attractions = [
                    {"id": "mum_01", "name": "Gateway of India & Colaba Promenade", "category": "Historical Places", "is_outdoor": True, "estimated_cost_inr": 100.0, "duration_hours": 2.0, "location": "Colaba, Mumbai"},
                    {"id": "mum_02", "name": "Marine Drive Sunset Walk", "category": "Nature", "is_outdoor": True, "estimated_cost_inr": 50.0, "duration_hours": 2.0, "location": "Marine Drive, Mumbai"},
                    {"id": "mum_03", "name": "Crawford Market & Street Food Tour", "category": "Food", "is_outdoor": False, "estimated_cost_inr": 700.0, "duration_hours": 2.5, "location": "Fort, Mumbai"},
                    {"id": "mum_04", "name": "Colaba Causeway Shopping Trail", "category": "Shopping", "is_outdoor": False, "estimated_cost_inr": 1000.0, "duration_hours": 2.5, "location": "Colaba, Mumbai"},
                    {"id": "mum_05", "name": "Chhatrapati Shivaji Museum & Gallery", "category": "Historical Places", "is_outdoor": False, "estimated_cost_inr": 300.0, "duration_hours": 2.5, "location": "Fort, Mumbai"}
                ]

        else:
            # Dynamic fallback place generator matching user interests and destination
            city = destination.strip().title()
            categories_to_use = interests if interests else ["Historical Places", "Sightseeing", "Food"]

            if indoor_only:
                attractions = [
                    {
                        "id": f"{city[:3].lower()}_ind_01",
                        "name": f"Heritage Art & History Museum in {city}",
                        "category": "Historical Places",
                        "is_outdoor": False,
                        "estimated_cost_inr": 300.0,
                        "duration_hours": 2.5,
                        "location": f"Central {city}",
                        "description": f"Indoor exhibition of {city} regional history and artifacts."
                    },
                    {
                        "id": f"{city[:3].lower()}_ind_02",
                        "name": f"Cultural Center & Indoor Gallery in {city}",
                        "category": "Historical Places",
                        "is_outdoor": False,
                        "estimated_cost_inr": 250.0,
                        "duration_hours": 2.0,
                        "location": f"Downtown {city}",
                        "description": f"Indoor gallery showcasing traditional craft and art of {city}."
                    }
                ]
            else:
                attractions = []
                for idx, cat in enumerate(categories_to_use * 3):
                    is_out = True if any(k in cat.lower() for k in ["beach", "park", "nature", "outdoor", "fort", "walk"]) else False
                    attractions.append({
                        "id": f"{city[:3].lower()}_{idx+1:02d}",
                        "name": f"{cat} Tour of {city} (Site #{idx+1})",
                        "category": cat,
                        "is_outdoor": is_out,
                        "estimated_cost_inr": round(250.0 + (idx * 120.0), -1),
                        "duration_hours": 2.0,
                        "location": f"{city} Landmark #{idx+1}"
                    })

        # Filter by interests if specified
        if interests and not indoor_only:
            filtered = [a for a in attractions if any(i.lower() in a.get("category", "").lower() or i.lower() in a.get("name", "").lower() for i in interests)]
            if filtered:
                attractions = filtered

        return {
            "destination": destination,
            "count": len(attractions),
            "attractions": attractions
        }

    def estimate_route(self, origin: str, destination: str, mode: str = "cab") -> Dict[str, Any]:
        return {
            "origin": origin,
            "destination": destination,
            "mode": mode,
            "distance_km": 12.5,
            "travel_time_mins": 30,
            "estimated_transit_cost_inr": 400.0
        }

    def check_availability(self, attraction_name: str, date: str = "", time_of_day: str = "Morning") -> Dict[str, Any]:
        return {
            "attraction_name": attraction_name,
            "is_open": True,
            "operating_hours": "09:00 AM - 06:00 PM",
            "capacity_status": "Normal availability",
            "evidence": f"Confirmed {attraction_name} is open during {time_of_day} on scheduled date."
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
        all_activities = []
        issues = []
        weather_valid = True
        
        weather_map = {w.get("day"): w for w in (weather_conditions or [])}

        for day_item in itinerary:
            day_num = day_item.get("day", 1)
            weather_for_day = weather_map.get(day_num, {})

            for slot in ["morning", "afternoon", "evening"]:
                act = day_item.get(slot)
                if act and isinstance(act, dict):
                    all_activities.append(act)
                    cost = act.get("cost_inr", 0)
                    total_cost += cost

                    # Weather conflict check
                    if weather_for_day and not weather_for_day.get("suitableForOutdoor", True):
                        if act.get("is_outdoor", False):
                            weather_valid = False
                            issues.append(f"Day {day_num} {slot}: Activity '{act.get('activity')}' is outdoor but weather condition is '{weather_for_day.get('condition')}'")

        # Transit estimation (~ 400 per day)
        days = len(itinerary)
        transit_est = days * 400.0
        food_est = days * 1200.0
        grand_total = total_cost + transit_est + food_est

        budget_valid = grand_total <= budget_inr
        if not budget_valid:
            issues.append(f"Grand total ₹{grand_total:,.2f} exceeds user budget ₹{budget_inr:,.2f}")

        time_valid = True
        preferences_valid = True

        overall_valid = budget_valid and weather_valid and time_valid

        return {
            "valid": overall_valid,
            "budgetValid": budget_valid,
            "timeValid": time_valid,
            "preferencesValid": preferences_valid,
            "availabilityValid": True,
            "weatherValid": weather_valid,
            "calculatedTotalCost": round(grand_total, 2),
            "remainingBudget": round(budget_inr - grand_total, 2),
            "issues": issues
        }
