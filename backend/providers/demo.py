
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

    def get_weather_forecast(self, destination: str, date: str = "", day: int = 1, start_date: str = "") -> Dict[str, Any]:
        dest_clean = destination.strip().lower()

        # If start_date is provided and date is empty, compute calendar date
        if start_date and str(start_date).strip().lower() not in ("flexible", "none") and not date:
            try:
                import datetime
                base = datetime.date.fromisoformat(str(start_date).strip())
                date = (base + datetime.timedelta(days=max(1, int(day)) - 1)).isoformat()
            except Exception:
                date = str(start_date).strip()

        date_str = f", {date}" if date else ""
        if "goa" in dest_clean:
            # Only numeric Day 2 has unfavorable weather.
            # The numeric day is authoritative; free-text dates must not override it.
            if day == 2:
                res = {
                    "destination": destination,
                    "day": day,
                    "condition": "heavy_rain_warning",
                    "temperature_c": 26.5,
                    "suitableForOutdoor": False,
                    "evidence": f"IMD Weather Alert: High wind & heavy monsoon showers expected on Day 2{date_str} in North Goa. Outdoor beach & water sports activities restricted."
                }
            else:
                res = {
                    "destination": destination,
                    "day": day,
                    "condition": "sunny",
                    "temperature_c": 31.0,
                    "suitableForOutdoor": True,
                    "evidence": f"Weather forecast for {destination} (Day {day}{date_str}) is clear and sunny. Outdoor activities suitable."
                }
        else:
            res = {
                "destination": destination,
                "day": day,
                "condition": "partly_cloudy",
                "temperature_c": 28.0,
                "suitableForOutdoor": True,
                "evidence": f"Weather forecast for {destination} (Day {day}{date_str}) is clear and pleasant."
            }

        if date:
            res["date"] = date
        return res

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
                    },
                    {
                        "id": "goa_hist_indoor_03",
                        "name": "Houses of Goa Architecture Museum",
                        "category": "Historical Places",
                        "is_outdoor": False,
                        "estimated_cost_inr": 300.0,
                        "duration_hours": 2.0,
                        "location": "Porvorim, Goa",
                        "description": "Unique multi-level ship-shaped museum showcasing Indo-Portuguese architectural history."
                    },
                    {
                        "id": "goa_hist_indoor_04",
                        "name": "Naval Aviation Museum Indoor Gallery",
                        "category": "Historical Places",
                        "is_outdoor": False,
                        "estimated_cost_inr": 200.0,
                        "duration_hours": 2.5,
                        "location": "Vasco da Gama, Goa",
                        "description": "Indoor exhibition of Indian naval aviation history, decommissioned aircraft artifacts, and military gallery."
                    },
                    {
                        "id": "goa_hist_indoor_05",
                        "name": "Mario Miranda Art Gallery & Cultural Exhibition",
                        "category": "Historical Places",
                        "is_outdoor": False,
                        "estimated_cost_inr": 150.0,
                        "duration_hours": 1.5,
                        "location": "Panaji, Goa",
                        "description": "Indoor gallery featuring original cartoons, cultural illustrations, and vibrant Goan lifestyle prints."
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
                    {"id": "blr_ind_02", "name": "National Gallery of Modern Art (NGMA)", "category": "Historical Places", "is_outdoor": False, "estimated_cost_inr": 200.0, "duration_hours": 2.0, "location": "Palace Road, Bangalore"},
                    {"id": "blr_ind_03", "name": "HAL Heritage Centre & Aerospace Exhibition", "category": "Historical Places", "is_outdoor": False, "estimated_cost_inr": 200.0, "duration_hours": 2.5, "location": "HAL Airport Road, Bangalore"},
                    {"id": "blr_ind_04", "name": "Jawaharlal Nehru Planetarium Space Gallery", "category": "Historical Places", "is_outdoor": False, "estimated_cost_inr": 150.0, "duration_hours": 2.0, "location": "High Grounds, Bangalore"},
                    {"id": "blr_ind_05", "name": "Karnataka Folk Museum & Crafts Pavilion", "category": "Historical Places", "is_outdoor": False, "estimated_cost_inr": 180.0, "duration_hours": 2.0, "location": "Kumara Park, Bangalore"}
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
                    {"id": "hyd_ind_02", "name": "Chowmahalla Palace Indoor Exhibition", "category": "Historical Places", "is_outdoor": False, "estimated_cost_inr": 250.0, "duration_hours": 2.0, "location": "Old City, Hyderabad"},
                    {"id": "hyd_ind_03", "name": "Nizam Museum & Purani Haveli Wardrobe Gallery", "category": "Historical Places", "is_outdoor": False, "estimated_cost_inr": 200.0, "duration_hours": 2.0, "location": "Purani Haveli, Hyderabad"},
                    {"id": "hyd_ind_04", "name": "Birla Science Centre & Dinosaurium", "category": "Historical Places", "is_outdoor": False, "estimated_cost_inr": 250.0, "duration_hours": 2.5, "location": "Naubat Pahad, Hyderabad"},
                    {"id": "hyd_ind_05", "name": "Sudha Car Museum Indoor Automotive Exhibition", "category": "Historical Places", "is_outdoor": False, "estimated_cost_inr": 150.0, "duration_hours": 2.0, "location": "Bahadurpura, Hyderabad"}
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
                    {"id": "mum_ind_02", "name": "Jehangir Art Gallery", "category": "Historical Places", "is_outdoor": False, "estimated_cost_inr": 150.0, "duration_hours": 2.0, "location": "Kala Ghoda, Mumbai"},
                    {"id": "mum_ind_03", "name": "Nehru Science Centre & Planetarium", "category": "Historical Places", "is_outdoor": False, "estimated_cost_inr": 200.0, "duration_hours": 2.5, "location": "Worli, Mumbai"},
                    {"id": "mum_ind_04", "name": "Dr. Bhau Daji Lad City Museum", "category": "Historical Places", "is_outdoor": False, "estimated_cost_inr": 100.0, "duration_hours": 2.0, "location": "Byculla, Mumbai"},
                    {"id": "mum_ind_05", "name": "National Museum of Indian Cinema", "category": "Historical Places", "is_outdoor": False, "estimated_cost_inr": 250.0, "duration_hours": 2.5, "location": "Pedder Road, Mumbai"}
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
                    },
                    {
                        "id": f"{city[:3].lower()}_ind_03",
                        "name": f"Science & Innovation Discovery Pavilion in {city}",
                        "category": "Historical Places",
                        "is_outdoor": False,
                        "estimated_cost_inr": 200.0,
                        "duration_hours": 2.0,
                        "location": f"Tech Corridor, {city}",
                        "description": f"Interactive indoor science exhibits and local innovation gallery in {city}."
                    },
                    {
                        "id": f"{city[:3].lower()}_ind_04",
                        "name": f"Craft & Folk Traditions Indoor Exhibition in {city}",
                        "category": "Historical Places",
                        "is_outdoor": False,
                        "estimated_cost_inr": 180.0,
                        "duration_hours": 2.0,
                        "location": f"Old Quarter, {city}",
                        "description": f"Preserved indoor artisanal workshops and textiles of {city}."
                    },
                    {
                        "id": f"{city[:3].lower()}_ind_05",
                        "name": f"Regional Architecture & Archaeology Museum in {city}",
                        "category": "Historical Places",
                        "is_outdoor": False,
                        "estimated_cost_inr": 220.0,
                        "duration_hours": 2.0,
                        "location": f"Civic Center, {city}",
                        "description": f"Indoor archaeological gallery with scale models and monuments of {city}."
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
            filtered = [
                a for a in attractions
                if any(
                    i.lower() in a.get("category", "").lower()
                    or i.lower() in a.get("name", "").lower()
                    for i in interests
                )
            ]
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
            "estimated_transit_cost_inr": 400.0,
            "source": "Simulated Route Service (Demo Provider)",
            "is_simulated": True,
            "confirmed": False,
        }

    def check_availability(self, attraction_name: str, date: str = "", time_of_day: str = "Morning") -> Dict[str, Any]:
        return {
            "attraction_name": attraction_name,
            "is_open": True,
            "operating_hours": "09:00 AM - 06:00 PM",
            "capacity_status": "Normal availability",
            "evidence": f"Simulated demo availability: {attraction_name} is open during {time_of_day} on scheduled date.",
            "source": "Simulated Availability Service (Demo Provider)",
            "is_simulated": True,
            "confirmed": False,
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

    def validate_itinerary(
        self,
        itinerary: List[Dict[str, Any]],
        budget_inr: float,
        interests: List[str] = None,
        weather_conditions: List[Dict[str, Any]] = None,
        request_context: Dict[str, Any] = None
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
        weather_conditions = weather_conditions or []
        interests = interests or []

        # 1. Verify the original request and its integrity hash.
        request_context_valid = False
        verified_request_hash = None
        requested_days = None

        if not isinstance(request_context, dict):
            issues.append("Original request context is missing.")
        else:
            required_fields = (
                "destination",
                "days",
                "budget",
                "interests",
                "travel_date",
                "demo_mode",
                "request_sha256",
            )

            missing_fields = [
                field for field in required_fields
                if field not in request_context
            ]

            if missing_fields:
                issues.append(
                    "Request context is missing fields: "
                    + ", ".join(missing_fields)
                )
            else:
                original_request = {
                    "destination": request_context["destination"],
                    "days": request_context["days"],
                    "budget": request_context["budget"],
                    "interests": request_context["interests"],
                    "travel_date": request_context["travel_date"],
                    "demo_mode": request_context["demo_mode"],
                }

                canonical_request = json.dumps(
                    original_request,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                    default=str,
                )

                calculated_hash = hashlib.sha256(
                    canonical_request.encode("utf-8")
                ).hexdigest()

                supplied_hash = request_context["request_sha256"]
                verified_request_hash = calculated_hash

                hash_matches = (
                    isinstance(supplied_hash, str)
                    and supplied_hash.lower() == calculated_hash
                )

                context_days = request_context["days"]
                context_budget = request_context["budget"]
                context_interests = request_context["interests"]

                valid_context_values = (
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
                    isinstance(budget_inr, (int, float))
                    and not isinstance(budget_inr, bool)
                    and math.isfinite(float(budget_inr))
                    and math.isclose(
                        float(budget_inr),
                        float(context_budget),
                        rel_tol=0,
                        abs_tol=0.001,
                    )
                ) if valid_context_values else False

                interests_match = (
                    interests == context_interests
                ) if valid_context_values else False

                request_context_valid = (
                    valid_context_values
                    and hash_matches
                    and budget_matches
                    and interests_match
                )

                if not hash_matches:
                    issues.append("Original request SHA-256 hash does not match.")

                if not valid_context_values:
                    issues.append("Original request context contains invalid values.")

                if not budget_matches:
                    issues.append("Validation budget does not match the original request.")

                if not interests_match:
                    issues.append("Validation interests do not match the original request.")

                if valid_context_values:
                    requested_days = context_days

        if not request_context_valid:
            issues.append("Itinerary cannot be verified against an authenticated original request.")

        # 2. Validate itinerary structure against the requested trip duration.
        expected_days = (
            list(range(1, requested_days + 1))
            if requested_days is not None
            else []
        )

        if not itinerary:
            issues.append("Itinerary is empty.")

        day_numbers = []

        for day_item in itinerary:
            if not isinstance(day_item, dict):
                issues.append("Invalid day entry: expected an object.")
                continue

            day_number = day_item.get("day")

            if (
                not isinstance(day_number, int)
                or isinstance(day_number, bool)
                or day_number < 1
            ):
                issues.append(f"Invalid itinerary day number: {day_number}.")
            else:
                day_numbers.append(day_number)

        structure_valid = (
            bool(expected_days)
            and len(day_numbers) == len(itinerary)
            and sorted(day_numbers) == expected_days
        )

        if not structure_valid:
            issues.append(
                "Itinerary must contain exactly the requested number "
                "of unique, consecutively numbered days."
            )

        # 3. Require all three valid activity slots for every requested day.
        total_activity_cost = 0.0
        activities = []
        required_slots = ("morning", "afternoon", "evening")

        for day_item in itinerary:
            if not isinstance(day_item, dict):
                continue

            day_number = day_item.get("day", "unknown")

            for slot in required_slots:
                activity = day_item.get(slot)

                if not isinstance(activity, dict):
                    issues.append(
                        f"Day {day_number}: missing or invalid {slot} activity."
                    )
                    continue

                activity_name = activity.get("activity") or activity.get("name")

                if not isinstance(activity_name, str) or not activity_name.strip():
                    issues.append(
                        f"Day {day_number} {slot}: activity name is missing."
                    )
                    continue

                cost = activity.get("cost_inr")

                if (
                    isinstance(cost, bool)
                    or not isinstance(cost, (int, float))
                    or not math.isfinite(float(cost))
                    or cost < 0
                ):
                    issues.append(
                        f"Day {day_number} {slot}: activity has an invalid cost."
                    )
                    continue

                total_activity_cost += float(cost)
                activities.append(activity)

        activities_complete = (
            structure_valid
            and len(activities) == len(expected_days) * len(required_slots)
        )

        # 4. Require valid weather evidence for every requested day.
        weather_by_day = {}

        for weather in weather_conditions:
            if not isinstance(weather, dict):
                continue

            day_number = weather.get("day")

            if isinstance(day_number, int) and not isinstance(day_number, bool):
                weather_by_day[day_number] = weather

        weather_valid = bool(expected_days)
        weather_coverage_valid = bool(expected_days)

        for day_number in expected_days:
            weather = weather_by_day.get(day_number)

            if not isinstance(weather, dict):
                weather_valid = False
                weather_coverage_valid = False
                issues.append(f"Day {day_number}: no weather evidence available.")
                continue

            condition = weather.get("condition")
            outdoor_suitable = weather.get("suitableForOutdoor")

            if not isinstance(condition, str) or not condition.strip():
                weather_valid = False
                issues.append(f"Day {day_number}: weather condition is missing.")

            if not isinstance(outdoor_suitable, bool):
                weather_valid = False
                issues.append(f"Day {day_number}: outdoor suitability is unknown.")

        # Check outdoor activities against their own day's weather.
        for day_item in itinerary:
            if not isinstance(day_item, dict):
                continue

            day_number = day_item.get("day")
            weather = weather_by_day.get(day_number, {})

            if weather.get("suitableForOutdoor") is False:
                for slot in required_slots:
                    activity = day_item.get(slot)

                    if (
                        isinstance(activity, dict)
                        and activity.get("is_outdoor") is True
                    ):
                        weather_valid = False
                        activity_name = (
                            activity.get("activity")
                            or activity.get("name")
                            or "Unnamed activity"
                        )
                        issues.append(
                            f"Day {day_number} {slot}: outdoor activity "
                            f"'{activity_name}' conflicts with unfavorable weather."
                        )

        # 5. Calculate budget using documented demo estimates.
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
                f"Estimated total Rs.{grand_total:,.2f} exceeds or cannot be "
                f"validated against budget Rs.{budget_inr:,.2f}."
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
            "source": "Demo Provider - simulated estimates; not independently verified",
        }