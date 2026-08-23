from collections import Counter

# Which failure codes are recoverable, and how
RECOVERY_MAP = {
    "BANK_SERVER_DOWN": {"recoverable": True, "action": "retry"},
    "ROUTE_DEGRADED": {"recoverable": True, "action": "reroute"},
    "TIMEOUT": {"recoverable": True, "action": "retry"},
    "INSUFFICIENT_FUNDS": {"recoverable": False, "action": "notify_customer"},
    "INVALID_VPA": {"recoverable": False, "action": "notify_customer"},
    "RISK_BLOCKED": {"recoverable": False, "action": "escalate_only"},
}

def classify_alert(alert, transactions):
    """
    Given an alert (from the detector) and the full transaction list,
    determine the dominant failure reason and the recommended action.
    """
    affected_ids = set(alert["affected_transaction_ids"])
    reasons = [
        t["failure_reason_code"] for t in transactions
        if t["transaction_id"] in affected_ids and t["failure_reason_code"]
    ]

    if not reasons:
        return {**alert, "root_cause": "UNKNOWN", "recoverable": False, "recommended_action": "escalate_only", "confidence": 0.0}

    reason_counts = Counter(reasons)
    dominant_reason, count = reason_counts.most_common(1)[0]
    confidence = round(count / len(reasons), 2)

    mapping = RECOVERY_MAP.get(dominant_reason, {"recoverable": False, "action": "escalate_only"})

    return {
        **alert,
        "root_cause": dominant_reason,
        "reason_breakdown": dict(reason_counts),
        "confidence": confidence,
        "recoverable": mapping["recoverable"],
        "recommended_action": mapping["action"]
    }

if __name__ == "__main__":
    from .detector import load_transactions, detect_degradation

    txns = load_transactions()
    alerts = detect_degradation(txns)
    classified = [classify_alert(a, txns) for a in alerts]

    for c in classified:
        print(f"⚠️  {c['payment_method']} / {c['route']}")
        print(f"   Root cause: {c['root_cause']} (confidence: {c['confidence']})")
        print(f"   Reason breakdown: {c['reason_breakdown']}")
        print(f"   Recoverable: {c['recoverable']} → action: {c['recommended_action']}")
        print(f"   Revenue at risk: ₹{c['revenue_at_risk']}\n")