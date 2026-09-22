"""
Travel Agent Orchestrator.
Executes the iterative Agentic Reasoning & Tool Loop with constraint verification and recovery.
"""

from typing import Any, Dict, List, Optional
import datetime
from backend.tools.base import ToolRegistry, ToolObservation
from backend.tools.weather import WeatherTool
from backend.tools.places import PlacesTool
from backend.tools.route import RouteTool
from backend.tools.availability import AvailabilityTool
from backend.tools.cost import CostTool
from backend.tools.validation import ValidationTool
from backend.providers.demo import DemoProvider
from backend.providers.real import RealProvider
from backend.agent.planner import TravelPlanner
from backend.agent.recovery import RecoveryEngine
from backend.agent.reflection import AgentReflection

MAX_ITERATIONS = 5

class ResilientTravelAgent:
    def __init__(self):
        self.registry = ToolRegistry()
        self.registry.register(WeatherTool())
        self.registry.register(PlacesTool())
        self.registry.register(RouteTool())
        self.registry.register(AvailabilityTool())
        self.registry.register(CostTool())
        self.registry.register(ValidationTool())

        self.planner = TravelPlanner()
        self.recovery_engine = RecoveryEngine()
        self.reflection_engine = AgentReflection()

    def run(
        self,
        destination: str,
        days: int = 4,
        budget: float = 15000.0,
        interests: List[str] = None,
        travel_date: Optional[str] = None,
        demo_mode: bool = True
    ) -> Dict[str, Any]:
        
        interests = interests or ["Beaches", "Historical Places"]
        provider = DemoProvider() if demo_mode else RealProvider()

        stages_log = []
        observations = []
        tools_executed = []

        def record_stage(stage_id: str, stage_name: str, status: str, detail: str):
            stages_log.append({
                "id": stage_id,
                "name": stage_name,
                "status": status,
                "detail": detail,
                "timestamp": datetime.datetime.now().isoformat()
            })

        # --- Stage 1: UNDERSTAND ---
        record_stage(
            "1", "UNDERSTAND", "completed",
            f"Parsed travel goal: {destination}, {days} Days, ₹{budget:,.0f} Budget, Interests: {', '.join(interests)}"
        )

        iteration = 0
        current_itinerary = []
        recovery_info = {"occurred": False}
        validation_res = {}
        weather_observations = []

        while iteration < MAX_ITERATIONS:
            iteration += 1

            if iteration == 1:
                # --- Stage 2: PLAN ---
                record_stage("2", "PLAN", "running", "Querying places discovery tool for destination attractions")
                places_tool = self.registry.get_tool("places.searchAttractions")
                places_res = places_tool.execute(provider, destination=destination, interests=interests)
                tools_executed.append("places.searchAttractions")
                
                obs = ToolObservation(
                    tool="places.searchAttractions",
                    status="success",
                    destination=destination,
                    data=places_res,
                    evidence=f"Retrieved {places_res.get('count', 0)} top attractions matching user interests.",
                    timestamp=datetime.datetime.now().isoformat()
                )
                observations.append(obs.model_dump())

                current_itinerary = self.planner.create_initial_plan(
                    destination=destination,
                    days=days,
                    budget=budget,
                    interests=interests,
                    places_data=places_res.get("attractions", [])
                )
                record_stage("2", "PLAN", "completed", "Generated candidate day-by-day itinerary")

                # --- Stage 3: OBSERVE ---
                record_stage("3", "OBSERVE", "running", "Checking weather and condition forecast across travel days")
                weather_tool = self.registry.get_tool("weather.getForecast")
                weather_observations = []

                for d in range(1, days + 1):
                    w_res = weather_tool.execute(provider, destination=destination, day=d)
                    weather_observations.append(w_res)
                    tools_executed.append("weather.getForecast")

                    obs_w = ToolObservation(
                        tool="weather.getForecast",
                        status="warning" if not w_res.get("suitableForOutdoor", True) else "success",
                        destination=destination,
                        data=w_res,
                        evidence=w_res.get("evidence", ""),
                        timestamp=datetime.datetime.now().isoformat()
                    )
                    observations.append(obs_w.model_dump())

                record_stage("3", "OBSERVE", "completed", f"Collected weather forecast for all {days} days")

                # --- Stage 4: DETECT ---
                record_stage("4", "DETECT", "running", "Evaluating itinerary against weather alerts and venue status")
                has_weather_disruption = any(not w.get("suitableForOutdoor", True) for w in weather_observations)
                
                if has_weather_disruption:
                    record_stage("4", "DETECT", "completed", "Detected weather conflict: Outdoor activities affected by weather alert")
                    
                    # --- Stage 5: RECOVER ---
                    record_stage("5", "RECOVER", "running", "Searching for indoor alternatives for all affected activities")
                    
                    current_itinerary, recovery_info = self.recovery_engine.detect_and_recover(
                        itinerary=current_itinerary,
                        weather_observations=weather_observations,
                        provider=provider,
                        user_interests=interests
                    )
                    
                    tools_executed.append("route.estimateTravel")
                    record_stage("5", "RECOVER", "completed", f"Replaced all weather-affected outdoor activities with indoor safe options ({', '.join(set(recovery_info.get('replacementActivities', [])))})")
                else:
                    record_stage("4", "DETECT", "completed", "No travel disruptions detected")
                    record_stage("5", "RECOVER", "completed", "No recovery action required")

            # --- Stage 6: VERIFY (Run on revised itinerary) ---
            record_stage("6", "VERIFY", "running", f"Running validation checks on itinerary (Iteration {iteration})")
            val_tool = self.registry.get_tool("validation.validateItinerary")
            validation_res = val_tool.execute(
                provider,
                itinerary=current_itinerary,
                budget_inr=budget,
                interests=interests,
                weather_conditions=weather_observations
            )
            tools_executed.append("validation.validateItinerary")

            obs_v = ToolObservation(
                tool="validation.validateItinerary",
                status="success" if validation_res.get("valid") else "warning",
                destination=destination,
                data=validation_res,
                evidence=f"Validated total cost (₹{validation_res.get('calculatedTotalCost', 0):,.0f}) against budget (₹{budget:,.0f}). Weather valid: {validation_res.get('weatherValid')}.",
                timestamp=datetime.datetime.now().isoformat()
            )
            observations.append(obs_v.model_dump())

            if validation_res.get("valid"):
                record_stage("6", "VERIFY", "completed", f"Verified budget & weather constraints: Remaining budget ₹{validation_res.get('remainingBudget', 0):,.0f}")
                break
            else:
                # If weather is still invalid and we can run another iteration, try recovering remaining conflicts
                if not validation_res.get("weatherValid") and iteration < MAX_ITERATIONS:
                    current_itinerary, recovery_info = self.recovery_engine.detect_and_recover(
                        itinerary=current_itinerary,
                        weather_observations=weather_observations,
                        provider=provider,
                        user_interests=interests
                    )
                else:
                    record_stage("6", "VERIFY", "completed", f"Validation finished: Valid={validation_res.get('valid')}")
                    break

        # --- Stage 7: FINAL PLAN ---
        record_stage("7", "FINAL PLAN", "running", "Synthesizing verified resilient itinerary")
        reflection_res = self.reflection_engine.reflect_and_explain(
            validation_res=validation_res,
            recovery_info=recovery_info,
            destination=destination,
            user_budget=budget,
            user_interests=interests
        )
        record_stage("7", "FINAL PLAN", "completed", "Final resilient itinerary prepared")

        final_status = "verified" if validation_res.get("valid") else "unverified"

        # Calculate final metrics
        total_activities = sum(
            1 for day in current_itinerary for slot in ["morning", "afternoon", "evening"] if day.get(slot)
        )
        total_cost = validation_res.get("calculatedTotalCost", budget * 0.95)
        total_travel_mins = sum(
            day.get(slot, {}).get("travel_time_mins", 20)
            for day in current_itinerary
            for slot in ["morning", "afternoon", "evening"]
            if day.get(slot)
        )

        return {
            "request": {
                "destination": destination,
                "days": days,
                "budget": budget,
                "interests": interests,
                "travelDate": travel_date or "Flexible",
                "demoMode": demo_mode
            },
            "status": final_status,
            "itinerary": current_itinerary,
            "metrics": {
                "totalCost": round(total_cost, 2),
                "remainingBudget": round(budget - total_cost, 2),
                "totalTravelTimeMinutes": total_travel_mins,
                "totalTravelTimeFormatted": f"{total_travel_mins // 60}h {total_travel_mins % 60}m",
                "activityCount": total_activities,
                "iterationsUsed": iteration,
                "maxIterations": MAX_ITERATIONS
            },
            "validation": validation_res,
            "recovery": recovery_info,
            "stages": stages_log,
            "evidence": observations,
            "explanation": reflection_res.get("summary_explanation", ""),
            "technicalDetails": {
                "toolsExecuted": list(set(tools_executed)),
                "providerUsed": provider.provider_name,
                "isDemoMode": demo_mode,
                "iterationCount": iteration
            }
        }
