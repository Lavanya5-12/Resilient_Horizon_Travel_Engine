"""
Planner Module.
Parses travel goals and generates dynamic candidate itineraries based on target destination, duration, budget, and interests.
"""

from typing import Any, Dict, List, Optional
import re

def parse_natural_language_request(prompt: str) -> Dict[str, Any]:
    """
    Parses a natural language travel query into structured parameters.
    Example: "Plan a 3-day Bangalore trip under ₹10,000 focused on food and shopping."
    """
    res = {}
    if not prompt or not prompt.strip():
        return res

    text = prompt.strip()

    # 1. Days extraction
    days_match = re.search(r'(\d+)\s*[- ]?(?:day|days|d\b)', text, re.IGNORECASE)
    if days_match:
        res['days'] = int(days_match.group(1))

    # 2. Budget extraction (₹, rs, inr, under, budget)
    budget_match = re.search(r'(?:₹|rs\.?|inr|under|budget of)\s*([\d,]+)', text, re.IGNORECASE)
    if budget_match:
        clean_num = budget_match.group(1).replace(',', '')
        res['budget'] = float(clean_num)

    # 3. Known Destination Extraction
    known_destinations = [
        "Goa", "Bangalore", "Bengaluru", "Hyderabad", "Mumbai", "Delhi",
        "New Delhi", "Jaipur", "Chennai", "Kolkata", "Agra", "Udaipur", "Kerala", "Manali", "Shimla"
    ]
    for dest in known_destinations:
        if re.search(r'\b' + re.escape(dest) + r'\b', text, re.IGNORECASE):
            res['destination'] = "Bangalore" if dest.lower() in ["bangalore", "bengaluru"] else dest.title()
            break

    # If no known destination matched, try extracting capitalized location word after "in", "to", "for", "trip"
    if 'destination' not in res:
        dest_match = re.search(r'(?:in|to|for|visit|trip to)\s+([A-Z][a-z]+)', text)
        if dest_match:
            res['destination'] = dest_match.group(1).title()

    # 4. Interests extraction
    found_interests = []
    interest_keywords = {
        "Beaches": ["beach", "beaches", "coast", "coastal", "sea"],
        "Historical Places": ["historic", "historical", "fort", "forts", "museum", "museums", "monument", "heritage", "palace"],
        "Food": ["food", "culinary", "dining", "cuisine", "restaurants", "street food", "dishes"],
        "Shopping": ["shopping", "bazaar", "market", "markets", "malls", "handicrafts"],
        "Nature": ["nature", "park", "parks", "garden", "gardens", "waterfall", "wildlife", "hills"],
        "Nightlife": ["nightlife", "clubs", "bars", "lounge", "pub", "parties"],
        "Adventure": ["adventure", "trekking", "water sports", "hiking", "sports"]
    }

    for cat, kws in interest_keywords.items():
        for kw in kws:
            if re.search(r'\b' + re.escape(kw) + r'\b', text, re.IGNORECASE):
                if cat not in found_interests:
                    found_interests.append(cat)
                break

    if found_interests:
        res['interests'] = found_interests

    return res


class TravelPlanner:
    def create_initial_plan(
        self,
        destination: str,
        days: int,
        budget: float,
        interests: List[str],
        places_data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        
        itinerary = []
        dest_clean = destination.strip().title()

        if not places_data:
            places_data = []

        # Target cost per activity to keep total within reasonable bounds
        target_activity_budget = max(100.0, (budget * 0.4) / (days * 3))

        # Separate outdoor and indoor places or generate dynamically per day
        place_idx = 0
        total_places = len(places_data)

        for d in range(1, days + 1):
            day_activities = {}

            for slot_name, default_cat in [("morning", interests[0] if interests else "Sightseeing"),
                                          ("afternoon", interests[1] if len(interests) > 1 else (interests[0] if interests else "Historical Places")),
                                          ("evening", "Leisure & Dining")]:
                
                # Check if we have a place from places_data
                if place_idx < total_places:
                    place = places_data[place_idx]
                    place_idx += 1
                    act_name = place.get("name")
                    loc = place.get("location", f"{dest_clean}")
                    cost = place.get("estimated_cost_inr", target_activity_budget)
                    cat = place.get("category", default_cat)
                    is_out = place.get("is_outdoor", True if "beach" in cat.lower() or "park" in cat.lower() else False)
                else:
                    # Dynamic place generation matching destination and slot
                    if "goa" in dest_clean.lower() and d == 2 and slot_name == "afternoon":
                        # Ensure Day 2 afternoon in Goa has an outdoor beach activity for weather disruption demo
                        act_name = "Miramar Beach & Water Sports Lounge"
                        loc = "Panaji, Goa"
                        cost = round(target_activity_budget * 1.5, -1)
                        cat = "Beaches"
                        is_out = True
                    else:
                        act_name = f"{default_cat} Experience in {dest_clean} (Day {d} {slot_name.capitalize()})"
                        loc = f"{dest_clean} City Center"
                        cost = round(target_activity_budget, -1)
                        cat = default_cat
                        is_out = True if slot_name == "afternoon" and ("beach" in cat.lower() or "outdoor" in cat.lower()) else False

                day_activities[slot_name] = {
                    "activity": act_name,
                    "location": loc,
                    "cost_inr": max(100.0, float(cost)),
                    "travel_time_mins": 20 + (d * 5) % 25,
                    "category": cat,
                    "is_outdoor": is_out
                }

            itinerary.append({
                "day": d,
                "title": f"Day {d}: {dest_clean} {interests[0] if interests else 'Highlights'}",
                "morning": day_activities["morning"],
                "afternoon": day_activities["afternoon"],
                "evening": day_activities["evening"]
            })

        return itinerary
