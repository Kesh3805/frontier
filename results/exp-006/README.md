# exp-006 results: what does stronger verification cost in verified yield?

**Kind: REAL TASKS, PILOT** (non-LLM worker). Protocol and scoring script:
[`research/preregistration/exp-006/`](../../research/preregistration/exp-006/protocol.md),
frozen at `20cfbfd`.

**Run history.** The first execution, on kernel 0.2, was **stopped before
completion** once errata E1/E2 were confirmed; its partial data were not
analysed. These results come from the corrected re-run on kernel 0.3.0:

- 2,100 audited campaigns from commit `4f68438`, with a clean tree;
- the protocol, configs and scoring script are unchanged;
- comparisons are paired against exp-004's own kernel-0.3 re-run (same
  seeds, order and worker streams; only the hidden suite differs).

Data: [`../rerun-k0.3/exp-006/`](../rerun-k0.3/exp-006/).

| | v1 suite (43 checks) | v2 suite (199 checks) |
|---|---|---|
| Charge per verification | 0.215 CU | 0.995 CU |
| Runs with a false solve (all budgets and policies) | 0–7% | **0 of 2,100** |
| Verification share of round-robin's compute (budget 60 / 240 / 480) | 14% / 11% / 10% | **42% / 37% / 34%** |

## Round-robin true solves, v2 − v1 (paired)

| Budget | v1 | v2 | Δ |
|---|---|---|---|
| 60 | 12.38 | 8.45 | **−3.93** [−4.26, −3.61] |
| 240 | 20.53 | 18.65 | **−1.88** [−2.16, −1.60] |
| 480 | 23.13 | 22.07 | **−1.06** [−1.24, −0.88] |

Every policy loses true solves under v2 at every budget. The estimated
oracle loses least: −2.04, −1.00 and −0.49.

## Scorecard

| Prediction | Result |
|---|---|
| W1: at most one v2 run with a false solve | ✔ 0 runs |
| W2: round-robin true solves drop at budget 60 | ✔ −3.93 |
| W3: round-robin changes by < 0.3 at budget 480 | ✘ −1.06 |
| W4: verification share more than doubles at budget 240 | ✔ 11% → 37% |
| **Decision (round-robin)** | **Strong verification costs true yield at some budget** (in fact at all three) |

## What it means

1. **At this verifier error rate, stronger verification is a bad trade in
   yield terms.** It removes about 0.02–0.06 false solves per run, and
   costs 1–4 true solves per run. The trade would look different where
   false acceptance is common: exp-001's simulation shows 12–24% of
   accepted results false at fpr = 0.02.
2. **Expensive verification makes allocation matter more when the budget
   is scarce.** Under v2, hinted Thompson beats round-robin by
   **+3.41 [3.00, 3.84]** at budget 60, about twice its v1 margin (+1.86).
   At 240 and 480 there is no significant difference (−0.24 and −0.16).
   Round-robin keeps paying for expensive checks on hopeless tasks.
3. **Verification cost belongs inside the allocation problem.** The
   obvious cheaper design is fail-fast verification: stop at the first
   failing case, so wrong candidates cost little. Every verdict stays the
   same, and only the cost of failures falls. That is a natural next
   experiment.

## Limits

- Compute units are modelled charges: 0.005 CU per test case. Measured CPU
  time per verification was not recorded per run. Mapping CU to physical
  cost is open work.
- Non-LLM worker; 34 tasks written by the project.
