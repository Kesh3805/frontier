# exp-008 results: fail-fast verification charging

**Kind: REAL TASKS, PILOT.** The worker is a non-LLM DSL search; the
verifier is trust class V1 with hidden suite v2. This is not a
confirmatory test.

**Protocol:** [`research/preregistration/exp-008/`](../../research/preregistration/exp-008/protocol.md),
frozen at `3565087` and merged to `main` as `a89b9d3`. The scoring script
was frozen with it.

**Runs.** 3,900 audited campaigns from `a89b9d3` with a clean tree:

- Part S: 7 policies × 100 seeds × 3 budgets on catalog v2 (exp-006's
  design);
- Part D: 6 policies × 100 seeds × 3 budgets on catalog v3 (exp-007's
  design).

Every run passed the in-line audit. **No run had a false solve.** Wall
time was about 5.2 hours.

Data: [`evaluation.json`](evaluation.json), `runs.csv.gz`,
[`manifests.json`](manifests.json).

## Scorecard

| Prediction | Result |
|---|---|
| F1: round-robin's verification share at S-b240 falls by ≥ 40% | ✔ 36.9% → 12.9% (−65%) |
| F2: round-robin's true solves rise at S-b60 (CI > 0) | ✔ +2.78 [2.49, 3.07] |
| F3: round-robin recovers ≥ half of its v1 → v2 loss at S-b60 | ✔ 71% |
| F4: at most one fail-fast run with a false solve | ✔ 0 of 3,900 |
| F5: hinted Thompson beats round-robin at D-b120 (CI > 0) | ✔ +5.07 [4.75, 5.39] |
| F6: round-robin's true solves rise at D-b120 (CI > 0) | ✔ +0.63 [0.49, 0.78] |
| **Decision** | **Fail-fast recovers yield** |

## Part S: single-step tasks (26 live)

Round-robin's true solves under three verification settings, paired over
100 seeds:

| Budget | v1 (43 checks) | v2 full charge | v2 fail-fast | Recovered |
|---|---|---|---|---|
| 60 | 12.38 | 8.45 | 11.23 | 71% |
| 240 | 20.53 | 18.65 | 20.39 | 93% |
| 480 | 23.13 | 22.07 | 23.09 | 96% |

Fail-fast minus v1: −1.15 [−1.34, −0.96] at 60, −0.14 [−0.23, −0.06] at
240, −0.04 [−0.12, 0.03] at 480.

Round-robin's verification share of compute:

| Budget | v1 | v2 full charge | v2 fail-fast |
|---|---|---|---|
| 60 | 13.5% | 42.2% | 23.9% |
| 240 | 10.6% | 36.9% | 12.9% |
| 480 | 9.9% | 33.9% | 10.6% |

Every policy gains at every budget (+0.66 to +2.78; every CI lower bound ≥ 0.52).
Fail-fast keeps v2's verdicts, so it keeps v2's zero false solves, while
costing only slightly more than v1 at 240 and 480 CU.

Policies against round-robin under fail-fast:

| Policy | @60 | @240 | @480 |
|---|---|---|---|
| thompson (hints) | **+2.29** [1.95, 2.63] | −0.33 [−0.66, 0.00] | +0.18 [−0.02, 0.38] |
| greedy_prior | −0.15 [−0.58, 0.28] | −0.95 [−1.29, −0.62] | −0.05 [−0.29, 0.18] |
| thompson (no hints) | −0.37 [−0.71, −0.03] | +0.35 [0.11, 0.58] | +0.15 [−0.01, 0.31] |
| random | −1.24 [−1.61, −0.86] | +0.11 [−0.06, 0.28] | +0.14 [0.03, 0.26] |
| fifo | −4.76 | −6.64 | −3.41 |
| oracle_index (estimated) | +5.56 | +2.37 | +1.00 |

## Part D: dependency tasks (19 live)

True solves, fail-fast minus exp-007 (full charge):

| Policy | @120 | @480 | @1920 |
|---|---|---|---|
| round_robin | +0.63 [0.49, 0.78] | +2.05 [1.83, 2.28] | +0.57 [0.43, 0.72] |
| thompson (hints) | +1.26 [1.07, 1.46] | +1.20 [0.99, 1.41] | +0.44 [0.32, 0.56] |
| greedy_prior | +1.23 | +0.53 | +1.32 |
| thompson (no hints) | +0.78 | +1.61 | +0.41 |
| random | +1.12 | +2.10 | +0.53 |
| oracle_index | +1.07 | +0.60 | 0.00 |

Policies against round-robin under fail-fast:

| Policy | @120 | @480 | @1920 |
|---|---|---|---|
| thompson (hints) | **+5.07** [4.75, 5.39] | **+3.60** [3.31, 3.88] | +0.35 [0.22, 0.49] |
| greedy_prior | +4.86 [4.53, 5.19] | +2.51 [2.18, 2.83] | −1.17 [−1.39, −0.95] |
| thompson (no hints) | +0.97 [0.77, 1.19] | −1.94 [−2.19, −1.68] | +0.28 [0.20, 0.37] |
| random | −0.08 [−0.37, 0.21] | +0.31 [0.03, 0.58] | +0.32 [0.23, 0.42] |
| oracle_index (estimated) | +7.46 | +5.40 | +0.57 |

Round-robin's verification share fell from 35% to 16% (120 CU), 32% to
9% (480) and 27% to 4% (1,920).

## What it shows, and what it doesn't

1. **Most of the cost of strong verification was the cost of failures.**
   Charging a failing candidate only for the cases it ran keeps the
   199-check suite's verdicts, and its zero false solves, while bringing
   compute spent on verification back near v1 levels. At 240 and 480 CU,
   round-robin is within 0.2 true solves of v1, with none of v1's false
   solves.
2. **Cheaper verification shrinks the allocation margin on single-step
   tasks.** Under full charge, exp-006 found hinted Thompson's scarce-budget
   margin roughly doubled (+3.41). Under fail-fast it is +2.29, between
   v1 (+1.86) and full charge. When failures are cheap, wasting attempts
   costs less, so a smart allocator has less to save. At 240 and 480 CU no
   adaptive policy beats round-robin by more than 0.35.
3. **The dependency-task result is robust to verification cost.** Hinted
   Thompson's gain over round-robin at 120 CU grew (+4.44 → +5.07). At 480
   CU it shrank (+4.45 → +3.60) because round-robin gained most there. The
   pattern of exp-007 is unchanged: the static index falls behind at
   1,920 CU, and hint-free Thompson loses at 480.
4. **It is a charging model, not a measured saving.** Fail-fast charges
   are modelled compute units. Whether a real test runner saves the same
   fraction depends on per-case runtime and suite order (v2 runs its 156
   exhaustive small inputs first, where most wrong candidates fail).

## Limits

- Non-LLM worker; tasks written by the project.
- Verifier trust class V1 (`--sandbox none`).
- Compute units are modelled, not measured CPU time or cost.
- The fail-fast saving depends on v2's case order.
- The oracle uses calibration estimates.
