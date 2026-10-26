# exp-000: Can receipt-driven allocation beat round-robin in a calibrated simulator?

Status: **FROZEN** before any exp-000 outcome was generated.
Kind: **simulation** (synthetic environment with known ground truth; no
models, no spend). Results say nothing directly about LLM workers.

## Frozen inputs

| Item | Value |
|---|---|
| Source commit | `bcdaeb9c5f7537f68643ed2f84fe8e4a9cc471c7` (kernel, policies, simulator, analysis) |
| `scarce.json` | `1bcf1ca7310809d73bf7d572ebacf2e5a86033158afaabd729278c87a5abda85` |
| `moderate.json` | `57c051135696e509c0bfd1fa19ce920d530662ce7a081cebc7eb8a14d0f62201` |
| `python/frontier_py/analysis.py` | `fbbf32e21c9cb5e9814820f7a0dc76e4ed7d1490a773256556fc6bced5661a0c` |
| `crates/frontier-sim/src/runner.rs` | `0308773cd8473cba6f79eaa8b9fe9d4de9855501630f6ec7ff705716c041ada3` |
| `crates/frontier-sim/src/env.rs` | `9c26ec83a790deacf0e99e6c5c710203eb3c3c95931be863cbfad198d9294b81` |
| `crates/frontier-sched/src/lib.rs` | `22b5bc5cee7af71ab36cd2e8813ee85e7e4ab5da50449cb7bc4f3db85c57109f` |

## Question

H1 needs adaptive allocation to beat strong fixed policies with real
workers. A necessary condition is that it does so in a simulator whose
success-rate distributions match published pass@k data, when the scheduler
sees only verifier receipts. If it fails here, H1 has no mechanism to rely on.

## Design

- **Regimes.** Six, each with 50 problems. Parameters are fitted in
  [`docs/research/calibration.md`](../../../docs/research/calibration.md).
  - **R0** homogeneous control: every problem has p ≈ 0.25 with no spread, no
    dead problems, near-constant cost.
  - **R1–R4** use calibrated single-step problems:
    - R1 saturated-easy: d=0.03, Beta(0.81, 0.26)
    - R2 formal-plateau: d=0.11, Beta(0.38, 0.17)
    - R3 agentic-SWE: d=0.30, Beta(0.27, 0.91)
    - R4 frontier-hard: d=0.85, Beta(0.2, 6)
  - **R5** structured: 1–3 approaches of 1–4 obligation chains, shared
    lemmas with probability 0.5, R2 parameters per obligation.
  - **Common to R1–R5:** cost LogNormal(0, 0.5) per task, attempt sd 0.3,
    failed attempts ×1.5, hint noise 1.0 (logit sd).
- **Budgets.** Two levels: *scarce* (150 CU, about 1.7 attempts per
  problem) and *moderate* (600 CU, about 7).
- **Run settings.** 8 workers, attempt cap 8 CU, verification 0.25 CU,
  crash probability 0.02, at most 64 attempts per task, 1 in flight per task.
- **Policies.** round_robin (primary baseline; Zuo et al. Alg. 1 with K=1),
  fixed_slice, fifo, random, greedy_prior,
  hopeless_elimination(n=5, thr=0.05), ucb(k=2, hints, β=1),
  **thompson(k=2, hints)** (primary treatment), thompson(k=2, no hints), and
  oracle_index (diagnostic only).
- **Seeds.** 1–200 for every regime × budget. For a given seed, every
  policy faces the same campaign and the same per-attempt outcome streams.
  The paired cluster is (regime, seed).

## Endpoints and analysis

- **Primary.** `solved` (problems with an accepted terminal receipt) for
  thompson(k=2,hints=true) − round_robin. The estimate is the paired mean
  difference over 200 clusters per cell, with a 95% percentile bootstrap
  CI (10,000 replicates, seed 26102026) from `frontier_py.analysis`. An
  exact two-sided sign test is also reported.
- **Secondary (descriptive).**
  - The same comparison against fixed_slice, greedy_prior and
    hopeless_elimination.
  - thompson-without-hints vs round_robin. This separates learning from
    prior information.
  - oracle_index vs thompson (the remaining gap).
  - `time_to_first_solve` (conditional on both arms solving, noted as such),
    `wasted_units`, `units_per_solved`, utilisation, and host-measured
    policy overhead per decision.

## Predictions (made before running)

- **P0 (R0, both budgets):** the CI for the primary difference contains 0,
  or |difference| < 0.5 problems. There is no heterogeneity to exploit.
- **P1 (R1 moderate):** |difference| < 1 problem, because nearly
  everything is solvable within budget. R1 scarce: no prediction.
- **P2 (R2, R3, R5 at both budgets; six cells):** difference > 0 with the
  CI excluding 0.
- **P3 (R4, both budgets):** difference > 0. Round-robin keeps paying for
  dead problems.
- **P4:** thompson-without-hints also beats round_robin in R2/R3/R5,
  though by less than with hints.

## Decision rule for H1-sim

- **Supported** if P2 holds in all six cells.
- **Rejected** if, in any of the six P2 cells, the CI lies entirely
  below 0, or if four or more of the six CIs include 0.
- **Partially supported** otherwise. The failing cells are reported.

P0, P1, P3 and P4 are reported as confirmed or not confirmed, with no
retrospective reinterpretation. CIs are not adjusted for multiplicity; with
six primary cells, an isolated marginal cell should be read with that in
mind.

## Invalidation conditions

The experiment is invalid, and must be re-run from a new preregistration,
if any of these occur:

- any audit failure (budget overrun, unsupported acceptance, broken
  chain);
- a nonzero `source_dirty` in the manifest;
- a config hash mismatch.

## Known limitations (accepted in advance)

- Attempts are i.i.d. given p. Real attempts are likely correlated, which
  would reduce the information each failure carries.
- `attempt_cost_sd` and the per-regime cost parameters have no empirical
  source.
- Hints come from the true p with noise. Real difficulty predictors may be
  worse, or biased.
- The verifier is perfect. Real verifiers have false negatives, and
  formal-to-informal fidelity gaps (arXiv 2610.08144).
