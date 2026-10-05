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
- **Role**: Model-mediated policy engine deciding the next action per step.
- **Provider Support**: Integrates local Ollama (`llama3.2:3b` default at `http://localhost:11434`), OpenAI API, and a deterministic state-machine fallback policy.
- **Dynamic Catalog Injection**: Automatically injects JSON Schema tool specifications from `MCPToolBoundary` into the system prompt.

### 2. Pydantic Action Validation (`backend/agent/action_models.py`)
- **Schema**: `AgentAction(action="tool"|"finish", tool_name, arguments, reasoning)`.
- **Safety Boundary**: Every model output is validated against Pydantic schema and allowlisted registered tool names. Invalid actions or malformed parameters are converted to safe error observations without crashing the agent.

### 3. MCP Tool Boundary (`backend/tools/mcp_boundary.py`)
- **In-Process Local Tool Boundary Abstraction**: Enforces one unified, in-process boundary for tool discovery, input schema definition, validation, and execution.
- **Transport Architecture**: Functions as an MCP-equivalent/inspired local tool boundary without requiring a separate background network process or JSON-RPC transport overhead.
- **Registered Tools**:
  1. `places.searchAttractions`: Discovers attractions matching user interests.
  2. `weather.getForecast`: Evaluates forecast conditions and outdoor activity suitability.
  3. `route.estimateTravel`: Calculates transit distance and time between locations.
  4. `availability.checkStatus`: Checks attraction operating hours and slot capacity.
  5. `cost.calculateEstimate`: Computes itemized expenses for activities, transit, and food.
  6. `validation.validateItinerary`: Audits budget, schedule feasibility, and weather conflicts.

### 4. Dynamic Iteration Loop (`backend/agent/travel_agent.py`)
- **Execution Loop**: `DECIDE` → `VALIDATE` → `ACT` → `OBSERVE` → `UPDATE STATE` → `REPEAT`.
- **Iteration Cap**: Enforces `MAX_ITERATIONS` limit (default 8) with safe exit.

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
| **Error Handling** | Tool timeouts and HTTP failures produce structured error observations; agent never crashes. |
| **Durable Audit Trail** | Full execution history persisted to `traces/trace_{session_id}_{dest}.json`. |
