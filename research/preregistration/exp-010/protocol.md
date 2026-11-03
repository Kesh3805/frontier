# exp-010: Do the allocation and verification findings survive the measured cost of verification?

Status: **FROZEN** before any exp-010 outcome was generated. The scoring
script [`evaluate.py`](evaluate.py) is frozen with this protocol.
Kind: **real tasks, pilot** (non-LLM DSL worker; trust class V1). Not
confirmatory.

## Why

Every real-task experiment so far (exp-004 to exp-008) charged verification
0.005 CU per case and nothing per call. exp-009 measured the real cost on
this host: about 120.5 ms fixed plus 0.0516 ms per case. In the worker's
own unit (one DSL sample = 0.01 CU, measured at 0.1133 ms, so 1 s = 88.3
CU) that is:

| | Per-case model (so far) | Measured (exp-009) |
|---|---|---|
| Verification, suite v1 (43 cases) | 0.215 CU | 10.84 CU |
| Verification, suite v2 (199 cases) | 0.995 CU | 11.55 CU |
| v2 extra over v1 | 4.6× | 1.07× |
| Fail-fast saving on a first-case failure | 99% | 7.8% |

So the per-case figure was about right, but a fixed cost about 11× a whole
v2 charge was missing. Three earlier conclusions depend on the charge:

- **exp-006:** the stronger suite costs 1–4 true solves per run.
- **exp-008:** fail-fast charging recovers most of that loss.
- **exp-004/006/007:** the size of adaptive allocation's gain over
  round-robin at a scarce budget.

## Design

`--charge-model measured` (service) charges a verification
10.64 CU + 0.00456 CU × cases charged. Generation charges are unchanged.
Configs come from [`make_configs.py`](make_configs.py): the frozen exp-004,
exp-006 and exp-007 configs with only these changes:

- the charge model;
- `--fail-fast` in one arm;
- budgets × 5.5;
- `verify_cost_units` set to the measured full charge, rounded up (10.9 CU
  for v1, 11.6 for v2).

The ×5.5 is the ratio of the cost of a v2 attempt plus verification under
the measured charge (1.35 + 11.55 CU) to the same under the per-case
charge (1.35 + 0.995 CU). It is fixed by arithmetic, not by a sweep, so
round-robin makes about as many attempts as in the earlier experiments.

| Arm | Source design | Budgets (CU) | Policies | Seeds |
|---|---|---|---|---|
| S-v1 | exp-004 (catalog v1, suite v1) | 330, 1320, 2640 | 7 | 1001–1100 |
| S-v2 | exp-006 (catalog v2, suite v2) | 330, 1320, 2640 | 7 | 1001–1100 |
| S-v2ff | exp-006 + `--fail-fast` | 330, 1320, 2640 | 7 | 1001–1100 |
| D-v2 | exp-007 (catalog v3, suite v2) | 660, 2640 | 6 | 3001–3100 |

That is 6,300 + 1,200 = 7,500 audited runs. The metric is
`sim_true_solved`. Comparisons are paired by (policy, seed) with the frozen
`analysis.py` bootstrap (10,000 replicates, seed 26102026).

## Frozen inputs

Harness commit `c32d8eb597f30d29dcbeffb83e3c678262dc29ba`:

| File | SHA-256 |
|---|---|
| `research/preregistration/exp-010/make_configs.py` | `fa59c45b75d29335929873ec991a27526957f824c81b49d4d7b97ec5735952f7` |
| `research/preregistration/exp-010/evaluate.py` | `a5df3e5c7fcd9996401548618ad11271e79d833aae8f538233485b5c54028fa7` |
| `research/preregistration/exp-010/S-v1-b330.json` | `27a077c8c4c1f9cd896684709b81a944f61ca11efe468952a385ba8d89ce0dc8` |
| `research/preregistration/exp-010/S-v1-b1320.json` | `45ac08fc21262965b8399c9a15c5bc630f7d30ffe484168ef3b2f6432477e265` |
| `research/preregistration/exp-010/S-v1-b2640.json` | `e1ee54f6cfebbaff80ac2cf677edc7932da2b14a9a3950501f0e5bed9dfd4fa5` |
| `research/preregistration/exp-010/S-v2-b330.json` | `698d1e94a64659f8f38beedc84caacd3840fbf0f8a91f74c5e6a3986f57c9653` |
| `research/preregistration/exp-010/S-v2-b1320.json` | `f4663649418147b68189ea980c55c12a364f3459a77d88f9076d2f8954dc9ceb` |
| `research/preregistration/exp-010/S-v2-b2640.json` | `6dd97747c340304b523509183f5bb479577e4b1fa0007bb1c7fbe818116f4561` |
| `research/preregistration/exp-010/S-v2ff-b330.json` | `63838a81269e25ded3deb9ba6aa44f26f4726c5ebdb6bfef0a5b33779aa29327` |
| `research/preregistration/exp-010/S-v2ff-b1320.json` | `83dc2ba7346e5a6a7ff6a1c69082dd6dc1ca3c42fa3db2b9cd6363856ec170dd` |
| `research/preregistration/exp-010/S-v2ff-b2640.json` | `c725ee2bc60873e4daaba1b7eb74ffbdc6961096a3ef8aa3b0bcf9c87f2bf1b8` |
| `research/preregistration/exp-010/D-v2-b660.json` | `dd2f6ded578f672101eea65c846759cae8b806a14bc3d10aabfc42a1240e1198` |
| `research/preregistration/exp-010/D-v2-b2640.json` | `6036bb8986682c1988016472333301c3f2186c3bddf7a4d84482acbdc00264ea` |
| `python/frontier_py/realtasks/server.py` | `72ff87cfae3a07ca7fd36136cab289f85fb753110b496d47b079280fa1f115c7` |
| `python/frontier_py/analysis.py` | `fbbf32e21c9cb5e9814820f7a0dc76e4ed7d1490a773256556fc6bced5661a0c` |

## Seen before freezing (disclosed)

- **The charge constants**, derived from exp-009's published data.
- **A dev smoke run** of S-v2-b330 and D-v2-b660 (round-robin, dev seed 1,
  one run each) to check that reservations and charges work. Only the
  accounting fields were looked at, not solve counts:
  - S-v2-b330: 25 attempts, 288.7 of 323.5 committed CU on verification;
  - D-v2-b660: 49 attempts, 566.5 of 651.8 CU on verification.
- **A scoring-script check:** `evaluate.py` was run on exp-004/006/007/008
  data relabelled as exp-010 arms. It reproduced the published per-case
  numbers (−3.93, +2.78, +3.41).

## Predictions

- **G1: the stronger suite no longer costs yield.** At S-b330, round-robin
  v2 − v1 > −1.0 (point estimate). Under the per-case model it was −3.93.
  Reason: v2 now costs only 7% more per verification.
- **G2: fail-fast charging stops mattering.** At S-b330,
  |round-robin v2ff − v2| < 0.75 (point). Under the per-case model it was
  +2.78.
- **G3: adaptive allocation gains more.** At S-b330 (v2), hinted Thompson
  − round-robin has CI > 0 and point > +1.86 (exp-004's per-case margin).
  Reason: every failed verification now costs about 11 CU, so avoiding
  hopeless tasks saves more. exp-006 found a larger margin when
  verification was expensive.
- **G4: the dependency-task gain holds.** At D-b660, hinted Thompson −
  round-robin has CI > 0.
- **G5: verdict quality is unchanged.** No run with suite v2 (S-v2, S-v2ff,
  D-v2) has a false solve; at least one S-v1 run does.
- **G6: verification dominates compute.** Round-robin's verification share
  at S-b330 (v2) ≥ 0.80.

## Decisions

**Suite cost:**
- "No longer costs yield" if G1 holds.
- "Still costs yield" if the CI upper bound of round-robin v2 − v1 at
  S-b330 is < −1.0.
- "Unclear" otherwise.

**Allocation:**
- "Robust to measured cost" if hinted Thompson − round-robin has CI > 0 at
  both S-b330 (v2) and D-b660.
- "Not robust" if either CI lies entirely below 0.
- "Mixed" otherwise.

## Invalidation

The pilot is invalid if any of these occur:

- an audit failure;
- `source_dirty` is true;
- a config or catalog hash mismatch;
- a service protocol error.

## Limits

- **One host's cost:** the measured cost is this host's (Windows). On a
  host with cheap process start-up, the fixed term would be smaller.
- **Unconditional verification:** the DSL worker submits a candidate even
  when no sample matched the visible examples. Under the measured charge
  that costs a full verification. A visible-example gate is a design
  change, left for later.
- **Budgets:** are scaled by arithmetic. Saturation points may not line up
  exactly with the earlier experiments.
- **Worker, tasks and verifier:** non-LLM worker, tasks written by the
  project, V1 verifier.
