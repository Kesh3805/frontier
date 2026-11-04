# exp-011: Why does hinted Thompson lose at moderate budgets under the measured verification cost?

Status: **FROZEN** before any exp-011 outcome was generated. The scoring
script [`evaluate.py`](evaluate.py) is frozen with this protocol.
Kind: **real tasks, pilot** (non-LLM DSL worker; trust class V1). Not
confirmatory.

## Why

In exp-010, with verification charged at its measured cost, hinted
Thompson lost to round-robin at the moderate single-step budgets: −0.93
[−1.24, −0.61] at 1,320 CU and −0.66 at 2,640. That result was **not
preregistered**. Under the per-case charge, at the matching budgets, it was
roughly level.

Diagnostics on the published exp-010 data (seen before this protocol)
suggest one mechanism. At S-v2-b1320, hinted Thompson made 179 attempts per
run on average, against round-robin's 113. Of those, 102 were on dead tasks
(round-robin: 44), and 75 were reused rejections (round-robin: 15).

A reused rejection is charged only its generation cost (about 0.6 CU).
This is in [`runner.rs`](../../../crates/frontier-sim/src/runner.rs)
(`reused_rejection`). Thompson's index divides each task's *observed mean
cost per attempt* by its sampled success probability. Under the measured
charge, a fresh verification costs about 11.6 CU. So a hopeless task that
keeps returning an already-rejected candidate looks about 20× cheaper per
attempt than a live task; under the per-case charge the gap was about 4×.

**Hypothesis (H-cost).** The observed-cost index is biased towards cheaply
failing hopeless tasks. Every fresh candidate those tasks produce still
costs a full verification. That bias causes the moderate-budget loss.

**Intervention.** `thompson_flat` (added in [PR 20](https://github.com/Kesh3805/frontier/pull/20), harness commit below)
is the same Beta-posterior Thompson index, with every attempt priced at
`prior_cost`. It ranks by sampled success alone. If H-cost is right, it
should spend fewer attempts on dead tasks and recover the lost yield under
the measured charge, and matter less under the per-case charge.

## Design

Configs come from [`make_configs.py`](make_configs.py): catalog v2, hidden
suite v2, the same 8 workers and caps as before, and **fresh seeds
5001–5100** (exp-004/006/008/010 used 1001–1100).

| Part | Source | Charge | Budgets (CU) |
|---|---|---|---|
| M | exp-010 S-v2 | measured (`--charge-model measured`) | 330, 1,320, 2,640 |
| P | exp-006 | per-case (0.005 CU per case) | 60, 240, 480 |

Five policies in every config:

- `round_robin`;
- `thompson(k=2,hints=true)`;
- `thompson_flat(k=2,hints=true)`;
- `thompson(k=2,hints=false)`;
- `thompson_flat(k=2,hints=false)`.

That is 5 × 100 × 6 = 3,000 audited runs. The primary metric is
`sim_true_solved`. The mechanism metric is `sim_dead_attempts`.
`reused_rejections` and `rejected` (fresh rejections) are reported as
well. Comparisons are paired by seed with the frozen `analysis.py`
bootstrap (10,000 replicates, seed 26102026).

## Frozen inputs

Harness commit `a905815ab0c78097537a0ea1200791abd7f8e319` ([PR 20](https://github.com/Kesh3805/frontier/pull/20)).
SHA-256 of each file with LF line endings:

| File | SHA-256 |
|---|---|
| `research/preregistration/exp-011/make_configs.py` | `863677264e22355c1d032da611ac68f18cc76cc830e52cd7632f11b05bb2cb6d` |
| `research/preregistration/exp-011/evaluate.py` | `e6dbef79801f637aa2c715d854f18cb92868a2621accaa692387439e087c7ced` |
| `research/preregistration/exp-011/M-b330.json` | `74defc682eb1b9165fbe16b01b872bbdf83b9180a6fe8cff920fe03666d60a55` |
| `research/preregistration/exp-011/M-b1320.json` | `02f396e369d54582d448c0e8c6a2e25d24e657547f51890a76af0ed99247ae67` |
| `research/preregistration/exp-011/M-b2640.json` | `f23457eac3b54e1729680b7b2139bf4cf5c730ee749eaaf74b9e0a42b6bc6d7f` |
| `research/preregistration/exp-011/P-b60.json` | `9ba215fd179e902f14b12fc5b4e319640b580f21bd509bf5a94d823071752b11` |
| `research/preregistration/exp-011/P-b240.json` | `66d055d170c2b3f0494a87d3faa58292b76bcc27c8bbbce9b5619767c94ed9b7` |
| `research/preregistration/exp-011/P-b480.json` | `39490c88d851bc5201f3a2313dc0401709bb7028dea8940cca9a1f99ef174e4e` |
| `crates/frontier-sched/src/lib.rs` | `d1ecb7e8acce0785b8d7f32448508f88b1da08e4586b62cd10af4a44357da36f` |
| `crates/frontier-sim/src/runner.rs` | `4d7b12198caa86d579568c9f8e6836149d95f7734f4ce95d63d0b1c36c610082` |
| `python/frontier_py/realtasks/server.py` | `72ff87cfae3a07ca7fd36136cab289f85fb753110b496d47b079280fa1f115c7` |
| `python/frontier_py/verifiers/property_tests.py` | `7944be8850c672e4e6d84d6ec68a3ee9ba50e3620dd94fb7fd6c8dbfb7e01a39` |
| `python/frontier_py/analysis.py` | `fbbf32e21c9cb5e9814820f7a0dc76e4ed7d1490a773256556fc6bced5661a0c` |

`property_tests.py` differs from exp-010's harness by the six early-stop
fixes in [PR 17](https://github.com/Kesh3805/frontier/pull/17). Those change only the `--early-stop` path, which neither
part uses.

## Seen before freezing (disclosed)

- **All published exp-010 data**, including the diagnostics quoted in
  *Why*, and exp-004/006/008 data.
- **A dev smoke run** of M-b1320 and P-b240, all five policies, dev seed 1,
  one run each. It checked that the new policy kind deserializes and that
  reservations and charges work. Only these accounting fields were looked
  at, not solve counts. Attempts / committed CU / reused rejections were:

  | Policy | M-b1320 | P-b240 |
  |---|---|---|
  | round-robin | 110 / 1310.5 / 12 | 95 / 237.7 / 9 |
  | hinted Thompson | 161 / 1308.2 / 59 | 218 / 236.0 / 108 |
  | hinted Thompson, flat cost | 177 / 1309.4 / 75 | 199 / 237.4 / 93 |
  | Thompson without hints | 129 / 1312.7 / 30 | 136 / 238.2 / 42 |
  | Thompson without hints, flat cost | 111 / 1309.3 / 13 | 101 / 238.1 / 14 |

  On this one seed, hinted flat-cost Thompson made **more** reused
  rejections than hinted Thompson under the measured charge, which is
  against H-cost. One seed of a randomised policy is weak evidence, and the
  predictions below were not changed after seeing it. An alternative
  explanation is stated so that either outcome can be read: **H-hints**,
  confident hints on dead tasks keep the posterior optimistic. That
  happens whatever the cost index, and under the measured charge each fresh
  rejection those tasks produce costs about 9× more than under the
  per-case charge.
- **A scoring-script check:** `evaluate.py` was run on exp-010 S-v2 and
  exp-008 S data, with each Thompson arm copied as its flat twin. It
  reproduced the published −0.93, +2.47 and +2.29, and an exact 0 for
  every flat-minus-observed difference.

## Predictions

All at part M unless stated. "TH" is hinted Thompson, "THflat" hinted
flat-cost Thompson.

- **R1: the loss replicates on fresh seeds.** TH − round-robin at M-b1320
  has CI < 0.
- **R2: flat cost recovers yield.** THflat − TH at M-b1320 has CI > 0.
- **R3: flat cost spends fewer attempts on dead tasks.** For
  `sim_dead_attempts`, THflat − TH at M-b1320 has CI < 0.
- **R4: flat cost closes most of the gap.** THflat − round-robin at
  M-b1320 ≥ −0.3 (point).
- **R5: the scarce-budget gain survives.** THflat − round-robin at M-b330
  has CI > 0.
- **R6: cost matters more under the measured charge.** THflat − TH is
  larger (point) at M-b1320 than at P-b240.
- **R7: verdict quality is unchanged.** No run has a false solve.

## Decisions

- **"The moderate-budget loss did not replicate"** if R1 fails.
- **"The observed-cost index's bias towards cheaply failing tasks explains
  the loss"** if R1, R2 and R3 hold.
- **"The loss replicated but has another cause"** if R1 holds and the CI
  upper bound of THflat − TH at M-b1320 is ≤ 0. That points to H-hints or
  something else; this experiment does not separate the two.
- **"The loss replicated; the cost-bias explanation is unclear"** otherwise.

Results at M-b2640, P-b60, P-b480 and for the hint-free pair are reported
descriptively.

## Invalidation

The pilot is invalid if any of these occur:

- an audit failure;
- `source_dirty` is true;
- a config or catalog hash mismatch;
- a service protocol error.

## Limits

- **One host's cost:** the measured charge constants are this Windows
  host's (exp-009). Linux's fixed cost is about 4.8× smaller (exp-009L).
- **One intervention:** flat cost removes the cost signal entirely, so it
  also removes any useful cost information. It tests whether the observed
  cost index hurts, not what the best cost estimate is.
- **Worker, tasks and verifier:** non-LLM worker, tasks written by the
  project, V1 verifier (`--sandbox none`).
