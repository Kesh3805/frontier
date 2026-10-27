# exp-009: Does fail-fast verification save measured compute, or only modelled compute?

Status: **FROZEN** before any exp-009 outcome was generated. The scoring
script [`evaluate.py`](evaluate.py) is frozen with this protocol.
Kind: **measurement study, real tasks** (non-LLM DSL worker; trust class
V1). Not confirmatory: the predictions are informed by a disclosed dev
smoke run.

## Why

exp-008 found that charging a failing verification only for the cases up
to its first failure recovers 71–96% of the yield the 199-check suite cost.
But that charge is a model: 0.005 CU per case, nothing for process start-up
or expected-output computation. And the verifier did not actually stop
early; it ran every case and only charged less. So exp-008 shows what fail-
fast would buy *if* verification cost were linear in cases run. This
experiment measures whether it is.

## What changed for this experiment

`verify(early_stop=True)` (service flag `--early-stop`) makes fail-fast
physical. The child streams each output as it computes it; the parent
computes the expected output for that case, compares at once, and on the
first mismatch stops reading, so the child exits at its next write (or is
killed after 1 s). Verdicts and fail-fast charges are unchanged (tested);
the child still never sees an expected value. The verifier also reports the
child's CPU time on Windows now (GetProcessTimes, 15.6 ms ticks).

## Frozen inputs

Harness commit `9647db1bc77f52ffdcedc5d5befc253a81a3b0bf`:

| File | SHA-256 |
|---|---|
| `research/preregistration/exp-009/measure.py` | `b7aa58b07c283b89782eba12630413a5d997ef54e8471d90c7e2c388410190f1` |
| `research/preregistration/exp-009/evaluate.py` | `e33499ba52b1a6350dbb5b5f568aa7bf142e823bf31a7c9b18c6d466775199fd` |
| `research/preregistration/exp-009/make_configs.py` | `5a161f663d7953168fbf13e742030642f5c35ae471b367c2b504032485a2a308` |
| `research/preregistration/exp-009/C-E1.json` | `fefcadf69ea934e9a0c54a9bf1ed51a5d2260f238e6199821119c79f43d85b2c` |
| `research/preregistration/exp-009/C-F1.json` | `273f3aee7c6fe5b6e396e19954c4f00bb282d61f07e471da1ffdccf12709e7c0` |
| `research/preregistration/exp-009/C-F2.json` | `2495382c0ddb5671c454cc1b24ec7e87f94ef49840cbe83e7c6ebfdb97c94c29` |
| `research/preregistration/exp-009/C-E2.json` | `d95e2d6b8ab48a1885f70734e9800c8128e6e5ed4f539bc9494095903dabbf1e` |
| `python/frontier_py/verifiers/property_tests.py` | `e0e9615c95b2cd1840608593aa6e1d3d50912cbbffb05d0174f7628f720191cb` |
| `python/frontier_py/realtasks/server.py` | `c7ab18916c0ef94b12712639cf542baf7cd525d5ac2a3850d8b1c8d549ece33e` |
| `python/frontier_py/realtasks/worker.py` | `73278e8bc05fd8be042a5b6c7bd7f822d854bca3b075d5e2a678e92643fa54e7` |
| `python/frontier_py/realtasks/suite.py` | `3a7cc086906b2c18a61e38fe5dcaf104711e6ef10a0d64ad973adf30b9a88d97` |

## Design

**Part M (primary): per-candidate measurement.**

- **Corpus:** the DSL worker's attempts k = 0–3 at seeds 9001–9020 (disjoint
  from every earlier seed) on all 34 catalog-v2 single-step tasks: 2,720
  attempts, 1,257 unique (task, source) candidates. Corpus size and status
  mix were checked before freezing; no candidate was verified.
- **Modes:** F = full execution with fail-fast charging (exp-008's
  verifier); E = early stop. Hidden suite v2 (199 checks).
- **Procedure:** one process, sequential. 20 warm-up verifications are
  discarded. Candidate order is shuffled once (seed 9009); each candidate
  is measured 3 times per mode, with mode order shuffled per repetition.
- **Per call:** wall seconds around `verify` (hidden-input generation,
  expected outputs, process start, run, comparison), parent CPU, child CPU,
  verdict, charge. The worker's attempt wall time is recorded once per
  attempt (descriptive only).
- **Per candidate:** median over repetitions.

**Part C (secondary): campaigns.** exp-008's S-b60 config (700 runs: 7
policies × 100 seeds) with the service in mode E or F, run in the order
E1, F1, F2, E2 on the same day. Measured verification wall time comes from
the manifests, so it includes 8-way concurrency.

**Host:** this Windows 11 machine (x86-64, 8 threads), otherwise idle.

## Quantities (all in `evaluate.py`)

- **S_meas_fail:** 1 − Σ t_E / Σ t_F over candidates that FAIL, with a 95%
  CI from a bootstrap that resamples tasks (10,000 replicates, seed
  26102026).
- **S_mod_fail:** the same saving under the charge model,
  1 − Σ fail-fast charge / Σ full charge (0.995 CU).
- **S_meas_all, S_mod_all:** both savings over all candidates.
- **Fixed share:** fit t_E = a + b · (cases run) by OLS over all candidates.
  The fixed share is a / (a + 199·b), the part of a full verification that
  does not depend on how many cases run. Bootstrap CI as above.
- **PASS ratio:** median t_E / t_F over PASS candidates (streaming
  overhead).
- **Campaign saving:** 1 − (E1 + E2) / (F1 + F2) in verification wall
  seconds; identical outcomes per (policy, seed) across all four runs.

## Seen before freezing (disclosed)

- **Dev smoke run:** dev seed 1, k = 0–2, 102 candidates, once per mode,
  under ordinary desktop load. Total wall: full execution and full charge
  10.76 s, F 10.52 s, E 10.26 s. That is about 100 ms per verification and
  about 2–5% saved by early stop. Verdicts agreed in all three modes, and
  F and E charges were identical.
- **CPU-time checks:** Python start-up shows as 0 CPU at Windows' 15.6 ms
  granularity; a 10M-iteration loop showed 0.59 s.
- **Prior data:** exp-008's manifests report summed verification wall time
  per campaign set, for example 2,077 s for S-b60. Fail-fast there was
  charge-only, so it says nothing about early stop.
- **Script check:** `evaluate.py` was run on synthetic data with a known
  fixed cost (0.0825 s) and per-case cost (1e-4 s), and recovered both.

## Predictions

- **M1:** measured saving on FAIL candidates is small: CI upper bound
  < 0.25.
- **M2:** the charge model overstates it: S_mod_fail − S_meas_fail ≥ 0.40.
- **M3:** fixed overhead dominates: fixed share ≥ 0.75.
- **M4:** streaming costs PASS candidates little: PASS ratio in
  [0.90, 1.10].
- **M5:** E and F agree on every candidate's verdict and charge, and all
  four campaign runs have identical outcomes for every (policy, seed).
- **M6:** campaign measured saving < 0.25.

## Decision

- **"Modelled fail-fast saving does not hold physically on this
  harness"** if M1 and M2 hold. exp-008's recovery then reflects the charge
  model, and measured verification cost is mostly per-call overhead.
- **"Holds physically"** if the CI lower bound of S_meas_fail is at least
  half of S_mod_fail.
- **"Partial"** otherwise.

## Invalidation

The study is invalid if any of these occur:

- `source_dirty` is true in any manifest;
- a hash mismatch;
- a service protocol error;
- an audit failure in part C;
- the machine was visibly loaded by other work (logged and disclosed).

## Limits

- **One host:** process start-up is far cheaper on Linux, so the fixed
  share is host-specific. The result is about this harness on this machine,
  not about verification in general.
- **Candidates:** DSL candidates are tiny programs; per-case cost is small.
  LLM-written programs, or heavier tasks, would shift weight to the
  per-case term.
- **Execution:** inputs are still sent to the child all at once and
  generated up front; only execution and expected-output computation stop
  early.
- **Timing:** wall time on a desktop OS is noisy. Medians of 3 repetitions
  and interleaved modes reduce, but do not remove, drift.
