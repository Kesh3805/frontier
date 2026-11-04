# exp-011 results: is hinted Thompson's moderate-budget loss a cost-index bias?

**Kind: REAL TASKS, PILOT.** The worker is a non-LLM DSL search; the
verifier is trust class V1. This is not a confirmatory test.

**Protocol:** [`research/preregistration/exp-011/`](../../research/preregistration/exp-011/protocol.md),
frozen at harness commit `a905815` and merged to `main` as `c56a5e9`. The
scoring script was frozen with it, and every frozen file's hash matched at
scoring time.

**Runs.** 3,000 audited campaigns from `c56a5e9` with a clean tree:
5 policies × 100 fresh seeds (5001–5100) × 6 configs.

- **Part M:** `--charge-model measured`, budgets 330 / 1,320 / 2,640 CU.
- **Part P:** per-case charges, budgets 60 / 240 / 480.

Every run passed the in-line audit, and there were no protocol errors.
Wall time was about 2.3 hours.

Data: [`evaluation.json`](evaluation.json), `runs.csv.gz`,
[`manifests.json`](manifests.json).

## Scorecard

"TH" is hinted Thompson; "THflat" is hinted Thompson with a constant cost
estimate (`thompson_flat`).

| Prediction | Result |
|---|---|
| R1: TH − round-robin at M-b1320: CI < 0 | ✔ −0.86 [−1.18, −0.54] (exp-010: −0.93) |
| R2: THflat − TH at M-b1320: CI > 0 | ✘ +0.10 [−0.09, 0.30] |
| R3: dead attempts THflat − TH at M-b1320: CI < 0 | ✔ −4.95 [−6.49, −3.51] (of 102.6) |
| R4: THflat − round-robin at M-b1320 ≥ −0.3 | ✘ −0.76 [−1.09, −0.42] |
| R5: THflat − round-robin at M-b330: CI > 0 | ✔ +2.36 [2.00, 2.72] |
| R6: THflat − TH larger at M-b1320 than at P-b240 (point) | ✔ +0.10 against −0.01 |
| R7: no false solve | ✔ 0 of 3,000 runs |
| **Decision** | **The loss replicated; the cost-bias explanation is unclear** |

R2 failed and its CI does not lie entirely at or below zero, so the
preregistered outcome is "unclear", not "another cause".

## Solves against round-robin

| Policy | M-b330 | M-b1320 | M-b2640 |
|---|---|---|---|
| TH | **+2.03** [1.68, 2.37] | **−0.86** [−1.18, −0.54] | **−0.77** [−1.03, −0.53] |
| THflat | **+2.36** [2.00, 2.72] | **−0.76** [−1.09, −0.42] | **−0.56** [−0.82, −0.30] |
| Thompson, no hints | −0.44 [−0.79, −0.10] | −0.30 [−0.45, −0.15] | −0.19 [−0.33, −0.06] |
| flat, no hints | −0.45 [−0.79, −0.11] | −0.21 [−0.33, −0.10] | −0.07 [−0.14, 0.00] |

| Policy | P-b60 | P-b240 | P-b480 |
|---|---|---|---|
| TH | **+3.14** [2.71, 3.55] | +0.06 [−0.27, 0.39] | −0.09 [−0.35, 0.17] |
| THflat | **+3.83** [3.37, 4.29] | +0.05 [−0.29, 0.40] | −0.01 [−0.29, 0.25] |
| Thompson, no hints | −0.26 [−0.74, 0.20] | −0.31 [−0.55, −0.08] | +0.10 [−0.07, 0.27] |
| flat, no hints | −0.35 [−0.75, 0.05] | +0.02 [−0.11, 0.15] | +0.08 [−0.02, 0.18] |

Round-robin's mean true solves: 9.39 / 19.65 / 23.16 (M) and
9.20 / 18.85 / 22.32 (P).

## Where the attempts go (M-b1320, means per run)

| Policy | Solves | Dead-task attempts | Reused rejections |
|---|---|---|---|
| round-robin | 19.65 | 44.5 | 14.9 |
| TH | 18.79 | 102.6 | 72.9 |
| THflat | 18.89 | 97.7 | 69.2 |
| Thompson, no hints | 19.35 | 53.2 | 22.1 |
| flat, no hints | 19.44 | 45.7 | 15.8 |

## What it shows, and what it doesn't

1. **The moderate-budget loss is real.** On fresh seeds, hinted Thompson
   loses to round-robin by 0.86 at 1,320 CU and 0.77 at 2,640 CU, close to
   exp-010's −0.93 and −0.66. Under per-case charges at the matching
   budgets it ties round-robin. The loss is specific to the measured
   charge.
2. **Removing the cost signal does not fix it.** Flat cost cut hinted
   Thompson's dead-task attempts by only about 5% (102.6 → 97.7) and
   recovered 0.10 of a solve, with a CI that includes zero. Most of the gap
   to round-robin (−0.76) remains.
3. **Descriptive, not preregistered: the excess sits with the hints.** Without
   hints, flat cost brings dead-task attempts down to round-robin's level
   (53.2 → 45.7, against 44.5), and the gap narrows to −0.21. With hints,
   the dead-task excess barely moves. Hinted Thompson also makes 72.9
   reused rejections per run (candidates byte-identical to one already
   rejected), nearly five times round-robin's 14.9. That fits the alternative the protocol named,
   H-hints: confident hints keep the posterior optimistic on dead tasks,
   whatever the cost index. This experiment was not designed to separate
   the two explanations, so this is a lead, not a finding.
4. **Flat cost helps where budgets are scarce.** THflat − TH is +0.33
   [0.21, 0.45] at M-b330 and +0.69 [0.49, 0.89] at P-b60. These are
   descriptive.

[exp-012](../../research/preregistration/exp-012/protocol.md) was frozen
before any of these outcomes was looked at. It tests pricing per novel
candidate and stops counting reused rejections as failures, within hinted
Thompson. Its `thompson_flat` cell can be compared with this result.

## Disclosures

- **An aborted first launch.** The first background launch of the six
  configs died when the controlling session ended ("service closed its
  output") before writing any results. It was deleted and all six configs
  were run again from the same commit. Those reruns are the only data
  scored.
- **Concurrent load.** Unit tests and dev builds for exp-012 ran on this
  host while P-b60 and P-b240 were running. The verifier has wall-clock
  timeouts, so both configs were run again on an idle machine. Every
  outcome field was identical. Only `select_nanos`, a timing measurement,
  differed, and no run in either version had a timeout.

## Limits

- **One host's cost:** the measured charge constants are this Windows
  host's (exp-009). Linux's fixed cost is about 4.8× smaller (exp-009L).
- **One intervention:** flat cost removes all cost information. It tests
  whether the observed-cost index causes the loss, not what the best cost
  estimate is.
- **Worker, tasks and verifier:** non-LLM worker, tasks written by the
  project, V1 verifier (`--sandbox none`).
