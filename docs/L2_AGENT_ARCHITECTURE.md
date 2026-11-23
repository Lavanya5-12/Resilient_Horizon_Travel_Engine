# Resilient Horizon Travel Engine - L2 Agentic Architecture Specification

## Overview & Agent Loop Design

The **Resilient Horizon Travel Engine** implements an **L2 Model-Mediated Agent Architecture**. The AI model acts as the dynamic decision-making policy layer, selecting tools based on step-level state and observations, while the Python framework provides strict runtime safety, schema validation, and iteration bounds.

```
                  ┌──────────────────────────────────────────────┐
                  │                 User Request                 │
                  └──────────────────────┬───────────────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │   LLM Policy Engine (Ollama / Local / Solv)  │
                  └──────────────────────┬───────────────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │ AgentAction Pydantic Validation (ActionModel)│
                  └──────────────────────┬───────────────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │       MCP Tool Boundary (MCPToolBoundary)     │
                  └──────┬───────────────┬───────────────┬───────┘
                         │               │               │
                         ▼               ▼               ▼
                  ┌────────────┐   ┌────────────┐  ┌───────────┐
                  │  Weather   │   │   Places   │  │   Route   │ ...
                  └─────┬──────┘   └─────┬──────┘  └─────┬─────┘
                        │                │               │
                        └────────────────┼───────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │ Structured ToolObservations (Evidence Trail) │
                  └──────────────────────┬───────────────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │        Disruption Recovery Engine            │
                  └──────────────────────┬───────────────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │  Evidence-Based Reflection & Final Audit    │
                  └──────────────────────┬───────────────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │ Saved Durable Execution Trace (traces/*.json)│
                  └──────────────────────────────────────────────┘
```

---

## Key Architectural Components

### 1. LLM Policy Layer (`backend/agent/llm_policy.py`)
- **Role**: Model-mediated policy engine deciding the next action per step based on current observations and outstanding planning requirements.
- **Provider Support**: Integrates local Ollama (`llama3.2:3b` default at `http://localhost:11434`) with configurable HTTP timeout and an evidence-aware deterministic fallback policy.
- **Dynamic Catalog Injection**: Automatically injects JSON Schema tool specifications discovered from the MCP server into the system prompt.
- **Strict Ollama Mode**: When `REQUIRE_OLLAMA_FOR_DEMO=true` or strict mode is active, fallback is disabled and the engine rejects invalid/malformed decisions with `invalid_action` fail-closed semantics.

### 2. Pydantic Action Validation (`backend/agent/action_models.py`)
- **Schema**: `AgentAction(action="tool"|"finish", tool_name, arguments, reasoning)`.
- **Validation**: Strict validation of actions, tool names, and arguments against discovered MCP schemas. Missing or None `reasoning` fields are safely normalized to default text without breaking execution.
- **Safety Boundary**: Every model output is validated against Pydantic schema and allowlisted registered tool names. Invalid actions or malformed parameters are converted to safe error observations without crashing the agent.

### 3. Genuine MCP Tool Boundary (`backend/tools/mcp_boundary.py` & `backend/tools/mcp_server.py`)
- **FastMCP Server**: `backend/tools/mcp_server.py` defines and registers tools on FastMCP (`TravelPlanningTools`).
- **Official MCP Client SDK**: `PersistentMCPConnection` manages an official MCP client session over `stdio_client` and `ClientSession` on a dedicated thread with an async event loop.
- **Dynamic Tool Discovery**: Queries `session.list_tools()` at startup to dynamically construct the tool catalog and parameter schemas.
- **In-Process Fallback**: Provides a safe in-process fallback executing tool functions directly if stdio transport is disabled or unavailable.
- **Registered Tools**:
  1. `places.searchAttractions`: Discovers attractions matching user interests.
  2. `weather.getForecast`: Evaluates forecast conditions and outdoor activity suitability.
  3. `route.estimateTravel`: Calculates transit distance and time between distinct locations.
  4. `availability.checkStatus`: Checks attraction operating hours and slot capacity.
  5. `cost.calculateEstimate`: Computes itemized expenses for activities, transit, and food.
  6. `validation.validateItinerary`: Audits budget, schedule feasibility, weather conflicts, and request integrity.

### 4. Dynamic Iteration Loop & Completion Architecture (`backend/agent/travel_agent.py`)
- **Execution Loop**: `DECIDE` → `VALIDATE` → `ACT` → `OBSERVE` → `UPDATE STATE` → `REPEAT`.
- **Deterministic Orchestrator Completion**: Before invoking the LLM for a new decision, the orchestrator evaluates whether all five planning requirements are satisfied:
  1. Complete itinerary constructed for all requested days.
  2. Usable weather coverage obtained for every requested day.
  3. Successful attraction availability verified for planned attractions.
  4. Valid route observations computed between distinct itinerary locations.
  5. Valid itemized cost estimation calculated.
  Any pending weather recovery, unresolved disruptions, failed observations, or warnings prevent early completion.
- **Truthful Provenance Recording**: When the orchestrator finishes the loop upon requirement satisfaction, it records `finish_source="orchestrator"`, `decision_provider="orchestrator"`, and `ollama_request_attempted=False`, ensuring zero false attribution.
- **Authoritative Post-Loop Validation**: After loop completion (whether from orchestrator detection or policy finish), the orchestrator executes mandatory deterministic validation via `validation.validateItinerary`. The final plan status is marked `verified` only if this authoritative validation passes.
- **Iteration Cap**: Enforces `MAX_ITERATIONS` limit (default 8) with safe fail-closed exit (`iteration_limit`).

### 5. Evidence-Based Reflection (`backend/agent/reflection.py`)
- **Independent Audit**: Audits observations trail for evidence citations (`ev_001_weather_getForecast`, `ev_002_cost_calculateEstimate`, etc.).
- **Grounded Final Output**: Generates explanations explicitly citing tool observation evidence.

### 6. Durable Execution Trace System (`traces/`)
- Every execution run saves a durable JSON trace on disk containing step reasoning, validated arguments, MCP tool invocation outputs, evidence citations, and reflection summaries.

---

## Safety & Governance Controls

| Control | Implementation |
| :--- | :--- |
| **Max Iterations** | Bounded at `MAX_ITERATIONS=8`. |
| **Tool Allowlisting** | Rejects any model action referencing unregistered tools. |
| **Pydantic Validation** | Enforces input types and required fields for all tool calls. |
| **Strict Ollama Mode** | Rejects invalid or malformed actions with fail-closed termination when strict mode is enabled. |
| **Deterministic Completion** | Terminates loop only when all 5 requirements are satisfied without pending disruptions or warnings. |
| **Truthful Provenance** | Records accurate decision provider (`ollama`, `deterministic_fallback`, `orchestrator`) in persistent trace. |
| **Request Integrity** | SHA-256 hash computed on user request parameters and verified in final validation. |
| **Authoritative Validation**| Mandatory post-loop validation gate enforces budget, weather suitability, and itinerary structure before setting `verified`. |
| **Error Handling** | Tool timeouts and HTTP failures produce structured error observations; agent never crashes. |
| **Durable Audit Trail** | Full execution history persisted to `traces/trace_{session_id}_{dest}.json`. |
| **Regression Testing** | 115 automated tests covering unit, integration, boundary, and live strict LLM workflows. |
