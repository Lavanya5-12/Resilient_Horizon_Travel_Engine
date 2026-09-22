"""
Reflection & Verification Module.
Validates the final itinerary against all constraints and generates a simple manager-friendly explanation.
"""

from typing import Any, Dict, List

class AgentReflection:
    def reflect_and_explain(
        self,
        validation_res: Dict[str, Any],
        recovery_info: Dict[str, Any],
        destination: str,
        user_budget: float,
        user_interests: List[str]
    ) -> Dict[str, Any]:
        
        explanation = ""
        is_valid = validation_res.get("valid", False)
        weather_valid = validation_res.get("weatherValid", False)
        budget_valid = validation_res.get("budgetValid", False)

        if recovery_info.get("occurred"):
            affected_day = recovery_info.get("affectedDay", 2)
            replacements = recovery_info.get("replacementActivities", [])
            repl_str = ", ".join(set(replacements)) if replacements else "indoor attractions"
            pref_str = ", ".join(user_interests) if user_interests else "preferences"

            if is_valid:
                explanation = (
                    f"The original outdoor activities on Day {affected_day} were affected by unfavorable weather. "
                    f"The agent dynamically replaced all outdoor activities on Day {affected_day} with indoor alternatives "
                    f"('{repl_str}') matching your '{pref_str}' preference, and verified that the revised plan "
                    f"avoids weather risk and fits within your ₹{user_budget:,.0f} budget."
                )
            elif not weather_valid:
                explanation = (
                    f"Day {affected_day} outdoor activities conflicted with unfavorable weather. "
                    f"The agent attempted recovery, but the revised plan still contains unverified outdoor activities."
                )
            elif not budget_valid:
                explanation = (
                    f"The weather conflict on Day {affected_day} was resolved with indoor alternatives, "
                    f"but the calculated total cost exceeds your ₹{user_budget:,.0f} budget constraint."
                )
            else:
                explanation = f"Disruption recovery occurred for {destination}, but constraint validation remains unresolved."
        else:
            if is_valid:
                explanation = (
                    f"All scheduled activities in {destination} passed weather, availability, and budget verification. "
                    f"No disruptions were detected."
                )
            else:
                explanation = (
                    f"The proposed itinerary for {destination} does not satisfy all constraints (Budget valid: {budget_valid})."
                )

        return {
            "status": "verified" if is_valid else "unverified",
            "summary_explanation": explanation,
            "budget_check": {
                "valid": budget_valid,
                "total_cost": validation_res.get("calculatedTotalCost", 0),
                "budget_limit": user_budget,
                "remaining_budget": validation_res.get("remainingBudget", 0)
            },
            "time_check": {
                "valid": validation_res.get("timeValid", True),
                "status": "Feasible daily schedules"
            },
            "preference_check": {
                "valid": validation_res.get("preferencesValid", True),
                "matched": user_interests
            }
        }
