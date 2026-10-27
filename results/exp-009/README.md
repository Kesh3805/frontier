# exp-009 results: measured cost of fail-fast verification

**Kind: MEASUREMENT STUDY, REAL TASKS.** The worker is a non-LLM DSL search;
the verifier is trust class V1 with hidden suite v2. One Windows 11 host
(x86-64, 8 threads). Not confirmatory: the predictions were informed by a
disclosed dev smoke run.

**Protocol:** [`research/preregistration/exp-009/`](../../research/preregistration/exp-009/protocol.md),
frozen at `9647db1` and merged to `main` as `bad09c9`. Every run in this
study used `bad09c9` with a clean tree.

- **Part M:** 1,257 held-out candidates × 2 modes × 3 repetitions, 7,542
  timed verifications in 16 minutes.
- **Part C:** 4 × 700 audited campaigns.

Data:
- [`evaluation.json`](evaluation.json) and [`manifests.json`](manifests.json);
- `M-measurements.jsonl.gz`, `M-corpus.jsonl.gz` and
  `M-attempts.jsonl.gz`;
- `C-runs.csv.gz`.

## Scorecard

| Prediction | Result |
|---|---|
| M1: measured saving on FAIL candidates is small (CI upper < 0.25) | ✔ 6.4% [5.1, 7.8] |
| M2: the charge model overstates it by ≥ 40 points | ✔ modelled 92.9% vs measured 6.4% |
| M3: fixed overhead is ≥ 75% of a full verification | ✔ 92% [86, 97] |
| M4: streaming costs PASS candidates within 10% | ✔ median ratio 1.003 |
| M5: same verdicts, charges and campaign outcomes | ✔ 1,257/1,257 candidates; 4 × 700/700 runs identical |
| M6: campaign measured saving < 0.25 | ✔ formally (−66%), but uninformative; see below |
| **Decision** | **The modelled fail-fast saving does not hold physically on this harness** |

## Part M: what a verification actually costs

| | Full execution (F) | Early stop (E) |
|---|---|---|
| Mean wall time, all candidates | 129.5 ms | 123.1 ms |
| Mean wall time, FAIL candidates (1,020) | 131.8 ms | 124.1 ms |
| Mean wall time, PASS candidates (237) | 133.3 ms | 133.4 ms |
| Modelled charge, FAIL candidates | 0.995 CU | 0.071 CU (mean 14.1 cases) |

The fitted cost of an early-stopped verification is about 120.5 ms of fixed
cost plus 0.05 ms per case run. The fixed part covers process start-up,
hidden-input generation and the harness. A full 199-check verification
therefore spends about 92% of its time on overhead that early stop cannot
remove.

Half of the failing candidates fail on their very first case. Even so,
stopping there saves about 8 ms of 132 ms. The charge model, at 0.005 CU
per case and nothing for overhead, says it saves 93%.

**Measured verification share.** One DSL attempt takes 14.6 ms of wall
time. By measured wall time, then, verification is about 90% of the
compute in either mode. Under the charge model it was 4–42% of round-robin's compute in exp-008.
This is descriptive: DSL sampling is far cheaper than an LLM call would be.

**Drift.** Median times drifted down about 10% over the 16 minutes, equally
in both modes (F 130 → 117 ms, E 125 → 110 ms from first to last quarter).
Modes were interleaved per repetition, so the comparison is unaffected.

**CPU time is not usable here.** Child CPU time read 0 in nearly every call.
Windows counts CPU in 15.6 ms ticks, and a child that runs about 120 ms of
wall time mostly waiting on start-up registers no ticks. The CPU-based
saving in `evaluation.json` (`S_cpu_fail` 0.51) is therefore just the
parent's expected-output work: 3.2 → 2.2 ms. It is not a measure of the
candidate's run.

## Part C: campaigns

**Correctness.** All four runs of exp-008's S-b60 design, two with early
stop and two without, produced **identical outcomes for every one of the
700 (policy, seed) runs**. So early stop changes nothing the scheduler
sees.

**Timing.** Summed verification wall times were E1 2,459 s, F1 2,260 s,
F2 2,768 s and E2 5,869 s. The last run took twice as long as the others,
in wall time too (872 s against 396–481 s). Something else was loading the host: the
modes are identical in work, and Part M shows a difference of a few
percent. Neither the protocol nor its invalidation rule anticipated this.
I report the campaign saving (−66%) as frozen, but it measures host drift,
not early stop. Part C's timing is uninformative. Its correctness result
stands.

## What it shows, and what it doesn't

1. **exp-008's yield recovery was a property of the charge model.** On this
   harness, verification cost is dominated by a fixed per-call overhead of
   about 120 ms. Stopping at the first failing case saves 6% of measured
   time, not the 93% the per-case charge implied. A scheduler trading
   attempts against verifications under the real cost would face nearly
   full-price failures.
2. **The modelled cost should change.** A charge of the form
   a + b × (cases run), with a ≈ 0.12 s and b ≈ 0.05 ms on this host, is
   what the data support. exp-006's finding that a 4.6× costlier suite
   cost yield also used the per-case model. Under measured cost, the 199-
   and 43-check suites differ by only about 8 ms per call (156 × 0.05 ms),
   so the stronger suite is nearly free here.
3. **The physical lever is the overhead, not early stopping.** Reusing a
   warm interpreter per task or batching candidates would attack the 92%.
   That needs its own isolation analysis: a persistent child weakens the
   per-candidate process boundary.
4. **Early stop itself is sound and cheap.** Verdicts and charges are
   unchanged everywhere, including the adversarial set in the tests, and
   PASS candidates pay nothing extra (ratio 1.003).

## Limits

- **One host:** process start-up on Windows is slow. On Linux the fixed
  share would be smaller, and per-case costs relatively larger.
- **Candidates:** DSL candidates are tiny programs. Heavier tasks or
  LLM-written code would move weight to the per-case term, where early
  stop helps.
- **CPU time:** unusable at Windows' tick granularity for calls this short.
- **Campaign timing:** confounded by host load, as described above.
- **Timing noise:** wall time on a desktop OS is noisy. Medians of 3
  interleaved repetitions reduce this but do not remove it.
