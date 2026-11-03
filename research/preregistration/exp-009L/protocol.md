# exp-009L: Is exp-009's measured cost of verification specific to Windows?

Status: **FROZEN** before any exp-009L timing was generated. The scoring
script [`score.py`](score.py) and the workflow
[`.github/workflows/exp-009l.yml`](../../../.github/workflows/exp-009l.yml)
are frozen with this protocol.
Kind: **measurement study, real tasks, replication on a second host**
(non-LLM DSL worker; trust class V1). Not confirmatory: the predictions are
informed by exp-009's Windows result.

## Why

exp-009 part M measured 1,257 held-out DSL candidates on one Windows 11
desktop. A verification cost about 120 ms fixed plus 0.05 ms per case run,
so the fixed share of a full 199-check verification was 0.92 [0.86, 0.97].
Stopping at the first failing case saved 6.4% [5.1, 7.8] of wall time on
failing candidates, against 92.9% under the modelled per-case charge.

exp-009 itself named the main limit: process start-up is slow on Windows.
This experiment repeats part M on a GitHub-hosted Linux runner to see
whether "verification cost is mostly fixed overhead; early stop saves
little" is a property of the harness or of the host.

## What runs

Nothing in the measured harness changes. The workflow checks out two trees:

- **The measured harness:** exp-009's own run commit,
  `bad09c9f497524c1ee6fc7146b4a541b4fbf9667`, checked out into `src/`.
  `measure.py` runs from there unchanged: same corpus, seeds, modes,
  repetitions, warm-up and order seed. When this protocol was written, the
  hash-checked harness files were identical at `bad09c9` and on `main`.
  By inspection, `measure.py` needs no change for Linux; it was not run
  there before freezing. Its only OS-dependent call,
  `platform.processor()`, may return an empty string there, which is
  harmless. The verifier's POSIX path is covered by CI's Linux unit tests.
- **The scoring tree:** the commit the workflow is dispatched from, which
  carries this protocol, `score.py` and the Windows baseline in
  `results/exp-009/`.

`score.py` imports exp-009's frozen `evaluate.py` and calls its functions
unchanged: `per_candidate`, `saving`, `ols`, `fixed_share` and `boot`
(tasks resampled, 10,000 replicates, seed 26102026). It recomputes the
same part-M output fields. Part C, the campaigns, is not replicated. It
adds a drift summary, the invalidation checks, a comparison with Windows
and the verdicts below.

## Frozen inputs

LF blobs at the freeze commit, hashed as `git show HEAD:path | sha256sum`.
Before measuring, the workflow checks [`SHA256SUMS`](SHA256SUMS), which
lists every file below except the workflow. It checks the harness entries
in the measured tree (`src/`, at `bad09c9`). It checks the scoring entries
(`score.py`, exp-009's `evaluate.py` and the Windows baseline) in the
scoring tree. The harness hashes are the ones exp-009 froze.

| File | SHA-256 |
|---|---|
| `research/preregistration/exp-009/measure.py` | `b7aa58b07c283b89782eba12630413a5d997ef54e8471d90c7e2c388410190f1` |
| `python/frontier_py/verifiers/property_tests.py` | `e0e9615c95b2cd1840608593aa6e1d3d50912cbbffb05d0174f7628f720191cb` |
| `python/frontier_py/realtasks/server.py` | `c7ab18916c0ef94b12712639cf542baf7cd525d5ac2a3850d8b1c8d549ece33e` |
| `python/frontier_py/realtasks/worker.py` | `73278e8bc05fd8be042a5b6c7bd7f822d854bca3b075d5e2a678e92643fa54e7` |
| `python/frontier_py/realtasks/suite.py` | `3a7cc086906b2c18a61e38fe5dcaf104711e6ef10a0d64ad973adf30b9a88d97` |
| `research/preregistration/exp-009/evaluate.py` | `e33499ba52b1a6350dbb5b5f568aa7bf142e823bf31a7c9b18c6d466775199fd` |
| `research/preregistration/exp-009L/score.py` | `06a7cc8f13492cacbef760b61e95ee94eb1616b4f7523d20901752dbd1a1b0b1` |
| `results/exp-009/evaluation.json` | `5bd196c524512ecb10fba00191ddfcad95798e74f8ed6295665350b1266cc381` |
| `results/exp-009/M-measurements.jsonl.gz` | `d2022bfeac125e9a01f51bac4be5b8df5294d53401055ba69ed6413aff6dbd78` |
| `results/exp-009/M-corpus.jsonl.gz` | `ceaaeef7895f814a1701c9287574b133c8e131716d4b75451342027e83284651` |
| `.github/workflows/exp-009l.yml` | `cd215c667fb73185478e3adec2f49c76b61e5b60cbcd6f93d3be15b1b763949d` |

## Host

The host is a GitHub-hosted runner with the `ubuntu-24.04` label, a shared
VM. Python 3.12 comes from `actions/setup-python`, the same as `ci.yml`.
The workflow writes `runner.json` with these fields:

- runner image name and version (`ImageOS`, `ImageVersion`);
- CPU model, logical CPU count, memory, kernel and OS release;
- Python version, workflow commit, measured ref, run id and attempt,
  triggering event;
- load average before and after measurement.

The image, CPU model and Python version are not known before the run. They
are reported from that file in the results.

**Shared runners are noisy.** The VM shares a physical host with other
tenants, its CPU model varies between runs, and nothing can make it idle.
exp-009 ran on an otherwise idle desktop. Noise mainly widens the CIs. The
F/E comparison is protected by the same design as on Windows: modes are
interleaved per repetition in shuffled order, and each candidate's median
of 3 repetitions is used. Drift is reported as median F and E time in the
first and last quarter of measurement order.

## Procedure

1. Merge this protocol, `score.py`, `SHA256SUMS` and the workflow to `main`
   through a PR with passing CI.
2. Dispatch the workflow once, from `main` at the merge commit, with
   `ref = bad09c9f497524c1ee6fc7146b4a541b4fbf9667`. The workflow takes no
   other input.
3. The workflow checks hashes, records the runner, runs
   `measure.py runs/exp-009L/M`, scores, and uploads `runs/exp-009L/` as
   artifact `exp-009L`.
4. The first run that completes measurement is the run that is scored.
   Re-dispatching is allowed only if a run fails before `measure.py` has
   written `manifest.json`, for example on runner loss, timeout or a
   portability error. Every dispatch is disclosed. No run is repeated once
   its timings exist.

## Quantities

These are exp-009's part-M quantities, computed by its `evaluate.py`
functions. Here t is a candidate's median wall time over 3 repetitions.
F is full execution with fail-fast charging; E is early stop.

- **S_meas_fail:** 1 − Σ t_E / Σ t_F over FAIL candidates, with a 95%
  task-cluster bootstrap CI.
- **S_mod_fail:** 1 − Σ fail-fast charge / Σ full charge.
- **S_meas_all and S_mod_all:** the same over all candidates.
- **Fit:** the OLS fit t_E = a + b · (cases run). The fixed share is
  a / (a + 199·b), with a bootstrap CI.
- **PASS ratio:** median t_E / t_F over PASS candidates.
- **S_cpu_fail and the measured verification share:** descriptive only.
  `measure.py` never passes a `stats` dict, so child CPU is null on every
  host, and S_cpu_fail measures only the parent.

**Comparison with Windows:** a table pairing each quantity with
`results/exp-009/evaluation.json`, plus the Linux/Windows ratios of a and
b. It also records whether the candidate corpus is identical, and how many
candidates have the same verdict and charge as on Windows.

## Seen before freezing (disclosed)

- **Windows data:** all of exp-009's results.
- **Script check:** `score.py` was run on exp-009's own Windows data,
  decompressed from `results/exp-009/`. It reproduced every field of
  exp-009's `evaluation.json` part-M block exactly. Its drift output, F
  0.130 → 0.117 s and E 0.125 → 0.110 s, matched exp-009's README. Its
  invalidation check correctly flagged "not Linux".
- **No Linux timing of this harness was looked at.** The repository's CI
  runs the verifier's unit tests on `ubuntu-24.04`. Their durations were
  not inspected, and they time no verification.

## Predictions, with reasons

**Reasons.** On Windows, nearly all of the ~120 ms fixed cost is starting a
fresh interpreter (`python -I -S -c <harness>`) through `CreateProcess`.
The parent's own fixed work is small: about 3 ms of CPU for
expected-output computation in mode F. On Linux, fork plus exec of a
`-I -S` interpreter typically takes 10–25 ms. The harness also sets
rlimits in `preexec_fn`, which forces the slower fork path. I therefore
expect a ≈ 15–40 ms. The per-case work is pure Python in both processes.
It should cost about the same per case on a comparable x86-64 core, so
b ≈ 0.03–0.10 ms.

With a ≈ 25 ms and b ≈ 0.06 ms, the fixed share is about 0.68. Failing
candidates run 14.1 cases on average under early stop, so the saving is
about 185 · b / (a + 199 · b) ≈ 0.30. The charge model's 92.9% is
unchanged, because charges are deterministic.

| ID | Prediction | Threshold (frozen) |
|---|---|---|
| L1 | The fixed cost is much smaller on Linux. | a ≤ 0.06 s |
| L2 | The fixed share is lower than on Windows. | CI upper bound < 0.9215 |
| L3 | Early stop saves more than on Windows. | S_meas_fail CI lower bound > 0.0779 |
| L4 | The work is host-independent. | The Linux corpus is identical to exp-009's, and every candidate has the same verdict and fail-fast charge as on Windows. |

exp-009's own criteria are applied to the Linux data unchanged:

- **M1:** S_meas_fail CI upper bound < 0.25. Predicted to **fail** on
  Linux.
- **M2:** S_mod_fail − S_meas_fail ≥ 0.40. Predicted to **hold**: even a
  30–50% saving leaves the model overstating it by 40 points or more.
- **M3:** fixed share ≥ 0.75. Predicted to **fail**.
- **M4:** PASS ratio in [0.90, 1.10]. Predicted to hold.
- **M5:** zero F/E verdict disagreements and charge mismatches. Predicted
  to hold.

**Predicted decision:** "host-specific". The main alternative is
"partial", if the fixed cost stays above about 50 ms or b is smaller than
expected.

## Decision (frozen)

The decision uses exp-009's M1–M3 on Linux:

- **"Windows result generalises"** if M1, M2 and M3 all hold on Linux. A
  verification is then still mostly fixed overhead (≥ 75%), and early stop
  still saves little (CI upper bound < 25%).
- **"Host-specific"** if both M1 and M3 fail. The overhead share falls
  below 75%, and the measured saving's CI reaches 25% or more.
- **"Partial"** otherwise.

`score.py` also reports exp-009's own decision rule evaluated on Linux,
for reference.

## Invalidation (frozen)

The run is invalid, and is reported as invalid with its numbers, if any of
these hold:

- `source_dirty` is true, or `source_commit` is not `bad09c9…`;
- any `SHA256SUMS` check fails in either tree;
- `manifest.json`'s `measurements_sha256` does not match the file;
- the measurements are incomplete (rows ≠ candidates × 3 × 2);
- the host is not Linux x86-64, or Python is not 3.12.x;
- the run was not triggered by `workflow_dispatch`, or its workflow commit
  is not the merge commit of the freeze PR;
- a verifier or harness error aborts `measure.py`, in which case there is
  no scored run and the re-dispatch rule above applies.

Runner noise is not an invalidation criterion: it cannot be detected
reliably on a shared VM. The drift summary and load averages are reported
instead.

## Limits

- **Second host only:** one Windows desktop and one Linux cloud VM is two
  hosts, not a population. Other Linux hosts, macOS, or containers (the V2
  docker sandbox adds `docker run`) will differ.
- **Noisy VM:** the timings come from a shared virtual machine, not an
  idle bare-metal host.
- **Same candidates:** these are tiny DSL programs. Heavier candidates
  shift weight to the per-case term on any host.
- **Part C not replicated:** campaign outcomes are deterministic. exp-009
  showed early stop does not change them, and campaign timing was
  uninformative there.
