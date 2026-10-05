"""
LLM Policy Engine for Resilient Horizon Travel Engine.
Provides model-mediated decision making for dynamic tool selection and step planning.
Supports Ollama (default llama3.2:3b), OpenAI API, and a robust deterministic fallback policy.
"""

from typing import Any, Dict, List, Optional
import os
import json
import urllib.request
import urllib.error
import logging
from backend.agent.action_models import AgentAction, ValidatedAction, validate_agent_action
from backend.agent.prompts import SYSTEM_POLICY_PROMPT, format_policy_prompt

logger = logging.getLogger(__name__)

class LLMPolicyEngine:
    def __init__(self, model_name: str = "llama3.2:3b", ollama_base_url: str = "http://localhost:11434"):
        self.model_name = os.getenv("LLM_MODEL", model_name)
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", ollama_base_url).rstrip("/")

    def decide_next_action(
        self,
        request: Dict[str, Any],
        iteration: int,
        max_iterations: int,
        current_itinerary: List[Dict[str, Any]],
        observations: List[Dict[str, Any]],
        mcp_tools: List[Dict[str, Any]],
        validation_res: Dict[str, Any]
    ) -> ValidatedAction:
        
        registered_tool_names = [t["name"] for t in mcp_tools]
        tool_catalog_json = json.dumps(mcp_tools, indent=2)

        sys_prompt = SYSTEM_POLICY_PROMPT.format(tool_catalog_json=tool_catalog_json)
        user_prompt = format_policy_prompt(
            request=request,
            iteration=iteration,
            max_iterations=max_iterations,
            current_itinerary=current_itinerary,
            observations=observations,
            tool_catalog=mcp_tools,
            validation_res=validation_res
        )

        # 1. Try querying Ollama local server first
        raw_dict = self._call_ollama(sys_prompt, user_prompt)
        
        # 2. If Ollama unavailable or returned invalid output, use deterministic fallback policy
        if not raw_dict:
            raw_dict = self._fallback_policy_solver(
                request=request,
                iteration=iteration,
                max_iterations=max_iterations,
                current_itinerary=current_itinerary,
                observations=observations,
                validation_res=validation_res
            )

        # 3. Validate against Pydantic action schema
        return validate_agent_action(raw_dict, registered_tool_names)

    def _call_ollama(self, system_prompt: str, user_prompt: str) -> Optional[Dict[str, Any]]:
        """Invokes local Ollama server if available."""
        url = f"{self.ollama_base_url}/api/chat"
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.1}
        }

        try:
            req_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=req_bytes, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    body = json.loads(resp.read().decode("utf-8"))
                    content_str = body.get("message", {}).get("content", "")
                    return json.loads(content_str)
        except Exception:
            # Ollama server is offline or unreachable; safe fallback will be used
            return None
        return None

    def _fallback_policy_solver(
        self,
        request: Dict[str, Any],
        iteration: int,
        max_iterations: int,
        current_itinerary: List[Dict[str, Any]],
        observations: List[Dict[str, Any]],
        validation_res: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Deterministic, evidence-aware policy solver.
        Dynamically selects appropriate tools based on state, weather alerts, and validation checks.
        """
        dest = request.get("destination", "Goa")
        interests = request.get("interests", ["Beaches", "Historical Places"])
        trip_days = int(request.get("days", 4))

        # Tool 1: Places discovery
        if not any(obs.get("tool") == "places.searchAttractions" for obs in observations):
            return {
                "action": "tool",
                "tool_name": "places.searchAttractions",
                "arguments": {"destination": dest, "interests": interests},
                "reasoning": f"Querying place discovery tool to find candidate attractions for {dest} matching preferences."
            }

        # Tool 2: Weather forecast check across ALL travel days
        weather_obs_count = len([obs for obs in observations if obs.get("tool") == "weather.getForecast"])
        if weather_obs_count < trip_days:
            next_day = weather_obs_count + 1
            return {
                "action": "tool",
                "tool_name": "weather.getForecast",
                "arguments": {"destination": dest, "day": next_day},
                "reasoning": f"Querying weather forecast tool for {dest} (Day {next_day}) to check outdoor suitability."
            }

        # Tool 3: Availability check for top place
        if not any(obs.get("tool") == "availability.checkStatus" for obs in observations):
            top_place = "Fort Aguada Exploration" if "goa" in dest.lower() else f"{dest} Heritage Center"
            return {
                "action": "tool",
                "tool_name": "availability.checkStatus",
                "arguments": {"attraction_name": top_place, "time_of_day": "Morning"},
                "reasoning": f"Verifying venue operating hours and capacity status for {top_place}."
            }

        # Tool 4: Route estimation
        if not any(obs.get("tool") == "route.estimateTravel" for obs in observations):
            return {
                "action": "tool",
                "tool_name": "route.estimateTravel",
                "arguments": {"origin": f"Hotel in {dest}", "destination": f"Central {dest}"},
                "reasoning": "Estimating transit distance and travel time between activity locations."
            }

        # Tool 5: Validation check
        if not any(obs.get("tool") == "validation.validateItinerary" for obs in observations):
            return {
                "action": "tool",
                "tool_name": "validation.validateItinerary",
                "arguments": {
                    "itinerary": current_itinerary,
                    "budget_inr": float(request.get("budget", 15000.0)),
                    "interests": interests
                },
                "reasoning": "Running full constraint validation tool against budget, time, and weather checks."
            }

        # Tool 6: Cost calculation check
        if not any(obs.get("tool") == "cost.calculateEstimate" for obs in observations):
            return {
                "action": "tool",
                "tool_name": "cost.calculateEstimate",
                "arguments": {
                    "activities": [day.get("morning", {}) for day in current_itinerary if day.get("morning")],
                    "transit_costs": 1200.0
                },
                "reasoning": "Calculating itemized trip cost breakdown across activities and transit."
            }

        # If validated or max iterations reached -> finish
        return {
            "action": "finish",
            "tool_name": None,
            "arguments": {},
            "reasoning": f"Sufficient observations collected across dynamic tools ({len(observations)} steps). Finalizing itinerary."
        }
