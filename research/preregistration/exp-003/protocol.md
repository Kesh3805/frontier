# exp-003: First real verifier-backed pilot of the scheduler (non-LLM worker)

Status: **FROZEN** before any exp-003 outcome was generated. The scoring
script [`evaluate.py`](evaluate.py) is frozen with this protocol.
Kind: **real tasks, pilot.** Real candidate programs are checked by the
real property-test verifier, run in subprocesses (trust class V1). The
worker is a deterministic DSL program search, **not an LLM**. This is a
pilot in the dossier's Stage-P sense: it informs the design of
confirmatory work and is not itself a confirmatory test of H1.

## Frozen inputs

SHA-256 of committed bytes at config commit `b4d188ca0c8b43bdb14e69bf5912ff7c6be44a96`:

| File | SHA-256 |
|---|---|
| `research/preregistration/exp-003/b60.json` | `8fca868cca70dcd704689a263319f57d776f80206e5d608ce84b0c1dbd58b46a` |
| `research/preregistration/exp-003/b240.json` | `5054ce08d8ac4262ba3f43ba4b3e9669cd7269755e1d07722e7d9c303e6336e9` |
| `research/preregistration/exp-003/b480.json` | `d2bb543e965f8bbd26c2fb6afd7872571dcd0fbf67f6eb914daba5056e23d9bc` |
| `research/preregistration/exp-003/make_configs.py` | `b729d94f77780fe9f4077a8f06cd1f2c2758784ebb866594db426a1a7a2a64db` |
| `research/realtasks/catalog-v1.json` | `80bdd82bec3e249b17d7938dab3e28786989dae55edd0650875c0c6c440b9585` |
| `python/frontier_py/analysis.py` | `fbbf32e21c9cb5e9814820f7a0dc76e4ed7d1490a773256556fc6bced5661a0c` |
| `python/frontier_py/realtasks/worker.py` | `ec0861a240d80985182891ee0674438528dc6989bf7d83d462857622707590f9` |
| `python/frontier_py/realtasks/suite.py` | `4a33418ef092dc7cd672796ab85789db2158b2eb76eaa3c5410d3dea9b827755` |
| `python/frontier_py/realtasks/dsl.py` | `ceb72cdd71a0dd346cff71fe6482548c1d140fe9d0621aca524e6d00a1863c29` |
| `python/frontier_py/realtasks/server.py` | `783cec9290e8495a4b68ec078e6ba6cb1c53014270889317c1342913b3e86081` |
| `python/frontier_py/verifiers/property_tests.py` | `4ace5caa54018379a523a5d55036d08129ce2d1db6a508faa50112f313b49ff2` |
| `crates/frontier-sim/src/runner.rs` | `195f83641651ec8752522c35338311cf7855e6c58cb9785a25367d96e6572932` |
| `crates/frontier-sim/src/real.rs` | `fe83407ffd8f1db7daad41733e5734e1141561dc7c0ae7dfbacf18261dd1c9fa` |
| `crates/frontier-sched/src/lib.rs` | `4727cce88e0cb0ae9f0e968d038f86e70a335d6461fc1808e9a9da892b4ef149` |

## What was seen before freezing (disclosed)

**Calibration, from 200 attempts per task on a separate calibration seed:**

- p̂ for every task;
- that the probe hint is poorly calibrated;
- that the two "contradictory" tasks are alive. They were relabelled
  "misleading" before this freeze;
- that the frozen hidden suite admits wrong programs on max0, span and
  max_abs.

**Engineering runs on dev seeds 1–3, disjoint from the pilot seeds:**

- round-robin only, at budgets 30–480, used to choose these three budget
  levels;
- one 2-policy dev run at budget 60.

One round-robin dev run at budget 480 contained a verifier false
acceptance. No policy comparison on pilot seeds was seen.

## Design

**Tasks.** The 34-task catalog v1:

- 24 solvable in the worker's DSL;
- 2 "misleading": alive, but their visible examples contradict each other;
- 8 dead: 6 inexpressible in the DSL and 2 misspecified.

Policies see only the probe hint. Its quality is mixed:

- 3 of the 8 dead tasks look easy (hint 0.999): count_above_7 and both
  misspecified tasks;
- 5 dead tasks look hard (hint 0.001);
- several live tasks have hints far off their p̂.

**Worker.** Each attempt runs a seeded DSL search of up to 256 programs and
submits the first that matches the visible examples. Its deterministic
charge is 0.05 + 0.01 × samples CU, at most 2.61. Verification charges
0.005 CU per case, 0.215 CU in total.

**Run settings.** Budgets 60, 240 and 480 CU; 8 workers; attempt cap
3 CU; at most 64 attempts per task; 1 in flight per task; seeds 1001–1100.
Outcomes are paired by seed: for a given seed, the k-th attempt on a task
is identical under every policy.

**Policies.**

- round_robin, fifo, random;
- greedy_prior;
- thompson(k=2, hints) (TH);
- thompson(k=2, no hints) (TN);
- oracle_index. This uses calibration p̂ and mean charge, so it is an
  estimate rather than true ground truth. Diagnostic only.

**Metrics.**

- **`sim_true_solved`** (primary): problems whose accepted program is also
  correct on the extended 1,000-input check.
- `solved`: accepted by the verifier.
- `sim_dead_attempts`.
- `sim_false_solved`, reported descriptively.

**Statistics.** Paired bootstrap over seeds with the frozen `analysis.py`
(10,000 replicates, seed 26102026), plus a sign test. Δ = TH − round_robin.

## Predictions

These are carried over from the simulation findings:

- **P1:** TH spends more attempts on dead tasks than round_robin at all
  three budgets (CI above 0). Its index favours tasks with confident hints
  and cheap failures, which here include 3 dead tasks.
- **P2a:** Δ on `sim_true_solved` > 0 at budget 60 (CI above 0).
  Prioritising cheap, likely tasks pays when the budget is scarce.
- **P2b:** Δ ≤ 0 at budget 480 (point estimate). This mirrors the
  simulated moderate-budget loss.
- **P3:** the CI for TN − round_robin contains 0 at budgets 240 and 480.
- **P4:** at budgets 240 and 480, TN's mean dead attempts are below TH's.

## Pilot decision on H1, applied to `sim_true_solved`

- **Supported (pilot):** CI above 0 at both budgets 60 and 240.
- **Contradicted (pilot):** CI below 0 at any budget.
- **Inconclusive:** otherwise.

None of these outcomes is confirmatory. The worker is not an LLM, and the
suite was designed by us.

## Invalidation

The pilot is invalid if any of these occur:

- an audit failure;
- `source_dirty` is true;
- a catalog or config hash mismatch;
- a worker-service protocol error.

Verifier timeouts (INCONCLUSIVE receipts) are possible in principle and
would make a run machine-dependent. They are reported if any occur.

## Accepted limitations

- The worker is not an LLM; its success distribution is that of DSL
  search.
- Small task suite (34), built by us.
- The verifier is V1 (not isolated).
- Extended-check "truth" is itself a finite test (1,000 inputs).
- Real logs are platform-specific: receipt reasons name the OS harness.
