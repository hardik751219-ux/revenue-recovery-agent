from detector import load_transactions, detect_degradation
from root_cause import classify_alert
from recovery_policy import evaluate_recovery

txns = load_transactions()
alerts = detect_degradation(txns)
classified = [classify_alert(a, txns) for a in alerts]

# Grab the one alert that would normally be approved
approved = [c for c in classified if c["recoverable"] and c["confidence"] >= 0.5][0]

print(f"Simulating repeated failures for: {approved['payment_method']}/{approved['route']}\n")

for i in range(1, 4):
    d = evaluate_recovery(approved, simulate_failure=True)
    print(f"Attempt {i}: [{d['status']}] — {d['reason']}")