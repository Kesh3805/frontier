# exp-012 results: pricing a novel candidate in hinted Thompson

**Kind: REAL TASKS, PILOT.** The worker is a non-LLM DSL search; the
verifier is trust class V1. This is not a confirmatory test.

**Protocol:** [`research/preregistration/exp-012/`](../../research/preregistration/exp-012/protocol.md),
frozen at harness commit `e38e0b9` and merged to `main` as `1c423d2`. The
design came out of an exchange with ChatGPT, which also reviewed the draft.
The scoring script was frozen with the protocol, and every frozen file's
hash matched before the runs.

**Runs.** 1,800 audited campaigns from `1c423d2` with a clean tree:
6 hinted policies × 100 fresh seeds (7001–7100) × 3 budgets (330, 1,320 and
2,640 CU), all under `--charge-model measured`. Every run passed the in-line
audit, and there were no protocol errors. Wall time was about 1.0 hour, on
an otherwise idle machine.

Data: [`evaluation.json`](evaluation.json), `runs.csv.gz`,
[`manifests.json`](manifests.json).

## Cells

| Label | Policy | Cost model | Reuse |
|---|---|---|---|
| RR | `round_robin` | | |
| TH | `thompson` (hints) | observed | failure |
| OI | `thompson_novel` | observed | ignored |
| NF | `thompson_novel` | per novel candidate | failure |
| NI | `thompson_novel` | per novel candidate | ignored |
| FL | `thompson_flat` (hints) | constant | failure |

## Scorecard (b1320 unless stated)

| Prediction | Result |
|---|---|
| N0: TH − RR: CI < 0 (the loss replicates) | ✔ −0.70 [−1.03, −0.36] |
| N1: NF − TH: CI > 0 | ✘ +0.05 [−0.11, 0.22] |
| N2: NF − RR ≥ −0.3 (point) | ✘ −0.65 [−1.00, −0.29] |
| N3: NF − RR at b330: CI > 0 | ✔ +2.48 [2.14, 2.82] |
| N4: OI − TH: CI < 0 | ✘ −0.12 [−0.24, 0.00] |
| N5: cost effect larger with reuse ignored (point) | ✔ +0.08 against +0.05 |
| N6: dead-task share NF − TH: CI < 0 | ✔ −0.012 [−0.016, −0.008] |
| N7: no false solve | ✔ 0 of 1,800 runs |
| **Decision** | **Unclear** |

N1 failed and the CI of NF − TH crosses zero, so neither "fixes", "improves"
nor "does not help" applies. N4 missed its threshold only at the CI's upper
bound (0.00).

## Solves against round-robin

| Cell | b330 | b1320 | b2640 |
|---|---|---|---|
| TH | +2.33 [1.99, 2.68] | **−0.70** [−1.03, −0.36] | **−0.66** [−0.90, −0.43] |
| OI | +2.29 [1.95, 2.63] | −0.82 [−1.16, −0.46] | −0.70 [−0.95, −0.46] |
| NF | +2.48 [2.14, 2.82] | −0.65 [−1.00, −0.29] | −0.28 [−0.49, −0.07] |
| NI | +2.31 [1.97, 2.65] | −0.74 [−1.10, −0.37] | −0.35 [−0.56, −0.14] |
| FL | +2.50 [2.12, 2.87] | −0.71 [−1.05, −0.37] | −0.56 [−0.81, −0.30] |

Round-robin's mean true solves: 8.79 / 19.41 / 22.95.

## Against hinted Thompson

| Cell | b330 | b1320 | b2640 |
|---|---|---|---|
| OI | −0.04 [−0.13, 0.04] | −0.12 [−0.24, 0.00] | −0.04 [−0.19, 0.11] |
| NF | +0.15 [0.01, 0.29] | +0.05 [−0.11, 0.22] | **+0.38** [0.18, 0.59] |
| NI | −0.02 [−0.15, 0.11] | −0.04 [−0.20, 0.12] | **+0.31** [0.13, 0.50] |
| FL | +0.17 [0.05, 0.29] | −0.01 [−0.23, 0.21] | +0.10 [−0.07, 0.28] |

## Where the attempts go (b1320, means per run)

| Cell | Attempts | Dead-task share | Dead-task attempts | Reused rejections |
|---|---|---|---|---|
| RR | 112.9 | 0.388 | 43.9 | 14.1 |
| TH | 177.4 | 0.575 | 102.2 | 73.6 |
| OI | 179.1 | 0.583 | 104.5 | 75.2 |
| NF | 173.2 | 0.564 | 97.8 | 69.4 |
| NI | 176.7 | 0.573 | 101.5 | 72.9 |
| FL | 172.7 | 0.561 | 97.1 | 69.1 |

## What it shows, and what it doesn't

1. **The moderate-budget loss replicated a third time.** It was −0.93 in
   exp-010, −0.86 in exp-011 and −0.70 here, each on different seeds.
2. **No cost-index change closes it at 1,320 CU.** Per-novel pricing moves
   the dead-task share down by about one percentage point, from 0.575 to
   0.564. That is real (N6) but far too small: round-robin's share is
   0.388, and solves are unchanged. Every Thompson cell stays 0.65–0.82
   behind round-robin.
3. **Per-novel pricing helps at the larger budget (descriptive).** At
   2,640 CU, NF and NI recover +0.38 and +0.31 over hinted Thompson, and
   cut the gap to round-robin from −0.66 to −0.28. Flat cost does not
   (+0.10). This was not a prediction, so it needs its own test.
4. **Ignoring reused rejections does not help.** OI is slightly worse than
   TH at every budget, and makes slightly more dead-task attempts.
5. **The cost-blind cell agrees with exp-011.** FL − TH at 1,320 CU is
   −0.01 here and +0.10 in exp-011. Both CIs include zero.
6. **Across exp-011 and exp-012, the evidence points away from the cost
   index.** Three different cost treatments each shift hinted Thompson's
   dead-task attempts by at most ~5%. Without hints, the dead-task excess
   largely disappears (exp-011, descriptive). The next test should target
   the hint prior itself, for example a weaker prior strength k or hints
   that decay with fresh rejections.

## Limits

- **One host's cost:** the measured charge constants are this Windows
  host's (exp-009). Linux's fixed cost is about 4.8× smaller (exp-009L),
  which would change V relative to G.
- **The novelty model:** q is a stationary per-task rate. A worker whose
  search space is exhausting may have a falling q.
- **Scope:** every Thompson cell uses hints, so the claim is about hinted
  Thompson only.
- **Worker, tasks and verifier:** non-LLM worker, tasks written by the
  project, V1 verifier (`--sandbox none`).
