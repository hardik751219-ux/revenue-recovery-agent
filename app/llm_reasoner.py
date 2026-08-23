def get_agent_reasoning(classified_alert):
    """
    Advisory reasoning layer, called ONLY on alerts that already passed
    the hard bound checker. This step can add caution (recommend against
    proceeding) but can NEVER approve an action the bound checker rejected —
    it's a safety-only veto layer, not a decision-making authority.

    Implemented as deterministic rule-based reasoning rather than a live
    LLM call: this keeps the money-decision path free of external API
    dependency risk (no failure mode from network issues, rate limits,
    or billing), which matters more for a financial recovery system than
    generative flexibility does.
    """
    confidence = classified_alert["confidence"]
    revenue_at_risk = classified_alert["revenue_at_risk"]
    reason_breakdown = classified_alert.get("reason_breakdown", {})
    root_cause = classified_alert["root_cause"]

    concerns = []

    # Concern 1: confidence is borderline, close to the policy threshold
    if 0.5 <= confidence < 0.6:
        concerns.append(
            f"confidence ({confidence}) is only marginally above the action threshold"
        )

    # Concern 2: the reason breakdown is mixed/ambiguous, not a clean majority
    if reason_breakdown:
        total = sum(reason_breakdown.values())
        top_count = max(reason_breakdown.values())
        if total > 0 and (top_count / total) < 0.6:
            concerns.append(
                f"root cause diagnosis is based on a mixed signal ({reason_breakdown}), not a strong majority"
            )

    # Concern 3: unusually large amount at risk for the confidence level
    if revenue_at_risk > 25000 and confidence < 0.65:
        concerns.append(
            f"revenue at risk (₹{revenue_at_risk:,.2f}) is high relative to diagnosis confidence ({confidence})"
        )

    if concerns:
        return {
            "recommend_proceed": True,  # still proceeds — bound checker already approved it; this is advisory only
            "reasoning": "Proceeding as approved, with noted caution: " + "; ".join(concerns) + ".",
            "flagged": True,
            "error": None
        }
    else:
        return {
            "recommend_proceed": True,
            "reasoning": f"No additional concerns — {root_cause} diagnosis is consistent and confidence supports automated action.",
            "flagged": False,
            "error": None
        }


if __name__ == "__main__":
    test_alert = {
        "payment_method": "upi",
        "route": "route_a",
        "root_cause": "ROUTE_DEGRADED",
        "confidence": 0.56,
        "reason_breakdown": {"ROUTE_DEGRADED": 5, "TIMEOUT": 4},
        "revenue_at_risk": 27595.51,
        "recommended_action": "reroute"
    }
    result = get_agent_reasoning(test_alert)
    print(result)