# exp-008: Does fail-fast verification charging recover the yield lost to a stronger suite?

Status: **FROZEN** before any exp-008 outcome was generated. The scoring
script [`evaluate.py`](evaluate.py) is frozen with this protocol.
Kind: **real tasks, pilot** (non-LLM DSL worker; trust class V1).
Not confirmatory.

## Why

In exp-006 (corrected), the 199-check hidden suite (v2) removed every
false solve. But it charged every verification in full (0.995 CU), so
verification took 34–42% of compute, and round-robin lost true solves
compared with the 43-check suite (v1):

| Budget | Round-robin true solves lost |
|---|---|
| 60 | −3.93 |
| 240 | −1.88 |
| 480 | −1.06 |

A test runner that stops at the first failing case would charge wrong
candidates only for the cases it ran. Verdicts are unchanged; only the
cost of failures falls.

## Frozen inputs

Config commit `3565087a4d85ffbb28e5531bf3b60753f56b2187`:

| File | SHA-256 |
|---|---|
| `S-b60.json` | `fad1ad344a9cfb59aa968ebfcf4f74c78bc97a9c35ecbd51a33ed3385a927ee0` |
| `S-b240.json` | `b6771c2a100387ea4e3272e8ae938ca8252cbab72f23c8edca09faca2cf25d3f` |
| `S-b480.json` | `8a45ea69b390a6fa56666ae456ea25eca27e0608e6c20d515e8e16c612600a58` |
| `D-b120.json` | `c064d532a09d299bbeab5a30da1cff09a6ad3e3cfccb189b19dc1941a55552f0` |
| `D-b480.json` | `a9fd099427c2ba0c4521b6d95944a060c439759212285407e426468f511f2cb2` |
| `D-b1920.json` | `187fee45b31c697f1319536fbb521a751eb64f2bb39ba73ab96b86225fb4ea37` |
| `make_configs.py` | `91e967c2404b669381934de3c24b36eaed20ca2c4dff20a9b2f373536d76f03d` |
| `evaluate.py` | `64ebb38670d87845e5849834ed4782eef8280b069a48f14a2f946e1db1381458` |
| `python/frontier_py/verifiers/property_tests.py` | `4c08627b8b7805acd03fb7aab78e0c9c3dfb8b297da9fb0141c3652390df897c` |
| `python/frontier_py/realtasks/server.py` | `d7297d3ed4c5cc9b1402d3e9215cd4d00d75d4f2a4b7a22dfd8e3b9aaaa52381` |

## Design

**Part S.** exp-006's frozen configs (catalog v2, suite v2, shuffled
order, seeds 1001–1100, budgets 60/240/480, the same 7 policies), with the
service flag `--fail-fast` added. Comparisons, paired by (budget, policy,
seed):

- **v2 full charge:** exp-006's kernel-0.3 re-run;
- **v1:** exp-004's kernel-0.3 re-run.

**Part D.** exp-007's frozen configs (catalog v3, seeds 3001–3100, budgets
120/480/1920, the same 6 policies) with `--fail-fast`. Paired against
exp-007.

**Why pairing is valid.** Before freezing, current `main` with fail-fast
off was checked against both earlier experiments. It reproduced
exp-006/b60 (4 seeds × 7 policies) and exp-007/b120 (4 seeds × 6
policies) with identical log heads, 28/28 and 24/24. So any difference in
exp-008 comes from fail-fast charging alone.

**What fail-fast changes.** A FAIL caused by a specific case (an output
mismatch or an exception) is charged 0.005 CU for each case up to and
including the first failing one, in suite order: visible, then hidden
(v2: 156 exhaustive small inputs, then 40 random). PASS and INCONCLUSIVE
are charged in full.

**Metric:** `sim_true_solved`. The verification share of round-robin's
compute is also reported.

## Seen before freezing (disclosed)

- The unit test: identical verdicts in both modes, PASS charged in full,
  failures charged less.
- The reproduction check above.
- A smoke test of `evaluate.py`, with the full-charge data substituted for
  fail-fast data, so every difference was zero.

No fail-fast experiment output has been seen.

## Predictions

- **F1:** at S-b240, round-robin's verification share falls by at least
  40% relative to full charge (from 37% to at most 22%).
- **F2:** at S-b60, round-robin's true solves rise with fail-fast (CI above
  0, against v2 full charge).
- **F3:** at S-b60, round-robin recovers at least half of its v1 → v2 loss.
  The recovery fraction is (FF − v2 full) / (v1 − v2 full), on point
  estimates.
- **F4:** at most one fail-fast run, across both parts, has a false solve.
  The verdicts are the same as v2's.
- **F5:** at D-b120, hinted Thompson still beats round-robin under
  fail-fast (CI above 0).
- **F6:** at D-b120, round-robin's true solves rise with fail-fast (CI
  above 0, against exp-007).

## Decision

- **"Fail-fast recovers yield"** if F2 and F3 hold.
- **"Does not recover yield"** if F2 fails.
- **"Partial recovery"** otherwise.

## Invalidation

The pilot is invalid if any of these occur:

- an audit failure;
- `source_dirty` is true;
- a config or catalog hash mismatch;
- a service protocol error.

## Limits

- Fail-fast cost depends on suite order. Exhaustive small inputs come
  first in v2; another order would charge differently.
- Charges are modelled compute units, not measured CPU time.
- Non-LLM worker; tasks written by the project.
