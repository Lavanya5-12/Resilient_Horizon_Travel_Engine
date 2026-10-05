"""
Prompts and Policy Templates for Resilient Horizon Travel Engine LLM Policy Layer.
"""

from typing import Any, Dict, List
import json

SYSTEM_POLICY_PROMPT = """You are the autonomous AI decision-making policy layer for the Resilient Horizon Travel Engine.
Your goal is to plan a verified, resilient travel itinerary that satisfies user constraints and handles disruptions (weather, budget, time, availability).

### CRITICAL RULES:
1. You must decide the EXACT next action at each iteration step.
2. Output ONLY a valid JSON object matching the AgentAction schema below. No Markdown code fences, no extra text.
3. Available actions are:
   - "tool": Execute one registered tool from the dynamic tool catalog.
   - "finish": Complete planning when sufficient evidence exists and validation passes.
4. You MUST ONLY use tool names that exist in the Tool Catalog.
5. Base all decisions strictly on actual observations returned in previous tool steps. NEVER fabricate results.
6. If a weather conflict or budget violation is detected, select an appropriate tool to recover or adjust the itinerary.
7. Always run `validation.validateItinerary` before finishing.

### AGENT ACTION JSON SCHEMA:
{{
  "action": "tool" | "finish",
  "tool_name": "<registered_tool_name_or_null>",
  "arguments": {{ <keyword_arguments_for_tool> }},
  "reasoning": "<short_explanation_of_why_this_action_was_chosen>"
}}

### DISCOVERED TOOL CATALOG (MCP Boundary):
{tool_catalog_json}
"""

USER_STEP_PROMPT_TEMPLATE = """### TRAVEL REQUEST:
- Destination: {destination}
- Days: {days}
- Budget: ₹{budget:,.0f}
- Interests: {interests}
- Travel Start Date: {travel_date}
- Demo Mode: {demo_mode}

### CURRENT AGENT STATE:
- Iteration Step: {iteration} / {max_iterations}
- Itinerary Generated: {has_itinerary} (Total Days: {itinerary_days})
- Observations Collected Count: {observation_count}

### PREVIOUS OBSERVATIONS TRAIL:
{observations_text}

### RECENT VALIDATION / CONFLICT STATE:
{validation_summary}

Choose the single best next action (either call a tool or finish). Output ONLY the JSON matching AgentAction schema.
"""

def format_policy_prompt(
    request: Dict[str, Any],
    iteration: int,
    max_iterations: int,
    current_itinerary: List[Dict[str, Any]],
    observations: List[Dict[str, Any]],
    tool_catalog: List[Dict[str, Any]],
    validation_res: Dict[str, Any]
) -> str:
    """Formats the step-level prompt for the LLM policy engine."""
    obs_summary_lines = []
    for idx, obs in enumerate(observations, 1):
        tool = obs.get("tool", "unknown")
        status = obs.get("status", "info")
        ev = obs.get("evidence", "")
        obs_summary_lines.append(f"Step {idx} [{tool}] ({status}): {ev}")

    obs_text = "\n".join(obs_summary_lines) if obs_summary_lines else "No observations collected yet."

    val_text = "Not validated yet."
    if validation_res:
        is_v = validation_res.get("valid", False)
        b_v = validation_res.get("budgetValid", False)
        w_v = validation_res.get("weatherValid", False)
        issues = ", ".join(validation_res.get("issues", [])) or "None"
        val_text = f"Valid: {is_v} | Budget Valid: {b_v} | Weather Valid: {w_v} | Issues: {issues}"

    return USER_STEP_PROMPT_TEMPLATE.format(
        destination=request.get("destination", "Goa"),
        days=request.get("days", 4),
        budget=float(request.get("budget", 15000.0)),
        interests=", ".join(request.get("interests", [])),
        travel_date=request.get("travel_date") or "Flexible",
        demo_mode=request.get("demo_mode", True),
        iteration=iteration,
        max_iterations=max_iterations,
        has_itinerary=bool(current_itinerary),
        itinerary_days=len(current_itinerary),
        observation_count=len(observations),
        observations_text=obs_text,
        validation_summary=val_text
    )
