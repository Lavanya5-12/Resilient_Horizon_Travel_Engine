"""
Resilient Horizon Travel Engine - Streamlit Main Application
Pure Python frontend integrating directly with the backend agentic travel architecture.
"""

import streamlit as st
import datetime
import json
import time
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
    placeholder="Example: Plan a 4-day Goa trip under ₹15,000 with beaches and historical places.",
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
    workflow_status = st.status("Initializing agent reasoning loop...", expanded=True)
    
    try:
        workflow_status.write(f"1️⃣ **UNDERSTAND**: Parsing travel goals ({effective_destination}, {effective_days} Days, ₹{effective_budget:,.0f} Budget)...")
        time.sleep(0.2)
        
        workflow_status.write(f"2️⃣ **PLAN**: Dynamic tool selection & querying attractions registry for {effective_destination}...")
        time.sleep(0.2)
        
        workflow_status.write("3️⃣ **OBSERVE**: Checking forecast weather and attraction availability...")
        time.sleep(0.2)
        
        workflow_status.write("4️⃣ **DETECT**: Evaluating weather conditions against scheduled activities...")
        time.sleep(0.2)

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
        
        recovery_occurred = results.get("recovery", {}).get("occurred", False)
        is_valid = results.get("validation", {}).get("valid", False)

        if recovery_occurred:
            workflow_status.write("5️⃣ **RECOVER**: ⚠️ Weather disruption detected! Replacing ALL outdoor activities with indoor safe options.")
            time.sleep(0.2)
        else:
            workflow_status.write("5️⃣ **RECOVER**: No disruptions detected. Current itinerary verified.")
            time.sleep(0.2)
            
        workflow_status.write("6️⃣ **VERIFY**: Running post-recovery validation on revised itinerary...")
        time.sleep(0.2)
        
        workflow_status.write("7️⃣ **FINAL PLAN**: Synthesizing verified resilient itinerary.")
        
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
        st.caption("Structured observations returned by dynamic tools during reasoning loop:")
        for obs in evidence:
            t_name = obs.get("tool", "Unknown Tool")
            status = obs.get("status", "success")
            ev_text = obs.get("evidence", "")
            
            if status == "warning":
                st.warning(f"**{t_name}** | status: {status.upper()}\n\n{ev_text}")
            else:
                st.success(f"**{t_name}** | status: {status.upper()}\n\n{ev_text}")

    # --- TECHNICAL DETAILS ---
    with st.expander("⚙️ Technical Details"):
        st.markdown(f"""
        - **Provider Used**: `{tech.get('providerUsed', 'Demo Provider')}`
        - **Agent Iterations Used**: `{tech.get('iterationCount', 2)} / {data.get('metrics', {}).get('maxIterations', 5)}`
        - **Tools Executed**: `{', '.join(tech.get('toolsExecuted', []))}`
        - **Demo Mode**: `{tech.get('isDemoMode', True)}`
        """)
        
        st.markdown("#### Simplified Architecture Flow")
        st.code("""
User Request (Sidebar / Natural Language Prompt)
    ↓
Streamlit (app.py)
    ↓
Travel Agent (travel_agent.py)
    ↓
Dynamic Tool Selection (ToolRegistry)
    ↓
Weather / Places / Route / Cost / Availability Tools
    ↓
Structured Observations
    ↓
Conflict Detection & Disruption Recovery
    ↓
Constraint Validation (Budget / Time / Preferences)
    ↓
Reflection & Explanation
    ↓
Final Verified Itinerary
        """, language="text")

        st.markdown("#### Raw Agent Payload")
        st.json(data)
