# exp-010 results: allocation and verification under the measured verification cost

**Kind: REAL TASKS, PILOT.** The worker is a non-LLM DSL search; the
verifier is trust class V1. This is not a confirmatory test.

**Protocol:** [`research/preregistration/exp-010/`](../../research/preregistration/exp-010/protocol.md),
frozen at harness commit `c32d8eb` and merged to `main` as `b87fcf3`. The
scoring script was frozen with it, and every frozen file's hash matched at
scoring time.

**Runs.** 7,500 audited campaigns from `b87fcf3` with a clean tree:

- Part S: 7 policies × 100 seeds × 3 budgets × 3 arms (S-v1, S-v2, S-v2ff);
- Part D: 6 policies × 100 seeds × 2 budgets (D-v2).

Verification was charged `--charge-model measured`: 10.64 CU per call plus
0.00456 CU per case charged, the cost exp-009 measured on this host. Every
run passed the in-line audit, and there were no protocol errors. Wall time
was about 2.4 hours.

Data: [`evaluation.json`](evaluation.json), `runs.csv.gz`,
[`manifests.json`](manifests.json).

## Scorecard

| Prediction | Result |
|---|---|
| G1: round-robin v2 − v1 at S-b330 > −1.0 | ✔ −0.55 [−0.68, −0.43] (was −3.93 under per-case charges) |
| G2: \|round-robin v2ff − v2\| at S-b330 < 0.75 | ✔ +0.38 [0.28, 0.49] (was +2.78) |
| G3: hinted Thompson − round-robin at S-b330 (v2): CI > 0, point > +1.86 | ✔ +2.47 [2.14, 2.81] |
| G4: hinted Thompson − round-robin at D-b660: CI > 0 | ✔ +3.99 [3.69, 4.30] |
| G5: no false solve with suite v2; at least one with v1 | ✔ 0 of 5,400 v2 runs; 70 of 2,100 v1 runs |
| G6: round-robin verification share at S-b330 (v2) ≥ 0.80 | ✔ 0.896 |
| **Decision (suite cost)** | **The stronger suite no longer costs yield under measured cost** |
| **Decision (allocation)** | **Adaptive allocation's scarce-budget gain is robust to measured cost** |

## Part S: single-step tasks

Round-robin's true solves (mean over 100 seeds):

| Budget | v1 | v2 | v2 fail-fast | v2 − v1 | v2ff − v2 |
|---|---|---|---|---|---|
| 330 | 9.17 | 8.62 | 9.00 | −0.55 [−0.68, −0.43] | +0.38 [0.28, 0.49] |
| 1,320 | 19.79 | 19.50 | 19.78 | −0.29 [−0.40, −0.19] | +0.28 [0.18, 0.39] |
| 2,640 | 22.93 | 22.79 | 22.96 | −0.14 [−0.24, −0.05] | +0.17 [0.10, 0.25] |

Under per-case charges (exp-006 and exp-008, budgets 60/240/480), v2 − v1
was −3.93, −1.88 and −1.06, and fail-fast recovered +2.78, +1.74 and +1.02.
Both effects are now about a seventh to a sixth of their old size. They are
still distinguishable from zero, because each v2 verification costs about
7% more than a v1 one, and a fail-fast charge saves at most 7.8%.

Round-robin's verification share of committed compute was 84–90% in every
arm and budget (v1 0.89 / 0.86 / 0.84; v2 0.90 / 0.87 / 0.85).

Policies against round-robin, suite v2:

| Policy | @330 | @1,320 | @2,640 |
|---|---|---|---|
| thompson (hints) | **+2.47** [2.14, 2.81] | **−0.93** [−1.24, −0.61] | **−0.66** [−0.92, −0.41] |
| greedy_prior | +0.44 [0.08, 0.80] | −1.63 [−1.94, −1.32] | −1.33 [−1.62, −1.06] |
| thompson (no hints) | +0.05 [−0.34, 0.44] | −0.34 [−0.50, −0.19] | −0.07 [−0.18, 0.04] |
| random | −0.38 [−0.75, −0.01] | −0.21 [−0.40, −0.03] | −0.09 [−0.19, 0.01] |
| fifo | −2.75 | −7.03 | −5.57 |
| oracle_index (estimated) | +5.96 | +2.40 | +1.09 |

The v1 and v2 fail-fast arms give the same picture within 0.3 (hinted
Thompson: +2.22 and +2.18 at 330; −0.94 and −0.84 at 1,320; −0.49 and −0.64
at 2,640).

## Part D: dependency tasks (suite v2)

| Policy | @660 | @2,640 |
|---|---|---|
| thompson (hints) | **+3.99** [3.69, 4.30] | **+2.95** [2.63, 3.27] |
| greedy_prior | +3.68 [3.38, 3.98] | +2.35 [2.02, 2.67] |
| thompson (no hints) | +1.42 [1.19, 1.66] | −2.10 [−2.35, −1.84] |
| random | −0.25 [−0.58, 0.08] | −0.06 [−0.30, 0.19] |
| oracle_index (estimated) | +6.52 | +5.38 |

Under per-case charges (exp-007, budgets 120/480) hinted Thompson's gain was
+4.44 and +4.45. Round-robin's verification share is 0.86 at 660 CU and
0.84 at 2,640.

## What it shows, and what it doesn't

1. **The suite-cost and fail-fast findings were artefacts of the per-case
   charge.** Once a verification costs mostly its fixed per-call overhead,
   the 199-check suite costs about half a true solve at the scarcest
   budget, not four. It keeps every verdict benefit: 0 false solves in
   5,400 v2 runs, against 70 of 2,100 v1 runs. Fail-fast charging is worth
   less than half a solve. Under measured cost the case for the stronger
   suite is clear.
2. **The scarce-budget allocation gain holds, and is slightly larger.**
   Hinted Thompson beats round-robin by +2.47 at S-b330 (exp-004 v1: +1.86;
   exp-008 fail-fast: +2.29) and by +3.99 on dependency tasks.
3. **New, not preregistered: at moderate single-step budgets, hinted
   Thompson now loses to round-robin.** At 1,320 and 2,640 CU it is −0.93
   and −0.66, in all three arms. Under per-case charges at the matching
   budgets it was +0.25 and +0.22 (exp-004) or −0.33 and +0.18 (exp-008).
   greedy_prior loses more. One plausible reason: once each failed
   verification costs about 11 CU, a policy that keeps retrying tasks it
   believes are promising pays heavily for every miss. This has not been
   tested. A follow-up should test it before the moderate-budget
   single-step result is treated as a finding.
4. **Verification dominates compute.** About 85–90% of committed compute
   is verification in every arm. The DSL worker submits a candidate even
   when no sample matched the visible examples, and under the measured
   charge each such submission costs a full verification. A visible-example
   gate before submission is the obvious next design change.

## Limits

- **One host's cost:** the charge constants are this Windows host's. On
  Linux, exp-009L measured a fixed cost about 4.8× smaller (25 ms against
  120 ms), so the fixed term there would be about 2.2 CU, not 10.6.
- **Charges, not timing:** charges are deterministic, derived from
  exp-009's measurement. Per-call wall time during the campaigns (about
  280–390 ms, with 8 threads busy) is reported in the manifests but is not
  a measurement of cost.
- **Budgets** were scaled by arithmetic (×5.5). Round-robin made about
  25, 113–121 and 273–293 attempts per run at the three single-step
  budgets, against 32, 136 and 315 in exp-008.
- **Worker, tasks and verifier:** non-LLM worker, tasks written by the
  project, V1 verifier (`--sandbox none`). The oracle uses calibration
  estimates.
