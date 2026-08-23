# Revenue Recovery Agent

An autonomous agent that detects payment degradation, diagnoses its root cause, and executes a bounded, auditable recovery workflow on Razorpay test-mode APIs.

Built for Razorpay's AI Builder Internship Buildathon — **Track 03: AI Revenue Recovery**.

## The problem

Revenue loss from payment failures rarely happens as one clean event. A payment route degrades, failures spike for a specific segment of transactions, and by the time anyone notices, real money has already slipped away. Most teams solve this by blindly retrying every failed payment — which is both wasteful (retrying failures that will never succeed) and risky (retrying transactions that were correctly blocked for fraud).

This agent closes the loop: **detect → diagnose → decide → execute → verify → audit** — with hard safety bounds at every step.

## Live demo

python -m uvicorn app.main:app --reload

Then open `http://127.0.0.1:8000/dashboard`

Two actions:
- **Regenerate Data** — generates a fresh batch of 500 synthetic transactions, including a deliberately injected payment-degradation incident
- **Run Recovery Pipeline** — runs the full detect→diagnose→decide→execute loop and shows the audit trail, including a real Razorpay test-mode order for any approved recovery

## Architecture

\`\`\`
Synthetic Transactions
        |
   [ DETECTOR ]
   sliding-window failure-rate analysis per (payment_method, route),
   overlapping windows merged to avoid double-counting one incident
        |
  Degradation Alert (with revenue at risk)
        |
 [ ROOT-CAUSE CLASSIFIER ]
   majority-vote on failure_reason_code within the alert window
        |
  Diagnosis + Confidence Score
        |
 [ RECOVERY POLICY / BOUND CHECKER ]
   hard-coded gates, not LLM judgment
        |
   REJECTED vs APPROVED
        |
 REJECTED path:                    APPROVED path:
 never-retry code,                 passed confidence
 not recoverable, or               threshold + eligible
 confidence too low                root cause
        |                                |
 BLOCKED / ESCALATED          [ AGENT REASONING LAYER ]
 (logged, no action            advisory only - can flag
  taken)                        caution, cannot override
                                 the bound checker's approval
                                        |
                              [ RAZORPAY TEST-MODE API ]
                                 real order creation
                                        |
                          SUCCESS                FAILURE
                    verified, logged,       bounded retry (max 2)
                    revenue counted                |
                    as recovered            graceful abandonment,
                                              no infinite loop
                          |                          |
                          -----------  ---------------
                                    |
                       AUDIT LOG + BATCH METRICS
\`\`\`

## Why this architecture

**The bound checker is hard-coded, not prompted.** Every gate — the never-retry list, the confidence threshold, the retry cap — is enforced in plain Python, not asked of an LLM. This matters because "explainable, bounded, and gated" (the track's stated bar) needs to be *provably* true, not just plausible. An LLM can be talked out of a rule; a hard-coded `if` statement can't.

**Confidence-gated action, not confidence-decorated action.** The root-cause classifier returns a real confidence score (majority-vote strength within the alert window), and the policy actually uses it — actions below 0.5 confidence get escalated to human review rather than auto-executed, even when the underlying issue is a known-recoverable type.

**Hard-blocked categories exist independent of confidence.** `RISK_BLOCKED` failures are never retried, regardless of confidence score or detector output. This is a compliance/safety boundary, not a tunable parameter.

**Bounded retry, not infinite retry.** A failed recovery action gets one additional attempt, then the system stops and logs `RECOVERY_ABANDONED` rather than retrying indefinitely or silently giving up.

**Overlapping alerts are merged, not double-counted.** The detector's sliding window can flag the same underlying incident more than once as it steps across time. These are merged into a single deduplicated alert before reaching the policy layer, so the audit trail and revenue numbers reflect distinct real incidents, not re-detections of the same event.

**Every decision is logged, including non-actions.** The audit trail records `BLOCKED` and `ESCALATED` decisions with their specific reason, not just successful recoveries — this is what lets the system prove it isn't just chasing every rupee blindly.

## The reasoning layer

On top of the hard-coded bound checker, every approved action passes through an advisory reasoning layer before execution. This layer can only add caution — it flags concerns (borderline confidence, mixed root-cause signal, unusually large amount relative to confidence) but can never override a bound-checker rejection into an approval, and it can never turn an approval into a block on its own authority either. It's a second set of eyes, not a second decision-maker.

It's implemented as deterministic rule-based reasoning rather than a live LLM call. This was a deliberate choice: a financial recovery system's execution path shouldn't depend on an external API being available, fast, or within budget — a network blip or rate limit shouldn't be able to silently change whether real money moves. The reasoning logic here (flagging borderline confidence, mixed signals, or large-amount/low-confidence combinations) is fully swappable for a live LLM call in a production version without changing anything else in the pipeline, since it's isolated behind a single function (`get_agent_reasoning`).

You can see this in action in the Audit Trail: approved actions occasionally show a flagged note explaining exactly why the reasoning layer is cautious, even though the action still proceeded — this is intentional and visible, not hidden.

## Sample batch results

Since transaction data is regenerated on demand (via the "Regenerate Data" button), exact numbers vary run to run — this is intentional, not a bug. What stays consistent across runs:

- Revenue at risk is never fully recovered by default — the policy engine and reasoning layer together mean some fraction of alerts are always escalated rather than auto-actioned, by design.
- Every approved action includes a real Razorpay test-mode order ID, verifiable independently.
- The Agent Reasoning layer visibly flags its own approvals when confidence is borderline or the root-cause signal is mixed — proof it's doing real evaluative work, not rubber-stamping the policy engine's decision.

## Tech stack

- **Backend**: Python, FastAPI
- **Payment execution**: Razorpay Python SDK (test-mode)
- **Data**: synthetic transaction generator with deliberately injected degradation events
- **Frontend**: vanilla HTML/CSS/JS dashboard, Razorpay-themed

## Project structure

app/
├── main.py # FastAPI app + routes
├── synthetic_data.py # generates synthetic transaction batches
├── detector.py # sliding-window degradation detection + alert merging
├── root_cause.py # failure classification + confidence scoring
├── recovery_policy.py # bound checker, retry logic, Razorpay execution
├── razorpay_client.py # Razorpay SDK wrapper (+ simulated failure for testing)
├── llm_reasoner.py # advisory reasoning layer
├── static/
│ └── dashboard.html # live dashboard UI
data/
├── transactions.json # current synthetic transaction batch
├── audit_log.json # most recent recovery run's audit trail


## What I'd build next with more time

- **Persistent retry tracking** (currently in-memory, resets on server restart) — would move to a real datastore for production use
- **A held-out test set** to measure detector precision/recall formally, rather than eyeballing alert quality
- **Multi-channel recovery actions** beyond reroute/retry — e.g., an actual payment-link generation flow for `notify_customer` cases, rather than just logging the intent
- **Configurable policy thresholds** exposed via an admin endpoint, so a merchant could tune `MIN_CONFIDENCE` and `MAX_RETRIES` without a code change
- **A live LLM call as a drop-in replacement** for the current rule-based reasoning layer, now that the interface is already isolated behind a single function