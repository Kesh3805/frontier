# exp-009L results: exp-009's measured cost of verification, on Linux

**Kind: MEASUREMENT STUDY, REAL TASKS, SECOND HOST.** This is a
replication of exp-009 part M on a GitHub-hosted Linux runner. Same
harness, same 1,257 held-out DSL candidates, same suite v2 (199 checks).
Trust class V1. Not confirmatory: the predictions were informed by
exp-009's Windows result.

**Protocol:** [`research/preregistration/exp-009L/`](../../research/preregistration/exp-009L/protocol.md),
frozen and merged to `main` as `0c58003` before any Linux timing was
generated.

**Run:** [actions run 41706743779](https://github.com/Kesh3805/frontier/actions/runs/41706743779),
attempt 1, the only dispatch. It was triggered by `workflow_dispatch` from
`0c58003`. It measured exp-009's own run commit `bad09c9` with a clean tree
and passed every frozen hash check. All invalidation checks were false.
Measurement took 4 minutes: 1,257 candidates × 2 modes × 3 repetitions,
7,542 timed verifications.

**Host:**

| | |
|---|---|
| Runner image | `ubuntu24` 20261026.354.1, Ubuntu 24.04.5 LTS, kernel 7.0.0-1017-azure |
| CPU | AMD EPYC 7763, 4 logical CPUs, 16 GB |
| Python | 3.12.15 (GCC 13.3.0) |
| Load average | 0.55 before measuring, 1.12 after (1-minute) |

Data:
- [`evaluation.json`](evaluation.json): `score.py` output as produced on the
  runner, and identical when re-scored locally from the downloaded data;
- [`manifests.json`](manifests.json): the `measure.py` manifest, `runner.json`
  and the run link;
- `M-measurements.jsonl.gz`, `M-corpus.jsonl.gz` and `M-attempts.jsonl.gz`;
- [`explore.py`](explore.py): the exploratory breakdown below. It is not
  frozen.

## Scorecard

| Prediction | Result |
|---|---|
| L1: fixed cost a ≤ 0.06 s on Linux | ✔ 25.2 ms (Windows 120.5 ms) |
| L2: fixed share CI upper < Windows' 0.9215 | ✔ 0.880 [0.877, 0.883] |
| L3: measured FAIL saving, CI lower > Windows' CI upper 0.078 | ✔ 33.6% [32.9, 34.1] |
| L4: same corpus; same verdict and charge as Windows for every candidate | ✔ 1,257 / 1,257 |
| exp-009 M1 on Linux: FAIL saving CI upper < 0.25 | ✘ 0.341 |
| exp-009 M2 on Linux: modelled − measured ≥ 0.40 | ✔ 92.9% − 33.6% = 59 points |
| exp-009 M3 on Linux: fixed share ≥ 0.75 | ✔ 0.880 |
| exp-009 M4 on Linux: PASS ratio in [0.90, 1.10] | ✘ 0.752 (E is *cheaper*) |
| exp-009 M5 on Linux: F/E verdicts and charges agree | ✔ 0 disagreements, 0 mismatches |
| **Decision** (frozen rule: M1–M3 all hold → generalises; M1 and M3 both fail → host-specific) | **Partial** |

My predicted decision, "host-specific", was **wrong**. I expected the
fixed share to fall below 0.75. It fell only to 0.88, because the per-case
cost fell with it (3×) as well as the fixed cost (4.8×). The early-stop
saving did grow, as predicted, past the 25% bound. exp-009's own decision
rule, evaluated on Linux, also gives "partial".

## Windows vs Linux

| | Windows (exp-009) | Linux (exp-009L) |
|---|---|---|
| Fixed cost a (fit on t_E) | 120.5 ms | 25.2 ms |
| Per-case cost b | 0.052 ms | 0.017 ms |
| Fixed share of a full verification | **0.92** [0.86, 0.97] | **0.88** [0.877, 0.883] |
| Mean wall time, F (full execution) | 129.5 ms | 38.2 ms |
| Mean wall time, E (early stop) | 123.1 ms | 26.0 ms |
| Measured saving, FAIL candidates | **6.4%** [5.1, 7.8] | **33.6%** [32.9, 34.1] |
| Measured saving, all candidates | 5.0% | 31.9% |
| Modelled saving, FAIL candidates | 92.9% | 92.9% |
| PASS ratio t_E / t_F (median) | 1.003 | 0.752 |
| Verification share of measured compute (F) | 0.90 | 0.81 |

The Linux CIs are much narrower than Windows'. That reflects a quieter,
faster run and no visible drift: median F was 38.2 ms in both the first
and last quarter, and E 25.4 ms. By contrast, exp-009 drifted about 10%
down over 16 minutes.

## What the Linux saving is made of (exploratory)

M4's failure points to a mechanism the protocol did not anticipate. On
Linux, early stop makes **PASS candidates 25% cheaper**, though they run
every case. The code at `bad09c9` explains why:

- **Mode F** (`property_tests.verify`, `early_stop=False`) computes all 199
  expected outputs in the parent *before* starting the child.
- **Mode E** computes each expected output lazily, in the thread that reads
  the child's stream. That work then overlaps the child's start-up.

Mode E therefore differs from F in two ways: it **pipelines** the parent's
work with the child, and it **stops** early.

`explore.py` separates the two roughly. It applies the same median-of-3
per-candidate times and computes means over candidates.

| | Windows | Linux |
|---|---|---|
| PASS candidates: F → E | 130.8 → 132.2 ms | 38.1 → 28.7 ms (−9.5 ms) |
| FAIL candidates: F → E | 129.2 → 121.0 ms | 38.2 → 25.4 ms |
| FAIL candidates stopped at case 1 (705 of 1,020): t_E | 121.0 ms | 25.2 ms |
| FAIL saving left after discounting the PASS ratio | 6.7% | 11.6% |
| Median parent CPU per call, F / E | 0 / 0 ms (15.6 ms ticks) | 6.0 / 3.0 ms |

On Linux, roughly a quarter of F's wall time is parent-side work that E
hides behind process start-up. Stopping proper accounts for about 12
points of the 34. On Windows, the overlap does not show (PASS ratio
1.003). Why is not established: the parent's work there is below CPU-tick
resolution, and a 120 ms `CreateProcess` start-up dwarfs it. This decomposition is post hoc
and approximate. It assumes the pipelining gain scales the same way on
FAIL as on PASS candidates.

## What it shows, and what it doesn't

1. **The headline direction generalises; the magnitude is host-specific.**
   On both hosts, a verification is mostly fixed per-call overhead (92%
   and 88%), and the per-case charge model overstates the early-stop
   saving by 59–87 points (93% modelled against 6% and 34% measured). Absolute cost differs about 3.4× (130 ms against 38 ms per
   full verification).
2. **"Early stop saves about 6%" is Windows-specific.** On Linux it saves
   about a third. Most of that comes from overlapping the parent's
   expected-output work with child start-up, not from running fewer cases.
   The same overlap could be added to full execution: compute expected
   outputs while the child starts. That would make F cheaper too.
3. **The fixed share is stable across hosts:** 0.88–0.92. Faster process
   start-up on Linux came with faster per-case work on the EPYC core, so
   the ratio barely moved. A measured cost model a + b·cases needs
   host-specific a and b, but the conclusion that a dominates held on
   both.
4. **Verification is host-independent in outcome.** The corpus, every
   verdict and every fail-fast charge were identical to Windows for all
   1,257 candidates.

## Limits

- **Two hosts:** one Windows desktop and one shared Linux cloud VM. That is
  not a population. macOS, other CPUs and the V2 docker sandbox (which adds
  `docker run`) are untested.
- **Noisy VM:** the runner is a shared virtual machine. Load stayed low
  (0.55 → 1.12) and no drift was visible, but tenant noise cannot be ruled
  out.
- **Old verifier:** this measured `bad09c9`, exp-009's harness. Later
  verifier changes on `main`, such as #17's early-stop robustness fixes,
  are not covered.
- **Post-hoc decomposition:** the pipelining-versus-stopping split is
  exploratory. A frozen follow-up would need a third mode: full execution
  with expected outputs computed concurrently.
- **Per-group Windows means:** `explore.py`'s Windows per-group means
  (PASS 130.8 / 132.2 ms, FAIL 129.2 / 121.0 ms) differ from exp-009's
  README table (PASS 133.3 / 133.4, FAIL 131.8 / 124.1). The README's
  figures are not consistent with its own all-candidate means: both
  groups exceed the overall 129.5 / 123.1 ms. The frozen quantities in
  exp-009's `evaluation.json` are unaffected and match this
  recomputation's totals.
