import random
import json
from datetime import datetime, timedelta

def generate_transactions(n=500):
    transactions = []
    base_time = datetime(2026, 8, 20, 9, 0, 0)
    
    for i in range(n):
        ts = base_time + timedelta(minutes=i * 2)
        in_degradation_window = 100 <= i <= 160
        
        payment_method = random.choice(["upi", "card", "netbanking", "wallet"])
        route = "route_a" if payment_method == "upi" else "route_b"
        
        if in_degradation_window and payment_method == "upi" and route == "route_a":
            fail_chance = 0.75
            reason_pool = ["ROUTE_DEGRADED", "TIMEOUT"]
        else:
            fail_chance = 0.08
            reason_pool = ["INSUFFICIENT_FUNDS", "INVALID_VPA", "RISK_BLOCKED", "TIMEOUT"]
        
        failed = random.random() < fail_chance
        status = "failed" if failed else "success"
        reason = random.choice(reason_pool) if failed else None
        
        transactions.append({
            "transaction_id": f"TXN{i:05d}",
            "timestamp": ts.isoformat(),
            "amount": round(random.uniform(100, 5000), 2),
            "currency": "INR",
            "payment_method": payment_method,
            "status": status,
            "failure_reason_code": reason,
            "customer_id": f"CUST{random.randint(1, 150):04d}",
            "route": route,
            "retry_count": 0
        })
    
    return transactions

if __name__ == "__main__":
    data = generate_transactions()
    with open("data/transactions.json", "w") as f:
        json.dump(data, f, indent=2)
    print(f"Generated {len(data)} transactions")