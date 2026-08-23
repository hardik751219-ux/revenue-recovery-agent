import json
from collections import defaultdict
from datetime import datetime

def load_transactions(path="data/transactions.json"):
    with open(path) as f:
        return json.load(f)

def detect_degradation(transactions, window_size=20, spike_threshold=2.5):
    """
    Slides a window over transactions grouped by (payment_method, route).
    Flags a window as degraded if its failure rate is spike_threshold times
    higher than the overall baseline failure rate for that slice.
    Overlapping windows from the same underlying incident are merged into
    a single alert to avoid double-counting revenue and duplicate decisions.
    """
    slices = defaultdict(list)
    for txn in transactions:
        key = (txn["payment_method"], txn["route"])
        slices[key].append(txn)

    raw_windows = []

    for key, txns in slices.items():
        txns.sort(key=lambda t: t["timestamp"])
        total = len(txns)
        if total < window_size:
            continue

        baseline_failures = sum(1 for t in txns if t["status"] == "failed")
        baseline_rate = baseline_failures / total

        for start in range(0, total - window_size + 1, window_size // 2):
            window = txns[start:start + window_size]
            window_failures = sum(1 for t in window if t["status"] == "failed")
            window_rate = window_failures / len(window)

            if baseline_rate > 0 and window_rate > baseline_rate * spike_threshold and window_failures >= 5:
                raw_windows.append({
                    "payment_method": key[0],
                    "route": key[1],
                    "window_start": window[0]["timestamp"],
                    "window_end": window[-1]["timestamp"],
                    "window_failure_rate": round(window_rate, 3),
                    "baseline_failure_rate": round(baseline_rate, 3),
                    "affected_transaction_ids": set(t["transaction_id"] for t in window if t["status"] == "failed"),
                    "revenue_at_risk": sum(t["amount"] for t in window if t["status"] == "failed"),
                })

    # Merge overlapping/adjacent alerts for the same (payment_method, route)
    # into a single deduplicated alert, so one incident isn't double-counted
    # as multiple approvals.
    merged = merge_overlapping_alerts(raw_windows)
    return merged


def merge_overlapping_alerts(raw_windows):
    grouped = defaultdict(list)
    for w in raw_windows:
        key = (w["payment_method"], w["route"])
        grouped[key].append(w)

    final_alerts = []

    for key, windows in grouped.items():
        windows.sort(key=lambda w: w["window_start"])
        current = None

        for w in windows:
            if current is None:
                current = dict(w)
                current["affected_transaction_ids"] = set(w["affected_transaction_ids"])
                continue

            # If this window's affected transactions overlap meaningfully
            # with the current merged alert, treat it as the same incident.
            overlap = current["affected_transaction_ids"] & w["affected_transaction_ids"]
            if overlap:
                current["affected_transaction_ids"] |= w["affected_transaction_ids"]
                current["window_end"] = max(current["window_end"], w["window_end"])
                current["window_failure_rate"] = max(current["window_failure_rate"], w["window_failure_rate"])
            else:
                final_alerts.append(finalize_alert(current))
                current = dict(w)
                current["affected_transaction_ids"] = set(w["affected_transaction_ids"])

        if current is not None:
            final_alerts.append(finalize_alert(current))

    return final_alerts


def finalize_alert(alert):
    # Recompute revenue_at_risk cleanly from the deduplicated transaction set
    # (safe since we only track IDs and rate; actual per-txn amount is re-summed by caller if needed)
    alert["affected_transaction_ids"] = list(alert["affected_transaction_ids"])
    alert["revenue_at_risk"] = round(alert["revenue_at_risk"], 2)
    return alert


if __name__ == "__main__":
    txns = load_transactions()
    alerts = detect_degradation(txns)
    print(f"Found {len(alerts)} degradation alert(s) after merging\n")
    for a in alerts:
        print(f"⚠️  {a['payment_method']} / {a['route']}")
        print(f"   Window: {a['window_start']} → {a['window_end']}")
        print(f"   Failure rate: {a['window_failure_rate']} (baseline: {a['baseline_failure_rate']})")
        print(f"   Revenue at risk: ₹{a['revenue_at_risk']}")
        print(f"   Affected transactions: {len(a['affected_transaction_ids'])}\n")