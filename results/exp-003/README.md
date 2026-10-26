# exp-003 results: first real verifier-backed pilot (non-LLM worker)

> **Correction (exp-004).** The task-order confound flagged below also
> affected round_robin (−0.79 at budget 60) and greedy_prior. With order
> shuffled per seed, the budget-240 gain is no longer significant, and the
> pilot H1 verdict becomes **inconclusive**. See [exp-004](../exp-004/README.md).

**Kind: REAL TASKS, PILOT.** Real candidate programs, real subprocess
verification (property tests, trust class V1). The worker is a
deterministic DSL program search, **not an LLM**. Not confirmatory.

Protocol and scoring script:
[`research/preregistration/exp-003/`](../../research/preregistration/exp-003/protocol.md),
both frozen at `f90eaf3`.

**Runs.** 2,100 campaigns (34 tasks × 7 policies × 100 seeds × 3 budgets)
from that commit, with a clean tree. Every run passed the log audit.

**Host.** Windows, i5-1135G7, 8 threads.

**Wall time.** 36 minutes. Most of it is real verification: one subprocess
per unique candidate program.

**Reproducibility.** A re-run of 6 seeds × 7 policies at budget 480 with 2
threads instead of 8 reproduced all 42 log heads exactly. So there is no
sign of load-dependent verifier timeouts.

Data: [`evaluation.json`](evaluation.json) and `runs.csv.gz`.

The primary metric is **true solves**: tasks whose accepted program is also
correct on a 1,000-input extended check. Δ is the paired difference
against round-robin over 100 seeds, with 95% bootstrap CIs.

## Results

| Policy | True solves @60 | Δ @60 | True solves @240 | Δ @240 | True solves @480 | Δ @480 |
|---|---|---|---|---|---|---|
| round_robin | 12.28 | | 20.52 | | 23.08 | |
| thompson (hints) | 13.30 | **+1.02** [0.64, 1.41] | 21.14 | **+0.62** [0.34, 0.90] | 23.36 | +0.28 [0.12, 0.44] |
| thompson (no hints) | 10.50 | −1.78 [−2.17, −1.36] | 20.27 | −0.25 [−0.54, 0.04] | 23.22 | +0.14 [−0.01, 0.29] |
| greedy_prior | 13.20 | +0.92 [0.53, 1.31] | 21.50 | +0.98 [0.74, 1.22] | 23.30 | +0.22 [0.04, 0.40] |
| random | 9.89 | −2.39 [−2.79, −1.98] | 20.59 | +0.07 [−0.09, 0.23] | 23.22 | +0.14 [0.02, 0.26] |
| fifo ⚠ | 15.69 | +3.41 [3.10, 3.74] | 21.84 | +1.32 [1.03, 1.62] | 22.90 | −0.18 [−0.39, 0.02] |
| oracle_index (estimated) | 16.19 | +3.91 [3.57, 4.26] | 22.38 | +1.86 [1.62, 2.11] | 23.87 | +0.79 [0.61, 0.98] |

There are 26 live tasks; 8 tasks are dead.

### Scorecard

| Prediction | Result |
|---|---|
| P1: thompson (hints) over-spends on dead tasks at every budget | ✔ +22, +156 and +80 attempts beyond round-robin (all CIs above 0) |
| P2a: gain at budget 60 | ✔ +1.02 [0.64, 1.41] |
| P2b: no gain at budget 480 | ✘ +0.28 [0.12, 0.44] |
| P3: hint-free thompson ≈ round-robin at budgets 240 and 480 | ✔ Both CIs contain 0 |
| P4: hint-free thompson wastes fewer dead attempts than the hinted version at budgets 240 and 480 | ✔ |
| **H1 (pilot rule)** | **Supported:** CI above 0 at budgets 60 and 240 |

## How to read this, skeptically

1. **FIFO's lead is an artifact of how the suite was built.** I wrote the
   easy tasks first and appended all 8 dead tasks last. "Lowest index
   first" therefore carries hidden difficulty information. FIFO's result
   is **not** a finding. Round-robin also iterates in this order; it treats
   all tasks symmetrically, but it is not proven immune. Fix for the next
   run: shuffle problem order per seed.
2. **Prior information, not learning, explains most of the gain.**
   - With hints, thompson gains at every budget.
   - Without hints, it **loses** badly at budget 60 (−1.78), as it did in the
     simulator's dead-heavy, scarce-budget cell (exp-001/002 R3).
   - The static hint index (greedy_prior), which never learns, is about as
     good as thompson with hints.
   - This is the exp-000 secondary finding, reproduced on real tasks.
3. **Thompson with hints wastes many attempts on dead tasks, as predicted.**
   It spends 156 more dead attempts than round-robin at budget 240,
   because 3 dead tasks carry confident probe hints and fail cheaply. It
   still gains overall: the hints help more on live tasks than they cost
   on dead ones.
4. **Some dead attempts are forced by the run design, not chosen by
   policies.** Even the estimated oracle spends 150 attempts on dead tasks
   at budget 240. With 8 workers, at most one attempt in flight per task,
   and policies that never leave a worker idle, a worker is sent to a dead
   task whenever every remaining live task already has an attempt running.
   This interaction between work conservation and the parallelism cap is
   a design issue for future runs. It is an explanation, not tested here.
5. **Real verifier false acceptances occur.** The frozen hidden suite (43
   cases with values in [−20, 20]) accepted programs that the extended
   check rejects; calibration located these in max0, span and max_abs.
   The share of runs with at least one false solve was:

   | Budget | Runs with a false solve |
   |---|---|
   | 60 | 0–3% |
   | 240 | 4–5% |
   | 480 | 5–7% |

   This is a direct, real-world instance of exp-001's base-rate finding:
   more attempts give a weak test suite more chances to accept a wrong
   answer.

## What carries over from simulation, and what doesn't

| Simulation finding | On real tasks |
|---|---|
| Hinted allocation over-spends on dead problems that look feasible (exp-002) | ✔ Reproduced |
| Hint-free adaptivity loses at scarce budget when dead problems are common | ✔ Reproduced |
| Hints carry most of the gain | ✔ Reproduced |
| Hinted allocation loses at generous budget (exp-000/001 R2) | ✘ Not reproduced: a small gain instead. Here 5 of 8 dead tasks *are* flagged by the hint (detection ≈ 0.6), and exp-002 showed detection removes that loss. |

## Limits

- The worker is not an LLM.
- 34 tasks, written by us.
- Task-order confound (see 1).
- Trust class V1: no OS sandbox. Tasks are trusted DSL output anyway.
- The extended check is finite.
- The oracle uses calibration estimates.

**Bookkeeping bug, found after the run:** `verify_wall_seconds` in the
manifests is inflated. Memoised verifier replies re-reported their
original wall time on every cache hit, giving 45,653 s for a 1,216 s run.
It is outside the deterministic log and affects no result; it is fixed in
the commit after this one.

## Next

- exp-004: re-run with problem order shuffled per seed, to remove the FIFO
  confound and check that the round-robin baseline is not order-sensitive.
- Then: an LLM worker, which requires an explicit spending authorisation,
  and a verifier with a larger hidden suite.
