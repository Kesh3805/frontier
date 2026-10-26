# exp-006: What does stronger verification cost in verified yield?

Status: **FROZEN** before any exp-006 outcome was generated. The scoring
script [`evaluate.py`](evaluate.py) is frozen with this protocol.
Kind: **real tasks, pilot** (non-LLM worker). Not confirmatory.

## Why

The v1 hidden suite (43 cases) accepts boundary bugs (exp-005). Suite v2
adds 156 exhaustive small inputs (199 cases), which removes every
calibration false acceptance. But it charges 0.995 CU per verification
instead of 0.215, about 4.6×, so each attempt costs more. The question is
the program's central trade-off in miniature: does stronger verification
buy correctness at the price of fewer verified results per unit of
compute?

## Design

Identical to exp-004 (shuffled order, seeds 1001–1100, budgets 60/240/480,
the same 7 policies, the same worker streams), except:

- catalog v2 (`cb72f7fd…`): the same tasks, hints and labels, with the v2
  hidden suite;
- the server runs with `--suite-version 2`;
- the verification reservation is 1.0 CU.

Pairing (budget, policy, seed) against exp-004 isolates the verifier.

## Frozen inputs

Config commit `0bbb52c07383457edf482390b08fdf660a4a6256`:

| File | SHA-256 |
|---|---|
| `research/preregistration/exp-006/b60.json` | `f9c78954888da1d1a2bac1ca07c2b470c00737ee3210be0fca35573b331e4de0` |
| `research/preregistration/exp-006/b240.json` | `1173b66532f4694d99e30f59942f21d95e4e812f99ca7a731894d0ad23a440c4` |
| `research/preregistration/exp-006/b480.json` | `aa2d9c4d45c7ee1c5535e0472b8e0fb3d35b485a39da152eeb26b096a7f024e6` |
| `research/realtasks/catalog-v2.json` | `cb72f7fdc87d04c8700fa6c543da98a9005af35a6645ef6623d66bfcf1fbbb47` |
| `python/frontier_py/realtasks/suite.py` | `3be7c1d625de0e6878bb6592544de82e4d92681a0ae3c423356ad0f3178af208` |
| `python/frontier_py/realtasks/server.py` | `31f96918bbb94ea73d51d820e5b0a5b2d25a2e93c73cc70e9e8fb0a257dac990` |

## Predictions (v2 − v1, paired; true solves unless stated)

- **W1:** at most one exp-006 run, across all budgets and policies, has a
  false solve. exp-004 had 0–7% of runs with one.
- **W2:** at budget 60, round-robin's true solves fall (CI below 0).
  Verification eats the scarce budget.
- **W3:** at budget 480, round-robin's true solves change by less than 0.3.
- **W4:** at budget 240, round-robin's verification share of committed
  compute more than doubles.

**Decision, for round-robin:**

- "strong verification does not cost true yield" if every budget's CI
  lower bound is ≥ 0;
- "costs true yield at some budget" if any CI lies entirely below 0;
- otherwise "inconclusive".

Thompson's Δ vs round-robin under v2 is also reported, to see whether the
scheduler comparison is robust to the verifier.

## Invalidation

As exp-003/004.

## Limits

- Verification is charged for every case, even after the first failure.
  A fail-fast verifier would make wrong candidates cheaper; that is a
  natural follow-up.
- v2's improvement is measured against a finite truth (the extended check).
- Non-LLM worker.
