import json
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .detector import load_transactions, detect_degradation
from .root_cause import classify_alert
from .recovery_policy import evaluate_recovery, run_batch
from .synthetic_data import generate_transactions

app = FastAPI(title="Revenue Recovery Agent")

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/dashboard")
def dashboard():
    return FileResponse("app/static/dashboard.html")


@app.get("/")
def root():
    return {"status": "ok", "service": "revenue-recovery-agent"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/transactions/summary")
def transactions_summary():
    """Quick overview of the synthetic transaction dataset."""
    txns = load_transactions()
    total = len(txns)
    failed = sum(1 for t in txns if t["status"] == "failed")
    return {
        "total_transactions": total,
        "failed_transactions": failed,
        "failure_rate": round(failed / total, 3),
    }


@app.post("/transactions/regenerate")
def regenerate_transactions():
    """Generates a fresh batch of synthetic transactions and saves them."""
    data = generate_transactions()
    with open("data/transactions.json", "w") as f:
        json.dump(data, f, indent=2)
    failed = sum(1 for t in data if t["status"] == "failed")
    return {
        "message": "Fresh transaction batch generated",
        "total_transactions": len(data),
        "failed_transactions": failed
    }


@app.get("/alerts")
def get_alerts():
    """Run the detector and return raw degradation alerts."""
    txns = load_transactions()
    alerts = detect_degradation(txns)
    return {"count": len(alerts), "alerts": alerts}


@app.get("/alerts/classified")
def get_classified_alerts():
    """Run detector + root-cause classifier together."""
    txns = load_transactions()
    alerts = detect_degradation(txns)
    classified = [classify_alert(a, txns) for a in alerts]
    return {"count": len(classified), "alerts": classified}


@app.post("/recovery/run")
def run_recovery():
    """
    Full pipeline: detect -> classify -> evaluate policy -> execute
    approved recovery actions via Razorpay test-mode -> return audit log
    and batch summary.
    """
    txns = load_transactions()
    alerts = detect_degradation(txns)
    classified = [classify_alert(a, txns) for a in alerts]
    audit_log = run_batch(classified)

    total_at_risk = sum(d["revenue_at_risk"] for d in audit_log)
    total_recovered = sum(d["revenue_recovered"] for d in audit_log)
    recovery_rate = round(total_recovered / total_at_risk * 100, 1) if total_at_risk > 0 else 0

    status_counts = {}
    for d in audit_log:
        status_counts[d["status"]] = status_counts.get(d["status"], 0) + 1

    with open("data/audit_log.json", "w") as f:
        json.dump(audit_log, f, indent=2)

    return {
        "summary": {
            "total_revenue_at_risk": round(total_at_risk, 2),
            "total_revenue_recovered": round(total_recovered, 2),
            "recovery_rate_pct": recovery_rate,
            "status_breakdown": status_counts,
        },
        "audit_log": audit_log,
    }

@app.post("/recovery/simulate-failure")
def simulate_failure_demo():
    """
    Deliberately triggers repeated failures on the current best recovery
    candidate to demonstrate bounded retry and graceful abandonment.
    Uses an isolated tracker so it never consumes retry budget from
    the real recovery pipeline's state.
    """
    txns = load_transactions()
    alerts = detect_degradation(txns)
    classified = [classify_alert(a, txns) for a in alerts]

    candidates = [c for c in classified if c["recoverable"] and c["confidence"] >= 0.5]
    if not candidates:
        return {"error": "No recoverable candidate available in current data. Try regenerating data first."}

    target = candidates[0]
    demo_tracker = {}  # isolated — doesn't touch the real pipeline's retry_tracker
    attempts = []

    for i in range(1, 4):
        d = evaluate_recovery(target, simulate_failure=True, tracker=demo_tracker)
        attempts.append({
            "attempt_number": i,
            "status": d["status"],
            "reason": d["reason"],
        })

    return {
        "segment": f"{target['payment_method']} / {target['route']}",
        "root_cause": target["root_cause"],
        "attempts": attempts
    }

@app.get("/audit-log")
def get_audit_log():
    """Return the most recently saved audit log."""
    try:
        with open("data/audit_log.json") as f:
            log = json.load(f)
        return {"count": len(log), "audit_log": log}
    except FileNotFoundError:
        return {"count": 0, "audit_log": [], "note": "No audit log yet — call POST /recovery/run first"}