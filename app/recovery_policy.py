import json
from datetime import datetime, UTC
from .razorpay_client import create_recovery_order, create_recovery_order_simulated_failure
from .llm_reasoner import get_agent_reasoning

MIN_CONFIDENCE = 0.5
MAX_RETRIES = 2
NEVER_RETRY_CODES = {"RISK_BLOCKED"}

retry_tracker = {}


def get_alert_key(classified_alert):
    return f"{classified_alert['payment_method']}_{classified_alert['route']}"


def evaluate_recovery(classified_alert, simulate_failure=False, tracker=None):
    if tracker is None:
        tracker = retry_tracker

    root_cause = classified_alert["root_cause"]
    confidence = classified_alert["confidence"]
    recommended_action = classified_alert["recommended_action"]

    decision = {
        "timestamp": datetime.now(UTC).isoformat(),
        "payment_method": classified_alert["payment_method"],
        "route": classified_alert["route"],
        "root_cause": root_cause,
        "confidence": confidence,
        "revenue_at_risk": classified_alert["revenue_at_risk"],
        "affected_count": len(classified_alert["affected_transaction_ids"]),
        "agent_reasoning": None,
        "agent_flagged": False,
    }

    if root_cause in NEVER_RETRY_CODES:
        decision["status"] = "BLOCKED"
        decision["reason"] = "policy: never_retry_code"
        decision["action_taken"] = None
        decision["revenue_recovered"] = 0
        return decision

    if not classified_alert["recoverable"]:
        decision["status"] = "ESCALATED"
        decision["reason"] = "not_recoverable_type"
        decision["action_taken"] = "notify_customer"
        decision["revenue_recovered"] = 0
        return decision

    if confidence < MIN_CONFIDENCE:
        decision["status"] = "ESCALATED"
        decision["reason"] = f"confidence_below_threshold ({confidence} < {MIN_CONFIDENCE})"
        decision["action_taken"] = None
        decision["revenue_recovered"] = 0
        return decision

    # Passed hard bound checker — now consult the advisory reasoning layer.
    # This layer can only add caution/flags, it cannot override an approval.
    agent_result = get_agent_reasoning(classified_alert)
    decision["agent_reasoning"] = agent_result["reasoning"]
    decision["agent_flagged"] = agent_result["flagged"]

    decision["status"] = "APPROVED"
    decision["reason"] = "passed_all_bounds"
    decision["action_taken"] = recommended_action

    alert_key = get_alert_key(classified_alert)
    attempt = tracker.get(alert_key, 0)

    if attempt >= MAX_RETRIES:
        decision["status"] = "RECOVERY_ABANDONED"
        decision["reason"] = f"max_retries_exceeded ({attempt}/{MAX_RETRIES})"
        decision["action_taken"] = None
        decision["revenue_recovered"] = 0
        decision["execution_status"] = "stopped_no_infinite_retry"
        return decision

    receipt_id = f"recovery_{classified_alert['payment_method']}_{classified_alert['route']}_{int(datetime.now(UTC).timestamp())}"

    call_fn = create_recovery_order_simulated_failure if simulate_failure else create_recovery_order
    result = call_fn(classified_alert["revenue_at_risk"], receipt_id)

    if result["success"]:
        decision["razorpay_order_id"] = result["order"]["id"]
        decision["execution_status"] = "order_created"
        decision["revenue_recovered"] = classified_alert["revenue_at_risk"]
        decision["attempt_number"] = attempt + 1
        tracker[alert_key] = 0
    else:
        tracker[alert_key] = attempt + 1
        decision["razorpay_order_id"] = None
        decision["execution_status"] = "failed"
        decision["execution_error"] = result["error"]
        decision["revenue_recovered"] = 0
        decision["attempt_number"] = attempt + 1
        decision["status"] = "RETRY_SCHEDULED" if (attempt + 1) < MAX_RETRIES else "RECOVERY_ABANDONED"

    return decision


def run_batch(classified_alerts):
    return [evaluate_recovery(a) for a in classified_alerts]


if __name__ == "__main__":
    from .detector import load_transactions, detect_degradation
    from .root_cause import classify_alert

    txns = load_transactions()
    alerts = detect_degradation(txns)
    classified = [classify_alert(a, txns) for a in alerts]
    audit_log = run_batch(classified)

    total_at_risk = sum(d["revenue_at_risk"] for d in audit_log)
    total_recovered = sum(d["revenue_recovered"] for d in audit_log)

    for d in audit_log:
        print(f"[{d['status']}] {d['payment_method']}/{d['route']} — {d['root_cause']}")
        print(f"   Reason: {d['reason']}")
        if d.get("agent_reasoning"):
            print(f"   Agent note: {d['agent_reasoning']}")
        print(f"   Action: {d['action_taken']}")
        if d.get("razorpay_order_id"):
            print(f"   Razorpay order: {d['razorpay_order_id']}")
        print(f"   Revenue at risk: ₹{d['revenue_at_risk']} | Recovered: ₹{d['revenue_recovered']}\n")

    print("=" * 50)
    print("BATCH SUMMARY")
    print(f"Total revenue at risk: ₹{round(total_at_risk, 2)}")
    print(f"Total revenue recovered: ₹{round(total_recovered, 2)}")
    print(f"Recovery rate: {round(total_recovered/total_at_risk*100, 1)}%")

    with open("data/audit_log.json", "w") as f:
        json.dump(audit_log, f, indent=2)
    print(f"\nAudit log written: {len(audit_log)} decisions")