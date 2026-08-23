import os
import razorpay
from dotenv import load_dotenv

load_dotenv()

client = razorpay.Client(
    auth=(os.getenv("RAZORPAY_KEY_ID"), os.getenv("RAZORPAY_KEY_SECRET"))
)

def create_recovery_order(amount_rupees, receipt_id):
    """
    Creates a real Razorpay test-mode order representing a recovery attempt.
    Amount must be in paise (smallest currency unit).
    """
    amount_paise = int(amount_rupees * 100)
    try:
        order = client.order.create({
            "amount": amount_paise,
            "currency": "INR",
            "receipt": receipt_id,
            "payment_capture": 1
        })
        return {"success": True, "order": order}
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_recovery_order_simulated_failure(amount_rupees, receipt_id):
    """
    Deliberately fails — used to demo the bounded retry / graceful failure
    path on demand, without waiting for a real API error.
    """
    return {"success": False, "error": "SIMULATED_FAILURE: bank_gateway_timeout"}


if __name__ == "__main__":
    result = create_recovery_order(500.00, "test_recovery_001")
    print(result)