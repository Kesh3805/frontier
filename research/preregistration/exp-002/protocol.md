# exp-002: Do optimistic hints on undetected dead problems cause the R2-moderate loss?

Status: **FROZEN** before any exp-002 outcome was generated. The scoring
script [`evaluate.py`](evaluate.py) is frozen with this protocol.
Kind: **simulation**. Kernel 0.2.0.

## Frozen inputs

SHA-256 of committed bytes at config commit `09dd828cbc2be0353e42e726580d62ab4291bd64`:

| File | SHA-256 |
|---|---|
| `research/preregistration/exp-002/b600.json` | `d2bf4d3ef1a1e3b40ba2818bcea841b99e59a8c5b26db87f3137b5cffa871b8b` |
| `research/preregistration/exp-002/b1200.json` | `ac07ff02e380f2590b33790aa81e230a7acef91c381291d6a5812b0a6be39677` |
| `research/preregistration/exp-002/make_configs.py` | `10b6d03ba9caf39a4569d491bcb121c316a14212c4db6645b866fba15a9149e5` |
| `python/frontier_py/analysis.py` | `fbbf32e21c9cb5e9814820f7a0dc76e4ed7d1490a773256556fc6bced5661a0c` |
| `crates/frontier-sim/src/env.rs` | `df9da31c8dec3b3b4b0c549a6e77c4d1087b6b766cd1dea0506483f462eb1b97` |
| `crates/frontier-sim/src/runner.rs` | `2996b80fc2ed75149c9872eef098f6e58e8e0409cb2f9c5886a0e48ff0d01940` |
| `crates/frontier-sched/src/lib.rs` | `4727cce88e0cb0ae9f0e968d038f86e70a335d6461fc1808e9a9da892b4ef149` |
| `crates/frontier-core/src/rng.rs` | `5ecbacfcfc99ba7ae3023ad0bc2bd5b8d7174f6290cc22517782451bdf697c09` |
| `crates/frontier-core/src/detmath.rs` | `cb57fa4cd279c2f29bbaa220e24ac36114af5d2460b358613705493e7b1678c7` |

The hash of `evaluate.py` is recorded in the commit that freezes this
protocol.

## Background

exp-000 found the loss and exp-001 replicated it. With i.i.d. attempts in
R2 (d=0.11, Beta(0.38, 0.17)) at budget 600, Thompson with prior hints lost
to round-robin: Δ = −0.26 problems, CI [−0.38, −0.14]. Removing hint noise
did not remove the loss.

The simulator always gave dead problems live-looking hints, so no
condition ever revealed deadness. exp-002 introduces
`dead_hint_detection` λ: the probability that the predictor recognises a
dead obligation and reports a near-zero estimate. Ground truth and the
hints of live problems are identical across λ.

## Mechanisms under test

- **O (optimistic dead priors).** A high hint on an undetected dead
  problem adds pseudo-successes to its Beta prior. Its posterior then
  decays slowly as failures accumulate, so dead problems absorb attempts
  that round-robin would spend on solvable problems.
- **U (alternative: under-exploration of live problems).** Problems that
  are solvable but have low hints are starved. This does not depend on
  dead problems, so it would not respond to λ.

## Design

- Regimes and budgets:
  - R2 and R3 (exp-001 parameters, hint noise 1) at budget 600;
  - R2 at budget 1200;
  - λ ∈ {0, 0.5, 1} in each.
- Policies: round_robin, greedy_prior, thompson(k ∈ {0.5, 2, 8}, hints),
  thompson(k=2, no hints), oracle_index.
- Seeds 1–200, paired by (regime, seed). Other settings are as in exp-001.
- Metrics:
  - `solved`;
  - `sim_dead_attempts`, the attempts dispatched on obligations whose true
    p = 0 (ground truth).
- Statistics: paired bootstrap from the frozen `analysis.py` (10,000
  replicates, seed 26102026).

TH means thompson(k=2, hints) and RR means round_robin. Δ(λ) = TH − RR on
`solved`. ΔD(λ) = TH − RR on `sim_dead_attempts`.

## Predictions

The primary cell is R2 at budget 600.

- **P1:** ΔD(0) > 0 with the CI entirely above 0. TH spends more attempts
  on dead problems than RR.
- **P2:** TH's mean `sim_dead_attempts` falls as λ rises: λ=0 > λ=0.5 > λ=1.
- **P3:** Δ(0) < Δ(0.5) < Δ(1) (point estimates).
- **P4:** the CI of Δ(1) is not entirely below 0, so the loss is gone with
  full detection.
  - *P4-strong*, reported but not decisive: the CI lower bound of Δ(1) is
    above 0.
- **P5:** at λ=0, the mean `sim_dead_attempts` of thompson(k, hints) rises
  with k: k=0.5 < k=2 < k=8.

Secondary (reported, not decisive): P1 and P3 in R2 at budget 1200 and in
R3 at budget 600.

## Decision rule for mechanism O

- **Supported** if P1, P2, P3 and P4 all hold in the primary cell.
- **Refuted** if P1 fails (TH does not over-spend on dead problems), or if
  the CI of Δ(1) lies entirely below 0 (the loss persists with full
  detection, which points to U or something else).
- **Partially supported** otherwise.

## Invalidation

The experiment is invalid if any of these occur:

- an audit failure;
- `source_dirty` is true;
- a config hash mismatch;
- CI failure of the pinned cross-platform smoke head at the freeze commit.

## Accepted limitations

- Detection is all-or-nothing per dead obligation.
- A detected dead obligation's hint is logit(0.001) plus noise. There are
  no false detections: live problems never get dead-looking hints, which
  favours hint use.
- Single-step problems only.
- "Dead" means p = 0 exactly. Real problems are more often near-dead,
  which is not modelled.
