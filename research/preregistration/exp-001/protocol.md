# exp-001: Why did adaptive allocation lose in R2-moderate, and does its advantage survive correlated failures and imperfect verifiers?

Status: **FROZEN** before any exp-001 outcome was generated.
Kind: **simulation** (synthetic environment, no models, no spend).
Kernel: 0.2.0 (portable math). Random streams differ from exp-000's, so
any exp-000 cell repeated here is a **replication with new random
numbers**, not a re-execution.

## Frozen inputs

SHA-256 of committed (LF) bytes at source commit
`667476fab22f697f92ff33bc06a33d3f7281fade`:

| File | SHA-256 |
|---|---|
| `A-b300.json` | `d338c5390c9f26d6ae6c6dcf1d1f9c4b6bc3514cf68c25a006a4810db9e2a9f2` |
| `A-b600.json` | `bcdb86d9219c914de1c5eba82c29e46fe63b00ddc5bbf0524b6a9d59ecb76da8` |
| `A-b1200.json` | `40fd0239b4ab07c431c593909c828e81e0445b210599ee90789670ea24f2580a` |
| `B-scarce.json` | `a5fe3965d1239113b17892a6c5e7e16349ee6aa168a3b69170af39bf1553e3d9` |
| `B-moderate.json` | `73e934d8c5a1e0c46e2f473d70ec06208217879a2c12afd6c3cfaa68f9f161d9` |
| `C-moderate.json` | `2f182e458d9c8a7db73d32f9323d23bb15fbaf0aa612e65739bf8ac25f09b0bf` |
| `make_configs.py` | `2a905df025cc780bf6080e5a917409d95861e6a367e12a69cea8359ab4828b62` |
| `python/frontier_py/analysis.py` | `fbbf32e21c9cb5e9814820f7a0dc76e4ed7d1490a773256556fc6bced5661a0c` (unchanged from exp-000) |
| `crates/frontier-sim/src/runner.rs` | `8ccb15983ad87e9adc591255c7efdce53613a50c1a71684dd8e1e1ecd424a10a` |
| `crates/frontier-sim/src/env.rs` | `62d3058072810b00bd4491397a22f6a689e86231a28b1d7375f02d8106b7679a` |
| `crates/frontier-sched/src/lib.rs` | `4727cce88e0cb0ae9f0e968d038f86e70a335d6461fc1808e9a9da892b4ef149` |
| `crates/frontier-core/src/rng.rs` | `5ecbacfcfc99ba7ae3023ad0bc2bd5b8d7174f6290cc22517782451bdf697c09` |
| `crates/frontier-core/src/detmath.rs` | `cb57fa4cd279c2f29bbaa220e24ac36114af5d2460b358613705493e7b1678c7` |

## Common settings

The run settings match exp-000: 50 problems, 8 workers, attempt cap 8 CU,
verification 0.25 CU, crash probability 0.02, at most 64 attempts per task,
1 in flight per task, seeds 1–200. Pairing is by (regime, seed). Every
comparison uses the frozen `frontier_py.analysis`: paired mean difference
and 95% percentile bootstrap CI (10,000 replicates, seed 26102026), plus
an exact sign test.

Notation: **Δ = thompson(k=2, hints) − round_robin**, unless a policy is
named. "Increases" or "decreases" across a factor refers to paired point
estimates.

Parameters for each regime:

| Regime | d | α | β | Shape |
|---|---|---|---|---|
| R2 | 0.11 | 0.38 | 0.17 | single-step |
| R3 | 0.30 | 0.27 | 0.91 | single-step |
| R5 | R2 per obligation | | | 1–3 approaches × 1–4-step chains, shared lemmas p = 0.5 |

All three have hint noise 1, unless varied.

## Part A: mechanism of the exp-000 R2-moderate loss

**Design.** R2 with hint noise ∈ {0, 1, 2} and budget ∈ {300, 600, 1200}.
Policies:

- round_robin
- greedy_prior
- thompson(k ∈ {0.5, 2, 8}, hints)
- thompson(k=2, no hints)
- oracle_index

Metric: `solved`.

**Hypothesis M.** The loss comes from acting on misleading prior hints.
Problems that look hard but are solvable are under-sampled. Round-robin
still reaches them.

**Predictions:**

- **P-A0 (replication):** at noise 1 and B=600, Δ < 0 with the CI entirely
  below 0.
- **P-A1:** at noise 0, the CI lower bound of Δ is ≥ 0 at all three
  budgets, and the CI excludes 0 at B=300.
- **P-A2:** at each budget, Δ(noise 0) > Δ(noise 1) > Δ(noise 2).
- **P-A3:** at noise ∈ {1, 2} and B ∈ {600, 1200} (four cells),
  Δ_k=0.5 > Δ_k=2 > Δ_k=8, where Δ_k is thompson(k, hints) − round_robin.
- **P-A4:** thompson(k=2, no hints) − round_robin at B=1200 and noise 1 has
  a CI that contains 0 or lies above 0.

**Decision.**

- M is **supported** if P-A1, P-A2 and P-A3 all hold.
- M is **refuted** if P-A1 fails, because perfect hints would still lose.
- Otherwise M is **partially supported**, and we report which predictions
  failed.

## Part B: correlated attempt failures

**Design.** R2, R3 and R5, each with failure stickiness ρ ∈ {0, 0.5, 0.9},
at budgets 150 (scarce) and 600 (moderate).

- ρ is the lag-1 correlation of outcomes across attempts on the same
  obligation. Marginal success stays at p.
- Policies: round_robin, greedy_prior, thompson(k=2, hints),
  thompson(k=2, no hints), oracle_index.
- oracle_index knows p but assumes independent attempts.
- Metric: `solved`.

**Predictions:**

- **P-B1:** within each regime × budget, every policy's mean `solved`
  decreases from ρ=0 to ρ=0.9.
- **P-B2:** Δ(ρ=0) > Δ(ρ=0.9) in all six regime × budget cells.
  Concentrating attempts loses value when repeated attempts copy earlier
  failures, while round-robin's first attempts stay fresh.
- **P-B3:** at ρ=0.9, at least one of the six cells has Δ with its CI
  entirely below 0.

**Decision.** The adaptive advantage is "robust to correlation" only if,
in every cell where Δ(ρ=0) has a CI above 0, Δ(ρ=0.9) also has a CI above 0.

## Part C: imperfect verifiers

**Design.** R2, R3 and R5 at budget 600, with distinct solution content
throughout and (fnr, fpr) ∈ {0, 0.2} × {0, 0.02}.

- Policies: round_robin, greedy_prior, thompson(k=2, hints),
  thompson(k=2, no hints).
- **Primary metric:** `sim_true_solved`, problems whose accepted chain is
  entirely correct.
- **Also reported:** `sim_false_solved`, and the overstatement
  `solved − sim_true_solved`.

**Predictions:**

- **P-C1:** with fpr = 0.02, every policy has mean `sim_false_solved` > 0.
- **P-C2:** with fnr = 0, fpr = 0.02, the difference in `sim_false_solved`
  for thompson(k=2, hints) − round_robin has a CI entirely below 0 in R2
  and in R3. Round-robin spends more attempts on dead problems, which
  gives false positives more chances.
- **P-C3:** fnr = 0.2 lowers every policy's mean `sim_true_solved` compared
  with (0, 0), at the same fpr.
- **P-C4:** in each regime, the sign of Δ on `sim_true_solved` at
  (0.2, 0.02) is the same as at (0, 0).

## Invalidation

The experiment is invalid if any of these occur:

- an audit failure;
- `source_dirty` is true;
- a config hash mismatch;
- the pinned smoke log head fails in CI on Linux, meaning cross-platform
  results are not established. In that case results stand as
  Windows-only, and that limitation is stated.

## Accepted limitations

- Stickiness is lag-1 and per obligation only. There are no failures
  shared across problems.
- Verifier errors are independent across attempts.
- A false-positive lemma makes its whole chain unsound, but dependents
  still run at their nominal p.
- Hint noise is symmetric in logit space.
- The oracle's index ignores stickiness.
