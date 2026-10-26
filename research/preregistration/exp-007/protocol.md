# exp-007: Does allocation help when verified lemmas unlock further work? (real dependency tasks)

Status: **FROZEN** before any exp-007 outcome was generated. The scoring
script [`evaluate.py`](evaluate.py) is frozen with this protocol.
Kind: **real tasks, pilot** (non-LLM DSL worker; trust class V1 verifier).
Kernel 0.3.0. Not confirmatory.

## Why

The project review asked for dependency-structured research tasks:
intermediate verified results that unlock further work, with delayed
rewards. In simulation, the matching regime (R5: alternative approaches,
lemma chains, shared lemmas) showed the largest scheduler effects. The
corrected kernel-0.3 re-run of exp-000 gives:

| Policy (vs round-robin) | R5, scarce budget | R5, moderate budget |
|---|---|---|
| Hinted Thompson | +12.7 | +1.3 |
| Hint-free Thompson (exp-001 Part B, ρ=0) | about +10 | — |

The gain came mostly from structure awareness: choosing the cheapest
remaining approach. exp-007 asks whether that carries over to real
lemma-structured tasks.

## Frozen inputs

Config commit `4f02843909260d91036cbf3394bfb374907f5bcd`:

| File | SHA-256 |
|---|---|
| `research/preregistration/exp-007/b120.json` | `51783fe517b81c5f648c8bbce993b52fd84792677dafbce26960e8d4b58776a5` |
| `research/preregistration/exp-007/b480.json` | `8520219167eeddc86a14b4b15a08ed99389c40dcec8999922c287c3c0bedf6f1` |
| `research/preregistration/exp-007/b1920.json` | `b24b5dc042afe34987527f384e320b9ef47977564e438ff247b98f1c904493de` |
| `research/preregistration/exp-007/make_configs.py` | `e37bc260140f4ab447fefd482732709a9adcf480f4c9fc80e853f880f72e9817` |
| `research/preregistration/exp-007/evaluate.py` | `5adff48fc948c421bec5914cc6642c468aa10d910ab214975e630ac18fc1e8dc` |
| `research/realtasks/catalog-v3.json` | `6c63d226d405975517d67fc87f48e4d8345f6f315886cc59d87c35a9b70ef686` |
| `python/frontier_py/analysis.py` | `fbbf32e21c9cb5e9814820f7a0dc76e4ed7d1490a773256556fc6bced5661a0c` |
| `python/frontier_py/realtasks/worker.py` | `73278e8bc05fd8be042a5b6c7bd7f822d854bca3b075d5e2a678e92643fa54e7` |
| `python/frontier_py/realtasks/deps.py` | `72cef3ff1efdd6a0530cdb92012642ba742ab8f26a105304462fb7ff4bb90fe1` |
| `python/frontier_py/realtasks/server.py` | `94a7d7d1327dbaf817022e577b75cba6ad10d66b058af1b346240411a59be524` |
| `crates/frontier-sim/src/runner.rs` | `cd6fa238d27b80d85a6eae070d40b67cfa841bf624b59b90e470daa0aca81fd6` |
| `crates/frontier-sim/src/real.rs` | `2ee22aa54eab772f93ace99934a423c275e509332cb3d62d6e726454caef7fbc` |
| `crates/frontier-sched/src/lib.rs` | `4727cce88e0cb0ae9f0e968d038f86e70a335d6461fc1808e9a9da892b4ef149` |

## Seen before freezing (disclosed)

- **Catalog v3 calibration**, per task, with each dependent task calibrated
  on a library whose lemmas are verified (seed 999000001):
  - direct-route vs lemma-route expected costs;
  - the problem labels: 12 lemma-useful, 4 direct-easy, 3 trap, 5 dead.
- **A round-robin-only budget sweep** on dev seeds 1–3, at 30–1,920 CU,
  used to choose the budgets. Round-robin's true solves:

  | Budget (CU) | True solves of 19 live problems |
  |---|---|
  | about 120 | about 3 |
  | 480 | about 11 |
  | 1,920 | about 17 |

- One dev-v3 smoke run per policy in the qualification tests.

No policy comparison on catalog v3 has been seen.

## Design

- **Tasks:** catalog v3, 24 problems and 89 tasks. Each problem is
  solvable directly or through lemma tasks. Verified lemmas are passed to
  dependent attempts as helper functions.
- **Verifier:** hidden suite v2 (exhaustive small inputs plus random),
  charged per case. Trust class V1, with `--sandbox none`: the DSL
  programs are the project's own.
- **Order:** problem order shuffled per seed.
- **Seeds:** 3001–3100, disjoint from all earlier seeds.
- **Budgets:** 120, 480 and 1,920 CU.
- **Run settings:** 8 workers, attempt cap 3 CU, verification reservation
  1.05 CU, at most 64 attempts per task, 1 in flight per task.
- **Policies:**
  - round_robin (baseline);
  - random;
  - greedy_prior (static hint index over approaches);
  - thompson(k=2, hints) (TH);
  - thompson(k=2, no hints) (TN);
  - oracle_index (calibration estimates; diagnostic only).
- **Primary metric:** `sim_true_solved`, problems whose accepted chain is
  correct on the extended 1,000-input check. Also reported: `solved`,
  `sim_dead_attempts`, committed units.
- **Statistics:** paired bootstrap over seeds with the frozen
  `analysis.py` (10,000 replicates, seed 26102026).

## Predictions

- **D1:** TH − round-robin > 0 at budget 120 (CI above 0).
- **D2:** TN − round-robin > 0 at budget 120 (CI above 0). Structure
  awareness alone, without hints, helps.
- **D3:** |TH − round-robin| < 1 at budget 1,920, near saturation.
- **D4:** greedy_prior − round-robin > 0 at budget 120 (CI above 0).
- **D5:** TH spends more attempts on dead tasks than round-robin at budget
  480 (CI above 0). This is the exp-003/004 pattern.

## Pilot decision (H1 on dependency tasks)

- **Supported:** TH's CI is above 0 at budget 120 and its lower bound is
  ≥ 0 at budget 480.
- **Contradicted:** TH's CI lies entirely below 0 at any budget.
- **Inconclusive:** otherwise.

## Invalidation

The pilot is invalid if any of these occur:

- an audit failure, including the new prerequisite and parent checks;
- `source_dirty` is true;
- a catalog or config hash mismatch;
- a service protocol error.

## Limits

- Non-LLM worker.
- The task suite is written by the project.
- Libraries contain the first accepted artifact for each lemma, while
  calibration used calibration attempts; those can differ.
- The verifier is V1.
- The oracle is an estimate.
