"""
Travel Agent Orchestrator for Resilient Horizon Travel Engine.
Executes the dynamic LLM policy loop across the MCP Tool Boundary.
Saves durable agent execution traces and provides evidence-grounded final answers.
"""

from typing import Any, Dict, List, Optional
import datetime
import os
import json
import uuid
import logging

from backend.agent.action_models import TripRequest, AgentAction, ValidatedAction
from backend.agent.llm_policy import LLMPolicyEngine
from backend.tools.mcp_boundary import MCPToolBoundary
from backend.tools.base import ToolObservation
from backend.providers.demo import DemoProvider
from backend.providers.real import RealProvider
from backend.agent.planner import TravelPlanner
from backend.agent.recovery import RecoveryEngine
from backend.agent.reflection import AgentReflection

logger = logging.getLogger(__name__)
MAX_ITERATIONS = 8

class ResilientTravelAgent:
    def __init__(self):
        self.mcp = MCPToolBoundary()
        self.policy = LLMPolicyEngine()
        self.planner = TravelPlanner()
        self.recovery_engine = RecoveryEngine()
        self.reflection_engine = AgentReflection()

        # Ensure traces directory exists
        self.trace_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "traces")
        os.makedirs(self.trace_dir, exist_ok=True)

    def run(
        self,
        destination: str,
        days: int = 4,
        budget: float = 15000.0,
        interests: List[str] = None,
        travel_date: Optional[str] = None,
        demo_mode: bool = True
    ) -> Dict[str, Any]:
        
        # 1. Validate & Normalize Trip Request
        req_obj = TripRequest(
            destination=destination,
            days=days,
            budget=budget,
            interests=interests or ["Beaches", "Historical Places"],
            travel_date=travel_date,
            demo_mode=demo_mode
        )
        req_dict = req_obj.model_dump()
        provider = DemoProvider() if req_obj.demo_mode else RealProvider()

        session_id = str(uuid.uuid4())[:8]
        start_time = datetime.datetime.now().isoformat()

        stages_log = []
        observations: List[Dict[str, Any]] = []
        tools_executed: List[str] = []
        iteration_steps: List[Dict[str, Any]] = []

        def record_stage(stage_id: str, stage_name: str, status: str, detail: str):
            stages_log.append({
                "id": stage_id,
                "name": stage_name,
                "status": status,
                "detail": detail,
                "timestamp": datetime.datetime.now().isoformat()
            })

        record_stage("1", "UNDERSTAND", "completed", f"Parsed trip request for {req_obj.destination} ({req_obj.days} Days, ₹{req_obj.budget:,.0f} Budget).")

        iteration = 0
        current_itinerary: List[Dict[str, Any]] = []
        recovery_info: Dict[str, Any] = {"occurred": False}
        validation_res: Dict[str, Any] = {}
        weather_conditions: List[Dict[str, Any]] = []

        # MCP catalog for LLM policy prompt
        mcp_catalog = self.mcp.list_mcp_tools()

        # 2. DYNAMIC AGENT LOOP (DECIDE -> VALIDATE -> ACT -> OBSERVE -> REPEAT)
        while iteration < MAX_ITERATIONS:
            iteration += 1

            # LLM Policy Decides Next Action
            val_action: ValidatedAction = self.policy.decide_next_action(
                request=req_dict,
                iteration=iteration,
                max_iterations=MAX_ITERATIONS,
                current_itinerary=current_itinerary,
                observations=observations,
                mcp_tools=mcp_catalog,
                validation_res=validation_res
            )

            act_obj = val_action.action
            step_record = {
                "iteration": iteration,
                "reasoning": act_obj.reasoning,
                "action": act_obj.action,
                "tool_name": act_obj.tool_name,
                "arguments": act_obj.arguments,
                "is_valid": val_action.is_valid,
                "validation_errors": val_action.errors
            }

            if not val_action.is_valid or act_obj.action == "finish":
                step_record["status"] = "finished"
                iteration_steps.append(step_record)
                break

            # Execute Selected Tool via MCP Boundary
            tool_name = act_obj.tool_name
            args = act_obj.arguments or {}

            # Inject missing request defaults safely into tool arguments
            if tool_name == "places.searchAttractions" and "destination" not in args:
                args["destination"] = req_obj.destination
                args["interests"] = req_obj.interests
            elif tool_name == "weather.getForecast" and "destination" not in args:
                args["destination"] = req_obj.destination
                args["day"] = 1
            elif tool_name == "route.estimateTravel" and "origin" not in args:
                args["origin"] = f"Hotel in {req_obj.destination}"
                args["destination"] = f"Central {req_obj.destination}"
            elif tool_name == "availability.checkStatus" and "attraction_name" not in args:
                args["attraction_name"] = f"Main Landmark in {req_obj.destination}"
            elif tool_name == "cost.calculateEstimate" and "activities" not in args:
                args["activities"] = [d.get("morning", {}) for d in current_itinerary if d.get("morning")]
            elif tool_name == "validation.validateItinerary" and "itinerary" not in args:
                args["itinerary"] = current_itinerary
                args["budget_inr"] = req_obj.budget
                args["interests"] = req_obj.interests

            # INVOKE TOOL VIA MCP BOUNDARY
            obs_obj: ToolObservation = self.mcp.invoke_tool(
                tool_name=tool_name,
                arguments=args,
                provider=provider
            )
            
            tools_executed.append(tool_name)
            obs_dict = obs_obj.model_dump()
            observations.append(obs_dict)
            step_record["observation"] = obs_dict
            iteration_steps.append(step_record)

            # Update Internal State Based on Tool Output
            if tool_name == "places.searchAttractions":
                record_stage("2", "PLAN", "completed", f"Retrieved places observation from MCP boundary ({obs_obj.evidence})")
                if not current_itinerary:
                    places_list = obs_obj.data.get("attractions", [])
                    current_itinerary = self.planner.create_initial_plan(
                        destination=req_obj.destination,
                        days=req_obj.days,
                        budget=req_obj.budget,
                        interests=req_obj.interests,
                        places_data=places_list
                    )

            elif tool_name == "weather.getForecast":
                record_stage("3", "OBSERVE", "completed", f"Collected weather observation: {obs_obj.evidence}")
                weather_conditions.append(obs_obj.data)

                # Check weather disruption trigger
                if not obs_obj.data.get("suitableForOutdoor", True):
                    record_stage("4", "DETECT", "completed", f"Detected weather alert on Day {obs_obj.data.get('day', 1)}: {obs_obj.data.get('condition')}")
                    record_stage("5", "RECOVER", "running", "Executing disruption recovery through MCP tool boundary...")
                    
                    # Run Recovery via MCP Boundary
                    current_itinerary, recovery_info = self.recovery_engine.detect_and_recover(
                        itinerary=current_itinerary,
                        weather_observations=weather_conditions,
                        provider=provider,
                        user_interests=req_obj.interests,
                        mcp_boundary=self.mcp
                    )
                    record_stage("5", "RECOVER", "completed", f"Disruption recovery complete: {recovery_info.get('reason')}")

            elif tool_name == "validation.validateItinerary":
                validation_res = obs_obj.data
                record_stage("6", "VERIFY", "completed", f"Validated itinerary via MCP boundary (Valid={validation_res.get('valid')}).")

        # 3. Post-Loop Fallback & Final Validation Check
        if not validation_res and current_itinerary:
            # Ensure final validation is executed if model finished early
            obs_val = self.mcp.invoke_tool(
                tool_name="validation.validateItinerary",
                arguments={
                    "itinerary": current_itinerary,
                    "budget_inr": req_obj.budget,
                    "interests": req_obj.interests,
                    "weather_conditions": weather_conditions
                },
                provider=provider
            )
            validation_res = obs_val.data
            tools_executed.append("validation.validateItinerary")
            observations.append(obs_val.model_dump())

        # 4. Evidence-Based Reflection & Grounded Final Synthesis
        reflection_res = self.reflection_engine.reflect_and_explain(
            validation_res=validation_res,
            recovery_info=recovery_info,
            observations=observations,
            destination=req_obj.destination,
            user_budget=req_obj.budget,
            user_interests=req_obj.interests
        )
        record_stage("7", "FINAL PLAN", "completed", "Synthesized evidence-grounded final itinerary response.")

        final_status = "verified" if validation_res.get("valid", False) else "unverified"

        # Calculate Final Metrics
        total_activities = sum(
            1 for day in current_itinerary for slot in ["morning", "afternoon", "evening"] if day.get(slot)
        )
        total_cost = validation_res.get("calculatedTotalCost", req_obj.budget * 0.9)
        total_travel_mins = sum(
            day.get(slot, {}).get("travel_time_mins", 20)
            for day in current_itinerary
            for slot in ["morning", "afternoon", "evening"]
            if day.get(slot)
        )

        final_payload = {
            "session_id": session_id,
            "request": req_dict,
            "status": final_status,
            "itinerary": current_itinerary,
            "metrics": {
                "totalCost": round(total_cost, 2),
                "remainingBudget": round(req_obj.budget - total_cost, 2),
                "totalTravelTimeMinutes": total_travel_mins,
                "totalTravelTimeFormatted": f"{total_travel_mins // 60}h {total_travel_mins % 60}m",
                "activityCount": total_activities,
                "iterationsUsed": iteration,
                "maxIterations": MAX_ITERATIONS
            },
            "validation": validation_res,
            "recovery": recovery_info,
            "reflection": reflection_res,
            "explanation": reflection_res.get("summary_explanation", ""),
            "stages": stages_log,
            "evidence": observations,
            "technicalDetails": {
                "toolsExecuted": list(set(tools_executed)),
                "providerUsed": provider.provider_name,
                "isDemoMode": req_obj.demo_mode,
                "iterationCount": iteration,
                "llmModel": self.policy.model_name
            }
        }

        # 5. Save Durable Execution Trace to Disk
        try:
            safe_dest = "".join(c for c in req_obj.destination if c.isalnum() or c in ('_', '-')).lower()
            trace_filename = f"trace_{session_id}_{safe_dest}.json"
            trace_filepath = os.path.join(self.trace_dir, trace_filename)

            trace_data = {
                "session_id": session_id,
                "created_at": start_time,
                "completed_at": datetime.datetime.now().isoformat(),
                "request": req_dict,
                "iteration_steps": iteration_steps,
                "observations": observations,
                "reflection": reflection_res,
                "final_status": final_status,
                "validation": validation_res
            }

            with open(trace_filepath, "w", encoding="utf-8") as tf:
                json.dump(trace_data, tf, indent=2, ensure_ascii=False)
            
            final_payload["trace_file"] = trace_filepath
        except Exception as te:
            logger.warning(f"Failed to save trace file: {te}")

        return final_payload
