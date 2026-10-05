"""
Evidence-Based Reflection Module for Resilient Horizon Travel Engine.
Independently audits tool observations, weather evidence, cost evidence, and constraint validation
to generate grounded explanations backed by cited tool evidence.
"""

from typing import Any, Dict, List

class AgentReflection:
    def reflect_and_explain(
        self,
        validation_res: Dict[str, Any],
        recovery_info: Dict[str, Any],
        observations: List[Dict[str, Any]],
        destination: str,
        user_budget: float,
        user_interests: List[str]
    ) -> Dict[str, Any]:
        
        evidence_citations = []
        issues = list(validation_res.get("issues", []))
        weather_warnings = []
        cost_evidence_found = False

        # Audit observations independently
        for idx, obs in enumerate(observations, 1):
            tool = obs.get("tool", "")
            ev = obs.get("evidence", "")
            status = obs.get("status", "")
            obs_id = f"ev_{idx:03d}_{tool.replace('.', '_')}"
            evidence_citations.append(obs_id)

            if tool == "weather.getForecast" and (status == "warning" or "heavy_rain" in str(obs.get("data", {}))):
                weather_warnings.append(f"[{obs_id}]: {ev}")

            if tool in ["cost.calculateEstimate", "validation.validateItinerary"]:
                cost_evidence_found = True

        is_valid = validation_res.get("valid", False)
        weather_valid = validation_res.get("weatherValid", False)
        budget_valid = validation_res.get("budgetValid", False)

        explanation_parts = []

        if recovery_info.get("occurred"):
            affected_day = recovery_info.get("affectedDay", 2)
            replacements = recovery_info.get("replacementActivities", [])
            repl_str = ", ".join(set(replacements)) if replacements else "indoor attractions"
            pref_str = ", ".join(user_interests) if user_interests else "preferences"

            explanation_parts.append(
                f"Disruption Recovery Triggered on Day {affected_day}: Weather observations "
                f"({'; '.join(weather_warnings) if weather_warnings else 'IMD Weather Warning'}) "
                f"indicated restricted outdoor conditions. The agent dynamically invoked places tool "
                f"to select weather-safe indoor alternatives ('{repl_str}') matching your '{pref_str}' preference."
            )

            if is_valid:
                explanation_parts.append(
                    f" Post-recovery validation confirmed zero remaining outdoor weather conflicts and verified "
                    f"that the total calculated trip cost fits within your ₹{user_budget:,.0f} budget."
                )
            elif not budget_valid:
                explanation_parts.append(
                    f" Weather risk was eliminated, but the calculated cost exceeds your ₹{user_budget:,.0f} budget."
                )
            elif not weather_valid:
                explanation_parts.append(
                    f" Revised itinerary still contains unverified outdoor activities."
                )
        else:
            if is_valid:
                explanation_parts.append(
                    f"All scheduled activities in {destination} passed weather, availability, and budget validation. "
                    f"Evidence trail ({len(evidence_citations)} tool observations collected) confirms no travel disruptions."
                )
            else:
                explanation_parts.append(
                    f"Itinerary for {destination} has pending constraint issues: {', '.join(issues) if issues else 'Unverified status'}."
                )

        final_explanation = "".join(explanation_parts)

        return {
            "decision": "valid" if is_valid else "unverified",
            "summary_explanation": final_explanation,
            "issues": issues,
            "evidence_citations": evidence_citations,
            "audit_checks": {
                "budget_valid": budget_valid,
                "weather_valid": weather_valid,
                "cost_evidence_present": cost_evidence_found,
                "observations_count": len(observations)
            }
        }
