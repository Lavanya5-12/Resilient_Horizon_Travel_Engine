"""
Resilient Horizon Travel Engine - Streamlit Main Application
Pure Python frontend integrating directly with the backend agentic travel architecture.
"""

import streamlit as st
import datetime
import json
import os
from backend.agent.travel_agent import ResilientTravelAgent
from backend.agent.planner import parse_natural_language_request

# Configure Page Layout & Title
st.set_page_config(
    page_title="Resilient Horizon Travel Engine",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for polished styling
st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 800;
        color: #0F172A;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1.1rem;
        font-weight: 500;
        color: #475569;
        margin-bottom: 1.2rem;
    }
    .recovery-box {
        background-color: #FFFBEB;
        border: 1px solid #FCD34D;
        border-radius: 12px;
        padding: 1.25rem;
        margin-bottom: 1.5rem;
    }
    .explanation-box {
        background-color: #F0FDF4;
        border: 1px solid #86EFAC;
        border-radius: 10px;
        padding: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# Application Header
st.markdown("<div class='main-title'>🌍 Resilient Horizon Travel Engine</div>", unsafe_allow_html=True)
st.markdown("<div class='sub-title'>AI-Powered Travel Decision & Recovery System</div>", unsafe_allow_html=True)
st.info("Resilient Horizon plans trips using evidence, detects travel disruptions, finds alternatives, and verifies the revised itinerary.")

# Natural-Language Travel Request Section
natural_prompt = st.text_area(
    "Describe your trip (Natural Language Request)",
    placeholder="Example: Plan a 3-day Kakinada trip under ₹10,000 for food and sightseeing.",
    height=80
)

# Sidebar Configuration
st.sidebar.header("⚙️ Trip Configuration")

sb_destination = st.sidebar.text_input("Destination", value="Goa")
sb_days = st.sidebar.number_input("Number of Days", min_value=1, max_value=14, value=4, step=1)
sb_budget = st.sidebar.number_input("Budget (₹)", min_value=1000, value=15000, step=500)
sb_interests = st.sidebar.text_input("Interests", value="Beaches, Historical Places")
travel_date = st.sidebar.date_input("Travel Date", value=datetime.date.today() + datetime.timedelta(days=14))
demo_mode = st.sidebar.toggle("Demo Mode", value=True)

generate_btn = st.sidebar.button("🚀 Generate Resilient Itinerary", use_container_width=True, type="primary")

# Initialize Travel Agent
@st.cache_resource
def get_agent():
    return ResilientTravelAgent()

agent = get_agent()

# Determine effective parameters from natural language prompt or sidebar fields
parsed_nl = parse_natural_language_request(natural_prompt) if natural_prompt else {}

effective_destination = parsed_nl.get("destination", sb_destination)
effective_days = int(parsed_nl.get("days", sb_days))
effective_budget = float(parsed_nl.get("budget", sb_budget))
effective_interests = parsed_nl.get("interests", [i.strip() for i in sb_interests.split(",") if i.strip()])

if generate_btn:
    st.markdown("### 🤖 Agent Workflow")
    
    if natural_prompt and parsed_nl:
        st.success(f"Parsed Natural Language Request: Destination = **{effective_destination}**, Days = **{effective_days}**, Budget = **₹{effective_budget:,.0f}**, Interests = **{', '.join(effective_interests)}**")

    # Workflow Progress Status Container
    workflow_status = st.status("Executing LLM Agentic Reasoning & MCP Tool Loop...", expanded=True)
    
    try:
        # Execute backend agent directly with user parameters
        date_str = travel_date.strftime("%Y-%m-%d") if travel_date else ""
        results = agent.run(
            destination=effective_destination,
            days=effective_days,
            budget=effective_budget,
            interests=effective_interests,
            travel_date=date_str,
            demo_mode=demo_mode
        )
        
        # Display backend driven stage events
        backend_stages = results.get("stages", [])
        for stage in backend_stages:
            st.write(f"• **[{stage.get('name')}]** ({stage.get('status')}): {stage.get('detail')}")

        is_valid = results.get("validation", {}).get("valid", False)
        
        if is_valid:
            workflow_status.update(label="✅ Agent Workflow Completed & Fully Verified!", state="complete", expanded=False)
        else:
            workflow_status.update(label="⚠️ Agent Workflow Completed — Plan Requires Recovery", state="error", expanded=False)

        # Update session state with new execution results
        st.session_state["travel_results"] = results

    except Exception as e:
        workflow_status.update(label="❌ Agent Execution Failed", state="error", expanded=True)
        st.error(f"An error occurred during agent execution: {str(e)}")

# Display Results if Present in Session State
if "travel_results" in st.session_state:
    data = st.session_state["travel_results"]
    req = data.get("request", {})
    metrics = data.get("metrics", {})
    val = data.get("validation", {})
    recovery = data.get("recovery", {})
    itinerary = data.get("itinerary", [])
    evidence = data.get("evidence", [])
    explanation = data.get("explanation", "")
    reflection = data.get("reflection", {})
    tech = data.get("technicalDetails", {})

    st.divider()

    # --- TRIP SUMMARY METRICS ---
    st.markdown("### 📊 Trip Summary")
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    
    col1.metric("Destination", req.get("destination", effective_destination))
    col2.metric("Duration", f"{req.get('days', effective_days)} Days")
    col3.metric("Budget", f"₹{req.get('budget', effective_budget):,.0f}")
    col4.metric("Estimated Cost", f"₹{metrics.get('totalCost', 0):,.0f}")
    
    rem_budget = metrics.get('remainingBudget', 0)
    col5.metric("Budget Remaining", f"₹{rem_budget:,.0f}", delta=f"₹{rem_budget:,.0f}" if rem_budget >= 0 else f"-₹{abs(rem_budget):,.0f}")
    col6.metric("Total Travel Time", metrics.get('totalTravelTimeFormatted', '3h 45m'))

    # --- VALIDATION STATUS ---
    st.markdown("### 🛡️ Constraint Verification")
    v_col1, v_col2, v_col3, v_col4, v_col5 = st.columns(5)

    with v_col1:
        if val.get("budgetValid", False):
            st.success("✓ Budget Valid")
        else:
            st.error("❌ Budget Exceeded")

    with v_col2:
        if val.get("timeValid", False):
            st.success("✓ Time Feasible")
        else:
            st.warning("⚠️ Tight Schedule")

    with v_col3:
        if val.get("preferencesValid", False):
            st.success("✓ Preferences Matched")
        else:
            st.info("ℹ️ Partial Match")

    with v_col4:
        if val.get("availabilityValid", False):
            st.success("✓ Availability Open")
        else:
            st.warning("⚠️ Unverified Slots")

    with v_col5:
        if val.get("valid", False):
            st.success("✓ Plan Verified")
        else:
            st.error("❌ Plan Requires Recovery")

    # Display specific validation issues if any
    if val.get("issues"):
        for issue in val.get("issues", []):
            st.warning(f"⚠️ {issue}")

    # --- RESILIENCE & RECOVERY SECTION (MAIN HIGHLIGHT) ---
    if recovery and recovery.get("occurred"):
        st.markdown("---")
        st.markdown("### 🔄 Resilience & Recovery")
        
        box_header = "⚠️ Disruption Detected & Fully Recovered" if val.get("valid", False) else "⚠️ Disruption Detected — Plan Requires Recovery"
        header_color = "#92400E" if val.get("valid", False) else "#991B1B"

        orig_activities = ", ".join(recovery.get("originalActivities", [recovery.get("originalActivity", "Outdoor Activity")]))
        repl_activities = ", ".join(recovery.get("replacementActivities", [recovery.get("replacementActivity", "Indoor Attraction")]))

        if val.get("weatherValid", False) and val.get("budgetValid", False):
            verification_text = "Revised plan avoids weather risk across all days and satisfies budget constraint"
        elif not val.get("weatherValid", False):
            verification_text = "⚠️ Plan still contains weather-affected outdoor activities"
        elif not val.get("budgetValid", False):
            verification_text = "⚠️ Plan exceeds user budget constraint limit"
        else:
            verification_text = "⚠️ Plan requires further recovery"

        st.markdown(f"""
        <div class="recovery-box">
            <h4 style="color: {header_color}; margin-top: 0;">{box_header}</h4>
            <table style="width:100%; font-size: 0.95rem; border-collapse: collapse;">
                <tr><td style="width:25%; font-weight:bold; padding: 4px 0;">Original Activity:</td><td>{orig_activities}</td></tr>
                <tr><td style="font-weight:bold; padding: 4px 0; color: #B45309;">Problem Detected:</td><td style="color: #B45309;">{recovery.get('issueDetected', 'Unfavorable weather conditions')}</td></tr>
                <tr><td style="font-weight:bold; padding: 4px 0;">Impact:</td><td>{recovery.get('impact', 'Outdoor activities unsafe due to weather alert')}</td></tr>
                <tr><td style="font-weight:bold; padding: 4px 0;">Recovery Action:</td><td>{recovery.get('recoveryAction', 'Replaced all outdoor activities on weather-affected days with indoor safe options')}</td></tr>
                <tr><td style="font-weight:bold; padding: 4px 0; color: #15803D;">Replacement Activity:</td><td style="font-weight:bold; color: #15803D;">{repl_activities}</td></tr>
                <tr><td style="font-weight:bold; padding: 4px 0;">Updated Cost/Time:</td><td>{recovery.get('recalculation', 'Cost & routes updated')}</td></tr>
                <tr><td style="font-weight:bold; padding: 4px 0;">Verification Result:</td><td><strong>{verification_text}</strong></td></tr>
            </table>
        </div>
        """, unsafe_allow_html=True)

        # --- WHY WAS MY PLAN CHANGED CARD ---
        st.markdown("#### ❓ Why was my itinerary changed?")
        st.markdown(f"""
        <div class="explanation-box">
            <p style="margin:0; color: #166534; font-size: 0.95rem; line-height: 1.5;">
                {explanation}
            </p>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

    # --- DAY-BY-DAY ITINERARY DISPLAY ---
    st.markdown("### 🗓️ Verified Itinerary")
    
    for day_item in itinerary:
        d_num = day_item.get("day", 1)
        d_title = day_item.get("title", f"Day {d_num}")
        
        with st.expander(f"📌 {d_title}", expanded=True):
            cols = st.columns(3)
            
            for idx, slot in enumerate(["morning", "afternoon", "evening"]):
                act = day_item.get(slot)
                if act and isinstance(act, dict):
                    with cols[idx]:
                        is_rec = act.get("was_recovered", False)
                        rec_badge = " <span style='background:#F59E0B; color:white; padding:2px 6px; border-radius:4px; font-size:0.75rem;'>RECOVERED</span>" if is_rec else ""
                        
                        st.markdown(f"**{slot.capitalize()}** {rec_badge}", unsafe_allow_html=True)
                        st.markdown(f"##### {act.get('activity')}")
                        st.caption(f"📍 Location: {act.get('location')}")
                        st.markdown(f"💰 **₹{act.get('cost_inr', 0):,.0f}** | ⏱️ {act.get('travel_time_mins', 20)} mins travel")
                        st.markdown("---")

    # --- EVIDENCE & TOOL OBSERVATIONS ---
    with st.expander("🔎 Evidence & Tool Observations"):
        st.caption("Structured observations returned by dynamic tools across MCP Tool Boundary:")
        for obs in evidence:
            t_name = obs.get("tool", "Unknown Tool")
            status = obs.get("status", "success")
            ev_text = obs.get("evidence", "")
            
            if status == "warning":
                st.warning(f"**{t_name}** | status: {status.upper()}\n\n{ev_text}")
            elif status == "error":
                st.error(f"**{t_name}** | status: {status.upper()}\n\n{ev_text}")
            else:
                st.success(f"**{t_name}** | status: {status.upper()}\n\n{ev_text}")

    # --- TECHNICAL DETAILS ---
    with st.expander("⚙️ Technical Details & Saved Execution Trace"):
        trace_file = data.get("trace_file", "None")
        st.markdown(f"""
        - **LLM Policy Model**: `{tech.get('llmModel', 'llama3.2:3b')}`
        - **Provider Used**: `{tech.get('providerUsed', 'Demo Provider')}`
        - **Agent Iterations Used**: `{tech.get('iterationCount', 2)} / {data.get('metrics', {}).get('maxIterations', 8)}`
        - **MCP Tools Executed**: `{', '.join(tech.get('toolsExecuted', []))}`
        - **Saved Durable Trace File**: `{trace_file}`
        """)
        
        st.markdown("#### Simplified Architecture Flow")
        st.code("""
User Request (Sidebar / Natural Language Prompt)
    ↓
LLM Policy Engine (backend/agent/llm_policy.py)
    ↓
Validated AgentAction (backend/agent/action_models.py)
    ↓
MCP Tool Boundary (backend/tools/mcp_boundary.py)
    ↓
Tools (places, weather, route, availability, cost, validation)
    ↓
Structured ToolObservations (Evidence Trail)
    ↓
Disruption Recovery & Replanning (backend/agent/recovery.py)
    ↓
Evidence-Based Reflection (backend/agent/reflection.py)
    ↓
Saved Durable Trace File (traces/trace_*.json)
    ↓
Streamlit Dashboard (app.py)
        """, language="text")

        st.markdown("#### Evidence Citations & Audit")
        st.json(reflection.get("evidence_citations", []))

        st.markdown("#### Raw Agent Payload")
        st.json(data)
