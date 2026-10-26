# exp-000 results: receipt-driven allocation vs round-robin (simulation)

**Kind: SIMULATION.** Synthetic environment, perfect verifier, no models, no
spend. These results bound what an allocation policy can do in a model of
research attempts. They are not measurements of LLM research agents.

Protocol: [`research/preregistration/exp-000/protocol.md`](../../research/preregistration/exp-000/protocol.md)
(frozen at `9d306f1`; hashes corrected at `3906794`, before any run).
Executed from source commit `3906794e48d4066430f12be366b7424713e7254a`
with a clean tree (`source_dirty: false`). Host: Windows x86_64, Intel
i5-1135G7, 8 threads, 16 GB RAM. Wall time was 39 s (scarce) and 96 s
(moderate), for 24,000 runs. Every run passed the log audit:

- budget never exceeded;
- every acceptance backed by a PASS receipt;
- no problem solved twice;
- charges reconcile with the log.

Reproducibility: re-running `scarce` with 3 threads instead of 8 produced
identical per-run log heads for all 12,000 runs.

## Primary result (preregistered)

`solved` out of 50 problems. Paired difference thompson(k=2, hints) −
round_robin over 200 seeds, with a 95% percentile bootstrap CI.

| Regime | Budget | round_robin | thompson | Δ | 95% CI | Prediction |
|---|---|---|---|---|---|---|
| R0 homogeneous | scarce | 18.45 | 18.86 | +0.41 | [0.05, 0.76] | P0: \|Δ\|<0.5 ✔ |
| R0 homogeneous | moderate | 50.00 | 50.00 | 0 | [0, 0] | P0 ✔ |
| R1 saturated-easy | scarce | 41.34 | 42.38 | +1.04 | [0.79, 1.29] | (none) |
| R1 saturated-easy | moderate | 48.14 | 48.12 | −0.02 | [−0.05, 0] | P1 ✔ |
| **R2 formal-plateau** | **scarce** | 32.56 | 34.02 | **+1.46** | [1.22, 1.70] | P2 ✔ |
| **R2 formal-plateau** | **moderate** | 40.59 | 40.40 | **−0.19** | **[−0.30, −0.09]** | **P2 ✘** |
| **R3 agentic-swe** | **scarce** | 8.47 | 11.62 | **+3.16** | [2.89, 3.42] | P2 ✔ |
| **R3 agentic-swe** | **moderate** | 17.86 | 19.00 | **+1.15** | [0.92, 1.37] | P2 ✔ |
| R4 frontier-hard | scarce | 0.25 | 0.56 | +0.31 | [0.23, 0.39] | P3 ✔ |
| R4 frontier-hard | moderate | 0.97 | 1.46 | +0.49 | [0.38, 0.60] | P3 ✔ |
| **R5 structured** | **scarce** | 10.07 | 23.02 | **+12.95** | [12.54, 13.37] | P2 ✔ |
| **R5 structured** | **moderate** | 35.07 | 36.59 | **+1.52** | [1.27, 1.77] | P2 ✔ |

### Decision: H1-sim is **rejected** under the frozen rule

The rule rejects if any of the six P2 cells has its CI entirely below 0.
R2-formal-plateau at the moderate budget does. The other five P2 cells are
positive, with CIs excluding 0. We do not re-label this outcome. The
accurate statement is:

> In this simulator, receipt-driven Thompson allocation is **not uniformly
> better** than work-conserving round-robin (Zuo et al. Alg. 1, K = 1). It
> helps when the budget is scarce relative to problem difficulty, or when
> problems have multi-step structure. It is slightly **worse** in a
> plateau regime where moderate budget already solves almost every
> solvable problem.

A plausible mechanism, which we have **not** tested, is that hint-driven
priors make the index stop too early on low-p but solvable problems after a
few failures. Round-robin keeps sampling them. The α < 1 fits make such
problems common. This is a hypothesis for exp-001, not a finding.

## Secondary results (descriptive; not preregistered as decisions)

1. **Prior information, not learning, explains most single-step gains
   (P4 not confirmed).** Thompson *without* hints does not beat
   round-robin in R2 or R3 at the scarce budget (R2: +0.03, CI
   [−0.17, 0.23]; R3: −0.40, CI [−0.61, −0.20]). The static
   `greedy_prior` index, which never learns, reaches +2.5 in R3 scarce.
   Learning from receipts adds a modest amount on top of hints. Thompson
   vs greedy_prior is positive, with the CI excluding 0, in 8 of 12 cells
   (+0.23 to +3.1). It is null in R0 (both budgets) and R1 moderate, and
   negative in R4 scarce (−0.11, CI [−0.18, −0.04]). So with real workers, the quality of the difficulty prior may
   matter more than the bandit.
2. **Structure awareness drives the R5 gain.** At the scarce budget,
   greedy_prior gains +12.2 and hint-free Thompson +10.1 over round-robin.
   The expected-remaining-cost index prefers short approach chains;
   round-robin spreads attempts over every obligation of every approach.
   This is the one effect here that is specific to FRONTIER's
   evidence-graph setting. It needs testing on real dependency structure.
3. **Oracle gap.** Even the ground-truth index gains only +0.6 (R2
   moderate) to +17.6 (R5 scarce). In R3 the oracle reaches 15.5 against
   thompson's 11.6 at scarce budget, leaving large headroom for better
   difficulty estimates.
4. **Baseline degeneracy (engineering finding).** `fixed_slice` solves 0
   problems at the scarce budget. Its 3 CU slice per problem is smaller than
   the 8.25 CU worst-case reservation per attempt, so it never dispatches.
   This is a real property of strict slicing under worst-case reservation,
   but it makes fixed_slice a straw man at that budget. Claims against it
   are not made.
5. **Scheduler overhead.** Host-measured mean time per decision:
   round-robin ≈ 1 µs; UCB 20–35 µs; Thompson 80–150 µs (it draws a Beta
   sample for every task on every decision). All are negligible next to
   any real model attempt, but the cost grows with task count, and this
   was measured only at 50 problems.
6. **Hopeless elimination** is roughly neutral in single-step regimes and
   harmful in R5 at the moderate budget (−7.9). Its problem-level success
   statistic is confused by intermediate obligations.

The full tables include FIFO, random, UCB, wasted units and
time-to-first-solve (conditional on both arms solving):

- `*-solved_vs_round_robin.md`
- `*-solved_vs_greedy_prior.md`
- `*-wasted_vs_round_robin.md`
- `*-ttfs_vs_round_robin.md`

## Files

- `*-manifest.json`: config digest, results hash, source commit, host.
- `*-runs.csv.gz`: one row per run. Includes each run's log head, so any
  run can be regenerated and checked with `frontier run` / `frontier audit`.
  The full JSONL outputs (33 MB) are not committed; they regenerate
  bit-for-bit from the frozen configs, except for the host-timing field
  `select_nanos`.

## Limitations

These were accepted in advance in the protocol:

- outcomes are i.i.d. given p;
- cost parameters are unverified;
- hints are noisy truth rather than a real predictor;
- the verifier is perfect;
- one problem count (50) and one worker count (8).

## Implications for the program

- H1 cannot be assumed even in favourable conditions. Any real-worker
  test must include round-robin as the bar, and must report budget
  regimes separately.
- Next simulation question (exp-001): the R2-moderate failure, and whether
  the gains survive correlated attempt failures and imperfect verifiers.
- The structure effect (R5) is the most promising candidate contribution,
  and the most exposed to simulator assumptions. It should be the first
  thing tested with real tasks.
