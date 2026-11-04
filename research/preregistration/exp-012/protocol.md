# exp-012: Does pricing a novel candidate fix hinted Thompson under the measured verification cost?

Status: **FROZEN** before any exp-012 outcome was generated, and before any
exp-011 outcome was looked at. The scoring script [`evaluate.py`](evaluate.py)
is frozen with this protocol.
Kind: **real tasks, pilot** (non-LLM DSL worker; trust class V1). Not
confirmatory.

## Why

exp-010 found that, under the measured verification charge, hinted
Thompson loses to round-robin at moderate single-step budgets (−0.93 at
1,320 CU; not preregistered). [exp-011](../exp-011/protocol.md) tests one
explanation by removing the cost signal entirely (`thompson_flat`).

An independent review of the exp-011 design (ChatGPT, given the public
repository) raised two problems:

- **Flat cost is not a clean test.** It also throws away real per-task
  generation-cost differences.
- **Reused rejections are not independent evidence.** A candidate
  byte-identical to one already rejected says nothing new about whether the
  task is solvable. Yet the runner counts it as a failure in the success
  posterior.

The design below came out of that exchange. The useful unit is the **cost
of one novel candidate**, not the cost of one attempt.
- Let q be the chance that an attempt produces a fresh candidate, G the
  generation cost per attempt, and V the cost of verifying a fresh
  candidate. Then one novel candidate costs G / q + V.
- Success probability p is per novel candidate.
- Thompson's index becomes (G / q + V) / p. A task that keeps returning the
  same rejected candidate (q → 0) becomes expensive, not cheap.

That separates two questions that the current index mixes:

1. **Cost model:** observed mean charge per attempt vs cost per novel
   candidate.
2. **Reuse evidence:** a reused rejection counts as a failure vs is
   ignored.

## Design

`thompson_novel` was added in harness commit
`e4939f7e26b8bd018ae8c47891ecfef736e74d5f`.
- **Cost (`per_novel_cost`):** G / q + V, where:
  - G is the task's mean generation units per informative attempt;
  - V is the task's mean verification units per novel candidate;
  - each falls back to the mean pooled over all tasks, then to
    `prior_cost`;
  - q is Thompson-sampled at every decision from
    Beta(1 + novel, 1 + other informative attempts).
- **Novel vs other:** a *novel* attempt is one whose candidate was freshly
  verified. *Other informative* attempts are reused rejections and
  timeouts. Crashes and attempts cancelled because their task closed
  update neither count.
- **Reuse evidence (`reuse_is_failure` false):** reused rejections are
  removed from the success posterior's failure count. Timeouts stay
  failures.
- **The baseline cell:** observed cost with reuse counted as failure is
  exactly the existing `thompson` policy. A unit test asserts identical
  choices. The runner's new bookkeeping does not change any existing
  policy: a dev run of round-robin, Thompson and flat Thompson was
  bit-identical on the old and new binaries.

Configs come from [`make_configs.py`](make_configs.py): the exp-010 S-v2
configs (catalog v2, hidden suite v2, `--charge-model measured`,
`verify_cost_units` 11.6, 8 workers). Budgets are 330, 1,320 and 2,640
CU, with **fresh seeds 7001–7100**. Six hinted policies (k = 2):

| Label | Cost model | Reuse |
|---|---|---|
| RR: `round_robin` | | |
| TH: `thompson` | observed | failure |
| OI: `thompson_novel(..., cost=observed, reuse=ignored)` | observed | ignored |
| NF: `thompson_novel(..., cost=novel, reuse=failure)` | per novel | failure |
| NI: `thompson_novel(..., cost=novel, reuse=ignored)` | per novel | ignored |
| FL: `thompson_flat` (bridge to exp-011) | constant | failure |

That is 6 × 100 × 3 = 1,800 audited runs. The primary metric is
`sim_true_solved`. The mechanism metric is `sim_dead_attempts`. Paired by
seed with the frozen `analysis.py` bootstrap (10,000 replicates, seed
26102026).

## Frozen inputs

Harness commit `e4939f7e26b8bd018ae8c47891ecfef736e74d5f`. SHA-256 of
each file with LF line endings:

| File | SHA-256 |
|---|---|
| `research/preregistration/exp-012/make_configs.py` | `c537f5abe5b475d24c46fc5bfe6059cdebb6387ec488245b5d45b323e212e229` |
| `research/preregistration/exp-012/evaluate.py` | `3e4b054c95e7eb22cf42734dc85d2899c1961d780047e04e3b42e8f9b0ab4551` |
| `research/preregistration/exp-012/b330.json` | `33f724229fbbc0e0107d47dfa04a05991172035f8632954ffa55ac987ff32816` |
| `research/preregistration/exp-012/b1320.json` | `a4563fefc7669bed3a1d0d7f2338e50fd8e4d50294a69ae37fe07b9b63c4e0eb` |
| `research/preregistration/exp-012/b2640.json` | `ae5b7afad9354fc512d2a9a8e0c074b041c2a4fc723a81631765b623bb9068dc` |
| `crates/frontier-sched/src/lib.rs` | `a87a5c9184490242627c502e57e72a5fea516e8c18cb11fc5cf4bcc9da6435fb` |
| `crates/frontier-sim/src/runner.rs` | `50a77677447a79f0f6a8a0d85787621c95cf348419c97cfa3694d7f878e37fdb` |
| `python/frontier_py/realtasks/server.py` | `72ff87cfae3a07ca7fd36136cab289f85fb753110b496d47b079280fa1f115c7` |
| `python/frontier_py/verifiers/property_tests.py` | `7944be8850c672e4e6d84d6ec68a3ee9ba50e3620dd94fb7fd6c8dbfb7e01a39` |
| `python/frontier_py/analysis.py` | `fbbf32e21c9cb5e9814820f7a0dc76e4ed7d1490a773256556fc6bced5661a0c` |

## Seen before freezing (disclosed)

- **All published data from exp-010 and earlier**, and the exp-011 protocol.
  No exp-011 outcome was looked at. exp-011 was still running; only its
  first config's record count and manifest were checked.
- **A unit-test fixture** (a task with one fresh and 15 reused rejections
  against a task with one fresh rejection). Out of 400 draws, the
  stuck task was chosen:

  | Cell | Times chosen |
  |---|---|
  | TH | 244 |
  | OI | 376 |
  | NI | 166 |
  | NF | 34 |

  Ignoring reuse alone makes stuck tasks more attractive. Pricing a novel
  candidate takes back part of that pull. Because V (~11.5 CU) dominates G
  (~0.5 CU), G / q adds relatively little until q is very small.
- **A dev smoke run** of b1320 with all six policies, dev seed 1, one run
  each. Only accounting fields were looked at, as attempts / committed CU
  / reused rejections:

  | Cell | Attempts | Committed CU | Reused rejections |
  |---|---|---|---|
  | RR | 110 | 1310.5 | 12 |
  | TH | 161 | 1308.2 | 59 |
  | OI | 163 | 1305.5 | 61 |
  | NF | 163 | 1311.0 | 61 |
  | NI | 166 | 1309.4 | 64 |
  | FL | 177 | 1309.4 | 75 |

  On this seed, no new cell cut reused rejections, which is weak evidence
  against N6.
- **A scoring-script check:** `evaluate.py` was run on exp-010 S-v2 data,
  with Thompson copied into every other Thompson cell. It reproduced the
  published −0.93 and +2.47, and an exact 0 for every Thompson-vs-Thompson
  contrast.

## Predictions

All at b1320 unless stated.

- **N1: per-novel pricing recovers yield.** NF − TH has CI > 0.
- **N2: it closes most of the gap.** NF − RR ≥ −0.3 (point).
- **N3: it keeps the scarce-budget gain.** NF − RR at b330 has CI > 0.
- **N4: ignoring reuse alone hurts.** OI − TH has CI < 0.
- **N5: the cost model matters more when reuse is ignored.** The point
  estimate of (NI − OI) exceeds that of (NF − TH).
- **N6: per-novel pricing spends fewer attempts on dead tasks.** For
  `sim_dead_attempts`, NF − TH has CI < 0.
- **N7: verdict quality is unchanged.** No run has a false solve.

## Decisions

- **"Pricing a novel candidate fixes hinted Thompson's moderate-budget
  loss"** if N1 and N6 hold.
- **"Pricing a novel candidate does not help"** if the CI upper bound of
  NF − TH is ≤ 0.
- **"Unclear"** otherwise.

Results at b2640, NI, FL and all means are reported descriptively. FL
against TH here can be compared with exp-011's result on different seeds.

## Invalidation

The pilot is invalid if any of these occur:

- an audit failure;
- `source_dirty` is true;
- a config or catalog hash mismatch;
- a service protocol error.

## Limits

- **One host's cost:** the measured charge constants are this Windows
  host's. Linux's fixed cost is about 4.8× smaller (exp-009L), which would
  change V relative to G.
- **The novelty model:** q is a stationary per-task rate. A worker whose
  search space is exhausting may have a falling q.
- **Hints:** all policies use the same hints. Whether better-calibrated
  hints would remove the loss is not tested here.
- **Worker, tasks and verifier:** non-LLM worker, tasks written by the
  project, V1 verifier (`--sandbox none`).
