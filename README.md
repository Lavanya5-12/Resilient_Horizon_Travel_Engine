# Resilient Horizon Travel Engine (L2 Agent Edition)

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-green.svg)](https://fastapi.tiangolo.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.30%2B-red.svg)](https://streamlit.io/)
[![MCP-Equivalent Boundary](https://img.shields.io/badge/MCP--Equivalent-Local%20Tool%20Boundary-purple.svg)](docs/L2_AGENT_ARCHITECTURE.md)

**Resilient Horizon Travel Engine** is an AI-powered L2 agentic travel planning and disruption recovery platform. The application uses a model-mediated policy layer (`DECIDE` → `VALIDATE` → `ACT` → `OBSERVE` → `REPEAT`) across an **in-process MCP-equivalent tool boundary**, featuring evidence-based reflection, durable trace recording, dynamic tool selection, and support for arbitrary travel destinations (e.g., Kakinada, Hyderabad, Mumbai, Goa).

---

## Architecture Overview

```mermaid
graph TD
    User([User Request]) --> Streamlit[Streamlit / FastAPI UI]
    Streamlit --> LLMPolicy[LLM Policy Engine]
    LLMPolicy --> ActionValidation[AgentAction Pydantic Validation]
    ActionValidation --> MCPBoundary[MCP Tool Boundary (In-Process)]
    
    MCPBoundary --> PlacesTool[places.searchAttractions]
    MCPBoundary --> WeatherTool[weather.getForecast]
    MCPBoundary --> RouteTool[route.estimateTravel]
    MCPBoundary --> AvailabilityTool[availability.checkStatus]
    MCPBoundary --> CostTool[cost.calculateEstimate]
    MCPBoundary --> ValidationTool[validation.validateItinerary]
    
    PlacesTool --> Observations[Structured Tool Observations]
    WeatherTool --> Observations
    RouteTool --> Observations
    AvailabilityTool --> Observations
    CostTool --> Observations
    ValidationTool --> Observations
    
    Observations --> RecoveryEngine[Disruption Recovery Engine]
    RecoveryEngine --> Reflection[Evidence-Based Reflection]
    Reflection --> FinalAnswer[Grounded Final Itinerary & Saved Trace]
```

---

## Key L2 Features

1. **Genuine LLM Policy Layer**: Model-mediated tool decision making supporting Ollama (`llama3.2:3b`), OpenAI API, and deterministic fallback solver.
2. **Strict Pydantic Action Schema**: `AgentAction(action="tool"|"finish", tool_name, arguments, reasoning)` validated before execution. Rejects unknown tools and malformed parameters safely.
3. **MCP Tool Boundary Abstraction**: All 6 dynamic tools (`places`, `weather`, `route`, `availability`, `cost`, `validation`) execute strictly across an in-process `MCPToolBoundary` providing tool discovery, input validation, and structured observations without requiring a networked JSON-RPC transport process.
4. **Arbitrary Destination Support**: Supports any city (e.g. Kakinada, Hyderabad, Mumbai, Delhi, Jaipur, Goa) without falling back to hardcoded defaults.
5. **Durable Agent Traces**: Every execution trace is saved to `traces/trace_{session_id}_{dest}.json`.
6. **Live Weather Integration**: `RealProvider` queries live real-world weather data via Open-Meteo HTTP API with timeout and error handling.
7. **Deterministic Goa Demo Mode**: Reliable reproduction of weather disruptions and indoor replacements.
8. **Automated Pytest Suite**: 18 unit and integration tests covering recovery, arbitrary destinations, action validation, tool failures, budget checks, and API endpoints.

---

## Registered MCP Tool Catalog

| Tool Name | Description | Input Schema |
| :--- | :--- | :--- |
| `places.searchAttractions` | Finds attractions matching user interests | `destination: str`, `interests: list`, `indoor_only: bool` |
| `weather.getForecast` | Evaluates forecast conditions and outdoor suitability | `destination: str`, `day: int`, `date: str` |
| `route.estimateTravel` | Calculates transit distance and time | `origin: str`, `destination: str`, `mode: str` |
| `availability.checkStatus` | Verifies attraction opening hours and capacity | `attraction_name: str`, `date: str`, `time_of_day: str` |
| `cost.calculateEstimate` | Computes itemized activity, transit, and food costs | `activities: list`, `transit_costs: float` |
| `validation.validateItinerary` | Audits budget, schedule, and weather compliance | `itinerary: list`, `budget_inr: float`, `interests: list` |

---

## Installation & Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Optional: Run Local Ollama LLM Model
```bash
ollama pull llama3.2:3b
ollama run llama3.2:3b
```
*(If Ollama is not running, the policy engine automatically uses its built-in solver seamlessly).*

---

## Running the Application

### Option A: Run Streamlit User Interface
```bash
streamlit run app.py
```
Open your browser at **`http://localhost:8501`**.

### Option B: Run FastAPI REST API Server
```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```
API Documentation available at **`http://localhost:8000/docs`**.

---

## Running Automated Tests

Run the complete 18-test suite with Pytest:
```bash
python -m pytest -v
```

---

## Example Execution Scenarios

### Scenario 1: Kakinada Arbitrary Destination
- **Input**: `"Plan a 3-day Kakinada trip under ₹10,000 for food and sightseeing."`
- **Output**: 3-day Kakinada itinerary, budget verified against ₹10,000, evidence citations saved to `traces/trace_*_kakinada.json`.

### Scenario 2: Goa Disruption Recovery (Demo Mode)
- **Input**: Goa 4 days, Budget ₹15,000.
- **Output**: Detects Day 2 weather alert, replaces outdoor beach activity with indoor museum, verifies revised cost (₹13,700), and outputs evidence explanation.
